"""
tests/test_document_forms_articles.py
WO-DOC260-SHARED-ARTICLE-READ-019-R2

R2 보정 포함 단위 테스트 (21건).
No live DB; all Supabase calls are mocked.

실제 field_rule_mapping 컬럼: doc_id / field_key / article_id / review_status
law_article 컬럼 추가: law_version_id
law_master 컬럼 추가: current_version_id

Test matrix:
  T01 — 28건 → 1개 조문 중복 제거 + 컬럼명 런타임 검증
  T02 — 화학물질관리법 제24조 정상 반환
  T03 — PENDING-only 필터 제외 시 UNCONFIRMED_MAPPING gap (내부 ID 미노출)
  T04 — 고시 제6조 자동 추론 없음
  T05 — PENDING 매핑 is_confirmed=False
  T06 — APPROVED 매핑 is_confirmed=True
  T07 — include_pending=False → PENDING 제외 → 빈 배열
  T08 — include_pending=True → PENDING 포함
  T09 — 존재하지 않는 서식 → HTTPException 404
  T10 — DELETED + is_deleted_in_version 제외 검증
  T11 — field_rule_mapping 0건 → 빈 배열 반환
  T12 — 미인증 include_pending=true → 401
  T13 — DB 조회 오류 예외 전파
  T14 — APPROVED+PENDING 혼합 + include_pending=True → is_confirmed=False, MIXED
  T15 — APPROVED+PENDING 혼합 + include_pending=False → 공개 응답에서 제외 (R2-01)
  T16 — 공개 gap 메시지에 article_id / field_key 미노출 (R2-02)
  T17 — 일반 인증 사용자 include_pending=True → 403 (R2-03)
  T18 — 관리자 include_pending=True → 정상 조회 (R2-03)
  T19 — 구버전 조문 → 반환 제외 (R2-04)
  T20 — 현재 버전 조문 → 정상 반환 (R2-04)
  T21 — law_master 누락 → 확정 근거 반환 금지 (R2-04)
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
# Fixtures
# ---------------------------------------------------------------------------

_FORM_UUID         = "aaaaaaaa-0001-0001-0001-000000000001"
_ARTICLE_UUID_24   = "bbbbbbbb-0002-0002-0002-000000000002"
_ARTICLE_UUID_6    = "cccccccc-0003-0003-0003-000000000003"
_LAW_UUID_CHEM     = "dddddddd-0004-0004-0004-000000000004"
_VERSION_UUID      = "vvvvvvvv-0006-0006-0006-000000000006"  # current version
_OLD_VERSION_UUID  = "oooooooo-0007-0007-0007-000000000007"  # old version

_FORM_ROW = {
    "id": _FORM_UUID,
    "doc_id": "DOC-CHEM-001",
    "doc_name": "유해화학물질 취급시설 설치검사 신청서",
}

_ART_ROW_24 = {
    "id": _ARTICLE_UUID_24,
    "law_id": _LAW_UUID_CHEM,
    "law_version_id": _VERSION_UUID,        # current version
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
    "current_version_id": _VERSION_UUID,    # matches _ART_ROW_24.law_version_id
}


def _make_frm_rows(count: int, article_id: str, review_status: str = "PENDING") -> list[dict]:
    """field_rule_mapping 행 — 실제 컬럼: article_id, review_status."""
    field_keys = [
        "applicant_information",
        "inspection_target_facility_information",
        "preferred_inspection_date",
        "inspection_detail",
    ]
    return [
        {"field_key": field_keys[i % len(field_keys)], "article_id": article_id, "review_status": review_status}
        for i in range(count)
    ]


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
    form_data = form_data if form_data is not None else [_FORM_ROW]
    frm_rows  = frm_rows  if frm_rows  is not None else _make_frm_rows(28, _ARTICLE_UUID_24, "PENDING")
    art_data  = art_data  if art_data  is not None else [_ART_ROW_24]
    law_data  = law_data  if law_data  is not None else [_LAW_ROW_CHEM]

    def _table(name):
        if name == "document_forms":    return _chain(form_data)
        if name == "field_rule_mapping": return _chain(frm_rows)
        if name == "law_article":        return _chain(art_data)
        if name == "law_master":         return _chain(law_data)
        return _chain([])

    sb = MagicMock()
    sb.table.side_effect = _table
    return sb


# ---------------------------------------------------------------------------
# T01 — 28건 → 1개 조문 중복 제거 + 컬럼명 런타임 검증
# ---------------------------------------------------------------------------
def test_t01_deduplication_and_correct_columns():
    frm_rows = _make_frm_rows(28, _ARTICLE_UUID_24, "APPROVED")
    sb = _make_supabase_mock(frm_rows=frm_rows, art_data=[_ART_ROW_24], law_data=[_LAW_ROW_CHEM])

    selected: dict[str, str] = {}
    orig = sb.table.side_effect

    def capture(name):
        chain = orig(name)
        if name == "field_rule_mapping":
            orig_sel = chain.select
            def spy(cols):
                selected["frm"] = cols
                return orig_sel(cols)
            chain.select = spy
        return chain

    sb.table.side_effect = capture

    with patch("services.document_forms_service.get_supabase", return_value=sb):
        result = get_document_form_articles("DOC-CHEM-001", include_pending=True)

    assert result["article_count"] == 1
    frm_sel = selected.get("frm", "")
    assert "article_id" in frm_sel
    assert "review_status" in frm_sel
    assert "law_article_id" not in frm_sel
    assert "form_id" not in frm_sel


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
    assert art["law_article_id"] == _ARTICLE_UUID_24


# ---------------------------------------------------------------------------
# T03 — PENDING-only 필터 제외 시 UNCONFIRMED_MAPPING gap 보고 (내부 ID 미노출)
# ---------------------------------------------------------------------------
def test_t03_unconfirmed_mapping_gap_no_internal_ids():
    frm_rows = [
        {"field_key": "applicant_information", "article_id": _ARTICLE_UUID_24, "review_status": "PENDING"},
    ]
    sb = _make_supabase_mock(frm_rows=frm_rows, art_data=[_ART_ROW_24])
    with patch("services.document_forms_service.get_supabase", return_value=sb):
        result = get_document_form_articles("DOC-CHEM-001", include_pending=False)

    assert result["article_count"] == 0
    assert len(result["mapping_gaps"]) > 0
    gap_text = " ".join(result["mapping_gaps"])
    assert "UNCONFIRMED_MAPPING" in gap_text
    # 공개 응답: 내부 UUID 및 field_key 미노출 (R2-02)
    assert _ARTICLE_UUID_24 not in gap_text
    assert "applicant_information" not in gap_text
    assert "고시 제6조" not in gap_text


# ---------------------------------------------------------------------------
# T04 — 고시 제6조 자동 추론 없음
# ---------------------------------------------------------------------------
def test_t04_no_auto_inference_of_gosi_art6():
    frm_rows = [
        {"field_key": "applicant_information", "article_id": _ARTICLE_UUID_24, "review_status": "APPROVED"},
    ]
    _LAW_UUID_GOSI = "eeeeeeee-0005-0005-0005-000000000005"
    _VERSION_UUID_GOSI = "gggggggg-0008-0008-0008-000000000008"
    art_both = [
        _ART_ROW_24,
        {
            "id": _ARTICLE_UUID_6,
            "law_id": _LAW_UUID_GOSI,
            "law_version_id": _VERSION_UUID_GOSI,
            "article_no": 6,
            "article_title": "사전서면검사자료",
            "article_text": "제6조...",
            "article_internal_key": "nfpc-art-006",
            "enforcement_date": "2025-10-07",
            "article_status_code": "ACTIVE",
            "is_deleted_in_version": False,
        },
    ]
    law_both = [
        _LAW_ROW_CHEM,
        {
            "id": _LAW_UUID_GOSI,
            "law_name": "환경부고시 제2025-165호",
            "law_number": "환경부고시 제2025-165호",
            "enforcement_date": "2025-10-07",
            "current_version_id": _VERSION_UUID_GOSI,
        },
    ]
    sb = _make_supabase_mock(frm_rows=frm_rows, art_data=art_both, law_data=law_both)
    with patch("services.document_forms_service.get_supabase", return_value=sb):
        result = get_document_form_articles("DOC-CHEM-001")

    ids = [a["law_article_id"] for a in result["articles"]]
    assert _ARTICLE_UUID_6 not in ids, "매핑 없는 고시 제6조는 자동으로 반환되지 않아야 함"


# ---------------------------------------------------------------------------
# T05 — PENDING → is_confirmed=False
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
# T06 — APPROVED → is_confirmed=True
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
    sb = _make_supabase_mock(frm_rows=_make_frm_rows(4, _ARTICLE_UUID_24, "PENDING"))
    with patch("services.document_forms_service.get_supabase", return_value=sb):
        result = get_document_form_articles("DOC-CHEM-001", include_pending=False)

    assert result["article_count"] == 0
    assert result["articles"] == []


# ---------------------------------------------------------------------------
# T08 — include_pending=True → PENDING 포함
# ---------------------------------------------------------------------------
def test_t08_include_pending_flag():
    sb = _make_supabase_mock(frm_rows=_make_frm_rows(4, _ARTICLE_UUID_24, "PENDING"), art_data=[_ART_ROW_24])
    with patch("services.document_forms_service.get_supabase", return_value=sb):
        result = get_document_form_articles("DOC-CHEM-001", include_pending=True)

    assert result["article_count"] == 1
    assert result["articles"][0]["is_confirmed"] is False


# ---------------------------------------------------------------------------
# T09 — 404 not found
# ---------------------------------------------------------------------------
def test_t09_not_found_raises_404():
    sb = _make_supabase_mock(form_data=[])
    with patch("services.document_forms_service.get_supabase", return_value=sb):
        with pytest.raises(HTTPException) as exc_info:
            get_document_form_articles("DOC-NONEXISTENT-999")
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# T10 — DELETED + is_deleted_in_version 필터 검증
# ---------------------------------------------------------------------------
def test_t10_deleted_and_version_deleted_excluded():
    frm_rows = [{"field_key": "applicant_information", "article_id": _ARTICLE_UUID_24, "review_status": "APPROVED"}]
    sb = _make_supabase_mock(frm_rows=frm_rows, art_data=[])  # DELETED/is_deleted 제외 후 0건
    with patch("services.document_forms_service.get_supabase", return_value=sb):
        result = get_document_form_articles("DOC-CHEM-001")
    assert result["article_count"] == 0

    # is_deleted_in_version 필터 호출 확인
    eq_calls: list[tuple] = []

    def _t2(name):
        if name == "document_forms":
            return _chain([_FORM_ROW])
        if name == "field_rule_mapping":
            return _chain(frm_rows)
        if name == "law_article":
            c = _chain([])
            def spy_eq(col, val):
                eq_calls.append((col, val))
                return c
            c.eq.side_effect = spy_eq
            return c
        return _chain([])

    sb2 = MagicMock()
    sb2.table.side_effect = _t2
    with patch("services.document_forms_service.get_supabase", return_value=sb2):
        get_document_form_articles("DOC-CHEM-001")

    assert "is_deleted_in_version" in [col for col, _ in eq_calls]


# ---------------------------------------------------------------------------
# T11 — field_rule_mapping 0건 → 빈 배열
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
# T12 — 미인증 include_pending=True → 401 (라우터)
# ---------------------------------------------------------------------------
def test_t12_pending_requires_authentication():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers.document_forms import router as doc_router
    from routers.auth import get_current_user_optional

    _app = FastAPI()
    _app.include_router(doc_router)
    _app.dependency_overrides[get_current_user_optional] = lambda: None

    client = TestClient(_app, raise_server_exceptions=False)
    resp = client.get("/document-forms/DOC-CHEM-001/articles?include_pending=true")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# T13 — DB 오류 예외 전파 (빈 결과 은폐 금지)
# ---------------------------------------------------------------------------
def test_t13_db_error_propagates_not_silenced():
    def _t(name):
        if name == "document_forms":
            return _chain([_FORM_ROW])
        if name == "field_rule_mapping":
            c = MagicMock()
            c.execute.side_effect = Exception("DB timeout")
            c.select.return_value = c
            c.eq.return_value = c
            return c
        return _chain([])

    sb = MagicMock()
    sb.table.side_effect = _t
    with patch("services.document_forms_service.get_supabase", return_value=sb):
        with pytest.raises(Exception) as exc:
            get_document_form_articles("DOC-CHEM-001")
    if isinstance(exc.value, HTTPException):
        assert exc.value.status_code != 404


# ---------------------------------------------------------------------------
# T14 — APPROVED+PENDING 혼합 + include_pending=True → is_confirmed=False, MIXED
# ---------------------------------------------------------------------------
def test_t14_mixed_status_include_pending_true():
    frm_rows = [
        {"field_key": "applicant_information",    "article_id": _ARTICLE_UUID_24, "review_status": "APPROVED"},
        {"field_key": "preferred_inspection_date", "article_id": _ARTICLE_UUID_24, "review_status": "PENDING"},
    ]
    sb = _make_supabase_mock(frm_rows=frm_rows, art_data=[_ART_ROW_24])
    with patch("services.document_forms_service.get_supabase", return_value=sb):
        result = get_document_form_articles("DOC-CHEM-001", include_pending=True)

    assert result["article_count"] == 1
    art = result["articles"][0]
    assert art["is_confirmed"] is False
    assert art["mapping_status"] == "MIXED"
    assert len(art["field_keys"]) == 2


# ---------------------------------------------------------------------------
# T15 — APPROVED+PENDING 혼합 + include_pending=False → 공개 응답에서 제외 (R2-01)
# ---------------------------------------------------------------------------
def test_t15_mixed_status_excluded_from_public():
    """혼합 상태 조문은 공개(include_pending=false) 응답에 포함하지 않음."""
    frm_rows = [
        {"field_key": "applicant_information",    "article_id": _ARTICLE_UUID_24, "review_status": "APPROVED"},
        {"field_key": "preferred_inspection_date", "article_id": _ARTICLE_UUID_24, "review_status": "PENDING"},
    ]
    sb = _make_supabase_mock(frm_rows=frm_rows, art_data=[_ART_ROW_24])
    with patch("services.document_forms_service.get_supabase", return_value=sb):
        result = get_document_form_articles("DOC-CHEM-001", include_pending=False)

    # 혼합 조문은 확정 근거로 공개 응답에 반환되지 않음 (R2-01)
    assert result["article_count"] == 0, "APPROVED+PENDING 혼합 조문은 공개 응답 제외"
    ids = [a["law_article_id"] for a in result["articles"]]
    assert _ARTICLE_UUID_24 not in ids


# ---------------------------------------------------------------------------
# T16 — 공개 gap 메시지에 article_id / field_key 미노출 (R2-02)
# ---------------------------------------------------------------------------
def test_t16_public_gap_no_internal_ids():
    """공개 gap에 article UUID와 field_key 이름 노출 금지."""
    frm_rows = [
        {"field_key": "applicant_information",     "article_id": _ARTICLE_UUID_24, "review_status": "PENDING"},
        {"field_key": "inspection_target_facility", "article_id": _ARTICLE_UUID_24, "review_status": "PENDING"},
    ]
    sb = _make_supabase_mock(frm_rows=frm_rows)
    with patch("services.document_forms_service.get_supabase", return_value=sb):
        result = get_document_form_articles("DOC-CHEM-001", include_pending=False)

    gap_text = " ".join(result["mapping_gaps"])
    assert _ARTICLE_UUID_24 not in gap_text,           "공개 gap에 article UUID 노출 금지"
    assert "applicant_information" not in gap_text,    "공개 gap에 field_key 노출 금지"
    assert "inspection_target_facility" not in gap_text
    assert "UNCONFIRMED_MAPPING" in gap_text


# ---------------------------------------------------------------------------
# T17 — 일반 인증 사용자 include_pending=True → 403 (R2-03)
# ---------------------------------------------------------------------------
def test_t17_general_user_include_pending_returns_403():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers.document_forms import router as doc_router
    from routers.auth import get_current_user_optional

    _non_admin = {"id": "user-001", "role_code": "003"}

    # _require_admin은 get_supabase() 결과를 인수로 받으므로 두 곳 모두 패치
    with patch("routers.document_forms.get_supabase", return_value=MagicMock()):
        with patch("routers.document_forms._require_admin",
                   side_effect=HTTPException(status_code=403, detail="권한이 없습니다")):
            _app = FastAPI()
            _app.include_router(doc_router)
            _app.dependency_overrides[get_current_user_optional] = lambda: _non_admin
            client = TestClient(_app, raise_server_exceptions=False)
            resp = client.get("/document-forms/DOC-CHEM-001/articles?include_pending=true")

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# T18 — 관리자 include_pending=True → 정상 조회 (R2-03)
# ---------------------------------------------------------------------------
def test_t18_admin_include_pending_returns_200():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers.document_forms import router as doc_router
    from routers.auth import get_current_user_optional

    _admin = {"id": "admin-001", "role_code": "001"}
    frm_rows = _make_frm_rows(4, _ARTICLE_UUID_24, "PENDING")
    sb = _make_supabase_mock(frm_rows=frm_rows, art_data=[_ART_ROW_24])

    _app = FastAPI()
    _app.include_router(doc_router)
    _app.dependency_overrides[get_current_user_optional] = lambda: _admin

    with patch("routers.document_forms._require_admin"):          # 관리자 통과
        with patch("services.document_forms_service.get_supabase", return_value=sb):
            with patch("routers.document_forms.get_supabase", return_value=sb):
                client = TestClient(_app, raise_server_exceptions=True)
                resp = client.get("/document-forms/DOC-CHEM-001/articles?include_pending=true")

    assert resp.status_code == 200
    body = resp.json()
    assert body["include_pending"] is True


# ---------------------------------------------------------------------------
# T19 — 구버전 조문 → 반환 제외 (R2-04)
# ---------------------------------------------------------------------------
def test_t19_old_law_version_excluded():
    """law_article.law_version_id != law_master.current_version_id → 반환 제외."""
    art_old = {**_ART_ROW_24, "law_version_id": _OLD_VERSION_UUID}  # old version
    frm_rows = [{"field_key": "applicant_information", "article_id": _ARTICLE_UUID_24, "review_status": "APPROVED"}]
    sb = _make_supabase_mock(frm_rows=frm_rows, art_data=[art_old], law_data=[_LAW_ROW_CHEM])
    with patch("services.document_forms_service.get_supabase", return_value=sb):
        result = get_document_form_articles("DOC-CHEM-001")

    assert result["article_count"] == 0, "구버전 조문은 반환하지 않음"


# ---------------------------------------------------------------------------
# T20 — 현재 버전 조문 → 정상 반환 (R2-04)
# ---------------------------------------------------------------------------
def test_t20_current_law_version_included():
    """law_version_id == current_version_id → 정상 반환."""
    frm_rows = [{"field_key": "applicant_information", "article_id": _ARTICLE_UUID_24, "review_status": "APPROVED"}]
    sb = _make_supabase_mock(frm_rows=frm_rows, art_data=[_ART_ROW_24], law_data=[_LAW_ROW_CHEM])
    with patch("services.document_forms_service.get_supabase", return_value=sb):
        result = get_document_form_articles("DOC-CHEM-001")

    assert result["article_count"] == 1
    assert result["articles"][0]["law_article_id"] == _ARTICLE_UUID_24


# ---------------------------------------------------------------------------
# T21 — law_master 누락 → 확정 근거 반환 금지 (R2-04)
# ---------------------------------------------------------------------------
def test_t21_missing_law_master_not_returned():
    """law_master 없는 조문 (current_version_id 확인 불가) → 반환 금지."""
    frm_rows = [{"field_key": "applicant_information", "article_id": _ARTICLE_UUID_24, "review_status": "APPROVED"}]
    sb = _make_supabase_mock(frm_rows=frm_rows, art_data=[_ART_ROW_24], law_data=[])  # 법령 없음
    with patch("services.document_forms_service.get_supabase", return_value=sb):
        result = get_document_form_articles("DOC-CHEM-001")

    assert result["article_count"] == 0, "법령 미확인 시 확정 근거로 반환 금지"
