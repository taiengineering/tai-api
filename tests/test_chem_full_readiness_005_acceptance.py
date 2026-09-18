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
def _shrink_baselines(monkeypatch):
    """Rebind harness + CHEM-10 constants to the test-size baseline."""
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
    monkeypatch.setattr(pub, "FULL_OFFICIAL_CHEMICAL_COUNT", TEST_CHEMICAL_COUNT)
    monkeypatch.setattr(pub, "FULL_OFFICIAL_SECTION_COUNT", TEST_SECTION_COUNT)


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


def _plan_inputs(*, chemicals, execute_eligible=True,
                 execute_block_reasons=None) -> object:
    from services.kosha_msds.materialize_writer import MaterializePlanInputs
    return MaterializePlanInputs(
        manifest={
            "adapter_version": "CHEM05_V1",
            "plan_semantic_sha256": "plan-sem-sha",
            "responses_sha256": "resp-sha",
            "plan_file_sha256": "plan-file-sha",
            "execute_eligible": execute_eligible,
        },
        report={
            "execute_eligible": execute_eligible,
            "execute_block_reasons": list(execute_block_reasons or []),
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


def _snap_row(id: str, *, status=SNAPSHOT_COMPLETED,
              publish_state=PUBLISH_NOT_PUBLISHED,
              expected=TEST_CHEMICAL_COUNT, discovered=TEST_CHEMICAL_COUNT,
              completed_at="2026-09-20T10:00:00Z",
              started_at="2026-09-20T09:00:00Z",
              metrics=None) -> dict:
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
        "metrics_json": dict(metrics or {
            "adapter_version": "CHEM05_V1",
            "materialize_plan_sha256": "plan-sem-sha",
            "responses_sha256": "resp-sha",
        }),
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


def test_H3_duplicate_source_pair_blocks():
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
    )
    assert r.verdict == fa.VERDICT_BLOCKED
    assert fa.BLOCK_DUPLICATE_SOURCE_PAIR in r.overall_block_reasons


# ---------------------------------------------------------------------------
# H4 — full source (integrity + all_full=True) → source stage ready
# ---------------------------------------------------------------------------


def test_H4_full_source_ready():
    """Source-only readiness check. B/C/D/E are not-ready here (no
    plan / no store), but Stage A is ready — verdict is BLOCKED at
    the intermediate branch because stages beyond A are pending."""
    r = fa.evaluate_full_acceptance(
        hydration_status=_hydration_fully_complete(),
        dictionary_status=_dict_offline(),
    )
    src = next(s for s in r.stages if s.name == "source")
    assert src.ready is True
    assert src.block_reasons == ()
    # A is ready but B is not (no plan), so we're neither WAIT_HYDRATION
    # nor READY_FOR_*.
    assert r.verdict == fa.VERDICT_BLOCKED
    assert r.overall_block_reasons == ()


# ---------------------------------------------------------------------------
# H5 — preview plan (1997 → PREVIEW_CHEMS) → BLOCKED / NOT_FULL_PLAN
# ---------------------------------------------------------------------------


def test_H5_preview_plan_blocks_not_full_plan():
    chemicals = [_plan_row(i) for i in range(PREVIEW_CHEMS)]
    plan = _plan_inputs(chemicals=chemicals, execute_eligible=True)
    r = fa.evaluate_full_acceptance(
        hydration_status=_hydration_fully_complete(),
        plan_inputs=plan,
        dictionary_status=_dict_offline(),
    )
    assert r.verdict == fa.VERDICT_BLOCKED
    assert fa.BLOCK_NOT_FULL_PLAN in r.overall_block_reasons


# ---------------------------------------------------------------------------
# H6 — full plan exact → plan stage ready
# ---------------------------------------------------------------------------


def test_H6_full_plan_ready():
    chemicals = [_plan_row(i) for i in range(TEST_CHEMICAL_COUNT)]
    plan = _plan_inputs(chemicals=chemicals, execute_eligible=True)
    r = fa.evaluate_full_acceptance(
        hydration_status=_hydration_fully_complete(),
        plan_inputs=plan,
        dictionary_status=_dict_offline(),
    )
    b = next(s for s in r.stages if s.name == "plan")
    assert b.ready is True
    assert b.block_reasons == ()
    assert b.evidence["chemicals"] == TEST_CHEMICAL_COUNT
    assert b.evidence["sections"] == TEST_SECTION_COUNT


# ---------------------------------------------------------------------------
# H7 — preview→FULL dry-run classifies 1997 UNCHANGED / 18571 NEW / 0 CONFLICT
# ---------------------------------------------------------------------------


def test_H7_preview_to_full_dry_run_matches_expected_baseline():
    """Store already carries PREVIEW_CHEMS chemicals; plan is FULL.
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
    )
    c = next(s for s in r.stages if s.name == "materialize")
    assert c.ready is True
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


def test_H8_identity_regeneration_blocks():
    """Simulate a DB row that matches natural key and content hash but
    carries no `id` column (would force writer to mint a new UUID for
    an UNCHANGED chemical). The classifier surfaces this via
    db_chemical_id=None; the harness raises IDENTITY_REGENERATION."""
    # Chemical row with matching hash but no `id` — identity regen bait.
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
    )
    assert r.verdict == fa.VERDICT_BLOCKED
    assert fa.BLOCK_IDENTITY_REGENERATION in r.overall_block_reasons


# ---------------------------------------------------------------------------
# H9 — CONFLICT at chemical level → BLOCKED / CHEMICAL_CONFLICT
# ---------------------------------------------------------------------------


def test_H9_materialize_conflict_blocks():
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
    )
    assert r.verdict == fa.VERDICT_BLOCKED
    assert fa.BLOCK_CHEMICAL_CONFLICT in r.overall_block_reasons


# ---------------------------------------------------------------------------
# H10 — full plan + no FULL snapshot → READY_FOR_FULL_MATERIALIZE
# ---------------------------------------------------------------------------


def test_H10_no_full_snapshot_yields_ready_for_full_materialize():
    """Source complete, plan ready, dry-run passes; publish_store has
    no COMPLETED / FULL_OFFICIAL / NOT_PUBLISHED candidate. Harness
    stops at READY_FOR_FULL_MATERIALIZE."""
    mat_store = _preview_materialize_store()
    # Publish store carries only a PUBLISHED_SEO_PREVIEW snapshot.
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
    )
    assert r.verdict == fa.VERDICT_READY_FOR_FULL_MATERIALIZE
    d = next(s for s in r.stages if s.name == "materialized_full")
    assert d.ready is False
    assert d.evidence.get("note") == "NOT_YET_MATERIALIZED"


# ---------------------------------------------------------------------------
# H11 — complete FULL candidate → publish stage delegates PASS
# ---------------------------------------------------------------------------


def test_H11_complete_full_candidate_publish_stage_ready():
    """Publish store has a fully-materialized FULL_OFFICIAL / NOT_PUBLISHED
    snapshot with expected/discovered/items/sections all lined up.
    Publish stage should surface cutover.is_full_ready ready=True."""
    pub_store = _valid_full_publish_store()
    # Cross-check is_full_ready in isolation first.
    ready = cutover.is_full_ready("snap-FULL", store=pub_store)
    assert ready.ready is True

    # Now via harness. No plan / no materialize store — we're only
    # verifying stage E on top of stage D. Stage C's "no plan" note
    # keeps that stage not-ready; the verdict lands on BLOCKED for
    # the intermediate branch. We only assert D + E readiness.
    r = fa.evaluate_full_acceptance(
        hydration_status=_hydration_fully_complete(),
        publish_store=pub_store,
        dictionary_status=_dict_v2(),
    )
    d = next(s for s in r.stages if s.name == "materialized_full")
    e = next(s for s in r.stages if s.name == "publish")
    assert d.ready is True
    assert d.evidence["snapshot_id"] == "snap-FULL"
    assert e.ready is True
    assert e.block_reasons == ()


# ---------------------------------------------------------------------------
# H12 — search-dict 503 → SEARCH_RUNTIME_READY=false
# ---------------------------------------------------------------------------


def test_H12_search_dict_offline_blocks_public_cutover():
    """Dictionary probe returns UNVERIFIED_NETWORK. Stage F not-ready
    prevents the READY_FOR_FULL_CUTOVER transition even if everything
    else is green."""
    pub_store = _valid_full_publish_store()
    mat_store = _preview_materialize_store()
    chemicals = [_plan_row(i) for i in range(TEST_CHEMICAL_COUNT)]
    plan = _plan_inputs(chemicals=chemicals, execute_eligible=True)
    r = fa.evaluate_full_acceptance(
        hydration_status=_hydration_fully_complete(),
        plan_inputs=plan,
        materialize_store=mat_store,
        publish_store=pub_store,
        dictionary_status=_dict_offline(),
        public_mode=PUBLIC_MODE_SEO_PREVIEW,
    )
    f = next(s for s in r.stages if s.name == "search_runtime")
    assert f.ready is False
    assert r.verdict != fa.VERDICT_READY_FOR_FULL_CUTOVER


# ---------------------------------------------------------------------------
# H13 — search-dict V2 → SEARCH_RUNTIME_READY=true
# ---------------------------------------------------------------------------


def test_H13_search_dict_v2_makes_stage_ready():
    r_stage = fa.evaluate_search_runtime_stage(_dict_v2())
    assert r_stage.ready is True
    assert r_stage.evidence["binding"] == "V2_MATCH"
    assert r_stage.evidence["chem_term_msds_matched"] is True

    # Also verify a partial-V2 (msds not matched) still refuses.
    partial = dict(_dict_v2())
    partial["chem_term_msds_matched"] = False
    assert fa.evaluate_search_runtime_stage(partial).ready is False


# ---------------------------------------------------------------------------
# H14 — everything green + public_mode=seo_preview → READY_FOR_FULL_CUTOVER
# ---------------------------------------------------------------------------


def test_H14_all_green_returns_ready_for_full_cutover():
    """Source complete + plan complete + preview→FULL dry-run at baseline
    + FULL candidate materialized + preflight passes + search dict V2
    + public_mode=seo_preview. Harness returns READY_FOR_FULL_CUTOVER."""
    # Materialize store: 2 preview chemicals (existing rows), rest NEW.
    mat_store = _preview_materialize_store()
    # Publish store: FULL_OFFICIAL / NOT_PUBLISHED candidate ready to promote.
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
    )

    assert r.verdict == fa.VERDICT_READY_FOR_FULL_CUTOVER, r.to_dict()
    assert r.overall_block_reasons == ()
    # Every stage ready.
    for s in r.stages:
        assert s.ready is True, f"stage {s.name} not ready: {s.to_dict()}"


# ---------------------------------------------------------------------------
# Auxiliary — running-snapshot hold (WO §19)
# ---------------------------------------------------------------------------


def test_H14b_running_snapshot_hold_forces_blocked():
    """Even with everything else green, a nonzero running snapshot count
    lands on VERDICT_BLOCKED with BLOCK_RUNNING_SNAPSHOT_HOLD."""
    mat_store = _preview_materialize_store()
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
        running_snapshots=1,
    )
    assert r.verdict == fa.VERDICT_BLOCKED
    assert fa.BLOCK_RUNNING_SNAPSHOT_HOLD in r.overall_block_reasons
