"""TAI-WO-P0-CONTENT-WP03-VERIFY-003 — EXT-165 화학사고 공개 읽기 계약 테스트.

─── Memory store 계약 (AC01-AC16) ───────────────────────────────────────────
AC01  목록 200 + items/total/page/page_size 필드
AC02  q 검색 → 필터링
AC03  page/page_size → 올바른 슬라이스
AC04  현행 스냅샷 없음(items=None) → 503  [fixed: 이전 200 기대값 수정]
AC05  DB 불가 → 503
AC06  datano 단건 조회 → 200 + 모든 공개 필드
AC07  존재하지 않는 datano → 404
AC08  공백만인 datano → 422
AC09  모든 공개 필드 존재
AC10  금지 필드 부재 (raw, snapshot_id)
AC11  검색 대소문자 무관
AC12  XSS 문자 포함 데이터 → JSON 유효 + content-type application/json
AC13  page=0 → 422
AC14  page_size 초과 → 422
AC15  q 길이 초과 → 422
AC16  스냅샷 있음 + 검색 결과 없음(items=[]) → 200 빈 목록 (503 아님)

─── Supabase store Mock 계약 (AC17-AC25) ────────────────────────────────────
AC17  collect_scope IS NULL 필터 적용 확인
AC18  is_current=true 필터 적용 확인
AC19  스냅샷 없음(Supabase) → 503
AC20  목록 검색: cause + place 포함 6개 필드 or_() 확인
AC21  escape_ilike: 역슬래시·퍼센트·언더스코어·쉼표 이스케이프
AC22  Supabase 단건 조회: snapshot_id + datano 필터
AC23  Supabase 목록: range(offset, offset+page_size-1) 페이지네이션
AC24  특수문자 검색어 → Q_INVALID 422
AC25  Supabase 쿼리 실패 → UNAVAILABLE 503

No real DB. MemoryChemicalAccidentStore 및 MagicMock 사용.
"""
from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.public_chemical_accident as chem_mod
from services.ext165_chemical_accident.read import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    MAX_Q_LEN,
    ChemicalAccidentQueryError,
    MemoryChemicalAccidentStore,
    SupabaseChemicalAccidentStore,
    escape_ilike,
    sanitize_q,
)

# ── Fixtures ─────────────────────────────────────────────────────────────────

_ITEM_A = {
    "datano": "1001",
    "accident_date": "2023-05-12",
    "accident_type": "폭발",
    "area": "경기도",
    "place": "화학공장",
    "chemical": "암모니아",
    "cause": "밸브 오작동",
    "summary": "암모니아 누출로 인한 폭발 사고",
}
_ITEM_B = {
    "datano": "1002",
    "accident_date": "2022-08-03",
    "accident_type": "누출",
    "area": "울산",
    "place": "정유공장",
    "chemical": "황산",
    "cause": "배관 부식",
    "summary": "황산 배관 누출 사고",
}
_ITEM_C = {
    "datano": "1003",
    "accident_date": "2021-11-01",
    "accident_type": "화재",
    "area": "전라도",
    "place": "창고",
    "chemical": "유기용제",
    "cause": "정전기",
    "summary": "유기용제 화재 발생",
}

_ITEMS_10 = [
    {
        "datano": str(2000 + i),
        "accident_date": "2020-01-01",
        "accident_type": "기타",
        "area": "서울",
        "place": "공장",
        "chemical": "화학물질",
        "cause": "원인",
        "summary": "요약",
    }
    for i in range(10)
]

_SNAP_ID = "snap-uuid-ext165-001"


def _make_app(items=None) -> FastAPI:
    store = MemoryChemicalAccidentStore(items)
    chem_mod.configure_chemical_accident_public(store)
    app = FastAPI()
    app.include_router(chem_mod.router)
    return app


def _make_app_with_store(store) -> FastAPI:
    chem_mod.configure_chemical_accident_public(store)
    app = FastAPI()
    app.include_router(chem_mod.router)
    return app


@pytest.fixture(autouse=True)
def _reset():
    yield
    chem_mod.reset_chemical_accident_public()


# ── Supabase client mock helpers ──────────────────────────────────────────────

def _mock_sb(snapshot_rows: list, item_rows: list, count: int | None = None) -> MagicMock:
    """EXT-165 읽기 경로용 Supabase 클라이언트 Mock."""
    sb = MagicMock()
    # snapshot query chain
    snap_chain = MagicMock()
    snap_result = MagicMock()
    snap_result.data = snapshot_rows
    snap_chain.execute.return_value = snap_result
    snap_chain.is_.return_value = snap_chain
    snap_chain.eq.return_value = snap_chain
    snap_chain.limit.return_value = snap_chain
    snap_chain.select.return_value = snap_chain
    # items query chain
    item_chain = MagicMock()
    item_result = MagicMock()
    item_result.data = item_rows
    item_result.count = count if count is not None else len(item_rows)
    item_chain.execute.return_value = item_result
    for m in ("select", "eq", "or_", "order", "range", "limit"):
        getattr(item_chain, m).return_value = item_chain

    def _table(name):
        from services.ext165_chemical_accident.contract import TABLE_SNAPSHOTS, TABLE_ITEMS
        return snap_chain if name == TABLE_SNAPSHOTS else item_chain

    sb.table.side_effect = _table
    return sb, snap_chain, item_chain


# ════════════════════════════════════════════════════════════════════════════
# AC01-AC16: Memory store 계약
# ════════════════════════════════════════════════════════════════════════════

def test_ac01_list_200_with_required_fields():
    client = TestClient(_make_app([_ITEM_A, _ITEM_B]))
    r = client.get("/public/accidents/chemical")
    assert r.status_code == 200
    body = r.json()
    for key in ("items", "total", "page", "page_size"):
        assert key in body


def test_ac02_q_filters_results():
    client = TestClient(_make_app([_ITEM_A, _ITEM_B, _ITEM_C]))
    r = client.get("/public/accidents/chemical?q=황산")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["datano"] == "1002"


def test_ac03_pagination_slice():
    client = TestClient(_make_app(_ITEMS_10))
    r = client.get("/public/accidents/chemical?page=2&page_size=3")
    assert r.status_code == 200
    body = r.json()
    assert body["page"] == 2
    assert body["page_size"] == 3
    assert len(body["items"]) == 3
    assert body["total"] == 10


def test_ac04_no_snapshot_returns_503():
    """items=None → MemoryStore raises NO_CURRENT_SNAPSHOT → 503."""
    client = TestClient(_make_app(None))
    r = client.get("/public/accidents/chemical")
    assert r.status_code == 503


def test_ac05_db_unavailable_returns_503():
    class _FailStore:
        def list_ready(self, q, page, page_size):
            raise ChemicalAccidentQueryError("UNAVAILABLE")
        def get_ready(self, datano):
            raise ChemicalAccidentQueryError("UNAVAILABLE")

    client = TestClient(_make_app_with_store(_FailStore()))
    r = client.get("/public/accidents/chemical")
    assert r.status_code == 503


def test_ac06_detail_200():
    client = TestClient(_make_app([_ITEM_A]))
    r = client.get("/public/accidents/chemical/1001")
    assert r.status_code == 200
    assert r.json()["datano"] == "1001"


def test_ac07_detail_not_found_404():
    client = TestClient(_make_app([_ITEM_A]))
    r = client.get("/public/accidents/chemical/9999")
    assert r.status_code == 404


def test_ac08_whitespace_datano_422():
    client = TestClient(_make_app([_ITEM_A]))
    r = client.get("/public/accidents/chemical/%20")
    assert r.status_code == 422


def test_ac09_all_public_fields_present():
    client = TestClient(_make_app([_ITEM_A]))
    r = client.get("/public/accidents/chemical/1001")
    assert r.status_code == 200
    body = r.json()
    expected = {"datano", "accident_date", "accident_type", "area", "place", "chemical", "cause", "summary"}
    assert expected.issubset(set(body.keys()))


def test_ac10_forbidden_fields_absent():
    client = TestClient(_make_app([_ITEM_A]))
    r = client.get("/public/accidents/chemical/1001")
    assert r.status_code == 200
    body = r.json()
    for f in ("raw", "snapshot_id"):
        assert f not in body, f"forbidden field present: {f}"


def test_ac11_search_case_insensitive():
    item = {**_ITEM_A, "chemical": "Ammonia"}
    client = TestClient(_make_app([item]))
    r = client.get("/public/accidents/chemical?q=ammonia")
    assert r.status_code == 200
    assert r.json()["total"] == 1


def test_ac12_xss_data_json_safe():
    xss_item = {**_ITEM_A, "summary": "<script>alert(1)</script>"}
    client = TestClient(_make_app([xss_item]))
    r = client.get("/public/accidents/chemical/1001")
    assert r.status_code == 200
    body = r.json()
    assert "script" in body["summary"]
    assert r.headers["content-type"].startswith("application/json")


def test_ac13_page_zero_422():
    client = TestClient(_make_app([]))
    assert client.get("/public/accidents/chemical?page=0").status_code == 422


def test_ac14_page_size_too_large_422():
    client = TestClient(_make_app([]))
    assert client.get(f"/public/accidents/chemical?page_size={MAX_PAGE_SIZE + 1}").status_code == 422


def test_ac15_q_too_long_422():
    client = TestClient(_make_app([]))
    assert client.get(f"/public/accidents/chemical?q={'a' * (MAX_Q_LEN + 1)}").status_code == 422


def test_ac16_empty_snapshot_200_empty_list():
    """items=[] → 스냅샷 있음, 결과 없음 → 200 빈 목록 (503 아님)."""
    client = TestClient(_make_app([]))
    r = client.get("/public/accidents/chemical")
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 0


# ════════════════════════════════════════════════════════════════════════════
# AC17-AC25: Supabase store Mock 계약
# ════════════════════════════════════════════════════════════════════════════

_RAW_ROW = {
    "datano": "1001",
    "raw": {
        "cscDe": "2023-05-12", "cscTy": "폭발", "area": "경기도",
        "place": "화학공장", "chem": "암모니아", "cause": "밸브 오작동",
        "summary": "암모니아 누출",
    },
}


def test_ac17_collect_scope_is_null_applied():
    """SupabaseChemicalAccidentStore: collect_scope IS NULL 조건 적용 확인."""
    sb, snap_chain, _ = _mock_sb([{"id": _SNAP_ID}], [_RAW_ROW])
    store = SupabaseChemicalAccidentStore(sb)
    store._get_snapshot_id()
    # is_("collect_scope", "null") 가 호출됐는지 확인
    snap_chain.is_.assert_called_once_with("collect_scope", "null")


def test_ac18_is_current_true_applied():
    """SupabaseChemicalAccidentStore: is_current=True 조건 적용 확인."""
    sb, snap_chain, _ = _mock_sb([{"id": _SNAP_ID}], [_RAW_ROW])
    store = SupabaseChemicalAccidentStore(sb)
    store._get_snapshot_id()
    # eq("is_current", True) 가 호출됐는지 확인
    eq_calls = [c for c in snap_chain.eq.call_args_list if c == call("is_current", True)]
    assert eq_calls, "is_current=True 필터가 적용되지 않음"


def test_ac19_no_snapshot_supabase_503():
    """Supabase에서 스냅샷 없을 때 목록 조회 → 503."""
    sb, _, _ = _mock_sb([], [])
    store = SupabaseChemicalAccidentStore(sb)
    chem_mod.configure_chemical_accident_public(store)
    app = FastAPI()
    app.include_router(chem_mod.router)
    client = TestClient(app)
    r = client.get("/public/accidents/chemical")
    assert r.status_code == 503


def test_ac20_search_fields_include_cause_and_place():
    """검색 or_() 절에 cause와 place 포함 확인."""
    sb, _, item_chain = _mock_sb([{"id": _SNAP_ID}], [], count=0)
    store = SupabaseChemicalAccidentStore(sb)
    store.list_ready("암모니아", 1, 20)
    or_calls = item_chain.or_.call_args_list
    assert or_calls, "or_() 가 호출되지 않음"
    clause = or_calls[0][0][0]
    assert "cause" in clause, f"cause 없음: {clause}"
    assert "place" in clause, f"place 없음: {clause}"
    assert "summary" in clause
    assert "chem" in clause
    assert "area" in clause
    assert "cscTy" in clause


def test_ac21_escape_ilike_special_chars():
    """escape_ilike: \\, %, _, , 이스케이프."""
    assert escape_ilike("test%value") == r"test\%value"
    assert escape_ilike("a_b") == r"a\_b"
    assert escape_ilike("a\\b") == r"a\\b"
    # 쉼표 → 공백 (or_() 절 주입 방지)
    assert escape_ilike("a,b") == "a b"
    # 조합
    result = escape_ilike("100%_safe,val")
    assert "%" not in result.replace("\\%", "")
    assert "," not in result


def test_ac22_supabase_detail_filters_snapshot_and_datano():
    """단건 조회: snapshot_id + datano 필터 적용 확인."""
    sb, _, item_chain = _mock_sb([{"id": _SNAP_ID}], [_RAW_ROW])
    store = SupabaseChemicalAccidentStore(sb)
    store.get_ready("1001")
    eq_calls = [c[0] for c in item_chain.eq.call_args_list]
    assert ("snapshot_id", _SNAP_ID) in eq_calls, "snapshot_id 필터 없음"
    assert ("datano", "1001") in eq_calls, "datano 필터 없음"


def test_ac23_supabase_list_pagination_range():
    """목록 페이지네이션: range(offset, offset+page_size-1) 호출 확인."""
    sb, _, item_chain = _mock_sb([{"id": _SNAP_ID}], [], count=0)
    store = SupabaseChemicalAccidentStore(sb)
    store.list_ready(None, page=3, page_size=10)
    # page=3, page_size=10 → offset=20, end=29
    item_chain.range.assert_called_once_with(20, 29)


def test_ac24_q_invalid_special_chars_422():
    """특수문자 검색어 → Q_INVALID → 422."""
    client = TestClient(_make_app([_ITEM_A]))
    r = client.get("/public/accidents/chemical?q=hack%3B%3B")
    assert r.status_code == 422


def test_ac25_supabase_query_failure_503():
    """Supabase 쿼리 예외 → UNAVAILABLE → 503."""
    sb, _, item_chain = _mock_sb([{"id": _SNAP_ID}], [])
    item_chain.execute.side_effect = RuntimeError("DB connection lost")
    store = SupabaseChemicalAccidentStore(sb)
    chem_mod.configure_chemical_accident_public(store)
    app = FastAPI()
    app.include_router(chem_mod.router)
    client = TestClient(app)
    r = client.get("/public/accidents/chemical")
    assert r.status_code == 503
