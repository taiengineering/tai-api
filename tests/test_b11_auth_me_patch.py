"""
B11-AUTH-API-003: PATCH /auth/me — 프로필 수정 계약 검증

검증 목표:
  C1: 토큰 없음 → 401
  C2: 유효하지 않은 토큰(get_user 예외) → 401
  C3: 유효 토큰이나 users 테이블에 사용자 없음 → 404
  C4: 정상 수정 → 200, 토큰 uid로만 업데이트 (body로 uid 주입 불가)

범위 외:
  PATCH /users/{id} (routers/users.py) — 별도 엔드포인트, 동일 QA ID로 처리 금지

운영 안전:
  monkeypatch + FastAPI TestClient 전용 — 운영 DB/API 미접촉
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.auth as auth_mod

_UID = "uid-b11-0001-0000-000000000001"
_AUTH_UID = "auth-b11-0001-0000-000000000001"


def _make_client(sb) -> TestClient:
    app = FastAPI()
    app.include_router(auth_mod.router)
    with patch.object(auth_mod, "get_supabase", return_value=sb):
        return TestClient(app, raise_server_exceptions=False)


# ── C1: 토큰 없음 → 401 ────────────────────────────────────────────────────

def test_C1_no_token_401():
    """C1: Authorization 헤더 없음 → 401 (Bearer 체크 직후 단락)."""
    sb = MagicMock()
    with patch.object(auth_mod, "get_supabase", return_value=sb):
        app = FastAPI()
        app.include_router(auth_mod.router)
        client = TestClient(app, raise_server_exceptions=False)
        r = client.patch("/auth/me", json={"name": "홍길동"})
    assert r.status_code == 401


# ── C2: 유효하지 않은 토큰 → 401 ──────────────────────────────────────────

def test_C2_invalid_token_401():
    """C2: 토큰 형식은 맞으나 auth.get_user가 예외 → 401 (토큰 검증 실패)."""
    sb = MagicMock()
    sb.auth.get_user.side_effect = Exception("invalid jwt")
    with patch.object(auth_mod, "get_supabase", return_value=sb):
        app = FastAPI()
        app.include_router(auth_mod.router)
        client = TestClient(app, raise_server_exceptions=False)
        r = client.patch(
            "/auth/me",
            json={"name": "홍길동"},
            headers={"Authorization": "Bearer bad-token-xyz"},
        )
    assert r.status_code == 401


# ── C3: 유효 토큰 + users 테이블 미존재 → 404 ─────────────────────────────

def test_C3_user_not_found_404():
    """C3: 토큰 검증 성공 + DB에 auth_id 대응 사용자 없음 → 404."""
    sb = MagicMock()

    ur = MagicMock()
    ur.user.id = _AUTH_UID
    sb.auth.get_user.return_value = ur

    # select("id").eq("auth_id", ...).limit(1).execute() → empty
    sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = \
        MagicMock(data=[])

    with patch.object(auth_mod, "get_supabase", return_value=sb):
        app = FastAPI()
        app.include_router(auth_mod.router)
        client = TestClient(app, raise_server_exceptions=False)
        r = client.patch(
            "/auth/me",
            json={"name": "홍길동"},
            headers={"Authorization": "Bearer valid-but-deleted-user"},
        )
    assert r.status_code == 404


# ── C4: 정상 수정 → 200, 본인 UID로만 업데이트 ──────────────────────────

def test_C4_success_own_uid_updated():
    """C4: 정상 수정 → 200. 업데이트 대상이 토큰에서 추출한 uid — body 주입 불가."""
    sb = MagicMock()

    ur = MagicMock()
    ur.user.id = _AUTH_UID
    sb.auth.get_user.return_value = ur

    # select chain: returns user row
    tbl = sb.table.return_value
    tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = \
        MagicMock(data=[{"id": _UID}])

    # update chain: returns updated row
    tbl.update.return_value.eq.return_value.execute.return_value = \
        MagicMock(data=[{"id": _UID, "name": "홍길동", "department": "안전팀"}])

    with patch.object(auth_mod, "get_supabase", return_value=sb):
        app = FastAPI()
        app.include_router(auth_mod.router)
        client = TestClient(app, raise_server_exceptions=False)
        r = client.patch(
            "/auth/me",
            json={"name": "홍길동", "department": "안전팀"},
            headers={"Authorization": "Bearer valid-token"},
        )

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"

    # update().eq("id", uid) 호출 확인 — 본인 UID로만 수정됨
    eq_calls = tbl.update.return_value.eq.call_args_list
    eq_args = [str(c) for c in eq_calls]
    assert any(_UID in s for s in eq_args), (
        f"update가 uid={_UID}로 eq 호출되지 않음. 실제 eq 인수: {eq_args}"
    )
