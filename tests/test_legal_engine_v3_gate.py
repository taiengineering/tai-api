"""Tests for WO-BE-V3-OBJ05: LEG Gate V3 Cutover helpers.

G01–G12: _assert_leg_compliance_core_http + _assert_leg_site_scope_http isolation tests.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException

from routers.legal_engine import (
    _assert_leg_compliance_core_http,
    _assert_leg_site_scope_http,
)

# ── Fixed test anchors ────────────────────────────────────────────────────────

_COMPANY_ID = str(uuid4())
_CONTRACT_ID = str(uuid4())
_CV_ID = str(uuid4())
_FACTORY_ID = str(uuid4())
_SITE_ID = str(uuid4())

# Past relative to current date (2026-09-29) — CV is effective at now_kst()
_PAST   = "2026-09-01T00:00:00+00:00"
# Future — CV not yet effective
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
    def __init__(self, tables: dict):
        self._tables = tables

    def table(self, name: str) -> _Q:
        return _Q(self._tables.get(name, []))


def _supabase(contracts=None, cvs=None, site_scopes=None) -> _MockSupabase:
    return _MockSupabase({
        "contracts": contracts or [],
        "saas_contract_commercial_versions": cvs or [],
        "saas_contract_site_scopes": site_scopes or [],
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


def _cv(product_tier: str, version_no: int = 1, effective_from: str = _PAST,
        superseded_at=None, cv_id=None, contract_id=None):
    return {
        "id": cv_id or _CV_ID,
        "contract_id": contract_id or _CONTRACT_ID,
        "version_no": version_no,
        "product_tier": product_tier,
        "effective_from": effective_from,
        "superseded_at": superseded_at,
    }


def _scope(cv_id=None, entity_type="factory", entity_id=None):
    return {
        "commercial_version_id": cv_id or _CV_ID,
        "entity_type": entity_type,
        "entity_id": entity_id or _FACTORY_ID,
    }


# ── G01–G06: _assert_leg_compliance_core_http ────────────────────────────────

def test_G01_no_contract_raises_403():
    sb = _supabase(contracts=[], cvs=[])
    with pytest.raises(HTTPException) as exc_info:
        _assert_leg_compliance_core_http(sb, _COMPANY_ID)
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["code"] == "NO_ACTIVE_SAAS_CONTRACT"


def test_G02_no_effective_cv_raises_403():
    sb = _supabase(
        contracts=[_contract()],
        cvs=[_cv("MANAGER", effective_from=_FUTURE)],
    )
    with pytest.raises(HTTPException) as exc_info:
        _assert_leg_compliance_core_http(sb, _COMPANY_ID)
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["code"] == "CURRENT_CV_NOT_FOUND"


def test_G03_manager_compliance_core_allowed_returns_resolution():
    sb = _supabase(contracts=[_contract()], cvs=[_cv("MANAGER")])
    resolution = _assert_leg_compliance_core_http(sb, _COMPANY_ID)
    assert resolution.product_tier == "MANAGER"
    assert resolution.commercial_version_id == _CV_ID


def test_G04_field_compliance_core_allowed_returns_resolution():
    sb = _supabase(contracts=[_contract()], cvs=[_cv("FIELD")])
    resolution = _assert_leg_compliance_core_http(sb, _COMPANY_ID)
    assert resolution.product_tier == "FIELD"
    assert resolution.commercial_version_id == _CV_ID


def test_G05_custom_tier_raises_403_saas_entitlement_required():
    sb = _supabase(contracts=[_contract()], cvs=[_cv("CUSTOM")])
    with pytest.raises(HTTPException) as exc_info:
        _assert_leg_compliance_core_http(sb, _COMPANY_ID)
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["code"] == "SAAS_ENTITLEMENT_REQUIRED"


def test_G06_ambiguous_cv_raises_403():
    sb = _supabase(
        contracts=[_contract()],
        cvs=[
            _cv("MANAGER", version_no=1, superseded_at=None),
            _cv("FIELD", version_no=2, superseded_at=None),
        ],
    )
    with pytest.raises(HTTPException) as exc_info:
        _assert_leg_compliance_core_http(sb, _COMPANY_ID)
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["code"] == "CURRENT_CV_AMBIGUOUS"


# ── G07–G10: _assert_leg_site_scope_http ─────────────────────────────────────

def test_G07_factory_in_scope_passes():
    sb = _supabase(site_scopes=[_scope(entity_type="factory", entity_id=_FACTORY_ID)])
    _assert_leg_site_scope_http(sb, _CV_ID, "factory", _FACTORY_ID)


def test_G08_factory_not_in_scope_raises_403():
    sb = _supabase(site_scopes=[])
    with pytest.raises(HTTPException) as exc_info:
        _assert_leg_site_scope_http(sb, _CV_ID, "factory", _FACTORY_ID)
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["code"] == "SAAS_SITE_SCOPE_REQUIRED"


def test_G09_construction_site_in_scope_passes():
    sb = _supabase(site_scopes=[_scope(entity_type="site", entity_id=_SITE_ID)])
    _assert_leg_site_scope_http(sb, _CV_ID, "site", _SITE_ID)


def test_G10_construction_site_not_in_scope_raises_403():
    sb = _supabase(site_scopes=[])
    with pytest.raises(HTTPException) as exc_info:
        _assert_leg_site_scope_http(sb, _CV_ID, "site", _SITE_ID)
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["code"] == "SAAS_SITE_SCOPE_REQUIRED"


# ── G11–G12: commercial_version_id propagation + schema invalid ──────────────

def test_G11_resolution_commercial_version_id_propagated():
    custom_cv_id = str(uuid4())
    sb = _supabase(
        contracts=[_contract()],
        cvs=[_cv("FIELD", cv_id=custom_cv_id)],
    )
    resolution = _assert_leg_compliance_core_http(sb, _COMPANY_ID)
    assert resolution.commercial_version_id == custom_cv_id


def test_G12_invalid_product_tier_raises_403():
    sb = _supabase(
        contracts=[_contract()],
        cvs=[_cv("LEGACY_PLAN")],
    )
    with pytest.raises(HTTPException) as exc_info:
        _assert_leg_compliance_core_http(sb, _COMPANY_ID)
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["code"] == "CURRENT_CV_SCHEMA_INVALID"
