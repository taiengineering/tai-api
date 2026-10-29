"""
tests/test_document_forms_articles.py
WO-DOC260-SHARED-ARTICLE-READ-019-R1

get_document_form_articles() 단위 테스트 (R1 보정: 운영 DB 스키마 정합).
No live DB; all Supabase calls are mocked.

실제 field_rule_mapping 컬럼: doc_id / field_key / article_id / review_status

Test matrix:
  T01 — 28건 field_rule_mapping → 1개 조문 중복 제거 + 실제 컬럼명 검증
  T02 — 화학물질관리법 제24조 article_no=24 정상 반환
  T03 — PENDING-only 매핑이 필터 제외 시 UNCONFIRMED_MAPPING gap 보고
  T04 — 고시 제6조 자동 추론 없음 (매핑 없으면 반환 안 됨)
  T05 — PENDING 매핑 is_confirmed=False
  T06 — APPROVED 매핑 is_confirmed=True
  T07 — include_pending=False → PENDING 제외 → 빈 배열
  T08 — include_pending=True → PENDING 포함
  T09 — 존재하지 않는 서식 → HTTPException 404
  T10 — DELETED + is_deleted_in_version 제외
  T11 — field_rule_mapping 0건 → 빈 배열 반환
  T12 — include_pending=True 인증 없이 요청 → 401 (라우터 계층 검증)
  T13 — DB 조회 오류는 빈 결과로 은폐되지 않고 예외 전파
  T14 — APPROVED + PENDING 혼합 → is_confirmed=False (보수적 처리)
"""
from __future__ import annotations

import sys
import os
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import HTTPException
from services.document_forms_service import get_document_form_articles

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FORM_UUID = "aaaaaaaa-0001-0001-0001-000000000001"
_ARTICLE_UUID_24 = "bbbbbbbb-0002-0002-0002-000000000002"   # 화학물질관리법 제24조
_ARTICLE_UUID_6  = "cccccccc-0003-0003-0003-000000000003"   # 환경부고시 제6조
_LAW_UUID_CHEM   = "dddddddd-0004-0004-0004-000000000004"

_FORM_ROW = {
    "id": _FORM_UUID,
    "doc_id": "DOC-CHEM-001",
    "doc_name": "유해화학물질 취급시설 설치검사 신청서",
}

_ART_ROW_24 = {
    "id": _ARTICLE_UUID_24,
    "law_id": _LAW_UUID_CHEM,
    "article_no": 24,
    "article_title": "설치검사",
    "article_text": "제24조(설치검사) ...",
    "article_internal_key": "art-024",
    "enforcement_date": "2021-04-01",
    "article_status_code": "ACTIVE",
    "is_deleted_in_version": False,
}

_LAW_ROW_CHEM = {
    "id": _LAW_UUID_CHEM,
    "law_name": "화학물질관리법",
    "law_number": "법률 제18827호",
    "enforcement_date": "2022-01-01",
}


def _make_frm_rows(count: int, article_id: str, review_status: str = "PENDING") -> list[dict]:
    """field_rule_mapping 행 생성 — 실제 컬럼: article_id, review_status."""
    field_keys = [
        "applicant_information",
        "inspection_target_facility_information",
        "preferred_inspection_date",
        "inspection_detail",
    ]
    rows = []
    for i in range(count):
        rows.append({
            "field_key": field_keys[i % len(field_keys)],
            "article_id": article_id,
            "review_status": review_status,
        })
    return rows


def _chain(data):
    c = MagicMock()
    c.execute.return_value = MagicMock(data=data)
    c.select.return_value = c
    c.eq.return_value = c
    c.in_.return_value = c
    c.neq.return_value = c
    c.limit.return_value = c
    return c


def _make_supabase_mock(
    form_data: list | None = None,
    frm_rows: list | None = None,
    art_data: list | None = None,
    law_data: list | None = None,
) -> MagicMock:
    """Supabase mock — table() 이름으로 라우팅. UUID fallback 없음."""
    form_data = form_data if form_data is not None else [_FORM_ROW]
    frm_rows  = frm_rows  if frm_rows  is not None else _make_frm_rows(28, _ARTICLE_UUID_24, "PENDING")
    art_data  = art_data  if art_data  is not None else [_ART_ROW_24]
    law_data  = law_data  if law_data  is not None else [_LAW_ROW_CHEM]

    def _table(name):
        if name == "document_forms":
            return _chain(form_data)
        if name == "field_rule_mapping":
            return _chain(frm_rows)
        if name == "law_article":
            return _chain(art_data)
        if name == "law_master":
            return _chain(law_data)
        return _chain([])

    sb = MagicMock()
    sb.table.side_effect = _table
    return sb


# ---------------------------------------------------------------------------
# T01 — 28건 → 1개 조문 중복 제거 + 실제 컬럼명 사용 검증
# ---------------------------------------------------------------------------
def test_t01_deduplication_and_correct_columns():
    """28건 매핑 → 1개 조문. 서비스가 article_id / review_status 컬럼 사용을 검증."""
    frm_rows = _make_frm_rows(28, _ARTICLE_UUID_24, "APPROVED")
    sb = _make_supabase_mock(frm_rows=frm_rows, art_data=[_ART_ROW_24], law_data=[_LAW_ROW_CHEM])

    # select 인수 캡처
    selected: dict[str, str] = {}
    orig_table_fn = sb.table.side_effect

    def capturing_table(name):
        chain = orig_table_fn(name)
        if name == "field_rule_mapping":
            orig_select = chain.select
            def spy_select(cols):
                selected["frm"] = cols
                return orig_select(cols)
            chain.select = spy_select
        return chain

    sb.table.side_effect = capturing_table

    with patch("services.document_forms_service.get_supabase", return_value=sb):
        result = get_document_form_articles("DOC-CHEM-001", include_pending=True)

    assert result["article_count"] == 1, "28건 → 중복 제거 후 1개 조문"
    assert len(result["articles"]) == 1

    # 실제 DB 컬럼명 검증
    frm_select = selected.get("frm", "")
    assert "article_id" in frm_select,      "article_id 컬럼 사용 필요 (not law_article_id)"
    assert "review_status" in frm_select,   "review_status 컬럼 사용 필요 (not status)"
    assert "law_article_id" not in frm_select, "잘못된 컬럼명 law_article_id 사용 금지"
    assert "form_id" not in frm_select,     "UUID form_id 컬럼 사용 금지"


# ---------------------------------------------------------------------------
# T02 — 화학물질관리법 제24조 정상 반환
# ---------------------------------------------------------------------------
def test_t02_chem_art24_returned():
    frm_rows = _make_frm_rows(4, _ARTICLE_UUID_24, "APPROVED")
    sb = _make_supabase_mock(frm_rows=frm_rows, art_data=[_ART_ROW_24], law_data=[_LAW_ROW_CHEM])
    with patch("services.document_forms_service.get_supabase", return_value=sb):
        result = get_document_form_articles("DOC-CHEM-001")

    art = result["articles"][0]
    assert art["article_no"] == 24
    assert "화학물질관리법" in art["law_name"]
    assert art["article_internal_key"] == "art-024"
    assert art["law_article_id"] == _ARTICLE_UUID_24


# ---------------------------------------------------------------------------
# T03 — PENDING-only 매핑 필터 제외 시 UNCONFIRMED_MAPPING gap 보고
# (하드코딩된 design_layout GAP 제거 확인)
# ---------------------------------------------------------------------------
def test_t03_unconfirmed_mapping_gap_when_pending_filtered():
    """include_pending=False 시 PENDING 매핑이 제외되면 UNCONFIRMED_MAPPING gap을 보고."""
    frm_rows = [
        {"field_key": "applicant_information", "article_id": _ARTICLE_UUID_24, "review_status": "PENDING"},
    ]
    sb = _make_supabase_mock(frm_rows=frm_rows, art_data=[_ART_ROW_24])
    with patch("services.document_forms_service.get_supabase", return_value=sb):
        result = get_document_form_articles("DOC-CHEM-001", include_pending=False)

    # articles가 비어 있어야 함 (PENDING 필터)
    assert result["article_count"] == 0
    # gap에 UNCONFIRMED_MAPPING 보고
    assert len(result["mapping_gaps"]) > 0
    gap_text = " ".join(result["mapping_gaps"])
    assert "UNCONFIRMED_MAPPING" in gap_text

    # 하드코딩된 design_layout GAP 미출력 검증 (관련 없는 서식에 오보고 금지)
    assert "고시 제6조" not in gap_text, "고시 제6조 자동 추론 금지"


# ---------------------------------------------------------------------------
# T04 — 고시 제6조 자동 추론 없음
# ---------------------------------------------------------------------------
def test_t04_no_auto_inference_of_gosi_art6():
    frm_rows = [
        {"field_key": "applicant_information", "article_id": _ARTICLE_UUID_24, "review_status": "APPROVED"},
    ]
    art_both = [
        _ART_ROW_24,
        {
            "id": _ARTICLE_UUID_6,
            "law_id": "eeeeeeee-0005-0005-0005-000000000005",
            "article_no": 6,
            "article_title": "사전서면검사자료",
            "article_text": "제6조...",
            "article_internal_key": "nfpc-art-006",
            "enforcement_date": "2025-10-07",
            "article_status_code": "ACTIVE",
            "is_deleted_in_version": False,
        },
    ]
    sb = _make_supabase_mock(frm_rows=frm_rows, art_data=art_both)
    with patch("services.document_forms_service.get_supabase", return_value=sb):
        result = get_document_form_articles("DOC-CHEM-001")

    article_ids = [a["law_article_id"] for a in result["articles"]]
    assert _ARTICLE_UUID_6 not in article_ids, "고시 제6조는 매핑 없으면 자동으로 반환되지 않아야 함"


# ---------------------------------------------------------------------------
# T05 — PENDING 매핑 is_confirmed=False
# ---------------------------------------------------------------------------
def test_t05_pending_is_not_confirmed():
    frm_rows = [{"field_key": "applicant_information", "article_id": _ARTICLE_UUID_24, "review_status": "PENDING"}]
    sb = _make_supabase_mock(frm_rows=frm_rows, art_data=[_ART_ROW_24])
    with patch("services.document_forms_service.get_supabase", return_value=sb):
        result = get_document_form_articles("DOC-CHEM-001", include_pending=True)

    assert result["article_count"] == 1
    assert result["articles"][0]["is_confirmed"] is False
    assert result["articles"][0]["mapping_status"] == "PENDING"


# ---------------------------------------------------------------------------
# T06 — APPROVED 매핑 is_confirmed=True
# ---------------------------------------------------------------------------
def test_t06_approved_is_confirmed():
    frm_rows = [{"field_key": "applicant_information", "article_id": _ARTICLE_UUID_24, "review_status": "APPROVED"}]
    sb = _make_supabase_mock(frm_rows=frm_rows, art_data=[_ART_ROW_24])
    with patch("services.document_forms_service.get_supabase", return_value=sb):
        result = get_document_form_articles("DOC-CHEM-001")

    assert result["articles"][0]["is_confirmed"] is True
    assert result["articles"][0]["mapping_status"] == "APPROVED"


# ---------------------------------------------------------------------------
# T07 — include_pending=False → PENDING 제외 → 빈 배열
# ---------------------------------------------------------------------------
def test_t07_exclude_pending_by_default():
    frm_rows = _make_frm_rows(4, _ARTICLE_UUID_24, "PENDING")
    sb = _make_supabase_mock(frm_rows=frm_rows)
    with patch("services.document_forms_service.get_supabase", return_value=sb):
        result = get_document_form_articles("DOC-CHEM-001", include_pending=False)

    assert result["article_count"] == 0
    assert result["articles"] == []


# ---------------------------------------------------------------------------
# T08 — include_pending=True → PENDING 포함
# ---------------------------------------------------------------------------
def test_t08_include_pending_flag():
    frm_rows = _make_frm_rows(4, _ARTICLE_UUID_24, "PENDING")
    sb = _make_supabase_mock(frm_rows=frm_rows, art_data=[_ART_ROW_24])
    with patch("services.document_forms_service.get_supabase", return_value=sb):
        result = get_document_form_articles("DOC-CHEM-001", include_pending=True)

    assert result["article_count"] == 1
    assert result["articles"][0]["is_confirmed"] is False


# ---------------------------------------------------------------------------
# T09 — 존재하지 않는 서식 → HTTPException 404
# ---------------------------------------------------------------------------
def test_t09_not_found_raises_404():
    sb = _make_supabase_mock(form_data=[])
    with patch("services.document_forms_service.get_supabase", return_value=sb):
        with pytest.raises(HTTPException) as exc_info:
            get_document_form_articles("DOC-NONEXISTENT-999")
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# T10 — DELETED article_status_code + is_deleted_in_version 제외
# ---------------------------------------------------------------------------
def test_t10_deleted_and_version_deleted_excluded():
    frm_rows = [{"field_key": "applicant_information", "article_id": _ARTICLE_UUID_24, "review_status": "APPROVED"}]
    # law_article 쿼리가 0건 반환: DELETED 또는 is_deleted_in_version=True 제외 시뮬레이션
    sb = _make_supabase_mock(frm_rows=frm_rows, art_data=[])
    with patch("services.document_forms_service.get_supabase", return_value=sb):
        result = get_document_form_articles("DOC-CHEM-001")

    assert result["article_count"] == 0

    # is_deleted_in_version 필터가 law_article 쿼리에 포함되는지 검증
    eq_calls: list[tuple] = []
    def _table_spy(name):
        chain = _chain([])
        if name == "law_article":
            def spy_eq(col, val):
                eq_calls.append((col, val))
                return chain
            chain.eq.side_effect = spy_eq
        return chain

    sb2 = MagicMock()
    form_res_chain = _chain([_FORM_ROW])
    frm_chain = _chain(frm_rows)
    def _table2(name):
        if name == "document_forms":
            return form_res_chain
        if name == "field_rule_mapping":
            return frm_chain
        if name == "law_article":
            c = _chain([])
            def spy_eq(col, val):
                eq_calls.append((col, val))
                return c
            c.eq.side_effect = spy_eq
            return c
        return _chain([])

    sb2.table.side_effect = _table2
    with patch("services.document_forms_service.get_supabase", return_value=sb2):
        get_document_form_articles("DOC-CHEM-001")

    called_cols = [col for col, _ in eq_calls]
    assert "is_deleted_in_version" in called_cols, "law_article 쿼리에 is_deleted_in_version 필터 필요"


# ---------------------------------------------------------------------------
# T11 — field_rule_mapping 0건 → 빈 배열 반환
# ---------------------------------------------------------------------------
def test_t11_no_mappings_returns_empty():
    sb = _make_supabase_mock(frm_rows=[], art_data=[])
    with patch("services.document_forms_service.get_supabase", return_value=sb):
        result = get_document_form_articles("DOC-CHEM-001", include_pending=True)

    assert result["articles"] == []
    assert result["article_count"] == 0
    assert result["doc_id"] == "DOC-CHEM-001"
    assert result["mapping_gaps"] == []


# ---------------------------------------------------------------------------
# T12 — include_pending=True 인증 없이 요청 → 401 (라우터 계층 검증)
# ---------------------------------------------------------------------------
def test_t12_pending_requires_authentication():
    """인증 없이 include_pending=true 요청 시 401 반환."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers.document_forms import router as doc_router
    from routers.auth import get_current_user_optional

    _app = FastAPI()
    _app.include_router(doc_router)
    _app.dependency_overrides[get_current_user_optional] = lambda: None  # 미인증

    client = TestClient(_app, raise_server_exceptions=False)
    resp = client.get("/document-forms/DOC-CHEM-001/articles?include_pending=true")
    assert resp.status_code == 401, f"미인증 PENDING 조회는 401이어야 함 (got {resp.status_code})"


# ---------------------------------------------------------------------------
# T13 — DB 조회 오류는 빈 결과로 은폐되지 않고 예외 전파
# ---------------------------------------------------------------------------
def test_t13_db_error_propagates_not_silenced():
    """field_rule_mapping DB 오류가 빈 articles가 아닌 예외로 전파됨을 검증."""
    def _table_with_error(name):
        if name == "document_forms":
            return _chain([_FORM_ROW])
        if name == "field_rule_mapping":
            c = MagicMock()
            c.execute.side_effect = Exception("DB connection timeout")
            c.select.return_value = c
            c.eq.return_value = c
            c.in_.return_value = c
            c.neq.return_value = c
            c.limit.return_value = c
            return c
        return _chain([])

    sb = MagicMock()
    sb.table.side_effect = _table_with_error

    with patch("services.document_forms_service.get_supabase", return_value=sb):
        with pytest.raises(Exception) as exc_info:
            get_document_form_articles("DOC-CHEM-001")

    # HTTPException(404)가 아닌 DB 오류여야 함
    if isinstance(exc_info.value, HTTPException):
        assert exc_info.value.status_code != 404, "DB 오류를 404로 오해석하면 안 됨"


# ---------------------------------------------------------------------------
# T14 — APPROVED + PENDING 혼합 매핑 → is_confirmed=False (보수적 처리)
# ---------------------------------------------------------------------------
def test_t14_mixed_status_conservative_is_not_confirmed():
    """동일 article_id에 APPROVED + PENDING 혼합 시 is_confirmed=False."""
    frm_rows = [
        {"field_key": "applicant_information", "article_id": _ARTICLE_UUID_24, "review_status": "APPROVED"},
        {"field_key": "preferred_inspection_date", "article_id": _ARTICLE_UUID_24, "review_status": "PENDING"},
    ]
    sb = _make_supabase_mock(frm_rows=frm_rows, art_data=[_ART_ROW_24])
    with patch("services.document_forms_service.get_supabase", return_value=sb):
        result = get_document_form_articles("DOC-CHEM-001", include_pending=True)

    assert result["article_count"] == 1
    art = result["articles"][0]
    assert art["is_confirmed"] is False, "APPROVED+PENDING 혼합 → 미승인 연결이 승인으로 승격되면 안 됨"
    assert len(art["field_keys"]) == 2, "두 field_key 모두 포함되어야 함"
