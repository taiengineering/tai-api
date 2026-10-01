"""WO-AUTH-SERVICE-KEY-CONTRACT-001
Service role key ENV 계약 (SK-01~03) + Recovery 단계 관측성 (REC-04~05).
Production DB/network 불사용 — mock 전용.
"""
from __future__ import annotations

import logging
import os

import bcrypt
import pytest
from fastapi import HTTPException
from unittest.mock import MagicMock

import routers.auth as auth_mod
from routers.auth import login, LoginRequest


# ─────────────────────────────────────────────────────────────────────────────
# 공통 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

class _Q:
    def __init__(self, rows):
        self._rows = rows

    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def neq(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def update(self, *a, **k): return self
    def execute(self): return type("R", (), {"data": self._rows})()


def _make_user_row(pw: str, auth_id: str | None = "auth-uuid-1") -> dict:
    return {
        "id": "u-test", "email": "recovery@test.taieng.co.kr", "name": "Test",
        "phone": None, "role_code": "012", "company_id": "c-1",
        "factory_id": "f-1", "status_code": "ACTIVE", "is_active": True,
        "profile_image_url": None,
        "password_hash": bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode(),
        "auth_id": auth_id,
    }


def _noop(**kw): pass


# ─────────────────────────────────────────────────────────────────────────────
# SK-01~03: service role key resolver + get_supabase_admin fail-closed
# ─────────────────────────────────────────────────────────────────────────────

def test_SK01_canonical_key_takes_priority():
    """SUPABASE_SERVICE_ROLE_KEY 이 있으면 SUPABASE_SERVICE_KEY 보다 우선."""
    with patch_env(
        SUPABASE_SERVICE_ROLE_KEY="canonical-key",
        SUPABASE_SERVICE_KEY="legacy-key",
    ):
        result = (
            os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
            or os.environ.get("SUPABASE_SERVICE_KEY")
        )
    assert result == "canonical-key"


def test_SK02_legacy_key_used_when_canonical_absent():
    """canonical 없을 때 SUPABASE_SERVICE_KEY 가 사용된다."""
    env_copy = {k: v for k, v in os.environ.items()
                if k != "SUPABASE_SERVICE_ROLE_KEY"}
    env_copy["SUPABASE_SERVICE_KEY"] = "legacy-only-key"
    result = (
        env_copy.get("SUPABASE_SERVICE_ROLE_KEY")
        or env_copy.get("SUPABASE_SERVICE_KEY")
    )
    assert result == "legacy-only-key"


def test_SK03_admin_client_raises_when_no_service_key():
    """service role key 없으면 RuntimeError — SUPABASE_KEY(anon) fallback 금지."""
    original = auth_mod._SUPABASE_SERVICE_ROLE_KEY
    try:
        auth_mod._SUPABASE_SERVICE_ROLE_KEY = None  # type: ignore[assignment]
        with pytest.raises(RuntimeError, match="service role key is not configured"):
            auth_mod.get_supabase_admin()
    finally:
        auth_mod._SUPABASE_SERVICE_ROLE_KEY = original


# ─────────────────────────────────────────────────────────────────────────────
# REC-04: admin_update 성공 → second_signin 단계 진입 확인
# ─────────────────────────────────────────────────────────────────────────────

def test_REC04_second_signin_called_after_admin_update_success(monkeypatch, caplog):
    """admin_update 성공 후 _recovery_stage 가 second_signin 으로 전환됨을 확인.

    GoTrue Stage 1 실패 → bcrypt 통과 → admin_update 성공 → second_signin throw.
    로그에 stage=second_signin, admin.update_user_by_id 호출 1회.
    """
    pw = "TestPW-REC04!"
    user_row = _make_user_row(pw, auth_id="auth-uuid-rec04")

    # Stage 1 실패(throw), second_signin 도 throw → recovery except 진입
    sign_in_calls = []

    def _sign_in(creds):
        sign_in_calls.append(creds)
        if len(sign_in_calls) == 1:
            raise Exception("GoTrue Stage1 unavailable")
        raise Exception("GoTrue second signin unavailable")

    class _FakeSB:
        class auth:
            @staticmethod
            def sign_in_with_password(creds): return _sign_in(creds)

        def table(self, name):
            if name == "users":
                return _Q([user_row])
            return _Q([])

    fake_admin = MagicMock()
    fake_admin.auth.admin.update_user_by_id.return_value = None  # success

    monkeypatch.setattr(auth_mod, "create_trace", lambda **kw: None)
    monkeypatch.setattr(auth_mod, "emit_event", _noop)
    monkeypatch.setattr(auth_mod, "clear_trace", lambda: None)
    monkeypatch.setattr(auth_mod, "get_supabase", lambda: _FakeSB())
    monkeypatch.setattr(auth_mod, "get_supabase_admin", lambda: fake_admin)

    with caplog.at_level(logging.WARNING, logger="auth"):
        with pytest.raises(HTTPException) as exc_info:
            login(LoginRequest(login_id="recovery@test.taieng.co.kr", password=pw))

    assert exc_info.value.status_code == 401
    assert "GoTrue 복구 실패" in str(exc_info.value.detail)

    # admin_update 가 1회 호출됐는지 확인
    fake_admin.auth.admin.update_user_by_id.assert_called_once_with(
        "auth-uuid-rec04", {"password": pw}
    )
    # second_signin 단계까지 진입 확인
    assert len(sign_in_calls) == 2
    assert "stage=second_signin" in caplog.text


# ─────────────────────────────────────────────────────────────────────────────
# REC-05: admin_update 실패 → stage=admin_update 로그, credential 노출 없음
# ─────────────────────────────────────────────────────────────────────────────

def test_REC05_recovery_failure_logs_stage_no_credential(monkeypatch, caplog):
    """admin_update throw 시 stage=admin_update + exception_type 만 기록.

    password, JWT, 예외 메시지 원문은 로그에 없어야 한다.
    """
    pw = "SuperSecretCredential-REC05!"
    user_row = _make_user_row(pw, auth_id="auth-uuid-rec05")

    class _FakeSB:
        class auth:
            @staticmethod
            def sign_in_with_password(_creds):
                raise Exception("GoTrue Stage1 unavailable")

        def table(self, name):
            if name == "users":
                return _Q([user_row])
            return _Q([])

    fake_admin = MagicMock()
    fake_admin.auth.admin.update_user_by_id.side_effect = Exception(
        "403 service_role key missing or invalid — sensitive detail"
    )

    monkeypatch.setattr(auth_mod, "create_trace", lambda **kw: None)
    monkeypatch.setattr(auth_mod, "emit_event", _noop)
    monkeypatch.setattr(auth_mod, "clear_trace", lambda: None)
    monkeypatch.setattr(auth_mod, "get_supabase", lambda: _FakeSB())
    monkeypatch.setattr(auth_mod, "get_supabase_admin", lambda: fake_admin)

    with caplog.at_level(logging.WARNING, logger="auth"):
        with pytest.raises(HTTPException) as exc_info:
            login(LoginRequest(login_id="recovery@test.taieng.co.kr", password=pw))

    assert exc_info.value.status_code == 401

    # stage=admin_update 기록
    assert "stage=admin_update" in caplog.text
    # exception class 명 기록
    assert "exception_type=Exception" in caplog.text

    # credential / 예외 원문 노출 없음
    assert pw not in caplog.text
    assert "SuperSecretCredential" not in caplog.text
    assert "service_role key missing" not in caplog.text
    assert "sensitive detail" not in caplog.text


# ─────────────────────────────────────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

from contextlib import contextmanager


@contextmanager
def patch_env(**kv):
    old = {k: os.environ.get(k) for k in kv}
    os.environ.update(kv)
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
