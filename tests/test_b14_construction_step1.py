from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.construction_sites_router as cs_mod
from routers.auth import get_current_user

_SITE_ID = "d0000000-0000-0000-0000-000000000001"
_CO_ID   = "cc000000-0000-0000-0000-000000000001"
_OTHER_CO = "dd000000-0000-0000-0000-000000000002"

_SITE_ROW = {
    "id": _SITE_ID,
    "company_id": _CO_ID,
    "site_name": "도심 현장",
    "site_type": "BUILDING",
    "contract_amount": 100.0,
    "total_workers": 10,
    "safety_manager_required": False,
    "is_active": True,
    "created_at": "2026-11-14T00:00:00",
    "updated_at": "2026-11-14T00:00:00",
}

_CALLER = {
    "id": "user-b14-con",
    "company_id": _CO_ID,
    "role_code": "010",
    "is_active": True,
    "status_code": "ACTIVE",
}
_CALLER_NO_CO = {
    "id": "user-b14-noco",
    "company_id": None,
    "role_code": "010",
    "is_active": True,
    "status_code": "ACTIVE",
}

_VALID_BODY = {
    "site_name": "도심 현장",
    "site_type": "BUILDING",
    "contract_amount": 100.0,
    "total_workers": 10,
}


def _make_sb():
    sites_m = MagicMock()
    sites_m.insert.return_value.execute.return_value = MagicMock(data=[_SITE_ROW])
    sites_m.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data=_SITE_ROW)

    sb = MagicMock()
    sb.table.side_effect = lambda name: sites_m if name == "construction_sites" else MagicMock()
    return sb, sites_m


def _make_app_with_user(sb: MagicMock, caller: dict) -> TestClient:
    app = FastAPI()
    app.include_router(cs_mod.router, prefix="/construction")
    app.dependency_overrides[get_current_user] = lambda: caller
    with patch.object(cs_mod, "get_supabase", return_value=sb):
        return TestClient(app, raise_server_exceptions=False)


# S1: 인증 없음 → 401
def test_S1_no_auth_401():
    sb, _ = _make_sb()
    with patch.object(cs_mod, "get_supabase", return_value=sb):
        app = FastAPI()
        app.include_router(cs_mod.router, prefix="/construction")
        client = TestClient(app, raise_server_exceptions=False)
        r = client.post("/construction/sites", json=_VALID_BODY)
    assert r.status_code == 401, f"예상 401, 실제 {r.status_code}: {r.text}"


# S2: 토큰에 company_id 없음 → 403
def test_S2_no_company_id_403():
    sb, sites_m = _make_sb()
    client = _make_app_with_user(sb, _CALLER_NO_CO)
    with patch.object(cs_mod, "get_supabase", return_value=sb), \
         patch.object(cs_mod, "create_factory_for_site", return_value="factory-01"), \
         patch.object(cs_mod, "auto_diagnose_and_schedule", return_value={}):
        r = client.post("/construction/sites", json=_VALID_BODY)
    assert r.status_code == 403, f"예상 403, 실제 {r.status_code}: {r.text}"
    assert "회사 등록이 필요합니다." in r.json().get("detail", "")


# S3: 정상 토큰 + 유효 데이터 → 200 success
def test_S3_success_200():
    sb, sites_m = _make_sb()
    client = _make_app_with_user(sb, _CALLER)
    with patch.object(cs_mod, "get_supabase", return_value=sb), \
         patch.object(cs_mod, "create_factory_for_site", return_value="factory-01"), \
         patch.object(cs_mod, "auto_diagnose_and_schedule", return_value={}):
        r = client.post("/construction/sites", json=_VALID_BODY)
    assert r.status_code == 200, f"예상 200, 실제 {r.status_code}: {r.text}"
    body = r.json()
    assert body["status"] == "success"
    assert "data" in body


# S4: 응답 data에 site_name과 토큰의 company_id 포함
def test_S4_response_contains_site_name_and_company_id():
    sb, sites_m = _make_sb()
    client = _make_app_with_user(sb, _CALLER)
    with patch.object(cs_mod, "get_supabase", return_value=sb), \
         patch.object(cs_mod, "create_factory_for_site", return_value="factory-01"), \
         patch.object(cs_mod, "auto_diagnose_and_schedule", return_value={}):
        r = client.post("/construction/sites", json=_VALID_BODY)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["site_name"] == "도심 현장"
    assert data["company_id"] == _CO_ID


# S5: body의 company_id는 무시 — 서버는 토큰의 company_id를 사용
def test_S5_body_company_id_ignored():
    sb, sites_m = _make_sb()
    client = _make_app_with_user(sb, _CALLER)
    body_with_other_co = {**_VALID_BODY, "company_id": _OTHER_CO}
    with patch.object(cs_mod, "get_supabase", return_value=sb), \
         patch.object(cs_mod, "create_factory_for_site", return_value="factory-01"), \
         patch.object(cs_mod, "auto_diagnose_and_schedule", return_value={}):
        r = client.post("/construction/sites", json=body_with_other_co)
    assert r.status_code == 200
    # insert에 전달된 데이터에서 company_id 확인
    call_args = sites_m.insert.call_args
    inserted = call_args[0][0]
    assert inserted["company_id"] == _CO_ID, (
        f"토큰 company_id({_CO_ID})가 사용돼야 하나 실제: {inserted['company_id']}"
    )


# S6: create_factory_for_site와 auto_diagnose_and_schedule 각 1회 호출
def test_S6_factory_and_diagnose_called_once():
    sb, sites_m = _make_sb()
    client = _make_app_with_user(sb, _CALLER)
    with patch.object(cs_mod, "get_supabase", return_value=sb), \
         patch.object(cs_mod, "create_factory_for_site", return_value="factory-01") as mock_factory, \
         patch.object(cs_mod, "auto_diagnose_and_schedule", return_value={}) as mock_auto:
        r = client.post("/construction/sites", json=_VALID_BODY)
    assert r.status_code == 200
    mock_factory.assert_called_once()
    mock_auto.assert_called_once()
