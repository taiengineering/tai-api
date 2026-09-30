"""BE01~BE24 — WO-FE-SAFE-01 Member Commercial Contract Read.

FakeSupabase + real service function. DB 없음. pricing 없음.

케이스 매트릭스:
  AUTH       BE01 GET /me/commercial/contract 존재
             BE02 client company_id param 없음
             BE03 company_id = auth token only (function sig)
  STATE      BE04 NO_COMPANY → state=NO_COMPANY
             BE05 NO_ACTIVE_SAAS_CONTRACT → state=NO_ACTIVE_CONTRACT
             BE06 AMBIGUOUS → state=ERROR
             BE07 CURRENT_CV_NOT_FOUND → state=ERROR
             BE08 CURRENT_CV_AMBIGUOUS → state=ERROR
             BE09 CURRENT_CV_SCHEMA_INVALID → state=ERROR
  ACTIVE     BE10 ACTIVE → contract exact read by canonical contract_id
             BE11 ACTIVE → CV exact read by canonical cv_id
             BE12 ACTIVE → site scopes by canonical cv_id
             BE13 ACTIVE → contract.company_id matches
  ENTITY     BE14 factory scope → entity_name from factories
             BE15 site scope → entity_name from construction_sites
             BE16 factory batch N+1=0 (≤1 factories query)
             BE17 site batch N+1=0 (≤1 construction_sites query)
             BE18 cross-company factory → entity_ref_ok=False
             BE19 missing factory → entity_ref_ok=False
  WRITE      BE20 DB write = 0
             BE21 pricing call = 0 (no price_master in query_log)
             BE22 renewal call = 0 (no pricing_composer in source)
  STATIC     BE23 admin commercial API not imported in member_commercial_svc
             BE24 _fetch_all_cvs not imported in member_commercial_svc
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from unittest.mock import patch, MagicMock

import pytest

os.environ.setdefault("INTERNAL_API_SECRET", "pytest-internal-secret")

from services import member_commercial_svc as svc
from services.saas_entitlement_runtime_v2 import SaasEntitlementRuntimeError


# ── FakeSupabase ──────────────────────────────────────────────────────────────

class _Result:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count if count is not None else (len(data) if data else 0)


class _Query:
    def __init__(self, store: dict, table: str, write_log: list, query_log: list):
        self._store = store
        self._table = table
        self._wl = write_log
        self._ql = query_log
        self._op = "select"
        self._filters: list = []
        self._in_filters: list = []

    def select(self, cols="*", *a, **kw):
        return self

    def insert(self, row):
        self._op = "insert"; self._payload = row; return self

    def update(self, patch):
        self._op = "update"; self._payload = patch; return self

    def delete(self):
        self._op = "delete"; return self

    def eq(self, c, v):     self._filters.append(("eq", c, v)); return self
    def in_(self, c, vs):   self._in_filters.append((c, list(vs))); return self
    def limit(self, n):     return self
    def range(self, s, e):  return self
    def order(self, *a, **kw): return self

    def _match(self, row: dict) -> bool:
        for op, c, v in self._filters:
            if op == "eq" and str(row.get(c, "")) != str(v):
                return False
        for c, vs in self._in_filters:
            if str(row.get(c, "")) not in [str(x) for x in vs]:
                return False
        return True

    def execute(self) -> _Result:
        if self._op in ("insert", "update", "delete"):
            self._wl.append(self._op)
            return _Result([], 0)
        self._ql.append(self._table)
        rows = [r for r in (self._store.get(self._table) or []) if self._match(r)]
        return _Result(rows)


class FakeSB:
    def __init__(self, store: dict):
        self._store = store
        self.write_log: list = []
        self.query_log: list = []

    def table(self, name: str) -> _Query:
        return _Query(self._store, name, self.write_log, self.query_log)


def _uid() -> str:
    return str(uuid.uuid4())


def _now_iso(offset_days: int = 0) -> str:
    return (datetime.now(tz=timezone.utc) + timedelta(days=offset_days)).isoformat()


def _make_contract(company_id: str, contract_id: str = None) -> dict:
    cid = contract_id or _uid()
    return {
        "id": cid,
        "contract_no": f"CTR-{cid[:8]}",
        "company_id": company_id,
        "quote_id": _uid(),
        "service_type": "SAAS_INDUSTRY",
        "status_code": "ACTIVE",
        "is_active": True,
        "start_date": _now_iso(-30)[:10],
        "end_date": _now_iso(335)[:10],
        "contract_amount": 1200000,
        "vat_amount": 120000,
        "total_amount": 1320000,
        "paid_amount": 1320000,
        "paid_at": _now_iso(-30),
        "created_at": _now_iso(-30),
    }


def _make_cv(contract_id: str, cv_id: str = None, product_tier: str = "MANAGER") -> dict:
    return {
        "id": cv_id or _uid(),
        "contract_id": contract_id,
        "version_no": 1,
        "commercial_schema_version": "v2",
        "product_tier": product_tier,
        "pricing_mode": "BAND",
        "worker_capacity": 0,
        "payment_months": 12,
        "pricing_result_status": "OK",
        "pricing_policy_version": "v3",
        "effective_from": _now_iso(-30),
        "superseded_at": None,
        "created_at": _now_iso(-30),
    }


def _make_scope(cv_id: str, entity_type: str = "factory", entity_id: str = None) -> dict:
    return {
        "id": _uid(),
        "commercial_version_id": cv_id,
        "entity_type": entity_type,
        "entity_id": entity_id or _uid(),
        "sector": "INDUSTRY",
        "base_band_code": "BAND_A",
        "created_at": _now_iso(),
    }


class _FakeResolution:
    def __init__(self, contract_id: str, cv_id: str, cv_no: int = 1, product_tier: str = "MANAGER"):
        self.contract_id = contract_id
        self.commercial_version_id = cv_id
        self.commercial_version_no = cv_no
        self.product_tier = product_tier


# ── STATIC CHECKS ─────────────────────────────────────────────────────────────

def test_be01_endpoint_exists():
    """BE01 GET /me/commercial/contract 존재."""
    import routers.member_commercial as rc
    assert rc.router is not None
    routes = [r.path for r in rc.router.routes]
    assert "/me/commercial/contract" in routes


def test_be02_no_client_company_id_param():
    """BE02 client company_id param = 없음 — endpoint 시그니처에 company_id query param 없음."""
    import inspect
    import routers.member_commercial as rc
    fn = rc.get_commercial_contract
    params = inspect.signature(fn).parameters
    assert "company_id" not in params


def test_be03_function_takes_company_id_from_user():
    """BE03 svc.get_member_commercial_contract(supabase, company_id) — company_id는 auth 파생."""
    import inspect
    params = inspect.signature(svc.get_member_commercial_contract).parameters
    assert "company_id" in params
    assert "supabase" in params
    assert "current_user" not in params


# ── STATE MACHINE ─────────────────────────────────────────────────────────────

def test_be04_no_company_state():
    """BE04 company_id=None → state=NO_COMPANY."""
    sb = FakeSB({})
    result = svc.get_member_commercial_contract(sb, None)
    assert result["state"] == "NO_COMPANY"
    assert result["contract"] is None
    assert result["commercial_version"] is None
    assert result["site_scopes"] == []


def test_be04b_empty_company_state():
    """BE04b company_id='' → state=NO_COMPANY."""
    sb = FakeSB({})
    result = svc.get_member_commercial_contract(sb, "")
    assert result["state"] == "NO_COMPANY"


def test_be05_no_active_contract():
    """BE05 NO_ACTIVE_SAAS_CONTRACT → state=NO_ACTIVE_CONTRACT."""
    sb = FakeSB({})
    with patch("services.member_commercial_svc.resolve_saas_entitlement_context_v2",
               side_effect=SaasEntitlementRuntimeError("NO_ACTIVE_SAAS_CONTRACT")):
        result = svc.get_member_commercial_contract(sb, "cmp-1")
    assert result["state"] == "NO_ACTIVE_CONTRACT"
    assert result["error_code"] == "NO_ACTIVE_SAAS_CONTRACT"


def test_be06_ambiguous_active_contract():
    """BE06 AMBIGUOUS_ACTIVE_SAAS_CONTRACT → state=ERROR."""
    sb = FakeSB({})
    with patch("services.member_commercial_svc.resolve_saas_entitlement_context_v2",
               side_effect=SaasEntitlementRuntimeError("AMBIGUOUS_ACTIVE_SAAS_CONTRACT")):
        result = svc.get_member_commercial_contract(sb, "cmp-1")
    assert result["state"] == "ERROR"
    assert result["error_code"] == "AMBIGUOUS_ACTIVE_SAAS_CONTRACT"


def test_be07_current_cv_not_found():
    """BE07 CURRENT_CV_NOT_FOUND → state=ERROR."""
    sb = FakeSB({})
    with patch("services.member_commercial_svc.resolve_saas_entitlement_context_v2",
               side_effect=SaasEntitlementRuntimeError("CURRENT_CV_NOT_FOUND")):
        result = svc.get_member_commercial_contract(sb, "cmp-1")
    assert result["state"] == "ERROR"
    assert result["error_code"] == "CURRENT_CV_NOT_FOUND"


def test_be08_current_cv_ambiguous():
    """BE08 CURRENT_CV_AMBIGUOUS → state=ERROR."""
    sb = FakeSB({})
    with patch("services.member_commercial_svc.resolve_saas_entitlement_context_v2",
               side_effect=SaasEntitlementRuntimeError("CURRENT_CV_AMBIGUOUS")):
        result = svc.get_member_commercial_contract(sb, "cmp-1")
    assert result["state"] == "ERROR"


def test_be09_current_cv_schema_invalid():
    """BE09 CURRENT_CV_SCHEMA_INVALID → state=ERROR."""
    sb = FakeSB({})
    with patch("services.member_commercial_svc.resolve_saas_entitlement_context_v2",
               side_effect=SaasEntitlementRuntimeError("CURRENT_CV_SCHEMA_INVALID")):
        result = svc.get_member_commercial_contract(sb, "cmp-1")
    assert result["state"] == "ERROR"


# ── ACTIVE STATE — EXACT READS ────────────────────────────────────────────────

def test_be10_contract_exact_canonical_id():
    """BE10 ACTIVE → contract read by canonical contract_id only."""
    company_id = _uid()
    contract_id = _uid()
    cv_id = _uid()
    ct = _make_contract(company_id, contract_id)
    cv = _make_cv(contract_id, cv_id)
    sb = FakeSB({
        "contracts": [ct],
        "saas_contract_commercial_versions": [cv],
        "saas_contract_site_scopes": [],
    })
    resolution = _FakeResolution(contract_id, cv_id)
    with patch("services.member_commercial_svc.resolve_saas_entitlement_context_v2",
               return_value=resolution):
        result = svc.get_member_commercial_contract(sb, company_id)
    assert result["state"] == "ACTIVE"
    assert result["contract"]["id"] == contract_id


def test_be11_cv_exact_canonical_id():
    """BE11 ACTIVE → CV read by canonical commercial_version_id only."""
    company_id = _uid()
    contract_id = _uid()
    cv_id = _uid()
    ct = _make_contract(company_id, contract_id)
    cv = _make_cv(contract_id, cv_id, product_tier="FIELD")
    sb = FakeSB({
        "contracts": [ct],
        "saas_contract_commercial_versions": [cv],
        "saas_contract_site_scopes": [],
    })
    resolution = _FakeResolution(contract_id, cv_id)
    with patch("services.member_commercial_svc.resolve_saas_entitlement_context_v2",
               return_value=resolution):
        result = svc.get_member_commercial_contract(sb, company_id)
    assert result["commercial_version"]["id"] == cv_id
    assert result["commercial_version"]["product_tier"] == "FIELD"


def test_be12_site_scopes_by_canonical_cv_id():
    """BE12 ACTIVE → site scopes filtered by canonical cv_id."""
    company_id = _uid()
    contract_id = _uid()
    cv_id = _uid()
    other_cv_id = _uid()
    ct = _make_contract(company_id, contract_id)
    cv = _make_cv(contract_id, cv_id)
    scope_match = _make_scope(cv_id, "factory")
    scope_other = _make_scope(other_cv_id, "factory")
    factory_id = scope_match["entity_id"]
    sb = FakeSB({
        "contracts": [ct],
        "saas_contract_commercial_versions": [cv],
        "saas_contract_site_scopes": [scope_match, scope_other],
        "factories": [{"id": factory_id, "company_id": company_id, "name": "공장A"}],
    })
    resolution = _FakeResolution(contract_id, cv_id)
    with patch("services.member_commercial_svc.resolve_saas_entitlement_context_v2",
               return_value=resolution):
        result = svc.get_member_commercial_contract(sb, company_id)
    scope_ids = [s["id"] for s in result["site_scopes"]]
    assert scope_match["id"] in scope_ids
    assert scope_other["id"] not in scope_ids


def test_be13_contract_company_id_matches():
    """BE13 contract.company_id must match auth company_id."""
    company_id = _uid()
    other_company_id = _uid()
    contract_id = _uid()
    cv_id = _uid()
    # contract belongs to other company (should not happen in canonical path but guard exists)
    ct = _make_contract(other_company_id, contract_id)
    cv = _make_cv(contract_id, cv_id)
    sb = FakeSB({
        "contracts": [ct],
        "saas_contract_commercial_versions": [cv],
        "saas_contract_site_scopes": [],
    })
    resolution = _FakeResolution(contract_id, cv_id)
    with patch("services.member_commercial_svc.resolve_saas_entitlement_context_v2",
               return_value=resolution):
        result = svc.get_member_commercial_contract(sb, company_id)
    assert result["state"] == "ERROR"
    assert result["contract"] is None


# ── ENTITY NAME BATCH ─────────────────────────────────────────────────────────

def test_be14_factory_entity_name():
    """BE14 factory scope → entity_name from factories.name."""
    company_id = _uid()
    contract_id = _uid()
    cv_id = _uid()
    factory_id = _uid()
    ct = _make_contract(company_id, contract_id)
    cv = _make_cv(contract_id, cv_id)
    scope = _make_scope(cv_id, "factory", factory_id)
    sb = FakeSB({
        "contracts": [ct],
        "saas_contract_commercial_versions": [cv],
        "saas_contract_site_scopes": [scope],
        "factories": [{"id": factory_id, "company_id": company_id, "name": "테스트공장"}],
    })
    resolution = _FakeResolution(contract_id, cv_id)
    with patch("services.member_commercial_svc.resolve_saas_entitlement_context_v2",
               return_value=resolution):
        result = svc.get_member_commercial_contract(sb, company_id)
    assert result["site_scopes"][0]["entity_name"] == "테스트공장"
    assert result["site_scopes"][0]["entity_ref_ok"] is True


def test_be15_site_entity_name():
    """BE15 site scope → entity_name from construction_sites.site_name."""
    company_id = _uid()
    contract_id = _uid()
    cv_id = _uid()
    site_id = _uid()
    ct = _make_contract(company_id, contract_id)
    cv = _make_cv(contract_id, cv_id)
    scope = _make_scope(cv_id, "site", site_id)
    sb = FakeSB({
        "contracts": [ct],
        "saas_contract_commercial_versions": [cv],
        "saas_contract_site_scopes": [scope],
        "construction_sites": [{"id": site_id, "company_id": company_id, "site_name": "테스트현장"}],
    })
    resolution = _FakeResolution(contract_id, cv_id)
    with patch("services.member_commercial_svc.resolve_saas_entitlement_context_v2",
               return_value=resolution):
        result = svc.get_member_commercial_contract(sb, company_id)
    assert result["site_scopes"][0]["entity_name"] == "테스트현장"
    assert result["site_scopes"][0]["entity_ref_ok"] is True


def test_be16_factory_batch_n1_zero():
    """BE16 factory batch lookup ≤1 queries (N+1=0)."""
    company_id = _uid()
    contract_id = _uid()
    cv_id = _uid()
    f1, f2, f3 = _uid(), _uid(), _uid()
    ct = _make_contract(company_id, contract_id)
    cv = _make_cv(contract_id, cv_id)
    scopes = [
        _make_scope(cv_id, "factory", f1),
        _make_scope(cv_id, "factory", f2),
        _make_scope(cv_id, "factory", f3),
    ]
    sb = FakeSB({
        "contracts": [ct],
        "saas_contract_commercial_versions": [cv],
        "saas_contract_site_scopes": scopes,
        "factories": [
            {"id": f1, "company_id": company_id, "name": "공장1"},
            {"id": f2, "company_id": company_id, "name": "공장2"},
            {"id": f3, "company_id": company_id, "name": "공장3"},
        ],
    })
    resolution = _FakeResolution(contract_id, cv_id)
    with patch("services.member_commercial_svc.resolve_saas_entitlement_context_v2",
               return_value=resolution):
        svc.get_member_commercial_contract(sb, company_id)
    factory_queries = [q for q in sb.query_log if q == "factories"]
    assert len(factory_queries) <= 1


def test_be17_site_batch_n1_zero():
    """BE17 construction_sites batch lookup ≤1 queries (N+1=0)."""
    company_id = _uid()
    contract_id = _uid()
    cv_id = _uid()
    s1, s2 = _uid(), _uid()
    ct = _make_contract(company_id, contract_id)
    cv = _make_cv(contract_id, cv_id)
    scopes = [
        _make_scope(cv_id, "site", s1),
        _make_scope(cv_id, "site", s2),
    ]
    sb = FakeSB({
        "contracts": [ct],
        "saas_contract_commercial_versions": [cv],
        "saas_contract_site_scopes": scopes,
        "construction_sites": [
            {"id": s1, "company_id": company_id, "site_name": "현장1"},
            {"id": s2, "company_id": company_id, "site_name": "현장2"},
        ],
    })
    resolution = _FakeResolution(contract_id, cv_id)
    with patch("services.member_commercial_svc.resolve_saas_entitlement_context_v2",
               return_value=resolution):
        svc.get_member_commercial_contract(sb, company_id)
    site_queries = [q for q in sb.query_log if q == "construction_sites"]
    assert len(site_queries) <= 1


def test_be18_cross_company_entity():
    """BE18 cross-company factory → entity_ref_ok=False, entity_name=None."""
    company_id = _uid()
    other_company = _uid()
    contract_id = _uid()
    cv_id = _uid()
    factory_id = _uid()
    ct = _make_contract(company_id, contract_id)
    cv = _make_cv(contract_id, cv_id)
    scope = _make_scope(cv_id, "factory", factory_id)
    sb = FakeSB({
        "contracts": [ct],
        "saas_contract_commercial_versions": [cv],
        "saas_contract_site_scopes": [scope],
        "factories": [{"id": factory_id, "company_id": other_company, "name": "타사공장"}],
    })
    resolution = _FakeResolution(contract_id, cv_id)
    with patch("services.member_commercial_svc.resolve_saas_entitlement_context_v2",
               return_value=resolution):
        result = svc.get_member_commercial_contract(sb, company_id)
    assert result["site_scopes"][0]["entity_ref_ok"] is False
    assert result["site_scopes"][0]["entity_name"] is None


def test_be19_missing_entity():
    """BE19 missing factory → entity_ref_ok=False."""
    company_id = _uid()
    contract_id = _uid()
    cv_id = _uid()
    factory_id = _uid()
    ct = _make_contract(company_id, contract_id)
    cv = _make_cv(contract_id, cv_id)
    scope = _make_scope(cv_id, "factory", factory_id)
    sb = FakeSB({
        "contracts": [ct],
        "saas_contract_commercial_versions": [cv],
        "saas_contract_site_scopes": [scope],
        "factories": [],  # missing
    })
    resolution = _FakeResolution(contract_id, cv_id)
    with patch("services.member_commercial_svc.resolve_saas_entitlement_context_v2",
               return_value=resolution):
        result = svc.get_member_commercial_contract(sb, company_id)
    assert result["site_scopes"][0]["entity_ref_ok"] is False


# ── WRITE / PRICING GUARDS ─────────────────────────────────────────────────────

def test_be20_db_write_zero():
    """BE20 DB write = 0 in happy path."""
    company_id = _uid()
    contract_id = _uid()
    cv_id = _uid()
    ct = _make_contract(company_id, contract_id)
    cv = _make_cv(contract_id, cv_id)
    sb = FakeSB({
        "contracts": [ct],
        "saas_contract_commercial_versions": [cv],
        "saas_contract_site_scopes": [],
    })
    resolution = _FakeResolution(contract_id, cv_id)
    with patch("services.member_commercial_svc.resolve_saas_entitlement_context_v2",
               return_value=resolution):
        svc.get_member_commercial_contract(sb, company_id)
    assert sb.write_log == []


def test_be21_no_price_master_query():
    """BE21 price_master not queried (pricing call = 0)."""
    company_id = _uid()
    contract_id = _uid()
    cv_id = _uid()
    ct = _make_contract(company_id, contract_id)
    cv = _make_cv(contract_id, cv_id)
    sb = FakeSB({
        "contracts": [ct],
        "saas_contract_commercial_versions": [cv],
        "saas_contract_site_scopes": [],
    })
    resolution = _FakeResolution(contract_id, cv_id)
    with patch("services.member_commercial_svc.resolve_saas_entitlement_context_v2",
               return_value=resolution):
        svc.get_member_commercial_contract(sb, company_id)
    assert "price_master" not in sb.query_log


def test_be22_no_pricing_composer_import():
    """BE22 renewal/pricing composer not imported in member_commercial_svc."""
    import inspect
    src = inspect.getsource(svc)
    assert "saas_pricing_composer" not in src
    assert "preview_saas_price" not in src
    assert "renewal_apply" not in src
    assert "payment_prepare" not in src


# ── STATIC SOURCE CHECKS ──────────────────────────────────────────────────────

def test_be23_no_admin_commercial_import():
    """BE23 admin_commercial API not imported in member_commercial_svc."""
    import inspect
    src = inspect.getsource(svc)
    # 실제 import 구문으로만 체크 (docstring/주석 제외)
    import_lines = [ln for ln in src.splitlines() if ln.strip().startswith("import ") or ln.strip().startswith("from ")]
    assert not any("admin_commercial" in ln for ln in import_lines)


def test_be24_no_fetch_all_cvs_import():
    """BE24 _fetch_all_cvs (private) not imported in member_commercial_svc."""
    import inspect
    src = inspect.getsource(svc)
    import_lines = [ln for ln in src.splitlines() if ln.strip().startswith("import ") or ln.strip().startswith("from ")]
    assert not any("_fetch_all_cvs" in ln for ln in import_lines)
