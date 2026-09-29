"""WO-BE-FE-QUOTE-SCOPE-01 — QSI-01 ~ QSI-14 (+ router contract).

Coverage:
  QSI-01  자사 INDUSTRY factory + 동일 employee_count → PASS
  QSI-02  자사 BUILDING factory + 동일 building_area → PASS
  QSI-03  자사 CONSTRUCTION site + 동일 contract_amount(억원×EOK) → PASS
  QSI-04  타사 factory → FAIL / Quote INSERT 0
  QSI-05  타사 construction_site → FAIL / Quote INSERT 0
  QSI-06  존재하지 않는 UUID → FAIL
  QSI-07  Sector mismatch (INDUSTRY factory, request BUILDING) → FAIL
  QSI-08  criteria tampering INDUSTRY (DB 300 / request 10) → QUOTE_SITE_DATA_CHANGED / INSERT 0
  QSI-09  criteria tampering BUILDING (DB 7500 / request 1000) → FAIL
  QSI-10  criteria tampering CONSTRUCTION (DB 50억 / request 100,000,000원) → FAIL
  QSI-11  criteria NULL → QUOTE_SITE_CRITERIA_REQUIRED
  QSI-12  복수 자사 사업장 → PASS
  QSI-13  한 개 정상 + 한 개 타사 → 전체 FAIL / 부분 Quote 없음
  QSI-14  Public Preview temporary UUID → 기존대로 PASS (regression)

  ROUTER  router 에서 QuoteSiteScopeError → 422/409 HTTP
  SOURCE  saas_quote_v2.py source guard (기존 Q-series 안전망 유지)
"""
from __future__ import annotations

import os
import uuid
from typing import List, Optional
from uuid import UUID, uuid4

import pytest

os.environ.setdefault("INTERNAL_API_SECRET", "pytest-internal-secret")

from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.member_quotes as mq
from schemas.saas_pricing_preview_v2 import SaasPricingPreviewSiteRequestV2
from schemas.saas_quote_v2 import SaasQuoteIssueRequestV2
from services.saas_quote_site_scope_v2 import (
    QuoteSiteScopeError,
    resolve_quote_site_scope_v2,
)
from services.saas_quote_v2 import SaasQuoteV2Error, issue_saas_quote_v2

_EOK_TO_WON = 100_000_000
_COMPANY_ID = "C-OWN"
_OTHER_COMPANY = "C-OTHER"
_USER_ID = "U-TEST"


# ═══════════════════════════════════════════════════════════════════════════════
# Fake Supabase
# ═══════════════════════════════════════════════════════════════════════════════

class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, store, table, log):
        self.store = store
        self.table_name = table
        self.log = log
        self._filters: list = []

    def select(self, *a, **k): return self
    def insert(self, row): self.log.append(("insert", self.table_name, row)); return self
    def eq(self, c, v): self._filters.append((c, v)); return self
    def limit(self, n): return self

    def execute(self):
        rows = self.store.get(self.table_name, [])
        matched = rows[:]
        for c, v in self._filters:
            matched = [r for r in matched if str(r.get(c)) == str(v)]
        return _Result(matched)


class FakeSB:
    def __init__(self, store):
        self.store = store
        self.log: list = []

    def table(self, name):
        return _Query(self.store, name, self.log)


def _sb(*, factories=None, sites=None, companies=None, quotes=None):
    return FakeSB({
        "factories": factories or [],
        "construction_sites": sites or [],
        "companies": companies or [{"id": _COMPANY_ID, "name": "자사"}],
        "quotes": quotes or [],
    })


def _factory(*, factory_id=None, company_id=_COMPANY_ID, sector="INDUSTRY",
              employee_count=100, building_area=None):
    return {
        "id": str(factory_id or uuid4()),
        "company_id": company_id,
        "sector": sector,
        "employee_count": employee_count,
        "building_area": building_area,
    }


def _site_row(*, site_id=None, company_id=_COMPANY_ID, contract_amount=50):
    return {
        "id": str(site_id or uuid4()),
        "company_id": company_id,
        "contract_amount": contract_amount,
    }


def _req_site(entity_id, sector="INDUSTRY", criteria_value=100):
    return SaasPricingPreviewSiteRequestV2(
        entity_id=entity_id, sector=sector, criteria_value=criteria_value,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# QSI-01 — INDUSTRY factory 자사 + 동일 employee_count
# ═══════════════════════════════════════════════════════════════════════════════

def test_QSI_01_industry_own_pass():
    fid = uuid4()
    sb = _sb(factories=[_factory(factory_id=fid, sector="INDUSTRY", employee_count=85)])
    result = resolve_quote_site_scope_v2(sb, _COMPANY_ID, [_req_site(fid, "INDUSTRY", 85)])
    assert len(result) == 1
    assert result[0].sector == "INDUSTRY"
    assert float(result[0].criteria_value) == 85.0


# ═══════════════════════════════════════════════════════════════════════════════
# QSI-02 — BUILDING factory 자사 + 동일 building_area
# ═══════════════════════════════════════════════════════════════════════════════

def test_QSI_02_building_own_pass():
    fid = uuid4()
    sb = _sb(factories=[_factory(factory_id=fid, sector="BUILDING",
                                  employee_count=None, building_area=7500)])
    result = resolve_quote_site_scope_v2(sb, _COMPANY_ID, [_req_site(fid, "BUILDING", 7500)])
    assert result[0].sector == "BUILDING"
    assert float(result[0].criteria_value) == 7500.0


# ═══════════════════════════════════════════════════════════════════════════════
# QSI-03 — CONSTRUCTION site 자사 + 동일 contract_amount
# ═══════════════════════════════════════════════════════════════════════════════

def test_QSI_03_construction_own_pass():
    sid = uuid4()
    sb = _sb(sites=[_site_row(site_id=sid, contract_amount=50)])
    canonical_value = 50 * _EOK_TO_WON  # 5,000,000,000
    result = resolve_quote_site_scope_v2(sb, _COMPANY_ID,
                                         [_req_site(sid, "CONSTRUCTION", canonical_value)])
    assert result[0].sector == "CONSTRUCTION"
    assert float(result[0].criteria_value) == float(canonical_value)


# ═══════════════════════════════════════════════════════════════════════════════
# QSI-04 — 타사 factory → FAIL
# ═══════════════════════════════════════════════════════════════════════════════

def test_QSI_04_other_company_factory_fail():
    fid = uuid4()
    sb = _sb(factories=[_factory(factory_id=fid, company_id=_OTHER_COMPANY,
                                   sector="INDUSTRY", employee_count=100)])
    with pytest.raises(QuoteSiteScopeError) as exc:
        resolve_quote_site_scope_v2(sb, _COMPANY_ID, [_req_site(fid, "INDUSTRY", 100)])
    assert exc.value.code == "QUOTE_SITE_SCOPE_INVALID"
    assert exc.value.http_status == 422


# ═══════════════════════════════════════════════════════════════════════════════
# QSI-05 — 타사 construction_site → FAIL
# ═══════════════════════════════════════════════════════════════════════════════

def test_QSI_05_other_company_site_fail():
    sid = uuid4()
    sb = _sb(sites=[_site_row(site_id=sid, company_id=_OTHER_COMPANY, contract_amount=50)])
    with pytest.raises(QuoteSiteScopeError) as exc:
        resolve_quote_site_scope_v2(sb, _COMPANY_ID,
                                    [_req_site(sid, "CONSTRUCTION", 50 * _EOK_TO_WON)])
    assert exc.value.code == "QUOTE_SITE_SCOPE_INVALID"


# ═══════════════════════════════════════════════════════════════════════════════
# QSI-06 — 존재하지 않는 UUID → FAIL
# ═══════════════════════════════════════════════════════════════════════════════

def test_QSI_06_nonexistent_uuid_fail():
    sb = _sb()  # empty factories
    ghost = uuid4()
    with pytest.raises(QuoteSiteScopeError) as exc:
        resolve_quote_site_scope_v2(sb, _COMPANY_ID, [_req_site(ghost, "INDUSTRY", 10)])
    assert exc.value.code == "QUOTE_SITE_SCOPE_INVALID"


def test_QSI_06b_nonexistent_construction_fail():
    sb = _sb()
    ghost = uuid4()
    with pytest.raises(QuoteSiteScopeError) as exc:
        resolve_quote_site_scope_v2(sb, _COMPANY_ID,
                                    [_req_site(ghost, "CONSTRUCTION", 10 * _EOK_TO_WON)])
    assert exc.value.code == "QUOTE_SITE_SCOPE_INVALID"


# ═══════════════════════════════════════════════════════════════════════════════
# QSI-07 — Sector mismatch: INDUSTRY factory, request BUILDING
# ═══════════════════════════════════════════════════════════════════════════════

def test_QSI_07_sector_mismatch_fail():
    fid = uuid4()
    sb = _sb(factories=[_factory(factory_id=fid, sector="INDUSTRY",
                                   employee_count=100, building_area=5000)])
    with pytest.raises(QuoteSiteScopeError) as exc:
        # request says BUILDING, but factory.sector == INDUSTRY
        resolve_quote_site_scope_v2(sb, _COMPANY_ID, [_req_site(fid, "BUILDING", 5000)])
    assert exc.value.code == "QUOTE_SITE_SCOPE_INVALID"


# ═══════════════════════════════════════════════════════════════════════════════
# QSI-08 — criteria tampering INDUSTRY (DB 300 / request 10)
# ═══════════════════════════════════════════════════════════════════════════════

def test_QSI_08_industry_criteria_tamper_fail():
    fid = uuid4()
    sb = _sb(factories=[_factory(factory_id=fid, sector="INDUSTRY", employee_count=300)])
    with pytest.raises(QuoteSiteScopeError) as exc:
        resolve_quote_site_scope_v2(sb, _COMPANY_ID, [_req_site(fid, "INDUSTRY", 10)])
    assert exc.value.code == "QUOTE_SITE_DATA_CHANGED"
    assert exc.value.http_status == 409


def test_QSI_08_no_insert_on_criteria_tamper(monkeypatch):
    """criteria 위변조 시 Quote INSERT = 0."""
    fid = uuid4()
    sb = _sb(factories=[_factory(factory_id=fid, sector="INDUSTRY", employee_count=300)])
    insert_calls = []
    monkeypatch.setattr("services.member_quote_svc._insert_quote_with_unique_retry",
                        lambda *a, **k: insert_calls.append(1) or {})

    from schemas.saas_quote_v2 import SaasQuoteIssueRequestV2
    req = SaasQuoteIssueRequestV2(
        product_tier="MANAGER", worker_capacity=0, payment_months=1,
        sites=[SaasPricingPreviewSiteRequestV2(
            entity_id=fid, sector="INDUSTRY", criteria_value=10,
        )],
    )
    with pytest.raises(QuoteSiteScopeError):
        issue_saas_quote_v2(sb, req, _USER_ID, _COMPANY_ID)
    assert len(insert_calls) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# QSI-09 — criteria tampering BUILDING
# ═══════════════════════════════════════════════════════════════════════════════

def test_QSI_09_building_criteria_tamper_fail():
    fid = uuid4()
    sb = _sb(factories=[_factory(factory_id=fid, sector="BUILDING",
                                   employee_count=None, building_area=7500)])
    with pytest.raises(QuoteSiteScopeError) as exc:
        resolve_quote_site_scope_v2(sb, _COMPANY_ID, [_req_site(fid, "BUILDING", 1000)])
    assert exc.value.code == "QUOTE_SITE_DATA_CHANGED"


# ═══════════════════════════════════════════════════════════════════════════════
# QSI-10 — criteria tampering CONSTRUCTION (DB 50억 / request 100,000,000원)
# ═══════════════════════════════════════════════════════════════════════════════

def test_QSI_10_construction_criteria_tamper_fail():
    sid = uuid4()
    sb = _sb(sites=[_site_row(site_id=sid, contract_amount=50)])  # 50억 = 5,000,000,000원
    with pytest.raises(QuoteSiteScopeError) as exc:
        # request 100,000,000 ≠ DB 5,000,000,000
        resolve_quote_site_scope_v2(sb, _COMPANY_ID,
                                    [_req_site(sid, "CONSTRUCTION", 100_000_000)])
    assert exc.value.code == "QUOTE_SITE_DATA_CHANGED"


# ═══════════════════════════════════════════════════════════════════════════════
# QSI-11 — criteria NULL → QUOTE_SITE_CRITERIA_REQUIRED
# ═══════════════════════════════════════════════════════════════════════════════

def test_QSI_11_null_employee_count_fail():
    fid = uuid4()
    sb = _sb(factories=[_factory(factory_id=fid, sector="INDUSTRY", employee_count=None)])
    with pytest.raises(QuoteSiteScopeError) as exc:
        resolve_quote_site_scope_v2(sb, _COMPANY_ID, [_req_site(fid, "INDUSTRY", 0)])
    assert exc.value.code == "QUOTE_SITE_CRITERIA_REQUIRED"


def test_QSI_11_null_building_area_fail():
    fid = uuid4()
    sb = _sb(factories=[_factory(factory_id=fid, sector="BUILDING",
                                   employee_count=None, building_area=None)])
    with pytest.raises(QuoteSiteScopeError) as exc:
        resolve_quote_site_scope_v2(sb, _COMPANY_ID, [_req_site(fid, "BUILDING", 0)])
    assert exc.value.code == "QUOTE_SITE_CRITERIA_REQUIRED"


def test_QSI_11_null_contract_amount_fail():
    sid = uuid4()
    sb = _sb(sites=[_site_row(site_id=sid, contract_amount=None)])
    with pytest.raises(QuoteSiteScopeError) as exc:
        resolve_quote_site_scope_v2(sb, _COMPANY_ID,
                                    [_req_site(sid, "CONSTRUCTION", 0)])
    assert exc.value.code == "QUOTE_SITE_CRITERIA_REQUIRED"


# ═══════════════════════════════════════════════════════════════════════════════
# QSI-12 — 복수 자사 사업장 → PASS
# ═══════════════════════════════════════════════════════════════════════════════

def test_QSI_12_multi_own_sites_pass():
    fid1, fid2 = uuid4(), uuid4()
    sb = _sb(factories=[
        _factory(factory_id=fid1, sector="INDUSTRY", employee_count=50),
        _factory(factory_id=fid2, sector="BUILDING", employee_count=None, building_area=3000),
    ])
    result = resolve_quote_site_scope_v2(sb, _COMPANY_ID, [
        _req_site(fid1, "INDUSTRY", 50),
        _req_site(fid2, "BUILDING", 3000),
    ])
    assert len(result) == 2
    sectors = {r.sector for r in result}
    assert sectors == {"INDUSTRY", "BUILDING"}


# ═══════════════════════════════════════════════════════════════════════════════
# QSI-13 — 한 개 정상 + 한 개 타사 → 전체 FAIL / 부분 Quote 없음
# ═══════════════════════════════════════════════════════════════════════════════

def test_QSI_13_partial_fail_no_quote():
    fid_own = uuid4()
    fid_other = uuid4()
    sb = _sb(factories=[
        _factory(factory_id=fid_own, sector="INDUSTRY", employee_count=100),
        _factory(factory_id=fid_other, company_id=_OTHER_COMPANY,
                  sector="INDUSTRY", employee_count=100),
    ])
    with pytest.raises(QuoteSiteScopeError) as exc:
        resolve_quote_site_scope_v2(sb, _COMPANY_ID, [
            _req_site(fid_own, "INDUSTRY", 100),
            _req_site(fid_other, "INDUSTRY", 100),
        ])
    assert exc.value.code == "QUOTE_SITE_SCOPE_INVALID"


# ═══════════════════════════════════════════════════════════════════════════════
# QSI-14 — Public Preview temporary UUID → PASS (regression)
# ═══════════════════════════════════════════════════════════════════════════════

def test_QSI_14_public_preview_temp_uuid_pass(monkeypatch):
    """POST /public/pricing/v2/preview는 인증 없이 임시 UUID 허용."""
    from services.saas_pricing_preview_v2 import preview_saas_price_v2

    monkeypatch.setattr("services.pricing_resolver_svc.resolve_plan",
                        lambda *a, **k: {"status": "success", "data": {
                            "service_type": "SAAS", "sector": "INDUSTRY",
                            "tier_code": "STANDARD", "amount": 149_000,
                            "billing_unit": "MONTHLY", "is_active": True,
                        }})
    from datetime import date
    from schemas.saas_pricing_policy_v2 import (
        SaasPricingPolicyV2, SaasTermDiscountPolicy, SaasWorkerRateBracketPolicy,
    )
    policy = SaasPricingPolicyV2(
        policy_version="QSI14_TEST",
        effective_from=date(2026, 9, 28),
        field_base_amount=249000,
        primary_site_rate_bps=10_000,
        additional_site_rate_bps=8_000,
        worker_brackets=[SaasWorkerRateBracketPolicy(range_from=1, range_to=None, unit_rate=3_000)],
        vat_rate_bps=1_000,
        term_discounts=[
            SaasTermDiscountPolicy(payment_months=1,  discount_rate_bps=0),
            SaasTermDiscountPolicy(payment_months=3,  discount_rate_bps=300),
            SaasTermDiscountPolicy(payment_months=6,  discount_rate_bps=500),
            SaasTermDiscountPolicy(payment_months=9,  discount_rate_bps=700),
            SaasTermDiscountPolicy(payment_months=12, discount_rate_bps=1_000),
        ],
    )
    monkeypatch.setattr("services.saas_pricing_composer_v2.get_canonical_pricing_policy_v2",
                        lambda: policy)

    from schemas.saas_pricing_preview_v2 import SaasPricingPreviewRequestV2
    req = SaasPricingPreviewRequestV2(
        product_tier="MANAGER",
        worker_capacity=0,
        payment_months=1,
        sites=[SaasPricingPreviewSiteRequestV2(
            entity_id=uuid4(),  # 임시 UUID — DB에 없어도 됨
            sector="INDUSTRY",
            criteria_value=10,
        )],
    )
    result = preview_saas_price_v2(None, req)
    assert result.status == "READY"


# ═══════════════════════════════════════════════════════════════════════════════
# Router: QuoteSiteScopeError → HTTP mapping
# ═══════════════════════════════════════════════════════════════════════════════

def _make_app():
    app = FastAPI()
    app.include_router(mq.router)
    return app


def _current():
    return {"id": _USER_ID, "company_id": _COMPANY_ID, "role_code": "002"}


class _FakeSBWithCompany:
    """require_company_id 통과 + factories empty → SCOPE_INVALID."""
    def __init__(self):
        self.store = {
            "companies": [{"id": _COMPANY_ID, "name": "자사"}],
            "role_data_scope": [{"role_code": "002", "scope_type": "COMPANY"}],
            "factories": [],
            "construction_sites": [],
            "quotes": [],
        }
        self.log: list = []

    def table(self, name):
        return _Query(self.store, name, self.log)


def test_ROUTER_scope_invalid_returns_422():
    """존재하지 않는 entity_id → router가 422 반환."""
    app = _make_app()
    app.dependency_overrides[mq.get_current_user] = lambda: _current()
    mq.get_supabase = lambda: _FakeSBWithCompany()
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/me/quotes/v2/issue", json={
        "product_tier": "MANAGER", "worker_capacity": 0, "payment_months": 1,
        "sites": [{"entity_id": str(uuid4()), "sector": "INDUSTRY", "criteria_value": 10}],
    })
    assert resp.status_code == 422
    data = resp.json()
    assert data["detail"]["code"] == "QUOTE_SITE_SCOPE_INVALID"


def test_ROUTER_data_changed_returns_409(monkeypatch):
    """criteria 위변조 → router가 409 반환."""
    fid = uuid4()

    class SBWithFactory(_FakeSBWithCompany):
        def __init__(self):
            super().__init__()
            self.store["factories"] = [
                {"id": str(fid), "company_id": _COMPANY_ID, "sector": "INDUSTRY",
                 "employee_count": 300, "building_area": None}
            ]

    app = _make_app()
    app.dependency_overrides[mq.get_current_user] = lambda: _current()
    mq.get_supabase = lambda: SBWithFactory()
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/me/quotes/v2/issue", json={
        "product_tier": "MANAGER", "worker_capacity": 0, "payment_months": 1,
        "sites": [{"entity_id": str(fid), "sector": "INDUSTRY", "criteria_value": 10}],
    })
    assert resp.status_code == 409
    data = resp.json()
    assert data["detail"]["code"] == "QUOTE_SITE_DATA_CHANGED"


# ═══════════════════════════════════════════════════════════════════════════════
# SOURCE guard — saas_quote_v2.py에 resolve_quote_site_scope_v2 호출 존재
# ═══════════════════════════════════════════════════════════════════════════════

def test_SOURCE_scope_resolver_called_in_issue():
    from pathlib import Path
    src = Path(__file__).parent.parent / "services" / "saas_quote_v2.py"
    code = src.read_text()
    assert "resolve_quote_site_scope_v2" in code, "scope resolver 미호출 — GAP 미닫힘"


def test_SOURCE_canonical_request_used():
    from pathlib import Path
    src = Path(__file__).parent.parent / "services" / "saas_quote_v2.py"
    code = src.read_text()
    assert "canonical_request" in code, "canonical_request 미사용 — client request 그대로 preview로"


def test_SOURCE_no_direct_db_in_quote_svc():
    """quote service가 factories/construction_sites 직접 조회하지 않음 (scope resolver 위임)."""
    from pathlib import Path
    src = Path(__file__).parent.parent / "services" / "saas_quote_v2.py"
    code = src.read_text()
    assert '"factories"' not in code, "quote service가 factories 직접 조회 — scope resolver 위임 깨짐"
    assert '"construction_sites"' not in code, "quote service가 construction_sites 직접 조회"
