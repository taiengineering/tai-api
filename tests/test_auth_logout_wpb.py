"""
WP-B T-WPB-01~08
GATE: CHEM-WO-OBJ12-G7-008-WPB-IMPLEMENTATION-GATE-009
"""
import pytest
from fastapi import HTTPException

from routers import auth
from supabase_auth.errors import AuthApiError


class _FakeAdmin:
    def __init__(self, error=None):
        self._error = error
        self.calls = []

    def sign_out(self, jwt, scope):
        self.calls.append({"jwt": jwt, "scope": scope})
        if self._error:
            raise self._error


class _FakeGoTrue:
    def __init__(self, error=None):
        self.admin = _FakeAdmin(error)


class _FakeSupabaseAdmin:
    def __init__(self, error=None):
        self.auth = _FakeGoTrue(error)


def _make_admin(monkeypatch, error=None):
    fake = _FakeSupabaseAdmin(error)
    monkeypatch.setattr(auth, "get_supabase_admin", lambda: fake)
    return fake


# ── T-WPB-01 ─────────────────────────────────────────────────────────────────

def test_wpb_01_no_bearer_returns_success(monkeypatch):
    """Bearer 없음 → 200, 서버 폐기 미시도"""
    fake = _make_admin(monkeypatch)
    result = auth.logout(authorization=None)
    assert result["status"] == "success"
    assert fake.auth.admin.calls == []


# ── T-WPB-02 ─────────────────────────────────────────────────────────────────

def test_wpb_02_valid_bearer_calls_sign_out(monkeypatch):
    """유효 Bearer → admin.sign_out(jwt, scope='local') 호출 → 200"""
    fake = _make_admin(monkeypatch)
    result = auth.logout(authorization="Bearer valid-access-token")
    assert result["status"] == "success"
    assert len(fake.auth.admin.calls) == 1
    call = fake.auth.admin.calls[0]
    assert call["jwt"] == "valid-access-token"
    assert call["scope"] == "local"


# ── T-WPB-03 ─────────────────────────────────────────────────────────────────

def test_wpb_03_malformed_bearer_returns_401(monkeypatch):
    """잘못된 Bearer 형식 → 401"""
    _make_admin(monkeypatch)
    with pytest.raises(HTTPException) as exc_info:
        auth.logout(authorization="Token some-value")
    assert exc_info.value.status_code == 401


def test_wpb_03_empty_token_returns_401(monkeypatch):
    """'Bearer ' 뒤 토큰 없음 → 401"""
    _make_admin(monkeypatch)
    with pytest.raises(HTTPException) as exc_info:
        auth.logout(authorization="Bearer ")
    assert exc_info.value.status_code == 401


# ── T-WPB-04 ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("status_code", [400, 401, 403])
def test_wpb_04_invalid_token_returns_401(monkeypatch, status_code):
    """무효 토큰 (GoTrue 4xx) → 401"""
    error = AuthApiError("invalid jwt", status_code, "bad_jwt")
    _make_admin(monkeypatch, error=error)
    with pytest.raises(HTTPException) as exc_info:
        auth.logout(authorization="Bearer expired-token")
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "AUTH_TOKEN_INVALID"


# ── T-WPB-05 ─────────────────────────────────────────────────────────────────

def test_wpb_05_gotrue_5xx_does_not_return_success(monkeypatch):
    """GoTrue 5xx 폐기 실패 → 502, 성공 응답 금지"""
    error = AuthApiError("internal server error", 500, None)
    _make_admin(monkeypatch, error=error)
    with pytest.raises(HTTPException) as exc_info:
        auth.logout(authorization="Bearer some-token")
    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "LOGOUT_UPSTREAM_ERROR"


def test_wpb_05_service_unavailable_does_not_return_success(monkeypatch):
    """GoTrue 연결 불가 → 503, 성공 응답 금지"""
    _make_admin(monkeypatch, error=RuntimeError("connection refused"))
    with pytest.raises(HTTPException) as exc_info:
        auth.logout(authorization="Bearer some-token")
    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "LOGOUT_SERVICE_UNAVAILABLE"


# ── T-WPB-06 ─────────────────────────────────────────────────────────────────

def test_wpb_06_success_response_structure_unchanged(monkeypatch):
    """기존 성공 응답 구조 불변"""
    _make_admin(monkeypatch)
    result = auth.logout(authorization="Bearer valid-token")
    assert result["status"] == "success"
    assert result["message"] == "로그아웃되었습니다"
    assert set(result.keys()) == {"status", "message"}


# ── T-WPB-07 ─────────────────────────────────────────────────────────────────

def test_wpb_07_existing_tai_client_compat_no_header(monkeypatch):
    """기존 TAI 클라이언트 — Authorization 미제공 시 200 호환"""
    _make_admin(monkeypatch)
    result = auth.logout(authorization=None)
    assert result["status"] == "success"


def test_wpb_07_existing_tai_client_compat_with_bearer(monkeypatch):
    """기존 TAI 클라이언트 — Bearer 제공 시 sign_out 성공 → 200 호환"""
    fake = _make_admin(monkeypatch)
    result = auth.logout(authorization="Bearer tai-client-token")
    assert result["status"] == "success"
    assert fake.auth.admin.calls[0]["scope"] == "local"


# ── T-WPB-08 ─────────────────────────────────────────────────────────────────

def test_wpb_08_token_not_in_success_response(monkeypatch):
    """성공 응답 body에 토큰 미포함"""
    _make_admin(monkeypatch)
    result = auth.logout(authorization="Bearer secret-access-token-value")
    response_str = str(result)
    assert "secret-access-token-value" not in response_str


def test_wpb_08_token_not_in_error_log(monkeypatch, caplog):
    """에러 로그에 토큰 값 미포함"""
    import logging
    error = AuthApiError("internal error", 500, None)
    _make_admin(monkeypatch, error=error)
    with caplog.at_level(logging.ERROR, logger="auth"):
        with pytest.raises(HTTPException):
            auth.logout(authorization="Bearer super-secret-token")
    for record in caplog.records:
        assert "super-secret-token" not in record.message
