"""WO-TAI-API-SENTRY-STABILIZATION-001-R1 WP-C
UUID path parameter validation for /price-setting/saas-plans/{plan_id}

R1 변경: .single() → .limit(1).execute() 계약 반영.
FakeSingle 제거; FakeQ.execute()가 select 시 배열을 직접 반환하므로
nonexistent UUID에서 빈 배열 [] → 404 계약이 실제 PostgREST 동작과 일치.

테스트 목록:
  UV-01  GET malformed UUID → 422 (DB 쿼리 미실행)
  UV-02  GET valid non-existing UUID → 404
  UV-03  GET existing UUID → 200 (기존 동작 유지)
  UV-04  PATCH malformed UUID → 422 (DB 쿼리 미실행)
  UV-05  PATCH valid non-existing UUID → 404
  UV-06  PATCH existing UUID → 200 (기존 동작 유지)
  UV-07  Unauthorized GET → 401/403 (인증 정책 유지)
  UV-08  Unauthorized PATCH → 401/403 (인증 정책 유지)
  UV-NC1 NC: malformed UUID 시 DB 쿼리 호출 안 됨 확인 (GET)
  UV-NC2 NC: malformed UUID 시 DB 쿼리 호출 안 됨 확인 (PATCH)
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import routers.price_setting as _ps_mod
from routers.auth import get_current_user

# ── Fake Supabase ──────────────────────────────────────────────────────────────
# R1: _FakeSingle 제거. 라우터가 .single() 대신 .limit(1).execute()를 사용하므로
# execute()가 항상 배열을 반환한다. nonexistent UUID → [] → 404 계약이
# 실제 PostgREST 동작(.limit(1) 0건 → 빈 배열)과 일치한다.


class _FakeResp:
    def __init__(self, data):
        self.data = data


class _FakeQ:
    def __init__(self, sb, name: str):
        self._sb = sb
        self._name = name
        self._op = "select"
        self._filters: list = []
        self._payload = None

    def select(self, *_, **__):
        self._op = "select"
        return self

    def insert(self, row):
        self._op = "insert"
        # row may be a list (bulk insert) or a single dict
        self._payload = row
        return self

    def update(self, row):
        self._op = "update"
        self._payload = dict(row)
        return self

    def eq(self, col, val):
        self._filters.append((col, val))
        return self

    def order(self, *_, **__):
        return self

    def limit(self, _):
        return self

    def execute(self):
        self._sb.queries.append({"table": self._name, "op": self._op, "filters": list(self._filters)})
        if self._op == "insert":
            payload = self._payload if isinstance(self._payload, list) else [self._payload]
            self._sb.inserts.append({"table": self._name, "rows": payload})
            return _FakeResp(payload)
        rows = list(self._sb.tables.get(self._name, []))
        for col, val in self._filters:
            rows = [r for r in rows if r.get(col) == val]
        if self._op == "update":
            self._sb.updates.append({"table": self._name, "filters": list(self._filters)})
            # Supabase PostgREST UPDATE returns a list — mimic that
            return _FakeResp(rows)
        # select: always return a list ([] when no rows — matches .limit(1) empty result)
        return _FakeResp(rows)


class FakeSB:
    def __init__(self, tables: dict | None = None):
        self.tables: dict = tables or {}
        self.queries: list = []
        self.updates: list = []
        self.inserts: list = []

    def table(self, name: str):
        return _FakeQ(self, name)


# ── 테스트 데이터 ──────────────────────────────────────────────────────────────

_EXISTING_UUID = "11111111-1111-1111-1111-111111111111"
_NONEXISTENT_UUID = "22222222-2222-2222-2222-222222222222"
_MALFORMED_IDS = [
    "nonexistent",
    "not-a-uuid",
    "12345",
    "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "",
    "123e4567-e89b-12d3-a456",   # 불완전 UUID
]

_EXISTING_PLAN = {
    "id": _EXISTING_UUID,
    "plan_name": "BASIC",
    "monthly_base_fee": 100000,
    "is_active": True,
}

_SEED = {
    "price_saas_plan": [_EXISTING_PLAN],
}

_ADMIN_USER = {"id": "admin-1", "role_code": "001", "company_id": "co-1"}


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────

def _require_admin_pass(user, sb):
    """_require_admin 통과 시뮬레이션."""
    pass


def _require_admin_fail(user, sb):
    """_require_admin 인증 실패 시뮬레이션."""
    raise HTTPException(status_code=403, detail="권한이 없습니다")


def _make_client(fake: FakeSB, monkeypatch, require_admin_fn=_require_admin_pass, user=_ADMIN_USER):
    monkeypatch.setattr(_ps_mod, "get_supabase", lambda: fake)
    monkeypatch.setattr(_ps_mod, "_require_admin", require_admin_fn)
    app = FastAPI()
    app.include_router(_ps_mod.router)
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


# ── UV-01: GET malformed UUID → 422 ──────────────────────────────────────────

@pytest.mark.parametrize("bad_id", [
    "nonexistent",
    "not-a-uuid",
    "12345",
    "123e4567-e89b-12d3-a456",
])
def test_uv_01_get_malformed_uuid_returns_422(bad_id, monkeypatch):
    """UV-01: GET /price-setting/saas-plans/{plan_id} — malformed UUID → 422."""
    fake = FakeSB(_SEED)
    client = _make_client(fake, monkeypatch)
    r = client.get(f"/price-setting/saas-plans/{bad_id}")
    assert r.status_code == 422, (
        f"bad_id={bad_id!r}: expected 422, got {r.status_code}. body={r.text[:200]}"
    )


# ── UV-02: GET valid non-existing UUID → 404 ─────────────────────────────────

def test_uv_02_get_valid_nonexistent_uuid_returns_404(monkeypatch):
    """UV-02: GET /price-setting/saas-plans/{plan_id} — valid UUID but no row → 404."""
    fake = FakeSB(_SEED)
    client = _make_client(fake, monkeypatch)
    r = client.get(f"/price-setting/saas-plans/{_NONEXISTENT_UUID}")
    assert r.status_code == 404, f"expected 404, got {r.status_code}. body={r.text[:200]}"


# ── UV-03: GET existing UUID → 200 ───────────────────────────────────────────

def test_uv_03_get_existing_uuid_returns_200(monkeypatch):
    """UV-03: GET /price-setting/saas-plans/{plan_id} — existing UUID → 200."""
    fake = FakeSB(_SEED)
    client = _make_client(fake, monkeypatch)
    r = client.get(f"/price-setting/saas-plans/{_EXISTING_UUID}")
    assert r.status_code == 200, f"expected 200, got {r.status_code}. body={r.text[:200]}"
    data = r.json()
    assert data.get("status") == "success"
    assert data["data"]["id"] == _EXISTING_UUID


# ── UV-04: PATCH malformed UUID → 422 ────────────────────────────────────────

@pytest.mark.parametrize("bad_id", [
    "nonexistent",
    "not-a-uuid",
    "12345",
    "123e4567-e89b-12d3-a456",
])
def test_uv_04_patch_malformed_uuid_returns_422(bad_id, monkeypatch):
    """UV-04: PATCH /price-setting/saas-plans/{plan_id} — malformed UUID → 422."""
    fake = FakeSB(_SEED)
    client = _make_client(fake, monkeypatch)
    r = client.patch(
        f"/price-setting/saas-plans/{bad_id}",
        json={"plan_name": "NEW_NAME"},
    )
    assert r.status_code == 422, (
        f"bad_id={bad_id!r}: expected 422, got {r.status_code}. body={r.text[:200]}"
    )


# ── UV-05: PATCH valid non-existing UUID → 404 ───────────────────────────────

def test_uv_05_patch_valid_nonexistent_uuid_returns_404(monkeypatch):
    """UV-05: PATCH /price-setting/saas-plans/{plan_id} — valid UUID but no row → 404."""
    fake = FakeSB(_SEED)
    client = _make_client(fake, monkeypatch)
    r = client.patch(
        f"/price-setting/saas-plans/{_NONEXISTENT_UUID}",
        json={"plan_name": "NEW_NAME"},
    )
    assert r.status_code == 404, f"expected 404, got {r.status_code}. body={r.text[:200]}"


# ── UV-06: PATCH existing UUID → 200 ─────────────────────────────────────────

def test_uv_06_patch_existing_uuid_returns_200(monkeypatch):
    """UV-06: PATCH /price-setting/saas-plans/{plan_id} — existing UUID → 200."""
    fake = FakeSB(_SEED)
    client = _make_client(fake, monkeypatch)
    r = client.patch(
        f"/price-setting/saas-plans/{_EXISTING_UUID}",
        json={"plan_name": "UPDATED_NAME"},
    )
    assert r.status_code == 200, f"expected 200, got {r.status_code}. body={r.text[:200]}"
    data = r.json()
    assert data.get("status") == "success"


# ── UV-07: Unauthorized GET → 401/403 ────────────────────────────────────────

def test_uv_07_unauthorized_get_rejected(monkeypatch):
    """UV-07: GET /price-setting/saas-plans/{plan_id} — non-admin user → 401 or 403."""
    fake = FakeSB(_SEED)
    client = _make_client(fake, monkeypatch, require_admin_fn=_require_admin_fail)
    r = client.get(f"/price-setting/saas-plans/{_EXISTING_UUID}")
    assert r.status_code in (401, 403), (
        f"expected 401 or 403, got {r.status_code}. body={r.text[:200]}"
    )


# ── UV-08: Unauthorized PATCH → 401/403 ──────────────────────────────────────

def test_uv_08_unauthorized_patch_rejected(monkeypatch):
    """UV-08: PATCH /price-setting/saas-plans/{plan_id} — non-admin user → 401 or 403."""
    fake = FakeSB(_SEED)
    client = _make_client(fake, monkeypatch, require_admin_fn=_require_admin_fail)
    r = client.patch(
        f"/price-setting/saas-plans/{_EXISTING_UUID}",
        json={"plan_name": "SHOULD_FAIL"},
    )
    assert r.status_code in (401, 403), (
        f"expected 401 or 403, got {r.status_code}. body={r.text[:200]}"
    )


# ── UV-NC1: malformed UUID → DB 쿼리 미호출 (GET) ─────────────────────────────

@pytest.mark.parametrize("bad_id", [
    "nonexistent",
    "not-a-uuid",
    "12345",
])
def test_uv_nc1_malformed_uuid_no_db_query_get(bad_id, monkeypatch):
    """UV-NC1 (NC): GET malformed UUID → DB table 조회 없음."""
    fake = FakeSB(_SEED)
    client = _make_client(fake, monkeypatch)
    r = client.get(f"/price-setting/saas-plans/{bad_id}")
    assert r.status_code == 422, f"bad_id={bad_id!r}: expected 422, got {r.status_code}"
    price_plan_queries = [q for q in fake.queries if q.get("table") == "price_saas_plan"]
    assert len(price_plan_queries) == 0, (
        f"bad_id={bad_id!r}: DB에 {len(price_plan_queries)}회 쿼리 발생 — malformed UUID에서 DB 호출 금지"
    )


# ── UV-NC2: malformed UUID → DB 쿼리 미호출 (PATCH) ──────────────────────────

@pytest.mark.parametrize("bad_id", [
    "nonexistent",
    "not-a-uuid",
    "12345",
])
def test_uv_nc2_malformed_uuid_no_db_query_patch(bad_id, monkeypatch):
    """UV-NC2 (NC): PATCH malformed UUID → DB table 조회/수정 없음."""
    fake = FakeSB(_SEED)
    client = _make_client(fake, monkeypatch)
    r = client.patch(
        f"/price-setting/saas-plans/{bad_id}",
        json={"plan_name": "SHOULD_NOT_REACH_DB"},
    )
    assert r.status_code == 422, f"bad_id={bad_id!r}: expected 422, got {r.status_code}"
    price_plan_queries = [q for q in fake.queries if q.get("table") == "price_saas_plan"]
    assert len(price_plan_queries) == 0, (
        f"bad_id={bad_id!r}: DB에 {len(price_plan_queries)}회 쿼리 발생 — malformed UUID에서 DB 호출 금지"
    )
    assert len(fake.updates) == 0, (
        f"bad_id={bad_id!r}: DB UPDATE {len(fake.updates)}회 발생 — malformed UUID에서 UPDATE 금지"
    )
