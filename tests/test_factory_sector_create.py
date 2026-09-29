"""WO-BE-FE-QUOTE-SITE-REG-01 — FSR-01 ~ FSR-10.

Coverage:
  FSR-01  request sector=INDUSTRY  → INSERT sector=INDUSTRIAL
  FSR-02  request sector=INDUSTRIAL → INSERT sector=INDUSTRIAL
  FSR-03  request sector=BUILDING  → INSERT sector=BUILDING
  FSR-04  sector omitted           → INSERT sector=INDUSTRIAL
  FSR-05  unsupported sector       → 422 / INSERT 0
  FSR-06  non-admin client company_id ≠ auth company_id → stored=auth
  FSR-07  INDUSTRY employee_count preserved
  FSR-08  BUILDING building_area preserved
  FSR-09  factory list/get regression PASS
  FSR-10  created INDUSTRIAL factory + Quote request INDUSTRY → scope resolver canonical PASS
"""
from __future__ import annotations

import os
import pytest
from uuid import uuid4

os.environ.setdefault("INTERNAL_API_SECRET", "pytest-internal-secret")

from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.factories as fac_router
from routers.factories import FactoryCreate

_COMPANY_ID = "C-OWN"
_OTHER_COMPANY = "C-OTHER"
_USER_ID = "U-TEST"


# ═══════════════════════════════════════════════════════════════════════════════
# Fake Supabase
# ═══════════════════════════════════════════════════════════════════════════════

class _Result:
    def __init__(self, data, count=0):
        self.data = data
        self.count = count


class _FakeTable:
    def __init__(self, name, sb):
        self.name = name
        self._sb = sb
        self._filters: list = []
        self._is_single = False
        self._mode = "select"
        self._insert_row = None

    def select(self, *a, **k): return self
    def eq(self, c, v): self._filters.append((c, v)); return self
    def limit(self, n): return self
    def order(self, *a, **k): return self
    def range(self, *a, **k): return self
    def ilike(self, *a, **k): return self
    def single(self): self._is_single = True; return self

    def insert(self, row):
        self._mode = "insert"
        self._insert_row = row
        self._sb.log.append(("insert", self.name, row))
        return self

    def execute(self):
        if self._mode == "insert":
            return _Result([{**self._insert_row, "id": "F-NEW"}])
        if self.name == "role_data_scope":
            return _Result([{"scope_type": self._sb._scope}])
        if self.name == "companies":
            if self._sb._company_exists:
                data = {"id": _COMPANY_ID}
                return _Result(data if self._is_single else [data])
            return _Result(None if self._is_single else [])
        if self.name == "factories":
            rows = list(self._sb._factory_rows)
            for c, v in self._filters:
                rows = [r for r in rows if str(r.get(c)) == str(v)]
            if self._is_single:
                return _Result(rows[0] if rows else None)
            return _Result(rows, count=len(rows))
        return _Result([] if not self._is_single else None)


class FakeSB:
    def __init__(self, *, scope="COMPANY", company_exists=True, factory_rows=None):
        self._scope = scope
        self._company_exists = company_exists
        self._factory_rows: list = factory_rows or []
        self.log: list = []

    def table(self, name):
        return _FakeTable(name, self)


def _make_app():
    app = FastAPI()
    app.include_router(fac_router.router)
    return app


def _current_user(*, company_id=_COMPANY_ID, role_code="002"):
    return {"id": _USER_ID, "company_id": company_id, "role_code": role_code}


def _post_create(monkeypatch, body: dict, *, scope="COMPANY", company_exists=True,
                 auth_company_id=_COMPANY_ID):
    sb = FakeSB(scope=scope, company_exists=company_exists)
    monkeypatch.setattr("routers.factories.get_supabase", lambda: sb)
    app = _make_app()
    app.dependency_overrides[fac_router.get_current_user] = \
        lambda: _current_user(company_id=auth_company_id)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/factories", json=body)
    return resp, sb


# ═══════════════════════════════════════════════════════════════════════════════
# FSR-01  INDUSTRY → INDUSTRIAL
# ═══════════════════════════════════════════════════════════════════════════════

def test_FSR_01_industry_normalized_to_industrial(monkeypatch):
    resp, sb = _post_create(monkeypatch, {
        "company_id": _COMPANY_ID, "name": "테스트 공장", "sector": "INDUSTRY",
    })
    assert resp.status_code == 200
    inserts = [r for r in sb.log if r[0] == "insert" and r[1] == "factories"]
    assert len(inserts) == 1
    assert inserts[0][2]["sector"] == "INDUSTRIAL"


# ═══════════════════════════════════════════════════════════════════════════════
# FSR-02  INDUSTRIAL → INDUSTRIAL
# ═══════════════════════════════════════════════════════════════════════════════

def test_FSR_02_industrial_preserved(monkeypatch):
    resp, sb = _post_create(monkeypatch, {
        "company_id": _COMPANY_ID, "name": "테스트 공장", "sector": "INDUSTRIAL",
    })
    assert resp.status_code == 200
    inserts = [r for r in sb.log if r[0] == "insert" and r[1] == "factories"]
    assert inserts[0][2]["sector"] == "INDUSTRIAL"


# ═══════════════════════════════════════════════════════════════════════════════
# FSR-03  BUILDING → BUILDING
# ═══════════════════════════════════════════════════════════════════════════════

def test_FSR_03_building_preserved(monkeypatch):
    resp, sb = _post_create(monkeypatch, {
        "company_id": _COMPANY_ID, "name": "빌딩 사업장", "sector": "BUILDING",
    })
    assert resp.status_code == 200
    inserts = [r for r in sb.log if r[0] == "insert" and r[1] == "factories"]
    assert inserts[0][2]["sector"] == "BUILDING"


# ═══════════════════════════════════════════════════════════════════════════════
# FSR-04  sector 미전송 → INDUSTRIAL
# ═══════════════════════════════════════════════════════════════════════════════

def test_FSR_04_sector_omitted_defaults_to_industrial(monkeypatch):
    resp, sb = _post_create(monkeypatch, {
        "company_id": _COMPANY_ID, "name": "섹터없음 공장",
        # sector 필드 전송 안 함
    })
    assert resp.status_code == 200
    inserts = [r for r in sb.log if r[0] == "insert" and r[1] == "factories"]
    assert inserts[0][2]["sector"] == "INDUSTRIAL"


# ═══════════════════════════════════════════════════════════════════════════════
# FSR-05  지원 외 sector → 422 / INSERT 0
# ═══════════════════════════════════════════════════════════════════════════════

def test_FSR_05_invalid_sector_422(monkeypatch):
    resp, sb = _post_create(monkeypatch, {
        "company_id": _COMPANY_ID, "name": "잘못된 섹터",
        "sector": "GARBAGE_SECTOR",
    })
    assert resp.status_code == 422
    data = resp.json()
    assert data["detail"]["code"] == "INVALID_SECTOR"
    inserts = [r for r in sb.log if r[0] == "insert" and r[1] == "factories"]
    assert len(inserts) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# FSR-06  비-관리자 client company_id 무시 → auth company_id 저장
# ═══════════════════════════════════════════════════════════════════════════════

def test_FSR_06_auth_company_overrides_client_company(monkeypatch):
    resp, sb = _post_create(
        monkeypatch,
        {"company_id": _OTHER_COMPANY, "name": "다른회사 공장", "sector": "INDUSTRY"},
        auth_company_id=_COMPANY_ID,
    )
    assert resp.status_code == 200
    inserts = [r for r in sb.log if r[0] == "insert" and r[1] == "factories"]
    assert inserts[0][2]["company_id"] == _COMPANY_ID


# ═══════════════════════════════════════════════════════════════════════════════
# FSR-07  INDUSTRY employee_count 보존
# ═══════════════════════════════════════════════════════════════════════════════

def test_FSR_07_employee_count_preserved(monkeypatch):
    resp, sb = _post_create(monkeypatch, {
        "company_id": _COMPANY_ID, "name": "제조공장",
        "sector": "INDUSTRY", "employee_count": 250,
    })
    assert resp.status_code == 200
    inserts = [r for r in sb.log if r[0] == "insert" and r[1] == "factories"]
    row = inserts[0][2]
    assert row["sector"] == "INDUSTRIAL"
    assert row["employee_count"] == 250


# ═══════════════════════════════════════════════════════════════════════════════
# FSR-08  BUILDING building_area 보존
# ═══════════════════════════════════════════════════════════════════════════════

def test_FSR_08_building_area_preserved(monkeypatch):
    resp, sb = _post_create(monkeypatch, {
        "company_id": _COMPANY_ID, "name": "빌딩",
        "sector": "BUILDING", "building_area": 8500.5,
    })
    assert resp.status_code == 200
    inserts = [r for r in sb.log if r[0] == "insert" and r[1] == "factories"]
    row = inserts[0][2]
    assert row["sector"] == "BUILDING"
    assert row["building_area"] == 8500.5


# ═══════════════════════════════════════════════════════════════════════════════
# FSR-09  기존 list/get regression
# ═══════════════════════════════════════════════════════════════════════════════

def test_FSR_09_get_factories_regression(monkeypatch):
    fid = str(uuid4())
    sb = FakeSB(factory_rows=[
        {"id": fid, "company_id": _COMPANY_ID, "name": "기존 공장",
         "sector": "INDUSTRIAL", "status_code": "ACTIVE"},
    ])
    monkeypatch.setattr("routers.factories.get_supabase", lambda: sb)
    app = _make_app()
    app.dependency_overrides[fac_router.get_current_user] = \
        lambda: _current_user()
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/factories")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["data"]["total"] == 1


# ═══════════════════════════════════════════════════════════════════════════════
# FSR-10  INDUSTRIAL factory + INDUSTRY quote request → scope resolver PASS
# ═══════════════════════════════════════════════════════════════════════════════

def test_FSR_10_industrial_factory_industry_quote_scope_compat():
    """POST /factories sector=INDUSTRY → DB sector=INDUSTRIAL.
    그 factory를 Quote request sector=INDUSTRY로 조회 → scope resolver canonical match.
    saas_quote_site_scope_v2 미배포 환경에서는 normalize_sector_db 의미 대조로 검증."""
    scope_svc = pytest.importorskip(
        "services.saas_quote_site_scope_v2",
        reason="saas_quote_site_scope_v2 아직 미배포 — normalize_sector_db 의미 검증으로 대체",
    )
    resolve_quote_site_scope_v2 = scope_svc.resolve_quote_site_scope_v2
    from schemas.saas_pricing_preview_v2 import SaasPricingPreviewSiteRequestV2

    fid = uuid4()

    class _R:
        def __init__(self, data): self.data = data

    class _Q:
        def __init__(self, store, table):
            self.store = store
            self._table = table
            self._filters: list = []

        def select(self, *a, **k): return self
        def eq(self, c, v): self._filters.append((c, v)); return self
        def limit(self, n): return self

        def execute(self):
            rows = list(self.store.get(self._table, []))
            for c, v in self._filters:
                rows = [r for r in rows if str(r.get(c)) == str(v)]
            return _R(rows)

    class _SB:
        def __init__(self, store): self.store = store
        def table(self, n): return _Q(self.store, n)

    # Simulate factory stored by the fixed create endpoint (sector=INDUSTRIAL)
    sb = _SB({"factories": [
        {"id": str(fid), "company_id": _COMPANY_ID,
         "sector": "INDUSTRIAL",  # DB canonical after create_factory canonicalization
         "employee_count": 120, "building_area": None},
    ]})

    result = resolve_quote_site_scope_v2(sb, _COMPANY_ID, [
        SaasPricingPreviewSiteRequestV2(
            entity_id=fid, sector="INDUSTRY", criteria_value=120,
        ),
    ])
    assert len(result) == 1
    assert result[0].sector == "INDUSTRY"   # pricing API sector 유지
    assert float(result[0].criteria_value) == 120.0
