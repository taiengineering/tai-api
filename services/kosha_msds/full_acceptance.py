"""OBJ-CHEM-FULL-READINESS-005 — FULL acceptance harness (read-only).

Pure orchestration + evidence aggregation. NEVER re-implements a
decision engine. Every stage delegates to an existing collector:

    Stage A  SOURCE_READY
      ops.collect_hydration_status  (P4)
      + queue identity check       (WO §5)
      + WO §4 aggregate gates

    Stage B  FULL_PLAN_READY
      services.kosha_msds.materialize.build_plan output shape
      (CHEM-05) — caller supplies MaterializePlanInputs

    Stage C  MATERIALIZE_READY  (dry-run classification)
      services.kosha_msds.materialize_writer
        preload_existing_state + classify_chemicals + classify_sections
      (CHEM-08) — no write; identity invariants + CONFLICT=0

    Stage D  MATERIALIZED_FULL_READY
      publish_store.find_full_candidate  (P4 store contract)

    Stage E  PUBLISH_READY
      services.kosha_msds.cutover.is_full_ready
      (P2 / CHEM-10) — reuses preflight_publish

    Stage F  SEARCH_RUNTIME_READY
      ops.collect_dictionary_runtime  (P4)

    Stage G  PUBLIC_CUTOVER_READY
      A + B + C + D + E + F + public_mode == seo_preview

State machine (WO §14) — exactly four verdicts:

    WAIT_HYDRATION              source not yet complete (SOURCE_READY = false,
                                                          no integrity violation)
    BLOCKED                     any integrity failure (queue mismatch,
                                                        CONFLICT rows, identity
                                                        regeneration, drift)
    READY_FOR_FULL_MATERIALIZE  A + B + C ready, D not yet materialized
    READY_FOR_FULL_CUTOVER      A..F all ready + public_mode = seo_preview
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from services.kosha_msds.contract import (
    PUBLIC_MODE_SEO_PREVIEW,
    PUBLISH_PUBLISHED_FULL,
)


# WO baseline constants (mirrored from CHEM-04 / CHEM-05).
EXPECTED_QUEUE_ROWS = 329_088
EXPECTED_CHEMICAL_COUNT = 20_568
EXPECTED_SECTION_COUNT = 329_088
EXPECTED_QUEUE_SHA256 = (
    "7eba2dca2e183bab2c09f6260874cf8b5380ccb6d2f4bec61dfd193c881085d9"
)

# Verdict vocabulary (WO §14).
VERDICT_WAIT_HYDRATION = "WAIT_HYDRATION"
VERDICT_BLOCKED = "BLOCKED"
VERDICT_READY_FOR_FULL_MATERIALIZE = "READY_FOR_FULL_MATERIALIZE"
VERDICT_READY_FOR_FULL_CUTOVER = "READY_FOR_FULL_CUTOVER"

# Block reason vocabulary (only fires when we're moving to VERDICT_BLOCKED).
BLOCK_QUEUE_IDENTITY_MISMATCH = "QUEUE_IDENTITY_MISMATCH"
BLOCK_DUPLICATE_SOURCE_PAIR = "DUPLICATE_SOURCE_PAIR"
BLOCK_SOURCE_CONTRACT_FAILURE = "SOURCE_CONTRACT_FAILURE"
BLOCK_NOT_FULL_PLAN = "NOT_FULL_PLAN"
BLOCK_CHEMICAL_CONFLICT = "CHEMICAL_CONFLICT"
BLOCK_SECTION_CONFLICT = "SECTION_CONFLICT"
BLOCK_IDENTITY_REGENERATION = "IDENTITY_REGENERATION"
BLOCK_EXPECTED_BASELINE_DRIFT = "EXPECTED_BASELINE_DRIFT"
BLOCK_RUNNING_SNAPSHOT_HOLD = "RUNNING_SNAPSHOT_HOLD"


# ---------------------------------------------------------------------------
# Stage report shape
# ---------------------------------------------------------------------------


@dataclass
class StageReport:
    name: str
    ready: bool
    block_reasons: tuple = ()
    evidence: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "ready": self.ready,
            "block_reasons": list(self.block_reasons),
            "evidence": dict(self.evidence),
        }


@dataclass
class AcceptanceReport:
    verdict: str
    stages: tuple  # tuple[StageReport, ...]
    overall_block_reasons: tuple = ()

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "overall_block_reasons": list(self.overall_block_reasons),
            "stages": {s.name: s.to_dict() for s in self.stages},
        }


# ---------------------------------------------------------------------------
# Stage A — SOURCE_READY
# ---------------------------------------------------------------------------


def evaluate_source_stage(
    hydration_status: Mapping[str, Any],
    *,
    queue_path: Optional[Path] = None,
    queue_sha256: Optional[str] = None,
    queue_rows: Optional[int] = None,
) -> StageReport:
    """Aggregate the hydration snapshot into a single SOURCE_READY verdict.

    Inputs are the shape returned by ops.collect_hydration_status.
    Integrity gates (queue identity / duplicates / source contract) fire
    a BLOCK reason. Completeness gates (completed<queue_total etc.) do
    NOT block — they just leave ready=False so the caller renders
    WAIT_HYDRATION.
    """
    ev: dict = {}
    reasons: list[str] = []
    integrity_violation = False

    completed = hydration_status.get("completed")
    remaining = hydration_status.get("remaining")
    unique = hydration_status.get("unique_chemicals")
    complete = hydration_status.get("complete_chemicals")
    incomplete = hydration_status.get("incomplete_chemicals")

    ev["queue_total"] = hydration_status.get("queue_total")
    ev["completed"] = completed
    ev["remaining"] = remaining
    ev["unique_chemicals"] = unique
    ev["complete_chemicals"] = complete
    ev["incomplete_chemicals"] = incomplete

    # WO §5: frozen queue integrity. Only checked when queue_path exists.
    if queue_path is not None and queue_path.exists():
        actual_rows = 0
        h = hashlib.sha256()
        try:
            with queue_path.open("rb") as fh:
                for chunk in iter(lambda: fh.read(65536), b""):
                    h.update(chunk)
            with queue_path.open(encoding="utf-8") as fh:
                for _ in fh:
                    actual_rows += 1
        except OSError as exc:
            ev["queue_error"] = f"{type(exc).__name__}: {exc}"
        else:
            ev["queue_sha256"] = h.hexdigest()
            ev["queue_rows"] = actual_rows
            expected_sha = queue_sha256 or EXPECTED_QUEUE_SHA256
            expected_rows = queue_rows or EXPECTED_QUEUE_ROWS
            if h.hexdigest() != expected_sha or actual_rows != expected_rows:
                reasons.append(BLOCK_QUEUE_IDENTITY_MISMATCH)
                integrity_violation = True

    # WO §4 completeness gates.
    all_full = (
        completed == EXPECTED_QUEUE_ROWS
        and remaining == 0
        and unique == EXPECTED_CHEMICAL_COUNT
        and complete == EXPECTED_CHEMICAL_COUNT
        and (incomplete or 0) == 0
    )
    ev["all_full"] = bool(all_full)

    return StageReport(
        name="source",
        ready=(all_full and not integrity_violation),
        block_reasons=tuple(reasons),
        evidence=ev,
    )


# ---------------------------------------------------------------------------
# Stage B — FULL_PLAN_READY
# ---------------------------------------------------------------------------


# CHEM-05 → harness block-reason translation (WO §7).
# Keys are `services.kosha_msds.materialize`'s BLOCK_* string constants;
# values are our harness vocabulary. Anything unknown falls through as
# BLOCK_NOT_FULL_PLAN so we default-refuse rather than silently pass.
_CHEM05_BLOCK_TRANSLATION: Mapping[str, str] = {
    "FULL_OFFICIAL_CORPUS_INCOMPLETE": BLOCK_NOT_FULL_PLAN,
    "SOURCE_CONTRACT_FAIL": BLOCK_SOURCE_CONTRACT_FAILURE,
    "DUPLICATE_PAIRS": BLOCK_DUPLICATE_SOURCE_PAIR,
    "MISSING_SECTIONS": BLOCK_NOT_FULL_PLAN,
    "INCOMPLETE_CHEMICALS": BLOCK_NOT_FULL_PLAN,
}


def evaluate_full_plan_stage(plan_inputs) -> StageReport:
    """Verify a MaterializePlanInputs represents a FULL corpus plan.

    Preview plans (1,997 rows) are refused with BLOCK_NOT_FULL_PLAN.
    CHEM-05 execute_block_reasons on the report are translated into
    the harness vocabulary — the plan adapter is the authoritative
    source-contract / duplicate-pair judge, we just surface it.
    """
    if plan_inputs is None:
        return StageReport(
            name="plan", ready=False,
            block_reasons=(),
            evidence={"available": False,
                       "note": "CHEM-05 plan artifacts not supplied"},
        )
    ev: dict = {"available": True}
    reasons: list[str] = []

    chemicals = list(plan_inputs.chemicals or [])
    chemical_count = len(chemicals)
    section_count = sum(len(c.get("sections") or []) for c in chemicals)
    ev["chemicals"] = chemical_count
    ev["sections"] = section_count

    manifest = plan_inputs.manifest or {}
    report = plan_inputs.report or {}
    execute_eligible = bool(manifest.get("execute_eligible")
                            or report.get("execute_eligible"))
    ev["execute_eligible"] = execute_eligible
    ev["plan_semantic_sha256"] = manifest.get("plan_semantic_sha256")
    ev["responses_sha256"] = manifest.get("responses_sha256")
    ev["plan_file_sha256"] = manifest.get("plan_file_sha256")

    # Translate CHEM-05's own block reasons before deriving our own so
    # DUPLICATE_PAIRS / SOURCE_CONTRACT_FAIL surface with harness names.
    plan_block_reasons = list(report.get("execute_block_reasons") or [])
    ev["plan_execute_block_reasons"] = plan_block_reasons
    for br in plan_block_reasons:
        reasons.append(
            _CHEM05_BLOCK_TRANSLATION.get(br, BLOCK_NOT_FULL_PLAN)
        )

    if chemical_count != EXPECTED_CHEMICAL_COUNT:
        reasons.append(BLOCK_NOT_FULL_PLAN)
    if section_count != EXPECTED_SECTION_COUNT:
        reasons.append(BLOCK_NOT_FULL_PLAN)
    # De-dup while preserving order.
    seen = set()
    dedup: list[str] = []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            dedup.append(r)

    ready = (chemical_count == EXPECTED_CHEMICAL_COUNT
             and section_count == EXPECTED_SECTION_COUNT
             and execute_eligible
             and not dedup)
    return StageReport(
        name="plan",
        ready=ready,
        block_reasons=tuple(dedup),
        evidence=ev,
    )


# ---------------------------------------------------------------------------
# Stage C — MATERIALIZE_READY  (dry-run classification)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MaterializeExpectedBaseline:
    """Expected NEW / UNCHANGED / CHANGED counts under an authoritative
    preview + full plan. See WO §8:

        chemicals: UNCHANGED=1997 NEW=18571 CHANGED=0 CONFLICT=0
        sections:  UNCHANGED=31952 NEW=297136 CHANGED=0 CONFLICT=0
    """
    chemicals_unchanged: int
    chemicals_new: int
    chemicals_changed: int
    sections_unchanged: int
    sections_new: int
    sections_changed: int


DEFAULT_PREVIEW_TO_FULL_BASELINE = MaterializeExpectedBaseline(
    chemicals_unchanged=1_997,
    chemicals_new=18_571,          # 20,568 − 1,997
    chemicals_changed=0,
    sections_unchanged=31_952,     # 1,997 × 16
    sections_new=297_136,          # 329,088 − 31,952
    sections_changed=0,
)


def evaluate_materialize_dry_run_stage(
    plan_inputs,
    *,
    store,
    expected: Optional[MaterializeExpectedBaseline] = None,
) -> StageReport:
    """Classify the plan against the current store state (dry-run).

    Uses CHEM-08's classifier + preload machinery — no store write.
    A CONFLICT row at either level raises BLOCKED. An UNCHANGED/NEW
    count that deviates from the expected baseline (when provided)
    raises EXPECTED_BASELINE_DRIFT — Owner should investigate before
    Owner-approved materialize.
    """
    if plan_inputs is None:
        return StageReport(
            name="materialize", ready=False,
            evidence={"note": "no plan supplied"},
        )
    from services.kosha_msds import materialize_writer as w
    state = w.preload_existing_state(plan_inputs, store)
    chem_class = w.classify_chemicals(
        plan_inputs.chemicals, store=store,
        preloaded_chemicals=state.chemicals,
    )
    sec_class = w.classify_sections(
        plan_inputs.chemicals, chem_class, store=store,
        preloaded_sections=state.sections,
    )
    kinds_c = {"NEW": 0, "UNCHANGED": 0, "CHANGED": 0, "CONFLICT": 0}
    for c in chem_class:
        kinds_c[c.kind] = kinds_c.get(c.kind, 0) + 1
    kinds_s = {"NEW": 0, "UNCHANGED": 0, "CHANGED": 0, "CONFLICT": 0}
    for s in sec_class:
        kinds_s[s.kind] = kinds_s.get(s.kind, 0) + 1

    ev: dict = {
        "chemical_counts": kinds_c,
        "section_counts": kinds_s,
    }
    reasons: list[str] = []
    if kinds_c["CONFLICT"] > 0:
        reasons.append(BLOCK_CHEMICAL_CONFLICT)
    if kinds_s["CONFLICT"] > 0:
        reasons.append(BLOCK_SECTION_CONFLICT)

    # Identity-preservation gate (WO §9): UNCHANGED / CHANGED chemicals
    # must all carry a db_chemical_id (means the classifier resolved
    # them against existing DB rows; no NEW UUID needed).
    identity_regen = False
    for c in chem_class:
        if c.kind in ("UNCHANGED", "CHANGED") and not c.db_chemical_id:
            identity_regen = True
            break
    if identity_regen:
        reasons.append(BLOCK_IDENTITY_REGENERATION)
    ev["identity_regeneration"] = identity_regen

    # Optional expected-baseline check (WO §8).
    if expected is not None:
        drift = False
        if (kinds_c["UNCHANGED"] != expected.chemicals_unchanged
                or kinds_c["NEW"] != expected.chemicals_new
                or kinds_c["CHANGED"] != expected.chemicals_changed):
            drift = True
        if (kinds_s["UNCHANGED"] != expected.sections_unchanged
                or kinds_s["NEW"] != expected.sections_new
                or kinds_s["CHANGED"] != expected.sections_changed):
            drift = True
        if drift:
            reasons.append(BLOCK_EXPECTED_BASELINE_DRIFT)
            ev["expected"] = {
                "chemicals_unchanged": expected.chemicals_unchanged,
                "chemicals_new": expected.chemicals_new,
                "chemicals_changed": expected.chemicals_changed,
                "sections_unchanged": expected.sections_unchanged,
                "sections_new": expected.sections_new,
                "sections_changed": expected.sections_changed,
            }

    ready = (kinds_c["CONFLICT"] == 0
             and kinds_s["CONFLICT"] == 0
             and not identity_regen
             and not any(r == BLOCK_EXPECTED_BASELINE_DRIFT for r in reasons))
    return StageReport(
        name="materialize",
        ready=ready,
        block_reasons=tuple(reasons),
        evidence=ev,
    )


# ---------------------------------------------------------------------------
# Stage D — MATERIALIZED_FULL_READY  (candidate discovery)
# ---------------------------------------------------------------------------


def evaluate_materialized_stage(*, publish_store) -> StageReport:
    """Look for a COMPLETED / FULL_OFFICIAL / NOT_PUBLISHED snapshot
    via publish_store.find_full_candidate. If none exists, ready=False
    with reason NOT_YET_MATERIALIZED — that is NOT a hard block.
    """
    find_fn = getattr(publish_store, "find_full_candidate", None)
    candidate = None
    if callable(find_fn):
        try:
            candidate = find_fn()
        except Exception:
            candidate = None
    if candidate is None:
        return StageReport(
            name="materialized_full", ready=False,
            evidence={"note": "NOT_YET_MATERIALIZED",
                      "snapshot_id": None},
        )
    return StageReport(
        name="materialized_full", ready=True,
        evidence={"snapshot_id": candidate.get("id"),
                  "expected_count": candidate.get("expected_count"),
                  "discovered_count": candidate.get("discovered_count")},
    )


# ---------------------------------------------------------------------------
# Stage E — PUBLISH_READY  (delegate to cutover.is_full_ready)
# ---------------------------------------------------------------------------


def evaluate_publish_stage(
    *,
    publish_store,
    snapshot_id: Optional[str],
) -> StageReport:
    if not snapshot_id:
        return StageReport(
            name="publish", ready=False,
            evidence={"note": "no snapshot to evaluate"},
        )
    from services.kosha_msds.cutover import is_full_ready
    report = is_full_ready(snapshot_id, store=publish_store)
    return StageReport(
        name="publish",
        ready=report.ready,
        block_reasons=tuple(report.block_reasons),
        evidence={"snapshot_id": snapshot_id, **report.to_dict()},
    )


# ---------------------------------------------------------------------------
# Stage F — SEARCH_RUNTIME_READY
# ---------------------------------------------------------------------------


def evaluate_search_runtime_stage(dictionary_status: Mapping[str, Any]) -> StageReport:
    """V2_MATCH → ready. V1_OR_OTHER or UNVERIFIED_NETWORK → NOT ready.
    This stage is a hard cutover gate under WO §12: FULL public
    cutover cannot proceed while the runtime dictionary binding
    is unverified.
    """
    binding = dictionary_status.get("binding")
    ev = {
        "binding": binding,
        "runtime_snapshot": dictionary_status.get("runtime_snapshot"),
        "chem_term_msds_matched": dictionary_status.get("chem_term_msds_matched"),
        "error": dictionary_status.get("error"),
    }
    ready = (binding == "V2_MATCH"
             and dictionary_status.get("chem_term_msds_matched") is True)
    return StageReport(
        name="search_runtime", ready=ready, evidence=ev,
    )


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------


def evaluate_full_acceptance(
    *,
    hydration_status: Mapping[str, Any],
    plan_inputs=None,
    publish_store=None,
    materialize_store=None,
    dictionary_status: Optional[Mapping[str, Any]] = None,
    public_mode: str = "off",
    queue_path: Optional[Path] = None,
    running_snapshots: int = 0,
    materialize_expected_baseline: Optional[MaterializeExpectedBaseline] = None,
) -> AcceptanceReport:
    """Compose stage reports into a single verdict + evidence dict.

    `materialize_store` (with `get_chemical_by_natural_key` /
    `get_section` / bulk equivalents) drives the dry-run classification
    stage. `publish_store` (with `find_full_candidate` / preflight-shaped
    read methods) drives the materialized-full + publish stages.
    In production both slots receive their own Supabase-backed store
    class; in tests they can be the same object as long as the object
    implements both interfaces.
    """

    # Stage A
    a = evaluate_source_stage(hydration_status, queue_path=queue_path)

    # Running snapshot hold (WO §19): a RUNNING FULL snapshot must
    # block cutover until an operator closes it.
    running_hold = running_snapshots > 0

    # Stage B
    b = evaluate_full_plan_stage(plan_inputs)

    # Stage C
    mat_store = materialize_store if materialize_store is not None else publish_store
    if mat_store is None or plan_inputs is None:
        c = StageReport(name="materialize", ready=False,
                        evidence={"note": "materialize_store or plan not supplied"})
    else:
        c = evaluate_materialize_dry_run_stage(
            plan_inputs, store=mat_store,
            expected=materialize_expected_baseline,
        )

    # Stage D
    if publish_store is None:
        d = StageReport(name="materialized_full", ready=False,
                        evidence={"note": "no publish_store"})
    else:
        d = evaluate_materialized_stage(publish_store=publish_store)

    # Stage E
    if publish_store is None or not d.ready:
        e = StageReport(name="publish", ready=False,
                        evidence={"note": "no materialized FULL candidate"})
    else:
        e = evaluate_publish_stage(
            publish_store=publish_store,
            snapshot_id=(d.evidence or {}).get("snapshot_id"),
        )

    # Stage F
    if dictionary_status is None:
        f = StageReport(
            name="search_runtime", ready=False,
            evidence={"note": "no dictionary_status supplied"},
        )
    else:
        f = evaluate_search_runtime_stage(dictionary_status)

    # Stage G — derived gate.
    all_stages_ready = all(s.ready for s in (a, b, c, d, e, f))
    public_mode_pre_cutover = (public_mode == PUBLIC_MODE_SEO_PREVIEW)
    g = StageReport(
        name="public_cutover", ready=(all_stages_ready and public_mode_pre_cutover),
        evidence={"public_mode": public_mode,
                  "all_stages_ready": all_stages_ready,
                  "public_mode_pre_cutover": public_mode_pre_cutover},
    )

    stages = (a, b, c, d, e, f, g)

    # Aggregate block reasons.
    reasons: list[str] = []
    for s in stages:
        for r in s.block_reasons:
            if r not in reasons:
                reasons.append(r)
    if running_hold:
        reasons.append(BLOCK_RUNNING_SNAPSHOT_HOLD)

    # Verdict resolution.
    verdict: str
    if reasons:
        verdict = VERDICT_BLOCKED
    elif not a.ready:
        verdict = VERDICT_WAIT_HYDRATION
    elif a.ready and b.ready and c.ready and not d.ready:
        # Materialize is dry-run-eligible but no snapshot exists yet.
        verdict = VERDICT_READY_FOR_FULL_MATERIALIZE
    elif all_stages_ready and public_mode_pre_cutover:
        verdict = VERDICT_READY_FOR_FULL_CUTOVER
    else:
        # Intermediate: A/B/C ready, D ready, E blocked (edge case).
        verdict = VERDICT_BLOCKED
        # Surface the missing readiness as a note; do not fabricate a reason.

    return AcceptanceReport(
        verdict=verdict,
        stages=stages,
        overall_block_reasons=tuple(reasons),
    )
