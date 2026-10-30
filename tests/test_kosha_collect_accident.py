"""
WO-ACCIDENT-PROD-HOTFIX-005-R1 — unit tests for _collect_accident_cases.
T-01..T-10: field mapping, FAIL_CLOSED, duplicate detection, data protection, dry_run.
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
    sb = MagicMock()
    existing_rows = existing_rows or []
    # .table().select().execute() → existing rows
    sb.table.return_value.select.return_value.execute.return_value = MagicMock(data=existing_rows)
    # .table().upsert().execute() → success
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
