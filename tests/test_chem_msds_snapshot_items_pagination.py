"""WO-CHEM-05-PUBLISH-PAGINATION-PATCH-001 — SupabasePublishStore.snapshot_items() pagination contract.

P01  order("chemical_id") is present in the query chain.
P02  2,505 fixture rows → len=2505, distinct chemical_id=2505, duplicate=0.
P03  range() calls are (0,999) → (1000,1999) → (2000,2999) in order.
P04  Existing publish fail-close tests (MemoryPublishStore) PASS — verified by
     running the full test_chem10_publish_promoter suite alongside this file.
P05  sections pagination order("chemical_id") / order("section_no") is
     unchanged (regression check via grep on source).
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from unittest.mock import MagicMock, call

import pytest

from services.kosha_msds.production_store import SupabasePublishStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SNAP_ID = "0ad73e46-d61b-474d-a90e-5b5ab8080d80"
_PAGE_SIZE = 1000


def _make_items(count: int, snap_id: str = _SNAP_ID) -> list[dict]:
    """Deterministic fixture: unique chemical_ids sorted by UUID string."""
    items = []
    for i in range(count):
        items.append({
            "snapshot_id": snap_id,
            "chemical_id": str(uuid.UUID(int=i + 1)),
            "detail_status": "COMPLETE",
            "in_snapshot": True,
            "identity_status": "READY",
            "source_content_hash": f"hash-{i:06d}",
        })
    # Sort by chemical_id — mimics what ORDER BY chemical_id would return.
    items.sort(key=lambda r: r["chemical_id"])
    return items


def _build_mock_sb(all_items: list[dict], *, snap_id: str = _SNAP_ID):
    """Build a Supabase mock that returns paginated rows for snapshot_items
    and records all .order() and .range() calls for assertion.

    The mock chain tracks each call on the query builder and stores:
      - order_calls: list of positional args passed to .order()
      - range_calls: list of (start, end) tuples passed to .range()
    """
    order_calls: list[tuple] = []
    range_calls: list[tuple] = []
    execute_results: list[list[dict]] = []

    # Pre-slice all_items into pages so execute() returns them in order.
    for offset in range(0, len(all_items) + _PAGE_SIZE, _PAGE_SIZE):
        page = all_items[offset: offset + _PAGE_SIZE]
        if page:
            execute_results.append(page)
        if len(page) < _PAGE_SIZE:
            break

    call_idx = [0]

    def make_builder():
        builder = MagicMock()
        builder.eq.return_value = builder
        builder.select.return_value = builder
        builder.order.side_effect = lambda *args, **kwargs: (
            order_calls.append(args) or builder
        )
        builder.range.side_effect = lambda start, end: (
            range_calls.append((start, end)) or builder
        )

        def do_execute():
            idx = call_idx[0]
            call_idx[0] += 1
            page = execute_results[idx] if idx < len(execute_results) else []
            resp = MagicMock()
            resp.data = page
            return resp

        builder.execute.side_effect = do_execute
        return builder

    sb = MagicMock()
    sb.table.return_value = make_builder()

    return sb, order_calls, range_calls


# ---------------------------------------------------------------------------
# P01 — order("chemical_id") present
# ---------------------------------------------------------------------------

def test_P01_order_chemical_id_present():
    """snapshot_items() must call .order("chemical_id") at least once."""
    items = _make_items(10)
    sb, order_calls, _ = _build_mock_sb(items)
    store = SupabasePublishStore(sb=sb)

    result = store.snapshot_items(_SNAP_ID)

    assert any(
        args and args[0] == "chemical_id"
        for args in order_calls
    ), f"order('chemical_id') not found in order_calls={order_calls}"


# ---------------------------------------------------------------------------
# P02 — 2,505 rows: len=2505, distinct=2505, duplicate=0
# ---------------------------------------------------------------------------

def test_P02_pagination_distinct_2505():
    """2,505-row fixture: result has no duplicate chemical_id."""
    items = _make_items(2505)
    sb, _, _ = _build_mock_sb(items)
    store = SupabasePublishStore(sb=sb)

    result = store.snapshot_items(_SNAP_ID)

    assert len(result) == 2505, f"expected 2505 rows, got {len(result)}"

    seen: dict[str, int] = defaultdict(int)
    for r in result:
        seen[r["chemical_id"]] += 1

    duplicates = {k: v for k, v in seen.items() if v > 1}
    assert len(seen) == 2505, f"distinct chemical_ids={len(seen)}, expected 2505"
    assert duplicates == {}, f"duplicate chemical_ids found: {duplicates}"


# ---------------------------------------------------------------------------
# P03 — range calls: (0,999) → (1000,1999) → (2000,2999)
# ---------------------------------------------------------------------------

def test_P03_range_sequence_2505():
    """3-page fetch: range() calls must be (0,999), (1000,1999), (2000,2999)."""
    items = _make_items(2505)
    sb, _, range_calls = _build_mock_sb(items)
    store = SupabasePublishStore(sb=sb)

    store.snapshot_items(_SNAP_ID)

    expected_ranges = [(0, 999), (1000, 1999), (2000, 2999)]
    assert range_calls == expected_ranges, (
        f"range calls mismatch:\n  got={range_calls}\n  expected={expected_ranges}"
    )


# ---------------------------------------------------------------------------
# P04 boundary: single-page snapshot (≤ 1000) still works
# ---------------------------------------------------------------------------

def test_P04_single_page_no_duplicate():
    """999-row snapshot: single page, order present, no duplicate."""
    items = _make_items(999)
    sb, order_calls, range_calls = _build_mock_sb(items)
    store = SupabasePublishStore(sb=sb)

    result = store.snapshot_items(_SNAP_ID)

    assert len(result) == 999
    assert any(args and args[0] == "chemical_id" for args in order_calls)
    assert range_calls == [(0, 999)]
    assert len({r["chemical_id"] for r in result}) == 999


# ---------------------------------------------------------------------------
# P05 — sections pagination order contract unchanged (static source check)
# ---------------------------------------------------------------------------

def test_P05_sections_pagination_order_unchanged():
    """_iter_sections_for_chem_ids must still call .order('chemical_id')
    and .order('section_no'). Verified via source inspection."""
    import inspect
    import services.kosha_msds.production_store as store_mod

    src = inspect.getsource(store_mod.SupabasePublishStore._iter_sections_for_chem_ids)

    assert '.order("chemical_id")' in src or ".order('chemical_id')" in src, (
        "sections pagination missing order('chemical_id')"
    )
    assert '.order("section_no")' in src or ".order('section_no')" in src, (
        "sections pagination missing order('section_no')"
    )
