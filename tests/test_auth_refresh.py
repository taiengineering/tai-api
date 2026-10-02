from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from routers import auth


class _FakeAuth:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.seen_token = None

    def refresh_session(self, refresh_token):
        self.seen_token = refresh_token
        if self.error:
            raise self.error
        return self.result


class _FakeSupabase:
    def __init__(self, auth_client):
        self.auth = auth_client


def _session_result():
    return SimpleNamespace(
        session=SimpleNamespace(
            access_token="new-access",
            refresh_token="new-refresh",
            expires_in=3600,
        )
    )


def test_refresh_auth_session_rotates_tokens(monkeypatch):
    auth_client = _FakeAuth(result=_session_result())
    monkeypatch.setattr(auth, "get_supabase", lambda: _FakeSupabase(auth_client))

    out = auth.refresh_auth_session(auth.RefreshRequest(refresh_token=" old-refresh "))

    assert auth_client.seen_token == "old-refresh"
    assert out == {
        "status": "success",
        "data": {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "token_type": "Bearer",
            "expires_in": 3600,
        },
    }


def test_refresh_auth_session_rejects_blank_token():
    with pytest.raises(HTTPException) as exc:
        auth.refresh_auth_session(auth.RefreshRequest(refresh_token="  "))

    assert exc.value.status_code == 400


def test_refresh_auth_session_maps_provider_failure_to_401(monkeypatch):
    auth_client = _FakeAuth(error=RuntimeError("provider failure"))
    monkeypatch.setattr(auth, "get_supabase", lambda: _FakeSupabase(auth_client))

    with pytest.raises(HTTPException) as exc:
        auth.refresh_auth_session(auth.RefreshRequest(refresh_token="bad-refresh"))

    assert exc.value.status_code == 401
