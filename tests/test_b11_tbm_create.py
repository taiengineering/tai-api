"""
B11-EDU-FNC-002: POST /tbm — TBM 작성 계약 검증

검증 목표:
  T1: 인증 없음 → 401
  T2: 정상 생성 → 200, data.id 반환
  T3a: factory_id/construction_site_id 모두 없음 → 400
  T3b: work_date 누락 → 422 (Pydantic 필드 검증)
  T4: 비-관리자가 body에 타사 company_id 주입 → 토큰 company_id로 강제 덮어씀

정정 사항 (GPT R1):
  - conductor_id는 body에서 수신 (토큰에서 오지 않음)
  - factory/site 모두 없으면 400, work_date 누락이면 422
  - company_id 격리: require_company_id()가 body 주입 무효화

운영 안전:
  monkeypatch + FastAPI TestClient 전용 — 운영 DB/API 미접촉
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.tbm as tbm_mod
from routers.auth import get_current_user

_FAC_ID   = "fac-b11-0001-0000-000000000001"
_TBM_ID   = "tbm-b11-0001-0000-000000000001"
_CO_A_ID  = "co-aaaa-0000-0000-0000-000000000001"
_CO_B_ID  = "co-bbbb-0000-0000-0000-000000000002"

_CALLER = {
    "id":          "usr-b11-0001",
    "company_id":  _CO_A_ID,
    "factory_id":  _FAC_ID,
    "role_code":   "010",
    "is_active":   True,
    "status_code": "ACTIVE",
}


def _make_sb_for_create(*, inject_company_id: str | None = None) -> MagicMock:
    """
    create_tbm 경로에서 호출되는 Supabase 체인을 모의.

    모든 SELECT 체인은 동일 mock을 반환하므로,
    {"scope_type": "COMPANY", "company_id": _CO_A_ID} 를 담아
    role_data_scope / factories 쿼리 모두 처리.
    """
    sb = MagicMock()

    # SELECT 체인 (role_data_scope + factories 조회 공통)
    sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = \
        MagicMock(data=[{"scope_type": "COMPANY", "company_id": _CO_A_ID}])

    # INSERT 체인 — tbm_meetings
    captured: dict = {}

    def _capture_insert(row: dict):
        captured["row"] = row
        m = MagicMock()
        m.execute.return_value = MagicMock(data=[{"id": _TBM_ID, **row}])
        return m

    sb.table.return_value.insert.side_effect = _capture_insert

    # 호출 측에서 captured 에 접근할 수 있도록 sb 에 첨부
    sb._captured = captured
    return sb


def _make_app_with_user(sb: MagicMock) -> TestClient:
    app = FastAPI()
    app.include_router(tbm_mod.router)
    app.dependency_overrides[get_current_user] = lambda: _CALLER
    with patch.object(tbm_mod, "get_supabase", return_value=sb):
        return TestClient(app, raise_server_exceptions=False)


# ── T1: 인증 없음 → 401 ──────────────────────────────────────────────────────

def test_T1_no_auth_401():
    """T1: Authorization 헤더 없음 → get_current_user가 401 발생."""
    sb = MagicMock()
    # Supabase 없이도 Depends 에서 단락되므로 get_supabase 불필요
    with patch.object(tbm_mod, "get_supabase", return_value=sb):
        app = FastAPI()
        app.include_router(tbm_mod.router)
        # dependency_overrides 없음 → 실제 get_current_user 실행 → 401
        client = TestClient(app, raise_server_exceptions=False)
        r = client.post("/tbm", json={"work_date": "2026-11-08", "factory_id": _FAC_ID})
    assert r.status_code == 401


# ── T2: 정상 생성 → 200, data.id 반환 ───────────────────────────────────────

def test_T2_success_200_data_id():
    """T2: factory_id + work_date 제공, 인증 완료 → 200, data.id 존재."""
    sb = _make_sb_for_create()
    client = _make_app_with_user(sb)
    with patch.object(tbm_mod, "get_supabase", return_value=sb):
        r = client.post(
            "/tbm",
            json={
                "factory_id": _FAC_ID,
                "work_date":  "2026-11-08",
                "work_location": "1라인",
            },
        )
    assert r.status_code == 200, f"예상 200, 실제 {r.status_code}: {r.text}"
    body = r.json()
    assert body["status"] == "success"
    assert body["data"]["id"] == _TBM_ID


# ── T3a: 사업장·현장 모두 없음 → 400 ─────────────────────────────────────────

def test_T3a_no_factory_no_site_400():
    """T3a: factory_id=None AND construction_site_id=None → 400 (시설 또는 현장을 지정하세요)."""
    sb = _make_sb_for_create()
    client = _make_app_with_user(sb)
    with patch.object(tbm_mod, "get_supabase", return_value=sb):
        r = client.post(
            "/tbm",
            json={"work_date": "2026-11-08"},  # factory/site 모두 없음
        )
    assert r.status_code == 400, f"예상 400, 실제 {r.status_code}: {r.text}"


# ── T3b: work_date 누락 → 422 ─────────────────────────────────────────────

def test_T3b_missing_work_date_422():
    """T3b: work_date(필수 필드) 누락 → Pydantic 422 검증 오류."""
    sb = _make_sb_for_create()
    client = _make_app_with_user(sb)
    with patch.object(tbm_mod, "get_supabase", return_value=sb):
        r = client.post(
            "/tbm",
            json={"factory_id": _FAC_ID},  # work_date 없음
        )
    assert r.status_code == 422, f"예상 422, 실제 {r.status_code}: {r.text}"


# ── T4: body company_id 주입 → require_company_id가 토큰 company_id로 강제 ──

def test_T4_body_company_id_injection_blocked():
    """T4: 비-관리자(role_code=010)가 타사 company_id 주입 → 토큰 company_id(_CO_A_ID)로 덮어씀.

    require_company_id(current, supabase) 가 비-ALL 사용자는 body 값을 무시하고
    토큰의 company_id 를 강제한다.
    """
    sb = _make_sb_for_create()
    client = _make_app_with_user(sb)
    with patch.object(tbm_mod, "get_supabase", return_value=sb):
        r = client.post(
            "/tbm",
            json={
                "factory_id":  _FAC_ID,
                "company_id":  _CO_B_ID,     # 타사 주입 시도
                "work_date":   "2026-11-08",
            },
        )

    assert r.status_code == 200, f"예상 200, 실제 {r.status_code}: {r.text}"

    inserted = sb._captured.get("row", {})
    assert inserted.get("company_id") == _CO_A_ID, (
        f"삽입된 company_id가 토큰 company({_CO_A_ID})이어야 함. "
        f"실제: {inserted.get('company_id')}"
    )
    assert inserted.get("company_id") != _CO_B_ID, (
        "body의 타사 company_id가 그대로 삽입됨 — 격리 실패"
    )
