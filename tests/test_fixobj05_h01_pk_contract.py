"""WO-E2E2000-FIXOBJ05-H01-PK-CONTRACT-BE-001
건축물대장 PK 기반 식별 계약 — 후보 조회 + 검증 적용

PK01  유효한 bdmgtsn → PK 후보 반환, DB WRITE 0
PK02  주건축물 후보 2개 → 첫 행 자동 선택 없음 (전체 목록 반환)
PK03  PK 없는 H01 응답 → unresolved
PK04  제출 PK = H01 PK → 적용 성공 (h01_updated=True)
PK05  제출 PK ≠ H01 PK → 409, UPDATE 0
PK06  기존 확정 PK ≠ 제출 PK → 409, UPDATE 0
PK07  H01 외부 API 오류 → UPDATE 0 (502 / partial)
PK08  높이 0 / 층수 0 → 값 보존
PK09  H01 공식 수치 미확정 → 인증 완료 표시 금지 (h01_updated=False)
PK10  동일 PK·동일 데이터 순차 재호출 → 불필요한 UPDATE 0
PK11  인증 실패 → 401
PK12  타사 factory → 404, H01 조회 및 UPDATE 0
PK13  INDUSTRIAL / CONSTRUCTION → BUILDING 전용 적용 차단 (422)
PK14  기존 /apply 계약 회귀 — W01/W06/W07 재확인
PK15  전체 페이지 수집 실패(None) → 502, UPDATE 0
PK16  이미 확정된 PK 재검증 시 변경된 공식 수치만 처리
"""
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from fastapi import HTTPException as FE


# ── 공통 픽스처 ────────────────────────────────────────────────────────────────

_BDMGTSN = "1168010100103560001"
_PK_A    = "11680-100021234"
_PK_B    = "11680-200034567"

_FACTORY_BUILDING = {
    "id":             "fac-001",
    "name":           "테스트빌딩",
    "sector":         "BUILDING",
    "bdmgtsn":        None,
    "mgm_bldrgst_pk": None,
    "building_height": None,
    "floor_count":    None,
}

_FACTORY_INDUSTRIAL = {
    **_FACTORY_BUILDING,
    "sector": "INDUSTRIAL",
}

_FACTORY_CONSTRUCTION = {
    **_FACTORY_BUILDING,
    "sector": "CONSTRUCTION",
}

_FACTORY_WITH_PK = {
    **_FACTORY_BUILDING,
    "bdmgtsn":                      _BDMGTSN,
    "mgm_bldrgst_pk":               _PK_A,
    "building_height":              45.0,
    "floor_count":                  10,
    "building_register_updated_at": "2026-10-01T10:00:00+09:00",
}

_TITLE_SINGLE = [
    {
        "mgmBldrgstPk":   _PK_A,
        "mainAtchGbCdNm": "주건축물",
        "heit":           "45.0",
        "grndFlrCnt":     "10",
        "mainPurpsCd":    "02000",
        "mainPurpsCdNm":  "공장",
        "bldNm":          "A동",
    }
]

_TITLE_MULTI = [
    {
        "mgmBldrgstPk":   _PK_A,
        "mainAtchGbCdNm": "주건축물",
        "heit":           "45.0",
        "grndFlrCnt":     "10",
        "mainPurpsCdNm":  "공장",
    },
    {
        "mgmBldrgstPk":   _PK_B,
        "mainAtchGbCdNm": "주건축물",
        "heit":           "20.0",
        "grndFlrCnt":     "5",
        "mainPurpsCdNm":  "창고시설",
    },
]

_TITLE_NO_PK = [
    {
        "mgmBldrgstPk":   "",
        "mainAtchGbCdNm": "주건축물",
        "heit":           "30.0",
        "grndFlrCnt":     "7",
    }
]

_TITLE_HEIGHT_ZERO = [
    {
        "mgmBldrgstPk":   _PK_A,
        "mainAtchGbCdNm": "주건축물",
        "heit":           "0.0",
        "grndFlrCnt":     "0",
    }
]

_TITLE_NO_NUMERIC = [
    {
        "mgmBldrgstPk":   _PK_A,
        "mainAtchGbCdNm": "주건축물",
        "heit":           None,
        "grndFlrCnt":     None,
    }
]


def _sb_stub(factory_row=None):
    """Supabase stub: single() → factory_row, update().eq().execute() 추적 가능."""
    sb = MagicMock()
    # select().eq().single().execute()
    res = MagicMock()
    res.data = factory_row
    (sb.table.return_value.select.return_value
     .eq.return_value.single.return_value.execute.return_value) = res
    # update().eq().execute()
    upd_res = MagicMock()
    upd_res.data = [factory_row] if factory_row else []
    (sb.table.return_value.update.return_value
     .eq.return_value.execute.return_value) = upd_res
    return sb


def _make_client():
    from main import app
    return TestClient(app, raise_server_exceptions=True)


def _auth():
    return {"Authorization": "Bearer test-token"}


def _user():
    return {"id": "user-1", "company_id": "co-1"}


# ═══════════════════════════════════════════════════════════════════════════
# PK01~PK03: GET /h01-candidates
# ═══════════════════════════════════════════════════════════════════════════

def test_pk01_candidates_returns_list_no_db_write():
    """PK01: 유효한 bdmgtsn → PK 후보 반환, update() 미호출(DB WRITE 0)."""
    sb = _sb_stub()
    with patch("routers.building_register.get_supabase", return_value=sb), \
         patch("routers.building_register.get_current_user", return_value=_user()), \
         patch("routers.building_register.fetch_h01_title_for_bdmgtsn",
               return_value=_TITLE_SINGLE):
        client = _make_client()
        resp = client.get(f"/building-register/h01-candidates?bdmgtsn={_BDMGTSN}",
                          headers=_auth())
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["total"] == 1
    assert data["candidates"][0]["mgm_bldrgst_pk"] == _PK_A
    # DB WRITE 0
    sb.table.return_value.update.assert_not_called()


def test_pk02_multi_candidates_all_returned_no_auto_select():
    """PK02: 주건축물 2개 → 전체 반환, 첫 행 자동 선택 없음."""
    with patch("routers.building_register.get_supabase", return_value=_sb_stub()), \
         patch("routers.building_register.get_current_user", return_value=_user()), \
         patch("routers.building_register.fetch_h01_title_for_bdmgtsn",
               return_value=_TITLE_MULTI):
        client = _make_client()
        resp = client.get(f"/building-register/h01-candidates?bdmgtsn={_BDMGTSN}",
                          headers=_auth())
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    pks = [c["mgm_bldrgst_pk"] for c in data["candidates"]]
    assert _PK_A in pks
    assert _PK_B in pks
    # 자동 선택 없음 — 2건 모두 반환
    assert len(data["candidates"]) == 2


def test_pk03_no_pk_in_h01_unresolved():
    """PK03: PK 없는 H01 응답 → unresolved, 후보 0건."""
    with patch("routers.building_register.get_supabase", return_value=_sb_stub()), \
         patch("routers.building_register.get_current_user", return_value=_user()), \
         patch("routers.building_register.fetch_h01_title_for_bdmgtsn",
               return_value=_TITLE_NO_PK):
        client = _make_client()
        resp = client.get(f"/building-register/h01-candidates?bdmgtsn={_BDMGTSN}",
                          headers=_auth())
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "unresolved"
    assert data["total"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# PK04~PK10, PK15~PK16: POST /apply-verified/{factory_id}
# ═══════════════════════════════════════════════════════════════════════════

def test_pk04_matching_pk_apply_success():
    """PK04: 제출 PK = H01 PK → h01_updated=True, UPDATE 호출."""
    sb = _sb_stub(_FACTORY_BUILDING)
    with patch("routers.building_register.get_supabase", return_value=sb), \
         patch("routers.building_register.get_current_user", return_value=_user()), \
         patch("routers.building_register._ensure_factory_own"), \
         patch("routers.building_register.fetch_h01_title_for_bdmgtsn",
               return_value=_TITLE_SINGLE), \
         patch("routers.building_register.extract_h01_fields",
               return_value={"mgm_bldrgst_pk": _PK_A, "building_height": 45.0, "floor_count": 10}):
        client = _make_client()
        resp = client.post("/building-register/apply-verified/fac-001",
                           json={"bdmgtsn": _BDMGTSN, "expected_mgm_bldrgst_pk": _PK_A},
                           headers=_auth())
    assert resp.status_code == 200
    data = resp.json()
    assert data["h01_updated"] is True
    assert data["mgm_bldrgst_pk"] == _PK_A
    assert data["building_height"] == 45.0
    assert data["floor_count"] == 10
    sb.table.return_value.update.assert_called_once()


def test_pk05_pk_mismatch_h01_returns_409_no_update():
    """PK05: 제출 PK ≠ H01 PK → 409 BUILDING_IDENTITY_MISMATCH, UPDATE 0."""
    sb = _sb_stub(_FACTORY_BUILDING)
    # H01에서 PK_B가 실제로 반환됐지만 사용자는 PK_A 제출 → extract_h01_fields는 {}
    with patch("routers.building_register.get_supabase", return_value=sb), \
         patch("routers.building_register.get_current_user", return_value=_user()), \
         patch("routers.building_register._ensure_factory_own"), \
         patch("routers.building_register.fetch_h01_title_for_bdmgtsn",
               return_value=_TITLE_MULTI), \
         patch("routers.building_register.extract_h01_fields", return_value={}):
        client = _make_client()
        resp = client.post("/building-register/apply-verified/fac-001",
                           json={"bdmgtsn": _BDMGTSN, "expected_mgm_bldrgst_pk": _PK_A},
                           headers=_auth())
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "BUILDING_IDENTITY_MISMATCH"
    sb.table.return_value.update.assert_not_called()


def test_pk06_existing_pk_mismatch_returns_409_no_update():
    """PK06: 기존 확정 PK ≠ 제출 PK → 409, UPDATE 0."""
    factory_confirmed = {**_FACTORY_BUILDING, "mgm_bldrgst_pk": "11680-OTHER"}
    sb = _sb_stub(factory_confirmed)
    with patch("routers.building_register.get_supabase", return_value=sb), \
         patch("routers.building_register.get_current_user", return_value=_user()), \
         patch("routers.building_register._ensure_factory_own"), \
         patch("routers.building_register.fetch_h01_title_for_bdmgtsn") as mock_h01:
        client = _make_client()
        resp = client.post("/building-register/apply-verified/fac-001",
                           json={"bdmgtsn": _BDMGTSN, "expected_mgm_bldrgst_pk": _PK_A},
                           headers=_auth())
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "BUILDING_IDENTITY_MISMATCH"
    # H01 조회 호출 없음 (기존 PK 불일치로 조기 차단)
    mock_h01.assert_not_called()
    sb.table.return_value.update.assert_not_called()


def test_pk07_h01_api_error_no_update():
    """PK07: H01 외부 API 오류(None 반환) → 502, UPDATE 0."""
    sb = _sb_stub(_FACTORY_BUILDING)
    with patch("routers.building_register.get_supabase", return_value=sb), \
         patch("routers.building_register.get_current_user", return_value=_user()), \
         patch("routers.building_register._ensure_factory_own"), \
         patch("routers.building_register.fetch_h01_title_for_bdmgtsn", return_value=None):
        client = _make_client()
        resp = client.post("/building-register/apply-verified/fac-001",
                           json={"bdmgtsn": _BDMGTSN, "expected_mgm_bldrgst_pk": _PK_A},
                           headers=_auth())
    assert resp.status_code == 502
    assert resp.json()["detail"]["code"] == "SOURCE_UNAVAILABLE"
    sb.table.return_value.update.assert_not_called()


def test_pk08_height_zero_floor_zero_preserved():
    """PK08: 높이 0 / 층수 0 → 값 보존 (None 대체 금지)."""
    sb = _sb_stub(_FACTORY_BUILDING)
    with patch("routers.building_register.get_supabase", return_value=sb), \
         patch("routers.building_register.get_current_user", return_value=_user()), \
         patch("routers.building_register._ensure_factory_own"), \
         patch("routers.building_register.fetch_h01_title_for_bdmgtsn",
               return_value=_TITLE_HEIGHT_ZERO), \
         patch("routers.building_register.extract_h01_fields",
               return_value={"mgm_bldrgst_pk": _PK_A, "building_height": 0.0, "floor_count": 0}):
        client = _make_client()
        resp = client.post("/building-register/apply-verified/fac-001",
                           json={"bdmgtsn": _BDMGTSN, "expected_mgm_bldrgst_pk": _PK_A},
                           headers=_auth())
    assert resp.status_code == 200
    data = resp.json()
    assert data["h01_updated"] is True
    # 0 값 보존 확인
    update_call = sb.table.return_value.update.call_args[0][0]
    assert update_call["building_height"] == 0.0
    assert update_call["floor_count"] == 0


def test_pk09_no_numeric_no_official_auth():
    """PK09: H01 공식 수치 미확정(height=None, floor=None) → h01_updated=False, UPDATE 0."""
    sb = _sb_stub(_FACTORY_BUILDING)
    with patch("routers.building_register.get_supabase", return_value=sb), \
         patch("routers.building_register.get_current_user", return_value=_user()), \
         patch("routers.building_register._ensure_factory_own"), \
         patch("routers.building_register.fetch_h01_title_for_bdmgtsn",
               return_value=_TITLE_NO_NUMERIC), \
         patch("routers.building_register.extract_h01_fields",
               return_value={"mgm_bldrgst_pk": _PK_A}):
        client = _make_client()
        resp = client.post("/building-register/apply-verified/fac-001",
                           json={"bdmgtsn": _BDMGTSN, "expected_mgm_bldrgst_pk": _PK_A},
                           headers=_auth())
    assert resp.status_code == 200
    data = resp.json()
    assert data["h01_updated"] is False
    assert data["code"] == "H01_NUMERIC_ABSENT"
    sb.table.return_value.update.assert_not_called()


def test_pk10_same_pk_same_data_no_update():
    """PK10: 동일 PK·동일 수치 → idempotent=True, UPDATE 0."""
    factory_same = {**_FACTORY_WITH_PK}
    sb = _sb_stub(factory_same)
    with patch("routers.building_register.get_supabase", return_value=sb), \
         patch("routers.building_register.get_current_user", return_value=_user()), \
         patch("routers.building_register._ensure_factory_own"), \
         patch("routers.building_register.fetch_h01_title_for_bdmgtsn",
               return_value=_TITLE_SINGLE), \
         patch("routers.building_register.extract_h01_fields",
               return_value={"mgm_bldrgst_pk": _PK_A, "building_height": 45.0, "floor_count": 10}):
        client = _make_client()
        resp = client.post("/building-register/apply-verified/fac-001",
                           json={"bdmgtsn": _BDMGTSN, "expected_mgm_bldrgst_pk": _PK_A},
                           headers=_auth())
    assert resp.status_code == 200
    data = resp.json()
    assert data["h01_updated"] is False
    assert data.get("idempotent") is True
    sb.table.return_value.update.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# PK11~PK13: 접근 제어
# ═══════════════════════════════════════════════════════════════════════════

def test_pk11_no_auth_returns_401_candidates():
    """PK11: 인증 없음 → 401 (h01-candidates)."""
    client = _make_client()
    resp = client.get(f"/building-register/h01-candidates?bdmgtsn={_BDMGTSN}")
    assert resp.status_code == 401


def test_pk11b_no_auth_returns_401_apply_verified():
    """PK11: 인증 없음 → 401 (apply-verified)."""
    client = _make_client()
    resp = client.post("/building-register/apply-verified/fac-001",
                       json={"bdmgtsn": _BDMGTSN, "expected_mgm_bldrgst_pk": _PK_A})
    assert resp.status_code == 401


def test_pk12_wrong_company_returns_404_no_h01_no_update():
    """PK12: 타사 factory → 404, H01 조회 및 UPDATE 0."""
    sb = _sb_stub(_FACTORY_BUILDING)
    with patch("routers.building_register.get_supabase", return_value=sb), \
         patch("routers.building_register.get_current_user", return_value=_user()), \
         patch("routers.building_register._ensure_factory_own",
               side_effect=FE(status_code=404, detail="시설을 찾을 수 없습니다")), \
         patch("routers.building_register.fetch_h01_title_for_bdmgtsn") as mock_h01:
        client = _make_client()
        resp = client.post("/building-register/apply-verified/fac-001",
                           json={"bdmgtsn": _BDMGTSN, "expected_mgm_bldrgst_pk": _PK_A},
                           headers=_auth())
    assert resp.status_code == 404
    mock_h01.assert_not_called()
    sb.table.return_value.update.assert_not_called()


def test_pk13_industrial_sector_rejected():
    """PK13: INDUSTRIAL → 422 SECTOR_NOT_BUILDING."""
    sb = _sb_stub(_FACTORY_INDUSTRIAL)
    with patch("routers.building_register.get_supabase", return_value=sb), \
         patch("routers.building_register.get_current_user", return_value=_user()), \
         patch("routers.building_register._ensure_factory_own"), \
         patch("routers.building_register.fetch_h01_title_for_bdmgtsn") as mock_h01:
        client = _make_client()
        resp = client.post("/building-register/apply-verified/fac-001",
                           json={"bdmgtsn": _BDMGTSN, "expected_mgm_bldrgst_pk": _PK_A},
                           headers=_auth())
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "SECTOR_NOT_BUILDING"
    mock_h01.assert_not_called()
    sb.table.return_value.update.assert_not_called()


def test_pk13b_construction_sector_rejected():
    """PK13: CONSTRUCTION → 422 SECTOR_NOT_BUILDING."""
    sb = _sb_stub(_FACTORY_CONSTRUCTION)
    with patch("routers.building_register.get_supabase", return_value=sb), \
         patch("routers.building_register.get_current_user", return_value=_user()), \
         patch("routers.building_register._ensure_factory_own"), \
         patch("routers.building_register.fetch_h01_title_for_bdmgtsn") as mock_h01:
        client = _make_client()
        resp = client.post("/building-register/apply-verified/fac-001",
                           json={"bdmgtsn": _BDMGTSN, "expected_mgm_bldrgst_pk": _PK_A},
                           headers=_auth())
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "SECTOR_NOT_BUILDING"
    mock_h01.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# PK14: 기존 /apply 계약 회귀
# ═══════════════════════════════════════════════════════════════════════════

def test_pk14_existing_apply_w07_no_auth_401():
    """PK14 회귀: 기존 POST /apply/{factory_id} — 인증 없으면 401."""
    with patch("routers.building_register.get_supabase", return_value=_sb_stub(_FACTORY_BUILDING)):
        client = _make_client()
        resp = client.post("/building-register/apply/fac-001")
    assert resp.status_code == 401


def test_pk14_existing_apply_w06_identity_mismatch_409():
    """PK14 회귀: 기존 /apply — 다른 bdmgtsn + 확정 PK → 409."""
    confirmed = {
        **_FACTORY_BUILDING,
        "address_road":   "서울특별시 강남구 테헤란로 1",
        "address_jibun":  None,
        "bdmgtsn":        "9999999999999999999",
        "mgm_bldrgst_pk": "99999-EXISTING",
    }
    juso_new = {
        "bdMgtSn":        "1234567890123456789",
        "roadAddr":       "서울특별시 강남구 테헤란로 1",
        "roadAddrPart1":  "서울특별시 강남구 테헤란로 1",
        "jibunAddr":      "서울특별시 강남구 역삼동 1",
        "zipNo":          "06234",
    }
    with patch("routers.building_register.get_supabase", return_value=_sb_stub(confirmed)), \
         patch("routers.building_register.get_current_user", return_value=_user()), \
         patch("routers.building_register._ensure_factory_own"), \
         patch("routers.building_register.get_juso", return_value=juso_new):
        client = _make_client()
        resp = client.post("/building-register/apply/fac-001", headers=_auth())
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "BUILDING_IDENTITY_MISMATCH"


def test_pk14_existing_apply_w01_single_building_success():
    """PK14 회귀: 기존 /apply — 단일 본동 정상 등록, h01_updated=True."""
    factory_with_addr = {
        **_FACTORY_BUILDING,
        "address_road":  "서울특별시 강남구 테헤란로 1",
        "address_jibun": None,
    }
    juso = {
        "bdMgtSn":        _BDMGTSN,
        "roadAddr":       "서울특별시 강남구 테헤란로 1",
        "roadAddrPart1":  "서울특별시 강남구 테헤란로 1",
        "jibunAddr":      "서울특별시 강남구 역삼동 831",
        "zipNo":          "06234",
        "siNm":           "서울특별시",
        "sggNm":          "강남구",
        "emdNm":          "역삼동",
    }
    with patch("routers.building_register.get_supabase", return_value=_sb_stub(factory_with_addr)), \
         patch("routers.building_register.get_current_user", return_value=_user()), \
         patch("routers.building_register._ensure_factory_own"), \
         patch("routers.building_register.get_juso", return_value=juso), \
         patch("routers.building_register.fetch_h01_title_for_bdmgtsn",
               return_value=_TITLE_SINGLE), \
         patch("routers.building_register.extract_h01_fields",
               return_value={"mgm_bldrgst_pk": _PK_A, "building_height": 45.0, "floor_count": 10}):
        client = _make_client()
        resp = client.post("/building-register/apply/fac-001", headers=_auth())
    assert resp.status_code == 200
    assert resp.json()["h01_updated"] is True


# ═══════════════════════════════════════════════════════════════════════════
# PK15: 전체 페이지 수집 실패 → fail-closed
# ═══════════════════════════════════════════════════════════════════════════

def test_pk15_page_collect_failure_fail_closed():
    """PK15: fetch_h01_title_for_bdmgtsn=None → 502, UPDATE 0 (apply-verified)."""
    sb = _sb_stub(_FACTORY_BUILDING)
    with patch("routers.building_register.get_supabase", return_value=sb), \
         patch("routers.building_register.get_current_user", return_value=_user()), \
         patch("routers.building_register._ensure_factory_own"), \
         patch("routers.building_register.fetch_h01_title_for_bdmgtsn", return_value=None):
        client = _make_client()
        resp = client.post("/building-register/apply-verified/fac-001",
                           json={"bdmgtsn": _BDMGTSN, "expected_mgm_bldrgst_pk": _PK_A},
                           headers=_auth())
    assert resp.status_code == 502
    sb.table.return_value.update.assert_not_called()


def test_pk15b_candidates_source_unavailable():
    """PK15: GET /h01-candidates에서 fetch 실패(None) → 502."""
    with patch("routers.building_register.get_supabase", return_value=_sb_stub()), \
         patch("routers.building_register.get_current_user", return_value=_user()), \
         patch("routers.building_register.fetch_h01_title_for_bdmgtsn", return_value=None):
        client = _make_client()
        resp = client.get(f"/building-register/h01-candidates?bdmgtsn={_BDMGTSN}",
                          headers=_auth())
    assert resp.status_code == 502
    assert resp.json()["detail"]["code"] == "SOURCE_UNAVAILABLE"


# ═══════════════════════════════════════════════════════════════════════════
# PK16: 이미 확정된 PK 재검증 — 변경된 공식 수치만 처리
# ═══════════════════════════════════════════════════════════════════════════

def test_pk16_same_pk_updated_numeric_triggers_update():
    """PK16: 동일 PK이지만 수치가 변경된 경우 UPDATE 실행."""
    factory_old = {
        **_FACTORY_WITH_PK,
        "building_height": 45.0,
        "floor_count":     10,
    }
    sb = _sb_stub(factory_old)
    # H01에서 이번에는 층수가 11로 바뀜
    with patch("routers.building_register.get_supabase", return_value=sb), \
         patch("routers.building_register.get_current_user", return_value=_user()), \
         patch("routers.building_register._ensure_factory_own"), \
         patch("routers.building_register.fetch_h01_title_for_bdmgtsn",
               return_value=_TITLE_SINGLE), \
         patch("routers.building_register.extract_h01_fields",
               return_value={"mgm_bldrgst_pk": _PK_A, "building_height": 45.0, "floor_count": 11}):
        client = _make_client()
        resp = client.post("/building-register/apply-verified/fac-001",
                           json={"bdmgtsn": _BDMGTSN, "expected_mgm_bldrgst_pk": _PK_A},
                           headers=_auth())
    assert resp.status_code == 200
    data = resp.json()
    assert data["h01_updated"] is True
    assert data["floor_count"] == 11
    # UPDATE가 실제로 호출됐는지 확인
    sb.table.return_value.update.assert_called_once()
    updated_patch = sb.table.return_value.update.call_args[0][0]
    assert updated_patch["floor_count"] == 11


# ════════════════════════════════════════════════════════════════════════════
# ID01~ID08 — 멱등성 5조건 계약
#   ID01  최초 인증(timestamp=None) → 멱등 생략 불가, UPDATE 실행
#   ID02  동일 bdmgtsn + NULL timestamp + 동일 수치 → 멱등 생략 불가, UPDATE 실행
#   ID03  다른 bdmgtsn + 동일 수치 → 멱등 생략 불가, UPDATE 실행
#   ID04  5조건 전부 충족 → 멱등 생략, UPDATE 0
#   ID05  PK 동일 + timestamp 있음 + 수치 일치 + bdmgtsn 불일치 → UPDATE 실행
#   ID06  PK 동일 + timestamp 있음 + bdmgtsn 일치 + height 변경 → UPDATE 실행
#   ID07  PK 동일 + timestamp 있음 + bdmgtsn 일치 + floor 변경 → UPDATE 실행
#   ID08  PK 불일치(이미 다른 PK) + 5조건 무관 → 409
# ════════════════════════════════════════════════════════════════════════════


def test_id01_first_certification_no_timestamp_triggers_update():
    """ID01: 최초 인증 — timestamp=None이면 멱등 생략 불가, UPDATE 실행."""
    factory_no_ts = {
        **_FACTORY_WITH_PK,
        "building_register_updated_at": None,
    }
    sb = _sb_stub(factory_no_ts)
    with patch("routers.building_register.get_supabase", return_value=sb), \
         patch("routers.building_register.get_current_user", return_value=_user()), \
         patch("routers.building_register._ensure_factory_own"), \
         patch("routers.building_register.fetch_h01_title_for_bdmgtsn",
               return_value=_TITLE_SINGLE), \
         patch("routers.building_register.extract_h01_fields",
               return_value={"mgm_bldrgst_pk": _PK_A, "building_height": 45.0, "floor_count": 10}):
        client = _make_client()
        resp = client.post("/building-register/apply-verified/fac-001",
                           json={"bdmgtsn": _BDMGTSN, "expected_mgm_bldrgst_pk": _PK_A},
                           headers=_auth())
    assert resp.status_code == 200
    data = resp.json()
    assert data["h01_updated"] is True
    assert data.get("idempotent") is not True
    sb.table.return_value.update.assert_called_once()


def test_id02_same_pk_and_numerics_but_no_timestamp_triggers_update():
    """ID02: PK·수치 동일이어도 timestamp=None → UPDATE 실행 (미인증 상태)."""
    factory_no_ts = {
        **_FACTORY_WITH_PK,
        "building_register_updated_at": None,
    }
    sb = _sb_stub(factory_no_ts)
    with patch("routers.building_register.get_supabase", return_value=sb), \
         patch("routers.building_register.get_current_user", return_value=_user()), \
         patch("routers.building_register._ensure_factory_own"), \
         patch("routers.building_register.fetch_h01_title_for_bdmgtsn",
               return_value=_TITLE_SINGLE), \
         patch("routers.building_register.extract_h01_fields",
               return_value={"mgm_bldrgst_pk": _PK_A, "building_height": 45.0, "floor_count": 10}):
        client = _make_client()
        resp = client.post("/building-register/apply-verified/fac-001",
                           json={"bdmgtsn": _BDMGTSN, "expected_mgm_bldrgst_pk": _PK_A},
                           headers=_auth())
    assert resp.status_code == 200
    assert resp.json()["h01_updated"] is True
    sb.table.return_value.update.assert_called_once()


def test_id03_different_bdmgtsn_same_numerics_triggers_update():
    """ID03: bdmgtsn 불일치 — 같은 수치이어도 멱등 생략 불가, UPDATE 실행."""
    other_bdmgtsn = "1168010100103560002"
    factory_other_bn = {
        **_FACTORY_WITH_PK,
        "bdmgtsn": other_bdmgtsn,
    }
    sb = _sb_stub(factory_other_bn)
    with patch("routers.building_register.get_supabase", return_value=sb), \
         patch("routers.building_register.get_current_user", return_value=_user()), \
         patch("routers.building_register._ensure_factory_own"), \
         patch("routers.building_register.fetch_h01_title_for_bdmgtsn",
               return_value=_TITLE_SINGLE), \
         patch("routers.building_register.extract_h01_fields",
               return_value={"mgm_bldrgst_pk": _PK_A, "building_height": 45.0, "floor_count": 10}):
        client = _make_client()
        # 요청 bdmgtsn = _BDMGTSN, DB bdmgtsn = other_bdmgtsn → 불일치
        resp = client.post("/building-register/apply-verified/fac-001",
                           json={"bdmgtsn": _BDMGTSN, "expected_mgm_bldrgst_pk": _PK_A},
                           headers=_auth())
    assert resp.status_code == 200
    assert resp.json()["h01_updated"] is True
    sb.table.return_value.update.assert_called_once()


def test_id04_all_five_conditions_met_skips_update():
    """ID04: 5조건(PK·bdmgtsn·timestamp·height·floor) 전부 충족 → 멱등 생략, UPDATE 0."""
    sb = _sb_stub(_FACTORY_WITH_PK)
    with patch("routers.building_register.get_supabase", return_value=sb), \
         patch("routers.building_register.get_current_user", return_value=_user()), \
         patch("routers.building_register._ensure_factory_own"), \
         patch("routers.building_register.fetch_h01_title_for_bdmgtsn",
               return_value=_TITLE_SINGLE), \
         patch("routers.building_register.extract_h01_fields",
               return_value={"mgm_bldrgst_pk": _PK_A, "building_height": 45.0, "floor_count": 10}):
        client = _make_client()
        resp = client.post("/building-register/apply-verified/fac-001",
                           json={"bdmgtsn": _BDMGTSN, "expected_mgm_bldrgst_pk": _PK_A},
                           headers=_auth())
    assert resp.status_code == 200
    data = resp.json()
    assert data["h01_updated"] is False
    assert data["idempotent"] is True
    sb.table.return_value.update.assert_not_called()


def test_id05_bdmgtsn_mismatch_skips_idempotent():
    """ID05: PK·timestamp·수치 일치이어도 bdmgtsn 다르면 UPDATE 실행."""
    factory_diff_bn = {
        **_FACTORY_WITH_PK,
        "bdmgtsn": "1168010100103560009",
    }
    sb = _sb_stub(factory_diff_bn)
    with patch("routers.building_register.get_supabase", return_value=sb), \
         patch("routers.building_register.get_current_user", return_value=_user()), \
         patch("routers.building_register._ensure_factory_own"), \
         patch("routers.building_register.fetch_h01_title_for_bdmgtsn",
               return_value=_TITLE_SINGLE), \
         patch("routers.building_register.extract_h01_fields",
               return_value={"mgm_bldrgst_pk": _PK_A, "building_height": 45.0, "floor_count": 10}):
        client = _make_client()
        resp = client.post("/building-register/apply-verified/fac-001",
                           json={"bdmgtsn": _BDMGTSN, "expected_mgm_bldrgst_pk": _PK_A},
                           headers=_auth())
    assert resp.status_code == 200
    assert resp.json()["h01_updated"] is True
    sb.table.return_value.update.assert_called_once()


def test_id06_height_changed_skips_idempotent():
    """ID06: bdmgtsn·PK·timestamp·floor 일치이어도 building_height 변경 → UPDATE 실행."""
    sb = _sb_stub(_FACTORY_WITH_PK)
    with patch("routers.building_register.get_supabase", return_value=sb), \
         patch("routers.building_register.get_current_user", return_value=_user()), \
         patch("routers.building_register._ensure_factory_own"), \
         patch("routers.building_register.fetch_h01_title_for_bdmgtsn",
               return_value=_TITLE_SINGLE), \
         patch("routers.building_register.extract_h01_fields",
               return_value={"mgm_bldrgst_pk": _PK_A, "building_height": 50.0, "floor_count": 10}):
        client = _make_client()
        resp = client.post("/building-register/apply-verified/fac-001",
                           json={"bdmgtsn": _BDMGTSN, "expected_mgm_bldrgst_pk": _PK_A},
                           headers=_auth())
    assert resp.status_code == 200
    data = resp.json()
    assert data["h01_updated"] is True
    assert data.get("idempotent") is not True
    sb.table.return_value.update.assert_called_once()


def test_id07_floor_changed_skips_idempotent():
    """ID07: bdmgtsn·PK·timestamp·height 일치이어도 floor_count 변경 → UPDATE 실행."""
    sb = _sb_stub(_FACTORY_WITH_PK)
    with patch("routers.building_register.get_supabase", return_value=sb), \
         patch("routers.building_register.get_current_user", return_value=_user()), \
         patch("routers.building_register._ensure_factory_own"), \
         patch("routers.building_register.fetch_h01_title_for_bdmgtsn",
               return_value=_TITLE_SINGLE), \
         patch("routers.building_register.extract_h01_fields",
               return_value={"mgm_bldrgst_pk": _PK_A, "building_height": 45.0, "floor_count": 12}):
        client = _make_client()
        resp = client.post("/building-register/apply-verified/fac-001",
                           json={"bdmgtsn": _BDMGTSN, "expected_mgm_bldrgst_pk": _PK_A},
                           headers=_auth())
    assert resp.status_code == 200
    data = resp.json()
    assert data["h01_updated"] is True
    assert data.get("idempotent") is not True
    sb.table.return_value.update.assert_called_once()


def test_id08_pk_mismatch_returns_409_idempotency_irrelevant():
    """ID08: 기존 PK(B)와 제출 PK(A) 불일치 → 409, 멱등성 평가 전 차단."""
    factory_pk_b = {
        **_FACTORY_WITH_PK,
        "mgm_bldrgst_pk":               _PK_B,
        "building_register_updated_at": "2026-10-01T10:00:00+09:00",
    }
    sb = _sb_stub(factory_pk_b)
    with patch("routers.building_register.get_supabase", return_value=sb), \
         patch("routers.building_register.get_current_user", return_value=_user()), \
         patch("routers.building_register._ensure_factory_own"):
        client = _make_client()
        resp = client.post("/building-register/apply-verified/fac-001",
                           json={"bdmgtsn": _BDMGTSN, "expected_mgm_bldrgst_pk": _PK_A},
                           headers=_auth())
    assert resp.status_code == 409
    sb.table.return_value.update.assert_not_called()


# ════════════════════════════════════════════════════════════════════════════
# SG01~SG06 — H01 출처 신뢰 경계 + 실제 추출 함수 통합 계약
#   SG01  최초 인증, DB PK 없음 → fetch에 existing_pk=None 전달
#   SG02  기존 확정 PK 있음 → fetch에 existing_pk=DB값 전달
#   SG03  실제 extract_h01_fields, 제출 PK ≠ H01 PK → 409 / UPDATE 0
#   SG04  실제 extract_h01_fields, 복수 본동 중 제출 PK 정확히 1건 일치 → 해당 수치 사용
#   SG05  실제 extract_h01_fields, 주건축물 없음(부속건축물만) → 식별 불가 / UPDATE 0
#   SG06  멱등성 5조건 회귀 — 실제 extract 사용, UPDATE 0 유지
# ════════════════════════════════════════════════════════════════════════════

_TITLE_ATTACHED_ONLY = [
    {
        "mgmBldrgstPk":   _PK_A,
        "mainAtchGbCdNm": "부속건축물",
        "heit":           "10.0",
        "grndFlrCnt":     "2",
    }
]


def test_sg01_first_registration_fetch_called_with_none_existing_pk():
    """SG01: 최초 인증 — DB PK 없음 → fetch에 existing_pk=None 전달.

    사용자 제출 expected_pk를 fetch의 existing_pk로 사용하면
    미확정 PK를 근거로 대체 지번 fallback이 허용되는 결함이 생긴다.
    DB에서 읽은 existing_pk(None)를 전달해야 한다.
    """
    factory_first = {**_FACTORY_BUILDING, "bdmgtsn": None, "mgm_bldrgst_pk": None,
                     "building_register_updated_at": None}
    sb = _sb_stub(factory_first)
    fetch_mock = MagicMock(return_value=_TITLE_SINGLE)
    with patch("routers.building_register.get_supabase", return_value=sb), \
         patch("routers.building_register.get_current_user", return_value=_user()), \
         patch("routers.building_register._ensure_factory_own"), \
         patch("routers.building_register.fetch_h01_title_for_bdmgtsn", fetch_mock), \
         patch("routers.building_register.extract_h01_fields",
               return_value={"mgm_bldrgst_pk": _PK_A, "building_height": 45.0, "floor_count": 10}):
        client = _make_client()
        client.post("/building-register/apply-verified/fac-001",
                    json={"bdmgtsn": _BDMGTSN, "expected_mgm_bldrgst_pk": _PK_A},
                    headers=_auth())
    _, kwargs = fetch_mock.call_args
    assert kwargs.get("existing_pk") is None, (
        f"expected existing_pk=None (DB value), got {kwargs.get('existing_pk')!r}"
    )


def test_sg02_confirmed_pk_fetch_called_with_db_pk():
    """SG02: 기존 확정 PK 있음 → fetch에 DB에서 읽은 existing_pk 전달.

    DB 확정 PK가 있을 때 ji=0000 fallback은 허용된다.
    사용자 제출 expected_pk 대신 DB 값을 전달하는지 확인한다.
    """
    sb = _sb_stub(_FACTORY_WITH_PK)  # existing_pk = _PK_A in DB
    fetch_mock = MagicMock(return_value=_TITLE_SINGLE)
    with patch("routers.building_register.get_supabase", return_value=sb), \
         patch("routers.building_register.get_current_user", return_value=_user()), \
         patch("routers.building_register._ensure_factory_own"), \
         patch("routers.building_register.fetch_h01_title_for_bdmgtsn", fetch_mock), \
         patch("routers.building_register.extract_h01_fields",
               return_value={"mgm_bldrgst_pk": _PK_A, "building_height": 45.0, "floor_count": 10}):
        client = _make_client()
        client.post("/building-register/apply-verified/fac-001",
                    json={"bdmgtsn": _BDMGTSN, "expected_mgm_bldrgst_pk": _PK_A},
                    headers=_auth())
    _, kwargs = fetch_mock.call_args
    assert kwargs.get("existing_pk") == _PK_A, (
        f"expected existing_pk={_PK_A!r} (DB value), got {kwargs.get('existing_pk')!r}"
    )


def test_sg03_real_extract_pk_mismatch_returns_409_no_update():
    """SG03: 실제 extract_h01_fields — 제출 PK(_PK_B) ≠ H01 PK(_PK_A) → 409, UPDATE 0.

    extract_h01_fields Mock 없이 실제 함수 실행.
    H01에는 _PK_A만 있고, 사용자가 _PK_B를 제출하면 extract는 {} 반환 → 409.
    """
    factory_first = {**_FACTORY_BUILDING, "bdmgtsn": None, "mgm_bldrgst_pk": None,
                     "building_register_updated_at": None}
    sb = _sb_stub(factory_first)
    with patch("routers.building_register.get_supabase", return_value=sb), \
         patch("routers.building_register.get_current_user", return_value=_user()), \
         patch("routers.building_register._ensure_factory_own"), \
         patch("routers.building_register.fetch_h01_title_for_bdmgtsn",
               return_value=_TITLE_SINGLE):  # H01에는 _PK_A만 있음
        client = _make_client()
        resp = client.post("/building-register/apply-verified/fac-001",
                           json={"bdmgtsn": _BDMGTSN, "expected_mgm_bldrgst_pk": _PK_B},
                           headers=_auth())
    assert resp.status_code == 409
    sb.table.return_value.update.assert_not_called()


def test_sg04_real_extract_multi_building_exact_pk_match_uses_correct_numerics():
    """SG04: 실제 extract_h01_fields — 복수 본동(_PK_A·_PK_B) 중 _PK_A 정확 1건 일치 → 해당 수치만 사용.

    extract_h01_fields Mock 없이 실제 함수 실행.
    _TITLE_MULTI에서 _PK_A(45m/10층)만 추출되어야 한다.
    """
    factory_first = {**_FACTORY_BUILDING, "bdmgtsn": None, "mgm_bldrgst_pk": None,
                     "building_register_updated_at": None}
    sb = _sb_stub(factory_first)
    with patch("routers.building_register.get_supabase", return_value=sb), \
         patch("routers.building_register.get_current_user", return_value=_user()), \
         patch("routers.building_register._ensure_factory_own"), \
         patch("routers.building_register.fetch_h01_title_for_bdmgtsn",
               return_value=_TITLE_MULTI):  # _PK_A(45m/10층) + _PK_B(20m/5층)
        client = _make_client()
        resp = client.post("/building-register/apply-verified/fac-001",
                           json={"bdmgtsn": _BDMGTSN, "expected_mgm_bldrgst_pk": _PK_A},
                           headers=_auth())
    assert resp.status_code == 200
    data = resp.json()
    assert data["h01_updated"] is True
    assert data["mgm_bldrgst_pk"] == _PK_A
    assert data["building_height"] == 45.0
    assert data["floor_count"] == 10
    # _PK_B 수치(20m/5층)가 혼입됐으면 안 됨
    sb.table.return_value.update.assert_called_once()


def test_sg05_real_extract_no_main_building_unresolvable_no_update():
    """SG05: 실제 extract_h01_fields — 부속건축물만 있어 주건축물 식별 불가 → UPDATE 0.

    extract_h01_fields Mock 없이 실제 함수 실행.
    모든 행이 '부속건축물'이면 extract는 {} 반환 → 409.
    """
    factory_first = {**_FACTORY_BUILDING, "bdmgtsn": None, "mgm_bldrgst_pk": None,
                     "building_register_updated_at": None}
    sb = _sb_stub(factory_first)
    with patch("routers.building_register.get_supabase", return_value=sb), \
         patch("routers.building_register.get_current_user", return_value=_user()), \
         patch("routers.building_register._ensure_factory_own"), \
         patch("routers.building_register.fetch_h01_title_for_bdmgtsn",
               return_value=_TITLE_ATTACHED_ONLY):  # 주건축물 없음
        client = _make_client()
        resp = client.post("/building-register/apply-verified/fac-001",
                           json={"bdmgtsn": _BDMGTSN, "expected_mgm_bldrgst_pk": _PK_A},
                           headers=_auth())
    assert resp.status_code == 409
    sb.table.return_value.update.assert_not_called()


def test_sg06_idempotency_regression_with_real_extract():
    """SG06: 멱등성 5조건 회귀 — 실제 extract_h01_fields 경로에서 UPDATE 0 유지.

    소스 게이트 수정(existing_pk 인자 교정) 후에도 멱등성이 정상 작동해야 한다.
    _FACTORY_WITH_PK(PK_A/45m/10층/타임스탬프 있음) + _TITLE_SINGLE(PK_A) → idempotent=True.
    extract_h01_fields Mock 없이 실제 실행.
    """
    sb = _sb_stub(_FACTORY_WITH_PK)
    with patch("routers.building_register.get_supabase", return_value=sb), \
         patch("routers.building_register.get_current_user", return_value=_user()), \
         patch("routers.building_register._ensure_factory_own"), \
         patch("routers.building_register.fetch_h01_title_for_bdmgtsn",
               return_value=_TITLE_SINGLE):  # PK_A / 45m / 10층
        client = _make_client()
        resp = client.post("/building-register/apply-verified/fac-001",
                           json={"bdmgtsn": _BDMGTSN, "expected_mgm_bldrgst_pk": _PK_A},
                           headers=_auth())
    assert resp.status_code == 200
    data = resp.json()
    assert data["h01_updated"] is False
    assert data["idempotent"] is True
    sb.table.return_value.update.assert_not_called()
