"""B01-B16 — WO-COMM-V3-RUNTIME-WIRING-001 Runtime Gate.

FakeSupabase + real evaluate_saas_entitlement_v2. DB 없음.
resolve_saas_entitlement_context_v2 는 mock.

케이스 매트릭스:
  HAPPY      B01 MANAGER + scoped factory → ALLOWED, can_execute=True
             B02 FIELD + scoped factory → ALLOWED
             B03 MANAGER + scoped site → ALLOWED
             B04 FIELD + scoped site → ALLOWED
  SCOPE      B05 in-scope entitlement but scope check returns [] → SITE_OUT_OF_SCOPE
  ENTITLE    B06 CUSTOM product_tier → CUSTOM_CONTEXT_REQUIRED, can_execute=False
  RUNTIME    B07 SaasEntitlementRuntimeError(NO_ACTIVE_SAAS_CONTRACT) → NOT_COMMERCIAL_V3
             B08 SaasEntitlementRuntimeError(CURRENT_CV_NOT_FOUND) → NOT_COMMERCIAL_V3
  AUTH       B09 company_id None → NOT_COMMERCIAL_V3 (no error)
  PARAM      B10 factory_id + site_id 둘 다 → ValueError
             B11 둘 다 None → ValueError
  EXACT      B12 scope_res uses resolution.commercial_version_id (correct CV)
             B13 superseded CV (SaasEntitlementRuntimeError) → NOT_COMMERCIAL_V3
             B14 current CV scope used (cv_id 확인)
  CLEAN      B15 result에 plan_code 없음
             B16 result에 price_master 접근 없음 (mock에 price_master 없음 확인)
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Any, List, Optional
from unittest.mock import patch, MagicMock

import pytest

os.environ.setdefault("INTERNAL_API_SECRET", "pytest-internal-secret")

from services import member_commercial_svc as svc
from services.saas_entitlement_runtime_v2 import SaasEntitlementRuntimeError
from schemas.saas_entitlement_v2 import SaasEntitlementContextV2


# ── Helpers ───────────────────────────────────────────────────────────────────

def _uid() -> str:
    return str(uuid.uuid4())


def _now_iso(offset_days: int = 0) -> str:
    return (datetime.now(tz=timezone.utc) + timedelta(days=offset_days)).isoformat()


@dataclass
class _FakeResolution:
    contract_id: str
    commercial_version_id: str
    commercial_version_no: int
    product_tier: str
    context: SaasEntitlementContextV2


def _make_resolution(
    contract_id: str,
    cv_id: str,
    product_tier: str = "MANAGER",
    cv_no: int = 1,
) -> _FakeResolution:
    context = SaasEntitlementContextV2(product_tier=product_tier, custom_entitlements=None)
    return _FakeResolution(
        contract_id=contract_id,
        commercial_version_id=cv_id,
        commercial_version_no=cv_no,
        product_tier=product_tier,
        context=context,
    )


# ── FakeSupabase (minimal — spec=["table"]) ───────────────────────────────────

class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, store: dict, table: str, query_log: list):
        self._store = store
        self._table = table
        self._ql = query_log
        self._filters: list = []

    def select(self, cols="*", *a, **kw):
        return self

    def eq(self, c, v):
        self._filters.append((c, v))
        return self

    def limit(self, n):
        return self

    def execute(self) -> _Result:
        self._ql.append(self._table)
        rows = list(self._store.get(self._table) or [])
        for c, v in self._filters:
            rows = [r for r in rows if str(r.get(c, "")) == str(v)]
        return _Result(rows)


class FakeSB:
    """Minimal Supabase mock — spec=["table"]."""

    def __init__(self, store: dict):
        self._store = store
        self.query_log: list = []

    def table(self, name: str) -> _Query:
        return _Query(self._store, name, self.query_log)


def _make_scope_row(cv_id: str, entity_type: str, entity_id: str) -> dict:
    return {
        "id": _uid(),
        "commercial_version_id": cv_id,
        "entity_type": entity_type,
        "entity_id": entity_id,
    }


# ── B01-B04: Happy path (ALLOWED) ─────────────────────────────────────────────

def test_b01_manager_scoped_factory_allowed():
    """B01 MANAGER + scoped factory → ALLOWED, can_execute=True."""
    company_id = _uid()
    contract_id = _uid()
    cv_id = _uid()
    factory_id = _uid()

    resolution = _make_resolution(contract_id, cv_id, "MANAGER")
    store = {
        "saas_contract_site_scopes": [_make_scope_row(cv_id, "factory", factory_id)],
    }
    sb = FakeSB(store)

    with patch(
        "services.member_commercial_svc.resolve_saas_entitlement_context_v2",
        return_value=resolution,
    ):
        result = svc.get_member_runtime_gate(sb, company_id, factory_id=factory_id)

    assert result["generation"] == "COMMERCIAL_V3"
    assert result["can_execute"] is True
    assert result["status"] == "ALLOWED"
    assert result["reason_code"] is None
    assert result["product_tier"] == "MANAGER"
    assert result["target"]["entity_type"] == "factory"
    assert result["target"]["entity_id"] == factory_id


def test_b02_field_scoped_factory_allowed():
    """B02 FIELD + scoped factory → ALLOWED."""
    company_id = _uid()
    contract_id = _uid()
    cv_id = _uid()
    factory_id = _uid()

    resolution = _make_resolution(contract_id, cv_id, "FIELD")
    store = {
        "saas_contract_site_scopes": [_make_scope_row(cv_id, "factory", factory_id)],
    }
    sb = FakeSB(store)

    with patch(
        "services.member_commercial_svc.resolve_saas_entitlement_context_v2",
        return_value=resolution,
    ):
        result = svc.get_member_runtime_gate(sb, company_id, factory_id=factory_id)

    assert result["generation"] == "COMMERCIAL_V3"
    assert result["can_execute"] is True
    assert result["status"] == "ALLOWED"
    assert result["product_tier"] == "FIELD"


def test_b03_manager_scoped_site_allowed():
    """B03 MANAGER + scoped site → ALLOWED."""
    company_id = _uid()
    contract_id = _uid()
    cv_id = _uid()
    site_id = _uid()

    resolution = _make_resolution(contract_id, cv_id, "MANAGER")
    store = {
        "saas_contract_site_scopes": [_make_scope_row(cv_id, "site", site_id)],
    }
    sb = FakeSB(store)

    with patch(
        "services.member_commercial_svc.resolve_saas_entitlement_context_v2",
        return_value=resolution,
    ):
        result = svc.get_member_runtime_gate(sb, company_id, site_id=site_id)

    assert result["generation"] == "COMMERCIAL_V3"
    assert result["can_execute"] is True
    assert result["status"] == "ALLOWED"
    assert result["target"]["entity_type"] == "site"
    assert result["target"]["entity_id"] == site_id


def test_b04_field_scoped_site_allowed():
    """B04 FIELD + scoped site → ALLOWED."""
    company_id = _uid()
    contract_id = _uid()
    cv_id = _uid()
    site_id = _uid()

    resolution = _make_resolution(contract_id, cv_id, "FIELD")
    store = {
        "saas_contract_site_scopes": [_make_scope_row(cv_id, "site", site_id)],
    }
    sb = FakeSB(store)

    with patch(
        "services.member_commercial_svc.resolve_saas_entitlement_context_v2",
        return_value=resolution,
    ):
        result = svc.get_member_runtime_gate(sb, company_id, site_id=site_id)

    assert result["generation"] == "COMMERCIAL_V3"
    assert result["can_execute"] is True
    assert result["product_tier"] == "FIELD"


# ── B05: Site out of scope ─────────────────────────────────────────────────────

def test_b05_site_out_of_scope():
    """B05 in-scope entitlement but scope check returns [] → SITE_OUT_OF_SCOPE."""
    company_id = _uid()
    contract_id = _uid()
    cv_id = _uid()
    factory_id = _uid()

    resolution = _make_resolution(contract_id, cv_id, "MANAGER")
    # saas_contract_site_scopes에 해당 factory 없음
    store = {
        "saas_contract_site_scopes": [],
    }
    sb = FakeSB(store)

    with patch(
        "services.member_commercial_svc.resolve_saas_entitlement_context_v2",
        return_value=resolution,
    ):
        result = svc.get_member_runtime_gate(sb, company_id, factory_id=factory_id)

    assert result["generation"] == "COMMERCIAL_V3"
    assert result["can_execute"] is False
    assert result["status"] == "SITE_OUT_OF_SCOPE"
    assert result["reason_code"] == "SITE_OUT_OF_SCOPE"


# ── B06: CUSTOM product_tier → CUSTOM_CONTEXT_REQUIRED ────────────────────────

def test_b06_custom_tier_custom_context_required():
    """B06 CUSTOM product_tier → CUSTOM_CONTEXT_REQUIRED, can_execute=False."""
    company_id = _uid()
    contract_id = _uid()
    cv_id = _uid()
    factory_id = _uid()

    resolution = _make_resolution(contract_id, cv_id, "CUSTOM")
    store = {
        "saas_contract_site_scopes": [_make_scope_row(cv_id, "factory", factory_id)],
    }
    sb = FakeSB(store)

    with patch(
        "services.member_commercial_svc.resolve_saas_entitlement_context_v2",
        return_value=resolution,
    ):
        result = svc.get_member_runtime_gate(sb, company_id, factory_id=factory_id)

    assert result["generation"] == "COMMERCIAL_V3"
    assert result["can_execute"] is False
    assert result["status"] == "CUSTOM_CONTEXT_REQUIRED"
    assert result["reason_code"] == "CUSTOM_CONTEXT_REQUIRED"
    assert result["product_tier"] == "CUSTOM"


# ── B07-B08: SaasEntitlementRuntimeError → NOT_COMMERCIAL_V3 ──────────────────

def test_b07_runtime_error_no_active_contract():
    """B07 SaasEntitlementRuntimeError(NO_ACTIVE_SAAS_CONTRACT) → NOT_COMMERCIAL_V3."""
    company_id = _uid()
    factory_id = _uid()
    sb = FakeSB({})

    with patch(
        "services.member_commercial_svc.resolve_saas_entitlement_context_v2",
        side_effect=SaasEntitlementRuntimeError("NO_ACTIVE_SAAS_CONTRACT"),
    ):
        result = svc.get_member_runtime_gate(sb, company_id, factory_id=factory_id)

    assert result["generation"] == "NOT_COMMERCIAL_V3"
    assert result["can_execute"] is None
    assert result["status"] is None
    assert result["product_tier"] is None
    assert result["commercial_version_no"] is None
    assert result["target"]["entity_type"] == "factory"
    assert result["target"]["entity_id"] == factory_id


def test_b08_runtime_error_current_cv_not_found():
    """B08 SaasEntitlementRuntimeError(CURRENT_CV_NOT_FOUND) → NOT_COMMERCIAL_V3."""
    company_id = _uid()
    factory_id = _uid()
    sb = FakeSB({})

    with patch(
        "services.member_commercial_svc.resolve_saas_entitlement_context_v2",
        side_effect=SaasEntitlementRuntimeError("CURRENT_CV_NOT_FOUND"),
    ):
        result = svc.get_member_runtime_gate(sb, company_id, factory_id=factory_id)

    assert result["generation"] == "NOT_COMMERCIAL_V3"
    assert result["can_execute"] is None


# ── B09: company_id None → NOT_COMMERCIAL_V3 ──────────────────────────────────

def test_b09_no_company_id():
    """B09 company_id None → NOT_COMMERCIAL_V3 (no error raised)."""
    factory_id = _uid()
    sb = FakeSB({})

    result = svc.get_member_runtime_gate(sb, None, factory_id=factory_id)

    assert result["generation"] == "NOT_COMMERCIAL_V3"
    assert result["can_execute"] is None
    assert result["status"] is None
    assert result["target"]["entity_type"] == "factory"
    assert result["target"]["entity_id"] == factory_id


# ── B10-B11: Parameter validation ─────────────────────────────────────────────

def test_b10_both_factory_and_site_raises():
    """B10 factory_id + site_id 둘 다 → ValueError."""
    factory_id = _uid()
    site_id = _uid()
    sb = FakeSB({})

    with pytest.raises(ValueError):
        svc.get_member_runtime_gate(sb, _uid(), factory_id=factory_id, site_id=site_id)


def test_b11_neither_factory_nor_site_raises():
    """B11 둘 다 None → ValueError."""
    sb = FakeSB({})

    with pytest.raises(ValueError):
        svc.get_member_runtime_gate(sb, _uid())


# ── B12: scope_res uses resolution.commercial_version_id ──────────────────────

def test_b12_scope_uses_correct_cv_id():
    """B12 scope_res uses resolution.commercial_version_id (correct CV)."""
    company_id = _uid()
    contract_id = _uid()
    cv_id = _uid()
    other_cv_id = _uid()
    factory_id = _uid()

    resolution = _make_resolution(contract_id, cv_id, "MANAGER")
    # other_cv_id에 scope 있지만 current CV(cv_id)에는 없음
    store = {
        "saas_contract_site_scopes": [
            _make_scope_row(other_cv_id, "factory", factory_id),
        ],
    }
    sb = FakeSB(store)

    with patch(
        "services.member_commercial_svc.resolve_saas_entitlement_context_v2",
        return_value=resolution,
    ):
        result = svc.get_member_runtime_gate(sb, company_id, factory_id=factory_id)

    # current cv_id에 scope가 없으므로 SITE_OUT_OF_SCOPE
    assert result["status"] == "SITE_OUT_OF_SCOPE"
    assert result["can_execute"] is False


# ── B13: superseded CV → NOT_COMMERCIAL_V3 ────────────────────────────────────

def test_b13_superseded_cv_error():
    """B13 superseded CV (SaasEntitlementRuntimeError) → NOT_COMMERCIAL_V3."""
    company_id = _uid()
    factory_id = _uid()
    sb = FakeSB({})

    with patch(
        "services.member_commercial_svc.resolve_saas_entitlement_context_v2",
        side_effect=SaasEntitlementRuntimeError("CURRENT_CV_AMBIGUOUS"),
    ):
        result = svc.get_member_runtime_gate(sb, company_id, factory_id=factory_id)

    assert result["generation"] == "NOT_COMMERCIAL_V3"
    assert result["can_execute"] is None


# ── B14: current CV scope used (cv_id 확인) ────────────────────────────────────

def test_b14_current_cv_scope_used():
    """B14 current CV scope used — B01과 동일하지만 cv_id 명시 확인."""
    company_id = _uid()
    contract_id = _uid()
    cv_id = _uid()
    factory_id = _uid()

    resolution = _make_resolution(contract_id, cv_id, "MANAGER", cv_no=3)
    store = {
        "saas_contract_site_scopes": [_make_scope_row(cv_id, "factory", factory_id)],
    }
    sb = FakeSB(store)

    with patch(
        "services.member_commercial_svc.resolve_saas_entitlement_context_v2",
        return_value=resolution,
    ):
        result = svc.get_member_runtime_gate(sb, company_id, factory_id=factory_id)

    assert result["can_execute"] is True
    assert result["commercial_version_no"] == 3
    # scope 조회는 cv_id 기준으로만 했을 것 — query_log에 saas_contract_site_scopes 1회
    scope_queries = [q for q in sb.query_log if q == "saas_contract_site_scopes"]
    assert len(scope_queries) == 1


# ── B15: result에 plan_code 없음 ──────────────────────────────────────────────

def test_b15_no_plan_code_in_result():
    """B15 result에 plan_code 없음."""
    company_id = _uid()
    contract_id = _uid()
    cv_id = _uid()
    factory_id = _uid()

    resolution = _make_resolution(contract_id, cv_id, "MANAGER")
    store = {
        "saas_contract_site_scopes": [_make_scope_row(cv_id, "factory", factory_id)],
    }
    sb = FakeSB(store)

    with patch(
        "services.member_commercial_svc.resolve_saas_entitlement_context_v2",
        return_value=resolution,
    ):
        result = svc.get_member_runtime_gate(sb, company_id, factory_id=factory_id)

    assert "plan_code" not in result


# ── B16: price_master 접근 없음 ───────────────────────────────────────────────

def test_b16_no_price_master_access():
    """B16 result에 price_master 접근 없음 (mock에 price_master 없음 확인)."""
    company_id = _uid()
    contract_id = _uid()
    cv_id = _uid()
    factory_id = _uid()

    resolution = _make_resolution(contract_id, cv_id, "MANAGER")
    # price_master 테이블 없음 — 접근 시 빈 list 반환 (FakeSB 특성)
    store = {
        "saas_contract_site_scopes": [_make_scope_row(cv_id, "factory", factory_id)],
        # price_master 키 의도적으로 없음
    }
    sb = FakeSB(store)

    with patch(
        "services.member_commercial_svc.resolve_saas_entitlement_context_v2",
        return_value=resolution,
    ):
        result = svc.get_member_runtime_gate(sb, company_id, factory_id=factory_id)

    # price_master 쿼리가 발생하지 않았어야 함
    assert "price_master" not in sb.query_log
    assert result["can_execute"] is True
