"""WO-TAI-SEC03-D2B2-API-AUTH-HARDENING-001 — API 인증 보강 계약 테스트.

검증 항목:
  D2B2-T01  GET /document-engine/metrics  미인증 → 401
  D2B2-T02  GET /document-engine/metrics  COMPANY 스코프(비-ALL) → 403
  D2B2-T03  GET /document-engine/metrics  ALL 스코프 → 200

  D2B2-T04  GET /document-engine/metrics/factory/{id}  미인증 → 401
  D2B2-T05  GET /document-engine/metrics/factory/{id}  존재하지 않는 factory → 404
  D2B2-T06  GET /document-engine/metrics/factory/{id}  COMPANY 스코프 + 자사 factory → 200
  D2B2-T07  GET /document-engine/metrics/factory/{id}  COMPANY 스코프 + 타사 factory → 404
  D2B2-T08  GET /document-engine/metrics/factory/{id}  FACTORY 스코프 + 자기 factory → 200
  D2B2-T09  GET /document-engine/metrics/factory/{id}  FACTORY 스코프 + 타 factory → 404

  D2B2-T10  GET  /admin/stats          미인증 → 401
  D2B2-T11  GET  /admin/stats          COMPANY 스코프(비-ALL) → 403
  D2B2-T12  GET  /admin/stats          ALL 스코프 → 200

  D2B2-T13  POST /admin/stats/refresh  미인증 → 401
  D2B2-T14  POST /admin/stats/refresh  COMPANY 스코프(비-ALL) → 403
  D2B2-T15  POST /admin/stats/refresh  ALL 스코프 → 200

  D2B2-S01  소스 정적: document_engine_api.py — /metrics Depends(get_current_user) + _require_admin 존재
  D2B2-S02  소스 정적: document_engine_api.py — /metrics/factory/{id} Depends(get_current_user) + _ensure_own_company 존재
  D2B2-S03  소스 정적: admin_stats.py — /stats Depends(get_current_user) + _require_admin 존재
  D2B2-S04  소스 정적: admin_stats.py — /stats/refresh Depends(get_current_user) + _require_admin 존재

실 DB / 네트워크 0. AUTH 는 FastAPI dependency_overrides, FakeSB 인메모리.
"""
from __future__ import annotations

import os
import pathlib
import sys

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_DE_SRC = (_ROOT / "routers" / "document_engine_api.py").read_text(encoding="utf-8")
_AS_SRC = (_ROOT / "routers" / "admin_stats.py").read_text(encoding="utf-8")

# ─── 공통 사용자 픽스처 ────────────────────────────────────────────
_ALL_USER = {
    "id": "uid-all",
    "company_id": None,
    "role_code": "001",
    "status_code": "ACTIVE",
    "is_active": True,
}
_COMPANY_USER = {
    "id": "uid-co",
    "company_id": "cid-own",
    "role_code": "011",
    "status_code": "ACTIVE",
    "is_active": True,
    "factory_id": None,
}
_FACTORY_USER = {
    "id": "uid-fac",
    "company_id": "cid-own",
    "role_code": "012",
    "status_code": "ACTIVE",
    "is_active": True,
    "factory_id": "fid-own",
}


# ─── FakeSB ───────────────────────────────────────────────────────

class _Resp:
    def __init__(self, data):
        self.data = data
        self.count = len(data) if isinstance(data, list) else (1 if data else 0)


class _Q:
    def __init__(self, sb, table_name: str):
        self._sb = sb
        self._table = table_name
        self._filters: list = []

    def select(self, *a, **k):
        return self

    def eq(self, col, val):
        self._filters.append((col, val))
        return self

    def neq(self, col, val):
        return self

    def limit(self, n):
        return self

    def order(self, *a, **k):
        return self

    def execute(self):
        return self._sb._resolve(self._table, self._filters)


class FakeSB:
    """role_data_scope + factories 만 처리하는 최소 FakeSB."""

    def __init__(self, factory_rows: list[dict], scope_override: str | None = None):
        self._factories = {r["id"]: r for r in factory_rows}
        self._scope_override = scope_override  # None = role_code 기준 자동

    def table(self, name: str):
        return _Q(self, name)

    def rpc(self, fn: str, *a, **k):
        return _Q(self, f"rpc:{fn}")

    def _resolve(self, table: str, filters: list) -> _Resp:
        if table == "role_data_scope":
            # role_code 기준으로 scope 반환
            if self._scope_override:
                return _Resp([{"scope_type": self._scope_override}])
            role_code = next((v for k, v in filters if k == "role_code"), None)
            if role_code == "001":
                return _Resp([{"scope_type": "ALL"}])
            if role_code == "012":
                return _Resp([{"scope_type": "FACTORY"}])
            return _Resp([{"scope_type": "COMPANY"}])

        if table == "factories":
            fid = next((v for k, v in filters if k == "id"), None)
            row = self._factories.get(fid)
            return _Resp([row] if row else [])

        if table == "dashboard_stats":
            return _Resp([{"total_companies": 1, "synced_at": None}])

        return _Resp([])


# ─── 공통 앱 빌더 ─────────────────────────────────────────────────

def _de_app(user, fake, monkeypatch):
    """document_engine router 단독 앱."""
    import routers.document_engine_api as de
    from routers.auth import get_current_user

    monkeypatch.setattr(de, "get_supabase", lambda: fake)
    monkeypatch.setattr(de.svc, "get_metrics", lambda: {"total": 0})
    monkeypatch.setattr(de.svc, "get_metrics_by_factory", lambda fid: {"factory_id": fid})

    app = FastAPI()
    app.include_router(de.router)

    if user is False:
        def _deny():
            raise HTTPException(status_code=401, detail="토큰이 없습니다")
        app.dependency_overrides[get_current_user] = _deny
    else:
        app.dependency_overrides[get_current_user] = lambda: user

    return TestClient(app, raise_server_exceptions=False)


def _as_app(user, fake, monkeypatch):
    """admin_stats router 단독 앱."""
    import routers.admin_stats as ast
    from routers.auth import get_current_user

    monkeypatch.setattr(ast, "get_supabase", lambda: fake)

    app = FastAPI()
    app.include_router(ast.router)

    if user is False:
        def _deny():
            raise HTTPException(status_code=401, detail="토큰이 없습니다")
        app.dependency_overrides[get_current_user] = _deny
    else:
        app.dependency_overrides[get_current_user] = lambda: user

    return TestClient(app, raise_server_exceptions=False)


# ─── 공통 factory seed ────────────────────────────────────────────

_OWN_FACTORY = {"id": "fid-own", "company_id": "cid-own"}
_OTHER_FACTORY = {"id": "fid-other", "company_id": "cid-other"}


# ════════════════════════════════════════════════════════════════
# FIX-A: GET /document-engine/metrics
# ════════════════════════════════════════════════════════════════

def test_D2B2_T01_metrics_no_token(monkeypatch):
    fake = FakeSB([])
    client = _de_app(False, fake, monkeypatch)
    r = client.get("/document-engine/metrics")
    assert r.status_code == 401, f"미인증 /metrics → 기대 401, 실제 {r.status_code}"


def test_D2B2_T02_metrics_company_scope_403(monkeypatch):
    fake = FakeSB([])
    client = _de_app(_COMPANY_USER, fake, monkeypatch)
    r = client.get("/document-engine/metrics")
    assert r.status_code == 403, f"COMPANY 스코프 /metrics → 기대 403, 실제 {r.status_code}"


def test_D2B2_T03_metrics_all_scope_200(monkeypatch):
    fake = FakeSB([])
    client = _de_app(_ALL_USER, fake, monkeypatch)
    r = client.get("/document-engine/metrics")
    assert r.status_code == 200, f"ALL 스코프 /metrics → 기대 200, 실제 {r.status_code}: {r.text}"


# ════════════════════════════════════════════════════════════════
# FIX-B: GET /document-engine/metrics/factory/{factory_id}
# ════════════════════════════════════════════════════════════════

def test_D2B2_T04_factory_metrics_no_token(monkeypatch):
    fake = FakeSB([_OWN_FACTORY])
    client = _de_app(False, fake, monkeypatch)
    r = client.get("/document-engine/metrics/factory/fid-own")
    assert r.status_code == 401, f"미인증 /metrics/factory → 기대 401, 실제 {r.status_code}"


def test_D2B2_T05_factory_metrics_nonexistent_factory_404(monkeypatch):
    fake = FakeSB([])  # factory 없음
    client = _de_app(_ALL_USER, fake, monkeypatch)
    r = client.get("/document-engine/metrics/factory/fid-nonexistent")
    assert r.status_code == 404, f"존재하지 않는 factory → 기대 404, 실제 {r.status_code}"


def test_D2B2_T06_factory_metrics_company_scope_own_company_200(monkeypatch):
    fake = FakeSB([_OWN_FACTORY])
    client = _de_app(_COMPANY_USER, fake, monkeypatch)
    r = client.get("/document-engine/metrics/factory/fid-own")
    assert r.status_code == 200, f"COMPANY 스코프 자사 factory → 기대 200, 실제 {r.status_code}: {r.text}"


def test_D2B2_T07_factory_metrics_company_scope_other_company_404(monkeypatch):
    fake = FakeSB([_OWN_FACTORY, _OTHER_FACTORY])
    client = _de_app(_COMPANY_USER, fake, monkeypatch)
    r = client.get("/document-engine/metrics/factory/fid-other")
    assert r.status_code == 404, f"COMPANY 스코프 타사 factory → 기대 404, 실제 {r.status_code}"


def test_D2B2_T08_factory_metrics_factory_scope_own_factory_200(monkeypatch):
    fake = FakeSB([_OWN_FACTORY])
    client = _de_app(_FACTORY_USER, fake, monkeypatch)
    r = client.get("/document-engine/metrics/factory/fid-own")
    assert r.status_code == 200, f"FACTORY 스코프 자기 factory → 기대 200, 실제 {r.status_code}: {r.text}"


def test_D2B2_T09_factory_metrics_factory_scope_other_factory_404(monkeypatch):
    # 같은 회사지만 다른 factory
    other_same_co = {"id": "fid-other-same-co", "company_id": "cid-own"}
    fake = FakeSB([_OWN_FACTORY, other_same_co])
    client = _de_app(_FACTORY_USER, fake, monkeypatch)
    r = client.get("/document-engine/metrics/factory/fid-other-same-co")
    assert r.status_code == 404, f"FACTORY 스코프 타 factory(같은 회사) → 기대 404, 실제 {r.status_code}"


# ════════════════════════════════════════════════════════════════
# FIX-C: GET /admin/stats
# ════════════════════════════════════════════════════════════════

def test_D2B2_T10_admin_stats_no_token(monkeypatch):
    fake = FakeSB([])
    client = _as_app(False, fake, monkeypatch)
    r = client.get("/admin/stats")
    assert r.status_code == 401, f"미인증 /admin/stats → 기대 401, 실제 {r.status_code}"


def test_D2B2_T11_admin_stats_company_scope_403(monkeypatch):
    fake = FakeSB([])
    client = _as_app(_COMPANY_USER, fake, monkeypatch)
    r = client.get("/admin/stats")
    assert r.status_code == 403, f"COMPANY 스코프 /admin/stats → 기대 403, 실제 {r.status_code}"


def test_D2B2_T12_admin_stats_all_scope_200(monkeypatch):
    fake = FakeSB([])
    client = _as_app(_ALL_USER, fake, monkeypatch)
    r = client.get("/admin/stats")
    assert r.status_code == 200, f"ALL 스코프 /admin/stats → 기대 200, 실제 {r.status_code}: {r.text}"


# ════════════════════════════════════════════════════════════════
# FIX-D: POST /admin/stats/refresh
# ════════════════════════════════════════════════════════════════

def test_D2B2_T13_admin_refresh_no_token(monkeypatch):
    fake = FakeSB([])
    client = _as_app(False, fake, monkeypatch)
    r = client.post("/admin/stats/refresh")
    assert r.status_code == 401, f"미인증 /admin/stats/refresh → 기대 401, 실제 {r.status_code}"


def test_D2B2_T14_admin_refresh_company_scope_403(monkeypatch):
    fake = FakeSB([])
    client = _as_app(_COMPANY_USER, fake, monkeypatch)
    r = client.post("/admin/stats/refresh")
    assert r.status_code == 403, f"COMPANY 스코프 /admin/stats/refresh → 기대 403, 실제 {r.status_code}"


def test_D2B2_T15_admin_refresh_all_scope_200(monkeypatch):
    fake = FakeSB([])
    client = _as_app(_ALL_USER, fake, monkeypatch)
    r = client.post("/admin/stats/refresh")
    assert r.status_code == 200, f"ALL 스코프 /admin/stats/refresh → 기대 200, 실제 {r.status_code}: {r.text}"


# ════════════════════════════════════════════════════════════════
# 소스 정적 검증
# ════════════════════════════════════════════════════════════════

def test_D2B2_S01_de_metrics_has_auth():
    assert "get_current_user" in _DE_SRC, "document_engine_api.py에 get_current_user 없음"
    assert "_require_admin" in _DE_SRC, "document_engine_api.py에 _require_admin 없음"


def test_D2B2_S02_de_factory_metrics_has_scope():
    assert "_ensure_own_company" in _DE_SRC, "document_engine_api.py에 _ensure_own_company 없음"


def test_D2B2_S03_admin_stats_get_has_auth():
    assert "get_current_user" in _AS_SRC, "admin_stats.py에 get_current_user 없음"
    assert "_require_admin" in _AS_SRC, "admin_stats.py에 _require_admin 없음"


def test_D2B2_S04_admin_stats_refresh_has_auth():
    assert "get_current_user" in _AS_SRC
    assert "_require_admin" in _AS_SRC
    # refresh 엔드포인트에 Depends 사용 확인
    assert "stats/refresh" in _AS_SRC and "Depends(get_current_user)" in _AS_SRC
