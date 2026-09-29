"""Tests for BE-V3-OBJ04: Entitlement Runtime V2.

E01–E12: Runtime integration tests (mock Supabase).
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from services.saas_entitlement_runtime_v2 import (
    SaasEntitlementRuntimeDecisionV2,
    SaasEntitlementRuntimeError,
    SaasEntitlementResolutionV2,
    evaluate_saas_entitlement_runtime_v2,
    resolve_saas_entitlement_context_v2,
)

# ── Fixed test anchors ────────────────────────────────────────────────────────

_AS_OF = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)

_COMPANY_ID = str(uuid4())
_CONTRACT_ID = str(uuid4())
_CV_ID = str(uuid4())

_PAST   = "2026-09-01T00:00:00+00:00"
_MID    = "2026-09-15T00:00:00+00:00"
_FUTURE = "2026-10-01T00:00:00+00:00"


# ── Mock Supabase ─────────────────────────────────────────────────────────────

class _R:
    def __init__(self, data):
        self.data = data


class _Q:
    def __init__(self, data):
        self._data = data

    def select(self, *_):
        return self

    def eq(self, *_):
        return self

    def limit(self, *_):
        return self

    def execute(self):
        return _R(list(self._data))


class _MockSupabase:
    """Simple mock Supabase — returns preset rows per table name, ignores filters."""

    def __init__(self, tables: dict):
        self._tables = tables

    def table(self, name: str) -> _Q:
        return _Q(self._tables.get(name, []))


def _supabase(contracts=None, cvs=None) -> _MockSupabase:
    return _MockSupabase({
        "contracts": contracts or [],
        "saas_contract_commercial_versions": cvs or [],
    })


# ── Data builders ─────────────────────────────────────────────────────────────

def _contract(contract_id=None, company_id=None):
    return {
        "id": contract_id or _CONTRACT_ID,
        "company_id": company_id or _COMPANY_ID,
        "service_type": "SAAS",
        "status_code": "ACTIVE",
        "is_active": True,
    }


def _cv(
    product_tier: str,
    version_no: int = 1,
    effective_from: str = _PAST,
    superseded_at=None,
    contract_id=None,
    plan_code=None,
    cv_id=None,
):
    row = {
        "id": cv_id or _CV_ID,
        "contract_id": contract_id or _CONTRACT_ID,
        "version_no": version_no,
        "product_tier": product_tier,
        "effective_from": effective_from,
        "superseded_at": superseded_at,
    }
    if plan_code is not None:
        row["plan_code"] = plan_code
    return row


# ── E01–E05: Tier entitlement decisions ───────────────────────────────────────

def test_E01_manager_compliance_core_allowed():
    sb = _supabase(
        contracts=[_contract()],
        cvs=[_cv("MANAGER")],
    )
    r = evaluate_saas_entitlement_runtime_v2(sb, _COMPANY_ID, _AS_OF, "COMPLIANCE_CORE")
    assert isinstance(r, SaasEntitlementRuntimeDecisionV2)
    assert r.product_tier == "MANAGER"
    assert r.decision.status == "ALLOWED"
    assert r.decision.requested_entitlement == "COMPLIANCE_CORE"


def test_E02_manager_field_tbm_denied():
    sb = _supabase(
        contracts=[_contract()],
        cvs=[_cv("MANAGER")],
    )
    r = evaluate_saas_entitlement_runtime_v2(sb, _COMPANY_ID, _AS_OF, "FIELD_TBM")
    assert r.product_tier == "MANAGER"
    assert r.decision.status == "DENIED"


def test_E03_field_compliance_core_allowed():
    sb = _supabase(
        contracts=[_contract()],
        cvs=[_cv("FIELD")],
    )
    r = evaluate_saas_entitlement_runtime_v2(sb, _COMPANY_ID, _AS_OF, "COMPLIANCE_CORE")
    assert r.product_tier == "FIELD"
    assert r.decision.status == "ALLOWED"


def test_E04_field_field_tbm_allowed():
    sb = _supabase(
        contracts=[_contract()],
        cvs=[_cv("FIELD")],
    )
    r = evaluate_saas_entitlement_runtime_v2(sb, _COMPANY_ID, _AS_OF, "FIELD_TBM")
    assert r.product_tier == "FIELD"
    assert r.decision.status == "ALLOWED"


def test_E05_custom_returns_custom_context_required():
    sb = _supabase(
        contracts=[_contract()],
        cvs=[_cv("CUSTOM")],
    )
    r = evaluate_saas_entitlement_runtime_v2(sb, _COMPANY_ID, _AS_OF, "COMPLIANCE_CORE")
    assert r.product_tier == "CUSTOM"
    assert r.decision.status == "CUSTOM_CONTEXT_REQUIRED"


# ── E06–E09: Contract / CV error paths ───────────────────────────────────────

def test_E06_no_active_contract_raises():
    sb = _supabase(contracts=[], cvs=[])
    with pytest.raises(SaasEntitlementRuntimeError) as exc_info:
        resolve_saas_entitlement_context_v2(sb, _COMPANY_ID, _AS_OF)
    assert exc_info.value.code == "NO_ACTIVE_SAAS_CONTRACT"


def test_E07_ambiguous_contracts_raises():
    sb = _supabase(
        contracts=[_contract(), _contract(contract_id=str(uuid4()))],
        cvs=[_cv("MANAGER")],
    )
    with pytest.raises(SaasEntitlementRuntimeError) as exc_info:
        resolve_saas_entitlement_context_v2(sb, _COMPANY_ID, _AS_OF)
    assert exc_info.value.code == "AMBIGUOUS_ACTIVE_SAAS_CONTRACT"


def test_E08_no_effective_cv_raises():
    # CV effective_from is in the future — not effective at AS_OF
    sb = _supabase(
        contracts=[_contract()],
        cvs=[_cv("MANAGER", effective_from=_FUTURE)],
    )
    with pytest.raises(SaasEntitlementRuntimeError) as exc_info:
        resolve_saas_entitlement_context_v2(sb, _COMPANY_ID, _AS_OF)
    assert exc_info.value.code == "CURRENT_CV_NOT_FOUND"


def test_E09_ambiguous_effective_cvs_raises():
    # Two CVs both effective at AS_OF (both effective_from <= AS_OF, superseded_at=None)
    sb = _supabase(
        contracts=[_contract()],
        cvs=[
            _cv("MANAGER", version_no=1, effective_from=_PAST, superseded_at=None),
            _cv("FIELD",   version_no=2, effective_from=_PAST, superseded_at=None),
        ],
    )
    with pytest.raises(SaasEntitlementRuntimeError) as exc_info:
        resolve_saas_entitlement_context_v2(sb, _COMPANY_ID, _AS_OF)
    assert exc_info.value.code == "CURRENT_CV_AMBIGUOUS"


# ── E10–E11: Temporal selection correctness ───────────────────────────────────

def test_E10_future_renewal_cv_not_used_as_current():
    """Future CV (effective_from > AS_OF) must not be selected as current."""
    current_cv = _cv("MANAGER", version_no=1, effective_from=_PAST, superseded_at=_FUTURE)
    future_cv  = _cv("FIELD",   version_no=2, effective_from=_FUTURE, superseded_at=None)
    sb = _supabase(contracts=[_contract()], cvs=[current_cv, future_cv])

    r = resolve_saas_entitlement_context_v2(sb, _COMPANY_ID, _AS_OF)
    assert r.commercial_version_no == 1
    assert r.product_tier == "MANAGER"


def test_E11_superseded_old_cv_not_selected():
    """Old CV superseded before AS_OF must not be selected; newer current CV is used."""
    old_cv     = _cv("MANAGER", version_no=1, effective_from=_PAST, superseded_at=_MID)
    current_cv = _cv("FIELD",   version_no=2, effective_from=_MID,  superseded_at=None)
    sb = _supabase(contracts=[_contract()], cvs=[old_cv, current_cv])

    r = resolve_saas_entitlement_context_v2(sb, _COMPANY_ID, _AS_OF)
    assert r.commercial_version_no == 2
    assert r.product_tier == "FIELD"


# ── E12: plan_code irrelevance ────────────────────────────────────────────────

def test_E12_legacy_plan_code_irrelevant_entitlement_from_cv_tier():
    """Entitlement is determined by CV.product_tier, not plan_code."""
    # CV is FIELD — plan_code is legacy data, ignored entirely
    cv_row = _cv("FIELD", plan_code="SAAS_FACILITY")
    sb = _supabase(contracts=[_contract()], cvs=[cv_row])

    r = evaluate_saas_entitlement_runtime_v2(sb, _COMPANY_ID, _AS_OF, "FIELD_TBM")
    assert r.product_tier == "FIELD"
    assert r.decision.status == "ALLOWED"


# ── Resolution output structure ───────────────────────────────────────────────

def test_resolution_includes_contract_id_and_version_no():
    sb = _supabase(
        contracts=[_contract()],
        cvs=[_cv("MANAGER", version_no=3)],
    )
    r = resolve_saas_entitlement_context_v2(sb, _COMPANY_ID, _AS_OF)
    assert isinstance(r, SaasEntitlementResolutionV2)
    assert r.contract_id == _CONTRACT_ID
    assert r.commercial_version_id == _CV_ID
    assert r.commercial_version_no == 3
    assert r.product_tier == "MANAGER"


def test_runtime_decision_includes_contract_id_and_version_no():
    sb = _supabase(
        contracts=[_contract()],
        cvs=[_cv("FIELD", version_no=2)],
    )
    r = evaluate_saas_entitlement_runtime_v2(sb, _COMPANY_ID, _AS_OF, "COMPLIANCE_CORE")
    assert isinstance(r, SaasEntitlementRuntimeDecisionV2)
    assert r.contract_id == _CONTRACT_ID
    assert r.commercial_version_no == 2
    assert r.product_tier == "FIELD"


# ── CV schema invalid ─────────────────────────────────────────────────────────

def test_cv_invalid_product_tier_raises():
    bad_cv = _cv("LEGACY_PLAN")  # not a valid ProductTier
    sb = _supabase(contracts=[_contract()], cvs=[bad_cv])
    with pytest.raises(SaasEntitlementRuntimeError) as exc_info:
        resolve_saas_entitlement_context_v2(sb, _COMPANY_ID, _AS_OF)
    assert exc_info.value.code == "CURRENT_CV_SCHEMA_INVALID"
