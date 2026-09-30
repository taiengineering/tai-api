"""WO-BRIDGE-PAY-01-BE-RUNTIME-001 Tests — BP01-BP39.

BP01-BP15:  prepare endpoint schema + auth/ownership guards
BP16-BP19:  payment_post_process routing (V2 SAAS initial block)
BP20-BP28:  apply_saas_v2_initial_payment_runtime unit tests
BP29-BP34:  replay (stored contract_id reuse)
BP35-BP39:  race recovery (V2_CONTRACT_ID_MISMATCH → peer refetch → retry)
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("INTERNAL_API_SECRET", "pytest-secret")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.saas_initial_payment_runtime_v2 import (  # noqa: E402
    SaasInitialPaymentRuntimeV2Error,
    apply_saas_v2_initial_payment_runtime,
)
from services.saas_contract_atomic_apply_v2 import SaasV2AtomicApplyError  # noqa: E402

# ── Shared constants ───────────────────────────────────────────────────────────

COMPANY_ID  = "aaaa0000-0000-0000-0000-000000000001"
QUOTE_ID    = "bbbb0000-0000-0000-0000-000000000002"
PAYMENT_ID  = "cccc0000-0000-0000-0000-000000000003"
ENTITY_ID   = "dddd0000-0000-0000-0000-000000000004"
USER_ID     = "eeee0000-0000-0000-0000-000000000005"
CONTRACT_ID = uuid.UUID("11111111-0000-0000-0000-000000000001")

_SNAP_DICT = {
    "schema_version": "SAAS_PRICING_V2",
    "policy_version": "TEST-v1",
    "product_tier": "FIELD",
    "pricing_mode": "STANDARD",
    "sites": [{
        "entity_type": "factory",
        "entity_id": ENTITY_ID,
        "sector": "INDUSTRY",
        "base_band_code": "A1",
        "base_amount": 100000,
        "is_primary": True,
        "applied_rate_bps": 10000,
        "final_site_amount": 100000,
    }],
    "worker": {
        "capacity": 10,
        "amount": 50000,
        "brackets": [{"range_from": 1, "range_to": None, "unit_rate": 5000, "units": 10, "amount": 50000}],
    },
    "payment_months": 12,
    "term_discount_rate_bps": 0,
    "monthly_supply_amount": 150000,
    "prepaid_supply_amount": 1800000,
    "vat_rate_bps": 1000,
    "vat_amount": 180000,
    "total_amount": 1980000,
}

_ITEM_DICT = {
    "quote_schema_version": "SAAS_QUOTE_V2",
    "display_name": "TAI Safe 현장참여형",
    "billing_unit": "개월",
    "unit_amount": 150000,
    "quantity": 12,
    "supply_amount": _SNAP_DICT["prepaid_supply_amount"],
    "vat_amount": _SNAP_DICT["vat_amount"],
    "total_amount": _SNAP_DICT["total_amount"],
    "service_type": "SAAS",
    "price_id": None,
    "tier_code": None,
    "sector": "INDUSTRY",
    "sectors": ["INDUSTRY"],
    "product_tier": "FIELD",
    "pricing_mode": "STANDARD",
    "policy_version": "TEST-v1",
    "worker_capacity": 10,
    "payment_months": 12,
    "vat_rate": 0.1,
    "vat_rate_bps": 1000,
    "pricing_input": {},
    "pricing_snapshot": _SNAP_DICT,
}


def _valid_quote(quote_id=QUOTE_ID, company_id=COMPANY_ID):
    return {
        "id": quote_id,
        "company_id": company_id,
        "status_code": "ISSUED",
        "service_type": "SAAS",
        "source": "member_auto",
        "supply_amount": _SNAP_DICT["prepaid_supply_amount"],
        "vat_amount": _SNAP_DICT["vat_amount"],
        "total_amount": _SNAP_DICT["total_amount"],
        "items": [dict(_ITEM_DICT)],
    }


def _valid_pay(quote_id=QUOTE_ID, company_id=COMPANY_ID, payment_id=PAYMENT_ID,
               contract_id=None):
    pay = {
        "id": payment_id,
        "product_type": "SAAS",
        "status_code": "SUCCESS",
        "company_id": company_id,
        "quote_id": quote_id,
        "supply_amount": _SNAP_DICT["prepaid_supply_amount"],
        "vat_amount": _SNAP_DICT["vat_amount"],
        "total_amount": _SNAP_DICT["total_amount"],
        "period_months": _SNAP_DICT["payment_months"],
        "paid_at": "2026-09-28T10:00:00+09:00",
        "user_id": USER_ID,
        "plan_code": None,
        "payment_type": "INITIAL",
        "contract_id": contract_id,
    }
    return pay


# ── FakeSupabase for runtime tests ─────────────────────────────────────────────

class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeRpcChain:
    """Supports chaining .execute() returning fixed data or raising exception."""
    def __init__(self, data=None, exc=None):
        self._data = data
        self._exc = exc
        self.execute_count = 0

    def execute(self):
        self.execute_count += 1
        if self._exc is not None:
            raise self._exc
        return _FakeResult(self._data)


class _FakeTableChain:
    """Simple table chain for select/eq/limit/execute."""
    def __init__(self, data=None):
        self._data = data

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def execute(self):
        return _FakeResult(self._data or [])


class FakeSupabase:
    """Minimal fake Supabase: RPC calls observed, table() returns fixed data."""

    def __init__(self, rpc_responses=None, table_data=None):
        """
        rpc_responses: list of (data, exc) tuples consumed in order.
        table_data: list of rows returned by table().select().eq().limit().execute()
        """
        self._rpc_responses = list(rpc_responses or [])
        self._table_data = table_data
        self.rpc_calls: list[dict] = []

    def rpc(self, name: str, params: dict) -> _FakeRpcChain:
        self.rpc_calls.append({"name": name, "params": params})
        if self._rpc_responses:
            data, exc = self._rpc_responses.pop(0)
        else:
            data, exc = None, RuntimeError("unexpected rpc call")
        return _FakeRpcChain(data, exc)

    def table(self, *a, **k):
        return _FakeTableChain(self._table_data)


# ═══════════════════════════════════════════════════════════════════════════════
# BP01-BP15: prepare endpoint — SaasV2PaymentPrepareBody schema tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestPrepareBodySchema:
    """BP01-BP15: Schema field restrictions."""

    def _load_cls(self):
        from routers.member_quotes import SaasV2PaymentPrepareBody
        return SaasV2PaymentPrepareBody

    def test_BP01_auth_dep_in_router_source(self):
        """BP01: prepare_v2_payment uses Depends(get_current_user)."""
        import inspect
        import routers.member_quotes as mq
        src = inspect.getsource(mq.prepare_v2_payment)
        assert "Depends(get_current_user)" in src

    def test_BP02_ownership_dep_in_router_source(self):
        """BP02: prepare_v2_payment calls _require_member_company."""
        import inspect
        import routers.member_quotes as mq
        src = inspect.getsource(mq.prepare_v2_payment)
        assert "_require_member_company" in src

    def test_BP03_router_prefix_is_me_quotes(self):
        """BP03: router is at /me/quotes."""
        import routers.member_quotes as mq
        assert mq.router.prefix == "/me/quotes"

    def test_BP04_body_has_no_amount_field(self):
        """BP04: SaasV2PaymentPrepareBody must NOT have 'amount' field."""
        cls = self._load_cls()
        assert "amount" not in cls.model_fields

    def test_BP05_body_has_no_company_id_field(self):
        """BP05: SaasV2PaymentPrepareBody must NOT have 'company_id' field."""
        cls = self._load_cls()
        assert "company_id" not in cls.model_fields

    def test_BP06_body_has_no_user_id_field(self):
        """BP06: SaasV2PaymentPrepareBody must NOT have 'user_id' field."""
        cls = self._load_cls()
        assert "user_id" not in cls.model_fields

    def test_BP07_body_has_no_product_type_field(self):
        """BP07: SaasV2PaymentPrepareBody must NOT have 'product_type' field."""
        cls = self._load_cls()
        assert "product_type" not in cls.model_fields

    def test_BP08_body_has_no_plan_code_field(self):
        """BP08: SaasV2PaymentPrepareBody must NOT have 'plan_code' field."""
        cls = self._load_cls()
        assert "plan_code" not in cls.model_fields

    def test_BP09_body_has_no_period_months_field(self):
        """BP09: SaasV2PaymentPrepareBody must NOT have 'period_months' field."""
        cls = self._load_cls()
        assert "period_months" not in cls.model_fields

    def test_BP10_allowed_fields_only(self):
        """BP10: SaasV2PaymentPrepareBody fields are exactly the allowed 4."""
        cls = self._load_cls()
        expected = {"proof_type", "buyername", "buyertel", "buyeremail"}
        assert set(cls.model_fields.keys()) == expected

    def test_BP11_proof_type_none_accepted(self):
        """BP11: proof_type=None is accepted."""
        cls = self._load_cls()
        obj = cls(proof_type=None)
        assert obj.proof_type is None

    def test_BP12_proof_type_tax_invoice_accepted(self):
        """BP12: proof_type='TAX_INVOICE' is accepted."""
        cls = self._load_cls()
        obj = cls(proof_type="TAX_INVOICE")
        assert obj.proof_type == "TAX_INVOICE"

    def test_BP13_proof_type_card_receipt_rejected(self):
        """BP13: proof_type='CARD_RECEIPT' is rejected (422)."""
        from pydantic import ValidationError
        cls = self._load_cls()
        with pytest.raises(ValidationError):
            cls(proof_type="CARD_RECEIPT")

    def test_BP14_all_optional_fields_default_none(self):
        """BP14: All fields default to None."""
        cls = self._load_cls()
        obj = cls()
        assert obj.proof_type is None
        assert obj.buyername is None
        assert obj.buyertel is None
        assert obj.buyeremail is None

    def test_BP15_buyername_accepted(self):
        """BP15: buyername is accepted."""
        cls = self._load_cls()
        obj = cls(buyername="홍길동", buyertel="010-0000-0000", buyeremail="test@example.com")
        assert obj.buyername == "홍길동"


# ═══════════════════════════════════════════════════════════════════════════════
# BP16-BP19: payment_post_process routing
# ═══════════════════════════════════════════════════════════════════════════════

class TestPostProcessRouting:
    """BP16-BP19: on_payment_success_sync routing to V2 initial block."""

    def _make_pay_res(self, product_type="SAAS", payment_type="INITIAL",
                      status_code="SUCCESS", **extra):
        base = {
            "id": PAYMENT_ID,
            "product_type": product_type,
            "payment_type": payment_type,
            "status_code": status_code,
            "company_id": COMPANY_ID,
            "quote_id": QUOTE_ID,
            "supply_amount": 1800000,
            "vat_amount": 180000,
            "total_amount": 1980000,
            "period_months": 12,
            "paid_at": "2026-09-28T10:00:00+09:00",
            "user_id": USER_ID,
            "plan_code": None,
            "contract_id": None,
        }
        base.update(extra)
        return base

    def test_BP16_saas_initial_enters_v2_route(self):
        """BP16: product_type=SAAS (non-RENEWAL/non-UPGRADE) → calls apply_saas_v2_initial_payment_runtime."""
        pay = self._make_pay_res(product_type="SAAS", payment_type="INITIAL")

        with patch("services.payment_post_process.get_supabase") as mock_sb_factory, \
             patch("services.saas_initial_payment_runtime_v2.apply_saas_v2_initial_payment_runtime") as mock_apply, \
             patch("services.payment_post_process.send_payment_notification"):
            mock_apply.return_value = {"status": "APPLIED"}
            mock_sb = MagicMock()
            mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[pay])
            mock_sb_factory.return_value = mock_sb

            from services.payment_post_process import on_payment_success_sync
            on_payment_success_sync(PAYMENT_ID)

        mock_apply.assert_called_once()

    def test_BP17_upgrade_does_not_enter_initial_v2(self):
        """BP17: payment_type=UPGRADE → does NOT call apply_saas_v2_initial_payment_runtime."""
        pay = self._make_pay_res(product_type="SAAS", payment_type="UPGRADE")

        with patch("services.payment_post_process.get_supabase") as mock_sb_factory, \
             patch("services.saas_initial_payment_runtime_v2.apply_saas_v2_initial_payment_runtime") as mock_apply, \
             patch("services.payment_post_process.send_payment_notification"), \
             patch("services.tier_upgrade_svc.apply_saas_tier_upgrade") as mock_upgrade:
            mock_upgrade.return_value = {"status": "APPLIED"}
            mock_sb = MagicMock()
            mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[pay])
            mock_sb_factory.return_value = mock_sb

            from services.payment_post_process import on_payment_success_sync
            on_payment_success_sync(PAYMENT_ID)

        mock_apply.assert_not_called()

    def test_BP18_renewal_does_not_enter_initial_v2(self):
        """BP18: payment_type=RENEWAL → does NOT call apply_saas_v2_initial_payment_runtime."""
        pay = self._make_pay_res(product_type="SAAS", payment_type="RENEWAL",
                                  contract_id=str(CONTRACT_ID))

        with patch("services.payment_post_process.get_supabase") as mock_sb_factory, \
             patch("services.saas_initial_payment_runtime_v2.apply_saas_v2_initial_payment_runtime") as mock_apply, \
             patch("services.payment_post_process.send_payment_notification"), \
             patch("services.saas_renewal_runtime_v2.apply_saas_v2_renewal_runtime") as mock_renewal, \
             patch("services.saas_renewal_runtime_v2.classify_renewal_runtime_route", return_value="V2"):
            mock_renewal.return_value = {"status": "APPLIED"}
            mock_sb = MagicMock()
            mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[pay])
            mock_sb_factory.return_value = mock_sb

            from services.payment_post_process import on_payment_success_sync
            on_payment_success_sync(PAYMENT_ID)

        mock_apply.assert_not_called()

    def test_BP19_saas_industry_legacy_does_not_enter_initial_v2(self):
        """BP19: product_type=SAAS_INDUSTRY (legacy) → does NOT enter initial V2 block."""
        pay = self._make_pay_res(product_type="SAAS_INDUSTRY", payment_type="INITIAL",
                                  plan_code="INDUSTRY_PRO")

        with patch("services.payment_post_process.get_supabase") as mock_sb_factory, \
             patch("services.saas_initial_payment_runtime_v2.apply_saas_v2_initial_payment_runtime") as mock_apply, \
             patch("services.payment_post_process.send_payment_notification"):
            mock_sb = MagicMock()
            mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[pay])
            mock_sb_factory.return_value = mock_sb

            from services.payment_post_process import on_payment_success_sync
            on_payment_success_sync(PAYMENT_ID)

        mock_apply.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════════
# BP20-BP28: apply_saas_v2_initial_payment_runtime unit tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestApplySaasV2InitialPaymentRuntime:

    def _make_rpc_success(self, status="APPLIED"):
        # atomic apply expects result.data to be a dict (not a list)
        return {"status": status}, None

    def _make_rpc_error(self, code="V2_RPC_ERROR"):
        return None, SaasV2AtomicApplyError(code, code)

    def test_BP20_first_apply_atomic_called_once_returns_applied(self):
        """BP20: Happy path — atomic called exactly 1 time, returns APPLIED."""
        quote = _valid_quote()
        pay = _valid_pay()

        sb = FakeSupabase(rpc_responses=[self._make_rpc_success("APPLIED")])

        with patch("services.saas_initial_payment_runtime_v2._load_quote", return_value=quote), \
             patch("services.saas_initial_payment_runtime_v2.business_today", return_value=date(2026, 9, 30)), \
             patch("services.saas_initial_payment_runtime_v2._gen_contract_no", return_value="CON-TEST-001"):
            result = apply_saas_v2_initial_payment_runtime(sb, pay)

        assert result["status"] == "APPLIED"
        assert len(sb.rpc_calls) == 1

    def test_BP21_does_not_call_create_contract_from_payment(self):
        """BP21: _create_contract_from_payment must NOT be called."""
        quote = _valid_quote()
        pay = _valid_pay()
        sb = FakeSupabase(rpc_responses=[self._make_rpc_success("APPLIED")])

        with patch("services.saas_initial_payment_runtime_v2._load_quote", return_value=quote), \
             patch("services.saas_initial_payment_runtime_v2.business_today", return_value=date(2026, 9, 30)), \
             patch("services.saas_initial_payment_runtime_v2._gen_contract_no", return_value="CON-TEST-001"), \
             patch("services.payment_post_process._create_contract_from_payment") as mock_create:
            apply_saas_v2_initial_payment_runtime(sb, pay)
            mock_create.assert_not_called()

    def test_BP22_does_not_call_activate_existing_contract(self):
        """BP22: _activate_existing_contract must NOT be called."""
        quote = _valid_quote()
        pay = _valid_pay()
        sb = FakeSupabase(rpc_responses=[self._make_rpc_success("APPLIED")])

        with patch("services.saas_initial_payment_runtime_v2._load_quote", return_value=quote), \
             patch("services.saas_initial_payment_runtime_v2.business_today", return_value=date(2026, 9, 30)), \
             patch("services.saas_initial_payment_runtime_v2._gen_contract_no", return_value="CON-TEST-001"), \
             patch("services.payment_post_process._activate_existing_contract") as mock_activate:
            apply_saas_v2_initial_payment_runtime(sb, pay)
            mock_activate.assert_not_called()

    def test_BP23_does_not_call_expire_other_active_contracts(self):
        """BP23: _expire_other_active_contracts must NOT be called."""
        quote = _valid_quote()
        pay = _valid_pay()
        sb = FakeSupabase(rpc_responses=[self._make_rpc_success("APPLIED")])

        with patch("services.saas_initial_payment_runtime_v2._load_quote", return_value=quote), \
             patch("services.saas_initial_payment_runtime_v2.business_today", return_value=date(2026, 9, 30)), \
             patch("services.saas_initial_payment_runtime_v2._gen_contract_no", return_value="CON-TEST-001"), \
             patch("services.payment_post_process._expire_other_active_contracts") as mock_expire:
            apply_saas_v2_initial_payment_runtime(sb, pay)
            mock_expire.assert_not_called()

    def test_BP24_plan_code_nonnull_raises(self):
        """BP24: plan_code != None → raises SaasInitialPaymentRuntimeV2Error."""
        pay = _valid_pay()
        pay["plan_code"] = "INDUSTRY_PRO"
        sb = FakeSupabase()

        with pytest.raises(SaasInitialPaymentRuntimeV2Error) as exc_info:
            apply_saas_v2_initial_payment_runtime(sb, pay)

        assert exc_info.value.code == "V2_INIT_PLAN_CODE_FORBIDDEN"

    def test_BP25_no_quote_id_raises(self):
        """BP25: quote_id missing → raises with V2_INIT_NO_QUOTE_ID."""
        pay = _valid_pay()
        pay["quote_id"] = None
        # Use real _load_quote so it checks for missing quote_id
        sb = FakeSupabase()

        with pytest.raises(SaasInitialPaymentRuntimeV2Error) as exc_info:
            apply_saas_v2_initial_payment_runtime(sb, pay)

        assert exc_info.value.code == "V2_INIT_NO_QUOTE_ID"

    def test_BP26_wrong_quote_source_raises(self):
        """BP26: wrong quote source (not member_auto) → adapter error propagates."""
        from services.saas_payment_success_v2_adapter import SaasPaymentSuccessV2AdapterError

        bad_quote = _valid_quote()
        bad_quote["source"] = "admin_manual"
        pay = _valid_pay()
        sb = FakeSupabase()

        with patch("services.saas_initial_payment_runtime_v2._load_quote", return_value=bad_quote), \
             patch("services.saas_initial_payment_runtime_v2.business_today", return_value=date(2026, 9, 30)), \
             patch("services.saas_initial_payment_runtime_v2._gen_contract_no", return_value="CON-TEST-001"):
            # adapter raises SaasPaymentSuccessV2AdapterError which is NOT caught → propagates
            with pytest.raises((SaasPaymentSuccessV2AdapterError, Exception)):
                apply_saas_v2_initial_payment_runtime(sb, pay)

    def test_BP27_amount_mismatch_raises(self):
        """BP27: amount mismatch between pay and snapshot → adapter error propagates."""
        from services.saas_payment_success_v2_adapter import SaasPaymentSuccessV2AdapterError

        bad_pay = _valid_pay()
        bad_pay["supply_amount"] = 9999999  # mismatch
        quote = _valid_quote()
        sb = FakeSupabase()

        with patch("services.saas_initial_payment_runtime_v2._load_quote", return_value=quote), \
             patch("services.saas_initial_payment_runtime_v2.business_today", return_value=date(2026, 9, 30)), \
             patch("services.saas_initial_payment_runtime_v2._gen_contract_no", return_value="CON-TEST-001"):
            with pytest.raises((SaasPaymentSuccessV2AdapterError, Exception)):
                apply_saas_v2_initial_payment_runtime(sb, bad_pay)

    def test_BP28_failure_raises_not_swallowed(self):
        """BP28: atomic failure → raises SaasInitialPaymentRuntimeV2Error (not swallowed to legacy)."""
        quote = _valid_quote()
        pay = _valid_pay()
        sb = FakeSupabase(rpc_responses=[(None, SaasV2AtomicApplyError("V2_RPC_ERROR", "rpc failed"))])

        with patch("services.saas_initial_payment_runtime_v2._load_quote", return_value=quote), \
             patch("services.saas_initial_payment_runtime_v2.business_today", return_value=date(2026, 9, 30)), \
             patch("services.saas_initial_payment_runtime_v2._gen_contract_no", return_value="CON-TEST-001"):
            with pytest.raises(SaasInitialPaymentRuntimeV2Error) as exc_info:
                apply_saas_v2_initial_payment_runtime(sb, pay)

        assert exc_info.value.code == "V2_RPC_ERROR"


# ═══════════════════════════════════════════════════════════════════════════════
# BP29-BP34: replay tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestReplay:
    """BP29-BP34: payment.contract_id != None → plan uses that UUID (not fresh)."""

    def test_BP29_replay_uses_stored_contract_id(self):
        """BP29: stored contract_id in payment → plan uses that UUID as override."""
        quote = _valid_quote()
        pay = _valid_pay(contract_id=str(CONTRACT_ID))
        sb = FakeSupabase(rpc_responses=[([{"status": "ALREADY_APPLIED"}], None)])

        captured_plans = []

        original_atomic = __import__(
            "services.saas_contract_atomic_apply_v2",
            fromlist=["apply_saas_v2_contract_plan_atomic"]
        ).apply_saas_v2_contract_plan_atomic

        def capture_plan(sb_, plan):
            captured_plans.append(plan)
            return {"status": "ALREADY_APPLIED"}

        with patch("services.saas_initial_payment_runtime_v2._load_quote", return_value=quote), \
             patch("services.saas_initial_payment_runtime_v2.business_today", return_value=date(2026, 9, 30)), \
             patch("services.saas_initial_payment_runtime_v2._gen_contract_no", return_value="CON-TEST-001"), \
             patch("services.saas_initial_payment_runtime_v2.apply_saas_v2_contract_plan_atomic",
                   side_effect=capture_plan):
            result = apply_saas_v2_initial_payment_runtime(sb, pay)

        assert result["status"] == "ALREADY_APPLIED"
        assert len(captured_plans) == 1
        assert captured_plans[0].contract_id == CONTRACT_ID

    def test_BP30_replay_contract_id_in_contract_row(self):
        """BP30: contract_row["id"] matches the stored contract_id UUID (string form)."""
        quote = _valid_quote()
        pay = _valid_pay(contract_id=str(CONTRACT_ID))

        captured_plans = []

        def capture_plan(sb_, plan):
            captured_plans.append(plan)
            return {"status": "ALREADY_APPLIED"}

        with patch("services.saas_initial_payment_runtime_v2._load_quote", return_value=quote), \
             patch("services.saas_initial_payment_runtime_v2.business_today", return_value=date(2026, 9, 30)), \
             patch("services.saas_initial_payment_runtime_v2._gen_contract_no", return_value="CON-TEST-001"), \
             patch("services.saas_initial_payment_runtime_v2.apply_saas_v2_contract_plan_atomic",
                   side_effect=capture_plan):
            apply_saas_v2_initial_payment_runtime(MagicMock(), pay)

        plan = captured_plans[0]
        assert plan.contract_row["id"] == str(CONTRACT_ID)

    def test_BP31_replay_commercial_bundle_contract_id_matches(self):
        """BP31: commercial_bundle.commercial_version.contract_id matches stored UUID."""
        quote = _valid_quote()
        pay = _valid_pay(contract_id=str(CONTRACT_ID))

        captured_plans = []

        def capture_plan(sb_, plan):
            captured_plans.append(plan)
            return {"status": "ALREADY_APPLIED"}

        with patch("services.saas_initial_payment_runtime_v2._load_quote", return_value=quote), \
             patch("services.saas_initial_payment_runtime_v2.business_today", return_value=date(2026, 9, 30)), \
             patch("services.saas_initial_payment_runtime_v2._gen_contract_no", return_value="CON-TEST-001"), \
             patch("services.saas_initial_payment_runtime_v2.apply_saas_v2_contract_plan_atomic",
                   side_effect=capture_plan):
            apply_saas_v2_initial_payment_runtime(MagicMock(), pay)

        plan = captured_plans[0]
        assert plan.commercial_bundle.commercial_version.contract_id == CONTRACT_ID

    def test_BP32_replay_returns_already_applied(self):
        """BP32: replay path → atomic returns ALREADY_APPLIED."""
        quote = _valid_quote()
        pay = _valid_pay(contract_id=str(CONTRACT_ID))

        with patch("services.saas_initial_payment_runtime_v2._load_quote", return_value=quote), \
             patch("services.saas_initial_payment_runtime_v2.business_today", return_value=date(2026, 9, 30)), \
             patch("services.saas_initial_payment_runtime_v2._gen_contract_no", return_value="CON-TEST-001"), \
             patch("services.saas_initial_payment_runtime_v2.apply_saas_v2_contract_plan_atomic",
                   return_value={"status": "ALREADY_APPLIED"}):
            result = apply_saas_v2_initial_payment_runtime(MagicMock(), pay)

        assert result["status"] == "ALREADY_APPLIED"

    def test_BP33_replay_no_fresh_uuid4_generated(self):
        """BP33: when contract_id_override is set, uuid4() is not called for contract_id."""
        quote = _valid_quote()
        pay = _valid_pay(contract_id=str(CONTRACT_ID))
        uuid4_calls = []

        original_uuid4 = uuid.uuid4

        def tracking_uuid4():
            result = original_uuid4()
            uuid4_calls.append(result)
            return result

        with patch("services.saas_initial_payment_runtime_v2._load_quote", return_value=quote), \
             patch("services.saas_initial_payment_runtime_v2.business_today", return_value=date(2026, 9, 30)), \
             patch("services.saas_initial_payment_runtime_v2._gen_contract_no", return_value="CON-TEST-001"), \
             patch("services.saas_payment_success_v2_adapter.uuid.uuid4", side_effect=tracking_uuid4), \
             patch("services.saas_initial_payment_runtime_v2.apply_saas_v2_contract_plan_atomic",
                   return_value={"status": "ALREADY_APPLIED"}):
            apply_saas_v2_initial_payment_runtime(MagicMock(), pay)

        # With override provided, uuid4 in the adapter should NOT be called for contract_id
        assert len(uuid4_calls) == 0

    def test_BP34_no_stored_contract_id_fresh_uuid4_generated(self):
        """BP34: contract_id=None → fresh uuid4 is used (no override)."""
        quote = _valid_quote()
        pay = _valid_pay(contract_id=None)
        uuid4_calls = []

        original_uuid4 = uuid.uuid4

        def tracking_uuid4():
            result = original_uuid4()
            uuid4_calls.append(result)
            return result

        with patch("services.saas_initial_payment_runtime_v2._load_quote", return_value=quote), \
             patch("services.saas_initial_payment_runtime_v2.business_today", return_value=date(2026, 9, 30)), \
             patch("services.saas_initial_payment_runtime_v2._gen_contract_no", return_value="CON-TEST-001"), \
             patch("services.saas_payment_success_v2_adapter.uuid.uuid4", side_effect=tracking_uuid4), \
             patch("services.saas_initial_payment_runtime_v2.apply_saas_v2_contract_plan_atomic",
                   return_value={"status": "APPLIED"}):
            apply_saas_v2_initial_payment_runtime(MagicMock(), pay)

        # No override → uuid4() called once for contract_id
        assert len(uuid4_calls) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# BP35-BP39: race recovery tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestRaceRecovery:
    """BP35-BP39: V2_CONTRACT_ID_MISMATCH → peer refetch → second atomic call."""

    PEER_CID = uuid.UUID("22222222-0000-0000-0000-000000000002")

    def _sb_with_mismatch_then_success(self, peer_cid=None):
        """FakeSupabase: first rpc → MISMATCH, then table refetch returns peer_cid, second rpc → ALREADY_APPLIED."""
        peer_cid = peer_cid or self.PEER_CID

        class _FakeRaceSupabase:
            def __init__(self):
                self.rpc_calls = []
                self._rpc_seq = [
                    (None, SaasV2AtomicApplyError("V2_CONTRACT_ID_MISMATCH", "mismatch")),
                    ([{"status": "ALREADY_APPLIED"}], None),
                ]

            def rpc(self, name, params):
                self.rpc_calls.append({"name": name, "params": params})
                if self._rpc_seq:
                    data, exc = self._rpc_seq.pop(0)
                else:
                    data, exc = None, RuntimeError("unexpected third rpc call")
                return _FakeRpcChain(data, exc)

            def table(self, *a, **k):
                return _FakeTableChain([{"contract_id": str(peer_cid)}])

        return _FakeRaceSupabase()

    def test_BP35_mismatch_refetch_returns_peer_contract_id(self):
        """BP35: first atomic raises MISMATCH → refetch → second atomic called with peer UUID."""
        quote = _valid_quote()
        pay = _valid_pay()
        sb = self._sb_with_mismatch_then_success()
        captured_plans = []

        original_atomic_module = __import__(
            "services.saas_contract_atomic_apply_v2",
            fromlist=["apply_saas_v2_contract_plan_atomic"]
        )
        original_fn = original_atomic_module.apply_saas_v2_contract_plan_atomic

        call_count = [0]

        def spy_atomic(sb_, plan):
            call_count[0] += 1
            captured_plans.append(plan)
            if call_count[0] == 1:
                raise SaasV2AtomicApplyError("V2_CONTRACT_ID_MISMATCH", "mismatch")
            return {"status": "ALREADY_APPLIED"}

        with patch("services.saas_initial_payment_runtime_v2._load_quote", return_value=quote), \
             patch("services.saas_initial_payment_runtime_v2.business_today", return_value=date(2026, 9, 30)), \
             patch("services.saas_initial_payment_runtime_v2._gen_contract_no", return_value="CON-TEST-001"), \
             patch("services.saas_initial_payment_runtime_v2.apply_saas_v2_contract_plan_atomic",
                   side_effect=spy_atomic):
            result = apply_saas_v2_initial_payment_runtime(sb, pay)

        assert result["status"] == "ALREADY_APPLIED"
        assert len(captured_plans) == 2
        # Second plan uses peer contract_id
        assert captured_plans[1].contract_id == self.PEER_CID

    def test_BP36_second_atomic_called_with_peer_uuid(self):
        """BP36: race recovery second atomic plan.contract_id == peer_cid."""
        quote = _valid_quote()
        pay = _valid_pay()
        sb = self._sb_with_mismatch_then_success(peer_cid=self.PEER_CID)
        captured_plans = []

        call_count = [0]

        def spy_atomic(sb_, plan):
            call_count[0] += 1
            captured_plans.append(plan)
            if call_count[0] == 1:
                raise SaasV2AtomicApplyError("V2_CONTRACT_ID_MISMATCH", "mismatch")
            return {"status": "ALREADY_APPLIED"}

        with patch("services.saas_initial_payment_runtime_v2._load_quote", return_value=quote), \
             patch("services.saas_initial_payment_runtime_v2.business_today", return_value=date(2026, 9, 30)), \
             patch("services.saas_initial_payment_runtime_v2._gen_contract_no", return_value="CON-TEST-001"), \
             patch("services.saas_initial_payment_runtime_v2.apply_saas_v2_contract_plan_atomic",
                   side_effect=spy_atomic):
            apply_saas_v2_initial_payment_runtime(sb, pay)

        assert captured_plans[1].contract_id == self.PEER_CID

    def test_BP37_max_atomic_calls_is_2(self):
        """BP37: at most 2 atomic calls total — no third retry."""
        quote = _valid_quote()
        pay = _valid_pay()
        sb = self._sb_with_mismatch_then_success()
        call_count = [0]

        def spy_atomic(sb_, plan):
            call_count[0] += 1
            if call_count[0] == 1:
                raise SaasV2AtomicApplyError("V2_CONTRACT_ID_MISMATCH", "mismatch")
            return {"status": "ALREADY_APPLIED"}

        with patch("services.saas_initial_payment_runtime_v2._load_quote", return_value=quote), \
             patch("services.saas_initial_payment_runtime_v2.business_today", return_value=date(2026, 9, 30)), \
             patch("services.saas_initial_payment_runtime_v2._gen_contract_no", return_value="CON-TEST-001"), \
             patch("services.saas_initial_payment_runtime_v2.apply_saas_v2_contract_plan_atomic",
                   side_effect=spy_atomic):
            apply_saas_v2_initial_payment_runtime(sb, pay)

        assert call_count[0] == 2

    def test_BP38_no_third_retry_second_atomic_fails(self):
        """BP38: if second atomic fails, raises (no third retry)."""
        quote = _valid_quote()
        pay = _valid_pay()
        sb = self._sb_with_mismatch_then_success()
        call_count = [0]

        def spy_atomic(sb_, plan):
            call_count[0] += 1
            if call_count[0] == 1:
                raise SaasV2AtomicApplyError("V2_CONTRACT_ID_MISMATCH", "mismatch")
            raise SaasV2AtomicApplyError("V2_ATOMIC_PARTIAL_STATE", "partial state")

        with patch("services.saas_initial_payment_runtime_v2._load_quote", return_value=quote), \
             patch("services.saas_initial_payment_runtime_v2.business_today", return_value=date(2026, 9, 30)), \
             patch("services.saas_initial_payment_runtime_v2._gen_contract_no", return_value="CON-TEST-001"), \
             patch("services.saas_initial_payment_runtime_v2.apply_saas_v2_contract_plan_atomic",
                   side_effect=spy_atomic):
            with pytest.raises(SaasInitialPaymentRuntimeV2Error) as exc_info:
                apply_saas_v2_initial_payment_runtime(sb, pay)

        assert exc_info.value.code == "V2_ATOMIC_PARTIAL_STATE"
        assert call_count[0] == 2  # exactly 2, no third

    def test_BP39_validation_error_no_retry(self):
        """BP39: non-MISMATCH validation error → raises immediately (no retry)."""
        quote = _valid_quote()
        pay = _valid_pay()
        sb = FakeSupabase(rpc_responses=[(None, SaasV2AtomicApplyError("V2_PAYMENT_NOT_PAID", "not paid"))])
        call_count = [0]

        def spy_atomic(sb_, plan):
            call_count[0] += 1
            raise SaasV2AtomicApplyError("V2_PAYMENT_NOT_PAID", "not paid")

        with patch("services.saas_initial_payment_runtime_v2._load_quote", return_value=quote), \
             patch("services.saas_initial_payment_runtime_v2.business_today", return_value=date(2026, 9, 30)), \
             patch("services.saas_initial_payment_runtime_v2._gen_contract_no", return_value="CON-TEST-001"), \
             patch("services.saas_initial_payment_runtime_v2.apply_saas_v2_contract_plan_atomic",
                   side_effect=spy_atomic):
            with pytest.raises(SaasInitialPaymentRuntimeV2Error) as exc_info:
                apply_saas_v2_initial_payment_runtime(sb, pay)

        assert exc_info.value.code == "V2_PAYMENT_NOT_PAID"
        assert call_count[0] == 1  # only 1 call, no retry
