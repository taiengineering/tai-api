"""
B13-SAAS-CON-FNC-001: POST /construction/sites/{site_id}/processes — 건설 공정 등록 계약 검증

검증 목표:
  C1: 인증 없음 → 401
  C2: 타사 site_id → 404 (_ensure_site_own 존재 숨김)
  C3: 정상 등록 → 200, process data 반환

구조:
  _ensure_site_own: construction_sites.company_id 조회 → _ensure_own_company
  create_record: construction_site_processes.insert()

운영 안전:
  monkeypatch + FastAPI TestClient 전용 — 운영 DB/API 미접촉
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.construction_workflow_router as cwf_mod
from routers.auth import get_current_user

_SITE_A_ID = "a0000000-0000-0000-0000-000000000001"
_SITE_B_ID = "b0000000-0000-0000-0000-000000000002"
_PROC_ID   = "c0000000-0000-0000-0000-000000000001"
_CO_A_ID   = "aa000000-0000-0000-0000-000000000001"
_CO_B_ID   = "bb000000-0000-0000-0000-000000000002"

_CALLER = {
    "id":          "usr-b13-con-001",
    "company_id":  _CO_A_ID,
    "role_code":   "010",
    "is_active":   True,
    "status_code": "ACTIVE",
}


def _make_sb(site_company_id: str = _CO_A_ID) -> MagicMock:
    """table-aware 모의: construction_sites / role_data_scope / construction_site_processes."""
    sites_m = MagicMock()
    sites_m.select.return_value.eq.return_value.limit.return_value.execute.return_value = \
        MagicMock(data=[{"id": _SITE_A_ID, "company_id": site_company_id}])

    rds_m = MagicMock()
    rds_m.select.return_value.eq.return_value.limit.return_value.execute.return_value = \
        MagicMock(data=[{"scope_type": "COMPANY"}])

    proc_m = MagicMock()
    proc_m.insert.return_value.execute.return_value = MagicMock(data=[{
        "id":           _PROC_ID,
        "site_id":      _SITE_A_ID,
        "process_name": "흙막이 공사",
        "created_at":   "2026-11-08T00:00:00",
        "updated_at":   "2026-11-08T00:00:00",
    }])

    table_map = {
        "construction_sites":          sites_m,
        "role_data_scope":             rds_m,
        "construction_site_processes": proc_m,
    }

    sb = MagicMock()
    sb.table.side_effect = lambda name: table_map.get(name, MagicMock())
    return sb


def _make_app_with_user(sb: MagicMock) -> TestClient:
    app = FastAPI()
    app.include_router(cwf_mod.router, prefix="/construction")
    app.dependency_overrides[get_current_user] = lambda: _CALLER
    with patch.object(cwf_mod, "get_supabase", return_value=sb):
        return TestClient(app, raise_server_exceptions=False)


# ── C1: 인증 없음 → 401 ──────────────────────────────────────────────

def test_C1_no_auth_401():
    """C1: Authorization 헤더 없음 → get_current_user 401."""
    sb = MagicMock()
    with patch.object(cwf_mod, "get_supabase", return_value=sb):
        app = FastAPI()
        app.include_router(cwf_mod.router, prefix="/construction")
        client = TestClient(app, raise_server_exceptions=False)
        r = client.post(f"/construction/sites/{_SITE_A_ID}/processes",
                        json={"process_name": "흙막이 공사"})
    assert r.status_code == 401, f"예상 401, 실제 {r.status_code}: {r.text}"


# ── C2: 타사 site → 404 ──────────────────────────────────────────────

def test_C2_cross_company_404():
    """C2: 토큰 company_id(_CO_A_ID)와 현장 company_id(_CO_B_ID) 불일치 → 404."""
    sb = _make_sb(site_company_id=_CO_B_ID)
    client = _make_app_with_user(sb)
    with patch.object(cwf_mod, "get_supabase", return_value=sb):
        r = client.post(f"/construction/sites/{_SITE_B_ID}/processes",
                        json={"process_name": "타사 공사"})
    assert r.status_code == 404, f"예상 404 (존재 숨김), 실제 {r.status_code}: {r.text}"


# ── C3: 정상 등록 → 200 ──────────────────────────────────────────────

def test_C3_success_200():
    """C3: 자사 site_id + 유효 토큰 → 200, 공정 data 반환."""
    sb = _make_sb(site_company_id=_CO_A_ID)
    client = _make_app_with_user(sb)
    with patch.object(cwf_mod, "get_supabase", return_value=sb):
        r = client.post(f"/construction/sites/{_SITE_A_ID}/processes",
                        json={"process_name": "흙막이 공사", "is_high_risk": True})
    assert r.status_code == 200, f"예상 200, 실제 {r.status_code}: {r.text}"
    body = r.json()
    assert body["status"] == "success"
    assert "data" in body
    assert body["data"]["id"] == _PROC_ID
