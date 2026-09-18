"""WO-CHEM-FULL-READINESS-005 — FULL acceptance harness tests.

Fourteen H-cases exercise the harness state machine:

    WAIT_HYDRATION / BLOCKED / READY_FOR_FULL_MATERIALIZE /
    READY_FOR_FULL_CUTOVER

All tests are read-only. The harness is a composer over existing
collectors (ops.collect_hydration_status / cutover.is_full_ready /
materialize_writer classifiers); the tests verify that the seams
translate CHEM-05 / CHEM-08 / CHEM-10 verdicts into the harness's
own verdict + block-reason vocabulary faithfully.

To keep fixtures small, tests monkeypatch the frozen-baseline
constants (EXPECTED_CHEMICAL_COUNT / EXPECTED_SECTION_COUNT / the
default preview-to-FULL baseline) and CHEM-10's full-corpus
constants. The composition logic under test is size-independent.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from services.kosha_msds import full_acceptance as fa
from services.kosha_msds import publish as pub
from services.kosha_msds import cutover
from services.kosha_msds.contract import (
    ENUMERATION_FULL_OFFICIAL,
    PUBLIC_MODE_FULL,
    PUBLIC_MODE_OFF,
    PUBLIC_MODE_SEO_PREVIEW,
    PUBLISH_NOT_PUBLISHED,
    PUBLISH_PUBLISHED_FULL,
    PUBLISH_PUBLISHED_SEO_PREVIEW,
    SNAPSHOT_COMPLETED,
)
from services.kosha_msds.materialize_writer import MemoryMaterializeStore


# Small stand-ins so fixture assembly stays cheap. The harness logic
# doesn't depend on the specific numbers as long as source /plan /
# baseline agree.
TEST_QUEUE_ROWS = 320             # analog of 329,088
TEST_CHEMICAL_COUNT = 20          # analog of 20,568
TEST_SECTION_COUNT = 320          # analog of 329,088
PREVIEW_CHEMS = 2                 # analog of 1,997
PREVIEW_SECS = PREVIEW_CHEMS * 16 # analog of 31,952


@pytest.fixture(autouse=True)
def _shrink_baselines(monkeypatch, tmp_path):
    """Rebind harness + CHEM-10 constants to the test-size baseline
    AND materialize a matching fake queue file so PATCH-1 §C tests
    don't spuriously fire QUEUE_IDENTITY_MISMATCH."""
    monkeypatch.setattr(fa, "EXPECTED_QUEUE_ROWS", TEST_QUEUE_ROWS)
    monkeypatch.setattr(fa, "EXPECTED_CHEMICAL_COUNT", TEST_CHEMICAL_COUNT)
    monkeypatch.setattr(fa, "EXPECTED_SECTION_COUNT", TEST_SECTION_COUNT)
    monkeypatch.setattr(
        fa, "DEFAULT_PREVIEW_TO_FULL_BASELINE",
        fa.MaterializeExpectedBaseline(
            chemicals_unchanged=PREVIEW_CHEMS,
            chemicals_new=TEST_CHEMICAL_COUNT - PREVIEW_CHEMS,
            chemicals_changed=0,
            sections_unchanged=PREVIEW_SECS,
            sections_new=TEST_SECTION_COUNT - PREVIEW_SECS,
            sections_changed=0,
        ),
    )
    monkeypatch.setattr(
        fa, "FULL_REPLAY_BASELINE",
        fa.MaterializeExpectedBaseline(
            chemicals_unchanged=TEST_CHEMICAL_COUNT,
            chemicals_new=0,
            chemicals_changed=0,
            sections_unchanged=TEST_SECTION_COUNT,
            sections_new=0,
            sections_changed=0,
        ),
    )
    monkeypatch.setattr(pub, "FULL_OFFICIAL_CHEMICAL_COUNT", TEST_CHEMICAL_COUNT)
    monkeypatch.setattr(pub, "FULL_OFFICIAL_SECTION_COUNT", TEST_SECTION_COUNT)

    # Fake queue: TEST_QUEUE_ROWS lines. Compute the actual SHA and
    # rebind EXPECTED_QUEUE_SHA256 so the identity gate accepts it.
    qp = tmp_path / "hydration_queue.jsonl"
    with qp.open("w", encoding="utf-8") as fh:
        for i in range(TEST_QUEUE_ROWS):
            chem = i // 16
            sec = (i % 16) + 1
            fh.write(json.dumps({
                "chemId": f"C{chem:05d}",
                "sectionNo": sec,
            }, ensure_ascii=False) + "\n")
    sha = hashlib.sha256(qp.read_bytes()).hexdigest()
    monkeypatch.setattr(fa, "EXPECTED_QUEUE_SHA256", sha)


@pytest.fixture
def valid_queue_path(tmp_path):
    """Path to the queue file materialized in _shrink_baselines (same
    tmp_path)."""
    return tmp_path / "hydration_queue.jsonl"


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _hydration(*, completed: int, remaining: int, unique=None,
               complete=None, incomplete=None) -> dict:
    if unique is None:
        unique = completed // 16 + (1 if completed % 16 else 0)
    if complete is None:
        complete = completed // 16
    if incomplete is None:
        incomplete = 1 if completed % 16 else 0
    return {
        "queue_total": TEST_QUEUE_ROWS,
        "completed": completed,
        "remaining": remaining,
        "unique_chemicals": unique,
        "complete_chemicals": complete,
        "incomplete_chemicals": incomplete,
    }


def _hydration_fully_complete() -> dict:
    return {
        "queue_total": TEST_QUEUE_ROWS,
        "completed": TEST_QUEUE_ROWS,
        "remaining": 0,
        "unique_chemicals": TEST_CHEMICAL_COUNT,
        "complete_chemicals": TEST_CHEMICAL_COUNT,
        "incomplete_chemicals": 0,
    }


def _plan_row(i: int, *, source_content_hash=None) -> dict:
    chem_id = f"C{i:05d}"
    sec_hash = source_content_hash or f"sha-{chem_id}"
    return {
        "chem_id": chem_id,
        "source_id": "KOSHA_MSDS",
        "source_key": chem_id,
        "source_content_hash": sec_hash,
        "identity_status": "READY",
        "detail_status": "COMPLETE",
        "sections": [
            {"section_no": n, "section_hash": f"h-{chem_id}-{n}",
             "result_code": "00", "item_count": 1}
            for n in range(1, 17)
        ],
    }


class _FakeMaterializeStore:
    """Thin adapter so we can use the fixture-friendly
    MemoryMaterializeStore for `preload_existing_state`. All methods
    delegate to an underlying MemoryMaterializeStore."""

    def __init__(self, chemicals=None, sections=None):
        self._inner = MemoryMaterializeStore(
            chemicals=chemicals or [], sections=sections or [],
        )

    def get_chemical_by_natural_key(self, source_id, source_key):
        return self._inner.get_chemical_by_natural_key(source_id, source_key)

    def get_section(self, chemical_id, section_no):
        return self._inner.get_section(chemical_id, section_no)

    # Bulk methods for preload_existing_state.
    def get_chemicals_by_natural_keys(self, pairs):
        out = {}
        for pair in pairs:
            row = self._inner.get_chemical_by_natural_key(pair[0], pair[1])
            if row is not None:
                out[pair] = row
        return out

    def get_sections_by_chemical_ids(self, ids):
        out = {}
        for cid in ids:
            for n in range(1, 17):
                row = self._inner.get_section(cid, n)
                if row is not None:
                    out[(str(cid), int(n))] = row
        return out


DEFAULT_MANIFEST_RESPONSES_SHA = "resp-sha"
DEFAULT_MANIFEST_PLAN_FILE_SHA = "plan-file-sha"
DEFAULT_MANIFEST_PLAN_SEM_SHA = "plan-sem-sha"
DEFAULT_ADAPTER_VERSION = "CHEM05_V1"


def _snapshot_metrics(
    *,
    adapter_version=DEFAULT_ADAPTER_VERSION,
    materialize_plan_sha256=DEFAULT_MANIFEST_PLAN_SEM_SHA,
    artifact_responses_sha256=DEFAULT_MANIFEST_RESPONSES_SHA,
) -> dict:
    """The exact dict CHEM-05 writes as `manifest.snapshot.metrics_json`
    (and CHEM-08 copies verbatim into the FULL snapshot). Used by both
    plan fixtures and publish-store snapshot fixtures so lineage
    binding matches by default (PATCH-2 §A)."""
    return {
        "adapter_version": adapter_version,
        "materialize_plan_sha256": materialize_plan_sha256,
        "artifact_responses_sha256": artifact_responses_sha256,
    }


def _plan_inputs(*, chemicals, execute_eligible=True,
                 execute_block_reasons=None,
                 responses_sha256=DEFAULT_MANIFEST_RESPONSES_SHA,
                 plan_file_sha256=DEFAULT_MANIFEST_PLAN_FILE_SHA,
                 plan_semantic_sha256=DEFAULT_MANIFEST_PLAN_SEM_SHA,
                 snapshot_metrics=None) -> object:
    """MaterializePlanInputs whose manifest.snapshot.metrics_json is the
    same shape CHEM-05 emits. PATCH-2 §A: this dict is what the harness
    passes to `is_full_ready` as `expected_materialize_binding`."""
    from services.kosha_msds.materialize_writer import MaterializePlanInputs
    metrics = _snapshot_metrics(
        materialize_plan_sha256=plan_semantic_sha256,
        artifact_responses_sha256=responses_sha256,
    ) if snapshot_metrics is None else dict(snapshot_metrics)
    return MaterializePlanInputs(
        manifest={
            "adapter_version": DEFAULT_ADAPTER_VERSION,
            "plan_semantic_sha256": plan_semantic_sha256,
            "responses_sha256": responses_sha256,
            "plan_file_sha256": plan_file_sha256,
            "execute_eligible": execute_eligible,
            "snapshot": {"metrics_json": metrics},
        },
        report={
            "execute_eligible": execute_eligible,
            "execute_block_reasons": list(execute_block_reasons or []),
            "plan_sha256": plan_semantic_sha256,
        },
        chemicals=tuple(chemicals),
    )


def _preview_materialize_store() -> _FakeMaterializeStore:
    """Preview slice: PREVIEW_CHEMS chemicals + their 16 sections."""
    chemicals = []
    sections = []
    for i in range(PREVIEW_CHEMS):
        chem_id = f"C{i:05d}"
        uuid = f"uu-{i:05d}"
        chemicals.append({
            "id": uuid, "content_id": f"CHEM:{uuid}",
            "source_id": "KOSHA_MSDS", "source_key": chem_id,
            "chem_id": chem_id,
            "source_content_hash": f"sha-{chem_id}",
        })
        for n in range(1, 17):
            sections.append({
                "chemical_id": uuid, "section_no": n,
                "section_hash": f"h-{chem_id}-{n}",
                "result_code": "00",
            })
    return _FakeMaterializeStore(chemicals=chemicals, sections=sections)


def _full_materialize_store() -> _FakeMaterializeStore:
    """Post-materialization slice: TEST_CHEMICAL_COUNT chemicals with
    identical (source_content_hash / section_hash) to the plan. When
    classified against the FULL plan the writer must classify every
    row as UNCHANGED — this is the replay-safe state after a FULL
    materialize has committed."""
    chemicals = []
    sections = []
    for i in range(TEST_CHEMICAL_COUNT):
        chem_id = f"C{i:05d}"
        uuid = f"uu-full-{i:05d}"       # match _full_membership uuids
        chemicals.append({
            "id": uuid, "content_id": f"CHEM:{uuid}",
            "source_id": "KOSHA_MSDS", "source_key": chem_id,
            "chem_id": chem_id,
            "source_content_hash": f"sha-{chem_id}",
        })
        for n in range(1, 17):
            sections.append({
                "chemical_id": uuid, "section_no": n,
                "section_hash": f"h-{chem_id}-{n}",   # match plan hash
                "result_code": "00",
            })
    return _FakeMaterializeStore(chemicals=chemicals, sections=sections)


def _snap_row(id: str, *, status=SNAPSHOT_COMPLETED,
              publish_state=PUBLISH_NOT_PUBLISHED,
              expected=TEST_CHEMICAL_COUNT, discovered=TEST_CHEMICAL_COUNT,
              completed_at="2026-09-20T10:00:00Z",
              started_at="2026-09-20T09:00:00Z",
              metrics=None) -> dict:
    """FULL snapshot fixture. metrics_json defaults match _snapshot_metrics
    so PATCH-2 §A lineage binding passes by default; individual tests
    can pass `metrics={...}` to simulate drift."""
    return {
        "id": id, "source_id": "KOSHA_MSDS", "run_type": "FULL_SYNC",
        "status": status,
        "enumeration_mode": ENUMERATION_FULL_OFFICIAL,
        "publish_state": publish_state,
        "source_contract_version": "KOSHA_MSDS_OPENAPI_V1_2",
        "expected_count": expected,
        "discovered_count": discovered,
        "started_at": started_at,
        "completed_at": completed_at,
        "metrics_json": _snapshot_metrics() if metrics is None else dict(metrics),
    }


def _full_membership(snap_id: str, count: int = TEST_CHEMICAL_COUNT) -> list:
    return [{"snapshot_id": snap_id, "chemical_id": f"uu-full-{i:05d}",
             "detail_status": "COMPLETE", "in_snapshot": True}
            for i in range(count)]


def _full_sections(count: int = TEST_CHEMICAL_COUNT) -> list:
    out = []
    for i in range(count):
        cid = f"uu-full-{i:05d}"
        for n in range(1, 17):
            out.append({"chemical_id": cid, "section_no": n,
                        "section_hash": f"h-{cid}-{n}",
                        "result_code": "00"})
    return out


def _valid_full_publish_store() -> pub.MemoryPublishStore:
    """One COMPLETED / NOT_PUBLISHED FULL candidate + full membership +
    full sections. This is the input to Stage E."""
    return pub.MemoryPublishStore(
        snapshots=[_snap_row("snap-FULL")],
        snapshot_items=_full_membership("snap-FULL"),
        sections=_full_sections(),
    )


def _dict_v2() -> dict:
    return {
        "binding": "V2_MATCH",
        "runtime_snapshot": "SEARCH-DICT-LEGPROD-2026-09-16",
        "chem_term_msds_matched": True,
        "chem_term_sds_matched": True,
        "error": None,
    }


def _dict_offline() -> dict:
    return {
        "binding": "UNVERIFIED_NETWORK",
        "runtime_snapshot": None,
        "chem_term_msds_matched": None,
        "chem_term_sds_matched": None,
        "error": "HTTPError: 503",
    }


# ---------------------------------------------------------------------------
# H1 — current production state (partial hydration) → WAIT_HYDRATION
# ---------------------------------------------------------------------------


def test_H1_current_production_state_returns_wait_hydration():
    """31,961 completed / 297,127 remaining in the analog. No block
    reasons — just not-yet-done."""
    hydration = _hydration(
        completed=int(TEST_QUEUE_ROWS * 0.10),      # ~10%
        remaining=int(TEST_QUEUE_ROWS * 0.90),
    )
    r = fa.evaluate_full_acceptance(
        hydration_status=hydration,
        dictionary_status=_dict_offline(),
    )
    assert r.verdict == fa.VERDICT_WAIT_HYDRATION
    assert r.overall_block_reasons == ()
    # Source stage NOT ready.
    src = next(s for s in r.stages if s.name == "source")
    assert src.ready is False


# ---------------------------------------------------------------------------
# H2 — hydration short by exactly 1 → WAIT_HYDRATION
# ---------------------------------------------------------------------------


def test_H2_hydration_short_by_one_returns_wait_hydration():
    hydration = {
        "queue_total": TEST_QUEUE_ROWS,
        "completed": TEST_QUEUE_ROWS - 1,
        "remaining": 1,
        "unique_chemicals": TEST_CHEMICAL_COUNT,
        "complete_chemicals": TEST_CHEMICAL_COUNT - 1,
        "incomplete_chemicals": 1,
    }
    r = fa.evaluate_full_acceptance(
        hydration_status=hydration,
        dictionary_status=_dict_offline(),
    )
    assert r.verdict == fa.VERDICT_WAIT_HYDRATION
    assert fa.BLOCK_QUEUE_IDENTITY_MISMATCH not in r.overall_block_reasons


# ---------------------------------------------------------------------------
# H3 — plan reports DUPLICATE_PAIRS → BLOCKED / DUPLICATE_SOURCE_PAIR
# ---------------------------------------------------------------------------


def test_H3_duplicate_source_pair_blocks(valid_queue_path):
    """CHEM-05 detected a duplicate (chem_id, section_no) pair; the
    harness surfaces it as BLOCK_DUPLICATE_SOURCE_PAIR and refuses."""
    chemicals = [_plan_row(i) for i in range(TEST_CHEMICAL_COUNT)]
    plan = _plan_inputs(
        chemicals=chemicals,
        execute_eligible=False,
        execute_block_reasons=["DUPLICATE_PAIRS"],
    )
    r = fa.evaluate_full_acceptance(
        hydration_status=_hydration_fully_complete(),
        plan_inputs=plan,
        dictionary_status=_dict_offline(),
        queue_path=valid_queue_path,
    )
    assert r.verdict == fa.VERDICT_BLOCKED
    assert fa.BLOCK_DUPLICATE_SOURCE_PAIR in r.overall_block_reasons


# ---------------------------------------------------------------------------
# H4 — full source (integrity + all_full=True) → source stage ready
# ---------------------------------------------------------------------------


def test_H4_full_source_ready(valid_queue_path):
    """Source-only readiness check. B/C/D/E are not-ready here (no
    plan / no store), but Stage A is ready — verdict is BLOCKED at
    the intermediate branch because stages beyond A are pending. The
    intermediate BLOCKED (PATCH-1 §F) names WHY: no plan supplied."""
    r = fa.evaluate_full_acceptance(
        hydration_status=_hydration_fully_complete(),
        dictionary_status=_dict_offline(),
        queue_path=valid_queue_path,
    )
    src = next(s for s in r.stages if s.name == "source")
    assert src.ready is True
    assert src.block_reasons == ()
    # A is ready but B is not (no plan) → BLOCKED with a derived reason.
    assert r.verdict == fa.VERDICT_BLOCKED
    assert fa.BLOCK_NOT_FULL_PLAN in r.overall_block_reasons


# ---------------------------------------------------------------------------
# H5 — preview plan (1997 → PREVIEW_CHEMS) → BLOCKED / NOT_FULL_PLAN
# ---------------------------------------------------------------------------


def test_H5_preview_plan_blocks_not_full_plan(valid_queue_path):
    chemicals = [_plan_row(i) for i in range(PREVIEW_CHEMS)]
    plan = _plan_inputs(chemicals=chemicals, execute_eligible=True)
    r = fa.evaluate_full_acceptance(
        hydration_status=_hydration_fully_complete(),
        plan_inputs=plan,
        dictionary_status=_dict_offline(),
        queue_path=valid_queue_path,
    )
    assert r.verdict == fa.VERDICT_BLOCKED
    assert fa.BLOCK_NOT_FULL_PLAN in r.overall_block_reasons


# ---------------------------------------------------------------------------
# H6 — full plan exact → plan stage ready
# ---------------------------------------------------------------------------


def test_H6_full_plan_ready(valid_queue_path):
    chemicals = [_plan_row(i) for i in range(TEST_CHEMICAL_COUNT)]
    plan = _plan_inputs(chemicals=chemicals, execute_eligible=True)
    r = fa.evaluate_full_acceptance(
        hydration_status=_hydration_fully_complete(),
        plan_inputs=plan,
        dictionary_status=_dict_offline(),
        queue_path=valid_queue_path,
    )
    b = next(s for s in r.stages if s.name == "plan")
    assert b.ready is True
    assert b.block_reasons == ()
    assert b.evidence["chemicals"] == TEST_CHEMICAL_COUNT
    assert b.evidence["sections"] == TEST_SECTION_COUNT


# ---------------------------------------------------------------------------
# H7 — preview→FULL dry-run under PRE baseline (no FULL candidate yet)
# ---------------------------------------------------------------------------


def test_H7_preview_to_full_dry_run_matches_pre_baseline(valid_queue_path):
    """Store already carries PREVIEW_CHEMS chemicals; plan is FULL; no
    FULL candidate in publish store → harness auto-selects PRE baseline.
    Expected: PREVIEW_CHEMS UNCHANGED + (FULL - PREVIEW_CHEMS) NEW +
    0 CONFLICT at both chemical and section levels."""
    mat_store = _preview_materialize_store()
    chemicals = [_plan_row(i) for i in range(TEST_CHEMICAL_COUNT)]
    plan = _plan_inputs(chemicals=chemicals, execute_eligible=True)
    r = fa.evaluate_full_acceptance(
        hydration_status=_hydration_fully_complete(),
        plan_inputs=plan,
        materialize_store=mat_store,
        dictionary_status=_dict_offline(),
        queue_path=valid_queue_path,
    )
    c = next(s for s in r.stages if s.name == "materialize")
    assert c.ready is True, c.to_dict()
    assert c.evidence["baseline_source"] == "pre_materialize_preview_to_full"
    counts_c = c.evidence["chemical_counts"]
    counts_s = c.evidence["section_counts"]
    assert counts_c["UNCHANGED"] == PREVIEW_CHEMS
    assert counts_c["NEW"] == TEST_CHEMICAL_COUNT - PREVIEW_CHEMS
    assert counts_c["CONFLICT"] == 0
    assert counts_s["UNCHANGED"] == PREVIEW_SECS
    assert counts_s["NEW"] == TEST_SECTION_COUNT - PREVIEW_SECS
    assert counts_s["CONFLICT"] == 0


# ---------------------------------------------------------------------------
# H8 — identity regeneration on UNCHANGED row → BLOCKED / IDENTITY_REGENERATION
# ---------------------------------------------------------------------------


def test_H8_identity_regeneration_blocks(valid_queue_path):
    """Simulate a DB row that matches natural key and content hash but
    carries no `id` column (would force writer to mint a new UUID for
    an UNCHANGED chemical). The classifier surfaces this via
    db_chemical_id=None; the harness raises IDENTITY_REGENERATION."""
    bad = [{
        "id": None, "source_id": "KOSHA_MSDS", "source_key": "C00000",
        "chem_id": "C00000",
        "source_content_hash": "sha-C00000",
        "content_id": None,
    }]
    mat_store = _FakeMaterializeStore(chemicals=bad, sections=[])
    chemicals = [_plan_row(i) for i in range(TEST_CHEMICAL_COUNT)]
    plan = _plan_inputs(chemicals=chemicals, execute_eligible=True)
    r = fa.evaluate_full_acceptance(
        hydration_status=_hydration_fully_complete(),
        plan_inputs=plan,
        materialize_store=mat_store,
        dictionary_status=_dict_offline(),
        queue_path=valid_queue_path,
    )
    assert r.verdict == fa.VERDICT_BLOCKED
    assert fa.BLOCK_IDENTITY_REGENERATION in r.overall_block_reasons


# ---------------------------------------------------------------------------
# H9 — CONFLICT at chemical level → BLOCKED / CHEMICAL_CONFLICT
# ---------------------------------------------------------------------------


def test_H9_materialize_conflict_blocks(valid_queue_path):
    """DB row's chem_id disagrees with the plan's chem_id for the same
    natural key — a CONFLICT classification, must block."""
    bad = [{
        "id": "uu-conflict", "content_id": "CHEM:uu-conflict",
        "source_id": "KOSHA_MSDS", "source_key": "C00000",
        "chem_id": "C99999",                # ← disagrees with plan
        "source_content_hash": "sha-C00000",
    }]
    mat_store = _FakeMaterializeStore(chemicals=bad, sections=[])
    chemicals = [_plan_row(i) for i in range(TEST_CHEMICAL_COUNT)]
    plan = _plan_inputs(chemicals=chemicals, execute_eligible=True)
    r = fa.evaluate_full_acceptance(
        hydration_status=_hydration_fully_complete(),
        plan_inputs=plan,
        materialize_store=mat_store,
        dictionary_status=_dict_offline(),
        queue_path=valid_queue_path,
    )
    assert r.verdict == fa.VERDICT_BLOCKED
    assert fa.BLOCK_CHEMICAL_CONFLICT in r.overall_block_reasons


# ---------------------------------------------------------------------------
# H10 — full plan + no FULL snapshot → READY_FOR_FULL_MATERIALIZE
# ---------------------------------------------------------------------------


def test_H10_no_full_snapshot_yields_ready_for_full_materialize(valid_queue_path):
    """Source complete, plan ready, dry-run passes (PRE baseline);
    publish_store has no COMPLETED / FULL_OFFICIAL / NOT_PUBLISHED
    candidate. Harness stops at READY_FOR_FULL_MATERIALIZE."""
    mat_store = _preview_materialize_store()
    prev_snap = _snap_row("snap-preview",
                          publish_state=PUBLISH_PUBLISHED_SEO_PREVIEW,
                          expected=PREVIEW_CHEMS, discovered=PREVIEW_CHEMS)
    pub_store = pub.MemoryPublishStore(snapshots=[prev_snap])
    chemicals = [_plan_row(i) for i in range(TEST_CHEMICAL_COUNT)]
    plan = _plan_inputs(chemicals=chemicals, execute_eligible=True)
    r = fa.evaluate_full_acceptance(
        hydration_status=_hydration_fully_complete(),
        plan_inputs=plan,
        materialize_store=mat_store,
        publish_store=pub_store,
        dictionary_status=_dict_v2(),
        queue_path=valid_queue_path,
    )
    assert r.verdict == fa.VERDICT_READY_FOR_FULL_MATERIALIZE, r.to_dict()
    d = next(s for s in r.stages if s.name == "materialized_full")
    assert d.ready is False
    assert d.evidence.get("note") == "NOT_YET_MATERIALIZED"


# ---------------------------------------------------------------------------
# H11 — complete FULL candidate → publish stage delegates PASS
# ---------------------------------------------------------------------------


def test_H11_complete_full_candidate_publish_stage_ready(valid_queue_path):
    """Publish store has a fully-materialized FULL_OFFICIAL / NOT_PUBLISHED
    snapshot with expected/discovered/items/sections all lined up.
    Publish stage should surface cutover.is_full_ready ready=True.

    PATCH-1 §A: the presence of a FULL candidate (D.ready) auto-picks
    the POST replay baseline for Stage C; the materialize store passed
    here matches that (full-materialized). Everything green except
    public_mode → G not ready; verdict = BLOCKED but D and E still
    surface as ready."""
    pub_store = _valid_full_publish_store()
    ready = cutover.is_full_ready("snap-FULL", store=pub_store)
    assert ready.ready is True

    mat_store = _full_materialize_store()
    chemicals = [_plan_row(i) for i in range(TEST_CHEMICAL_COUNT)]
    plan = _plan_inputs(chemicals=chemicals, execute_eligible=True)
    r = fa.evaluate_full_acceptance(
        hydration_status=_hydration_fully_complete(),
        plan_inputs=plan,
        materialize_store=mat_store,
        publish_store=pub_store,
        dictionary_status=_dict_v2(),
        queue_path=valid_queue_path,
    )
    d = next(s for s in r.stages if s.name == "materialized_full")
    e = next(s for s in r.stages if s.name == "publish")
    assert d.ready is True
    assert d.evidence["snapshot_id"] == "snap-FULL"
    assert e.ready is True
    assert e.block_reasons == ()


# ---------------------------------------------------------------------------
# H12 — search-dict 503 → SEARCH_RUNTIME_READY=false → BLOCKED with reason
# ---------------------------------------------------------------------------


def test_H12_search_dict_offline_blocks_public_cutover(valid_queue_path):
    """Dictionary probe returns UNVERIFIED_NETWORK. Stage F not-ready
    prevents the READY_FOR_FULL_CUTOVER transition. PATCH-1 §F: the
    resulting BLOCKED verdict names WHY via BLOCK_SEARCH_RUNTIME_NOT_READY."""
    pub_store = _valid_full_publish_store()
    mat_store = _full_materialize_store()
    chemicals = [_plan_row(i) for i in range(TEST_CHEMICAL_COUNT)]
    plan = _plan_inputs(chemicals=chemicals, execute_eligible=True)
    r = fa.evaluate_full_acceptance(
        hydration_status=_hydration_fully_complete(),
        plan_inputs=plan,
        materialize_store=mat_store,
        publish_store=pub_store,
        dictionary_status=_dict_offline(),
        public_mode=PUBLIC_MODE_SEO_PREVIEW,
        queue_path=valid_queue_path,
    )
    f = next(s for s in r.stages if s.name == "search_runtime")
    assert f.ready is False
    assert r.verdict == fa.VERDICT_BLOCKED
    assert fa.BLOCK_SEARCH_RUNTIME_NOT_READY in r.overall_block_reasons


# ---------------------------------------------------------------------------
# H13 — search-dict V2 → SEARCH_RUNTIME_READY=true
# ---------------------------------------------------------------------------


def test_H13_search_dict_v2_makes_stage_ready():
    r_stage = fa.evaluate_search_runtime_stage(_dict_v2())
    assert r_stage.ready is True
    assert r_stage.evidence["binding"] == "V2_MATCH"
    assert r_stage.evidence["chem_term_msds_matched"] is True

    partial = dict(_dict_v2())
    partial["chem_term_msds_matched"] = False
    assert fa.evaluate_search_runtime_stage(partial).ready is False


# ---------------------------------------------------------------------------
# H14 — POST-materialization green path → READY_FOR_FULL_CUTOVER
# ---------------------------------------------------------------------------


def test_H14_post_materialization_all_green_returns_ready_for_full_cutover(
    valid_queue_path,
):
    """PATCH-1 §D: H14 now models the real production lifecycle at the
    point where FULL materialization has completed. Both stores hold
    the FULL corpus (the same Supabase DB in production). Classifying
    the plan against the FULL materialize store yields UNCHANGED for
    every row (POST replay baseline). Publish preflight passes; search
    dictionary is V2; public mode is seo_preview → READY_FOR_FULL_CUTOVER."""
    mat_store = _full_materialize_store()
    pub_store = _valid_full_publish_store()
    chemicals = [_plan_row(i) for i in range(TEST_CHEMICAL_COUNT)]
    plan = _plan_inputs(chemicals=chemicals, execute_eligible=True)

    r = fa.evaluate_full_acceptance(
        hydration_status=_hydration_fully_complete(),
        plan_inputs=plan,
        materialize_store=mat_store,
        publish_store=pub_store,
        dictionary_status=_dict_v2(),
        public_mode=PUBLIC_MODE_SEO_PREVIEW,
        queue_path=valid_queue_path,
    )

    c = next(s for s in r.stages if s.name == "materialize")
    assert c.evidence["baseline_source"] == "post_materialize_replay"
    counts_c = c.evidence["chemical_counts"]
    counts_s = c.evidence["section_counts"]
    assert counts_c["UNCHANGED"] == TEST_CHEMICAL_COUNT
    assert counts_c["NEW"] == 0
    assert counts_c["CHANGED"] == 0
    assert counts_c["CONFLICT"] == 0
    assert counts_s["UNCHANGED"] == TEST_SECTION_COUNT
    assert counts_s["NEW"] == 0

    assert r.verdict == fa.VERDICT_READY_FOR_FULL_CUTOVER, r.to_dict()
    assert r.overall_block_reasons == ()
    for s in r.stages:
        assert s.ready is True, f"stage {s.name} not ready: {s.to_dict()}"


# ---------------------------------------------------------------------------
# H14b — running-snapshot hold overrides even the green path (WO §19)
# ---------------------------------------------------------------------------


def test_H14b_running_snapshot_hold_forces_blocked(valid_queue_path):
    mat_store = _full_materialize_store()
    pub_store = _valid_full_publish_store()
    chemicals = [_plan_row(i) for i in range(TEST_CHEMICAL_COUNT)]
    plan = _plan_inputs(chemicals=chemicals, execute_eligible=True)
    r = fa.evaluate_full_acceptance(
        hydration_status=_hydration_fully_complete(),
        plan_inputs=plan,
        materialize_store=mat_store,
        publish_store=pub_store,
        dictionary_status=_dict_v2(),
        public_mode=PUBLIC_MODE_SEO_PREVIEW,
        queue_path=valid_queue_path,
        running_snapshots=1,
    )
    assert r.verdict == fa.VERDICT_BLOCKED
    assert fa.BLOCK_RUNNING_SNAPSHOT_HOLD in r.overall_block_reasons


# ---------------------------------------------------------------------------
# H15 — PRE baseline drift → BLOCKED / EXPECTED_BASELINE_DRIFT
# ---------------------------------------------------------------------------


def test_H15_pre_baseline_drift_blocks(valid_queue_path):
    """Materialize store shape doesn't match the PRE baseline (one
    fewer preview chemical, so UNCHANGED = PREVIEW_CHEMS - 1). No FULL
    candidate → PRE baseline chosen → drift → BLOCKED."""
    mat_store = _preview_materialize_store()
    # Trim one preview chemical from the materialize store so the
    # UNCHANGED count is PREVIEW_CHEMS - 1 (drift from PRE baseline).
    mat_store._inner._chemicals_by_key.pop(("KOSHA_MSDS", "C00000"))
    # Remove its sections too.
    for n in range(1, 17):
        mat_store._inner._sections_by_pair.pop(("uu-00000", n), None)

    chemicals = [_plan_row(i) for i in range(TEST_CHEMICAL_COUNT)]
    plan = _plan_inputs(chemicals=chemicals, execute_eligible=True)
    r = fa.evaluate_full_acceptance(
        hydration_status=_hydration_fully_complete(),
        plan_inputs=plan,
        materialize_store=mat_store,
        dictionary_status=_dict_offline(),
        queue_path=valid_queue_path,
    )
    assert r.verdict == fa.VERDICT_BLOCKED, r.to_dict()
    assert fa.BLOCK_EXPECTED_BASELINE_DRIFT in r.overall_block_reasons


# ---------------------------------------------------------------------------
# H16 — POST materialization replay is UNCHANGED across the board
# ---------------------------------------------------------------------------


def test_H16_post_materialization_replay_passes(valid_queue_path):
    """FULL candidate present + FULL materialize store → POST replay
    baseline. Every plan row classifies UNCHANGED with 0 NEW / 0
    CHANGED / 0 CONFLICT."""
    mat_store = _full_materialize_store()
    pub_store = _valid_full_publish_store()
    chemicals = [_plan_row(i) for i in range(TEST_CHEMICAL_COUNT)]
    plan = _plan_inputs(chemicals=chemicals, execute_eligible=True)
    r = fa.evaluate_full_acceptance(
        hydration_status=_hydration_fully_complete(),
        plan_inputs=plan,
        materialize_store=mat_store,
        publish_store=pub_store,
        dictionary_status=_dict_v2(),
        queue_path=valid_queue_path,
    )
    c = next(s for s in r.stages if s.name == "materialize")
    assert c.evidence["baseline_source"] == "post_materialize_replay"
    assert c.ready is True
    counts_c = c.evidence["chemical_counts"]
    counts_s = c.evidence["section_counts"]
    assert counts_c["UNCHANGED"] == TEST_CHEMICAL_COUNT
    assert counts_c["NEW"] == 0
    assert counts_c["CHANGED"] == 0
    assert counts_c["CONFLICT"] == 0
    assert counts_s["UNCHANGED"] == TEST_SECTION_COUNT
    assert counts_s["NEW"] == 0
    assert counts_s["CHANGED"] == 0
    assert counts_s["CONFLICT"] == 0


# ---------------------------------------------------------------------------
# H17 — wrong hydration/plan binding → BLOCKED / MANIFEST_BINDING_MISMATCH
# ---------------------------------------------------------------------------


def test_H17_wrong_hydration_plan_binding_blocks(valid_queue_path):
    """Hydration reports responses_sha256=A; the plan manifest claims
    B. The harness must reject this — a plan built from a different
    artifact than the one currently in hydration cannot pass."""
    chemicals = [_plan_row(i) for i in range(TEST_CHEMICAL_COUNT)]
    plan = _plan_inputs(chemicals=chemicals, execute_eligible=True,
                        responses_sha256="manifest-sha-B")
    r = fa.evaluate_full_acceptance(
        hydration_status=_hydration_fully_complete(),
        plan_inputs=plan,
        dictionary_status=_dict_offline(),
        queue_path=valid_queue_path,
        hydration_responses_sha256="on-disk-sha-A",
    )
    assert r.verdict == fa.VERDICT_BLOCKED
    assert fa.BLOCK_MANIFEST_BINDING_MISMATCH in r.overall_block_reasons


# ---------------------------------------------------------------------------
# H18 — plan file tamper → BLOCKED / MANIFEST_BINDING_MISMATCH
# ---------------------------------------------------------------------------


def test_H18_plan_file_tamper_blocks(valid_queue_path):
    """manifest.plan_file_sha256 = A; on-disk plan file recomputes to
    B. The harness's Stage B calls verify_manifest_binding with the
    recomputed value and refuses."""
    chemicals = [_plan_row(i) for i in range(TEST_CHEMICAL_COUNT)]
    plan = _plan_inputs(chemicals=chemicals, execute_eligible=True,
                        plan_file_sha256="manifest-plan-sha-A")
    r = fa.evaluate_full_acceptance(
        hydration_status=_hydration_fully_complete(),
        plan_inputs=plan,
        dictionary_status=_dict_offline(),
        queue_path=valid_queue_path,
        on_disk_plan_file_sha256="on-disk-plan-sha-B",
    )
    assert r.verdict == fa.VERDICT_BLOCKED
    assert fa.BLOCK_MANIFEST_BINDING_MISMATCH in r.overall_block_reasons


# ---------------------------------------------------------------------------
# H19 — FULL source but queue file missing → BLOCKED / QUEUE_IDENTITY_MISMATCH
# ---------------------------------------------------------------------------


def test_H19_full_source_but_queue_missing_blocks(tmp_path):
    """Hydration reports all-full but no queue file supplied. PATCH-1
    §C requires the frozen queue as evidence at FULL — missing = block."""
    missing = tmp_path / "does_not_exist.jsonl"
    r = fa.evaluate_full_acceptance(
        hydration_status=_hydration_fully_complete(),
        dictionary_status=_dict_offline(),
        queue_path=missing,
    )
    assert r.verdict == fa.VERDICT_BLOCKED
    assert fa.BLOCK_QUEUE_IDENTITY_MISMATCH in r.overall_block_reasons


# ---------------------------------------------------------------------------
# H20 — current production baseline still yields WAIT_HYDRATION
# ---------------------------------------------------------------------------


def test_H20_current_production_still_wait_hydration(valid_queue_path):
    """The PATCH-1 changes must not alter the current production
    verdict (31,961 / 297,127 in the analog). Hydration incomplete →
    WAIT_HYDRATION, no block reasons."""
    hydration = _hydration(
        completed=int(TEST_QUEUE_ROWS * 0.10),
        remaining=int(TEST_QUEUE_ROWS * 0.90),
    )
    r = fa.evaluate_full_acceptance(
        hydration_status=hydration,
        dictionary_status=_dict_offline(),
        queue_path=valid_queue_path,
    )
    assert r.verdict == fa.VERDICT_WAIT_HYDRATION
    assert r.overall_block_reasons == ()


# ---------------------------------------------------------------------------
# H21 — plan semantic SHA ≠ snapshot's → BLOCKED / MATERIALIZE_BINDING_MISMATCH
# ---------------------------------------------------------------------------


def test_H21_plan_snapshot_binding_drift_blocks(valid_queue_path):
    """FULL snapshot's metrics_json.materialize_plan_sha256 disagrees
    with the current plan's plan_semantic_sha256. PATCH-2 §A: the
    harness threads the plan's lineage into CHEM-10's canonical
    MATERIALIZE_BINDING_MISMATCH gate, which fires."""
    mat_store = _full_materialize_store()
    # FULL snapshot was materialized from a DIFFERENT plan (SHA=B).
    stale_snapshot = _snap_row(
        "snap-FULL",
        metrics=_snapshot_metrics(
            materialize_plan_sha256="STALE-plan-sem-sha",
            artifact_responses_sha256=DEFAULT_MANIFEST_RESPONSES_SHA,
        ),
    )
    pub_store = pub.MemoryPublishStore(
        snapshots=[stale_snapshot],
        snapshot_items=_full_membership("snap-FULL"),
        sections=_full_sections(),
    )
    chemicals = [_plan_row(i) for i in range(TEST_CHEMICAL_COUNT)]
    plan = _plan_inputs(chemicals=chemicals, execute_eligible=True)

    r = fa.evaluate_full_acceptance(
        hydration_status=_hydration_fully_complete(),
        plan_inputs=plan,
        materialize_store=mat_store,
        publish_store=pub_store,
        dictionary_status=_dict_v2(),
        queue_path=valid_queue_path,
    )
    e = next(s for s in r.stages if s.name == "publish")
    assert e.ready is False, e.to_dict()
    assert r.verdict == fa.VERDICT_BLOCKED
    assert "MATERIALIZE_BINDING_MISMATCH" in r.overall_block_reasons


# ---------------------------------------------------------------------------
# H22 — hydration responses SHA ≠ snapshot's → BLOCKED
# ---------------------------------------------------------------------------


def test_H22_hydration_snapshot_binding_drift_blocks(valid_queue_path):
    """Same failure surface as H21 but the drift is in
    artifact_responses_sha256 (FULL snapshot was built from a
    different hydration artifact than what the plan now points at)."""
    mat_store = _full_materialize_store()
    stale_snapshot = _snap_row(
        "snap-FULL",
        metrics=_snapshot_metrics(
            materialize_plan_sha256=DEFAULT_MANIFEST_PLAN_SEM_SHA,
            artifact_responses_sha256="STALE-artifact-responses-sha",
        ),
    )
    pub_store = pub.MemoryPublishStore(
        snapshots=[stale_snapshot],
        snapshot_items=_full_membership("snap-FULL"),
        sections=_full_sections(),
    )
    chemicals = [_plan_row(i) for i in range(TEST_CHEMICAL_COUNT)]
    plan = _plan_inputs(chemicals=chemicals, execute_eligible=True)

    r = fa.evaluate_full_acceptance(
        hydration_status=_hydration_fully_complete(),
        plan_inputs=plan,
        materialize_store=mat_store,
        publish_store=pub_store,
        dictionary_status=_dict_v2(),
        queue_path=valid_queue_path,
    )
    assert r.verdict == fa.VERDICT_BLOCKED
    assert "MATERIALIZE_BINDING_MISMATCH" in r.overall_block_reasons


# ---------------------------------------------------------------------------
# H23 — all binding matches → publish stage PASSes with lineage recorded
# ---------------------------------------------------------------------------


def test_H23_all_binding_matches_publish_ready(valid_queue_path):
    """FULL snapshot's metrics_json exactly matches the plan's
    manifest.snapshot.metrics_json (default fixture shape). Publish
    stage passes; evidence records the expected binding for
    provenance."""
    mat_store = _full_materialize_store()
    pub_store = _valid_full_publish_store()
    chemicals = [_plan_row(i) for i in range(TEST_CHEMICAL_COUNT)]
    plan = _plan_inputs(chemicals=chemicals, execute_eligible=True)

    r = fa.evaluate_full_acceptance(
        hydration_status=_hydration_fully_complete(),
        plan_inputs=plan,
        materialize_store=mat_store,
        publish_store=pub_store,
        dictionary_status=_dict_v2(),
        queue_path=valid_queue_path,
    )
    e = next(s for s in r.stages if s.name == "publish")
    assert e.ready is True, e.to_dict()
    assert "MATERIALIZE_BINDING_MISMATCH" not in r.overall_block_reasons
    binding = e.evidence.get("expected_materialize_binding") or {}
    assert binding.get("materialize_plan_sha256") == DEFAULT_MANIFEST_PLAN_SEM_SHA
    assert binding.get("artifact_responses_sha256") == DEFAULT_MANIFEST_RESPONSES_SHA


# ---------------------------------------------------------------------------
# H24 — everything green except public_mode=off → BLOCKED with reason
# ---------------------------------------------------------------------------


def test_H24_public_mode_off_blocks_with_reason(valid_queue_path):
    """A..F all ready but public_mode='off'. PATCH-2 §B: harness now
    surfaces BLOCK_PUBLIC_MODE_NOT_SEO_PREVIEW so the BLOCKED verdict
    is never reason-less."""
    mat_store = _full_materialize_store()
    pub_store = _valid_full_publish_store()
    chemicals = [_plan_row(i) for i in range(TEST_CHEMICAL_COUNT)]
    plan = _plan_inputs(chemicals=chemicals, execute_eligible=True)

    r = fa.evaluate_full_acceptance(
        hydration_status=_hydration_fully_complete(),
        plan_inputs=plan,
        materialize_store=mat_store,
        publish_store=pub_store,
        dictionary_status=_dict_v2(),
        public_mode=PUBLIC_MODE_OFF,
        queue_path=valid_queue_path,
    )
    assert r.verdict == fa.VERDICT_BLOCKED
    assert fa.BLOCK_PUBLIC_MODE_NOT_SEO_PREVIEW in r.overall_block_reasons


# ---------------------------------------------------------------------------
# H25 — everything green with public_mode=seo_preview → READY_FOR_FULL_CUTOVER
# ---------------------------------------------------------------------------


def test_H25_public_mode_seo_preview_yields_ready_for_cutover(valid_queue_path):
    """The mirror of H24: same green setup but public_mode=seo_preview
    → READY_FOR_FULL_CUTOVER. Confirms H24's block reason is scoped
    to the wrong mode only."""
    mat_store = _full_materialize_store()
    pub_store = _valid_full_publish_store()
    chemicals = [_plan_row(i) for i in range(TEST_CHEMICAL_COUNT)]
    plan = _plan_inputs(chemicals=chemicals, execute_eligible=True)

    r = fa.evaluate_full_acceptance(
        hydration_status=_hydration_fully_complete(),
        plan_inputs=plan,
        materialize_store=mat_store,
        publish_store=pub_store,
        dictionary_status=_dict_v2(),
        public_mode=PUBLIC_MODE_SEO_PREVIEW,
        queue_path=valid_queue_path,
    )
    assert r.verdict == fa.VERDICT_READY_FOR_FULL_CUTOVER, r.to_dict()
    assert r.overall_block_reasons == ()


# ---------------------------------------------------------------------------
# H26 — FULL source but queue file unreadable → BLOCKED / QUEUE_IDENTITY_MISMATCH
# ---------------------------------------------------------------------------


def test_H26_full_source_queue_read_failure_blocks(tmp_path, monkeypatch):
    """PATCH-2 §C: file exists but read raises. Under FULL that must
    fail-closed. We stub queue_path.open to raise OSError while
    keeping .exists()=True."""
    fake_queue = tmp_path / "unreadable_queue.jsonl"
    fake_queue.write_text("placeholder\n", encoding="utf-8")

    real_open = Path.open

    def _fail_open(self, *args, **kwargs):
        if self == fake_queue:
            raise OSError("simulated permission denied")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", _fail_open)

    r = fa.evaluate_full_acceptance(
        hydration_status=_hydration_fully_complete(),
        dictionary_status=_dict_offline(),
        queue_path=fake_queue,
    )
    assert r.verdict == fa.VERDICT_BLOCKED
    assert fa.BLOCK_QUEUE_IDENTITY_MISMATCH in r.overall_block_reasons
    src = next(s for s in r.stages if s.name == "source")
    assert "queue_error" in src.evidence
