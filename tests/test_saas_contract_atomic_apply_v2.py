"""TAI Safe SaaS Atomic Contract Apply V2 — C01-C86.

검증 범위:
  A. RPC 파라미터 구성 (C01-C12)
  B. Commercial version 직렬화 (C13-C22)
  C. Site scope 직렬화 (C23-C32)
  D. 성공 반환값 (C33-C44)
  E. 오류 처리 (C45-C60)
  F. SaasV2AtomicApplyError 클래스 (C61-C70)
  G. 모듈 구조 가드 (C71-C80)
  H. 경계/회귀 (C81-C86)

DB/네트워크 없음 — FakeSupabase로 RPC 호출 관찰.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.saas_contract_atomic_apply_v2 import (  # noqa: E402
    SaasV2AtomicApplyError,
    _TERMINAL_STATUSES,
    apply_saas_v2_contract_plan_atomic,
)
from services.saas_payment_success_v2_adapter import SaasV2ApplyPlan  # noqa: E402


# ── UUIDs ──────────────────────────────────────────────────────────────────────

_CONTRACT_ID = uuid.UUID("11111111-0000-0000-0000-000000000001")
_COMPANY_ID  = "aaaa0000-0000-0000-0000-000000000001"
_PAYMENT_ID  = "cccc0000-0000-0000-0000-000000000003"
_ENTITY_ID   = uuid.UUID("dddd0000-0000-0000-0000-000000000004")
_USER_ID     = uuid.UUID("eeee0000-0000-0000-0000-000000000005")

_EFFECTIVE_FROM = datetime(2026, 9, 28, 10, 0, 0, tzinfo=timezone.utc)


# ── Fake Supabase ──────────────────────────────────────────────────────────────

class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeRpcChain:
    def __init__(self, data=None, exc=None):
        self._data = data
        self._exc = exc
        self.execute_count = 0

    def execute(self):
        self.execute_count += 1
        if self._exc is not None:
            raise self._exc
        return _FakeResult(self._data)


class FakeSupabase:
    """RPC 호출을 관찰하고 미리 정한 data를 반환한다. 직접 테이블 접근 시 즉시 실패."""

    def __init__(self, rpc_data=None, rpc_exc=None):
        self._rpc_data = rpc_data
        self._rpc_exc = rpc_exc
        self.rpc_calls: list[dict] = []
        self._last_chain: _FakeRpcChain | None = None

    def rpc(self, name: str, params: dict) -> _FakeRpcChain:
        self.rpc_calls.append({"name": name, "params": params})
        chain = _FakeRpcChain(self._rpc_data, self._rpc_exc)
        self._last_chain = chain
        return chain

    def table(self, *a, **k):
        raise AssertionError("apply는 RPC 전용 — 직접 테이블 접근 금지")

    def from_(self, *a, **k):
        raise AssertionError("apply는 RPC 전용 — 직접 from_ 접근 금지")


# ── Test Fixtures ──────────────────────────────────────────────────────────────

def _make_snap():
    from schemas.saas_pricing_v2 import (
        SaasPricingSnapshotV2,
        SaasSiteScope,
        SaasWorkerBracketLine,
        SaasWorkerPricingSnapshot,
    )
    return SaasPricingSnapshotV2(
        schema_version="SAAS_PRICING_V2",
        policy_version="2026.09",
        product_tier="FIELD",
        pricing_mode="STANDARD",
        sites=[
            SaasSiteScope(
                entity_type="factory",
                entity_id=_ENTITY_ID,
                sector="INDUSTRY",
                base_band_code="B1",
                base_amount=500000,
                is_primary=True,
                applied_rate_bps=0,
                final_site_amount=500000,
            )
        ],
        worker=SaasWorkerPricingSnapshot(
            capacity=5,
            amount=100000,
            brackets=[
                SaasWorkerBracketLine(
                    range_from=1, range_to=10, unit_rate=20000, units=5, amount=100000
                )
            ],
        ),
        term_months=12,
        term_discount_rate_bps=0,
        monthly_supply_amount=100000,
        prepaid_supply_amount=1200000,
        vat_rate_bps=1000,
        vat_amount=120000,
        total_amount=1320000,
    )


def _make_bundle():
    from schemas.saas_pricing_v2 import SaasCommercialSelection
    from services.saas_contract_storage_mapper_v2 import build_standard_contract_storage_bundle_v2
    from services.saas_pricing_composer_v2 import SaasPricingCalculationResult

    snap = _make_snap()
    selection = SaasCommercialSelection(
        product_tier="FIELD",
        pricing_mode="STANDARD",
        worker_capacity=5,
        term_months=12,
    )
    calc = SaasPricingCalculationResult(
        status="READY",
        policy_version="2026.09",
        site_breakdown=None,
        worker_breakdown=snap.worker,
        monthly_supply_amount=100000,
        raw_prepaid_supply_amount=1200000,
        term_months=12,
        term_discount_rate_bps=0,
        snapshot=snap,
        block_reason=None,
    )
    return build_standard_contract_storage_bundle_v2(
        contract_id=_CONTRACT_ID,
        version_no=1,
        selection=selection,
        calculation_result=calc,
        effective_from=_EFFECTIVE_FROM,
        created_by=_USER_ID,
    )


def _make_contract_row():
    return {
        "id":              str(_CONTRACT_ID),
        "contract_no":     "CON-20260928-0001",
        "company_id":      _COMPANY_ID,
        "status_code":     "ACTIVE",
        "start_date":      "2026-09-28",
        "end_date":        "2027-09-27",
        "service_type":    "SAAS",
        "contract_amount": 1200000.0,
        "vat_amount":      120000.0,
        "total_amount":    1320000.0,
        "paid_amount":     1320000.0,
        "paid_at":         "2026-09-28T10:00:00+09:00",
        "is_active":       True,
        "created_at":      "2026-09-28T10:00:00+00:00",
        "updated_at":      "2026-09-28T10:00:00+00:00",
        "memo":            "자동생성 — 결제 cccc0000",
    }


def _make_plan() -> SaasV2ApplyPlan:
    return SaasV2ApplyPlan(
        payment_id=_PAYMENT_ID,
        company_id=_COMPANY_ID,
        contract_id=_CONTRACT_ID,
        contract_row=_make_contract_row(),
        commercial_bundle=_make_bundle(),
    )


def _applied_data(payment_id=_PAYMENT_ID, contract_id=str(_CONTRACT_ID)):
    return {
        "status":                "APPLIED",
        "payment_id":            payment_id,
        "contract_id":           contract_id,
        "commercial_version_id": "ffffffff-ffff-ffff-ffff-ffffffffffff",
    }


def _already_applied_data(payment_id=_PAYMENT_ID, contract_id=str(_CONTRACT_ID)):
    return {
        "status":      "ALREADY_APPLIED",
        "payment_id":  payment_id,
        "contract_id": contract_id,
    }


# ═══════════════════════════════════════════════════════════════════════════
# A. RPC 파라미터 구성 (C01-C12)
# ═══════════════════════════════════════════════════════════════════════════

class TestC01_RpcCalledOnce:
    def test_C01(self):
        sb = FakeSupabase(rpc_data=_applied_data())
        apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        assert len(sb.rpc_calls) == 1


class TestC02_RpcFunctionName:
    def test_C02(self):
        sb = FakeSupabase(rpc_data=_applied_data())
        apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        assert sb.rpc_calls[0]["name"] == "apply_saas_v2_contract_atomic"


class TestC03_PPaymentIdIsStr:
    def test_C03(self):
        sb = FakeSupabase(rpc_data=_applied_data())
        apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        params = sb.rpc_calls[0]["params"]
        assert isinstance(params["p_payment_id"], str)


class TestC04_PPaymentIdValue:
    def test_C04(self):
        sb = FakeSupabase(rpc_data=_applied_data())
        plan = _make_plan()
        apply_saas_v2_contract_plan_atomic(sb, plan)
        params = sb.rpc_calls[0]["params"]
        assert params["p_payment_id"] == str(plan.payment_id)


class TestC05_PContractRowIsDict:
    def test_C05(self):
        sb = FakeSupabase(rpc_data=_applied_data())
        apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        params = sb.rpc_calls[0]["params"]
        assert isinstance(params["p_contract_row"], dict)


class TestC06_PContractRowValue:
    def test_C06(self):
        sb = FakeSupabase(rpc_data=_applied_data())
        plan = _make_plan()
        apply_saas_v2_contract_plan_atomic(sb, plan)
        params = sb.rpc_calls[0]["params"]
        assert params["p_contract_row"] == plan.contract_row


class TestC07_PCommercialVersionIsDict:
    def test_C07(self):
        sb = FakeSupabase(rpc_data=_applied_data())
        apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        params = sb.rpc_calls[0]["params"]
        assert isinstance(params["p_commercial_version"], dict)


class TestC08_PSiteScopesIsList:
    def test_C08(self):
        sb = FakeSupabase(rpc_data=_applied_data())
        apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        params = sb.rpc_calls[0]["params"]
        assert isinstance(params["p_site_scopes"], list)


class TestC09_CommercialVersionHasContractId:
    def test_C09(self):
        sb = FakeSupabase(rpc_data=_applied_data())
        apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        cv = sb.rpc_calls[0]["params"]["p_commercial_version"]
        assert "contract_id" in cv


class TestC10_CommercialVersionContractIdMatchesPlan:
    def test_C10(self):
        sb = FakeSupabase(rpc_data=_applied_data())
        plan = _make_plan()
        apply_saas_v2_contract_plan_atomic(sb, plan)
        cv = sb.rpc_calls[0]["params"]["p_commercial_version"]
        assert cv["contract_id"] == str(plan.contract_id)


class TestC11_CommercialVersionVersionNoIsOne:
    def test_C11(self):
        sb = FakeSupabase(rpc_data=_applied_data())
        apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        cv = sb.rpc_calls[0]["params"]["p_commercial_version"]
        assert cv["version_no"] == 1


class TestC12_ExecuteCalledOnce:
    def test_C12(self):
        sb = FakeSupabase(rpc_data=_applied_data())
        apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        chain = sb._last_chain
        assert chain is not None
        assert chain.execute_count == 1


# ═══════════════════════════════════════════════════════════════════════════
# B. Commercial version 직렬화 (C13-C22)
# ═══════════════════════════════════════════════════════════════════════════

class TestC13_CommercialSchemaVersion:
    def test_C13(self):
        sb = FakeSupabase(rpc_data=_applied_data())
        apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        cv = sb.rpc_calls[0]["params"]["p_commercial_version"]
        assert cv.get("commercial_schema_version") == "SAAS_CONTRACT_COMMERCIAL_V2"


class TestC14_ProductTierPresent:
    def test_C14(self):
        sb = FakeSupabase(rpc_data=_applied_data())
        apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        cv = sb.rpc_calls[0]["params"]["p_commercial_version"]
        assert cv.get("product_tier") == "FIELD"


class TestC15_PricingModePresent:
    def test_C15(self):
        sb = FakeSupabase(rpc_data=_applied_data())
        apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        cv = sb.rpc_calls[0]["params"]["p_commercial_version"]
        assert cv.get("pricing_mode") == "STANDARD"


class TestC16_WorkerCapacityPresent:
    def test_C16(self):
        sb = FakeSupabase(rpc_data=_applied_data())
        apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        cv = sb.rpc_calls[0]["params"]["p_commercial_version"]
        assert cv.get("worker_capacity") == 5


class TestC17_TermMonthsPresent:
    def test_C17(self):
        sb = FakeSupabase(rpc_data=_applied_data())
        apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        cv = sb.rpc_calls[0]["params"]["p_commercial_version"]
        assert cv.get("term_months") == 12


class TestC18_PricingResultStatusPresent:
    def test_C18(self):
        sb = FakeSupabase(rpc_data=_applied_data())
        apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        cv = sb.rpc_calls[0]["params"]["p_commercial_version"]
        assert cv.get("pricing_result_status") == "READY"


class TestC19_PricingPolicyVersionPresent:
    def test_C19(self):
        sb = FakeSupabase(rpc_data=_applied_data())
        apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        cv = sb.rpc_calls[0]["params"]["p_commercial_version"]
        assert cv.get("pricing_policy_version") == "2026.09"


class TestC20_PricingSnapshotIsDict:
    def test_C20(self):
        sb = FakeSupabase(rpc_data=_applied_data())
        apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        cv = sb.rpc_calls[0]["params"]["p_commercial_version"]
        assert isinstance(cv.get("pricing_snapshot"), dict)


class TestC21_EffectiveFromIsStr:
    def test_C21(self):
        sb = FakeSupabase(rpc_data=_applied_data())
        apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        cv = sb.rpc_calls[0]["params"]["p_commercial_version"]
        assert isinstance(cv.get("effective_from"), str)


class TestC22_CreatedByIsStr:
    def test_C22(self):
        sb = FakeSupabase(rpc_data=_applied_data())
        apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        cv = sb.rpc_calls[0]["params"]["p_commercial_version"]
        # mode="json" converts UUID → str
        assert isinstance(cv.get("created_by"), str)
        assert cv.get("created_by") == str(_USER_ID)


# ═══════════════════════════════════════════════════════════════════════════
# C. Site scope 직렬화 (C23-C32)
# ═══════════════════════════════════════════════════════════════════════════

class TestC23_SiteScopesLength:
    def test_C23(self):
        sb = FakeSupabase(rpc_data=_applied_data())
        plan = _make_plan()
        apply_saas_v2_contract_plan_atomic(sb, plan)
        scopes = sb.rpc_calls[0]["params"]["p_site_scopes"]
        assert len(scopes) == len(plan.commercial_bundle.site_scopes)
        assert len(scopes) == 1


class TestC24_EachScopeIsDict:
    def test_C24(self):
        sb = FakeSupabase(rpc_data=_applied_data())
        apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        scopes = sb.rpc_calls[0]["params"]["p_site_scopes"]
        for scope in scopes:
            assert isinstance(scope, dict)


class TestC25_ScopeHasEntityType:
    def test_C25(self):
        sb = FakeSupabase(rpc_data=_applied_data())
        apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        scope = sb.rpc_calls[0]["params"]["p_site_scopes"][0]
        assert "entity_type" in scope


class TestC26_ScopeEntityIdIsStr:
    def test_C26(self):
        sb = FakeSupabase(rpc_data=_applied_data())
        apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        scope = sb.rpc_calls[0]["params"]["p_site_scopes"][0]
        assert isinstance(scope.get("entity_id"), str)


class TestC27_ScopeHasSector:
    def test_C27(self):
        sb = FakeSupabase(rpc_data=_applied_data())
        apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        scope = sb.rpc_calls[0]["params"]["p_site_scopes"][0]
        assert "sector" in scope


class TestC28_ScopeHasBaseBandCode:
    def test_C28(self):
        sb = FakeSupabase(rpc_data=_applied_data())
        apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        scope = sb.rpc_calls[0]["params"]["p_site_scopes"][0]
        assert "base_band_code" in scope


class TestC29_ScopeEntityIdMatchesEntityId:
    def test_C29(self):
        sb = FakeSupabase(rpc_data=_applied_data())
        apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        scope = sb.rpc_calls[0]["params"]["p_site_scopes"][0]
        assert scope["entity_id"] == str(_ENTITY_ID)


class TestC30_ScopeEntityTypeIsFactory:
    def test_C30(self):
        sb = FakeSupabase(rpc_data=_applied_data())
        apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        scope = sb.rpc_calls[0]["params"]["p_site_scopes"][0]
        assert scope["entity_type"] == "factory"


class TestC31_ScopeSectorIsIndustry:
    def test_C31(self):
        sb = FakeSupabase(rpc_data=_applied_data())
        apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        scope = sb.rpc_calls[0]["params"]["p_site_scopes"][0]
        assert scope["sector"] == "INDUSTRY"


class TestC32_ScopeBaseBandCodeIsB1:
    def test_C32(self):
        sb = FakeSupabase(rpc_data=_applied_data())
        apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        scope = sb.rpc_calls[0]["params"]["p_site_scopes"][0]
        assert scope["base_band_code"] == "B1"


# ═══════════════════════════════════════════════════════════════════════════
# D. 성공 반환값 (C33-C44)
# ═══════════════════════════════════════════════════════════════════════════

class TestC33_AppliedReturnsDict:
    def test_C33(self):
        sb = FakeSupabase(rpc_data=_applied_data())
        result = apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        assert isinstance(result, dict)


class TestC34_AppliedStatusInResult:
    def test_C34(self):
        sb = FakeSupabase(rpc_data=_applied_data())
        result = apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        assert result["status"] == "APPLIED"


class TestC35_AppliedHasPaymentId:
    def test_C35(self):
        sb = FakeSupabase(rpc_data=_applied_data())
        result = apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        assert "payment_id" in result


class TestC36_AppliedHasContractId:
    def test_C36(self):
        sb = FakeSupabase(rpc_data=_applied_data())
        result = apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        assert "contract_id" in result


class TestC37_AppliedDoesNotRaise:
    def test_C37(self):
        sb = FakeSupabase(rpc_data=_applied_data())
        try:
            apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        except SaasV2AtomicApplyError:
            pytest.fail("APPLIED는 예외를 발생시키면 안 됩니다")


class TestC38_AlreadyAppliedReturnsDict:
    def test_C38(self):
        sb = FakeSupabase(rpc_data=_already_applied_data())
        result = apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        assert isinstance(result, dict)


class TestC39_AlreadyAppliedStatusInResult:
    def test_C39(self):
        sb = FakeSupabase(rpc_data=_already_applied_data())
        result = apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        assert result["status"] == "ALREADY_APPLIED"


class TestC40_AlreadyAppliedDoesNotRaise:
    def test_C40(self):
        sb = FakeSupabase(rpc_data=_already_applied_data())
        try:
            apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        except SaasV2AtomicApplyError:
            pytest.fail("ALREADY_APPLIED는 예외를 발생시키면 안 됩니다")


class TestC41_ReturnedDictIsPassedThrough:
    def test_C41(self):
        data = _applied_data()
        data["extra_key"] = "extra_value"
        sb = FakeSupabase(rpc_data=data)
        result = apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        assert result is data


class TestC42_ExtraKeysPassedThrough:
    def test_C42(self):
        data = _applied_data()
        data["commercial_version_id"] = "ffffffff-ffff-ffff-ffff-ffffffffffff"
        sb = FakeSupabase(rpc_data=data)
        result = apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        assert "commercial_version_id" in result


class TestC43_FullAppliedResultDict:
    def test_C43(self):
        data = _applied_data()
        sb = FakeSupabase(rpc_data=data)
        result = apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        assert result["status"] == "APPLIED"
        assert result["payment_id"] == _PAYMENT_ID
        assert result["contract_id"] == str(_CONTRACT_ID)


class TestC44_FullAlreadyAppliedResultDict:
    def test_C44(self):
        data = _already_applied_data()
        sb = FakeSupabase(rpc_data=data)
        result = apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        assert result["status"] == "ALREADY_APPLIED"
        assert result["payment_id"] == _PAYMENT_ID
        assert result["contract_id"] == str(_CONTRACT_ID)


# ═══════════════════════════════════════════════════════════════════════════
# E. 오류 처리 (C45-C60)
# ═══════════════════════════════════════════════════════════════════════════

class TestC45_RpcExceptionRaises:
    def test_C45(self):
        sb = FakeSupabase(rpc_exc=RuntimeError("DB 연결 실패"))
        with pytest.raises(SaasV2AtomicApplyError):
            apply_saas_v2_contract_plan_atomic(sb, _make_plan())


class TestC46_RpcExceptionCodeIsV2RpcError:
    def test_C46(self):
        sb = FakeSupabase(rpc_exc=RuntimeError("DB 연결 실패"))
        with pytest.raises(SaasV2AtomicApplyError) as exc_info:
            apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        assert exc_info.value.code == "V2_RPC_ERROR"


class TestC47_OriginalExceptionChained:
    def test_C47(self):
        original = RuntimeError("원본 오류")
        sb = FakeSupabase(rpc_exc=original)
        with pytest.raises(SaasV2AtomicApplyError) as exc_info:
            apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        assert exc_info.value.__cause__ is original


class TestC48_DataNoneRaises:
    def test_C48(self):
        sb = FakeSupabase(rpc_data=None)
        with pytest.raises(SaasV2AtomicApplyError):
            apply_saas_v2_contract_plan_atomic(sb, _make_plan())


class TestC49_DataNoneCodeIsV2RpcError:
    def test_C49(self):
        sb = FakeSupabase(rpc_data=None)
        with pytest.raises(SaasV2AtomicApplyError) as exc_info:
            apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        assert exc_info.value.code == "V2_RPC_ERROR"


class TestC50_DataListRaises:
    def test_C50(self):
        sb = FakeSupabase(rpc_data=[{"status": "APPLIED"}])
        with pytest.raises(SaasV2AtomicApplyError):
            apply_saas_v2_contract_plan_atomic(sb, _make_plan())


class TestC51_DataStrRaises:
    def test_C51(self):
        sb = FakeSupabase(rpc_data="APPLIED")
        with pytest.raises(SaasV2AtomicApplyError):
            apply_saas_v2_contract_plan_atomic(sb, _make_plan())


class TestC52_DataIntRaises:
    def test_C52(self):
        sb = FakeSupabase(rpc_data=1)
        with pytest.raises(SaasV2AtomicApplyError):
            apply_saas_v2_contract_plan_atomic(sb, _make_plan())


class TestC53_PaymentNotFoundRaises:
    def test_C53(self):
        sb = FakeSupabase(rpc_data={"status": "V2_PAYMENT_NOT_FOUND", "payment_id": _PAYMENT_ID})
        with pytest.raises(SaasV2AtomicApplyError):
            apply_saas_v2_contract_plan_atomic(sb, _make_plan())


class TestC54_PaymentNotFoundCode:
    def test_C54(self):
        sb = FakeSupabase(rpc_data={"status": "V2_PAYMENT_NOT_FOUND", "payment_id": _PAYMENT_ID})
        with pytest.raises(SaasV2AtomicApplyError) as exc_info:
            apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        assert exc_info.value.code == "V2_PAYMENT_NOT_FOUND"


class TestC55_PaymentNotPaidRaises:
    def test_C55(self):
        sb = FakeSupabase(rpc_data={"status": "V2_PAYMENT_NOT_PAID"})
        with pytest.raises(SaasV2AtomicApplyError):
            apply_saas_v2_contract_plan_atomic(sb, _make_plan())


class TestC56_PaymentNotPaidCode:
    def test_C56(self):
        sb = FakeSupabase(rpc_data={"status": "V2_PAYMENT_NOT_PAID"})
        with pytest.raises(SaasV2AtomicApplyError) as exc_info:
            apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        assert exc_info.value.code == "V2_PAYMENT_NOT_PAID"


class TestC57_AtomicPartialStateRaises:
    def test_C57(self):
        sb = FakeSupabase(rpc_data={"status": "V2_ATOMIC_PARTIAL_STATE"})
        with pytest.raises(SaasV2AtomicApplyError):
            apply_saas_v2_contract_plan_atomic(sb, _make_plan())


class TestC58_AtomicPartialStateCode:
    def test_C58(self):
        sb = FakeSupabase(rpc_data={"status": "V2_ATOMIC_PARTIAL_STATE"})
        with pytest.raises(SaasV2AtomicApplyError) as exc_info:
            apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        assert exc_info.value.code == "V2_ATOMIC_PARTIAL_STATE"


class TestC59_EmptyStatusRaisesV2UnexpectedStatus:
    def test_C59(self):
        sb = FakeSupabase(rpc_data={"status": ""})
        with pytest.raises(SaasV2AtomicApplyError) as exc_info:
            apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        assert exc_info.value.code == "V2_UNEXPECTED_STATUS"


class TestC60_MissingStatusRaisesV2UnexpectedStatus:
    def test_C60(self):
        sb = FakeSupabase(rpc_data={"payment_id": _PAYMENT_ID})
        with pytest.raises(SaasV2AtomicApplyError) as exc_info:
            apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        assert exc_info.value.code == "V2_UNEXPECTED_STATUS"


# ═══════════════════════════════════════════════════════════════════════════
# F. SaasV2AtomicApplyError 클래스 (C61-C70)
# ═══════════════════════════════════════════════════════════════════════════

class TestC61_ErrorHasCodeAttr:
    def test_C61(self):
        err = SaasV2AtomicApplyError("V2_RPC_ERROR")
        assert hasattr(err, "code")


class TestC62_ErrorHasMessageAttr:
    def test_C62(self):
        err = SaasV2AtomicApplyError("V2_RPC_ERROR")
        assert hasattr(err, "message")


class TestC63_CodeStoredCorrectly:
    def test_C63(self):
        err = SaasV2AtomicApplyError("V2_ATOMIC_PARTIAL_STATE", "부분 상태")
        assert err.code == "V2_ATOMIC_PARTIAL_STATE"


class TestC64_MessageDefaultsToCode:
    def test_C64(self):
        err = SaasV2AtomicApplyError("V2_RPC_ERROR")
        assert err.message == "V2_RPC_ERROR"


class TestC65_MessageStoredWhenProvided:
    def test_C65(self):
        err = SaasV2AtomicApplyError("V2_RPC_ERROR", "RPC 호출 실패: timeout")
        assert err.message == "RPC 호출 실패: timeout"


class TestC66_IsExceptionSubclass:
    def test_C66(self):
        err = SaasV2AtomicApplyError("V2_RPC_ERROR")
        assert isinstance(err, Exception)


class TestC67_StrEqualsMessage:
    def test_C67(self):
        err = SaasV2AtomicApplyError("V2_RPC_ERROR", "custom message")
        assert str(err) == err.message


class TestC68_MultipleCodesInstantiable:
    def test_C68(self):
        codes = [
            "V2_RPC_ERROR",
            "V2_PAYMENT_NOT_FOUND",
            "V2_PAYMENT_NOT_PAID",
            "V2_ATOMIC_PARTIAL_STATE",
            "V2_UNEXPECTED_STATUS",
        ]
        for code in codes:
            err = SaasV2AtomicApplyError(code)
            assert err.code == code


class TestC69_IsNotAdapterError:
    def test_C69(self):
        from services.saas_payment_success_v2_adapter import SaasPaymentSuccessV2AdapterError
        err = SaasV2AtomicApplyError("V2_RPC_ERROR")
        assert not isinstance(err, SaasPaymentSuccessV2AdapterError)


class TestC70_ImportedFromCorrectModule:
    def test_C70(self):
        import services.saas_contract_atomic_apply_v2 as m
        assert hasattr(m, "SaasV2AtomicApplyError")
        assert m.SaasV2AtomicApplyError is SaasV2AtomicApplyError


# ═══════════════════════════════════════════════════════════════════════════
# G. 모듈 구조 가드 (C71-C80)
# ═══════════════════════════════════════════════════════════════════════════

import inspect  # noqa: E402
import importlib  # noqa: E402


def _module_src() -> str:
    import services.saas_contract_atomic_apply_v2 as m
    return inspect.getsource(m)


class TestC71_NoDirectTableCall:
    def test_C71(self):
        sb = FakeSupabase(rpc_data=_applied_data())
        # FakeSupabase.table() raises — if apply calls it, test fails
        apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        # also check source
        assert ".table(" not in _module_src()


class TestC72_NoDirectFromCall:
    def test_C72(self):
        sb = FakeSupabase(rpc_data=_applied_data())
        apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        assert ".from_(" not in _module_src()


class TestC73_NoRouterImport:
    def test_C73(self):
        src = _module_src()
        assert "router" not in src


class TestC74_NoPriceEngineImport:
    def test_C74(self):
        src = _module_src()
        assert "price_engine" not in src


class TestC75_DbWriteZeroDocumented:
    def test_C75(self):
        src = _module_src()
        assert "DB write = 0" in src


class TestC76_TerminalStatusesIsSet:
    def test_C76(self):
        assert isinstance(_TERMINAL_STATUSES, (set, frozenset))


class TestC77_AppliedInTerminalStatuses:
    def test_C77(self):
        assert "APPLIED" in _TERMINAL_STATUSES


class TestC78_AlreadyAppliedInTerminalStatuses:
    def test_C78(self):
        assert "ALREADY_APPLIED" in _TERMINAL_STATUSES


class TestC79_TerminalStatusesHasExactlyTwoMembers:
    def test_C79(self):
        assert len(_TERMINAL_STATUSES) == 2


class TestC80_ApplyFunctionIsCallable:
    def test_C80(self):
        assert callable(apply_saas_v2_contract_plan_atomic)


# ═══════════════════════════════════════════════════════════════════════════
# H. 경계/회귀 (C81-C86)
# ═══════════════════════════════════════════════════════════════════════════

class TestC81_PlanNotMutated:
    def test_C81(self):
        sb = FakeSupabase(rpc_data=_applied_data())
        plan = _make_plan()
        original_payment_id = plan.payment_id
        original_contract_id = plan.contract_id
        original_row = dict(plan.contract_row)
        apply_saas_v2_contract_plan_atomic(sb, plan)
        assert plan.payment_id == original_payment_id
        assert plan.contract_id == original_contract_id
        assert plan.contract_row == original_row


class TestC82_OnlyOneRpcCallPerApply:
    def test_C82(self):
        sb = FakeSupabase(rpc_data=_applied_data())
        apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        assert len(sb.rpc_calls) == 1


class TestC83_MultipleApplyCallsMakeMultipleRpcCalls:
    def test_C83(self):
        sb = FakeSupabase(rpc_data=_applied_data())
        plan = _make_plan()
        apply_saas_v2_contract_plan_atomic(sb, plan)
        apply_saas_v2_contract_plan_atomic(sb, plan)
        assert len(sb.rpc_calls) == 2


class TestC84_AlreadyAppliedFullDictPassedThrough:
    def test_C84(self):
        data = _already_applied_data()
        data["extra"] = "value"
        sb = FakeSupabase(rpc_data=data)
        result = apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        assert result["extra"] == "value"


class TestC85_NonTerminalErrorMessageContainsData:
    def test_C85(self):
        data = {"status": "V2_ATOMIC_PARTIAL_STATE", "contract_id": str(_CONTRACT_ID)}
        sb = FakeSupabase(rpc_data=data)
        with pytest.raises(SaasV2AtomicApplyError) as exc_info:
            apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        assert str(_CONTRACT_ID) in exc_info.value.message


class TestC86_ApplyFunctionAcceptsTwoArgs:
    def test_C86(self):
        sig = inspect.signature(apply_saas_v2_contract_plan_atomic)
        params = list(sig.parameters.keys())
        assert len(params) == 2
        assert params[0] == "supabase"
        assert params[1] == "plan"


# ═══════════════════════════════════════════════════════════════════════════
# PATCH1: SQL 구조 검증 + 신규 오류 코드 (P01-P22)
# ═══════════════════════════════════════════════════════════════════════════
# 검증 범위:
#   P01-P12: Migration SQL 파일 구조 / 보안 가드
#   P13-P17: SQL 신규 가드 구조 (contract_id 정합성, version_no=1, site_scope partial)
#   P18-P20: SQL 함수 INSERT 구조
#   P21-P22: Python adapter — 신규 오류 코드 처리
# ═══════════════════════════════════════════════════════════════════════════

from pathlib import Path  # noqa: E402


def _migration_sql() -> str:
    path = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "2026-09-28_saas_contract_commercial_v2_atomic_apply.sql"
    )
    return path.read_text()


class TestP01_SqlFileExists:
    def test_P01(self):
        path = (
            Path(__file__).resolve().parents[1]
            / "migrations"
            / "2026-09-28_saas_contract_commercial_v2_atomic_apply.sql"
        )
        assert path.exists()


class TestP02_SecurityInvokerPresent:
    def test_P02(self):
        assert "SECURITY INVOKER" in _migration_sql()


class TestP03_SecurityDefinerAbsent:
    def test_P03(self):
        assert "SECURITY DEFINER" not in _migration_sql()


class TestP04_SearchPathEmpty:
    def test_P04(self):
        assert "SET search_path = ''" in _migration_sql()


class TestP05_ServiceRoleGrantPresent:
    def test_P05(self):
        sql = _migration_sql()
        assert "GRANT EXECUTE" in sql
        assert "service_role" in sql


class TestP06_RevokeFromPublicPresent:
    def test_P06(self):
        assert "FROM PUBLIC" in _migration_sql()


class TestP07_RevokeFromAnonPresent:
    def test_P07(self):
        sql = _migration_sql()
        assert "FROM anon" in sql


class TestP08_RevokeFromAuthenticatedPresent:
    def test_P08(self):
        sql = _migration_sql()
        assert "FROM authenticated" in sql


class TestP09_ForUpdatePresent:
    def test_P09(self):
        assert "FOR UPDATE" in _migration_sql()


class TestP10_ProductionApplyZeroInHeader:
    def test_P10(self):
        assert "PRODUCTION APPLY = 0" in _migration_sql()


class TestP11_ArtifactOnlyInHeader:
    def test_P11(self):
        assert "ARTIFACT ONLY" in _migration_sql()


class TestP12_AtomicPartialStateThreePaths:
    def test_P12(self):
        # 3 경로: CV없음, site_scopes없음, orphan contract
        sql = _migration_sql()
        assert sql.count("V2_ATOMIC_PARTIAL_STATE") >= 3


class TestP13_ContractIdMismatchGuardPresent:
    def test_P13(self):
        assert "V2_CONTRACT_ID_MISMATCH" in _migration_sql()


class TestP14_VersionNoGuardPresent:
    def test_P14(self):
        assert "V2_VERSION_NO_INVALID" in _migration_sql()


class TestP15_SiteScopePartialCheckInAlreadyAppliedPath:
    def test_P15(self):
        sql = _migration_sql()
        # saas_contract_site_scopes은 ALREADY_APPLIED 검증(COUNT)과 INSERT 양쪽에 존재해야 함
        assert sql.count("saas_contract_site_scopes") >= 2


class TestP16_AlreadyAppliedPresent:
    def test_P16(self):
        assert "ALREADY_APPLIED" in _migration_sql()


class TestP17_StandardTierSiteScopeCheck:
    def test_P17(self):
        sql = _migration_sql()
        # MANAGER/FIELD tier에 대한 site_scope count 검증 코드 존재
        assert "'MANAGER'" in sql
        assert "'FIELD'" in sql
        assert "v_scope_count" in sql


class TestP18_ExplicitContractInsertNoPopulateRecord:
    def test_P18(self):
        # jsonb_populate_record는 contracts INSERT에 사용 금지
        assert "jsonb_populate_record" not in _migration_sql()


class TestP19_ContractAmountInExplicitInsert:
    def test_P19(self):
        sql = _migration_sql()
        assert "contract_amount" in sql


class TestP20_NullIfForPricingSnapshot:
    def test_P20(self):
        sql = _migration_sql()
        assert "NULLIF" in sql
        assert "'null'::jsonb" in sql


class TestP21_V2ContractIdMismatchRaisesWithCorrectCode:
    def test_P21(self):
        sb = FakeSupabase(rpc_data={"status": "V2_CONTRACT_ID_MISMATCH", "payment_id": _PAYMENT_ID})
        with pytest.raises(SaasV2AtomicApplyError) as exc_info:
            apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        assert exc_info.value.code == "V2_CONTRACT_ID_MISMATCH"


class TestP22_V2VersionNoInvalidRaisesWithCorrectCode:
    def test_P22(self):
        sb = FakeSupabase(rpc_data={"status": "V2_VERSION_NO_INVALID", "payment_id": _PAYMENT_ID})
        with pytest.raises(SaasV2AtomicApplyError) as exc_info:
            apply_saas_v2_contract_plan_atomic(sb, _make_plan())
        assert exc_info.value.code == "V2_VERSION_NO_INVALID"
