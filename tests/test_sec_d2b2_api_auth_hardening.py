"""WO-TAI-SEC03-D2B2-API-AUTH-HARDENING-001 + R1 — API 인증·스코프 보강 계약 테스트.

검증 항목 (원본 19개):
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
  D2B2-S02  소스 정적: document_engine_api.py — /metrics/factory/{id} Depends(get_current_user) + 스코프 검증 존재
  D2B2-S03  소스 정적: admin_stats.py — /stats Depends(get_current_user) + _require_admin 존재
  D2B2-S04  소스 정적: admin_stats.py — /stats/refresh Depends(get_current_user) + _require_admin 존재

R1 보강 케이스 (FIX-R1 스코프 매트릭스):
  D2B2-R01  TEAM + 자기 배정 공장 → 200
  D2B2-R02  TEAM + 같은 회사 다른 공장 → 404
  D2B2-R03  TEAM + factory_id 미배정 → 403/404
  D2B2-R04  ASSIGNED + 자사 공장 → 403
  D2B2-R05  ASSIGNED + 타사 공장 → 403
  D2B2-R06  PLATFORM + company_id 일치 → 403
  D2B2-R07  PLATFORM + company_id 없음 → 403
  D2B2-R08  UNKNOWN scope → 403
  D2B2-R09  role_data_scope 레코드 없음 → 403
  D2B2-R10  role_data_scope 조회 예외 → 403
  D2B2-R11  factory company_id 없음 → 404
  D2B2-R12  잘못된 UUID 형식 → 422
  D2B2-R13  존재하지 않는 UUID factory → 404
  D2B2-R14  타사 요청 시 svc 호출 0회
  D2B2-R15  권한 부족 시 svc 호출 0회
  D2B2-R16  정상 권한 요청 시 svc 호출 1회
  D2B2-R17  기존 3개 관리자 전용 API 회귀 (401/403/200)

실 DB / 네트워크 0. AUTH 는 FastAPI dependency_overrides, FakeSB 인메모리.
"""
from __future__ import annotations

import os
import pathlib
import sys
from typing import Optional

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

# UUID 형식 factory_id 사용 (R1 요구)
_FID_OWN   = "aaaaaaaa-0000-4000-8000-000000000001"
_FID_OTHER = "bbbbbbbb-0000-4000-8000-000000000002"
_FID_SAME_CO_OTHER = "cccccccc-0000-4000-8000-000000000003"
_FID_NO_CO = "dddddddd-0000-4000-8000-000000000004"
_FID_NONEXISTENT = "eeeeeeee-0000-4000-8000-000000000005"

_CID_OWN   = "cid-own"
_CID_OTHER = "cid-other"

# ─── 공통 사용자 픽스처 ────────────────────────────────────────────
_ALL_USER = {
    "id": "uid-all",
    "company_id": None,
    "role_code": "001",
    "status_code": "ACTIVE",
    "is_active": True,
    "factory_id": None,
}
_COMPANY_USER = {
    "id": "uid-co",
    "company_id": _CID_OWN,
    "role_code": "011",
    "status_code": "ACTIVE",
    "is_active": True,
    "factory_id": None,
}
_FACTORY_USER = {
    "id": "uid-fac",
    "company_id": _CID_OWN,
    "role_code": "012",
    "status_code": "ACTIVE",
    "is_active": True,
    "factory_id": _FID_OWN,
}
_TEAM_USER = {
    "id": "uid-team",
    "company_id": _CID_OWN,
    "role_code": "013",
    "status_code": "ACTIVE",
    "is_active": True,
    "factory_id": _FID_OWN,
}
_TEAM_USER_NO_FAC = {
    "id": "uid-team-nf",
    "company_id": _CID_OWN,
    "role_code": "013",
    "status_code": "ACTIVE",
    "is_active": True,
    "factory_id": None,
}
_ASSIGNED_USER = {
    "id": "uid-asgn",
    "company_id": _CID_OWN,
    "role_code": "014",
    "status_code": "ACTIVE",
    "is_active": True,
    "factory_id": _FID_OWN,
}
_PLATFORM_USER_OWN = {
    "id": "uid-plat-own",
    "company_id": _CID_OWN,
    "role_code": "099",
    "status_code": "ACTIVE",
    "is_active": True,
    "factory_id": None,
}
_PLATFORM_USER_NONE = {
    "id": "uid-plat-none",
    "company_id": None,
    "role_code": "099",
    "status_code": "ACTIVE",
    "is_active": True,
    "factory_id": None,
}
_UNKNOWN_USER = {
    "id": "uid-unk",
    "company_id": _CID_OWN,
    "role_code": "999",
    "status_code": "ACTIVE",
    "is_active": True,
    "factory_id": None,
}


# ─── FakeSB ───────────────────────────────────────────────────────

# role_code → scope_type 매핑
_DEFAULT_SCOPE_MAP: dict[str, str] = {
    "001": "ALL",
    "011": "COMPANY",
    "012": "FACTORY",
    "013": "TEAM",
    "014": "ASSIGNED",
    "099": "PLATFORM",
    # 999는 없음 → scope_res.data = []
}


class _Resp:
    def __init__(self, data, *, raise_on_execute: Optional[Exception] = None):
        self.data = data
        self.count = len(data) if isinstance(data, list) else (1 if data else 0)
        self._raise = raise_on_execute

    def execute(self):
        if self._raise:
            raise self._raise
        return self


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
    """role_data_scope + factories + dashboard_stats + rpc 처리 최소 FakeSB."""

    def __init__(
        self,
        factory_rows: list[dict],
        scope_map: dict[str, str] | None = None,
        scope_exception: Exception | None = None,
    ):
        self._factories = {r["id"]: r for r in factory_rows}
        self._scope_map = scope_map if scope_map is not None else _DEFAULT_SCOPE_MAP
        self._scope_exception = scope_exception

    def table(self, name: str):
        return _Q(self, name)

    def rpc(self, fn: str, *a, **k):
        return _Q(self, f"rpc:{fn}")

    def _resolve(self, table: str, filters: list) -> _Resp:
        if table == "role_data_scope":
            if self._scope_exception:
                raise self._scope_exception
            role_code = next((v for k, v in filters if k == "role_code"), None)
            scope = self._scope_map.get(role_code)
            if scope:
                return _Resp([{"scope_type": scope}])
            return _Resp([])  # 레코드 없음

        if table == "factories":
            fid = next((v for k, v in filters if k == "id"), None)
            row = self._factories.get(fid)
            return _Resp([row] if row else [])

        if table == "dashboard_stats":
            return _Resp([{"total_companies": 1, "synced_at": None}])

        return _Resp([])


# ─── 공통 앱 빌더 ─────────────────────────────────────────────────

def _de_app(user, fake, monkeypatch, call_counter: list | None = None):
    """document_engine router 단독 앱."""
    import routers.document_engine_api as de
    from routers.auth import get_current_user

    monkeypatch.setattr(de, "get_supabase", lambda: fake)
    monkeypatch.setattr(de.svc, "get_metrics", lambda: {"total": 0})

    if call_counter is not None:
        def _tracked(fid):
            call_counter.append(fid)
            return {"factory_id": fid}
        monkeypatch.setattr(de.svc, "get_metrics_by_factory", _tracked)
    else:
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


# ─── factory seed ─────────────────────────────────────────────────

def _seed():
    return [
        {"id": _FID_OWN,           "company_id": _CID_OWN},
        {"id": _FID_OTHER,         "company_id": _CID_OTHER},
        {"id": _FID_SAME_CO_OTHER, "company_id": _CID_OWN},
        {"id": _FID_NO_CO,         "company_id": None},
    ]


# ════════════════════════════════════════════════════════════════
# FIX-A: GET /document-engine/metrics
# ════════════════════════════════════════════════════════════════

def test_D2B2_T01_metrics_no_token(monkeypatch):
    client = _de_app(False, FakeSB([]), monkeypatch)
    r = client.get("/document-engine/metrics")
    assert r.status_code == 401, f"미인증 /metrics → 기대 401, 실제 {r.status_code}"


def test_D2B2_T02_metrics_company_scope_403(monkeypatch):
    client = _de_app(_COMPANY_USER, FakeSB([]), monkeypatch)
    r = client.get("/document-engine/metrics")
    assert r.status_code == 403, f"COMPANY 스코프 /metrics → 기대 403, 실제 {r.status_code}"


def test_D2B2_T03_metrics_all_scope_200(monkeypatch):
    client = _de_app(_ALL_USER, FakeSB([]), monkeypatch)
    r = client.get("/document-engine/metrics")
    assert r.status_code == 200, f"ALL 스코프 /metrics → 기대 200, 실제 {r.status_code}: {r.text}"


# ════════════════════════════════════════════════════════════════
# FIX-B: GET /document-engine/metrics/factory/{factory_id}
# ════════════════════════════════════════════════════════════════

def test_D2B2_T04_factory_metrics_no_token(monkeypatch):
    client = _de_app(False, FakeSB(_seed()), monkeypatch)
    r = client.get(f"/document-engine/metrics/factory/{_FID_OWN}")
    assert r.status_code == 401, f"미인증 /metrics/factory → 기대 401, 실제 {r.status_code}"


def test_D2B2_T05_factory_metrics_nonexistent_factory_404(monkeypatch):
    client = _de_app(_ALL_USER, FakeSB([]), monkeypatch)
    r = client.get(f"/document-engine/metrics/factory/{_FID_NONEXISTENT}")
    assert r.status_code == 404, f"존재하지 않는 factory → 기대 404, 실제 {r.status_code}"


def test_D2B2_T06_factory_metrics_company_scope_own_company_200(monkeypatch):
    client = _de_app(_COMPANY_USER, FakeSB(_seed()), monkeypatch)
    r = client.get(f"/document-engine/metrics/factory/{_FID_OWN}")
    assert r.status_code == 200, f"COMPANY 자사 factory → 기대 200, 실제 {r.status_code}: {r.text}"


def test_D2B2_T07_factory_metrics_company_scope_other_company_404(monkeypatch):
    client = _de_app(_COMPANY_USER, FakeSB(_seed()), monkeypatch)
    r = client.get(f"/document-engine/metrics/factory/{_FID_OTHER}")
    assert r.status_code == 404, f"COMPANY 타사 factory → 기대 404, 실제 {r.status_code}"


def test_D2B2_T08_factory_metrics_factory_scope_own_factory_200(monkeypatch):
    client = _de_app(_FACTORY_USER, FakeSB(_seed()), monkeypatch)
    r = client.get(f"/document-engine/metrics/factory/{_FID_OWN}")
    assert r.status_code == 200, f"FACTORY 자기 factory → 기대 200, 실제 {r.status_code}: {r.text}"


def test_D2B2_T09_factory_metrics_factory_scope_other_factory_404(monkeypatch):
    client = _de_app(_FACTORY_USER, FakeSB(_seed()), monkeypatch)
    r = client.get(f"/document-engine/metrics/factory/{_FID_SAME_CO_OTHER}")
    assert r.status_code == 404, f"FACTORY 타 factory(같은 회사) → 기대 404, 실제 {r.status_code}"


# ════════════════════════════════════════════════════════════════
# FIX-C: GET /admin/stats
# ════════════════════════════════════════════════════════════════

def test_D2B2_T10_admin_stats_no_token(monkeypatch):
    client = _as_app(False, FakeSB([]), monkeypatch)
    r = client.get("/admin/stats")
    assert r.status_code == 401, f"미인증 /admin/stats → 기대 401, 실제 {r.status_code}"


def test_D2B2_T11_admin_stats_company_scope_403(monkeypatch):
    client = _as_app(_COMPANY_USER, FakeSB([]), monkeypatch)
    r = client.get("/admin/stats")
    assert r.status_code == 403, f"COMPANY 스코프 /admin/stats → 기대 403, 실제 {r.status_code}"


def test_D2B2_T12_admin_stats_all_scope_200(monkeypatch):
    client = _as_app(_ALL_USER, FakeSB([]), monkeypatch)
    r = client.get("/admin/stats")
    assert r.status_code == 200, f"ALL 스코프 /admin/stats → 기대 200, 실제 {r.status_code}: {r.text}"


# ════════════════════════════════════════════════════════════════
# FIX-D: POST /admin/stats/refresh
# ════════════════════════════════════════════════════════════════

def test_D2B2_T13_admin_refresh_no_token(monkeypatch):
    client = _as_app(False, FakeSB([]), monkeypatch)
    r = client.post("/admin/stats/refresh")
    assert r.status_code == 401, f"미인증 /admin/stats/refresh → 기대 401, 실제 {r.status_code}"


def test_D2B2_T14_admin_refresh_company_scope_403(monkeypatch):
    client = _as_app(_COMPANY_USER, FakeSB([]), monkeypatch)
    r = client.post("/admin/stats/refresh")
    assert r.status_code == 403, f"COMPANY 스코프 /admin/stats/refresh → 기대 403, 실제 {r.status_code}"


def test_D2B2_T15_admin_refresh_all_scope_200(monkeypatch):
    client = _as_app(_ALL_USER, FakeSB([]), monkeypatch)
    r = client.post("/admin/stats/refresh")
    assert r.status_code == 200, f"ALL 스코프 /admin/stats/refresh → 기대 200, 실제 {r.status_code}: {r.text}"


# ════════════════════════════════════════════════════════════════
# 소스 정적 검증 (원본 S01~S04)
# ════════════════════════════════════════════════════════════════

def test_D2B2_S01_de_metrics_has_auth():
    assert "get_current_user" in _DE_SRC
    assert "_require_admin" in _DE_SRC


def test_D2B2_S02_de_factory_metrics_has_scope():
    # FIX-R1: _ensure_own_company 제거, 명시적 스코프 분기 존재 확인
    assert "ASSIGNED" in _DE_SRC, "명시적 ASSIGNED 거부 분기 없음"
    assert "PLATFORM" in _DE_SRC, "명시적 PLATFORM 거부 분기 없음"
    assert "role_data_scope" in _DE_SRC, "role_data_scope 직접 조회 없음"


def test_D2B2_S03_admin_stats_get_has_auth():
    assert "get_current_user" in _AS_SRC
    assert "_require_admin" in _AS_SRC


def test_D2B2_S04_admin_stats_refresh_has_auth():
    assert "Depends(get_current_user)" in _AS_SRC
    assert "_require_admin" in _AS_SRC


# ════════════════════════════════════════════════════════════════
# R1 보강 케이스 — 공장별 메트릭 스코프 매트릭스
# ════════════════════════════════════════════════════════════════

def test_D2B2_R01_team_own_factory_200(monkeypatch):
    """TEAM 스코프 + 자기 배정 공장 → 200."""
    client = _de_app(_TEAM_USER, FakeSB(_seed()), monkeypatch)
    r = client.get(f"/document-engine/metrics/factory/{_FID_OWN}")
    assert r.status_code == 200, f"TEAM 자기 factory → 기대 200, 실제 {r.status_code}: {r.text}"


def test_D2B2_R02_team_same_company_other_factory_404(monkeypatch):
    """TEAM 스코프 + 같은 회사 다른 공장 → 404."""
    client = _de_app(_TEAM_USER, FakeSB(_seed()), monkeypatch)
    r = client.get(f"/document-engine/metrics/factory/{_FID_SAME_CO_OTHER}")
    assert r.status_code == 404, f"TEAM 같은 회사 타 factory → 기대 404, 실제 {r.status_code}"


def test_D2B2_R03_team_no_factory_assigned_denied(monkeypatch):
    """TEAM 스코프 + factory_id 미배정 → 거부 (404)."""
    client = _de_app(_TEAM_USER_NO_FAC, FakeSB(_seed()), monkeypatch)
    r = client.get(f"/document-engine/metrics/factory/{_FID_OWN}")
    assert r.status_code in (403, 404), f"TEAM factory 미배정 → 기대 403/404, 실제 {r.status_code}"


def test_D2B2_R04_assigned_same_company_factory_403(monkeypatch):
    """ASSIGNED + 자사 공장 → 기본 거부 (403)."""
    client = _de_app(_ASSIGNED_USER, FakeSB(_seed()), monkeypatch)
    r = client.get(f"/document-engine/metrics/factory/{_FID_OWN}")
    assert r.status_code == 403, f"ASSIGNED 자사 factory → 기대 403, 실제 {r.status_code}"


def test_D2B2_R05_assigned_other_company_factory_403(monkeypatch):
    """ASSIGNED + 타사 공장 → 기본 거부 (403)."""
    client = _de_app(_ASSIGNED_USER, FakeSB(_seed()), monkeypatch)
    r = client.get(f"/document-engine/metrics/factory/{_FID_OTHER}")
    assert r.status_code == 403, f"ASSIGNED 타사 factory → 기대 403, 실제 {r.status_code}"


def test_D2B2_R06_platform_company_match_403(monkeypatch):
    """PLATFORM + company_id 일치 → 기본 거부 (403)."""
    client = _de_app(_PLATFORM_USER_OWN, FakeSB(_seed()), monkeypatch)
    r = client.get(f"/document-engine/metrics/factory/{_FID_OWN}")
    assert r.status_code == 403, f"PLATFORM 회사일치 → 기대 403, 실제 {r.status_code}"


def test_D2B2_R07_platform_no_company_403(monkeypatch):
    """PLATFORM + company_id 없음 → 기본 거부 (403)."""
    client = _de_app(_PLATFORM_USER_NONE, FakeSB(_seed()), monkeypatch)
    r = client.get(f"/document-engine/metrics/factory/{_FID_OWN}")
    assert r.status_code == 403, f"PLATFORM 회사없음 → 기대 403, 실제 {r.status_code}"


def test_D2B2_R08_unknown_scope_403(monkeypatch):
    """UNKNOWN scope (role_data_scope에 매핑 없음) → 403."""
    client = _de_app(_UNKNOWN_USER, FakeSB(_seed()), monkeypatch)
    r = client.get(f"/document-engine/metrics/factory/{_FID_OWN}")
    assert r.status_code == 403, f"UNKNOWN scope → 기대 403, 실제 {r.status_code}"


def test_D2B2_R09_scope_no_record_403(monkeypatch):
    """role_data_scope 레코드 없음 → 403 (FAIL-CLOSED)."""
    # 빈 scope_map → 모든 role_code에서 빈 데이터 반환
    fake = FakeSB(_seed(), scope_map={})
    client = _de_app(_COMPANY_USER, fake, monkeypatch)
    r = client.get(f"/document-engine/metrics/factory/{_FID_OWN}")
    assert r.status_code == 403, f"scope 레코드 없음 → 기대 403, 실제 {r.status_code}"


def test_D2B2_R10_scope_query_exception_403(monkeypatch):
    """role_data_scope 조회 예외 → 403 (FAIL-CLOSED)."""
    fake = FakeSB(_seed(), scope_exception=RuntimeError("DB connection error"))
    client = _de_app(_COMPANY_USER, fake, monkeypatch)
    r = client.get(f"/document-engine/metrics/factory/{_FID_OWN}")
    assert r.status_code == 403, f"scope 조회 예외 → 기대 403, 실제 {r.status_code}"


def test_D2B2_R11_factory_no_company_id_404(monkeypatch):
    """factory 레코드의 company_id가 None → 404."""
    client = _de_app(_ALL_USER, FakeSB(_seed()), monkeypatch)
    r = client.get(f"/document-engine/metrics/factory/{_FID_NO_CO}")
    assert r.status_code == 404, f"factory company_id=None → 기대 404, 실제 {r.status_code}"


def test_D2B2_R12_invalid_uuid_format_422(monkeypatch):
    """잘못된 UUID 형식 → 422."""
    client = _de_app(_ALL_USER, FakeSB([]), monkeypatch)
    r = client.get("/document-engine/metrics/factory/not-a-uuid")
    assert r.status_code == 422, f"잘못된 UUID → 기대 422, 실제 {r.status_code}"


def test_D2B2_R13_nonexistent_uuid_404(monkeypatch):
    """올바른 UUID 형식이지만 DB에 없는 factory → 404."""
    client = _de_app(_ALL_USER, FakeSB([]), monkeypatch)
    r = client.get(f"/document-engine/metrics/factory/{_FID_NONEXISTENT}")
    assert r.status_code == 404, f"존재하지 않는 UUID factory → 기대 404, 실제 {r.status_code}"


def test_D2B2_R14_other_company_zero_service_calls(monkeypatch):
    """타사 factory 접근 시 svc.get_metrics_by_factory 호출 0회."""
    calls: list = []
    client = _de_app(_COMPANY_USER, FakeSB(_seed()), monkeypatch, call_counter=calls)
    r = client.get(f"/document-engine/metrics/factory/{_FID_OTHER}")
    assert r.status_code == 404
    assert len(calls) == 0, f"타사 요청 시 svc 호출 발생: {calls}"


def test_D2B2_R15_insufficient_scope_zero_service_calls(monkeypatch):
    """ASSIGNED 권한 부족 시 svc.get_metrics_by_factory 호출 0회."""
    calls: list = []
    client = _de_app(_ASSIGNED_USER, FakeSB(_seed()), monkeypatch, call_counter=calls)
    r = client.get(f"/document-engine/metrics/factory/{_FID_OWN}")
    assert r.status_code == 403
    assert len(calls) == 0, f"권한 부족 시 svc 호출 발생: {calls}"


def test_D2B2_R16_valid_request_one_service_call(monkeypatch):
    """정상 권한(COMPANY + 자사) 시 svc.get_metrics_by_factory 정확히 1회 호출."""
    calls: list = []
    client = _de_app(_COMPANY_USER, FakeSB(_seed()), monkeypatch, call_counter=calls)
    r = client.get(f"/document-engine/metrics/factory/{_FID_OWN}")
    assert r.status_code == 200, f"정상 요청 → 기대 200, 실제 {r.status_code}: {r.text}"
    assert len(calls) == 1, f"svc 호출 횟수 → 기대 1, 실제 {len(calls)}"


def test_D2B2_R17_admin_api_regression(monkeypatch):
    """기존 3개 관리자 전용 API 회귀 확인."""
    # GET /document-engine/metrics
    de_client_no_token = _de_app(False, FakeSB([]), monkeypatch)
    assert de_client_no_token.get("/document-engine/metrics").status_code == 401

    de_client_co = _de_app(_COMPANY_USER, FakeSB([]), monkeypatch)
    assert de_client_co.get("/document-engine/metrics").status_code == 403

    de_client_all = _de_app(_ALL_USER, FakeSB([]), monkeypatch)
    assert de_client_all.get("/document-engine/metrics").status_code == 200

    # GET /admin/stats
    as_no_token = _as_app(False, FakeSB([]), monkeypatch)
    assert as_no_token.get("/admin/stats").status_code == 401

    as_co = _as_app(_COMPANY_USER, FakeSB([]), monkeypatch)
    assert as_co.get("/admin/stats").status_code == 403

    as_all = _as_app(_ALL_USER, FakeSB([]), monkeypatch)
    assert as_all.get("/admin/stats").status_code == 200

    # POST /admin/stats/refresh
    as_no_token2 = _as_app(False, FakeSB([]), monkeypatch)
    assert as_no_token2.post("/admin/stats/refresh").status_code == 401

    as_co2 = _as_app(_COMPANY_USER, FakeSB([]), monkeypatch)
    assert as_co2.post("/admin/stats/refresh").status_code == 403

    as_all2 = _as_app(_ALL_USER, FakeSB([]), monkeypatch)
    assert as_all2.post("/admin/stats/refresh").status_code == 200
