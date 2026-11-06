"""WO-TAI-QA-COVERAGE-WWW-WP06-001: /auth/ensure-user HTTP 경로 계약 — GAP 보완.

REUSE_FIRST: test_auth_social_email_owner_20261009.py (18건) 재사용.
이 파일은 기존 파일이 다루지 않은 세 가지 HTTP 경로 계약만 검증한다.

  HTTP_ROUTE_VERIFIED     — TestClient로 POST /auth/ensure-user 경로 등록 확인
  NO_BEARER_401_VERIFIED  — Authorization 헤더 없음 → 401 "토큰이 없습니다"
  INVALID_BEARER_401_VERIFIED — Bearer 이외 스킴 → 401 "토큰이 없습니다"
"""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.auth as auth_mod


# ── 최소 인메모리 Supabase 목 (HTTP 경로 성공 케이스 전용) ─────────────────

class _SbTable:
    def __init__(self, rows):
        self._rows = rows

    def select(self, *_):
        return self

    def eq(self, col, val):
        self._last_col, self._last_val = col, val
        return self

    def limit(self, _):
        return self

    def execute(self):
        matched = [r for r in self._rows if r.get(self._last_col) == self._last_val]
        return SimpleNamespace(data=matched[:1])


class _Sb:
    def __init__(self, rows):
        self._rows = rows

    def table(self, _name):
        return _SbTable(self._rows)


# ── TestClient 공통 픽스처 ────────────────────────────────────────────────────

@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(auth_mod.router)
    return TestClient(app, raise_server_exceptions=False)


# ── GAP-01: Authorization 헤더 없음 → 401 ────────────────────────────────────

def test_route_no_authorization_header_is_401(client):
    resp = client.post("/auth/ensure-user")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "토큰이 없습니다"


# ── GAP-02: Bearer 이외 스킴 → 401 ───────────────────────────────────────────

def test_route_non_bearer_scheme_is_401(client):
    resp = client.post("/auth/ensure-user", headers={"Authorization": "Token some-opaque-value"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "토큰이 없습니다"


# ── GAP-03: 유효 Bearer + 기존 사용자 → HTTP 200 (경로 등록 증거) ───────────

def test_route_bearer_valid_existing_user_is_200(monkeypatch, client):
    row = {"id": "pub-wp06", "auth_id": "uid-wp06", "email": "wp06@example.com"}
    sb = _Sb([row])
    auth_user = SimpleNamespace(
        id="uid-wp06", email="wp06@example.com",
        user_metadata={}, app_metadata={},
    )
    monkeypatch.setattr(auth_mod, "_auth_user_from_token", lambda _: (sb, auth_user))

    resp = client.post("/auth/ensure-user", headers={"Authorization": "Bearer fixture-wp06"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["created"] is False
    assert body["data"]["id"] == "pub-wp06"
