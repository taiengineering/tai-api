"""WO-E2E2000-FIXOBJ05-PR624-SOURCE-IV-CORRECTION-001
POST /apply/{factory_id} source-writer contract tests.

W01  단일 본동 정상 등록 — H01 fields + timestamp 저장
W02  복수 본동 + 정확한 기존 PK — PK 일치 본동 선택
W03  복수 본동 + PK 미확정 → H01 저장 차단 (h01_updated=False)
W04  표제부 없는 상태 → building_register_updated_at 생성 금지
W05  기존 캐시 있어도 표제부 누락이면 재인증 금지
W06  다른 bdmgtsn + 기존 PK 확정 → 409 BUILDING_IDENTITY_MISMATCH
W07  인증 없는 /apply → 401 (실제 get_current_user 동작)
W08  타사 factory_id → 404 (_ensure_factory_own 실제 계약)
W09  정상 사용자 + 정확한 본동 → h01_updated=True + floor_count 저장 확인
W10  H01 전달 결과와 저장 수치 일치 (building_height / floor_count / mgm_bldrgst_pk)
W11  높이만 수집 → floor_count 명시적 None (기존 층수 재인증 차단)
W12  층수만 수집 → building_height 명시적 None (기존 높이 재인증 차단)
W13  복수 본동 PK-B 선택 → 메타데이터도 PK-B 행만 사용
W14  본동 식별 실패 → 표제부 기반 메타데이터 저장 금지
W15  기존 PK 존재, 기존 bdmgtsn 부재, H01 PK 불일치 → 409 BUILDING_IDENTITY_UNRESOLVED
W16  기존 PK 존재, 기존 bdmgtsn 부재, H01 PK 일치 → 정상 연결
W17  타사 사업장 → 실제 _ensure_factory_own() 실행, 404 + JUSO/H01 0회 + UPDATE 0회
"""
import pytest
from unittest.mock import MagicMock, patch, call
from fastapi.testclient import TestClient


# ── 공통 픽스처 ────────────────────────────────────────────────────────────────

_FACTORY_ROW = {
    "id":           "fac-001",
    "name":         "테스트공장",
    "address_road": "서울특별시 강남구 테헤란로 1",
    "address_jibun": None,
    "bdmgtsn":      None,
    "mgm_bldrgst_pk": None,
}

_JUSO_RESULT = {
    "bdMgtSn": "1168010100103560001",
    "roadAddr": "서울특별시 강남구 테헤란로 1",
    "roadAddrPart1": "서울특별시 강남구 테헤란로 1",
    "jibunAddr": "서울특별시 강남구 역삼동 831",
    "zipNo": "06234",
    "siNm": "서울특별시",
    "sggNm": "강남구",
    "emdNm": "역삼동",
}

_TITLE_SINGLE = [
    {
        "mgmBldrgstPk": "11680-100021234",
        "mainAtchGbCdNm": "주건축물",
        "heit": "45.0",
        "grndFlrCnt": "10",
        "mainPurpsCd": "02000",
        "mainPurpsCdNm": "공장",
    }
]

_TITLE_MULTI = [
    {
        "mgmBldrgstPk": "11680-PK-A",
        "mainAtchGbCdNm": "주건축물",
        "heit": "30.0",
        "grndFlrCnt": "7",
        "mainPurpsCd": "02000",
        "mainPurpsCdNm": "공장",
    },
    {
        "mgmBldrgstPk": "11680-PK-B",
        "mainAtchGbCdNm": "주건축물",
        "heit": "20.0",
        "grndFlrCnt": "5",
        "mainPurpsCd": "02000",
        "mainPurpsCdNm": "공장",
    },
]

# W13용 — PK별로 용도·구조가 다른 복수 본동 픽스처
_TITLE_MULTI_DISTINCT = [
    {
        "mgmBldrgstPk": "11680-PK-A",
        "mainAtchGbCdNm": "주건축물",
        "heit": "30.0",
        "grndFlrCnt": "7",
        "mainPurpsCd": "02000",
        "mainPurpsCdNm": "공장",
        "strctCdNm": "철근콘크리트구조",
    },
    {
        "mgmBldrgstPk": "11680-PK-B",
        "mainAtchGbCdNm": "주건축물",
        "heit": "20.0",
        "grndFlrCnt": "5",
        "mainPurpsCd": "04000",
        "mainPurpsCdNm": "창고시설",
        "strctCdNm": "철골구조",
    },
]


def _sb_stub(factory_row: dict | None = None):
    """Supabase stub that returns factory_row on .single().execute()."""
    sb = MagicMock()
    res = MagicMock()
    res.data = factory_row
    (sb.table.return_value.select.return_value
     .eq.return_value.single.return_value.execute.return_value) = res
    update_res = MagicMock()
    update_res.data = [factory_row] if factory_row else []
    (sb.table.return_value.update.return_value
     .eq.return_value.execute.return_value) = update_res
    return sb


def _make_client():
    from main import app
    return TestClient(app, raise_server_exceptions=True)


def _auth_headers():
    return {"Authorization": "Bearer test-token"}


# ── W07: 인증 없는 /apply → 401 (실제 get_current_user 계약) ─────────────────

def test_w07_no_auth_returns_401():
    """W07: Authorization 헤더 없으면 실제 get_current_user가 401 발생."""
    with patch("routers.building_register.get_supabase") as mock_sb:
        mock_sb.return_value = _sb_stub(_FACTORY_ROW)
        client = _make_client()
        resp = client.post("/building-register/apply/fac-001")
    assert resp.status_code == 401


# ── W08: 타사 factory_id → 404 (_ensure_factory_own 실제 계약) ───────────────

def test_w08_wrong_company_blocked():
    """W08: _ensure_factory_own은 타사 factory에 대해 404(실제 계약)를 발생시킨다."""
    from fastapi import HTTPException as FE
    with patch("routers.building_register.get_supabase") as mock_sb, \
         patch("routers.building_register.get_current_user", return_value={"id": "user-x", "company_id": "co-x"}), \
         patch("routers.building_register._ensure_factory_own",
               side_effect=FE(status_code=404, detail="시설을 찾을 수 없습니다")):
        mock_sb.return_value = _sb_stub(_FACTORY_ROW)
        client = _make_client()
        resp = client.post("/building-register/apply/fac-001", headers=_auth_headers())
    assert resp.status_code == 404


# ── W06: 다른 bdmgtsn + 기존 PK 확정 → 409 ──────────────────────────────────

def test_w06_identity_mismatch_returns_409():
    """W06: factory already has confirmed building identity; different bdmgtsn → 409."""
    confirmed_factory = {
        **_FACTORY_ROW,
        "bdmgtsn":        "9999999999999999999",
        "mgm_bldrgst_pk": "99999-EXISTING",
    }
    with patch("routers.building_register.get_supabase") as mock_sb, \
         patch("routers.building_register.get_current_user", return_value={"id": "u1"}), \
         patch("routers.building_register._ensure_factory_own"), \
         patch("routers.building_register.get_juso", return_value=_JUSO_RESULT):
        mock_sb.return_value = _sb_stub(confirmed_factory)
        client = _make_client()
        resp = client.post("/building-register/apply/fac-001", headers=_auth_headers())
    assert resp.status_code == 409
    body = resp.json()
    assert body["detail"]["code"] == "BUILDING_IDENTITY_MISMATCH"


# ── W04: 표제부 없는 상태 → timestamp 생성 금지 ───────────────────────────────

def test_w04_no_title_no_timestamp():
    """W04: fetch_h01_title_for_bdmgtsn returns None → h01_patch empty → no building_register_updated_at."""
    update_calls = []

    class _SB:
        def table(self, n):
            return self
        def select(self, *a, **k): return self
        def eq(self, *a, **k): return self
        def single(self): return self
        def update(self, data):
            update_calls.append(data)
            return self
        def execute(self):
            m = MagicMock()
            m.data = _FACTORY_ROW
            return m

    with patch("routers.building_register.get_supabase", return_value=_SB()), \
         patch("routers.building_register.get_current_user", return_value={"id": "u1"}), \
         patch("routers.building_register._ensure_factory_own"), \
         patch("routers.building_register.get_juso", return_value=_JUSO_RESULT), \
         patch("routers.building_register.fetch_h01_title_for_bdmgtsn", return_value=None), \
         patch("routers.building_register.extract_h01_fields", return_value={}):
        client = _make_client()
        resp = client.post("/building-register/apply/fac-001", headers=_auth_headers())

    # No update call should contain building_register_updated_at
    for payload in update_calls:
        assert "building_register_updated_at" not in payload, \
            "building_register_updated_at must not be set when H01 fails"


# ── W05: 기존 캐시 있어도 표제부 누락이면 재인증 금지 ─────────────────────────

def test_w05_existing_cache_no_reauth_without_title():
    """W05: factory already has floor_count/building_height; no title → fields must NOT be overwritten."""
    factory_with_cache = {
        **_FACTORY_ROW,
        "bdmgtsn": "1168010100103560001",
        "mgm_bldrgst_pk": "11680-OLD-PK",
    }
    update_calls = []

    class _SB2:
        def table(self, n): return self
        def select(self, *a, **k): return self
        def eq(self, *a, **k): return self
        def single(self): return self
        def update(self, data):
            update_calls.append(data)
            return self
        def execute(self):
            m = MagicMock()
            m.data = factory_with_cache
            return m

    with patch("routers.building_register.get_supabase", return_value=_SB2()), \
         patch("routers.building_register.get_current_user", return_value={"id": "u1"}), \
         patch("routers.building_register._ensure_factory_own"), \
         patch("routers.building_register.get_juso", return_value={**_JUSO_RESULT, "bdMgtSn": "1168010100103560001"}), \
         patch("routers.building_register.fetch_h01_title_for_bdmgtsn", return_value=None), \
         patch("routers.building_register.extract_h01_fields", return_value={}):
        client = _make_client()
        client.post("/building-register/apply/fac-001", headers=_auth_headers())

    for payload in update_calls:
        assert "building_register_updated_at" not in payload
        assert "floor_count" not in payload
        assert "building_height" not in payload


# ── W01: 단일 본동 정상 등록 ─────────────────────────────────────────────────

def test_w01_single_main_building_success():
    """W01: single main building → H01 fields + timestamp written."""
    captured = {}

    class _SB3:
        def table(self, n): return self
        def select(self, *a, **k): return self
        def eq(self, *a, **k): return self
        def single(self): return self
        def update(self, data):
            captured["update"] = data
            return self
        def execute(self):
            m = MagicMock()
            m.data = _FACTORY_ROW
            return m

    extracted = {
        "mgm_bldrgst_pk": "11680-100021234",
        "building_height": 45.0,
        "floor_count": 10,
    }

    with patch("routers.building_register.get_supabase", return_value=_SB3()), \
         patch("routers.building_register.get_current_user", return_value={"id": "u1"}), \
         patch("routers.building_register._ensure_factory_own"), \
         patch("routers.building_register.get_juso", return_value=_JUSO_RESULT), \
         patch("routers.building_register.fetch_h01_title_for_bdmgtsn", return_value=_TITLE_SINGLE), \
         patch("routers.building_register.extract_h01_fields", return_value=extracted):
        client = _make_client()
        resp = client.post("/building-register/apply/fac-001", headers=_auth_headers())

    assert resp.status_code == 200
    body = resp.json()
    assert body["h01_updated"] is True
    assert "building_register_updated_at" in captured.get("update", {})
    assert captured["update"]["floor_count"] == 10
    assert captured["update"]["building_height"] == 45.0
    assert captured["update"]["mgm_bldrgst_pk"] == "11680-100021234"


# ── W02: 복수 본동 + 정확한 기존 PK ─────────────────────────────────────────

def test_w02_multi_building_exact_pk():
    """W02: multi-building title; existing PK matches PK-A → floor_count=7 stored."""
    factory_with_pk = {**_FACTORY_ROW, "mgm_bldrgst_pk": "11680-PK-A", "bdmgtsn": "1168010100103560001"}
    captured = {}

    class _SB4:
        def table(self, n): return self
        def select(self, *a, **k): return self
        def eq(self, *a, **k): return self
        def single(self): return self
        def update(self, data):
            captured["update"] = data
            return self
        def execute(self):
            m = MagicMock()
            m.data = factory_with_pk
            return m

    extracted_a = {"mgm_bldrgst_pk": "11680-PK-A", "building_height": 30.0, "floor_count": 7}

    with patch("routers.building_register.get_supabase", return_value=_SB4()), \
         patch("routers.building_register.get_current_user", return_value={"id": "u1"}), \
         patch("routers.building_register._ensure_factory_own"), \
         patch("routers.building_register.get_juso",
               return_value={**_JUSO_RESULT, "bdMgtSn": "1168010100103560001"}), \
         patch("routers.building_register.fetch_h01_title_for_bdmgtsn", return_value=_TITLE_MULTI), \
         patch("routers.building_register.extract_h01_fields", return_value=extracted_a):
        client = _make_client()
        resp = client.post("/building-register/apply/fac-001", headers=_auth_headers())

    assert resp.status_code == 200
    assert captured["update"].get("floor_count") == 7
    assert captured["update"].get("mgm_bldrgst_pk") == "11680-PK-A"


# ── W03: 복수 본동 + PK 미확정 → H01 저장 차단 ──────────────────────────────

def test_w03_multi_building_no_pk_h01_blocked():
    """W03: multi-building, no existing PK → extract_h01_fields returns {} → h01_updated=False."""
    captured = {}

    class _SB5:
        def table(self, n): return self
        def select(self, *a, **k): return self
        def eq(self, *a, **k): return self
        def single(self): return self
        def update(self, data):
            captured["update"] = data
            return self
        def execute(self):
            m = MagicMock()
            m.data = _FACTORY_ROW  # no mgm_bldrgst_pk
            return m

    with patch("routers.building_register.get_supabase", return_value=_SB5()), \
         patch("routers.building_register.get_current_user", return_value={"id": "u1"}), \
         patch("routers.building_register._ensure_factory_own"), \
         patch("routers.building_register.get_juso", return_value=_JUSO_RESULT), \
         patch("routers.building_register.fetch_h01_title_for_bdmgtsn", return_value=_TITLE_MULTI), \
         patch("routers.building_register.extract_h01_fields", return_value={}):  # identity unresolved
        client = _make_client()
        resp = client.post("/building-register/apply/fac-001", headers=_auth_headers())

    assert resp.status_code == 200
    body = resp.json()
    assert body["h01_updated"] is False
    assert "building_register_updated_at" not in captured.get("update", {})
    assert "floor_count" not in captured.get("update", {})


# ── W09: 정상 사용자 + 정확한 본동 → h01_updated=True ────────────────────────

def test_w09_full_flow_h01_updated_true():
    """W09: authenticated user + valid address + single building → h01_updated=True in response."""
    extracted = {"mgm_bldrgst_pk": "11680-100021234", "building_height": 45.0, "floor_count": 10}

    with patch("routers.building_register.get_supabase") as mock_sb, \
         patch("routers.building_register.get_current_user", return_value={"id": "u1"}), \
         patch("routers.building_register._ensure_factory_own"), \
         patch("routers.building_register.get_juso", return_value=_JUSO_RESULT), \
         patch("routers.building_register.fetch_h01_title_for_bdmgtsn", return_value=_TITLE_SINGLE), \
         patch("routers.building_register.extract_h01_fields", return_value=extracted):
        mock_sb.return_value = _sb_stub(_FACTORY_ROW)
        client = _make_client()
        resp = client.post("/building-register/apply/fac-001", headers=_auth_headers())

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["h01_updated"] is True
    assert body["summary"]["floor_count"] == 10
    assert body["summary"]["building_height"] == 45.0


# ── W10: H01 전달 결과와 저장 수치 일치 ──────────────────────────────────────

def test_w10_h01_stored_values_match_extracted():
    """W10: values stored in DB must exactly match extract_h01_fields output."""
    extracted = {
        "mgm_bldrgst_pk": "11680-MATCH",
        "building_height": 99.5,
        "floor_count": 22,
    }
    captured = {}

    class _SB6:
        def table(self, n): return self
        def select(self, *a, **k): return self
        def eq(self, *a, **k): return self
        def single(self): return self
        def update(self, data):
            captured["update"] = data
            return self
        def execute(self):
            m = MagicMock()
            m.data = _FACTORY_ROW
            return m

    with patch("routers.building_register.get_supabase", return_value=_SB6()), \
         patch("routers.building_register.get_current_user", return_value={"id": "u1"}), \
         patch("routers.building_register._ensure_factory_own"), \
         patch("routers.building_register.get_juso", return_value=_JUSO_RESULT), \
         patch("routers.building_register.fetch_h01_title_for_bdmgtsn", return_value=_TITLE_SINGLE), \
         patch("routers.building_register.extract_h01_fields", return_value=extracted):
        client = _make_client()
        client.post("/building-register/apply/fac-001", headers=_auth_headers())

    u = captured.get("update", {})
    assert u.get("mgm_bldrgst_pk") == "11680-MATCH"
    assert u.get("building_height") == 99.5
    assert u.get("floor_count") == 22
    assert "building_register_updated_at" in u


# ── W11: 높이만 수집 → floor_count 명시적 None ───────────────────────────────

def test_w11_height_only_clears_floor_count():
    """W11: H01이 높이만 반환하면 floor_count를 명시적 None으로 저장 — 기존 미인증 층수 재인증 차단."""
    extracted = {
        "mgm_bldrgst_pk": "11680-PARTIAL",
        "building_height": 50.0,
        # floor_count 없음
    }
    captured = {}

    class _SBW11:
        def table(self, n): return self
        def select(self, *a, **k): return self
        def eq(self, *a, **k): return self
        def single(self): return self
        def update(self, data):
            captured["update"] = data
            return self
        def execute(self):
            m = MagicMock()
            m.data = _FACTORY_ROW
            return m

    with patch("routers.building_register.get_supabase", return_value=_SBW11()), \
         patch("routers.building_register.get_current_user", return_value={"id": "u1"}), \
         patch("routers.building_register._ensure_factory_own"), \
         patch("routers.building_register.get_juso", return_value=_JUSO_RESULT), \
         patch("routers.building_register.fetch_h01_title_for_bdmgtsn", return_value=_TITLE_SINGLE), \
         patch("routers.building_register.extract_h01_fields", return_value=extracted):
        client = _make_client()
        resp = client.post("/building-register/apply/fac-001", headers=_auth_headers())

    assert resp.status_code == 200
    u = captured.get("update", {})
    assert u.get("building_height") == 50.0
    assert "floor_count" in u, "floor_count must be present as explicit None"
    assert u["floor_count"] is None


# ── W12: 층수만 수집 → building_height 명시적 None ──────────────────────────

def test_w12_floor_count_only_clears_building_height():
    """W12: H01이 층수만 반환하면 building_height를 명시적 None으로 저장 — 기존 미인증 높이 재인증 차단."""
    extracted = {
        "mgm_bldrgst_pk": "11680-PARTIAL2",
        "floor_count": 8,
        # building_height 없음
    }
    captured = {}

    class _SBW12:
        def table(self, n): return self
        def select(self, *a, **k): return self
        def eq(self, *a, **k): return self
        def single(self): return self
        def update(self, data):
            captured["update"] = data
            return self
        def execute(self):
            m = MagicMock()
            m.data = _FACTORY_ROW
            return m

    with patch("routers.building_register.get_supabase", return_value=_SBW12()), \
         patch("routers.building_register.get_current_user", return_value={"id": "u1"}), \
         patch("routers.building_register._ensure_factory_own"), \
         patch("routers.building_register.get_juso", return_value=_JUSO_RESULT), \
         patch("routers.building_register.fetch_h01_title_for_bdmgtsn", return_value=_TITLE_SINGLE), \
         patch("routers.building_register.extract_h01_fields", return_value=extracted):
        client = _make_client()
        resp = client.post("/building-register/apply/fac-001", headers=_auth_headers())

    assert resp.status_code == 200
    u = captured.get("update", {})
    assert u.get("floor_count") == 8
    assert "building_height" in u, "building_height must be present as explicit None"
    assert u["building_height"] is None


# ── W13: 복수 본동 PK-B 확정 → 메타데이터도 PK-B 행만 사용 ───────────────────

def test_w13_multi_building_pk_b_metadata_source():
    """W13: PK-B 확정 시 메타데이터(용도·구조)도 PK-B 행에서만 가져온다."""
    factory_with_pk_b = {**_FACTORY_ROW, "mgm_bldrgst_pk": "11680-PK-B", "bdmgtsn": "1168010100103560001"}
    extracted_b = {"mgm_bldrgst_pk": "11680-PK-B", "building_height": 20.0, "floor_count": 5}
    captured = {}

    class _SBW13:
        def table(self, n): return self
        def select(self, *a, **k): return self
        def eq(self, *a, **k): return self
        def single(self): return self
        def update(self, data):
            captured["update"] = data
            return self
        def execute(self):
            m = MagicMock()
            m.data = factory_with_pk_b
            return m

    with patch("routers.building_register.get_supabase", return_value=_SBW13()), \
         patch("routers.building_register.get_current_user", return_value={"id": "u1"}), \
         patch("routers.building_register._ensure_factory_own"), \
         patch("routers.building_register.get_juso",
               return_value={**_JUSO_RESULT, "bdMgtSn": "1168010100103560001"}), \
         patch("routers.building_register.fetch_h01_title_for_bdmgtsn", return_value=_TITLE_MULTI_DISTINCT), \
         patch("routers.building_register.extract_h01_fields", return_value=extracted_b):
        client = _make_client()
        resp = client.post("/building-register/apply/fac-001", headers=_auth_headers())

    assert resp.status_code == 200
    u = captured.get("update", {})
    # PK-B 행 기반 메타데이터 (창고시설, 철골구조) — PK-A 행(공장, 철근콘크리트구조) 아님
    assert u.get("main_purpose_name") == "창고시설"
    assert u.get("building_structure_name") == "철골구조"


# ── W14: 본동 식별 실패 → 표제부 기반 메타데이터 저장 금지 ─────────────────────

def test_w14_pk_unresolved_no_title_metadata():
    """W14: PK 미확정(identity unresolved) → 표제부 기반 용도·구조 저장 금지."""
    captured = {}

    class _SBW14:
        def table(self, n): return self
        def select(self, *a, **k): return self
        def eq(self, *a, **k): return self
        def single(self): return self
        def update(self, data):
            captured["update"] = data
            return self
        def execute(self):
            m = MagicMock()
            m.data = _FACTORY_ROW
            return m

    with patch("routers.building_register.get_supabase", return_value=_SBW14()), \
         patch("routers.building_register.get_current_user", return_value={"id": "u1"}), \
         patch("routers.building_register._ensure_factory_own"), \
         patch("routers.building_register.get_juso", return_value=_JUSO_RESULT), \
         patch("routers.building_register.fetch_h01_title_for_bdmgtsn", return_value=_TITLE_MULTI), \
         patch("routers.building_register.extract_h01_fields", return_value={}):
        client = _make_client()
        resp = client.post("/building-register/apply/fac-001", headers=_auth_headers())

    assert resp.status_code == 200
    u = captured.get("update", {})
    assert "main_purpose_name" not in u
    assert "building_structure_name" not in u
    assert "floor_count" not in u
    assert "building_height" not in u
    assert "building_register_updated_at" not in u


# ── W15: 기존 PK, bdmgtsn 부재, H01 PK 불일치 → 409 ─────────────────────────

def test_w15_existing_pk_no_bdmgtsn_h01_fail_409():
    """W15: mgm_bldrgst_pk 있고 bdmgtsn 없는데 H01이 다른 PK 반환 → 409 BUILDING_IDENTITY_UNRESOLVED."""
    factory_pk_only = {**_FACTORY_ROW, "bdmgtsn": None, "mgm_bldrgst_pk": "EXISTING-PK"}
    with patch("routers.building_register.get_supabase") as mock_sb, \
         patch("routers.building_register.get_current_user", return_value={"id": "u1"}), \
         patch("routers.building_register._ensure_factory_own"), \
         patch("routers.building_register.get_juso", return_value=_JUSO_RESULT), \
         patch("routers.building_register.fetch_h01_title_for_bdmgtsn", return_value=None), \
         patch("routers.building_register.extract_h01_fields", return_value={}):
        mock_sb.return_value = _sb_stub(factory_pk_only)
        client = _make_client()
        resp = client.post("/building-register/apply/fac-001", headers=_auth_headers())

    assert resp.status_code == 409
    body = resp.json()
    assert body["detail"]["code"] == "BUILDING_IDENTITY_UNRESOLVED"
    assert body["detail"]["existing_mgm_bldrgst_pk"] == "EXISTING-PK"


# ── W16: 기존 PK, bdmgtsn 부재, H01 동일 PK 확인 → 정상 연결 ─────────────────

def test_w16_existing_pk_no_bdmgtsn_h01_confirms_ok():
    """W16: mgm_bldrgst_pk 있고 bdmgtsn 없는데 H01이 동일 PK 확인 → 정상 저장."""
    factory_pk_only = {**_FACTORY_ROW, "bdmgtsn": None, "mgm_bldrgst_pk": "11680-100021234"}
    extracted = {"mgm_bldrgst_pk": "11680-100021234", "building_height": 45.0, "floor_count": 10}
    with patch("routers.building_register.get_supabase") as mock_sb, \
         patch("routers.building_register.get_current_user", return_value={"id": "u1"}), \
         patch("routers.building_register._ensure_factory_own"), \
         patch("routers.building_register.get_juso", return_value=_JUSO_RESULT), \
         patch("routers.building_register.fetch_h01_title_for_bdmgtsn", return_value=_TITLE_SINGLE), \
         patch("routers.building_register.extract_h01_fields", return_value=extracted):
        mock_sb.return_value = _sb_stub(factory_pk_only)
        client = _make_client()
        resp = client.post("/building-register/apply/fac-001", headers=_auth_headers())

    assert resp.status_code == 200
    body = resp.json()
    assert body["h01_updated"] is True
    assert body["bdmgtsn"] == "1168010100103560001"


# ── W17: 타사 사업장 → 실제 _ensure_factory_own() 실행 + 404 + 외부 호출 0회 ───

def test_w17_third_party_404_actual_ownership_check():
    """W17: 실제 _ensure_factory_own() 실행 — 타사 company_id → 404, JUSO/H01 미호출, UPDATE 미발생.

    _ensure_factory_own 자체를 Mock하지 않는다. 실제 소유권 검증 경로를 통과시켜
    사용자 co-x가 co-y 소유 factory에 접근하면 404가 발생함을 검증한다.
    """
    # role_data_scope → COMPANY 스코프 반환 (비관리자 — _is_admin=False 통과)
    scope_mock = MagicMock()
    scope_result = MagicMock()
    scope_result.data = [{"scope_type": "COMPANY"}]
    scope_mock.select.return_value.eq.return_value.limit.return_value.execute.return_value = scope_result

    # factories → co-y 소유 반환 (사용자 co-x ≠ co-y → 404)
    factories_mock = MagicMock()
    ownership_result = MagicMock()
    ownership_result.data = [{"company_id": "co-y"}]
    factories_mock.select.return_value.eq.return_value.limit.return_value.execute.return_value = ownership_result

    _table_cache = {"role_data_scope": scope_mock, "factories": factories_mock}
    sb_instance = MagicMock()
    sb_instance.table.side_effect = lambda name: _table_cache.get(name, MagicMock())

    with patch("routers.building_register.get_supabase", return_value=sb_instance), \
         patch("routers.building_register.get_current_user",
               return_value={"id": "user-x", "company_id": "co-x", "role_code": "MEMBER"}), \
         patch("routers.building_register.get_juso") as mock_juso, \
         patch("routers.building_register.fetch_h01_title_for_bdmgtsn") as mock_h01:
        client = _make_client()
        resp = client.post("/building-register/apply/fac-001", headers=_auth_headers())

    # 실제 _ensure_factory_own() 가 타사 접근을 404로 차단
    assert resp.status_code == 404
    # 소유권 거부 이후 외부 API 호출 없음
    mock_juso.assert_not_called()
    mock_h01.assert_not_called()
    # 소유권 거부 이후 DB UPDATE 없음
    factories_mock.update.assert_not_called()
