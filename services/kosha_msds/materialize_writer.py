"""OBJ-CHEM-08 KOSHA MSDS production materialize writer (pure logic).

Consumes a CHEM-05 materialize plan (materialize_plan.jsonl +
materialize_manifest.json + materialize_report.json) and produces a
classification / chunk plan targeted at the existing kosha_msds_*
tables. Fail-closed under three independent gates:

    Gate A  plan.execute_eligible must be true AND manifest bindings
            (responses_sha256, plan_semantic_sha256, plan_file_sha256)
            must match what the caller re-computed on disk.
    Gate B  DB preflight must be clean: no unexpected RUNNING snapshot,
            no CONFLICT rows.
    Gate C  Owner authorization + this-WO scope.
            WO-CHEM-08 forbids ANY production DB write. The writer
            refuses to open a DB connection even with an owner flag.
            A separate future execution WO must flip
            PRODUCTION_WRITE_ALLOWED to True.

The store interface below decouples the pure classification/orchestration
logic from Supabase or psycopg2. Two stores implement it here:

    MemoryMaterializeStore   -- in-memory replica for tests
    (SupabaseMaterializeStore is deferred to the future execution WO;
     this module never opens a live DB connection.)

Row classification vocabulary (WO §13/§14):
    NEW       row not present in DB
    UNCHANGED row present with identical content_hash / section_hash
    CHANGED   row present with different hash but consistent identity
    CONFLICT  identity mismatch (e.g., same source_key but different
              content_id, or DB row exists but chem_id disagrees with plan)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from services.kosha_msds.contract import (
    ALLOWED_SECTIONS,
    DETAIL_COMPLETE,
    DETAIL_EMPTY_BUT_VALID,
    DETAIL_INCOMPLETE,
    ENUMERATION_FULL_OFFICIAL,
    PUBLISH_NOT_PUBLISHED,
    PUBLISH_PUBLISHED_FULL,
    SNAPSHOT_COMPLETED,
    SNAPSHOT_FAILED,
    SNAPSHOT_RUNNING,
    SOURCE_CONTRACT_VERSION,
)

# ---------------------------------------------------------------------------
# WO scope gate — the load-bearing safety fence for this WO.
# WO-CHEM-08 forbids ALL production DB mutation. A future execution WO
# flips this to True by adding an override; there is no CLI flag under
# this WO that can set it to True.
# ---------------------------------------------------------------------------
WO_SCOPE = "WO-CHEM-08-PRODUCTION-MATERIALIZER-001"
PRODUCTION_WRITE_ALLOWED = False

# Chunk sizes (WO §10). Based on repo precedent:
#   tools/risk02/ingest001_source_core_local_exec.py
#     RECORD_BATCH = 100, MEMBERSHIP_BATCH = 500
#   tools/risk_map/map_materialize001.py
#     execute_values page_size = 200
CHEMICAL_BATCH_SIZE = 100
SECTION_BATCH_SIZE = 200
SNAPSHOT_ITEM_BATCH_SIZE = 500

# Classification vocabulary.
NEW = "NEW"
UNCHANGED = "UNCHANGED"
CHANGED = "CHANGED"
CONFLICT = "CONFLICT"

# Block reason vocabulary (mirrors CHEM-05 style).
BLOCK_PLAN_NOT_ELIGIBLE = "PLAN_NOT_ELIGIBLE"
BLOCK_MANIFEST_BINDING_MISMATCH = "MANIFEST_BINDING_MISMATCH"
BLOCK_PLAN_SHA_MISMATCH = "PLAN_SHA_MISMATCH"
BLOCK_EXISTING_RUNNING_SNAPSHOT = "EXISTING_RUNNING_SNAPSHOT"
BLOCK_CHEMICAL_CONFLICT = "CHEMICAL_CONFLICT"
BLOCK_SECTION_CONFLICT = "SECTION_CONFLICT"
BLOCK_INCOMPLETE_MEMBERSHIP = "INCOMPLETE_MEMBERSHIP"
BLOCK_PUBLISHED_FULL_ATTEMPTED = "PUBLISHED_FULL_ATTEMPTED"
BLOCK_OWNER_AUTHORIZATION_MISSING = "OWNER_AUTHORIZATION_MISSING"
BLOCK_WO_SCOPE_FORBIDS_WRITE = "WO_SCOPE_FORBIDS_PRODUCTION_WRITE"


class MaterializeWriterError(Exception):
    """Base class for materialize-writer failures."""


class ProductionWriteForbidden(MaterializeWriterError):
    """Raised when any code path would open a DB connection for a write.

    Under WO-CHEM-08, PRODUCTION_WRITE_ALLOWED is False and this is the
    load-bearing fence. Even if all other gates pass, this exception
    fires before any store method is called.
    """


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChemicalClassification:
    chem_id: str
    kind: str                     # NEW / UNCHANGED / CHANGED / CONFLICT
    reason: Optional[str] = None
    plan_source_content_hash: Optional[str] = None
    db_source_content_hash: Optional[str] = None
    db_chemical_id: Optional[str] = None
    db_content_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "chem_id": self.chem_id,
            "kind": self.kind,
            "reason": self.reason,
            "plan_source_content_hash": self.plan_source_content_hash,
            "db_source_content_hash": self.db_source_content_hash,
            "db_chemical_id": self.db_chemical_id,
            "db_content_id": self.db_content_id,
        }


@dataclass(frozen=True)
class SectionClassification:
    chem_id: str
    section_no: int
    kind: str                     # NEW / UNCHANGED / CHANGED / CONFLICT
    reason: Optional[str] = None
    plan_section_hash: Optional[str] = None
    db_section_hash: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "chem_id": self.chem_id,
            "section_no": self.section_no,
            "kind": self.kind,
            "reason": self.reason,
            "plan_section_hash": self.plan_section_hash,
            "db_section_hash": self.db_section_hash,
        }


@dataclass
class PreflightReport:
    plan_semantic_sha256: str
    plan_file_sha256: str
    responses_sha256: str
    execute_eligible: bool
    chemical_count: int
    section_count: int
    counts_by_kind: dict           # {NEW/UNCHANGED/CHANGED/CONFLICT: (chem_count, section_count)}
    conflict_chemicals: tuple      # tuple[ChemicalClassification, ...]
    conflict_sections: tuple       # tuple[SectionClassification, ...]
    incomplete_memberships: tuple  # tuple[chem_id, ...]
    existing_running_snapshot_id: Optional[str]
    block_reasons: tuple
    can_execute: bool

    def to_dict(self) -> dict:
        return {
            "plan_semantic_sha256": self.plan_semantic_sha256,
            "plan_file_sha256": self.plan_file_sha256,
            "responses_sha256": self.responses_sha256,
            "execute_eligible": self.execute_eligible,
            "chemical_count": self.chemical_count,
            "section_count": self.section_count,
            "counts_by_kind": {
                k: {"chemicals": v[0], "sections": v[1]}
                for k, v in self.counts_by_kind.items()
            },
            "conflict_chemicals_head": [c.to_dict() for c in self.conflict_chemicals[:10]],
            "conflict_sections_head": [s.to_dict() for s in self.conflict_sections[:10]],
            "incomplete_memberships_head": list(self.incomplete_memberships[:10]),
            "existing_running_snapshot_id": self.existing_running_snapshot_id,
            "block_reasons": list(self.block_reasons),
            "can_execute": self.can_execute,
        }


@dataclass
class ChunkPlan:
    """Deterministic chunking of NEW/CHANGED rows into batch-sized groups.

    UNCHANGED rows are excluded (idempotent skip). CONFLICT rows are
    excluded (fail-closed — preflight would have blocked already).
    """
    chemical_batches: tuple        # tuple[tuple[str, ...], ...]  each batch = tuple of chem_ids
    section_batches: tuple         # tuple[tuple[tuple[str,int], ...], ...]  each = (chem_id, section_no)
    snapshot_item_batches: tuple   # tuple[tuple[str, ...], ...]  each batch = tuple of chem_ids

    def to_dict(self) -> dict:
        return {
            "chemical_batch_count": len(self.chemical_batches),
            "section_batch_count": len(self.section_batches),
            "snapshot_item_batch_count": len(self.snapshot_item_batches),
            "chemical_batch_size": CHEMICAL_BATCH_SIZE,
            "section_batch_size": SECTION_BATCH_SIZE,
            "snapshot_item_batch_size": SNAPSHOT_ITEM_BATCH_SIZE,
        }


@dataclass
class MaterializePlanInputs:
    """The three-file input contract emitted by CHEM-05 build_materialize_plan."""
    manifest: dict
    report: dict
    chemicals: tuple  # tuple[dict, ...] parsed from plan.jsonl


# ---------------------------------------------------------------------------
# Store interface
# ---------------------------------------------------------------------------


class MemoryMaterializeStore:
    """In-memory read/write store for tests. No live DB.

    Even the write methods are exposed only for fixture tests; production
    stores live in a separate future WO. Under WO-CHEM-08 the writer
    module itself never calls these methods against a real connection.
    """

    def __init__(
        self,
        *,
        chemicals: Optional[Iterable[dict]] = None,
        sections: Optional[Iterable[dict]] = None,
        snapshots: Optional[Iterable[dict]] = None,
        snapshot_items: Optional[Iterable[dict]] = None,
    ):
        self._chemicals_by_key: dict[tuple[str, str], dict] = {}
        for c in (chemicals or []):
            key = (str(c["source_id"]), str(c["source_key"]))
            self._chemicals_by_key[key] = dict(c)
        self._sections_by_pair: dict[tuple[str, int], dict] = {}
        for s in (sections or []):
            key = (str(s["chemical_id"]), int(s["section_no"]))
            self._sections_by_pair[key] = dict(s)
        self._snapshots: list[dict] = [dict(x) for x in (snapshots or [])]
        self._snapshot_items: list[dict] = [dict(x) for x in (snapshot_items or [])]

    # -- read side --
    def get_chemical_by_natural_key(self, source_id: str, source_key: str) -> Optional[dict]:
        row = self._chemicals_by_key.get((source_id, source_key))
        return dict(row) if row else None

    def get_section(self, chemical_id: str, section_no: int) -> Optional[dict]:
        row = self._sections_by_pair.get((str(chemical_id), int(section_no)))
        return dict(row) if row else None

    def latest_running_snapshot(self) -> Optional[dict]:
        for snap in self._snapshots:
            if snap.get("status") == SNAPSHOT_RUNNING:
                return dict(snap)
        return None

    def get_snapshot(self, snapshot_id: str) -> Optional[dict]:
        for s in self._snapshots:
            if str(s.get("id")) == str(snapshot_id):
                return dict(s)
        return None

    # -- write side (fixture-only under WO-CHEM-08) --
    def insert_snapshot(self, snapshot: dict) -> None:
        self._snapshots.append(dict(snapshot))

    def update_snapshot_status(self, snapshot_id: str, status: str) -> None:
        for s in self._snapshots:
            if str(s.get("id")) == str(snapshot_id):
                s["status"] = status
                return

    def insert_chemicals(self, rows: list[dict]) -> None:
        for c in rows:
            key = (str(c["source_id"]), str(c["source_key"]))
            self._chemicals_by_key[key] = dict(c)

    def insert_sections(self, rows: list[dict]) -> None:
        for s in rows:
            key = (str(s["chemical_id"]), int(s["section_no"]))
            self._sections_by_pair[key] = dict(s)

    def insert_snapshot_items(self, rows: list[dict]) -> None:
        for m in rows:
            self._snapshot_items.append(dict(m))


# ---------------------------------------------------------------------------
# Input loading
# ---------------------------------------------------------------------------


def load_plan_inputs(
    *,
    plan_jsonl: Path,
    manifest_json: Path,
    report_json: Path,
) -> MaterializePlanInputs:
    """Read the three CHEM-05 artifacts from disk. Fail loudly on any
    missing file, since preflight cannot execute without all three."""
    if not plan_jsonl.exists():
        raise FileNotFoundError(f"materialize_plan.jsonl not found: {plan_jsonl}")
    if not manifest_json.exists():
        raise FileNotFoundError(f"materialize_manifest.json not found: {manifest_json}")
    if not report_json.exists():
        raise FileNotFoundError(f"materialize_report.json not found: {report_json}")

    manifest = json.loads(manifest_json.read_text(encoding="utf-8"))
    report = json.loads(report_json.read_text(encoding="utf-8"))

    chemicals: list[dict] = []
    with plan_jsonl.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                chemicals.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"materialize_plan.jsonl:{lineno} invalid JSON: {exc}"
                ) from exc

    return MaterializePlanInputs(
        manifest=manifest,
        report=report,
        chemicals=tuple(chemicals),
    )


# ---------------------------------------------------------------------------
# Manifest binding
# ---------------------------------------------------------------------------


def verify_manifest_binding(
    inputs: MaterializePlanInputs,
    *,
    on_disk_responses_sha256: Optional[str] = None,
    on_disk_plan_file_sha256: Optional[str] = None,
) -> list[str]:
    """Compare manifest binding fields against optional recomputed SHAs.

    Returns a list of block reasons; empty list means all bindings match.
    """
    reasons: list[str] = []
    m = inputs.manifest or {}
    r = inputs.report or {}

    # plan_semantic_sha256 must appear in both manifest and report and agree.
    m_plan = m.get("plan_semantic_sha256")
    r_plan = r.get("plan_sha256")
    if m_plan and r_plan and m_plan != r_plan:
        reasons.append(BLOCK_PLAN_SHA_MISMATCH)

    if on_disk_responses_sha256 is not None:
        if m.get("responses_sha256") != on_disk_responses_sha256:
            reasons.append(BLOCK_MANIFEST_BINDING_MISMATCH)
    if on_disk_plan_file_sha256 is not None:
        if m.get("plan_file_sha256") != on_disk_plan_file_sha256:
            reasons.append(BLOCK_MANIFEST_BINDING_MISMATCH)

    # De-duplicate while preserving order.
    seen = set()
    out = []
    for reason in reasons:
        if reason not in seen:
            seen.add(reason)
            out.append(reason)
    return out


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def classify_chemicals(
    chemicals: Iterable[Mapping[str, Any]],
    *,
    store: MemoryMaterializeStore,
) -> list[ChemicalClassification]:
    out: list[ChemicalClassification] = []
    for c in chemicals:
        chem_id = c.get("chem_id")
        source_id = c.get("source_id")
        source_key = c.get("source_key")
        plan_hash = c.get("source_content_hash")
        db = store.get_chemical_by_natural_key(source_id, source_key)
        if db is None:
            out.append(ChemicalClassification(
                chem_id=chem_id, kind=NEW,
                plan_source_content_hash=plan_hash,
            ))
            continue
        db_hash = db.get("source_content_hash")
        db_chem_id = db.get("chem_id")
        db_content_id = db.get("content_id")
        # Identity conflict: the DB's chem_id disagrees with the plan's
        # chem_id even though the natural key matched. The schema's
        # CHECK (source_key = chem_id) should prevent this, but a
        # defensive check is cheap.
        if db_chem_id != chem_id:
            out.append(ChemicalClassification(
                chem_id=chem_id, kind=CONFLICT,
                reason="db chem_id disagrees with plan chem_id",
                plan_source_content_hash=plan_hash,
                db_source_content_hash=db_hash,
                db_chemical_id=db.get("id"),
                db_content_id=db_content_id,
            ))
            continue
        if db_hash == plan_hash:
            out.append(ChemicalClassification(
                chem_id=chem_id, kind=UNCHANGED,
                plan_source_content_hash=plan_hash,
                db_source_content_hash=db_hash,
                db_chemical_id=db.get("id"),
                db_content_id=db_content_id,
            ))
        else:
            out.append(ChemicalClassification(
                chem_id=chem_id, kind=CHANGED,
                plan_source_content_hash=plan_hash,
                db_source_content_hash=db_hash,
                db_chemical_id=db.get("id"),
                db_content_id=db_content_id,
            ))
    return out


def classify_sections(
    chemicals: Iterable[Mapping[str, Any]],
    chem_classifications: Iterable[ChemicalClassification],
    *,
    store: MemoryMaterializeStore,
) -> list[SectionClassification]:
    """Classify every plan section against DB sections for the resolved
    chemical UUID (only meaningful for UNCHANGED/CHANGED/CONFLICT rows;
    NEW chemicals imply NEW sections)."""
    by_chem_id_uuid = {c.chem_id: c.db_chemical_id for c in chem_classifications}
    kind_by_chem_id = {c.chem_id: c.kind for c in chem_classifications}
    out: list[SectionClassification] = []
    for c in chemicals:
        chem_id = c.get("chem_id")
        c_kind = kind_by_chem_id.get(chem_id)
        db_uuid = by_chem_id_uuid.get(chem_id)
        for s in c.get("sections") or []:
            sec_no = int(s.get("section_no"))
            plan_hash = s.get("section_hash")
            if c_kind == NEW or db_uuid is None:
                out.append(SectionClassification(
                    chem_id=chem_id, section_no=sec_no, kind=NEW,
                    plan_section_hash=plan_hash,
                ))
                continue
            if c_kind == CONFLICT:
                out.append(SectionClassification(
                    chem_id=chem_id, section_no=sec_no, kind=CONFLICT,
                    reason="chemical is CONFLICT",
                    plan_section_hash=plan_hash,
                ))
                continue
            db_sec = store.get_section(db_uuid, sec_no)
            if db_sec is None:
                out.append(SectionClassification(
                    chem_id=chem_id, section_no=sec_no, kind=NEW,
                    plan_section_hash=plan_hash,
                ))
                continue
            db_hash = db_sec.get("section_hash")
            if db_hash == plan_hash:
                out.append(SectionClassification(
                    chem_id=chem_id, section_no=sec_no, kind=UNCHANGED,
                    plan_section_hash=plan_hash, db_section_hash=db_hash,
                ))
            else:
                out.append(SectionClassification(
                    chem_id=chem_id, section_no=sec_no, kind=CHANGED,
                    plan_section_hash=plan_hash, db_section_hash=db_hash,
                ))
    return out


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------


def preflight(
    inputs: MaterializePlanInputs,
    *,
    store: MemoryMaterializeStore,
    on_disk_responses_sha256: Optional[str] = None,
    on_disk_plan_file_sha256: Optional[str] = None,
    resume_snapshot_id: Optional[str] = None,
) -> PreflightReport:
    """Read-only preflight. Returns a PreflightReport whose can_execute
    is True only if all block gates are clean.
    """
    manifest = inputs.manifest or {}
    report = inputs.report or {}

    reasons: list[str] = []

    execute_eligible = bool(manifest.get("execute_eligible")
                            if "execute_eligible" in manifest
                            else report.get("execute_eligible"))
    if not execute_eligible:
        reasons.append(BLOCK_PLAN_NOT_ELIGIBLE)

    reasons.extend(verify_manifest_binding(
        inputs,
        on_disk_responses_sha256=on_disk_responses_sha256,
        on_disk_plan_file_sha256=on_disk_plan_file_sha256,
    ))

    # Never emit PUBLISHED_FULL from the writer.
    snap = manifest.get("snapshot") or {}
    if snap.get("publish_state") == PUBLISH_PUBLISHED_FULL:
        reasons.append(BLOCK_PUBLISHED_FULL_ATTEMPTED)

    # Existing RUNNING snapshot guard (§20).
    running = store.latest_running_snapshot()
    running_id = None
    if running is not None:
        running_id = str(running.get("id"))
        if resume_snapshot_id is None or resume_snapshot_id != running_id:
            reasons.append(BLOCK_EXISTING_RUNNING_SNAPSHOT)

    # Incomplete membership guard (§15).
    incomplete: list[str] = []
    for c in inputs.chemicals:
        status = c.get("detail_status")
        if status == DETAIL_INCOMPLETE:
            incomplete.append(c.get("chem_id"))
    if incomplete:
        reasons.append(BLOCK_INCOMPLETE_MEMBERSHIP)

    chem_class = classify_chemicals(inputs.chemicals, store=store)
    sec_class = classify_sections(inputs.chemicals, chem_class, store=store)

    chem_conflicts = [c for c in chem_class if c.kind == CONFLICT]
    sec_conflicts = [s for s in sec_class if s.kind == CONFLICT]
    if chem_conflicts:
        reasons.append(BLOCK_CHEMICAL_CONFLICT)
    if sec_conflicts:
        reasons.append(BLOCK_SECTION_CONFLICT)

    counts_by_kind: dict[str, tuple[int, int]] = {
        NEW: (0, 0), UNCHANGED: (0, 0), CHANGED: (0, 0), CONFLICT: (0, 0),
    }
    for c in chem_class:
        cc, sc = counts_by_kind[c.kind]
        counts_by_kind[c.kind] = (cc + 1, sc)
    for s in sec_class:
        cc, sc = counts_by_kind[s.kind]
        counts_by_kind[s.kind] = (cc, sc + 1)

    return PreflightReport(
        plan_semantic_sha256=(manifest.get("plan_semantic_sha256")
                              or report.get("plan_sha256") or ""),
        plan_file_sha256=manifest.get("plan_file_sha256") or "",
        responses_sha256=manifest.get("responses_sha256")
        or report.get("responses_sha256") or "",
        execute_eligible=execute_eligible,
        chemical_count=len(inputs.chemicals),
        section_count=sum(len(c.get("sections") or []) for c in inputs.chemicals),
        counts_by_kind=counts_by_kind,
        conflict_chemicals=tuple(chem_conflicts),
        conflict_sections=tuple(sec_conflicts),
        incomplete_memberships=tuple(incomplete),
        existing_running_snapshot_id=running_id,
        block_reasons=tuple(reasons),
        can_execute=len(reasons) == 0,
    )


# ---------------------------------------------------------------------------
# Chunk planning
# ---------------------------------------------------------------------------


def build_chunk_plan(
    inputs: MaterializePlanInputs,
    chem_class: list[ChemicalClassification],
    sec_class: list[SectionClassification],
) -> ChunkPlan:
    """Deterministic chunking of NEW / CHANGED rows.

    UNCHANGED rows are excluded (idempotent skip; already up-to-date).
    CONFLICT rows are excluded (preflight would have blocked the run).
    Every batch is sorted by natural key so replays produce identical
    plans.
    """
    changing_kinds = {NEW, CHANGED}

    chem_ids = sorted([c.chem_id for c in chem_class if c.kind in changing_kinds])
    chemical_batches = _chunk(chem_ids, CHEMICAL_BATCH_SIZE)

    changing_chem_ids = set(chem_ids)
    section_pairs = sorted(
        [(s.chem_id, s.section_no) for s in sec_class
         if s.kind in changing_kinds and s.chem_id in changing_chem_ids]
    )
    section_batches = _chunk(section_pairs, SECTION_BATCH_SIZE)

    # snapshot_items membership: one per chemical bundle in the plan
    # (all plan chemicals get a membership row; UNCHANGED chemicals
    # still get membership refreshed under the new snapshot). Chunk
    # over the full plan chem_id list, not just changing ones.
    all_plan_chem_ids = sorted([c.get("chem_id") for c in inputs.chemicals])
    snapshot_item_batches = _chunk(all_plan_chem_ids, SNAPSHOT_ITEM_BATCH_SIZE)

    return ChunkPlan(
        chemical_batches=tuple(tuple(b) for b in chemical_batches),
        section_batches=tuple(tuple(b) for b in section_batches),
        snapshot_item_batches=tuple(tuple(b) for b in snapshot_item_batches),
    )


def _chunk(seq: list, size: int) -> list:
    if size <= 0:
        raise ValueError(f"chunk size must be > 0, got {size}")
    return [seq[i:i + size] for i in range(0, len(seq), size)]


# ---------------------------------------------------------------------------
# The load-bearing safety fence.
# ---------------------------------------------------------------------------


def assert_can_execute_production_write(
    *,
    preflight_report: PreflightReport,
    owner_approved: bool,
    wo_scope_allows_write: bool = PRODUCTION_WRITE_ALLOWED,
) -> None:
    """Fail-closed authorization. Called BEFORE any store write call.

    Three gates in order:
      Gate A  preflight_report.can_execute must be True.
      Gate B  owner_approved must be True.
      Gate C  wo_scope_allows_write must be True.

    Under WO-CHEM-08, Gate C is hard-wired False by
    PRODUCTION_WRITE_ALLOWED. A separate future execution WO with
    explicit owner approval is the only mechanism that can flip it.
    """
    if not preflight_report.can_execute:
        raise ProductionWriteForbidden(
            f"preflight blocked: {list(preflight_report.block_reasons) or ['<unknown>']}"
        )
    if not owner_approved:
        raise ProductionWriteForbidden(
            f"{BLOCK_OWNER_AUTHORIZATION_MISSING}: owner_approved=False"
        )
    if not wo_scope_allows_write:
        raise ProductionWriteForbidden(
            f"{BLOCK_WO_SCOPE_FORBIDS_WRITE}: {WO_SCOPE} does not allow "
            f"production DB writes. A future execution WO must set "
            f"PRODUCTION_WRITE_ALLOWED=True."
        )


def assert_no_publish_full(snapshot_dict: Mapping[str, Any]) -> None:
    """Second guard against PUBLISHED_FULL emission (WO §12)."""
    if snapshot_dict.get("publish_state") == PUBLISH_PUBLISHED_FULL:
        raise ProductionWriteForbidden(
            "publish_state=PUBLISHED_FULL is a separate future WO; the "
            "materializer never emits it."
        )


# ---------------------------------------------------------------------------
# Snapshot lifecycle abstraction (fixture-only under WO-CHEM-08).
# ---------------------------------------------------------------------------


def open_snapshot(
    *,
    snapshot_id: str,
    manifest: Mapping[str, Any],
    discovered_count: int,
    expected_count: int,
) -> dict:
    """Build the RUNNING snapshot record. The writer NEVER inserts this
    into a live DB under WO-CHEM-08; this helper is used only by tests
    (against MemoryMaterializeStore) and by the future execution WO.
    """
    metrics_manifest = dict(manifest.get("snapshot", {}).get("metrics_json") or {})
    metrics_manifest.setdefault("adapter_version", "CHEM05_V1")
    metrics_manifest["writer_wo"] = WO_SCOPE
    return {
        "id": snapshot_id,
        "source_id": "KOSHA_MSDS",
        "run_type": "FULL_SYNC",
        "status": SNAPSHOT_RUNNING,
        "enumeration_mode": ENUMERATION_FULL_OFFICIAL,
        "publish_state": PUBLISH_NOT_PUBLISHED,
        "source_contract_version": SOURCE_CONTRACT_VERSION,
        "expected_count": int(expected_count),
        "discovered_count": int(discovered_count),
        "metrics_json": metrics_manifest,
    }


def mark_snapshot_completed(store: MemoryMaterializeStore, snapshot_id: str) -> None:
    """Fixture-only: flip an existing snapshot to COMPLETED."""
    store.update_snapshot_status(snapshot_id, SNAPSHOT_COMPLETED)


def mark_snapshot_failed(store: MemoryMaterializeStore, snapshot_id: str) -> None:
    store.update_snapshot_status(snapshot_id, SNAPSHOT_FAILED)


# ---------------------------------------------------------------------------
# High-level dry-run entrypoint (still no DB, still no writes).
# ---------------------------------------------------------------------------


def dry_run(
    inputs: MaterializePlanInputs,
    *,
    store: MemoryMaterializeStore,
    on_disk_responses_sha256: Optional[str] = None,
    on_disk_plan_file_sha256: Optional[str] = None,
    resume_snapshot_id: Optional[str] = None,
) -> dict:
    """Preflight + chunk planning summary. Never mutates the store."""
    report = preflight(
        inputs,
        store=store,
        on_disk_responses_sha256=on_disk_responses_sha256,
        on_disk_plan_file_sha256=on_disk_plan_file_sha256,
        resume_snapshot_id=resume_snapshot_id,
    )
    chem_class = classify_chemicals(inputs.chemicals, store=store)
    sec_class = classify_sections(inputs.chemicals, chem_class, store=store)
    plan = build_chunk_plan(inputs, chem_class, sec_class)
    return {
        "preflight": report.to_dict(),
        "chunk_plan": plan.to_dict(),
        "chemical_classifications_head": [c.to_dict() for c in chem_class[:10]],
        "section_classifications_head": [s.to_dict() for s in sec_class[:10]],
        "wo_scope": WO_SCOPE,
        "production_write_allowed": PRODUCTION_WRITE_ALLOWED,
    }
