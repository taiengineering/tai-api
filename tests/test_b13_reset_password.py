"""
B13-SAAS-AUTH-FNC-002: POST /auth/reset-password — 비밀번호 재설정 이메일 발송 계약 검증

검증 목표:
  E1: 미등록 전화번호 → 404 (가입되지 않은 전화번호)
  E2: 이메일 발송 실패 → 500
  E3: 정상 발송 → 200, 마스킹된 이메일 주소 반환

구조:
  FindPasswordRequest: phone 필드
  normalize_phone: 전화번호 정규화 (숫자만)
  supabase.table("users").select("email").eq("phone", pn) → 사용자 조회
  supabase.auth.reset_password_email(email) → 복구 이메일 발송
  복구 완료 후: reset-password.vue 에서 Supabase PUT /auth/v1/user 로 비밀번호 변경
                (이 pytest는 이메일 발송 단계만 — vue 소스 계약은 Playwright에서 확인)

운영 안전:
  monkeypatch + FastAPI TestClient 전용 — 운영 DB/API 미접촉
  Supabase auth.reset_password_email 모의 — 실제 이메일 미발송
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.auth as auth_mod

_PHONE_REG   = "010-1234-5678"       # 등록된 전화번호
_PHONE_UNREG = "010-9999-0000"       # 미등록 전화번호
_EMAIL       = "hong@example.com"


def _make_app() -> TestClient:
    """auth.router 를 포함한 테스트 앱. 인증 불필요(public endpoint)."""
    app = FastAPI()
    app.include_router(auth_mod.router)
    return TestClient(app, raise_server_exceptions=False)


def _ok_sb(email: str = _EMAIL) -> MagicMock:
    """정상 조회 — users 테이블에서 email 반환."""
    sb = MagicMock()
    sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = \
        MagicMock(data=[{"email": email}])
    sb.auth.reset_password_email.return_value = None
    return sb


def _not_found_sb() -> MagicMock:
    """미등록 전화번호 — users 조회 결과 없음."""
    sb = MagicMock()
    sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = \
        MagicMock(data=[])
    return sb


def _fail_sb(email: str = _EMAIL) -> MagicMock:
    """이메일 발송 실패 — reset_password_email 예외."""
    sb = MagicMock()
    sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = \
        MagicMock(data=[{"email": email}])
    sb.auth.reset_password_email.side_effect = Exception("SMTP connection refused")
    return sb


# ── E1: 미등록 전화번호 → 404 ────────────────────────────────────────

def test_E1_unregistered_phone_404():
    """E1: DB에 없는 전화번호 → 404 '가입되지 않은 전화번호입니다'."""
    sb = _not_found_sb()
    client = _make_app()
    with patch.object(auth_mod, "get_supabase", return_value=sb):
        r = client.post("/auth/reset-password", json={"phone": _PHONE_UNREG})
    assert r.status_code == 404, f"예상 404, 실제 {r.status_code}: {r.text}"
    assert "가입되지 않은" in r.text, f"'가입되지 않은' 메시지 없음: {r.text}"


# ── E2: 이메일 발송 실패 → 500 ───────────────────────────────────────

def test_E2_email_send_failure_500():
    """E2: reset_password_email 예외 → 500 '이메일 발송 실패'."""
    sb = _fail_sb()
    client = _make_app()
    with patch.object(auth_mod, "get_supabase", return_value=sb):
        r = client.post("/auth/reset-password", json={"phone": _PHONE_REG})
    assert r.status_code == 500, f"예상 500, 실제 {r.status_code}: {r.text}"
    assert "이메일 발송 실패" in r.text, f"'이메일 발송 실패' 메시지 없음: {r.text}"


# ── E3: 정상 발송 → 200 ──────────────────────────────────────────────

def test_E3_success_200():
    """E3: 등록된 전화번호 → 200, 마스킹 이메일 포함 메시지 반환."""
    sb = _ok_sb(email=_EMAIL)
    client = _make_app()
    with patch.object(auth_mod, "get_supabase", return_value=sb):
        r = client.post("/auth/reset-password", json={"phone": _PHONE_REG})
    assert r.status_code == 200, f"예상 200, 실제 {r.status_code}: {r.text}"
    body = r.json()
    assert body["status"] == "success"
    # 마스킹 패턴: "ho**@example.com" 형식 포함
    assert "message" in body
    assert "**@" in body["message"], f"마스킹 이메일 없음: {body['message']}"
    # auth.reset_password_email 호출 확인
    sb.auth.reset_password_email.assert_called_once_with(_EMAIL)
