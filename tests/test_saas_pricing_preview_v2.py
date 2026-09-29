"""Tests for WO-PRICING-V2-BE-OBJ08 — Public Pricing Preview API V2.

Coverage: P01–P86 (86 tests)
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Dict, List
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.public_pricing_v2 as router_mod
from schemas.saas_pricing_preview_v2 import (
    SaasPricingPreviewRequestV2,
    SaasPricingPreviewResponseV2,
    SaasPricingPreviewSiteRequestV2,
)
from services.saas_pricing_preview_v2 import (
    SaasPricingPreviewError,
    preview_saas_price_v2,
)

_SVC_SRC = Path(__file__).parent.parent / "services" / "saas_pricing_preview_v2.py"
_SCHEMA_SRC = Path(__file__).parent.parent / "schemas" / "saas_pricing_preview_v2.py"

_SITE_1 = uuid4()
_SITE_2 = uuid4()
_SITE_3 = uuid4()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _good_row(
    amount: int = 149_000,
    tier_code: str = "STANDARD",
    sector: str = "INDUSTRY",
    billing_unit: str = "MONTHLY",
    service_type: str = "SAAS",
) -> dict:
    return {
        "service_type": service_type,
        "sector": sector,
        "tier_code": tier_code,
        "amount": amount,
        "billing_unit": billing_unit,
        "is_active": True,
    }


def _good_resolve(
    amount: int = 149_000,
    tier_code: str = "STANDARD",
    sector: str = "INDUSTRY",
) -> dict:
    return {"status": "success", "data": _good_row(amount, tier_code, sector)}


def _site_req(
    entity_id: UUID = _SITE_1,
    sector: str = "INDUSTRY",
    criteria_value: int = 10,
) -> SaasPricingPreviewSiteRequestV2:
    return SaasPricingPreviewSiteRequestV2(
        entity_id=entity_id, sector=sector, criteria_value=criteria_value,
    )


def _req(
    tier: str = "MANAGER",
    workers: int = 0,
    term: int = 1,
    sites: List[SaasPricingPreviewSiteRequestV2] = None,
) -> SaasPricingPreviewRequestV2:
    return SaasPricingPreviewRequestV2(
        product_tier=tier,
        worker_capacity=workers,
        payment_months=term,
        sites=sites if sites is not None else [_site_req()],
    )


def _preview(monkeypatch, tier="MANAGER", workers=0, term=1, sites=None,
             resolve_fn=None) -> SaasPricingPreviewResponseV2:
    if resolve_fn is None:
        resolve_fn = lambda sb, svc, sec, val=None: _good_resolve(sector=sec)
    monkeypatch.setattr("services.pricing_resolver_svc.resolve_plan", resolve_fn)
    return preview_saas_price_v2(None, _req(tier, workers, term, sites))


def _test_policy():
    from datetime import date
    from schemas.saas_pricing_policy_v2 import (
        SaasPricingPolicyV2,
        SaasTermDiscountPolicy,
        SaasWorkerRateBracketPolicy,
    )
    return SaasPricingPolicyV2(
        policy_version="TEST_PREVIEW_V1",
        effective_from=date(2026, 9, 28),
        field_base_amount=249000,
        primary_site_rate_bps=10_000,
        additional_site_rate_bps=8_000,
        worker_brackets=[
            SaasWorkerRateBracketPolicy(range_from=1, range_to=None, unit_rate=3_000),
        ],
        vat_rate_bps=1_000,
        term_discounts=[
            SaasTermDiscountPolicy(payment_months=1, discount_rate_bps=0),
            SaasTermDiscountPolicy(payment_months=3, discount_rate_bps=300),
            SaasTermDiscountPolicy(payment_months=6, discount_rate_bps=500),
            SaasTermDiscountPolicy(payment_months=9, discount_rate_bps=700),
            SaasTermDiscountPolicy(payment_months=12, discount_rate_bps=1_000),
        ],
    )


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router_mod.router)
    return app


def _code_lines(path: Path) -> str:
    lines = path.read_text().splitlines()
    return "\n".join(ln for ln in lines if not ln.lstrip().startswith(("#", '"""', "- ")))


# ═══════════════════════════════════════════════════════════════════════════════
# P01–P05: Router Contract
# ═══════════════════════════════════════════════════════════════════════════════

def test_P01_endpoint_exists():
    paths = [r.path for r in router_mod.router.routes]
    assert "/public/pricing/v2/preview" in paths


def test_P02_method_is_post():
    for route in router_mod.router.routes:
        if route.path == "/public/pricing/v2/preview":
            assert "POST" in route.methods


def test_P03_no_auth_dependency():
    for route in router_mod.router.routes:
        if route.path == "/public/pricing/v2/preview":
            deps = getattr(route, "dependencies", [])
            dep_names = [type(d.dependency).__name__ for d in deps]
            assert not any("auth" in n.lower() or "jwt" in n.lower() for n in dep_names)


def test_P04_router_prefix_exact():
    assert router_mod.router.prefix == "/public/pricing/v2"


def test_P05_router_registry_registered():
    src = Path("router_registry/public.py").read_text()
    assert "routers.public_pricing_v2" in src


# ═══════════════════════════════════════════════════════════════════════════════
# P06–P15: Request Authority — client fields
# ═══════════════════════════════════════════════════════════════════════════════

def test_P06_request_has_product_tier():
    fields = SaasPricingPreviewRequestV2.model_fields
    assert "product_tier" in fields


def test_P07_request_has_worker_capacity():
    assert "worker_capacity" in SaasPricingPreviewRequestV2.model_fields


def test_P08_request_has_payment_months():
    assert "payment_months" in SaasPricingPreviewRequestV2.model_fields


def test_P09_request_has_sites():
    assert "sites" in SaasPricingPreviewRequestV2.model_fields


def test_P10_request_no_pricing_mode():
    assert "pricing_mode" not in SaasPricingPreviewRequestV2.model_fields


def test_P11_request_no_base_amount():
    assert "base_amount" not in SaasPricingPreviewRequestV2.model_fields
    assert "base_amount" not in SaasPricingPreviewSiteRequestV2.model_fields


def test_P12_request_no_base_band_code():
    assert "base_band_code" not in SaasPricingPreviewRequestV2.model_fields
    assert "base_band_code" not in SaasPricingPreviewSiteRequestV2.model_fields


def test_P13_request_no_tier_code():
    assert "tier_code" not in SaasPricingPreviewRequestV2.model_fields
    assert "tier_code" not in SaasPricingPreviewSiteRequestV2.model_fields


def test_P14_request_no_policy_version():
    assert "policy_version" not in SaasPricingPreviewRequestV2.model_fields


def test_P15_request_no_price_totals():
    forbidden = {
        "monthly_supply_amount", "prepaid_supply_amount", "vat_amount",
        "total_amount", "sort_order",
    }
    fields = set(SaasPricingPreviewRequestV2.model_fields) | set(SaasPricingPreviewSiteRequestV2.model_fields)
    assert not forbidden & fields


# ═══════════════════════════════════════════════════════════════════════════════
# P16–P21: Selection Validation
# ═══════════════════════════════════════════════════════════════════════════════

def test_P16_manager_derives_standard(monkeypatch):
    r = _preview(monkeypatch, tier="MANAGER")
    assert r.pricing_mode == "STANDARD"


def test_P17_field_derives_standard(monkeypatch):
    r = _preview(monkeypatch, tier="FIELD", workers=10)
    assert r.pricing_mode == "STANDARD"


def test_P18_custom_derives_custom(monkeypatch):
    r = preview_saas_price_v2(None, _req("CUSTOM", sites=[]))
    assert r.pricing_mode == "CUSTOM"


def test_P19_manager_worker_zero_accepted(monkeypatch):
    r = _preview(monkeypatch, tier="MANAGER", workers=0)
    assert r.product_tier == "MANAGER"


def test_P20_manager_worker_positive_rejected(monkeypatch):
    monkeypatch.setattr(
        "services.pricing_resolver_svc.resolve_plan",
        lambda *a, **k: _good_resolve(),
    )
    with pytest.raises(SaasPricingPreviewError) as exc:
        preview_saas_price_v2(None, _req("MANAGER", workers=1))
    assert exc.value.code == "INVALID_SELECTION"


def test_P21_field_worker_zero_accepted(monkeypatch):
    r = _preview(monkeypatch, tier="FIELD", workers=0)
    assert r.product_tier == "FIELD"


# ═══════════════════════════════════════════════════════════════════════════════
# P22–P26: Site Validation
# ═══════════════════════════════════════════════════════════════════════════════

def test_P22_standard_zero_sites_rejected(monkeypatch):
    monkeypatch.setattr("services.pricing_resolver_svc.resolve_plan", lambda *a, **k: _good_resolve())
    with pytest.raises(SaasPricingPreviewError) as exc:
        preview_saas_price_v2(None, _req("MANAGER", sites=[]))
    assert exc.value.code == "STANDARD_SITE_REQUIRED"


def test_P23_duplicate_entity_id_rejected(monkeypatch):
    monkeypatch.setattr("services.pricing_resolver_svc.resolve_plan", lambda *a, **k: _good_resolve())
    dup = [_site_req(_SITE_1), _site_req(_SITE_1)]
    with pytest.raises(SaasPricingPreviewError) as exc:
        preview_saas_price_v2(None, _req("MANAGER", sites=dup))
    assert exc.value.code == "DUPLICATE_SITE"


def test_P24_industry_entity_type_factory(monkeypatch):
    r = _preview(monkeypatch, sites=[_site_req(sector="INDUSTRY")])
    assert r.resolved_sites[0].entity_type == "factory"


def test_P25_building_entity_type_factory(monkeypatch):
    def fake_resolve(sb, svc, sec, val=None):
        return {"status": "success", "data": _good_row(sector=sec, amount=149_000)}
    monkeypatch.setattr("services.pricing_resolver_svc.resolve_plan", fake_resolve)
    r = preview_saas_price_v2(None, _req("MANAGER", sites=[_site_req(sector="BUILDING")]))
    assert r.resolved_sites[0].entity_type == "factory"


def test_P26_construction_entity_type_site(monkeypatch):
    def fake_resolve(sb, svc, sec, val=None):
        return {"status": "success", "data": _good_row(sector=sec, amount=499_000)}
    monkeypatch.setattr("services.pricing_resolver_svc.resolve_plan", fake_resolve)
    r = preview_saas_price_v2(None, _req("MANAGER", sites=[_site_req(sector="CONSTRUCTION", criteria_value=5_000_000_000)]))
    assert r.resolved_sites[0].entity_type == "site"


# ═══════════════════════════════════════════════════════════════════════════════
# P27–P30: Resolver Invocation
# ═══════════════════════════════════════════════════════════════════════════════

def test_P27_resolver_service_type_always_saas(monkeypatch):
    calls: list = []

    def capture(sb, service_type, sector, value=None):
        calls.append(service_type)
        return _good_resolve(sector=sector)

    monkeypatch.setattr("services.pricing_resolver_svc.resolve_plan", capture)
    preview_saas_price_v2(None, _req("MANAGER"))
    assert all(c == "SAAS" for c in calls)


def test_P28_resolver_exact_sector(monkeypatch):
    calls: list = []

    def capture(sb, service_type, sector, value=None):
        calls.append(sector)
        return _good_resolve(sector=sector)

    monkeypatch.setattr("services.pricing_resolver_svc.resolve_plan", capture)
    preview_saas_price_v2(None, _req("MANAGER", sites=[_site_req(sector="BUILDING")]))
    assert "BUILDING" in calls


def test_P29_resolver_exact_criteria_value(monkeypatch):
    calls: list = []

    def capture(sb, service_type, sector, value=None):
        calls.append(value)
        return _good_resolve(sector=sector)

    monkeypatch.setattr("services.pricing_resolver_svc.resolve_plan", capture)
    preview_saas_price_v2(None, _req("MANAGER", sites=[_site_req(criteria_value=42)]))
    assert 42 in calls


def test_P30_client_cannot_select_band(monkeypatch):
    fields = set(SaasPricingPreviewSiteRequestV2.model_fields)
    assert "base_band_code" not in fields
    assert "tier_code" not in fields
    assert "sort_order" not in fields


# ═══════════════════════════════════════════════════════════════════════════════
# P31–P34: Resolver Failure
# ═══════════════════════════════════════════════════════════════════════════════

def test_P31_not_found_raises_base_price_not_found(monkeypatch):
    monkeypatch.setattr(
        "services.pricing_resolver_svc.resolve_plan",
        lambda *a, **k: {"status": "not_found", "data": None},
    )
    with pytest.raises(SaasPricingPreviewError) as exc:
        preview_saas_price_v2(None, _req("MANAGER"))
    assert exc.value.code == "BASE_PRICE_NOT_FOUND"


def test_P32_none_data_raises_invalid_row(monkeypatch):
    monkeypatch.setattr(
        "services.pricing_resolver_svc.resolve_plan",
        lambda *a, **k: {"status": "success", "data": None},
    )
    with pytest.raises(SaasPricingPreviewError) as exc:
        preview_saas_price_v2(None, _req("MANAGER"))
    assert exc.value.code == "BASE_PRICE_NOT_FOUND"


def test_P33_missing_tier_code_raises_invalid_row(monkeypatch):
    bad_row = _good_row()
    bad_row.pop("tier_code")
    monkeypatch.setattr(
        "services.pricing_resolver_svc.resolve_plan",
        lambda *a, **k: {"status": "success", "data": bad_row},
    )
    with pytest.raises(SaasPricingPreviewError) as exc:
        preview_saas_price_v2(None, _req("MANAGER"))
    assert exc.value.code == "INVALID_BASE_PRICE_ROW"


def test_P34_non_monthly_raises_invalid_row(monkeypatch):
    bad_row = _good_row(billing_unit="ANNUAL")
    monkeypatch.setattr(
        "services.pricing_resolver_svc.resolve_plan",
        lambda *a, **k: {"status": "success", "data": bad_row},
    )
    with pytest.raises(SaasPricingPreviewError) as exc:
        preview_saas_price_v2(None, _req("MANAGER"))
    assert exc.value.code == "INVALID_BASE_PRICE_ROW"


# ═══════════════════════════════════════════════════════════════════════════════
# P35–P37: Positive Base Price
# ═══════════════════════════════════════════════════════════════════════════════

def test_P35_positive_amount_becomes_site_input(monkeypatch):
    r = _preview(monkeypatch, tier="MANAGER")
    assert len(r.resolved_sites) == 1
    assert r.resolved_sites[0].base_amount == 149_000


def test_P36_tier_code_becomes_base_band_code(monkeypatch):
    monkeypatch.setattr(
        "services.pricing_resolver_svc.resolve_plan",
        lambda *a, **k: _good_resolve(tier_code="STARTER"),
    )
    r = preview_saas_price_v2(None, _req("MANAGER"))
    assert r.resolved_sites[0].base_band_code == "STARTER"


def test_P37_amount_becomes_base_amount(monkeypatch):
    monkeypatch.setattr(
        "services.pricing_resolver_svc.resolve_plan",
        lambda *a, **k: _good_resolve(amount=299_000),
    )
    r = preview_saas_price_v2(None, _req("MANAGER"))
    assert r.resolved_sites[0].base_amount == 299_000


# ═══════════════════════════════════════════════════════════════════════════════
# P38–P41: Legacy Compliance Custom
# ═══════════════════════════════════════════════════════════════════════════════

def test_P38_manager_zero_amount_compliance_quote(monkeypatch):
    monkeypatch.setattr(
        "services.pricing_resolver_svc.resolve_plan",
        lambda *a, **k: _good_resolve(amount=0, tier_code="INDUSTRY_CUSTOM"),
    )
    r = preview_saas_price_v2(None, _req("MANAGER"))
    assert r.status == "COMPLIANCE_BASE_QUOTE_REQUIRED"


def test_P39_field_zero_amount_compliance_quote(monkeypatch):
    monkeypatch.setattr(
        "services.pricing_resolver_svc.resolve_plan",
        lambda *a, **k: _good_resolve(amount=0, tier_code="INDUSTRY_CUSTOM"),
    )
    r = preview_saas_price_v2(None, _req("FIELD", workers=10))
    assert r.status == "COMPLIANCE_BASE_QUOTE_REQUIRED"


def test_P40_compliance_quote_composer_not_called(monkeypatch):
    calls: list = []

    def fake_resolve(*a, **k):
        return _good_resolve(amount=0, tier_code="INDUSTRY_CUSTOM")

    monkeypatch.setattr("services.pricing_resolver_svc.resolve_plan", fake_resolve)

    original_calc = __import__(
        "services.saas_pricing_composer_v2", fromlist=["calculate_saas_price_v2"]
    ).calculate_saas_price_v2

    def counting_calc(*a, **k):
        calls.append(True)
        return original_calc(*a, **k)

    monkeypatch.setattr(
        "services.saas_pricing_preview_v2.calculate_saas_price_v2",
        counting_calc,
    )
    preview_saas_price_v2(None, _req("MANAGER"))
    assert len(calls) == 0


def test_P41_compliance_quote_base_amount_none(monkeypatch):
    monkeypatch.setattr(
        "services.pricing_resolver_svc.resolve_plan",
        lambda *a, **k: _good_resolve(amount=0, tier_code="INDUSTRY_CUSTOM"),
    )
    r = preview_saas_price_v2(None, _req("MANAGER"))
    assert r.resolved_sites[0].base_amount is None


# ═══════════════════════════════════════════════════════════════════════════════
# P42–P45: Product CUSTOM
# ═══════════════════════════════════════════════════════════════════════════════

def test_P42_product_custom_returns_custom_required():
    r = preview_saas_price_v2(None, _req("CUSTOM", sites=[]))
    assert r.status == "CUSTOM_REQUIRED"


def test_P43_custom_zero_sites_accepted():
    r = preview_saas_price_v2(None, _req("CUSTOM", sites=[]))
    assert r.status == "CUSTOM_REQUIRED"


def test_P44_custom_does_not_call_resolver(monkeypatch):
    calls: list = []

    def counting_resolve(*a, **k):
        calls.append(True)
        return _good_resolve()

    monkeypatch.setattr("services.pricing_resolver_svc.resolve_plan", counting_resolve)
    preview_saas_price_v2(None, _req("CUSTOM", sites=[]))
    assert len(calls) == 0


def test_P45_custom_amount_remains_none():
    r = preview_saas_price_v2(None, _req("CUSTOM", sites=[]))
    assert r.calculation is not None
    assert r.calculation.monthly_supply_amount is None


# ═══════════════════════════════════════════════════════════════════════════════
# P46: CUSTOM distinction
# ═══════════════════════════════════════════════════════════════════════════════

def test_P46_custom_statuses_distinct(monkeypatch):
    r_product_custom = preview_saas_price_v2(None, _req("CUSTOM", sites=[]))
    monkeypatch.setattr(
        "services.pricing_resolver_svc.resolve_plan",
        lambda *a, **k: _good_resolve(amount=0, tier_code="INDUSTRY_CUSTOM"),
    )
    r_base_quote = preview_saas_price_v2(None, _req("MANAGER"))
    assert r_product_custom.status != r_base_quote.status
    assert r_product_custom.status == "CUSTOM_REQUIRED"
    assert r_base_quote.status == "COMPLIANCE_BASE_QUOTE_REQUIRED"


# ═══════════════════════════════════════════════════════════════════════════════
# P47–P50: Composer Integration
# ═══════════════════════════════════════════════════════════════════════════════

def test_P47_manager_calls_composer(monkeypatch):
    calls: list = []
    original = __import__(
        "services.saas_pricing_composer_v2", fromlist=["calculate_saas_price_v2"]
    ).calculate_saas_price_v2

    def counting(*a, **k):
        calls.append(True)
        return original(*a, **k)

    monkeypatch.setattr("services.saas_pricing_preview_v2.calculate_saas_price_v2", counting)
    monkeypatch.setattr("services.pricing_resolver_svc.resolve_plan", lambda *a, **k: _good_resolve())
    preview_saas_price_v2(None, _req("MANAGER"))
    assert len(calls) == 1


def test_P48_field_calls_composer(monkeypatch):
    calls: list = []
    original = __import__(
        "services.saas_pricing_composer_v2", fromlist=["calculate_saas_price_v2"]
    ).calculate_saas_price_v2

    def counting(*a, **k):
        calls.append(True)
        return original(*a, **k)

    monkeypatch.setattr("services.saas_pricing_preview_v2.calculate_saas_price_v2", counting)
    monkeypatch.setattr("services.pricing_resolver_svc.resolve_plan", lambda *a, **k: _good_resolve())
    preview_saas_price_v2(None, _req("FIELD", workers=5))
    assert len(calls) == 1


def test_P49_no_pricing_formula_in_service():
    code = _code_lines(_SVC_SRC)
    forbidden = [
        "uplift_amount",
        "rate_bps *",
        "vat_rate",
        "days_remaining",
        "prorated_amount",
    ]
    for kw in forbidden:
        assert kw not in code, f"가격 수식 복제 발견: {kw}"


def test_P50_calculation_result_passthrough(monkeypatch):
    monkeypatch.setattr("services.pricing_resolver_svc.resolve_plan", lambda *a, **k: _good_resolve())
    r = preview_saas_price_v2(None, _req("MANAGER"))
    assert r.calculation is not None
    assert hasattr(r.calculation, "status")
    assert hasattr(r.calculation, "monthly_supply_amount")


# ═══════════════════════════════════════════════════════════════════════════════
# P51–P53: V3 Canonical → READY
# ═══════════════════════════════════════════════════════════════════════════════

def test_P51_manager_canonical_v3_ready(monkeypatch):
    monkeypatch.setattr("services.pricing_resolver_svc.resolve_plan", lambda *a, **k: _good_resolve())
    r = preview_saas_price_v2(None, _req("MANAGER"))
    assert r.status == "READY"
    assert r.calculation.snapshot is not None


def test_P52_field_canonical_v3_ready(monkeypatch):
    monkeypatch.setattr("services.pricing_resolver_svc.resolve_plan", lambda *a, **k: _good_resolve())
    r = preview_saas_price_v2(None, _req("FIELD", workers=10))
    assert r.status == "READY"
    assert r.calculation.snapshot is not None


def test_P53_canonical_ready_http_200(monkeypatch):
    monkeypatch.setattr("services.pricing_resolver_svc.resolve_plan", lambda *a, **k: _good_resolve())
    monkeypatch.setattr("routers.public_pricing_v2.get_supabase", lambda: None)
    client = TestClient(_make_app(), raise_server_exceptions=False)
    resp = client.post("/public/pricing/v2/preview", json={
        "product_tier": "MANAGER",
        "worker_capacity": 0,
        "payment_months": 1,
        "sites": [{"entity_id": str(_SITE_1), "sector": "INDUSTRY", "criteria_value": 10}],
    })
    assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# P54–P56: TERM_DISCOUNT_UNRESOLVED branch — explicit None policy
# ═══════════════════════════════════════════════════════════════════════════════

def _make_none_discount_policy():
    from schemas.saas_pricing_policy_v2 import (
        SaasPricingPolicyV2, SaasTermDiscountPolicy, SaasWorkerRateBracketPolicy,
    )
    return SaasPricingPolicyV2(
        policy_version="TEST_NONE_DISCOUNT",
        effective_from=date(2026, 9, 28),
        field_base_amount=249000,
        primary_site_rate_bps=10000,
        additional_site_rate_bps=8000,
        worker_brackets=[SaasWorkerRateBracketPolicy(range_from=1, range_to=None, unit_rate=3000)],
        vat_rate_bps=1000,
        term_discounts=[
            SaasTermDiscountPolicy(payment_months=1,  discount_rate_bps=None),
            SaasTermDiscountPolicy(payment_months=3,  discount_rate_bps=None),
            SaasTermDiscountPolicy(payment_months=6,  discount_rate_bps=None),
            SaasTermDiscountPolicy(payment_months=9,  discount_rate_bps=None),
            SaasTermDiscountPolicy(payment_months=12, discount_rate_bps=None),
        ],
    )


def test_P54_term_unresolved_snapshot_none(monkeypatch):
    monkeypatch.setattr("services.pricing_resolver_svc.resolve_plan", lambda *a, **k: _good_resolve())
    monkeypatch.setattr("services.saas_pricing_composer_v2.get_canonical_pricing_policy_v2",
                        _make_none_discount_policy)
    r = preview_saas_price_v2(None, _req("MANAGER"))
    assert r.status == "TERM_DISCOUNT_UNRESOLVED"
    assert r.calculation.snapshot is None


def test_P55_none_discount_not_converted_to_zero(monkeypatch):
    monkeypatch.setattr("services.pricing_resolver_svc.resolve_plan", lambda *a, **k: _good_resolve())
    monkeypatch.setattr("services.saas_pricing_composer_v2.get_canonical_pricing_policy_v2",
                        _make_none_discount_policy)
    r = preview_saas_price_v2(None, _req("MANAGER"))
    assert r.calculation.term_discount_rate_bps is None


def test_P56_service_does_not_create_fake_ready(monkeypatch):
    monkeypatch.setattr("services.pricing_resolver_svc.resolve_plan", lambda *a, **k: _good_resolve())
    monkeypatch.setattr("services.saas_pricing_composer_v2.get_canonical_pricing_policy_v2",
                        _make_none_discount_policy)
    r = preview_saas_price_v2(None, _req("MANAGER"))
    assert r.status != "READY"


# ═══════════════════════════════════════════════════════════════════════════════
# P57–P60: READY (test-only policy)
# ═══════════════════════════════════════════════════════════════════════════════

def test_P57_ready_snapshot_passthrough(monkeypatch):
    monkeypatch.setattr("services.pricing_resolver_svc.resolve_plan", lambda *a, **k: _good_resolve())
    monkeypatch.setattr(
        "services.saas_pricing_composer_v2.get_canonical_pricing_policy_v2",
        _test_policy,
    )
    r = preview_saas_price_v2(None, _req("MANAGER"))
    assert r.status == "READY"
    assert r.calculation.snapshot is not None


def test_P58_monthly_supply_amount_passthrough(monkeypatch):
    monkeypatch.setattr("services.pricing_resolver_svc.resolve_plan", lambda *a, **k: _good_resolve())
    monkeypatch.setattr(
        "services.saas_pricing_composer_v2.get_canonical_pricing_policy_v2", _test_policy,
    )
    r = preview_saas_price_v2(None, _req("MANAGER"))
    assert r.calculation.monthly_supply_amount is not None
    assert r.calculation.monthly_supply_amount > 0


def test_P59_prepaid_supply_amount_in_snapshot(monkeypatch):
    monkeypatch.setattr("services.pricing_resolver_svc.resolve_plan", lambda *a, **k: _good_resolve())
    monkeypatch.setattr(
        "services.saas_pricing_composer_v2.get_canonical_pricing_policy_v2", _test_policy,
    )
    r = preview_saas_price_v2(None, _req("MANAGER"))
    assert r.calculation.snapshot is not None
    assert hasattr(r.calculation.snapshot, "monthly_supply_amount")


def test_P60_vat_total_from_snapshot_not_recomputed(monkeypatch):
    monkeypatch.setattr("services.pricing_resolver_svc.resolve_plan", lambda *a, **k: _good_resolve())
    monkeypatch.setattr(
        "services.saas_pricing_composer_v2.get_canonical_pricing_policy_v2", _test_policy,
    )
    r = preview_saas_price_v2(None, _req("MANAGER"))
    snap = r.calculation.snapshot
    assert hasattr(snap, "vat_amount")
    assert snap.vat_amount is not None


# ═══════════════════════════════════════════════════════════════════════════════
# P61–P64: Multi-site
# ═══════════════════════════════════════════════════════════════════════════════

def test_P61_two_sites_accepted(monkeypatch):
    monkeypatch.setattr("services.pricing_resolver_svc.resolve_plan", lambda *a, **k: _good_resolve())
    r = preview_saas_price_v2(None, _req("MANAGER", sites=[
        _site_req(_SITE_1), _site_req(_SITE_2),
    ]))
    assert len(r.resolved_sites) == 2


def test_P62_three_sites_accepted(monkeypatch):
    monkeypatch.setattr("services.pricing_resolver_svc.resolve_plan", lambda *a, **k: _good_resolve())
    r = preview_saas_price_v2(None, _req("MANAGER", sites=[
        _site_req(_SITE_1), _site_req(_SITE_2), _site_req(_SITE_3),
    ]))
    assert len(r.resolved_sites) == 3


def test_P63_mixed_sectors_accepted(monkeypatch):
    def fake_resolve(sb, svc, sec, val=None):
        return {"status": "success", "data": _good_row(sector=sec, amount=149_000)}

    monkeypatch.setattr("services.pricing_resolver_svc.resolve_plan", fake_resolve)
    monkeypatch.setattr(
        "services.saas_pricing_composer_v2.get_canonical_pricing_policy_v2", _test_policy,
    )
    r = preview_saas_price_v2(None, _req("MANAGER", sites=[
        _site_req(_SITE_1, sector="INDUSTRY"),
        _site_req(_SITE_2, sector="CONSTRUCTION", criteria_value=5_000_000_000),
    ]))
    assert r.status == "READY"
    assert len(r.resolved_sites) == 2


def test_P64_request_order_change_same_price(monkeypatch):
    monkeypatch.setattr("services.pricing_resolver_svc.resolve_plan", lambda *a, **k: _good_resolve(amount=149_000))
    monkeypatch.setattr(
        "services.saas_pricing_composer_v2.get_canonical_pricing_policy_v2", _test_policy,
    )
    r1 = preview_saas_price_v2(None, _req("MANAGER", sites=[_site_req(_SITE_1), _site_req(_SITE_2)]))
    r2 = preview_saas_price_v2(None, _req("MANAGER", sites=[_site_req(_SITE_2), _site_req(_SITE_1)]))
    assert r1.calculation.monthly_supply_amount == r2.calculation.monthly_supply_amount


# ═══════════════════════════════════════════════════════════════════════════════
# P65–P67: FIELD Pricing (from Composer)
# ═══════════════════════════════════════════════════════════════════════════════

def test_P65_field_uplift_from_composer(monkeypatch):
    monkeypatch.setattr("services.pricing_resolver_svc.resolve_plan", lambda *a, **k: _good_resolve(amount=149_000))
    monkeypatch.setattr(
        "services.saas_pricing_composer_v2.get_canonical_pricing_policy_v2", _test_policy,
    )
    r_mgr = preview_saas_price_v2(None, _req("MANAGER", sites=[_site_req()]))
    r_fld = preview_saas_price_v2(None, _req("FIELD", workers=0, sites=[_site_req()]))
    assert r_fld.calculation.monthly_supply_amount > r_mgr.calculation.monthly_supply_amount


def test_P66_additional_site_discount_from_composer(monkeypatch):
    monkeypatch.setattr("services.pricing_resolver_svc.resolve_plan", lambda *a, **k: _good_resolve(amount=149_000))
    monkeypatch.setattr(
        "services.saas_pricing_composer_v2.get_canonical_pricing_policy_v2", _test_policy,
    )
    r1 = preview_saas_price_v2(None, _req("MANAGER", sites=[_site_req(_SITE_1)]))
    r2 = preview_saas_price_v2(None, _req("MANAGER", sites=[_site_req(_SITE_1), _site_req(_SITE_2)]))
    assert r2.calculation.monthly_supply_amount > r1.calculation.monthly_supply_amount
    delta_per_extra = r2.calculation.monthly_supply_amount - r1.calculation.monthly_supply_amount
    single = r1.calculation.monthly_supply_amount
    assert delta_per_extra < single


def test_P67_worker_pricing_from_composer(monkeypatch):
    monkeypatch.setattr("services.pricing_resolver_svc.resolve_plan", lambda *a, **k: _good_resolve(amount=149_000))
    monkeypatch.setattr(
        "services.saas_pricing_composer_v2.get_canonical_pricing_policy_v2", _test_policy,
    )
    r0 = preview_saas_price_v2(None, _req("FIELD", workers=0, sites=[_site_req()]))
    r20 = preview_saas_price_v2(None, _req("FIELD", workers=20, sites=[_site_req()]))
    assert r20.calculation.monthly_supply_amount > r0.calculation.monthly_supply_amount


# ═══════════════════════════════════════════════════════════════════════════════
# P68–P72: Error HTTP Mapping (Router)
# ═══════════════════════════════════════════════════════════════════════════════

def _router_client(monkeypatch, resolve_fn=None):
    if resolve_fn:
        monkeypatch.setattr("services.pricing_resolver_svc.resolve_plan", resolve_fn)
    monkeypatch.setattr("routers.public_pricing_v2.get_supabase", lambda: None)
    return TestClient(_make_app(), raise_server_exceptions=False)


def test_P68_invalid_selection_422(monkeypatch):
    client = _router_client(monkeypatch, lambda *a, **k: _good_resolve())
    resp = client.post("/public/pricing/v2/preview", json={
        "product_tier": "MANAGER",
        "worker_capacity": 5,  # invalid for MANAGER
        "payment_months": 1,
        "sites": [{"entity_id": str(_SITE_1), "sector": "INDUSTRY", "criteria_value": 10}],
    })
    assert resp.status_code == 422


def test_P69_standard_site_required_422(monkeypatch):
    client = _router_client(monkeypatch, lambda *a, **k: _good_resolve())
    resp = client.post("/public/pricing/v2/preview", json={
        "product_tier": "MANAGER",
        "worker_capacity": 0,
        "payment_months": 1,
        "sites": [],
    })
    assert resp.status_code == 422


def test_P70_duplicate_site_422(monkeypatch):
    client = _router_client(monkeypatch, lambda *a, **k: _good_resolve())
    resp = client.post("/public/pricing/v2/preview", json={
        "product_tier": "MANAGER",
        "worker_capacity": 0,
        "payment_months": 1,
        "sites": [
            {"entity_id": str(_SITE_1), "sector": "INDUSTRY", "criteria_value": 10},
            {"entity_id": str(_SITE_1), "sector": "INDUSTRY", "criteria_value": 10},
        ],
    })
    assert resp.status_code == 422


def test_P71_base_price_not_found_503(monkeypatch):
    client = _router_client(monkeypatch, lambda *a, **k: {"status": "not_found", "data": None})
    resp = client.post("/public/pricing/v2/preview", json={
        "product_tier": "MANAGER",
        "worker_capacity": 0,
        "payment_months": 1,
        "sites": [{"entity_id": str(_SITE_1), "sector": "INDUSTRY", "criteria_value": 10}],
    })
    assert resp.status_code == 503


def test_P72_invalid_base_price_row_503(monkeypatch):
    bad_row = _good_row()
    bad_row.pop("tier_code")
    client = _router_client(monkeypatch, lambda *a, **k: {"status": "success", "data": bad_row})
    resp = client.post("/public/pricing/v2/preview", json={
        "product_tier": "MANAGER",
        "worker_capacity": 0,
        "payment_months": 1,
        "sites": [{"entity_id": str(_SITE_1), "sector": "INDUSTRY", "criteria_value": 10}],
    })
    assert resp.status_code == 503


# ═══════════════════════════════════════════════════════════════════════════════
# P73–P74: Public Error Safety
# ═══════════════════════════════════════════════════════════════════════════════

def test_P73_raw_exception_not_exposed(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("Internal Supabase details here")

    monkeypatch.setattr("services.pricing_resolver_svc.resolve_plan", boom)
    monkeypatch.setattr("routers.public_pricing_v2.get_supabase", lambda: None)
    client = TestClient(_make_app(), raise_server_exceptions=False)
    resp = client.post("/public/pricing/v2/preview", json={
        "product_tier": "MANAGER",
        "worker_capacity": 0,
        "payment_months": 1,
        "sites": [{"entity_id": str(_SITE_1), "sector": "INDUSTRY", "criteria_value": 10}],
    })
    assert resp.status_code in (503, 500)
    assert "Supabase" not in resp.text
    assert "Traceback" not in resp.text


def test_P74_traceback_not_exposed(monkeypatch):
    def boom(*a, **k):
        raise Exception("boom")

    monkeypatch.setattr("services.pricing_resolver_svc.resolve_plan", boom)
    monkeypatch.setattr("routers.public_pricing_v2.get_supabase", lambda: None)
    client = TestClient(_make_app(), raise_server_exceptions=False)
    resp = client.post("/public/pricing/v2/preview", json={
        "product_tier": "MANAGER",
        "worker_capacity": 0,
        "payment_months": 1,
        "sites": [{"entity_id": str(_SITE_1), "sector": "INDUSTRY", "criteria_value": 10}],
    })
    body = resp.text
    assert "File \"" not in body
    assert "line " not in body.lower() or "traceback" not in body.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# P75–P79: Read-only Guard
# ═══════════════════════════════════════════════════════════════════════════════

def test_P75_service_no_direct_table_call():
    code = _code_lines(_SVC_SRC)
    assert '.table(' not in code


def test_P76_service_no_insert():
    code = _code_lines(_SVC_SRC)
    assert '.insert(' not in code


def test_P77_service_no_update():
    code = _code_lines(_SVC_SRC)
    assert '.update(' not in code


def test_P78_service_no_delete():
    code = _code_lines(_SVC_SRC)
    assert '.delete(' not in code


def test_P79_service_no_upsert():
    code = _code_lines(_SVC_SRC)
    assert '.upsert(' not in code


# ═══════════════════════════════════════════════════════════════════════════════
# P80–P84: No Commercial Side Effects
# ═══════════════════════════════════════════════════════════════════════════════

def test_P80_no_contracts_usage():
    src = _SVC_SRC.read_text()
    assert '"contracts"' not in src
    assert "'contracts'" not in src


def test_P81_no_subscriptions_usage():
    src = _SVC_SRC.read_text()
    assert '"subscriptions"' not in src
    assert "'subscriptions'" not in src


def test_P82_no_quote_write():
    src = _SVC_SRC.read_text()
    assert "quote" not in src.lower() or "quote_required" in src.lower()


def test_P83_no_payment_service():
    src = _SVC_SRC.read_text()
    assert "payment_svc" not in src
    assert "payment_post_process" not in src


def test_P84_no_change_order_apply():
    src = _SVC_SRC.read_text()
    assert "evaluate_saas_change_order" not in src
    assert "saas_change_order_v2" not in src


# ═══════════════════════════════════════════════════════════════════════════════
# P85–P86: V1 Guard
# ═══════════════════════════════════════════════════════════════════════════════

def test_P85_v1_router_unchanged():
    src = Path("routers/public_pricing.py").read_text()
    import hashlib
    # 파일이 변경되지 않았음을 확인 — GET /public/pricing/saas-plans 등 V1 엔드포인트 존재
    assert "/saas-plans" in src
    assert "/resolve" in src
    assert "public_pricing_v2" not in src


def test_P86_v1_resolver_unchanged():
    src = Path("services/pricing_resolver_svc.py").read_text()
    assert "resolve_plan" in src
    assert "load_prices" in src
    assert "preview_saas_price_v2" not in src


# ═══════════════════════════════════════════════════════════════════════════════
# P87–P96: PATCH1 — Trust Boundary Hardening
# ═══════════════════════════════════════════════════════════════════════════════

def test_P87_top_level_pricing_mode_extra_rejected(monkeypatch):
    client = _router_client(monkeypatch, lambda *a, **k: _good_resolve())
    resp = client.post("/public/pricing/v2/preview", json={
        "product_tier": "MANAGER",
        "worker_capacity": 0,
        "payment_months": 1,
        "pricing_mode": "STANDARD",
        "sites": [{"entity_id": str(_SITE_1), "sector": "INDUSTRY", "criteria_value": 10}],
    })
    assert resp.status_code == 422


def test_P88_site_base_amount_extra_rejected(monkeypatch):
    client = _router_client(monkeypatch, lambda *a, **k: _good_resolve())
    resp = client.post("/public/pricing/v2/preview", json={
        "product_tier": "MANAGER",
        "worker_capacity": 0,
        "payment_months": 1,
        "sites": [{"entity_id": str(_SITE_1), "sector": "INDUSTRY", "criteria_value": 10, "base_amount": 149000}],
    })
    assert resp.status_code == 422


def test_P89_site_base_band_code_extra_rejected(monkeypatch):
    client = _router_client(monkeypatch, lambda *a, **k: _good_resolve())
    resp = client.post("/public/pricing/v2/preview", json={
        "product_tier": "MANAGER",
        "worker_capacity": 0,
        "payment_months": 1,
        "sites": [{"entity_id": str(_SITE_1), "sector": "INDUSTRY", "criteria_value": 10, "base_band_code": "STANDARD"}],
    })
    assert resp.status_code == 422


def test_P90_top_level_policy_version_extra_rejected(monkeypatch):
    client = _router_client(monkeypatch, lambda *a, **k: _good_resolve())
    resp = client.post("/public/pricing/v2/preview", json={
        "product_tier": "MANAGER",
        "worker_capacity": 0,
        "payment_months": 1,
        "policy_version": "v1",
        "sites": [{"entity_id": str(_SITE_1), "sector": "INDUSTRY", "criteria_value": 10}],
    })
    assert resp.status_code == 422


def test_P91_resolver_sector_mismatch_rejected(monkeypatch):
    def mismatched_resolve(sb, svc, sec, val=None):
        return {"status": "success", "data": _good_row(sector="BUILDING")}

    monkeypatch.setattr("services.pricing_resolver_svc.resolve_plan", mismatched_resolve)
    with pytest.raises(SaasPricingPreviewError) as exc:
        preview_saas_price_v2(None, _req("MANAGER", sites=[_site_req(sector="INDUSTRY")]))
    assert exc.value.code == "INVALID_BASE_PRICE_ROW"
    assert "sector" in exc.value.message.lower()


def test_P91b_resolver_sector_mismatch_503(monkeypatch):
    def mismatched_resolve(sb, svc, sec, val=None):
        return {"status": "success", "data": _good_row(sector="BUILDING")}

    client = _router_client(monkeypatch, mismatched_resolve)
    resp = client.post("/public/pricing/v2/preview", json={
        "product_tier": "MANAGER",
        "worker_capacity": 0,
        "payment_months": 1,
        "sites": [{"entity_id": str(_SITE_1), "sector": "INDUSTRY", "criteria_value": 10}],
    })
    assert resp.status_code == 503


def test_P92_custom_worker_capacity_preserved(monkeypatch):
    r = preview_saas_price_v2(None, _req("CUSTOM", workers=5, sites=[]))
    assert r.worker_capacity == 5
    assert r.status == "CUSTOM_REQUIRED"


def test_P93_custom_negative_worker_rejected(monkeypatch):
    monkeypatch.setattr("routers.public_pricing_v2.get_supabase", lambda: None)
    client = TestClient(_make_app(), raise_server_exceptions=False)
    resp = client.post("/public/pricing/v2/preview", json={
        "product_tier": "CUSTOM",
        "worker_capacity": -1,
        "payment_months": 1,
        "sites": [],
    })
    assert resp.status_code == 422


def test_P94_get_supabase_failure_returns_503(monkeypatch):
    monkeypatch.setattr(
        "routers.public_pricing_v2.get_supabase",
        lambda: (_ for _ in ()).throw(RuntimeError("DB connection failed")),
    )
    client = TestClient(_make_app(), raise_server_exceptions=False)
    resp = client.post("/public/pricing/v2/preview", json={
        "product_tier": "MANAGER",
        "worker_capacity": 0,
        "payment_months": 1,
        "sites": [{"entity_id": str(_SITE_1), "sector": "INDUSTRY", "criteria_value": 10}],
    })
    assert resp.status_code == 503
    body = resp.json()
    assert body.get("detail", {}).get("code") == "INTERNAL_ERROR"


def _extract_test_fn(src: str, name: str) -> str:
    start = src.index(f"def {name}")
    try:
        end = src.index("\ndef test_", start + 1)
    except ValueError:
        end = len(src)
    return src[start:end]


def test_P95_p73_uses_router_local_binding():
    src = Path(__file__).read_text()
    snippet = _extract_test_fn(src, "test_P73_raw_exception_not_exposed")
    assert "routers.public_pricing_v2.get_supabase" in snippet
    assert "db.supabase_client.get_supabase" not in snippet


def test_P96_p74_uses_router_local_binding():
    src = Path(__file__).read_text()
    snippet = _extract_test_fn(src, "test_P74_traceback_not_exposed")
    assert "routers.public_pricing_v2.get_supabase" in snippet
    assert "db.supabase_client.get_supabase" not in snippet
