"""
tests/test_document_forms_articles.py
WO-DOC260-SHARED-ARTICLE-READ-019

get_document_form_articles() 단위 테스트.
No live DB; all Supabase calls are mocked.

Test matrix:
  T01 — 28건 field_rule_mapping → 1개 조문으로 중복 제거
  T02 — 화학물질관리법 제24조 article_no=24 정상 반환
  T03 — design_layout 직접 매핑 없음 → MAPPING_GAP 보고
  T04 — 고시 제6조 자동 추론 없음 (매핑 없으면 반환 안 됨)
  T05 — PENDING 매핑 is_confirmed=False
  T06 — APPROVED 매핑 is_confirmed=True
  T07 — include_pending=False → PENDING 제외 → 빈 배열
  T08 — include_pending=True → PENDING 포함
  T09 — 존재하지 않는 서식 → HTTPException 404
  T10 — DELETED article_status_code → 반환 제외
  T11 — field_rule_mapping 0건 → 빈 배열 반환
  T12 — form_id UUID 조회 실패 시 doc_id string fallback 시도
"""
from __future__ import annotations

import sys
import os
from http import HTTPStatus
from unittest.mock import MagicMock, call, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import HTTPException
from services.document_forms_service import get_document_form_articles

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FORM_UUID = "aaaaaaaa-0001-0001-0001-000000000001"
_ARTICLE_UUID_24 = "bbbbbbbb-0002-0002-0002-000000000002"   # 화학물질관리법 제24조
_ARTICLE_UUID_6 = "cccccccc-0003-0003-0003-000000000003"    # 환경부고시 제6조
_LAW_UUID_CHEM = "dddddddd-0004-0004-0004-000000000004"     # 화학물질관리법

_FORM_ROW = {"id": _FORM_UUID, "doc_id": "DOC-CHEM-001", "doc_name": "유해화학물질 취급시설 설치검사 신청서"}

_ART_ROW_24 = {
    "id": _ARTICLE_UUID_24,
    "law_id": _LAW_UUID_CHEM,
    "article_no": 24,
    "article_title": "설치검사",
    "article_text": "제24조(설치검사) ...",
    "article_internal_key": "art-024",
    "enforcement_date": "2021-04-01",
    "article_status_code": "ACTIVE",
}

_LAW_ROW_CHEM = {
    "id": _LAW_UUID_CHEM,
    "law_name": "화학물질관리법",
    "law_number": "법률 제18827호",
    "enforcement_date": "2022-01-01",
}


def _make_frm_rows(count: int, article_id: str, status: str = "PENDING") -> list[dict]:
    """field_rule_mapping rows — multiple field_keys pointing to same article_id."""
    field_keys = [
        "applicant_information",
        "inspection_target_facility_information",
        "preferred_inspection_date",
        "design_layout",
    ]
    rows = []
    for i in range(count):
        rows.append({
            "field_key": field_keys[i % len(field_keys)],
            "law_article_id": article_id,
            "status": status,
        })
    return rows


def _make_supabase_mock(
    form_data: list | None = None,
    frm_rows: list | None = None,
    art_data: list | None = None,
    law_data: list | None = None,
    frm_uuid_raises: bool = False,
) -> MagicMock:
    """Build a Supabase mock that routes table() calls by name."""
    form_data = form_data if form_data is not None else [_FORM_ROW]
    frm_rows = frm_rows if frm_rows is not None else _make_frm_rows(28, _ARTICLE_UUID_24, "PENDING")
    art_data = art_data if art_data is not None else [_ART_ROW_24]
    law_data = law_data if law_data is not None else [_LAW_ROW_CHEM]

    def _chain(data):
        c = MagicMock()
        c.execute.return_value = MagicMock(data=data)
        c.select.return_value = c
        c.eq.return_value = c
        c.in_.return_value = c
        c.neq.return_value = c
        c.limit.return_value = c
        return c

    def _chain_raise():
        c = MagicMock()
        c.execute.side_effect = Exception("column form_id does not exist")
        c.select.return_value = c
        c.eq.return_value = c
        c.in_.return_value = c
        c.neq.return_value = c
        c.limit.return_value = c
        return c

    call_count = [0]

    def _table(name):
        if name == "document_forms":
            return _chain(form_data)
        if name == "field_rule_mapping":
            call_count[0] += 1
            if frm_uuid_raises and call_count[0] == 1:
                return _chain_raise()
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
# T01 — 28건 field_rule_mapping → 1개 조문으로 중복 제거
# ---------------------------------------------------------------------------
def test_t01_deduplication():
    sb = _make_supabase_mock(
        frm_rows=_make_frm_rows(28, _ARTICLE_UUID_24, "APPROVED"),
        art_data=[_ART_ROW_24],
        law_data=[_LAW_ROW_CHEM],
    )
    with patch("services.document_forms_service.get_supabase", return_value=sb):
        result = get_document_form_articles("DOC-CHEM-001", include_pending=True)

    assert result["article_count"] == 1, "28건 → 중복 제거 후 1개 조문"
    assert len(result["articles"]) == 1


# ---------------------------------------------------------------------------
# T02 — 화학물질관리법 제24조 정상 반환
# ---------------------------------------------------------------------------
def test_t02_chem_art24_returned():
    sb = _make_supabase_mock(
        frm_rows=_make_frm_rows(4, _ARTICLE_UUID_24, "APPROVED"),
        art_data=[_ART_ROW_24],
        law_data=[_LAW_ROW_CHEM],
    )
    with patch("services.document_forms_service.get_supabase", return_value=sb):
        result = get_document_form_articles("DOC-CHEM-001")

    art = result["articles"][0]
    assert art["article_no"] == 24
    assert "화학물질관리법" in art["law_name"]
    assert art["article_internal_key"] == "art-024"


# ---------------------------------------------------------------------------
# T03 — design_layout 직접 매핑 없음 → MAPPING_GAP 보고
# ---------------------------------------------------------------------------
def test_t03_design_layout_mapping_gap():
    # design_layout이 포함되지 않은 매핑만 있는 경우
    frm_rows = [
        {"field_key": "applicant_information", "law_article_id": _ARTICLE_UUID_24, "status": "APPROVED"},
        {"field_key": "preferred_inspection_date", "law_article_id": _ARTICLE_UUID_24, "status": "APPROVED"},
    ]
    sb = _make_supabase_mock(frm_rows=frm_rows, art_data=[_ART_ROW_24])
    with patch("services.document_forms_service.get_supabase", return_value=sb):
        result = get_document_form_articles("DOC-CHEM-001")

    assert len(result["mapping_gaps"]) > 0
    gap_text = " ".join(result["mapping_gaps"])
    assert "design_layout" in gap_text
    assert "MAPPING_GAP" in gap_text


# ---------------------------------------------------------------------------
# T04 — 고시 제6조 자동 추론 없음 (매핑 없으면 반환 안 됨)
# ---------------------------------------------------------------------------
def test_t04_no_auto_inference_of_gosi_art6():
    # design_layout에 대한 field_rule_mapping이 없고, 고시 제6조 law_article도 DB에 있음
    frm_rows = [
        {"field_key": "applicant_information", "law_article_id": _ARTICLE_UUID_24, "status": "APPROVED"},
    ]
    # law_article에 고시 제6조가 존재해도 매핑이 없으면 반환 안 됨
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
    frm_rows = [{"field_key": "applicant_information", "law_article_id": _ARTICLE_UUID_24, "status": "PENDING"}]
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
    frm_rows = [{"field_key": "applicant_information", "law_article_id": _ARTICLE_UUID_24, "status": "APPROVED"}]
    sb = _make_supabase_mock(frm_rows=frm_rows, art_data=[_ART_ROW_24])
    with patch("services.document_forms_service.get_supabase", return_value=sb):
        result = get_document_form_articles("DOC-CHEM-001")

    assert result["articles"][0]["is_confirmed"] is True


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
# T10 — DELETED article_status_code → 반환 제외
# ---------------------------------------------------------------------------
def test_t10_deleted_article_excluded():
    frm_rows = [{"field_key": "applicant_information", "law_article_id": _ARTICLE_UUID_24, "status": "APPROVED"}]
    # law_article 조회 시 neq("article_status_code", "DELETED") → 빈 반환 시뮬레이션
    sb = _make_supabase_mock(frm_rows=frm_rows, art_data=[])  # DELETED 제외 후 0건
    with patch("services.document_forms_service.get_supabase", return_value=sb):
        result = get_document_form_articles("DOC-CHEM-001")

    assert result["article_count"] == 0


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


# ---------------------------------------------------------------------------
# T12 — form_id UUID 조회 실패 시 doc_id string fallback 시도
# ---------------------------------------------------------------------------
def test_t12_fallback_to_doc_id_string():
    frm_rows = [{"field_key": "applicant_information", "law_article_id": _ARTICLE_UUID_24, "status": "APPROVED"}]
    sb = _make_supabase_mock(
        frm_rows=frm_rows,
        art_data=[_ART_ROW_24],
        frm_uuid_raises=True,  # form_id UUID 쿼리 실패 → doc_id string fallback
    )
    with patch("services.document_forms_service.get_supabase", return_value=sb):
        result = get_document_form_articles("DOC-CHEM-001")

    # fallback 성공 시 결과 반환 (APPROVED이므로 포함)
    assert result["article_count"] == 1
