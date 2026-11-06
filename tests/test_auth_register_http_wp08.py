"""WO-TAI-QA-COVERAGE-WWW-WP08-001 — P1-API-AUTH-API-001 HTTP 경로 갭 보완.

기존 자산 재사용:
  test_auth_register_active.py (T1~T5) — 가입 성공·ACTIVE 상태·보상 처리·소셜 계정 (5건)

신규 갭 테스트 (HTTP 경로 미검증 항목만):
  GAP-01  HTTP_ROUTE_VERIFIED           — POST /auth/register 경로 존재, 200 반환
  GAP-02  RESPONSE_FIELDS_VERIFIED      — status·message·data.user_id/phone/name/company_id 확인,
                                          세션 토큰(access_token·refresh_token) 미발급 확인
  GAP-03  IDENTITY_REQUIREMENT_VERIFIED — mtx_id 미인증 시 400 "본인인증" 반환

T1~T5 는 register() 함수 직접 호출 — HTTP 계층 검증 없음.
이 파일은 FastAPI TestClient 를 사용해 HTTP 경로를 경유한다.

운영 안전:
  PRODUCTION_API_HITS=0 / REAL_INICIS_CALLS=0 / REAL_DB_WRITES=0
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("INTERNAL_API_SECRET", "pytest-internal-secret")

import routers.auth as auth_mod


# ── 픽스처 ────────────────────────────────────────────────────────────────────

@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(auth_mod.router)
    return TestClient(app, raise_server_exceptions=False)


def _make_sb_register_success() -> MagicMock:
    """register 성공 경로용 mock supabase."""
    sb = MagicMock()

    # 기본: 모든 select → 빈 목록 (중복 없음)
    sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])

    # inicis_auth_requests: mtx_id 조회 → SUCCESS 레코드
    ia_table = MagicMock()
    ia_table.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[{
        "status": "SUCCESS",
        "user_ci": "UNIT_TEST_CI_VALUE_WP08",
        "user_name": "홍길동",
        "user_phone": "01012345678",
        "user_birthday": "19900101",
    }])
    ia_table.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

    # users: select → 빈 목록(중복 없음), insert → 신규 row
    users_table = MagicMock()
    users_table.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
    users_table.insert.return_value.execute.return_value = MagicMock(data=[{
        "id": "user-wp08-001",
        "auth_id": "auth-wp08-001",
        "email": "wp08@example.com",
        "phone": "01012345678",
        "name": "홍길동",
        "company_id": None,
    }])
    users_table.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

    # diagnosis_auth_log
    diag_table = MagicMock()
    diag_table.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

    def table_dispatch(name: str) -> MagicMock:
        if name == "inicis_auth_requests":
            return ia_table
        if name in ("users", "companies"):
            return users_table
        return diag_table

    sb.table.side_effect = table_dispatch

    auth_user = MagicMock()
    auth_user.id = "auth-wp08-001"
    sb.auth.sign_up.return_value = MagicMock(user=auth_user)

    return sb


_REGISTER_PAYLOAD = {
    "name": "홍길동",
    "email": "wp08@example.com",
    "phone": "01012345678",
    "password": "Password123!",
    "mtx_id": "MTX_WP08_001",
}


# ── GAP-01: HTTP_ROUTE_VERIFIED ───────────────────────────────────────────────

def test_register_http_route_is_200_on_success(monkeypatch, client):
    """POST /auth/register 경로가 등록되어 있고 성공 시 HTTP 200 을 반환한다."""
    monkeypatch.setattr(auth_mod, "get_supabase", lambda: _make_sb_register_success())
    resp = client.post("/auth/register", json=_REGISTER_PAYLOAD)
    assert resp.status_code == 200


# ── GAP-02: RESPONSE_FIELDS_VERIFIED ─────────────────────────────────────────

def test_register_success_response_structure_and_no_session_token(monkeypatch, client):
    """성공 응답에 status·message·data 필드가 있고, 로그인 세션 토큰이 포함되지 않는다."""
    monkeypatch.setattr(auth_mod, "get_supabase", lambda: _make_sb_register_success())
    resp = client.post("/auth/register", json=_REGISTER_PAYLOAD)
    assert resp.status_code == 200
    body = resp.json()

    # 필수 응답 필드
    assert body["status"] == "success"
    assert body["message"] == "회원가입이 완료되었습니다."
    data = body["data"]
    assert "user_id" in data,    "data.user_id 누락"
    assert "phone" in data,      "data.phone 누락"
    assert "name" in data,       "data.name 누락"
    assert "company_id" in data, "data.company_id 누락"

    # 세션 토큰 미발급 — register 는 로그인이 아님
    assert "access_token"  not in body,            "루트에 access_token 미포함이어야 함"
    assert "refresh_token" not in body,            "루트에 refresh_token 미포함이어야 함"
    assert "access_token"  not in data,            "data 에 access_token 미포함이어야 함"
    assert "refresh_token" not in data,            "data 에 refresh_token 미포함이어야 함"


# ── GAP-03: IDENTITY_REQUIREMENT_VERIFIED ────────────────────────────────────

def test_register_http_route_no_valid_identity_is_400(monkeypatch, client):
    """mtx_id 에 해당하는 본인인증 SUCCESS 레코드가 없으면 HTTP 400 을 반환한다."""
    sb = MagicMock()
    # 모든 select → 빈 목록
    sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])

    # inicis_auth_requests: 빈 결과 (인증 이력 없음)
    ia_table = MagicMock()
    ia_table.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])

    def table_dispatch(name: str) -> MagicMock:
        if name == "inicis_auth_requests":
            return ia_table
        return sb.table.return_value

    sb.table.side_effect = table_dispatch

    monkeypatch.setattr(auth_mod, "get_supabase", lambda: sb)

    resp = client.post("/auth/register", json=_REGISTER_PAYLOAD)
    assert resp.status_code == 400
    assert "본인인증" in resp.json().get("detail", ""), \
        f"detail 에 '본인인증' 포함이어야 함: {resp.json()}"
