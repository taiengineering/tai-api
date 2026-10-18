"""WO-WWW-PERF-003-P0A — Published-First, Targeted-Hydration tests.

Validates that SupabaseMsdsReadStore.list_current (SEO_PREVIEW) now:
  1. Uses kosha_msds_seo_preview_current (lightweight) for pagination
  2. Batch-fetches sections IN (2, 15) for the page's chemicals only
  3. Batch-fetches last_date from kosha_msds_chemicals
  4. Computes display fields in Python (not via heavy seo_preview_display view)

Contract tests (no live DB):
  T1  list_current SEO_PREVIEW dispatches to list_current_fast
  T2  list_current_fast issues 3 queries (current_view + sections + chemicals)
  T3  Section 2 item codes → hazard_class / signal_word / pictograms
  T4  Section 15 item codes → reg_saolaw / reg_dangerous
  T5  last_date comes from kosha_msds_chemicals, not sections
  T6  Missing sections → None display fields (no KeyError)
  T7  Pagination total correct, page slice correct
  T8  FULL scope list_current unchanged (still uses display view)
  T9  search_current SEO_PREVIEW unchanged (still uses display view — no parity proven)
  T10 MemoryMsdsReadStore.list_current SEO_PREVIEW hydrates from seeded sections
  T11 _extract_item respects btrim / NULLIF semantics (blank → None)
  T12 display_view constant preserved for non-list callers (search / get_by_chem_id)
"""
from __future__ import annotations

from typing import Optional
from unittest.mock import MagicMock, call, patch

import pytest

from services.kosha_msds import read
from services.kosha_msds.contract import (
    PUBLICATION_SCOPE_FULL,
    PUBLICATION_SCOPE_SEO_PREVIEW,
)
from services.kosha_msds.read import (
    CHEMICALS_TABLE,
    CURRENT_VIEW,
    PREVIEW_VIEW,
    SEO_PREVIEW_CURRENT_VIEW,
    SECTIONS_TABLE,
    _HYDRATION_SECTION_NOS,
    _S2_HAZARD_CLASS,
    _S2_PICTOGRAMS,
    _S2_SIGNAL_WORD,
    _S15_REG_DANGEROUS,
    _S15_REG_SAOLAW,
    _extract_item,
    _hydrate_from_sections,
    MemoryMsdsReadStore,
    SupabaseMsdsReadStore,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _chem_row(chem_id: str, uid: Optional[str] = None) -> dict:
    uid = uid or f"uid-{chem_id}"
    return {
        "id": uid,
        "content_id": f"CHEM:{uid}",
        "source_id": "KOSHA_MSDS",
        "source_key": chem_id,
        "chem_id": chem_id,
        "identity_status": "READY",
        "chemical_name_ko": f"화학물질_{chem_id}",
        "chemical_name_en": f"Chemical_{chem_id}",
        "cas_no": None,
        "ke_no": None,
        "en_no": None,
        "un_no": None,
        "source_content_hash": f"sha-{chem_id}",
        "source_dataset_url": "https://www.data.go.kr/data/15157612/openapi.do",
        "snapshot_id": "snap-001",
    }


def _sec2_items(
    *,
    hazard_class: str = "인화성 액체 : 구분3",
    signal_word: str = "경고",
    pictograms: str = "GHS02.gif|GHS07.gif",
) -> list:
    return [
        {"msdsItemCode": _S2_HAZARD_CLASS, "msdsItemNameKor": "유해성·위험성 분류",
         "itemDetail": hazard_class, "lev": "1", "ordrIdx": "1022", "upMsdsItemCode": "B"},
        {"msdsItemCode": _S2_PICTOGRAMS, "msdsItemNameKor": "그림문자",
         "itemDetail": pictograms, "lev": "2", "ordrIdx": "1026", "upMsdsItemCode": "B04"},
        {"msdsItemCode": _S2_SIGNAL_WORD, "msdsItemNameKor": "신호어",
         "itemDetail": signal_word, "lev": "2", "ordrIdx": "1028", "upMsdsItemCode": "B04"},
    ]


def _sec15_items(
    *,
    reg_saolaw: str = "공정안전보고서(PSM) 제출 대상물질",
    reg_dangerous: str = "제4류 인화성액체의 제2석유류 비수용성액체",
) -> list:
    return [
        {"msdsItemCode": _S15_REG_SAOLAW, "msdsItemNameKor": "산업안전보건법에 의한 규제",
         "itemDetail": reg_saolaw, "lev": "1", "ordrIdx": "1322", "upMsdsItemCode": "O"},
        {"msdsItemCode": _S15_REG_DANGEROUS, "msdsItemNameKor": "위험물안전관리법에 의한 규제",
         "itemDetail": reg_dangerous, "lev": "1", "ordrIdx": "1326", "upMsdsItemCode": "O"},
    ]


def _section_row(chemical_id: str, section_no: int, payload: list) -> dict:
    return {
        "chemical_id": chemical_id,
        "section_no": section_no,
        "payload_json": payload,
    }


def _make_sb_mock(page_rows: list, section_rows: list, chem_rows: list) -> MagicMock:
    """Build a Supabase mock that returns page_rows, section_rows, chem_rows in order."""
    sb = MagicMock()

    page_result = MagicMock()
    page_result.data = page_rows
    page_result.count = len(page_rows)

    sec_result = MagicMock()
    sec_result.data = section_rows

    chem_result = MagicMock()
    chem_result.data = chem_rows

    # table().select().order()... chain → returns a new chainable mock per call
    call_seq = [page_result, sec_result, chem_result]
    idx = [0]

    def _execute():
        r = call_seq[idx[0]]
        idx[0] += 1
        return r

    chain = MagicMock()
    chain.select.return_value = chain
    chain.order.return_value = chain
    chain.range.return_value = chain
    chain.in_.return_value = chain
    chain.eq.return_value = chain
    chain.ilike.return_value = chain
    chain.limit.return_value = chain
    chain.execute.side_effect = _execute

    sb.table.return_value = chain
    return sb


# ---------------------------------------------------------------------------
# T1 — list_current SEO_PREVIEW dispatches to list_current_fast
# ---------------------------------------------------------------------------

def test_T1_list_current_seo_preview_dispatches_fast(monkeypatch):
    store = SupabaseMsdsReadStore.__new__(SupabaseMsdsReadStore)
    fast_called = []

    def _fake_fast(*, limit, offset):
        fast_called.append((limit, offset))
        return [], 0

    store.list_current_fast = _fake_fast
    store.list_current(limit=20, offset=0, scope=PUBLICATION_SCOPE_SEO_PREVIEW)
    assert fast_called == [(20, 0)], "SEO_PREVIEW must route to list_current_fast"


# ---------------------------------------------------------------------------
# T2 — list_current_fast issues exactly 3 queries
# ---------------------------------------------------------------------------

def test_T2_list_current_fast_issues_three_queries():
    row = _chem_row("001008")
    sec_rows = [
        _section_row(row["id"], 2, _sec2_items()),
        _section_row(row["id"], 15, _sec15_items()),
    ]
    chem_extra = [{"id": row["id"], "last_date": "2025-10-01"}]

    sb = _make_sb_mock([row], sec_rows, chem_extra)
    store = SupabaseMsdsReadStore.__new__(SupabaseMsdsReadStore)
    store.sb = sb

    result_rows, total = store.list_current_fast(limit=20, offset=0)
    assert total == 1
    assert sb.table.call_count == 3, f"Expected 3 table() calls, got {sb.table.call_count}"

    calls = [c.args[0] for c in sb.table.call_args_list]
    assert calls[0] == SEO_PREVIEW_CURRENT_VIEW, f"1st query must be lightweight view, got {calls[0]}"
    assert calls[1] == SECTIONS_TABLE, f"2nd query must be sections table, got {calls[1]}"
    assert calls[2] == CHEMICALS_TABLE, f"3rd query must be chemicals table, got {calls[2]}"


# ---------------------------------------------------------------------------
# T3 — Section 2 item codes → hazard_class / signal_word / pictograms
# ---------------------------------------------------------------------------

def test_T3_section2_field_extraction():
    items = _sec2_items(
        hazard_class="인화성 액체 : 구분3",
        signal_word="경고",
        pictograms="GHS02.gif|GHS07.gif",
    )
    assert _extract_item(items, _S2_HAZARD_CLASS) == "인화성 액체 : 구분3"
    assert _extract_item(items, _S2_SIGNAL_WORD) == "경고"
    assert _extract_item(items, _S2_PICTOGRAMS) == "GHS02.gif|GHS07.gif"


def test_T3_hydrate_from_section2_returns_correct_fields():
    sec2 = _section_row("uid-001", 2, _sec2_items())
    result = _hydrate_from_sections([sec2], last_date="2025-10-01")
    assert result["hazard_class"] == "인화성 액체 : 구분3"
    assert result["signal_word"] == "경고"
    assert result["pictograms"] == "GHS02.gif|GHS07.gif"
    assert result["last_date"] == "2025-10-01"


# ---------------------------------------------------------------------------
# T4 — Section 15 item codes → reg_saolaw / reg_dangerous
# ---------------------------------------------------------------------------

def test_T4_section15_field_extraction():
    items = _sec15_items(
        reg_saolaw="공정안전보고서(PSM) 제출 대상물질",
        reg_dangerous="제4류 인화성액체의 제2석유류 비수용성액체",
    )
    assert _extract_item(items, _S15_REG_SAOLAW) == "공정안전보고서(PSM) 제출 대상물질"
    assert _extract_item(items, _S15_REG_DANGEROUS) == "제4류 인화성액체의 제2석유류 비수용성액체"


def test_T4_hydrate_from_section15_returns_reg_fields():
    sec15 = _section_row("uid-001", 15, _sec15_items())
    result = _hydrate_from_sections([sec15], last_date=None)
    assert result["reg_saolaw"] == "공정안전보고서(PSM) 제출 대상물질"
    assert result["reg_dangerous"] == "제4류 인화성액체의 제2석유류 비수용성액체"
    assert result["last_date"] is None


# ---------------------------------------------------------------------------
# T5 — last_date from chemicals, not sections
# ---------------------------------------------------------------------------

def test_T5_last_date_from_chemicals_batch():
    row = _chem_row("001008")
    sec_rows = [_section_row(row["id"], 2, _sec2_items())]
    chem_extra = [{"id": row["id"], "last_date": "2025-10-01"}]

    sb = _make_sb_mock([row], sec_rows, chem_extra)
    store = SupabaseMsdsReadStore.__new__(SupabaseMsdsReadStore)
    store.sb = sb

    result_rows, _ = store.list_current_fast(limit=20, offset=0)
    assert result_rows[0]["last_date"] == "2025-10-01"


# ---------------------------------------------------------------------------
# T6 — Missing sections → None display fields (no KeyError)
# ---------------------------------------------------------------------------

def test_T6_missing_sections_yields_none_display_fields():
    result = _hydrate_from_sections([], last_date=None)
    assert result["hazard_class"] is None
    assert result["signal_word"] is None
    assert result["pictograms"] is None
    assert result["reg_saolaw"] is None
    assert result["reg_dangerous"] is None
    assert result["last_date"] is None


def test_T6_list_current_fast_empty_sections_no_error():
    row = _chem_row("001008")
    sb = _make_sb_mock([row], [], [{"id": row["id"], "last_date": None}])
    store = SupabaseMsdsReadStore.__new__(SupabaseMsdsReadStore)
    store.sb = sb
    result_rows, _ = store.list_current_fast(limit=20, offset=0)
    assert result_rows[0]["hazard_class"] is None


# ---------------------------------------------------------------------------
# T7 — Pagination: total reflects view count, page slice correct
# ---------------------------------------------------------------------------

def test_T7_pagination_total_from_count():
    rows = [_chem_row(str(i).zfill(6)) for i in range(5)]
    sec_rows = []
    chem_extra = [{"id": r["id"], "last_date": None} for r in rows]

    sb = MagicMock()
    page_result = MagicMock()
    page_result.data = rows[:2]
    page_result.count = 5  # total > page size

    sec_result = MagicMock()
    sec_result.data = sec_rows

    chem_result = MagicMock()
    chem_result.data = chem_extra[:2]

    call_seq = [page_result, sec_result, chem_result]
    idx = [0]

    def _execute():
        r = call_seq[idx[0]]
        idx[0] += 1
        return r

    chain = MagicMock()
    chain.select.return_value = chain
    chain.order.return_value = chain
    chain.range.return_value = chain
    chain.in_.return_value = chain
    chain.eq.return_value = chain
    chain.limit.return_value = chain
    chain.execute.side_effect = _execute
    sb.table.return_value = chain

    store = SupabaseMsdsReadStore.__new__(SupabaseMsdsReadStore)
    store.sb = sb

    result_rows, total = store.list_current_fast(limit=2, offset=0)
    assert total == 5, f"total must reflect view count (5), got {total}"
    assert len(result_rows) == 2


# ---------------------------------------------------------------------------
# T8 — FULL scope uses display view unchanged
# ---------------------------------------------------------------------------

def test_T8_full_scope_list_current_unchanged():
    store = SupabaseMsdsReadStore.__new__(SupabaseMsdsReadStore)
    fast_called = []
    store.list_current_fast = lambda **_: fast_called.append(True) or ([], 0)

    result = MagicMock()
    result.data = []
    result.count = 0

    chain = MagicMock()
    chain.select.return_value = chain
    chain.order.return_value = chain
    chain.range.return_value = chain
    chain.execute.return_value = result

    sb = MagicMock()
    sb.table.return_value = chain
    store.sb = sb

    store.list_current(limit=20, offset=0, scope=PUBLICATION_SCOPE_FULL)
    assert not fast_called, "FULL scope must NOT use list_current_fast"
    table_arg = sb.table.call_args.args[0]
    assert table_arg == CURRENT_VIEW, f"FULL scope must query {CURRENT_VIEW}, got {table_arg}"


# ---------------------------------------------------------------------------
# T9 — search_current SEO_PREVIEW still queries display view (legacy regression)
# ---------------------------------------------------------------------------

def test_T9_search_current_seo_preview_still_uses_display_view():
    result = MagicMock()
    result.data = []
    result.count = 0

    chain = MagicMock()
    for attr in ("select", "eq", "ilike", "order", "range", "in_"):
        getattr(chain, attr).return_value = chain
    chain.execute.return_value = result

    sb = MagicMock()
    sb.table.return_value = chain

    store = SupabaseMsdsReadStore.__new__(SupabaseMsdsReadStore)
    store.sb = sb

    store.search_current(name_ko="벤젠", limit=10, offset=0, scope=PUBLICATION_SCOPE_SEO_PREVIEW)
    table_arg = sb.table.call_args.args[0]
    assert table_arg == PREVIEW_VIEW, (
        f"search_current SEO_PREVIEW must still query {PREVIEW_VIEW} (not yet proven parity), "
        f"got {table_arg}"
    )


# ---------------------------------------------------------------------------
# T10 — MemoryMsdsReadStore.list_current SEO_PREVIEW hydrates from sections
# ---------------------------------------------------------------------------

def test_T10_memory_store_list_current_preview_hydrates():
    row = {**_chem_row("001008"), "id": "uid-001008"}
    preview_rows = [row]
    sections = [
        _section_row("uid-001008", 2, _sec2_items()),
        _section_row("uid-001008", 15, _sec15_items()),
    ]
    chemicals = [{"id": "uid-001008", "last_date": "2025-10-01"}]

    store = MemoryMsdsReadStore(
        preview_rows=preview_rows,
        sections=sections,
        chemicals=chemicals,
    )
    result_rows, total = store.list_current(limit=20, offset=0, scope=PUBLICATION_SCOPE_SEO_PREVIEW)
    assert total == 1
    item = result_rows[0]
    assert item["hazard_class"] == "인화성 액체 : 구분3"
    assert item["signal_word"] == "경고"
    assert item["pictograms"] == "GHS02.gif|GHS07.gif"
    assert item["reg_saolaw"] == "공정안전보고서(PSM) 제출 대상물질"
    assert item["reg_dangerous"] == "제4류 인화성액체의 제2석유류 비수용성액체"
    assert item["last_date"] == "2025-10-01"


def test_T10_memory_store_list_current_full_unchanged():
    row = _chem_row("001008")
    store = MemoryMsdsReadStore(current_rows=[row])
    result_rows, total = store.list_current(limit=20, offset=0, scope=PUBLICATION_SCOPE_FULL)
    assert total == 1
    assert result_rows[0]["chem_id"] == "001008"


# ---------------------------------------------------------------------------
# T11 — _extract_item btrim / NULLIF semantics
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("detail,expected", [
    ("경고", "경고"),
    ("  경고  ", "경고"),      # btrim
    ("", None),                # NULLIF("", "")
    ("   ", None),             # btrim then NULLIF
    (None, None),              # itemDetail absent
])
def test_T11_extract_item_btrim_nullif(detail, expected):
    items = [{"msdsItemCode": "B0404", "itemDetail": detail}]
    assert _extract_item(items, "B0404") == expected


def test_T11_extract_item_missing_code_returns_none():
    items = [{"msdsItemCode": "B0404", "itemDetail": "경고"}]
    assert _extract_item(items, "XXXX") is None


# ---------------------------------------------------------------------------
# T12 — PREVIEW_VIEW constant preserved for non-list callers
# ---------------------------------------------------------------------------

def test_T12_preview_view_constant_preserved():
    assert read.PREVIEW_VIEW == "kosha_msds_seo_preview_display", (
        "PREVIEW_VIEW must remain seo_preview_display — search + get_by_chem_id still use it"
    )
    assert read.SEO_PREVIEW_CURRENT_VIEW == "kosha_msds_seo_preview_current"
    assert read._HYDRATION_SECTION_NOS == (2, 15)
    assert read._S2_HAZARD_CLASS == "B02"
    assert read._S2_SIGNAL_WORD == "B0404"
    assert read._S2_PICTOGRAMS == "B0402"
    assert read._S15_REG_SAOLAW == "O02"
    assert read._S15_REG_DANGEROUS == "O06"
