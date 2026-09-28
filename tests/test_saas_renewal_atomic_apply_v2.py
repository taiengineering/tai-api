"""TAI Safe Pricing V2 — Renewal Atomic Apply Adapter Tests (A01-A30).

검증 범위 (DB 없음 — 순수 unit/static):
  A01-A12  adapter 동작 (RPC 호출 계약)
  A13-A18  금지 항목 (직접 write / legacy / runtime wiring)
  A19-A30  SQL static 검사 (security / lock / ACL / KST / partial state)

DB/네트워크 없음 — 순수 unit tests.
"""
from __future__ import annotations

import inspect
import pathlib
import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, call

import pytest

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.saas_renewal_atomic_apply_v2 import (  # noqa: E402
    SaasV2RenewalAtomicApplyError,
    apply_saas_v2_renewal_plan_atomic,
    _RPC_NAME,
    _serialize_cv,
    _serialize_scopes,
)
from services.saas_renewal_v2_adapter import (  # noqa: E402
    SaasV2RenewalApplyPlan,
    build_saas_v2_renewal_apply_plan,
)

# ── SQL artifact path ──────────────────────────────────────────────────────────

_MIGRATION_PATH = (
    pathlib.Path(__file__).parent.parent
    / "migrations"
    / "2026-09-28_saas_contract_commercial_v2_renewal_atomic_apply.sql"
)
_SQL = _MIGRATION_PATH.read_text()

# ── Fixtures ──────────────────────────────────────────────────────────────────

_PAYMENT_ID  = str(uuid.uuid4())
_CONTRACT_ID = str(uuid.uuid4())
_QUOTE_ID    = str(uuid.uuid4())
_COMPANY_ID  = str(uuid.uuid4())
_USER_ID     = str(uuid.uuid4())
_SITE_ID     = str(uuid.uuid4())
_CV_ID       = str(uuid.uuid4())

_EFFECTIVE_AT = datetime(2027, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


def _snap_dict(supply=200_000, vat=20_000, total=220_000, term=12):
    return {
        "schema_version": "SAAS_PRICING_V2",
        "policy_version": "2026.09",
        "product_tier": "FIELD",
        "pricing_mode": "STANDARD",
        "sites": [{
            "entity_type": "factory",
            "entity_id": _SITE_ID,
            "sector": "INDUSTRY",
            "base_band_code": "B1",
            "base_amount": supply,
            "is_primary": True,
            "applied_rate_bps": 0,
            "final_site_amount": supply,
        }],
        "worker": {"capacity": 5, "amount": 0, "brackets": []},
        "term_months": term,
        "term_discount_rate_bps": 0,
        "monthly_supply_amount": supply,
        "prepaid_supply_amount": supply,
        "vat_rate_bps": 1_000,
        "vat_amount": vat,
        "total_amount": total,
    }


def _cv_row(version_no=1):
    return {
        "id": _CV_ID,
        "contract_id": _CONTRACT_ID,
        "version_no": version_no,
        "commercial_schema_version": "SAAS_CONTRACT_COMMERCIAL_V2",
        "product_tier": "FIELD",
        "pricing_mode": "STANDARD",
        "worker_capacity": 5,
        "term_months": 12,
        "pricing_result_status": "READY",
        "pricing_policy_version": "2026.09",
        "pricing_snapshot": _snap_dict(),
        "effective_from": "2026-01-01T00:00:00+00:00",
        "superseded_at": None,
        "created_by": None,
    }


def _pay_row():
    return {
        "id": _PAYMENT_ID,
        "status_code": "PAID",
        "payment_type": "RENEWAL",
        "product_type": "SAAS",
        "plan_code": None,
        "contract_id": _CONTRACT_ID,
        "quote_id": _QUOTE_ID,
        "period_months": 12,
        "supply_amount": 200_000,
        "vat_amount": 20_000,
        "total_amount": 220_000,
        "company_id": _COMPANY_ID,
        "user_id": _USER_ID,
        "paid_at": "2026-12-31T15:00:00+00:00",
    }


def _quote_item():
    return {
        "quote_schema_version": "SAAS_QUOTE_V2",
        "display_name": "TAI Safe 현장참여형 갱신",
        "billing_unit": "MONTHLY",
        "unit_amount": 200_000,
        "quantity": 12,
        "supply_amount": 200_000,
        "vat_amount": 20_000,
        "total_amount": 220_000,
        "service_type": "SAAS",
        "price_id": None,
        "tier_code": None,
        "sector": "INDUSTRY",
        "sectors": ["INDUSTRY"],
        "product_tier": "FIELD",
        "pricing_mode": "STANDARD",
        "policy_version": "2026.09",
        "worker_capacity": 5,
        "term_months": 12,
        "vat_rate": 0.1,
        "vat_rate_bps": 1_000,
        "pricing_input": {
            "product_tier": "FIELD",
            "worker_capacity": 5,
            "term_months": 12,
            "sites": [{"entity_id": _SITE_ID, "sector": "INDUSTRY", "criteria_value": 50}],
        },
        "pricing_snapshot": _snap_dict(),
    }


def _valid_plan_args():
    return {
        "pay": _pay_row(),
        "quote": {
            "id": _QUOTE_ID, "company_id": _COMPANY_ID, "status_code": "ISSUED",
            "service_type": "SAAS", "source": "member_auto",
            "supply_amount": 200_000, "vat_amount": 20_000, "total_amount": 220_000,
            "items": [_quote_item()],
        },
        "current_cv": _cv_row(version_no=1),
        "requested_effective_at": _EFFECTIVE_AT,
    }


def _make_plan() -> SaasV2RenewalApplyPlan:
    return build_saas_v2_renewal_apply_plan(**_valid_plan_args())


def _fake_supabase(status: str = "APPLIED") -> MagicMock:
    result = {"status": status, "payment_id": _PAYMENT_ID, "contract_id": _CONTRACT_ID}
    mock_response = MagicMock()
    mock_response.data = result
    mock_rpc = MagicMock(return_value=MagicMock(execute=MagicMock(return_value=mock_response)))
    sb = MagicMock()
    sb.rpc = mock_rpc
    return sb


# ═══════════════════════════════════════════════════════════════════════════════
# A01-A12: Adapter 동작
# ═══════════════════════════════════════════════════════════════════════════════

def test_A01_exactly_one_rpc_call():
    """정상 경로에서 RPC를 정확히 1회 호출한다."""
    plan = _make_plan()
    sb = _fake_supabase("APPLIED")
    apply_saas_v2_renewal_plan_atomic(sb, plan)
    assert sb.rpc.call_count == 1


def test_A02_correct_function_name():
    """RPC 함수명 = apply_saas_v2_renewal_atomic."""
    plan = _make_plan()
    sb = _fake_supabase("APPLIED")
    apply_saas_v2_renewal_plan_atomic(sb, plan)
    called_name = sb.rpc.call_args[0][0]
    assert called_name == "apply_saas_v2_renewal_atomic"


def test_A03_payment_id_exact():
    """p_payment_id = plan.payment_id."""
    plan = _make_plan()
    sb = _fake_supabase("APPLIED")
    apply_saas_v2_renewal_plan_atomic(sb, plan)
    params = sb.rpc.call_args[0][1]
    assert params["p_payment_id"] == str(plan.payment_id)


def test_A04_contract_id_exact():
    """p_contract_id = plan.contract_id."""
    plan = _make_plan()
    sb = _fake_supabase("APPLIED")
    apply_saas_v2_renewal_plan_atomic(sb, plan)
    params = sb.rpc.call_args[0][1]
    assert params["p_contract_id"] == str(plan.contract_id)


def test_A05_quote_id_exact():
    """p_quote_id = plan.quote_id."""
    plan = _make_plan()
    sb = _fake_supabase("APPLIED")
    apply_saas_v2_renewal_plan_atomic(sb, plan)
    params = sb.rpc.call_args[0][1]
    assert params["p_quote_id"] == str(plan.quote_id)


def test_A06_current_version_no_exact():
    """p_current_version_no = plan.current_version_no."""
    plan = _make_plan()
    sb = _fake_supabase("APPLIED")
    apply_saas_v2_renewal_plan_atomic(sb, plan)
    params = sb.rpc.call_args[0][1]
    assert params["p_current_version_no"] == plan.current_version_no


def test_A07_new_cv_serialization_contains_key_fields():
    """p_new_commercial_version에 필수 필드 포함."""
    plan = _make_plan()
    cv_data = _serialize_cv(plan)
    assert cv_data["commercial_schema_version"] == "SAAS_CONTRACT_COMMERCIAL_V2"
    assert str(cv_data["contract_id"]) == str(plan.contract_id)
    assert cv_data["version_no"] == plan.next_version_no
    assert cv_data["superseded_at"] is None


def test_A08_scopes_serialization_is_list():
    """p_site_scopes는 list."""
    plan = _make_plan()
    scopes = _serialize_scopes(plan)
    assert isinstance(scopes, list)
    for scope in scopes:
        assert "entity_type" in scope
        assert "entity_id" in scope
        assert "sector" in scope


def test_A09_applied_returns_result():
    """APPLIED → dict 반환."""
    plan = _make_plan()
    sb = _fake_supabase("APPLIED")
    result = apply_saas_v2_renewal_plan_atomic(sb, plan)
    assert result["status"] == "APPLIED"


def test_A10_already_applied_returns_result():
    """ALREADY_APPLIED → dict 반환 (raises 없음)."""
    plan = _make_plan()
    sb = _fake_supabase("ALREADY_APPLIED")
    result = apply_saas_v2_renewal_plan_atomic(sb, plan)
    assert result["status"] == "ALREADY_APPLIED"


def test_A11_unexpected_status_raises():
    """APPLIED/ALREADY_APPLIED 외 status → SaasV2RenewalAtomicApplyError."""
    plan = _make_plan()
    sb = _fake_supabase("V2_RENEWAL_BOUNDARY_MISMATCH")
    with pytest.raises(SaasV2RenewalAtomicApplyError) as exc:
        apply_saas_v2_renewal_plan_atomic(sb, plan)
    assert exc.value.code == "V2_RENEWAL_BOUNDARY_MISMATCH"


def test_A12_rpc_exception_wrapped():
    """RPC 호출 자체가 예외 발생 → V2_RENEWAL_RPC_ERROR."""
    plan = _make_plan()
    sb = MagicMock()
    sb.rpc.side_effect = RuntimeError("network error")
    with pytest.raises(SaasV2RenewalAtomicApplyError) as exc:
        apply_saas_v2_renewal_plan_atomic(sb, plan)
    assert exc.value.code == "V2_RENEWAL_RPC_ERROR"


# ═══════════════════════════════════════════════════════════════════════════════
# A13-A18: 금지 항목 static 검사
# ═══════════════════════════════════════════════════════════════════════════════

def _adapter_source() -> str:
    import services.saas_renewal_atomic_apply_v2 as mod
    return inspect.getsource(mod)


def test_A13_no_direct_contracts_write():
    """adapter에서 contracts 테이블 직접 INSERT/UPDATE 없음."""
    src = _adapter_source()
    assert 'table("contracts")' not in src
    assert ".insert(" not in src or "contracts" not in src


def test_A14_no_direct_payment_write():
    """adapter에서 payments 테이블 직접 INSERT/UPDATE 없음."""
    src = _adapter_source()
    assert 'table("payments")' not in src


def test_A15_no_direct_commercial_write():
    """adapter에서 saas_contract_commercial_versions 직접 write 없음."""
    src = _adapter_source()
    assert "saas_contract_commercial_versions" not in src


def test_A16_no_pricing_engine():
    """adapter에서 pricing engine import 없음."""
    src = _adapter_source()
    assert "saas_pricing_composer" not in src
    assert "calculate_saas_price" not in src


def test_A17_no_legacy_renewal_helper():
    """adapter에서 legacy _extend_contract_for_renewal 참조 없음."""
    src = _adapter_source()
    assert "_extend_contract_for_renewal" not in src


def test_A18_no_runtime_wiring():
    """adapter에서 payment_post_process import 없음."""
    src = _adapter_source()
    assert "payment_post_process" not in src


# ═══════════════════════════════════════════════════════════════════════════════
# A19-A30: SQL static 검사
# ═══════════════════════════════════════════════════════════════════════════════

def test_A19_sql_security_invoker():
    """SQL function: SECURITY INVOKER (DEFINER 금지)."""
    assert "SECURITY INVOKER" in _SQL
    assert "SECURITY DEFINER" not in _SQL


def test_A20_sql_search_path_empty():
    """SQL function: SET search_path = '' (schema injection 방지)."""
    assert "search_path = ''" in _SQL


def test_A21_sql_payment_for_update():
    """SQL: payments FOR UPDATE (lock 순서 1번)."""
    # Search within the function body (FROM public.payments ... FOR UPDATE pattern)
    assert "FROM   public.payments" in _SQL
    pay_idx = _SQL.index("FROM   public.payments")
    assert "FOR UPDATE" in _SQL[pay_idx:pay_idx + 300]


def test_A22_sql_contract_for_update():
    """SQL: contracts FOR UPDATE (lock 순서 2번)."""
    assert "public.contracts" in _SQL
    con_idx = _SQL.index("FROM   public.contracts")
    assert "FOR UPDATE" in _SQL[con_idx:con_idx + 200]


def test_A23_sql_old_cv_for_update():
    """SQL: saas_contract_commercial_versions FOR UPDATE (lock 순서 3번)."""
    assert "saas_contract_commercial_versions" in _SQL
    cv_lock_idx = _SQL.index("FROM   public.saas_contract_commercial_versions\n    WHERE  contract_id = p_contract_id\n      AND  version_no  = p_current_version_no")
    assert "FOR UPDATE" in _SQL[cv_lock_idx:cv_lock_idx + 200]


def test_A24_sql_service_role_execute_only():
    """SQL: service_role에만 EXECUTE GRANT."""
    assert "GRANT EXECUTE" in _SQL
    assert "TO service_role" in _SQL


def test_A25_sql_public_anon_authenticated_revoke():
    """SQL: PUBLIC/anon/authenticated REVOKE EXECUTE."""
    assert "FROM PUBLIC" in _SQL
    assert "FROM anon" in _SQL
    assert "FROM authenticated" in _SQL


def test_A26_sql_update_superseded_at_grant():
    """SQL: service_role에 UPDATE (superseded_at) 컬럼 단위 GRANT."""
    assert "GRANT UPDATE (superseded_at)" in _SQL
    assert "saas_contract_commercial_versions" in _SQL


def test_A27_sql_production_artifact_header():
    """SQL: ARTIFACT ONLY + PRODUCTION APPLY = 0 헤더."""
    assert "ARTIFACT ONLY" in _SQL
    assert "PRODUCTION APPLY = 0" in _SQL
    assert "OWNER APPROVAL REQUIRED" in _SQL


def test_A28_sql_kst_timezone_literal():
    """SQL: KST boundary 계산에 'Asia/Seoul' 사용."""
    assert "Asia/Seoul" in _SQL


def test_A29_sql_partial_state_code():
    """SQL: V2_RENEWAL_PARTIAL_STATE 부분 상태 코드 존재."""
    assert "V2_RENEWAL_PARTIAL_STATE" in _SQL


def test_A30_sql_already_applied_branch():
    """SQL: ALREADY_APPLIED 멱등성 분기 존재."""
    assert "ALREADY_APPLIED" in _SQL


# ═══════════════════════════════════════════════════════════════════════════════
# A31-A36: PATCH1 static 검사
# ═══════════════════════════════════════════════════════════════════════════════

def test_A31_sql_cross_payment_collision_code():
    """SQL: V2_RENEWAL_CROSS_PAYMENT_COLLISION 교차결제 차단 코드 존재."""
    assert "V2_RENEWAL_CROSS_PAYMENT_COLLISION" in _SQL


def test_A32_sql_renewal_payment_id_column():
    """SQL: renewal_payment_id 컬럼 ADD COLUMN 존재."""
    assert "renewal_payment_id" in _SQL


def test_A33_sql_term_mismatch_code():
    """SQL: V2_RENEWAL_TERM_MISMATCH (top-level term authority) 코드 존재."""
    assert "V2_RENEWAL_TERM_MISMATCH" in _SQL


def test_A34_sql_created_by_mismatch_code():
    """SQL: V2_RENEWAL_CV_CREATED_BY_MISMATCH (provenance binding) 코드 존재."""
    assert "V2_RENEWAL_CV_CREATED_BY_MISMATCH" in _SQL


def test_A35_sql_scope_required_code():
    """SQL: V2_RENEWAL_SCOPE_REQUIRED (MANAGER/FIELD scope completeness) 코드 존재."""
    assert "V2_RENEWAL_SCOPE_REQUIRED" in _SQL


def test_A36_sql_scope_duplicate_code():
    """SQL: V2_RENEWAL_SCOPE_DUPLICATE (중복 entity_id 차단) 코드 존재."""
    assert "V2_RENEWAL_SCOPE_DUPLICATE" in _SQL


# ═══════════════════════════════════════════════════════════════════════════════
# A37-A42: PATCH2 static 검사
# ═══════════════════════════════════════════════════════════════════════════════

def test_A37_sql_renewal_payment_id_unique_index():
    """SQL: renewal_payment_id UNIQUE INDEX 존재 (1 payment = 1 renewal DB invariant)."""
    assert "CREATE UNIQUE INDEX" in _SQL
    assert "renewal_payment_id" in _SQL


def test_A38_sql_renewal_payment_id_fk():
    """SQL: renewal_payment_id FK REFERENCES public.payments 존재."""
    assert "REFERENCES public.payments" in _SQL


def test_A39_sql_payment_already_consumed_guard():
    """SQL: V2_RENEWAL_PAYMENT_ALREADY_CONSUMED (global consumed-payment guard) 존재."""
    assert "V2_RENEWAL_PAYMENT_ALREADY_CONSUMED" in _SQL


def test_A40_sql_scope_snapshot_mismatch_code():
    """SQL: V2_RENEWAL_SCOPE_SNAPSHOT_MISMATCH (scope ↔ snapshot SSOT) 존재."""
    assert "V2_RENEWAL_SCOPE_SNAPSHOT_MISMATCH" in _SQL


def test_A41_sql_scope_duplicate_composite_key():
    """SQL: scope duplicate 검사에 (entity_type, entity_id) composite key 사용."""
    dup_idx = _SQL.index("V2_RENEWAL_SCOPE_DUPLICATE")
    context = _SQL[max(0, dup_idx - 400):dup_idx]
    assert "entity_type" in context
    assert "entity_id" in context


def test_A42_sql_old_cv_schema_guard():
    """SQL: V2_RENEWAL_CURRENT_CV_SCHEMA_INVALID (old CV schema guard) 존재."""
    assert "V2_RENEWAL_CURRENT_CV_SCHEMA_INVALID" in _SQL
