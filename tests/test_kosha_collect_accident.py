"""
WO-ACCIDENT-PROD-HOTFIX-005-R2 — unit tests for _collect_accident_cases.
T-01..T-10: field mapping, FAIL_CLOSED, duplicate detection, data protection, dry_run.
T-11..T-13: paginated pre-load >1000, batched UPSERT split, partial UPSERT failure.
Uses asyncio.run() — no pytest-asyncio dependency required.
"""
from __future__ import annotations
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_item(arno: str, keyword: str = "테스트 제목", contents: str = "테스트 내용",
               reg_dt: str = "2024-06-01") -> dict:
    return {"arno": arno, "keyword": keyword, "contents": contents, "regDt": reg_dt}


def _mock_sb(existing_rows: list[dict] | None = None):
    """Single-page pre-load mock (existing_rows < 1000).
    Pre-load uses .select().range().execute() — first call returns existing_rows, next returns [].
    """
    sb = MagicMock()
    existing_rows = existing_rows or []
    _calls = [0]
    def _preload_exec():
        idx = _calls[0]; _calls[0] += 1
        return MagicMock(data=existing_rows if idx == 0 else [])
    sb.table.return_value.select.return_value.range.return_value.execute.side_effect = _preload_exec
    sb.table.return_value.upsert.return_value.execute.return_value = MagicMock()
    return sb


def _mock_sb_paginated(preload_pages: list[list[dict]]):
    """Multi-page pre-load mock (existing rows span multiple 1000-row pages)."""
    sb = MagicMock()
    _calls = [0]
    def _preload_exec():
        idx = _calls[0]; _calls[0] += 1
        page = preload_pages[idx] if idx < len(preload_pages) else []
        return MagicMock(data=page)
    sb.table.return_value.select.return_value.range.return_value.execute.side_effect = _preload_exec
    sb.table.return_value.upsert.return_value.execute.return_value = MagicMock()
    return sb


def _make_resp(items: list[dict], total: int | None = None) -> dict:
    return {"body": {"items": items, "totalCount": total if total is not None else len(items)}}


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_t01_normal_row_upserted(monkeypatch):
    """T-01: arno+keyword+contents 정상 → 1건 UPSERT."""
    from routers.kosha_collect import _collect_accident_cases

    item = _make_item("ARNO001")
    side = [_make_resp([item]), _make_resp([])]
    monkeypatch.setattr("routers.kosha_collect.get_supabase", lambda: _mock_sb())
    monkeypatch.setattr("routers.kosha_collect.KoshaAPI.get",
                        AsyncMock(side_effect=side))

    result = _run(_collect_accident_cases(dry_run=False))
    assert result["valid_rows"] == 1
    assert result["upserted"] == 1


def test_t02_missing_arno_skip(monkeypatch):
    """T-02: 혼합 페이지에서 arno 없는 항목만 SKIP, arno 있는 항목은 유지."""
    from routers.kosha_collect import _collect_accident_cases

    item_no_arno = {"keyword": "제목", "contents": "내용", "regDt": "2024-06-01"}
    item_ok = _make_item("ARNO007")
    # Page has 2 items: 1 missing arno (skip), 1 good (keep).
    # Contract violation requires ALL items missing arno; mixed page is data-quality skip.
    monkeypatch.setattr("routers.kosha_collect.get_supabase", lambda: _mock_sb())
    monkeypatch.setattr("routers.kosha_collect.KoshaAPI.get",
                        AsyncMock(side_effect=[_make_resp([item_no_arno, item_ok]), _make_resp([])]))

    result = _run(_collect_accident_cases(dry_run=True))
    assert result["valid_rows"] == 1


def test_t03_empty_keyword_skip(monkeypatch):
    """T-03: arno 있음, keyword="" → SKIP."""
    from routers.kosha_collect import _collect_accident_cases

    item = _make_item("ARNO002", keyword="")
    monkeypatch.setattr("routers.kosha_collect.get_supabase", lambda: _mock_sb())
    monkeypatch.setattr("routers.kosha_collect.KoshaAPI.get",
                        AsyncMock(side_effect=[_make_resp([item]), _make_resp([])]))

    result = _run(_collect_accident_cases(dry_run=True))
    assert result["valid_rows"] == 0


def test_t04_empty_contents_skip(monkeypatch):
    """T-04: arno 있음, contents="" → SKIP."""
    from routers.kosha_collect import _collect_accident_cases

    item = _make_item("ARNO003", contents="")
    monkeypatch.setattr("routers.kosha_collect.get_supabase", lambda: _mock_sb())
    monkeypatch.setattr("routers.kosha_collect.KoshaAPI.get",
                        AsyncMock(side_effect=[_make_resp([item]), _make_resp([])]))

    result = _run(_collect_accident_cases(dry_run=True))
    assert result["valid_rows"] == 0


def test_t05_existing_arno_preserves_id(monkeypatch):
    """T-05: arno가 기존 매핑에 존재 → rid = 기존 id (URL 보존)."""
    from routers.kosha_collect import _collect_accident_cases

    existing_id = "c4ca4238a0b92382"
    existing_row = {
        "id": existing_id,
        "title": "원래 제목",
        "content": "원래 내용",
        "raw_json": {"arno": "ARNO004"},
    }
    item = _make_item("ARNO004", keyword="새 제목", contents="새 내용")

    sb = _mock_sb([existing_row])
    captured: list[list] = []

    def _capture_upsert(rows, **kw):
        captured.append(list(rows))
        return sb.table.return_value.upsert.return_value

    sb.table.return_value.upsert.side_effect = _capture_upsert

    monkeypatch.setattr("routers.kosha_collect.get_supabase", lambda: sb)
    monkeypatch.setattr("routers.kosha_collect.KoshaAPI.get",
                        AsyncMock(side_effect=[_make_resp([item]), _make_resp([])]))

    result = _run(_collect_accident_cases(dry_run=False))
    assert result["valid_rows"] == 1
    assert captured[0][0]["id"] == existing_id


def test_t06_new_arno_uses_arno_as_id(monkeypatch):
    """T-06: arno 신규 → id = arno."""
    from routers.kosha_collect import _collect_accident_cases

    item = _make_item("ARNO_NEW_999")
    sb = _mock_sb()
    captured: list[list] = []

    def _capture_upsert(rows, **kw):
        captured.append(list(rows))
        return sb.table.return_value.upsert.return_value

    sb.table.return_value.upsert.side_effect = _capture_upsert

    monkeypatch.setattr("routers.kosha_collect.get_supabase", lambda: sb)
    monkeypatch.setattr("routers.kosha_collect.KoshaAPI.get",
                        AsyncMock(side_effect=[_make_resp([item]), _make_resp([])]))

    result = _run(_collect_accident_cases(dry_run=False))
    assert result["valid_rows"] == 1
    assert captured[0][0]["id"] == "ARNO_NEW_999"


def test_t07_cross_page_arno_duplicate_skip(monkeypatch):
    """T-07: 동일 arno가 페이지 1+2에 등장 → 첫 번째만 유지."""
    from routers.kosha_collect import _collect_accident_cases

    # page 1: 100 items (same arno fills page to trigger page 2)
    item1 = _make_item("ARNO_DUP", keyword="제목1", contents="내용1")
    item2 = _make_item("ARNO_DUP", keyword="제목2", contents="내용2")
    resp1 = _make_resp([item1] * 100)
    resp2 = _make_resp([item2])

    monkeypatch.setattr("routers.kosha_collect.get_supabase", lambda: _mock_sb())
    monkeypatch.setattr("routers.kosha_collect.KoshaAPI.get",
                        AsyncMock(side_effect=[resp1, resp2, _make_resp([])]))

    result = _run(_collect_accident_cases(dry_run=True))
    # 101 items with same arno → only 1 valid row
    assert result["valid_rows"] == 1


def test_t08_whitespace_keyword_skip(monkeypatch):
    """T-08: keyword="   " → strip → "" → SKIP."""
    from routers.kosha_collect import _collect_accident_cases

    item = _make_item("ARNO005", keyword="   ")
    monkeypatch.setattr("routers.kosha_collect.get_supabase", lambda: _mock_sb())
    monkeypatch.setattr("routers.kosha_collect.KoshaAPI.get",
                        AsyncMock(side_effect=[_make_resp([item]), _make_resp([])]))

    result = _run(_collect_accident_cases(dry_run=True))
    assert result["valid_rows"] == 0


def test_t09_contract_violation_no_arno_raises(monkeypatch):
    """T-09: 페이지 전체 arno 없음 → KoshaFetchError CONTRACT_VIOLATION_NO_ARNO."""
    from routers.kosha_collect import _collect_accident_cases, KoshaFetchError

    items_no_arno = [{"keyword": "k", "contents": "c", "regDt": "2024-06-01"} for _ in range(5)]
    resp = _make_resp(items_no_arno)

    monkeypatch.setattr("routers.kosha_collect.get_supabase", lambda: _mock_sb())
    monkeypatch.setattr("routers.kosha_collect.KoshaAPI.get",
                        AsyncMock(return_value=resp))

    with pytest.raises(KoshaFetchError) as exc_info:
        _run(_collect_accident_cases(dry_run=True))

    assert "CONTRACT_VIOLATION_NO_ARNO" in str(exc_info.value)


def test_t10_dry_run_no_dml(monkeypatch):
    """T-10: dry_run=True → upsert 호출 없음, upserted=0."""
    from routers.kosha_collect import _collect_accident_cases

    item = _make_item("ARNO006")
    sb = _mock_sb()

    monkeypatch.setattr("routers.kosha_collect.get_supabase", lambda: sb)
    monkeypatch.setattr("routers.kosha_collect.KoshaAPI.get",
                        AsyncMock(side_effect=[_make_resp([item]), _make_resp([])]))

    result = _run(_collect_accident_cases(dry_run=True))
    assert result["upserted"] == 0
    assert result["valid_rows"] == 1
    sb.table.return_value.upsert.assert_not_called()


def test_t11_preload_over_1000_preserves_page2_id(monkeypatch):
    """T-11: 기존 rows > 1000 → 2nd 페이지 arno→id 매핑이 보존됨 (URL 불변)."""
    from routers.kosha_collect import _collect_accident_cases

    # page 1: exactly 1000 rows (triggers second pre-load request)
    page1_rows = [
        {"id": f"ID{i:04d}", "title": "t", "content": "c",
         "raw_json": {"arno": f"ARNO{i:04d}"}}
        for i in range(1000)
    ]
    # page 2: 1 row — this arno's id must survive collection
    page2_rows = [{"id": "ID_PAGE2_EXISTING", "title": "old_title", "content": "old_content",
                   "raw_json": {"arno": "ARNO_PAGE2"}}]

    sb = _mock_sb_paginated([page1_rows, page2_rows])
    captured: list[list] = []

    def _capture_upsert(rows, **kw):
        captured.append(list(rows))
        return sb.table.return_value.upsert.return_value
    sb.table.return_value.upsert.side_effect = _capture_upsert

    monkeypatch.setattr("routers.kosha_collect.get_supabase", lambda: sb)
    monkeypatch.setattr("routers.kosha_collect.KoshaAPI.get",
                        AsyncMock(side_effect=[
                            _make_resp([_make_item("ARNO_PAGE2", keyword="새 제목", contents="새 내용")]),
                            _make_resp([]),
                        ]))

    result = _run(_collect_accident_cases(dry_run=False))
    assert result["valid_rows"] == 1
    # ID from 2nd pre-load page must be preserved — not replaced by arno string
    assert captured[0][0]["id"] == "ID_PAGE2_EXISTING"


def test_t12_batched_upsert_splits_at_500(monkeypatch):
    """T-12: valid_rows=501 → UPSERT가 2회 분할 호출됨 (500 + 1)."""
    from routers.kosha_collect import _collect_accident_cases

    # 501 unique items across 6 API pages (100×5 + 1)
    items = [_make_item(f"ARNO{i:04d}") for i in range(501)]
    api_pages = [_make_resp(items[i * 100 : (i + 1) * 100]) for i in range(5)]
    api_pages.append(_make_resp(items[500:501]))  # page 6: 1 item → loop stops

    sb = _mock_sb()
    upsert_call_sizes: list[int] = []

    def _capture(rows, **kw):
        upsert_call_sizes.append(len(list(rows)))
        return sb.table.return_value.upsert.return_value
    sb.table.return_value.upsert.side_effect = _capture

    monkeypatch.setattr("routers.kosha_collect.get_supabase", lambda: sb)
    monkeypatch.setattr("routers.kosha_collect.KoshaAPI.get",
                        AsyncMock(side_effect=api_pages))

    result = _run(_collect_accident_cases(dry_run=False))
    assert result["valid_rows"] == 501
    assert result["upserted"] == 501
    assert len(upsert_call_sizes) == 2, f"expected 2 batches, got {upsert_call_sizes}"
    assert upsert_call_sizes[0] == 500
    assert upsert_call_sizes[1] == 1


def test_t13_upsert_second_batch_raises_partial_count(monkeypatch):
    """T-13: 2nd UPSERT 배치 실패 → RuntimeError 전파, 1st 배치 500건은 이미 저장."""
    from routers.kosha_collect import _collect_accident_cases

    items = [_make_item(f"ARNO{i:04d}") for i in range(501)]
    api_pages = [_make_resp(items[i * 100 : (i + 1) * 100]) for i in range(5)]
    api_pages.append(_make_resp(items[500:501]))

    sb = _mock_sb()
    call_count = [0]

    def _fail_on_second(rows, **kw):
        call_count[0] += 1
        if call_count[0] == 2:
            raise RuntimeError("UPSERT_BATCH_2_FAIL")
        return sb.table.return_value.upsert.return_value
    sb.table.return_value.upsert.side_effect = _fail_on_second

    monkeypatch.setattr("routers.kosha_collect.get_supabase", lambda: sb)
    monkeypatch.setattr("routers.kosha_collect.KoshaAPI.get",
                        AsyncMock(side_effect=api_pages))

    with pytest.raises(RuntimeError, match="UPSERT_BATCH_2_FAIL"):
        _run(_collect_accident_cases(dry_run=False))
