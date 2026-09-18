"""WO-CHEM-10 publish promoter tests (fixture only).

MemoryPublishStore. No live Supabase. No live DB. §32 items 1..20
individually covered, plus 4 extras (§32 also lists 21..24 as
"recommended").
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from routers import kosha_public_msds as router_mod
from router_registry.public import ROUTERS as PUBLIC_ROUTERS
from services.kosha_msds import publish as p
from tools.chem10 import publish_snapshot as cli


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

FULL_CHEM = p.FULL_OFFICIAL_CHEMICAL_COUNT   # 20,568
FULL_SEC = p.FULL_OFFICIAL_SECTION_COUNT     # 329,088


def _snapshot(
    id: str = "snap-A",
    *,
    status: str = "COMPLETED",
    enumeration_mode: str = "FULL_OFFICIAL",
    publish_state: str = "NOT_PUBLISHED",
    expected_count: int = FULL_CHEM,
    discovered_count: int = FULL_CHEM,
    completed_at: str = "2026-09-19T10:00:00Z",
    started_at: str = "2026-09-19T09:00:00Z",
    metrics_json: dict | None = None,
) -> dict:
    return {
        "id": id,
        "source_id": "KOSHA_MSDS",
        "run_type": "FULL_SYNC",
        "status": status,
        "enumeration_mode": enumeration_mode,
        "publish_state": publish_state,
        "source_contract_version": "KOSHA_MSDS_OPENAPI_V1_2",
        "expected_count": expected_count,
        "discovered_count": discovered_count,
        "started_at": started_at,
        "completed_at": completed_at,
        "metrics_json": dict(metrics_json or {
            "adapter_version": "CHEM05_V1",
            "materialize_plan_sha256": "plan-sem-sha",
            "responses_sha256": "resp-sha",
        }),
    }


def _full_membership(snap_id: str, *, count: int = FULL_CHEM,
                     detail_status: str = "COMPLETE") -> list[dict]:
    return [
        {
            "snapshot_id": snap_id,
            "chemical_id": f"uu-{i:06d}",
            "detail_status": detail_status,
            "in_snapshot": True,
        }
        for i in range(count)
    ]


def _full_sections(*, chem_count: int = FULL_CHEM) -> list[dict]:
    """One section row per (chemical_id, section_no) in 1..16.
    Returns chem_count × 16 rows.
    """
    rows = []
    for i in range(chem_count):
        cid = f"uu-{i:06d}"
        for n in range(1, 17):
            rows.append({
                "chemical_id": cid,
                "section_no": n,
                "section_hash": f"sec-{cid}-{n}",
                "result_code": "00",
            })
    return rows


def _full_store(snap_id: str = "snap-A", **snap_kw) -> p.MemoryPublishStore:
    snap = _snapshot(snap_id, **snap_kw)
    return p.MemoryPublishStore(
        snapshots=[snap],
        snapshot_items=_full_membership(snap_id),
        sections=_full_sections(),
    )


# ---------------------------------------------------------------------------
# §32 items 1..20
# ---------------------------------------------------------------------------


def test_01_snapshot_missing_blocks():
    store = p.MemoryPublishStore()
    r = p.preflight_publish("does-not-exist", store=store)
    assert r.snapshot_exists is False
    assert p.BLOCK_SNAPSHOT_NOT_FOUND in r.block_reasons
    assert r.eligible is False


def test_02_running_snapshot_blocks():
    store = _full_store(status="RUNNING")
    r = p.preflight_publish("snap-A", store=store)
    assert p.BLOCK_SNAPSHOT_NOT_COMPLETED in r.block_reasons


def test_03_failed_snapshot_blocks():
    store = _full_store(status="FAILED")
    r = p.preflight_publish("snap-A", store=store)
    assert p.BLOCK_SNAPSHOT_NOT_COMPLETED in r.block_reasons


def test_04_non_full_official_blocks():
    store = _full_store(enumeration_mode="PROBE")
    r = p.preflight_publish("snap-A", store=store)
    assert p.BLOCK_NOT_FULL_OFFICIAL in r.block_reasons


def test_05_already_published_blocks():
    store = _full_store(publish_state="PUBLISHED_FULL")
    r = p.preflight_publish("snap-A", store=store)
    assert p.BLOCK_ALREADY_PUBLISHED in r.block_reasons
    assert r.eligible is False


def test_06_expected_count_mismatch_blocks():
    store = _full_store(expected_count=100)
    r = p.preflight_publish("snap-A", store=store)
    assert p.BLOCK_EXPECTED_COUNT_MISMATCH in r.block_reasons


def test_07_discovered_count_mismatch_blocks():
    store = _full_store(discovered_count=FULL_CHEM - 1)
    r = p.preflight_publish("snap-A", store=store)
    assert p.BLOCK_DISCOVERED_COUNT_MISMATCH in r.block_reasons


def test_08_snapshot_items_count_mismatch_blocks():
    snap = _snapshot("snap-A")
    store = p.MemoryPublishStore(
        snapshots=[snap],
        snapshot_items=_full_membership("snap-A", count=FULL_CHEM - 3),
        sections=_full_sections(),
    )
    r = p.preflight_publish("snap-A", store=store)
    assert p.BLOCK_SNAPSHOT_ITEM_COUNT_MISMATCH in r.block_reasons


def test_09_incomplete_membership_blocks():
    snap = _snapshot("snap-A")
    members = _full_membership("snap-A")
    members[0]["detail_status"] = "INCOMPLETE"
    store = p.MemoryPublishStore(
        snapshots=[snap],
        snapshot_items=members,
        sections=_full_sections(),
    )
    r = p.preflight_publish("snap-A", store=store)
    assert p.BLOCK_INCOMPLETE_MEMBERSHIP in r.block_reasons
    assert r.incomplete_memberships == 1


def test_10_section_count_mismatch_blocks():
    snap = _snapshot("snap-A")
    # Missing one section pair for a single chemical.
    sections = _full_sections()
    sections.pop()  # drop last (chemical_id, section_no) pair
    store = p.MemoryPublishStore(
        snapshots=[snap],
        snapshot_items=_full_membership("snap-A"),
        sections=sections,
    )
    r = p.preflight_publish("snap-A", store=store)
    assert p.BLOCK_SECTION_COUNT_MISMATCH in r.block_reasons
    assert r.section_count == FULL_SEC - 1


def test_11_duplicate_membership_blocks():
    snap = _snapshot("snap-A")
    members = _full_membership("snap-A")
    members.append(dict(members[0]))  # duplicate the first membership row
    store = p.MemoryPublishStore(
        snapshots=[snap],
        snapshot_items=members,
        sections=_full_sections(),
    )
    r = p.preflight_publish("snap-A", store=store)
    assert p.BLOCK_DUPLICATE_MEMBERSHIP in r.block_reasons
    assert r.duplicate_memberships == 1


def test_12_duplicate_section_blocks():
    snap = _snapshot("snap-A")
    sections = _full_sections()
    sections.append(dict(sections[0]))  # duplicate one (chemical_id, section_no)
    store = p.MemoryPublishStore(
        snapshots=[snap],
        snapshot_items=_full_membership("snap-A"),
        sections=sections,
    )
    r = p.preflight_publish("snap-A", store=store)
    assert p.BLOCK_DUPLICATE_SECTION in r.block_reasons


def test_13_materialize_binding_mismatch_blocks():
    store = _full_store(metrics_json={
        "adapter_version": "CHEM05_V1",
        "materialize_plan_sha256": "actual-sha",
        "responses_sha256": "resp-sha",
    })
    r = p.preflight_publish(
        "snap-A", store=store,
        expected_materialize_binding={
            "adapter_version": "CHEM05_V1",
            "materialize_plan_sha256": "different-sha",  # mismatch
            "responses_sha256": "resp-sha",
        },
    )
    assert p.BLOCK_MATERIALIZE_BINDING_MISMATCH in r.block_reasons
    assert r.materialize_binding_mismatch is True


def test_14_valid_full_snapshot_is_eligible():
    store = _full_store()
    r = p.preflight_publish("snap-A", store=store)
    assert r.block_reasons == ()
    assert r.eligible is True
    assert r.snapshot_item_count == FULL_CHEM
    assert r.section_count == FULL_SEC


def test_15_owner_approval_missing_blocks_promotion():
    store = _full_store()
    r = p.preflight_publish("snap-A", store=store)
    with pytest.raises(p.PublicationForbidden) as ei:
        p.assert_can_execute_publish(report=r, owner_approved=False)
    assert p.BLOCK_OWNER_AUTHORIZATION_MISSING in str(ei.value)


def test_16_wo_scope_forbids_publication_even_with_owner_approval():
    """Under WO-CHEM-10 the third gate is always False. Owner approval
    alone is insufficient."""
    store = _full_store()
    r = p.preflight_publish("snap-A", store=store)
    with pytest.raises(p.PublicationForbidden) as ei:
        p.assert_can_execute_publish(report=r, owner_approved=True)
    assert p.BLOCK_WO_SCOPE_FORBIDS_PUBLICATION in str(ei.value)
    assert p.PRODUCTION_PUBLISH_ALLOWED is False


def test_17_fixture_promotion_flips_publish_state():
    """Fixture-side promotion via wo_scope_allows_publish=True (which no
    real caller will supply under WO-CHEM-10; the future execution WO
    flips the module-level constant)."""
    store = _full_store()
    result = p.promote_to_published_full(
        "snap-A", store=store, owner_approved=True,
        wo_scope_allows_publish=True,
    )
    assert result.publish_state == "PUBLISHED_FULL"
    # And re-reading the store shows the same.
    assert store.get_snapshot("snap-A")["publish_state"] == "PUBLISHED_FULL"


def test_18_promotion_failure_preserves_old_published_state():
    """Simulate a store-side failure during promote_to_published_full.
    The prior state must not be corrupted; any partial write is undone.
    """
    # Setup: an already-published old snapshot AND a candidate new one.
    old = _snapshot("snap-OLD",
                    publish_state="PUBLISHED_FULL",
                    completed_at="2026-09-18T10:00:00Z",
                    started_at="2026-09-18T09:00:00Z")
    new = _snapshot("snap-A")
    store = p.MemoryPublishStore(
        snapshots=[old, new],
        snapshot_items=_full_membership("snap-A"),
        sections=_full_sections(),
    )

    class RaisingStore(p.MemoryPublishStore):
        def promote_to_published_full(self, snapshot_id):
            raise RuntimeError("simulated write failure")
    raiser = RaisingStore(
        snapshots=[dict(old), dict(new)],
        snapshot_items=_full_membership("snap-A"),
        sections=_full_sections(),
    )
    with pytest.raises(RuntimeError):
        p.promote_to_published_full(
            "snap-A", store=raiser, owner_approved=True,
            wo_scope_allows_publish=True,
        )
    # New snapshot's state must remain NOT_PUBLISHED.
    new_after = raiser.get_snapshot("snap-A")
    assert new_after["publish_state"] == "NOT_PUBLISHED"
    # Old published snapshot preserved.
    old_after = raiser.get_snapshot("snap-OLD")
    assert old_after["publish_state"] == "PUBLISHED_FULL"


def test_19_historical_snapshots_not_deleted():
    """Successful promotion of a new snapshot MUST NOT delete the old
    PUBLISHED_FULL snapshot (WO §19)."""
    old = _snapshot("snap-OLD",
                    publish_state="PUBLISHED_FULL",
                    completed_at="2026-09-18T10:00:00Z",
                    started_at="2026-09-18T09:00:00Z")
    new = _snapshot("snap-A")
    store = p.MemoryPublishStore(
        snapshots=[old, new],
        snapshot_items=_full_membership("snap-A"),
        sections=_full_sections(),
    )
    _ = p.promote_to_published_full(
        "snap-A", store=store, owner_approved=True,
        wo_scope_allows_publish=True,
    )
    # Old is still present, still PUBLISHED_FULL.
    assert store.get_snapshot("snap-OLD") is not None
    assert store.get_snapshot("snap-OLD")["publish_state"] == "PUBLISHED_FULL"
    # New is now also PUBLISHED_FULL.
    assert store.get_snapshot("snap-A")["publish_state"] == "PUBLISHED_FULL"


def test_20_dry_run_causes_zero_mutation():
    """dry_run reads state; the store is byte-identical before and after."""
    store = _full_store()
    snapshots_before = [dict(s) for s in store._snapshots]
    items_before = [dict(i) for i in store._items]
    sections_before = [dict(s) for s in store._sections]
    _ = p.dry_run("snap-A", store=store, owner_approved=False)
    assert [dict(s) for s in store._snapshots] == snapshots_before
    assert [dict(i) for i in store._items] == items_before
    assert [dict(s) for s in store._sections] == sections_before


# ---------------------------------------------------------------------------
# §32 items 21..24 (recommended)
# ---------------------------------------------------------------------------


def test_21_exactly_one_view_current_snapshot_after_promotion():
    """kosha_msds_current picks the newest PUBLISHED_FULL by completed_at.
    Simulate the view via latest_published_snapshot() and confirm the
    newly promoted snapshot wins on the same day."""
    old = _snapshot("snap-OLD",
                    publish_state="PUBLISHED_FULL",
                    completed_at="2026-09-18T10:00:00Z",
                    started_at="2026-09-18T09:00:00Z")
    new = _snapshot("snap-A")  # completed_at = 2026-09-19T10:00:00Z
    store = p.MemoryPublishStore(
        snapshots=[old, new],
        snapshot_items=_full_membership("snap-A"),
        sections=_full_sections(),
    )
    _ = p.promote_to_published_full(
        "snap-A", store=store, owner_approved=True,
        wo_scope_allows_publish=True,
    )
    current = store.latest_published_snapshot()
    assert current is not None
    assert current["id"] == "snap-A"


def test_22_cli_execute_blocked_even_with_owner_approved():
    """--execute --owner-approved returns rc=2 and never opens a DB path."""
    rc = cli.main([
        "--execute",
        "--owner-approved",
        "--snapshot-id", "does-not-exist",  # store is empty in the CLI
    ])
    assert rc == 2


def test_23_router_registry_untouched():
    """router_registry/public.py must not have been modified to register
    routers.kosha_public_msds under this WO."""
    modules = [entry.get("module") for entry in PUBLIC_ROUTERS]
    assert "routers.kosha_public_msds" not in modules


def test_24_search_adapter_untouched():
    """CHEM-09 search adapter file exists but is not imported by publish.py."""
    src = Path(p.__file__).read_text(encoding="utf-8")
    assert "search_adapter" not in src
    # And publish.py must not import any router module.
    for banned in ("from routers", "import routers"):
        assert banned not in src, f"publish.py leaks into HTTP layer: {banned!r}"


# ---------------------------------------------------------------------------
# Extra: cross-domain isolation
# ---------------------------------------------------------------------------


def test_25_no_kosha_safety_materials_dependency():
    for module_file in (p.__file__, cli.__file__):
        src = Path(module_file).read_text(encoding="utf-8")
        assert "kosha_safety_materials" not in src, (
            f"{module_file} must not import services.kosha_safety_materials"
        )
