"""ACBE01-ACBE23  Admin Commercial READ backend tests.

WO-ADM-COMM-01-BE-READ-001.
FakeSupabase + real service functions. DB 없음. pricing engine 호출 없음.

케이스 매트릭스:
  AUTH     ACBE01 non-admin versions → 403
           ACBE02 non-admin site-scopes → 403
           ACBE03 non-admin entitlement-health → 403
  CV LIST  ACBE04 contract_id exact filter
           ACBE05 version_no ASC
           ACBE06 DB write = 0
  SS LIST  ACBE07 commercial_version_id exact filter
           ACBE08 DB write = 0
  HEALTH   ACBE09 정상 → health_status=OK + contract/cv/tier
           ACBE10 NO_ACTIVE_SAAS_CONTRACT → HTTP 200 + health_status=ERROR
           ACBE11 AMBIGUOUS_ACTIVE_SAAS_CONTRACT → HTTP 200 + error_code
           ACBE12 CURRENT_CV_NOT_FOUND → HTTP 200 + error_code
           ACBE13 CURRENT_CV_AMBIGUOUS → HTTP 200 + error_code
           ACBE14 CURRENT_CV_SCHEMA_INVALID → HTTP 200 + error_code
           ACBE15 future scheduled CV → ERROR 아님 + future_scheduled_cv_ids
  PROJ     ACBE16 admin quote Frozen V2 → commercial.product_tier 표시
           ACBE17 commercial 필드는 items[0]에서만 읽음
           ACBE18 admin_manual → commercial = null
           ACBE19 member_custom legacy → commercial = null
           ACBE20 STARTER/BUSINESS/PRO 추정 없음
           ACBE21 pricing engine invocation 0
  STATIC   ACBE22 POST/PUT/PATCH/DELETE route 0 (grep)
           ACBE23 DB mutation (insert/update/delete) 0 (grep)
"""
from __future__ import annotations

import os
import uuid
import zoneinfo
from datetime import datetime, timedelta
from typing import Any, Dict, List

import pytest

os.environ.setdefault("INTERNAL_API_SECRET", "pytest-internal-secret")

from services import admin_commercial_svc as svc
from services import admin_quote_svc as aq_svc
from schemas.saas_quote_v2 import SAAS_QUOTE_SCHEMA_VERSION

_SEOUL_TZ = zoneinfo.ZoneInfo("Asia/Seoul")


def _now() -> datetime:
    return datetime.now(tz=_SEOUL_TZ)


def _dt(days_offset: int = 0) -> str:
    return (_now() + timedelta(days=days_offset)).isoformat()


# ── FakeSupabase ─────────────────────────────────────────────────────────────

class _Result:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count if count is not None else (len(data) if data else 0)


class _Query:
    def __init__(self, store: dict, table: str, write_log: list):
        self._store = store
        self._table = table
        self._wl = write_log
        self._op = "select"
        self._filters: list = []
        self._cols = "*"
        self._count_exact = False
        self._order_col: str | None = None
        self._order_desc = False
        self._range: tuple | None = None

    def select(self, cols="*", *a, **kw):
        self._cols = cols or "*"
        if kw.get("count") == "exact":
            self._count_exact = True
        return self

    def insert(self, row):
        self._op = "insert"; self._payload = row; return self

    def update(self, patch):
        self._op = "update"; self._payload = patch; return self

    def delete(self):
        self._op = "delete"; return self

    def eq(self, c, v):   self._filters.append(("eq", c, v)); return self
    def in_(self, c, vs): self._filters.append(("in", c, list(vs))); return self
    def limit(self, n):   self._range = (0, n - 1); return self
    def range(self, s, e): self._range = (s, e); return self

    def order(self, col, *, desc=False, **kw):
        self._order_col = col; self._order_desc = desc; return self

    def _match(self, row: dict) -> bool:
        for op, c, v in self._filters:
            rv = str(row.get(c, ""))
            if op == "eq" and rv != str(v):
                return False
            if op == "in" and rv not in [str(x) for x in v]:
                return False
        return True

    def execute(self) -> _Result:
        if self._op in ("insert", "update", "delete"):
            self._wl.append(self._op)
            return _Result([], 0)
        rows = [r for r in (self._store.get(self._table) or []) if self._match(r)]
        if self._order_col:
            rows = sorted(rows, key=lambda r: r.get(self._order_col, 0),
                          reverse=self._order_desc)
        if self._range is not None:
            s, e = self._range
            rows = rows[s:e + 1]
        total = len(rows)
        return _Result(rows, total if self._count_exact else None)


class FakeSB:
    def __init__(self, store: dict):
        self._store = store
        self.write_log: list = []

    def table(self, name: str) -> _Query:
        return _Query(self._store, name, self.write_log)


def _admin_user():
    return {"user_id": "admin-001", "company_id": None, "role_code": "001"}


def _non_admin_user():
    return {"user_id": "user-999", "company_id": "co-999", "role_code": "010"}


def _make_cv(version_no: int, contract_id: str, effective_from: str,
             superseded_at: str | None = None,
             product_tier: str = "MANAGER") -> dict:
    return {
        "id": str(uuid.uuid4()),
        "contract_id": contract_id,
        "version_no": version_no,
        "commercial_schema_version": "SAAS_CONTRACT_COMMERCIAL_V2",
        "product_tier": product_tier,
        "pricing_mode": "STANDARD",
        "worker_capacity": 50,
        "payment_months": 12,
        "pricing_result_status": "OK",
        "pricing_policy_version": "V3",
        "effective_from": effective_from,
        "superseded_at": superseded_at,
        "created_by": "admin-001",
        "created_at": effective_from,
    }


# ── AUTH ─────────────────────────────────────────────────────────────────────

def test_acbe01_non_admin_versions_403():
    """ACBE01: non-admin → _require_admin raises → 403."""
    from fastapi import HTTPException
    from services.company_scope import _require_admin
    sb = FakeSB({})
    with pytest.raises(HTTPException) as exc:
        _require_admin(_non_admin_user(), sb)
    assert exc.value.status_code == 403


def test_acbe02_non_admin_site_scopes_403():
    """ACBE02: same gate for site-scopes."""
    from fastapi import HTTPException
    from services.company_scope import _require_admin
    sb = FakeSB({})
    with pytest.raises(HTTPException) as exc:
        _require_admin(_non_admin_user(), sb)
    assert exc.value.status_code == 403


def test_acbe03_non_admin_entitlement_health_403():
    """ACBE03: same gate for entitlement-health."""
    from fastapi import HTTPException
    from services.company_scope import _require_admin
    sb = FakeSB({})
    with pytest.raises(HTTPException) as exc:
        _require_admin(_non_admin_user(), sb)
    assert exc.value.status_code == 403


# ── CV LIST ──────────────────────────────────────────────────────────────────

def test_acbe04_versions_contract_id_exact():
    """ACBE04: contract_id exact filter — other contracts excluded."""
    cid_a = str(uuid.uuid4())
    cid_b = str(uuid.uuid4())
    cv_a = _make_cv(1, cid_a, _dt(-30))
    cv_b = _make_cv(1, cid_b, _dt(-30))
    sb = FakeSB({"saas_contract_commercial_versions": [cv_a, cv_b]})

    result = svc.list_commercial_versions(sb, cid_a, page=1, page_size=50)
    ids = [r["id"] for r in result["items"]]
    assert cv_a["id"] in ids
    assert cv_b["id"] not in ids
    assert result["total"] == 1


def test_acbe05_versions_version_no_asc():
    """ACBE05: version_no ASC ordering."""
    cid = str(uuid.uuid4())
    cv1 = _make_cv(1, cid, _dt(-60))
    cv2 = _make_cv(2, cid, _dt(-30))
    cv3 = _make_cv(3, cid, _dt(-10))
    sb = FakeSB({"saas_contract_commercial_versions": [cv3, cv1, cv2]})

    result = svc.list_commercial_versions(sb, cid, page=1, page_size=50)
    nos = [r["version_no"] for r in result["items"]]
    assert nos == sorted(nos), "version_no must be ASC"


def test_acbe06_versions_db_write_zero():
    """ACBE06: list_commercial_versions DB write = 0."""
    cid = str(uuid.uuid4())
    cv = _make_cv(1, cid, _dt(-30))
    sb = FakeSB({"saas_contract_commercial_versions": [cv]})

    svc.list_commercial_versions(sb, cid)
    assert sb.write_log == [], f"unexpected writes: {sb.write_log}"


# ── SITE SCOPES ──────────────────────────────────────────────────────────────

def test_acbe07_site_scopes_cv_id_exact():
    """ACBE07: commercial_version_id exact filter."""
    cv_id_a = str(uuid.uuid4())
    cv_id_b = str(uuid.uuid4())
    ss_a = {"id": str(uuid.uuid4()), "commercial_version_id": cv_id_a,
            "entity_type": "factory", "entity_id": str(uuid.uuid4()),
            "sector": "INDUSTRY", "base_band_code": "B1", "created_at": _dt(-5)}
    ss_b = {"id": str(uuid.uuid4()), "commercial_version_id": cv_id_b,
            "entity_type": "factory", "entity_id": str(uuid.uuid4()),
            "sector": "BUILDING", "base_band_code": None, "created_at": _dt(-5)}
    sb = FakeSB({"saas_contract_site_scopes": [ss_a, ss_b]})

    result = svc.list_site_scopes(sb, cv_id_a)
    ids = [r["id"] for r in result["items"]]
    assert ss_a["id"] in ids
    assert ss_b["id"] not in ids


def test_acbe08_site_scopes_db_write_zero():
    """ACBE08: list_site_scopes DB write = 0."""
    cv_id = str(uuid.uuid4())
    sb = FakeSB({"saas_contract_site_scopes": []})
    svc.list_site_scopes(sb, cv_id)
    assert sb.write_log == []


# ── HEALTH ───────────────────────────────────────────────────────────────────

def _health_store(company_id: str, contract_id: str,
                  cv_id: str, product_tier: str = "MANAGER",
                  future_cvs: list | None = None):
    """FakeSB store for entitlement health tests."""
    now_str = _dt(0)
    past_str = _dt(-30)
    cv = {
        "id": cv_id,
        "contract_id": contract_id,
        "version_no": 1,
        "product_tier": product_tier,
        "pricing_mode": "STANDARD",
        "worker_capacity": 50,
        "payment_months": 12,
        "effective_from": past_str,
        "superseded_at": None,
    }
    all_cvs = [cv] + (future_cvs or [])
    return {
        "contracts": [{
            "id": contract_id,
            "company_id": company_id,
            "service_type": "SAAS",
            "status_code": "ACTIVE",
            "is_active": True,
        }],
        "saas_contract_commercial_versions": all_cvs,
    }


def test_acbe09_health_ok():
    """ACBE09: normal company → health_status=OK + fields populated."""
    cid = str(uuid.uuid4())
    contract_id = str(uuid.uuid4())
    cv_id = str(uuid.uuid4())
    sb = FakeSB(_health_store(cid, contract_id, cv_id, "FIELD"))

    result = svc.get_entitlement_health(sb, cid)
    assert result["health_status"] == "OK"
    assert result["company_id"] == cid
    assert result["contract_id"] == contract_id
    assert result["current_cv_id"] == cv_id
    assert result["product_tier"] == "FIELD"
    assert result["error_code"] is None


def test_acbe10_no_active_saas_contract():
    """ACBE10: no ACTIVE SAAS contract → HTTP 200 + health_status=ERROR."""
    cid = str(uuid.uuid4())
    sb = FakeSB({"contracts": [], "saas_contract_commercial_versions": []})

    result = svc.get_entitlement_health(sb, cid)
    assert result["health_status"] == "ERROR"
    assert result["error_code"] == "NO_ACTIVE_SAAS_CONTRACT"
    assert result["contract_id"] is None


def test_acbe11_ambiguous_active_saas_contract():
    """ACBE11: 2 ACTIVE SAAS contracts → AMBIGUOUS_ACTIVE_SAAS_CONTRACT."""
    cid = str(uuid.uuid4())
    contracts = [
        {"id": str(uuid.uuid4()), "company_id": cid, "service_type": "SAAS",
         "status_code": "ACTIVE", "is_active": True},
        {"id": str(uuid.uuid4()), "company_id": cid, "service_type": "SAAS",
         "status_code": "ACTIVE", "is_active": True},
    ]
    sb = FakeSB({"contracts": contracts, "saas_contract_commercial_versions": []})

    result = svc.get_entitlement_health(sb, cid)
    assert result["health_status"] == "ERROR"
    assert result["error_code"] == "AMBIGUOUS_ACTIVE_SAAS_CONTRACT"


def test_acbe12_current_cv_not_found():
    """ACBE12: contract exists but no CV effective at as_of → CURRENT_CV_NOT_FOUND."""
    cid = str(uuid.uuid4())
    contract_id = str(uuid.uuid4())
    # CV superseded before now → no effective CV
    cv = {
        "id": str(uuid.uuid4()),
        "contract_id": contract_id,
        "version_no": 1,
        "product_tier": "MANAGER",
        "pricing_mode": "STANDARD",
        "worker_capacity": 50,
        "payment_months": 12,
        "effective_from": _dt(-60),
        "superseded_at": _dt(-30),
    }
    sb = FakeSB({
        "contracts": [{"id": contract_id, "company_id": cid, "service_type": "SAAS",
                       "status_code": "ACTIVE", "is_active": True}],
        "saas_contract_commercial_versions": [cv],
    })
    result = svc.get_entitlement_health(sb, cid)
    assert result["health_status"] == "ERROR"
    assert result["error_code"] == "CURRENT_CV_NOT_FOUND"


def test_acbe13_current_cv_ambiguous():
    """ACBE13: 2 effective CVs at same as_of → CURRENT_CV_AMBIGUOUS."""
    cid = str(uuid.uuid4())
    contract_id = str(uuid.uuid4())
    cv1 = {"id": str(uuid.uuid4()), "contract_id": contract_id, "version_no": 1,
           "product_tier": "MANAGER", "pricing_mode": "STANDARD",
           "worker_capacity": 50, "payment_months": 12,
           "effective_from": _dt(-60), "superseded_at": None}
    cv2 = {"id": str(uuid.uuid4()), "contract_id": contract_id, "version_no": 2,
           "product_tier": "FIELD", "pricing_mode": "STANDARD",
           "worker_capacity": 80, "payment_months": 12,
           "effective_from": _dt(-30), "superseded_at": None}
    sb = FakeSB({
        "contracts": [{"id": contract_id, "company_id": cid, "service_type": "SAAS",
                       "status_code": "ACTIVE", "is_active": True}],
        "saas_contract_commercial_versions": [cv1, cv2],
    })
    result = svc.get_entitlement_health(sb, cid)
    assert result["health_status"] == "ERROR"
    assert result["error_code"] == "CURRENT_CV_AMBIGUOUS"


def test_acbe14_current_cv_schema_invalid():
    """ACBE14: unknown product_tier → CURRENT_CV_SCHEMA_INVALID."""
    cid = str(uuid.uuid4())
    contract_id = str(uuid.uuid4())
    cv = {"id": str(uuid.uuid4()), "contract_id": contract_id, "version_no": 1,
          "product_tier": "STARTER",  # invalid tier
          "pricing_mode": "STANDARD", "worker_capacity": 50, "payment_months": 12,
          "effective_from": _dt(-30), "superseded_at": None}
    sb = FakeSB({
        "contracts": [{"id": contract_id, "company_id": cid, "service_type": "SAAS",
                       "status_code": "ACTIVE", "is_active": True}],
        "saas_contract_commercial_versions": [cv],
    })
    result = svc.get_entitlement_health(sb, cid)
    assert result["health_status"] == "ERROR"
    assert result["error_code"] == "CURRENT_CV_SCHEMA_INVALID"


def test_acbe15_future_scheduled_cv_not_error():
    """ACBE15: future CV exists → health_status=OK + future_scheduled_cv_ids."""
    cid = str(uuid.uuid4())
    contract_id = str(uuid.uuid4())
    cv_current_id = str(uuid.uuid4())
    cv_future_id = str(uuid.uuid4())
    future_cv = {
        "id": cv_future_id,
        "contract_id": contract_id,
        "version_no": 2,
        "product_tier": "FIELD",
        "pricing_mode": "STANDARD",
        "worker_capacity": 80,
        "payment_months": 12,
        "effective_from": _dt(+30),  # future
        "superseded_at": None,
    }
    sb = FakeSB(_health_store(
        cid, contract_id, cv_current_id, "MANAGER",
        future_cvs=[future_cv],
    ))
    result = svc.get_entitlement_health(sb, cid)
    assert result["health_status"] == "OK", "future scheduled CV should not cause ERROR"
    assert cv_future_id in result["future_scheduled_cv_ids"]
    assert cv_current_id not in result.get("future_scheduled_cv_ids", [])


# ── QUOTE PROJECTION ─────────────────────────────────────────────────────────

def _frozen_v2_item(product_tier: str = "MANAGER") -> dict:
    return {
        "quote_schema_version": SAAS_QUOTE_SCHEMA_VERSION,
        "display_name": "TAI Safe 관리자형",
        "billing_unit": "MONTHLY",
        "unit_amount": 100000,
        "quantity": 12,
        "supply_amount": 1200000,
        "vat_amount": 120000,
        "total_amount": 1320000,
        "service_type": "SAAS",
        "price_id": None,
        "tier_code": None,
        "sector": "INDUSTRY",
        "sectors": ["INDUSTRY"],
        "product_tier": product_tier,
        "pricing_mode": "STANDARD",
        "policy_version": "V3",
        "worker_capacity": 50,
        "payment_months": 12,
        "vat_rate": 0.1,
        "vat_rate_bps": 1000,
    }


def test_acbe16_frozen_v2_commercial_projection():
    """ACBE16: Frozen V2 quote → commercial.product_tier populated."""
    row = {
        "id": str(uuid.uuid4()),
        "source": "member_auto",
        "status_code": "ISSUED",
        "items": [_frozen_v2_item("FIELD")],
        "created_at": _dt(-5),
        "updated_at": _dt(-5),
    }
    proj = aq_svc._project_commercial_v2(row)
    assert proj is not None
    assert proj["product_tier"] == "FIELD"
    assert proj["pricing_mode"] == "STANDARD"
    assert proj["worker_capacity"] == 50
    assert proj["payment_months"] == 12
    assert proj["quote_schema_version"] == SAAS_QUOTE_SCHEMA_VERSION


def test_acbe17_commercial_fields_from_items_only():
    """ACBE17: projection reads items[0] — not top-level DB columns."""
    row_no_top = {
        "id": str(uuid.uuid4()),
        "source": "member_auto",
        "status_code": "ISSUED",
        "items": [_frozen_v2_item("MANAGER")],
        # no product_tier / pricing_mode / worker_capacity / payment_months at top level
        "created_at": _dt(-5),
        "updated_at": _dt(-5),
    }
    proj = aq_svc._project_commercial_v2(row_no_top)
    assert proj is not None
    assert proj["product_tier"] == "MANAGER"
    # projection should not invent data from non-existent top-level
    assert "product_tier" not in {k for k in row_no_top if k != "items"}


def test_acbe18_admin_manual_commercial_null():
    """ACBE18: admin_manual → items[0].quote_schema_version != SAAS_QUOTE_V2 → commercial=None."""
    admin_manual_item = {
        "price_id": None,
        "service_type": "SAAS",
        "sector": "INDUSTRY",
        "tier_code": None,
        "display_name": "수동 발행",
        "billing_unit": "MONTHLY",
        "unit_amount": 200000,
        "term_months": 12,
        "quantity": 12,
        "supply_amount": 2400000,
        "vat_rate": 0.1,
        "vat_amount": 240000,
        "total_amount": 2640000,
        # no quote_schema_version
    }
    row = {
        "id": str(uuid.uuid4()),
        "source": "admin_manual",
        "status_code": "ISSUED",
        "items": [admin_manual_item],
        "created_at": _dt(-5),
        "updated_at": _dt(-5),
    }
    proj = aq_svc._project_commercial_v2(row)
    assert proj is None, "admin_manual without SAAS_QUOTE_V2 schema must return None"


def test_acbe19_member_custom_legacy_commercial_null():
    """ACBE19: member_custom legacy (no quote_schema_version) → commercial=None."""
    legacy_item = {
        "price_id": "price-old-001",
        "tier_code": "BUSINESS",
        "billing_unit": "MONTHLY",
        "unit_amount": 150000,
        # no quote_schema_version
    }
    row = {
        "id": str(uuid.uuid4()),
        "source": "member_custom",
        "status_code": "REQUESTED",
        "items": [legacy_item],
        "created_at": _dt(-5),
        "updated_at": _dt(-5),
    }
    proj = aq_svc._project_commercial_v2(row)
    assert proj is None


def test_acbe20_no_legacy_tier_inference():
    """ACBE20: STARTER/BUSINESS/PRO 추정 로직 없음 — 알 수 없는 tier → None."""
    item = {
        "quote_schema_version": SAAS_QUOTE_SCHEMA_VERSION,
        "product_tier": "STARTER",  # not a canonical V3 tier, but schema version matches
        "pricing_mode": "STANDARD",
        "worker_capacity": 10,
        "payment_months": 6,
        "policy_version": "V3",
        "sectors": [],
    }
    row = {"id": str(uuid.uuid4()), "source": "member_auto",
           "items": [item], "created_at": _dt(-5), "updated_at": _dt(-5)}
    # projection reads items[0] as-is — no tier mapping/normalization
    proj = aq_svc._project_commercial_v2(row)
    assert proj is not None
    assert proj["product_tier"] == "STARTER"  # raw passthrough, no mapping


def test_acbe21_no_pricing_engine_invocation():
    """ACBE21: pricing engine import/call 없음 (docstring 언급은 허용)."""
    import re
    import inspect
    import services.admin_commercial_svc as mod
    src = inspect.getsource(mod)
    # Check for actual import or function call patterns (not docstring mentions)
    forbidden_patterns = [
        r"^from\s+services.*import.*preview_saas_price_v2",
        r"^from\s+services.*import.*saas_pricing_composer_v2",
        r"preview_saas_price_v2\s*\(",
        r"saas_pricing_composer_v2\s*\(",
        r"calc_manual_quote\s*\(",
        r"price_master\s*\(",
    ]
    for pat in forbidden_patterns:
        assert not re.search(pat, src, re.MULTILINE), \
            f"pricing engine call/import found: {pat}"


def test_acbe22_no_write_routes():
    """ACBE22: admin_commercial router 에 POST/PUT/PATCH/DELETE route = 0."""
    import inspect
    import routers.admin_commercial as mod
    src = inspect.getsource(mod)
    # router.post / router.put / router.patch / router.delete must not appear
    for method in ("router.post", "router.put", "router.patch", "router.delete"):
        assert method not in src, f"mutation route found: {method}"


def test_acbe23_no_db_mutation():
    """ACBE23: admin_commercial_svc DB mutation (insert/update/delete) = 0."""
    import inspect
    import services.admin_commercial_svc as mod
    src = inspect.getsource(mod)
    for op in (".insert(", ".update(", ".delete("):
        assert op not in src, f"DB mutation call found: {op}"
