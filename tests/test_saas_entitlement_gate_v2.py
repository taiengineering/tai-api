"""Tests for WO-PRICING-V2-BE-OBJ06 — Product Tier Entitlement Gate V2.

Coverage: E01–E50 (50 tests)
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import List

import pytest
from pydantic import ValidationError

from schemas.saas_entitlement_v2 import (
    ENTITLEMENT_CANONICAL_ORDER,
    SaasEntitlementContextV2,
)
from services.saas_entitlement_gate_v2 import (
    FIELD_ENTITLEMENTS,
    MANAGER_ENTITLEMENTS,
    SaasEntitlementGateError,
    evaluate_saas_entitlement_v2,
    evaluate_saas_entitlements_v2,
    resolve_effective_entitlements_v2,
)

_GATE_SRC = Path(__file__).parent.parent / "services" / "saas_entitlement_gate_v2.py"
_SCHEMA_SRC = Path(__file__).parent.parent / "schemas" / "saas_entitlement_v2.py"

ALL_CODES = list(ENTITLEMENT_CANONICAL_ORDER)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mgr():
    return SaasEntitlementContextV2(product_tier="MANAGER")


def _field():
    return SaasEntitlementContextV2(product_tier="FIELD")


def _custom(entitlements=None):
    return SaasEntitlementContextV2(product_tier="CUSTOM", custom_entitlements=entitlements)


# ── E01–E06: MANAGER Evaluation ───────────────────────────────────────────────

def test_E01_manager_compliance_core_allowed():
    r = evaluate_saas_entitlement_v2(_mgr(), "COMPLIANCE_CORE")
    assert r.status == "ALLOWED"


def test_E02_manager_field_tbm_denied():
    r = evaluate_saas_entitlement_v2(_mgr(), "FIELD_TBM")
    assert r.status == "DENIED"


def test_E03_manager_field_ra_denied():
    r = evaluate_saas_entitlement_v2(_mgr(), "FIELD_RA")
    assert r.status == "DENIED"


def test_E04_manager_field_inspection_denied():
    r = evaluate_saas_entitlement_v2(_mgr(), "FIELD_INSPECTION")
    assert r.status == "DENIED"


def test_E05_manager_field_sign_denied():
    r = evaluate_saas_entitlement_v2(_mgr(), "FIELD_SIGN")
    assert r.status == "DENIED"


def test_E06_manager_field_hazard_denied():
    r = evaluate_saas_entitlement_v2(_mgr(), "FIELD_HAZARD_REPORT")
    assert r.status == "DENIED"


# ── E07–E12: FIELD Evaluation ─────────────────────────────────────────────────

def test_E07_field_compliance_core_allowed():
    r = evaluate_saas_entitlement_v2(_field(), "COMPLIANCE_CORE")
    assert r.status == "ALLOWED"


def test_E08_field_tbm_allowed():
    r = evaluate_saas_entitlement_v2(_field(), "FIELD_TBM")
    assert r.status == "ALLOWED"


def test_E09_field_ra_allowed():
    r = evaluate_saas_entitlement_v2(_field(), "FIELD_RA")
    assert r.status == "ALLOWED"


def test_E10_field_inspection_allowed():
    r = evaluate_saas_entitlement_v2(_field(), "FIELD_INSPECTION")
    assert r.status == "ALLOWED"


def test_E11_field_sign_allowed():
    r = evaluate_saas_entitlement_v2(_field(), "FIELD_SIGN")
    assert r.status == "ALLOWED"


def test_E12_field_hazard_allowed():
    r = evaluate_saas_entitlement_v2(_field(), "FIELD_HAZARD_REPORT")
    assert r.status == "ALLOWED"


# ── E13–E15: Tier Set Contract ────────────────────────────────────────────────

def test_E13_manager_effective_set_exact():
    effective = resolve_effective_entitlements_v2(_mgr())
    assert effective == ["COMPLIANCE_CORE"]


def test_E14_field_effective_set_exact():
    effective = resolve_effective_entitlements_v2(_field())
    assert effective == [
        "COMPLIANCE_CORE",
        "FIELD_TBM",
        "FIELD_RA",
        "FIELD_INSPECTION",
        "FIELD_SIGN",
        "FIELD_HAZARD_REPORT",
    ]


def test_E15_manager_strict_subset_of_field():
    mgr_set = set(MANAGER_ENTITLEMENTS)
    field_set = set(FIELD_ENTITLEMENTS)
    assert mgr_set < field_set


# ── E16–E18: CUSTOM No Context ────────────────────────────────────────────────

def test_E16_custom_none_compliance_core():
    r = evaluate_saas_entitlement_v2(_custom(None), "COMPLIANCE_CORE")
    assert r.status == "CUSTOM_CONTEXT_REQUIRED"


def test_E17_custom_none_field_tbm():
    r = evaluate_saas_entitlement_v2(_custom(None), "FIELD_TBM")
    assert r.status == "CUSTOM_CONTEXT_REQUIRED"


def test_E18_custom_none_effective_set_empty():
    effective = resolve_effective_entitlements_v2(_custom(None))
    assert effective == []


# ── E19–E22: CUSTOM Explicit ──────────────────────────────────────────────────

def test_E19_custom_explicit_compliance_core_allowed():
    ctx = _custom(["COMPLIANCE_CORE"])
    r = evaluate_saas_entitlement_v2(ctx, "COMPLIANCE_CORE")
    assert r.status == "ALLOWED"


def test_E20_custom_explicit_outside_set_denied():
    ctx = _custom(["COMPLIANCE_CORE"])
    r = evaluate_saas_entitlement_v2(ctx, "FIELD_TBM")
    assert r.status == "DENIED"


def test_E21_custom_explicit_field_tbm_allowed():
    ctx = _custom(["FIELD_TBM"])
    r = evaluate_saas_entitlement_v2(ctx, "FIELD_TBM")
    assert r.status == "ALLOWED"


def test_E22_custom_explicit_mixed_composition():
    ctx = _custom(["COMPLIANCE_CORE", "FIELD_RA", "FIELD_SIGN"])
    assert evaluate_saas_entitlement_v2(ctx, "COMPLIANCE_CORE").status == "ALLOWED"
    assert evaluate_saas_entitlement_v2(ctx, "FIELD_RA").status == "ALLOWED"
    assert evaluate_saas_entitlement_v2(ctx, "FIELD_SIGN").status == "ALLOWED"
    assert evaluate_saas_entitlement_v2(ctx, "FIELD_TBM").status == "DENIED"
    assert evaluate_saas_entitlement_v2(ctx, "FIELD_INSPECTION").status == "DENIED"
    assert evaluate_saas_entitlement_v2(ctx, "FIELD_HAZARD_REPORT").status == "DENIED"


# ── E23–E25: CUSTOM Empty Set ─────────────────────────────────────────────────

def test_E23_custom_empty_compliance_core_denied():
    ctx = _custom([])
    r = evaluate_saas_entitlement_v2(ctx, "COMPLIANCE_CORE")
    assert r.status == "DENIED"


def test_E24_custom_empty_field_tbm_denied():
    ctx = _custom([])
    r = evaluate_saas_entitlement_v2(ctx, "FIELD_TBM")
    assert r.status == "DENIED"


def test_E25_custom_empty_not_context_required():
    ctx = _custom([])
    r = evaluate_saas_entitlement_v2(ctx, "COMPLIANCE_CORE")
    assert r.status != "CUSTOM_CONTEXT_REQUIRED"


# ── E26–E27: Invalid Override ─────────────────────────────────────────────────

def test_E26_manager_custom_override_rejected():
    with pytest.raises(ValidationError):
        SaasEntitlementContextV2(
            product_tier="MANAGER",
            custom_entitlements=["COMPLIANCE_CORE"],
        )


def test_E27_field_custom_override_rejected():
    with pytest.raises(ValidationError):
        SaasEntitlementContextV2(
            product_tier="FIELD",
            custom_entitlements=["FIELD_TBM"],
        )


# ── E28: Duplicate Custom Context ─────────────────────────────────────────────

def test_E28_custom_duplicate_entitlement_rejected():
    with pytest.raises(ValidationError):
        SaasEntitlementContextV2(
            product_tier="CUSTOM",
            custom_entitlements=["FIELD_TBM", "FIELD_TBM"],
        )


# ── E29–E30: Unknown Code ─────────────────────────────────────────────────────

def test_E29_unknown_requested_entitlement_rejected():
    with pytest.raises(ValidationError):
        evaluate_saas_entitlement_v2(
            _mgr(),
            "UNKNOWN_FEATURE",  # type: ignore[arg-type]
        )


def test_E30_unknown_custom_entitlement_rejected():
    with pytest.raises(ValidationError):
        SaasEntitlementContextV2(
            product_tier="CUSTOM",
            custom_entitlements=["UNKNOWN_FEATURE"],  # type: ignore[list-item]
        )


# ── E31–E35: Batch Evaluation ─────────────────────────────────────────────────

def test_E31_manager_batch_exact():
    result = evaluate_saas_entitlements_v2(_mgr(), ALL_CODES)
    statuses = {d.requested_entitlement: d.status for d in result.decisions}
    assert statuses["COMPLIANCE_CORE"] == "ALLOWED"
    for code in ["FIELD_TBM", "FIELD_RA", "FIELD_INSPECTION", "FIELD_SIGN", "FIELD_HAZARD_REPORT"]:
        assert statuses[code] == "DENIED"


def test_E32_field_batch_exact():
    result = evaluate_saas_entitlements_v2(_field(), ALL_CODES)
    assert all(d.status == "ALLOWED" for d in result.decisions)


def test_E33_custom_none_batch_all_context_required():
    result = evaluate_saas_entitlements_v2(_custom(None), ALL_CODES)
    assert all(d.status == "CUSTOM_CONTEXT_REQUIRED" for d in result.decisions)


def test_E34_custom_explicit_batch_membership():
    ctx = _custom(["COMPLIANCE_CORE", "FIELD_TBM"])
    result = evaluate_saas_entitlements_v2(ctx, ALL_CODES)
    statuses = {d.requested_entitlement: d.status for d in result.decisions}
    assert statuses["COMPLIANCE_CORE"] == "ALLOWED"
    assert statuses["FIELD_TBM"] == "ALLOWED"
    assert statuses["FIELD_RA"] == "DENIED"
    assert statuses["FIELD_INSPECTION"] == "DENIED"
    assert statuses["FIELD_SIGN"] == "DENIED"
    assert statuses["FIELD_HAZARD_REPORT"] == "DENIED"


def test_E35_batch_duplicate_request_rejected():
    with pytest.raises(SaasEntitlementGateError) as exc_info:
        evaluate_saas_entitlements_v2(_mgr(), ["COMPLIANCE_CORE", "COMPLIANCE_CORE"])
    assert exc_info.value.code == "DUPLICATE_REQUESTED_ENTITLEMENT"


# ── E36–E38: Determinism ──────────────────────────────────────────────────────

def test_E36_custom_entitlement_input_reorder_same_effective_order():
    ctx_a = _custom(["FIELD_TBM", "COMPLIANCE_CORE"])
    ctx_b = _custom(["COMPLIANCE_CORE", "FIELD_TBM"])
    assert resolve_effective_entitlements_v2(ctx_a) == resolve_effective_entitlements_v2(ctx_b)


def test_E37_batch_requested_reorder_same_result_order():
    result_a = evaluate_saas_entitlements_v2(_field(), ["FIELD_TBM", "COMPLIANCE_CORE"])
    result_b = evaluate_saas_entitlements_v2(_field(), ["COMPLIANCE_CORE", "FIELD_TBM"])
    codes_a = [d.requested_entitlement for d in result_a.decisions]
    codes_b = [d.requested_entitlement for d in result_b.decisions]
    assert codes_a == codes_b


def test_E38_same_input_twice_exact_same_output():
    ctx = _custom(["COMPLIANCE_CORE", "FIELD_RA"])
    r1 = evaluate_saas_entitlement_v2(ctx, "COMPLIANCE_CORE")
    r2 = evaluate_saas_entitlement_v2(ctx, "COMPLIANCE_CORE")
    assert r1.model_dump() == r2.model_dump()


# ── E39–E48: Source Guard ─────────────────────────────────────────────────────

def _code_lines(path: Path) -> str:
    lines = path.read_text().splitlines()
    return "\n".join(
        ln for ln in lines if not ln.lstrip().startswith(("#", '"""', "- "))
    )


def test_E39_no_commercial_fit_import():
    src = _GATE_SRC.read_text()
    assert "commercial_fit" not in src
    assert "saas_commercial_fit" not in src


def test_E40_no_site_scope():
    src = _GATE_SRC.read_text()
    for kw in ["site_scope", "SiteScope", "entity_type", "entity_id"]:
        assert kw not in src, f"Site scope 키워드 발견: {kw}"


def test_E41_no_worker_capacity():
    src = _GATE_SRC.read_text()
    for kw in ["worker_capacity", "actual_worker_count"]:
        assert kw not in src, f"Worker 키워드 발견: {kw}"


def test_E42_no_pricing_resolver():
    code = _code_lines(_GATE_SRC)
    for kw in ["pricing_resolver", "tier_payment_gate", "tier_upgrade_svc"]:
        assert kw not in code, f"V1 의존 키워드 발견: {kw}"


def test_E43_no_plan_code():
    code = _code_lines(_GATE_SRC)
    assert "plan_code" not in code


def test_E44_no_contract_level():
    code = _code_lines(_GATE_SRC)
    for kw in ["contract_level", "tier_code"]:
        assert kw not in code, f"계약 등급 키워드 발견: {kw}"


def test_E45_no_price_calculation():
    code = _code_lines(_GATE_SRC)
    for kw in ["total_amount", "base_amount", "unit_price"]:
        assert kw not in code, f"가격 계산 키워드 발견: {kw}"


def test_E46_no_payment():
    code = _code_lines(_GATE_SRC)
    for kw in ["payment", "billing", "refund"]:
        assert kw not in code, f"결제 키워드 발견: {kw}"


def test_E47_no_db_io():
    src = _GATE_SRC.read_text()
    for kw in ["supabase", "execute_sql", "get_supabase", "psycopg"]:
        assert kw not in src, f"DB I/O 키워드 발견: {kw}"


def test_E48_no_router():
    src = _GATE_SRC.read_text()
    for kw in ["APIRouter", "from routers", "import routers"]:
        assert kw not in src, f"Router 키워드 발견: {kw}"


# ── E49–E50: LEG Core Contract ────────────────────────────────────────────────

def test_E49_manager_compliance_core_leg_contract():
    r = evaluate_saas_entitlement_v2(_mgr(), "COMPLIANCE_CORE")
    assert r.status == "ALLOWED"


def test_E50_field_compliance_core_leg_contract():
    r = evaluate_saas_entitlement_v2(_field(), "COMPLIANCE_CORE")
    assert r.status == "ALLOWED"


# ── E51–E54: PATCH1 — Immutability + Batch Validation ────────────────────────

def test_E51_canonical_order_is_immutable_tuple():
    from schemas.saas_entitlement_v2 import ENTITLEMENT_CANONICAL_ORDER
    assert isinstance(ENTITLEMENT_CANONICAL_ORDER, tuple)
    assert not isinstance(ENTITLEMENT_CANONICAL_ORDER, list)


def test_E51b_manager_entitlements_is_tuple():
    assert isinstance(MANAGER_ENTITLEMENTS, tuple)


def test_E51c_field_entitlements_is_tuple():
    assert isinstance(FIELD_ENTITLEMENTS, tuple)


def test_E52_batch_unknown_entitlement_rejected():
    with pytest.raises(Exception) as exc_info:
        evaluate_saas_entitlements_v2(
            _mgr(),
            ["UNKNOWN_FEATURE"],  # type: ignore[list-item]
        )
    assert type(exc_info.value).__name__ != "KeyError"


def test_E53_batch_unknown_does_not_expose_key_error():
    try:
        evaluate_saas_entitlements_v2(
            _mgr(),
            ["TOTALLY_INVALID"],  # type: ignore[list-item]
        )
    except KeyError:
        pytest.fail("KeyError가 외부로 노출됨 — ValidationError여야 합니다.")
    except Exception:
        pass  # ValidationError 또는 SaasEntitlementGateError 허용


def test_E54_valid_batch_canonical_order():
    result = evaluate_saas_entitlements_v2(
        _field(),
        ["FIELD_HAZARD_REPORT", "COMPLIANCE_CORE", "FIELD_TBM"],
    )
    codes = [d.requested_entitlement for d in result.decisions]
    assert codes == ["COMPLIANCE_CORE", "FIELD_TBM", "FIELD_HAZARD_REPORT"]
