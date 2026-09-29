"""BE-OBJ10-B Tests — _build_contract_row_from_payment + SaasV2ApplyPlan.

B01-B10:  _build_contract_row_from_payment unit
B11-B15:  _create_contract_from_payment V1 regression (delegates to builder)
B16-B25:  build_saas_v2_payment_success_apply_plan — quote/item/snapshot validation errors
B26-B30:  amount 3중 정합성
B31-B34:  period_months / payment_months 정합성
B35-B50:  contract_row field assertions
B51-B60:  SaasV2ApplyPlan field assertions
B61-B70:  commercial_bundle field assertions
B71-B82:  source guards
B83-B86:  PATCH1-A — payment status boundary (PAID/SUCCESS only)
B87-B88:  PATCH1-B — quote source / service boundary
B89:      PATCH1-C — legacy plan_code prohibition
B90-B92:  PATCH1-D — paid_at required + parse + effective_from
B93-B95:  PATCH1-E — user_id required + UUID + created_by
"""
from __future__ import annotations

import os
import uuid
from datetime import date

import pytest

os.environ.setdefault("INTERNAL_API_SECRET", "pytest-secret")

from services import payment_post_process as pp
from services.payment_post_process import (
    _PLAN_CODE_UNSET,
    _build_contract_row_from_payment,
    _create_contract_from_payment,
)
from services.saas_payment_success_v2_adapter import (
    SaasPaymentSuccessV2AdapterError,
    SaasV2ApplyPlan,
    _frozen_snapshot_to_calc_result,
    build_saas_v2_payment_success_apply_plan,
)

# ── Shared fixtures ───────────────────────────────────────────────────────────

COMPANY_ID = "aaaa0000-0000-0000-0000-000000000001"
QUOTE_ID = "bbbb0000-0000-0000-0000-000000000002"
PAYMENT_ID = "cccc0000-0000-0000-0000-000000000003"
ENTITY_ID = "dddd0000-0000-0000-0000-000000000004"
USER_ID = "eeee0000-0000-0000-0000-000000000005"

START = date(2026, 9, 28)
CONTRACT_NO = "CON-20260928-9999"

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


def _valid_pay(quote_id=QUOTE_ID, company_id=COMPANY_ID, payment_id=PAYMENT_ID):
    return {
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
    }


def _apply_plan(pay=None, quote=None, start=START, contract_no=CONTRACT_NO):
    return build_saas_v2_payment_success_apply_plan(
        pay or _valid_pay(),
        quote=quote or _valid_quote(),
        start=start,
        contract_no=contract_no,
    )


# ── FakeSupabase for _create_contract V1 tests ───────────────────────────────

class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, store, table, log):
        self.store = store
        self.table_name = table
        self.log = log
        self._op = None
        self._payload = None
        self._filters = []

    def insert(self, row):
        self._op = "insert"
        self._payload = row
        return self

    def update(self, patch):
        self._op = "update"
        self._payload = patch
        return self

    def select(self, *a, **k):
        self._op = "select"
        return self

    def eq(self, c, v):
        self._filters.append(("eq", c, v))
        return self

    def limit(self, n):
        return self

    def execute(self):
        if self._op == "insert":
            row = dict(self._payload)
            row.setdefault("id", str(uuid.uuid4()))
            self.store.setdefault(self.table_name, []).append(row)
            self.log.append({"op": "insert", "table": self.table_name, "row": row})
            return _Result([row])
        return _Result([])


class FakeSb:
    def __init__(self):
        self.store = {}
        self.log = []

    def table(self, name):
        return _Query(self.store, name, self.log)


# ═══════════════════════════════════════════════════════════════════════════════
# B01-B10: _build_contract_row_from_payment
# ═══════════════════════════════════════════════════════════════════════════════

class TestBuildContractRow:

    def _pay(self, **kw):
        base = {
            "id": PAYMENT_ID,
            "company_id": COMPANY_ID,
            "plan_code": "INDUSTRY_PRO",
            "period_months": 12,
            "supply_amount": 1000000,
            "vat_amount": 100000,
            "total_amount": 1100000,
            "paid_at": "2026-09-28T10:00:00+09:00",
            "quote_id": QUOTE_ID,
        }
        base.update(kw)
        return base

    def test_B01_unset_uses_pay_plan_code(self):
        row = _build_contract_row_from_payment(
            self._pay(plan_code="BUILDING_BASIC"),
            start=START,
            contract_no=CONTRACT_NO,
        )
        assert row["plan_code"] == "BUILDING_BASIC"

    def test_B02_unset_uppercases_plan_code(self):
        row = _build_contract_row_from_payment(
            self._pay(plan_code="industry_pro"),
            start=START,
            contract_no=CONTRACT_NO,
        )
        assert row["plan_code"] == "INDUSTRY_PRO"

    def test_B03_unset_absent_plan_code_defaults_to_industry_pro(self):
        pay = self._pay()
        pay.pop("plan_code")
        row = _build_contract_row_from_payment(pay, start=START, contract_no=CONTRACT_NO)
        assert row["plan_code"] == "INDUSTRY_PRO"

    def test_B04_override_none_omits_plan_code(self):
        row = _build_contract_row_from_payment(
            self._pay(),
            start=START,
            contract_no=CONTRACT_NO,
            plan_code_override=None,
        )
        assert "plan_code" not in row

    def test_B05_override_str_uses_override(self):
        row = _build_contract_row_from_payment(
            self._pay(plan_code="INDUSTRY_PRO"),
            start=START,
            contract_no=CONTRACT_NO,
            plan_code_override="CUSTOM_CODE",
        )
        assert row["plan_code"] == "CUSTOM_CODE"

    def test_B06_period_months_from_pay(self):
        row = _build_contract_row_from_payment(
            self._pay(period_months=3),
            start=date(2026, 9, 28),
            contract_no=CONTRACT_NO,
        )
        assert row["end_date"] == "2026-12-28"

    def test_B07_period_months_default_12(self):
        pay = self._pay()
        pay.pop("period_months")
        row = _build_contract_row_from_payment(pay, start=date(2026, 9, 28), contract_no=CONTRACT_NO)
        assert row["end_date"] == "2027-09-28"

    def test_B08_quote_id_passthrough(self):
        row = _build_contract_row_from_payment(self._pay(), start=START, contract_no=CONTRACT_NO)
        assert row.get("quote_id") == QUOTE_ID

    def test_B09_no_quote_id_omits_field(self):
        pay = self._pay()
        pay.pop("quote_id")
        row = _build_contract_row_from_payment(pay, start=START, contract_no=CONTRACT_NO)
        assert "quote_id" not in row

    def test_B10_amounts_from_pay(self):
        row = _build_contract_row_from_payment(self._pay(), start=START, contract_no=CONTRACT_NO)
        assert row["contract_amount"] == 1000000.0
        assert row["vat_amount"] == 100000.0
        assert row["total_amount"] == 1100000.0
        assert row["paid_amount"] == 1100000.0


# ═══════════════════════════════════════════════════════════════════════════════
# B11-B15: _create_contract_from_payment V1 regression
# ═══════════════════════════════════════════════════════════════════════════════

class TestCreateContractV1Regression:

    def _pay(self, **kw):
        base = {
            "id": PAYMENT_ID,
            "company_id": COMPANY_ID,
            "plan_code": "INDUSTRY_PRO",
            "period_months": 12,
            "supply_amount": 1000000,
            "vat_amount": 100000,
            "total_amount": 1100000,
            "paid_at": "2026-09-28T10:00:00+09:00",
        }
        base.update(kw)
        return base

    def test_B11_creates_contract_via_builder(self):
        sb = FakeSb()
        result = _create_contract_from_payment(sb, self._pay())
        assert result is not None
        inserts = [l for l in sb.log if l["table"] == "contracts"]
        assert len(inserts) == 1

    def test_B12_v1_plan_code_default_industry_pro(self):
        sb = FakeSb()
        pay = self._pay()
        pay.pop("plan_code")
        _create_contract_from_payment(sb, pay)
        row = sb.store["contracts"][0]
        assert row["plan_code"] == "INDUSTRY_PRO"

    def test_B13_v1_plan_code_from_pay(self):
        sb = FakeSb()
        _create_contract_from_payment(sb, self._pay(plan_code="BUILDING_BASIC"))
        row = sb.store["contracts"][0]
        assert row["plan_code"] == "BUILDING_BASIC"

    def test_B14_v1_period_months_applies(self):
        sb = FakeSb()
        _create_contract_from_payment(sb, self._pay(period_months=3))
        row = sb.store["contracts"][0]
        end = row["end_date"]
        start = row["start_date"]
        from dateutil.relativedelta import relativedelta
        from datetime import date as d
        start_d = d.fromisoformat(start)
        assert d.fromisoformat(end) == start_d + relativedelta(months=3)

    def test_B15_v1_quote_id_passthrough(self):
        sb = FakeSb()
        _create_contract_from_payment(sb, self._pay() | {"quote_id": QUOTE_ID})
        row = sb.store["contracts"][0]
        assert row["quote_id"] == QUOTE_ID


# ═══════════════════════════════════════════════════════════════════════════════
# B16-B25: build_saas_v2_payment_success_apply_plan validation errors
# ═══════════════════════════════════════════════════════════════════════════════

class TestApplyPlanValidation:

    def test_B16_product_type_not_saas_rejected(self):
        pay = _valid_pay()
        pay["product_type"] = "SAAS_INDUSTRY"
        with pytest.raises(SaasPaymentSuccessV2AdapterError) as exc:
            _apply_plan(pay=pay)
        assert exc.value.code == "PAY_NOT_SAAS_V2"

    def test_B17_no_company_id_rejected(self):
        pay = _valid_pay()
        pay["company_id"] = ""
        with pytest.raises(SaasPaymentSuccessV2AdapterError) as exc:
            _apply_plan(pay=pay)
        assert exc.value.code == "PAY_NO_COMPANY_ID"

    def test_B18_company_id_mismatch_rejected(self):
        pay = _valid_pay(company_id="ffff0000-0000-0000-0000-000000000099")
        with pytest.raises(SaasPaymentSuccessV2AdapterError) as exc:
            _apply_plan(pay=pay)
        assert exc.value.code == "PAY_QUOTE_COMPANY_MISMATCH"

    def test_B19_quote_not_issued_rejected(self):
        quote = _valid_quote()
        quote["status_code"] = "DRAFT"
        with pytest.raises(SaasPaymentSuccessV2AdapterError) as exc:
            _apply_plan(quote=quote)
        assert exc.value.code == "QUOTE_NOT_ISSUED"

    def test_B20_no_quote_id_in_pay_rejected(self):
        pay = _valid_pay()
        pay.pop("quote_id")
        with pytest.raises(SaasPaymentSuccessV2AdapterError) as exc:
            _apply_plan(pay=pay)
        assert exc.value.code == "PAY_NO_QUOTE_ID"

    def test_B21_quote_id_mismatch_rejected(self):
        pay = _valid_pay(quote_id="eeee0000-0000-0000-0000-000000000099")
        with pytest.raises(SaasPaymentSuccessV2AdapterError) as exc:
            _apply_plan(pay=pay)
        assert exc.value.code == "PAY_QUOTE_ID_MISMATCH"

    def test_B22_zero_items_rejected(self):
        quote = _valid_quote()
        quote["items"] = []
        with pytest.raises(SaasPaymentSuccessV2AdapterError) as exc:
            _apply_plan(quote=quote)
        assert exc.value.code == "QUOTE_ITEM_COUNT_INVALID"

    def test_B23_two_items_rejected(self):
        quote = _valid_quote()
        quote["items"] = [dict(_ITEM_DICT), dict(_ITEM_DICT)]
        with pytest.raises(SaasPaymentSuccessV2AdapterError) as exc:
            _apply_plan(quote=quote)
        assert exc.value.code == "QUOTE_ITEM_COUNT_INVALID"

    def test_B24_wrong_schema_version_rejected(self):
        quote = _valid_quote()
        item = dict(_ITEM_DICT)
        item["quote_schema_version"] = "SAAS_QUOTE_V1"
        quote["items"] = [item]
        with pytest.raises(SaasPaymentSuccessV2AdapterError) as exc:
            _apply_plan(quote=quote)
        assert exc.value.code == "QUOTE_NOT_V2"

    def test_B25_invalid_item_rejected(self):
        quote = _valid_quote()
        item = dict(_ITEM_DICT)
        item["supply_amount"] = "NOT_A_NUMBER"
        quote["items"] = [item]
        with pytest.raises(SaasPaymentSuccessV2AdapterError) as exc:
            _apply_plan(quote=quote)
        assert exc.value.code == "QUOTE_ITEM_INVALID"


# ═══════════════════════════════════════════════════════════════════════════════
# B26-B30: amount 3중 정합성
# ═══════════════════════════════════════════════════════════════════════════════

class TestAmountCrossValidation:

    def test_B26_pay_supply_mismatch_item_rejected(self):
        pay = _valid_pay()
        pay["supply_amount"] = 9999999
        with pytest.raises(SaasPaymentSuccessV2AdapterError) as exc:
            _apply_plan(pay=pay)
        assert exc.value.code == "AMOUNT_SNAPSHOT_MISMATCH"
        assert "supply_amount" in exc.value.message

    def test_B27_item_supply_mismatch_snap_rejected(self):
        quote = _valid_quote()
        item = dict(_ITEM_DICT)
        item["supply_amount"] = 9999999
        item["pricing_snapshot"] = dict(_SNAP_DICT)
        quote["items"] = [item]
        pay = _valid_pay()
        pay["supply_amount"] = 9999999
        with pytest.raises(SaasPaymentSuccessV2AdapterError) as exc:
            _apply_plan(pay=pay, quote=quote)
        assert exc.value.code == "AMOUNT_SNAPSHOT_MISMATCH"

    def test_B28_vat_mismatch_rejected(self):
        pay = _valid_pay()
        pay["vat_amount"] = 9999999
        with pytest.raises(SaasPaymentSuccessV2AdapterError) as exc:
            _apply_plan(pay=pay)
        assert exc.value.code == "AMOUNT_SNAPSHOT_MISMATCH"
        assert "vat_amount" in exc.value.message

    def test_B29_total_mismatch_rejected(self):
        pay = _valid_pay()
        pay["total_amount"] = 9999999
        with pytest.raises(SaasPaymentSuccessV2AdapterError) as exc:
            _apply_plan(pay=pay)
        assert exc.value.code == "AMOUNT_SNAPSHOT_MISMATCH"
        assert "total_amount" in exc.value.message

    def test_B30_all_match_passes(self):
        plan = _apply_plan()
        assert plan is not None


# ═══════════════════════════════════════════════════════════════════════════════
# B31-B34: period_months / payment_months 정합성
# ═══════════════════════════════════════════════════════════════════════════════

class TestPeriodTermConsistency:

    def test_B31_period_term_mismatch_rejected(self):
        pay = _valid_pay()
        pay["period_months"] = 3
        with pytest.raises(SaasPaymentSuccessV2AdapterError) as exc:
            _apply_plan(pay=pay)
        assert exc.value.code == "PAY_PERIOD_TERM_MISMATCH"

    def test_B32_period_absent_treated_as_zero_mismatch(self):
        pay = _valid_pay()
        pay.pop("period_months")
        with pytest.raises(SaasPaymentSuccessV2AdapterError) as exc:
            _apply_plan(pay=pay)
        assert exc.value.code == "PAY_PERIOD_TERM_MISMATCH"

    def test_B33_period_equals_term_passes(self):
        pay = _valid_pay()
        pay["period_months"] = _SNAP_DICT["payment_months"]
        plan = _apply_plan(pay=pay)
        assert plan is not None

    def test_B34_end_date_uses_payment_months(self):
        plan = _apply_plan()
        from dateutil.relativedelta import relativedelta
        expected_end = (START + relativedelta(months=_SNAP_DICT["payment_months"])).isoformat()
        assert plan.contract_row["end_date"] == expected_end


# ═══════════════════════════════════════════════════════════════════════════════
# B35-B50: contract_row field assertions
# ═══════════════════════════════════════════════════════════════════════════════

class TestContractRowFields:

    def setup_method(self):
        self.plan = _apply_plan()
        self.row = self.plan.contract_row

    def test_B35_company_id(self):
        assert self.row["company_id"] == COMPANY_ID

    def test_B36_status_code_active(self):
        assert self.row["status_code"] == "ACTIVE"

    def test_B37_service_type_saas(self):
        assert self.row["service_type"] == "SAAS"

    def test_B38_plan_code_absent_v2(self):
        assert "plan_code" not in self.row

    def test_B39_contract_amount_from_snapshot_supply(self):
        assert self.row["contract_amount"] == float(_SNAP_DICT["prepaid_supply_amount"])

    def test_B40_vat_amount_from_snapshot(self):
        assert self.row["vat_amount"] == float(_SNAP_DICT["vat_amount"])

    def test_B41_total_amount_from_snapshot(self):
        assert self.row["total_amount"] == float(_SNAP_DICT["total_amount"])

    def test_B42_paid_amount_equals_total(self):
        assert self.row["paid_amount"] == self.row["total_amount"]

    def test_B43_is_active_true(self):
        assert self.row["is_active"] is True

    def test_B44_start_date(self):
        assert self.row["start_date"] == START.isoformat()

    def test_B45_end_date_12_months(self):
        assert self.row["end_date"] == "2027-09-28"

    def test_B46_contract_no(self):
        assert self.row["contract_no"] == CONTRACT_NO

    def test_B47_quote_id_present(self):
        assert self.row["quote_id"] == QUOTE_ID

    def test_B48_id_is_str_uuid(self):
        assert uuid.UUID(self.row["id"]) is not None

    def test_B49_id_matches_plan_contract_id(self):
        assert self.row["id"] == str(self.plan.contract_id)

    def test_B50_memo_includes_payment_id_prefix(self):
        assert PAYMENT_ID[:8] in self.row["memo"]


# ═══════════════════════════════════════════════════════════════════════════════
# B51-B60: SaasV2ApplyPlan field assertions
# ═══════════════════════════════════════════════════════════════════════════════

class TestApplyPlanFields:

    def setup_method(self):
        self.plan = _apply_plan()

    def test_B51_payment_id(self):
        assert self.plan.payment_id == PAYMENT_ID

    def test_B52_company_id(self):
        assert self.plan.company_id == COMPANY_ID

    def test_B53_contract_id_is_uuid(self):
        assert isinstance(self.plan.contract_id, uuid.UUID)

    def test_B54_contract_id_matches_row(self):
        assert str(self.plan.contract_id) == self.plan.contract_row["id"]

    def test_B55_commercial_bundle_present(self):
        from schemas.saas_contract_commercial_v2 import SaasContractStorageBundleV2
        assert isinstance(self.plan.commercial_bundle, SaasContractStorageBundleV2)

    def test_B56_each_call_generates_different_contract_id(self):
        plan2 = _apply_plan()
        assert self.plan.contract_id != plan2.contract_id

    def test_B57_payment_id_from_pay_id(self):
        pay = _valid_pay(payment_id="eeee0000-0000-0000-0000-000000000007")
        plan = _apply_plan(pay=pay)
        assert plan.payment_id == "eeee0000-0000-0000-0000-000000000007"

    def test_B58_company_id_from_pay_not_quote(self):
        assert self.plan.company_id == COMPANY_ID

    def test_B59_is_dataclass(self):
        import dataclasses
        assert dataclasses.is_dataclass(self.plan)

    def test_B60_no_supabase_used(self):
        # builder 호출 시 supabase 인수 없음 — DB I/O 0 검증
        import inspect
        from services import saas_payment_success_v2_adapter as mod
        src = inspect.getsource(mod.build_saas_v2_payment_success_apply_plan)
        assert "supabase" not in src
        assert "get_supabase" not in src


# ═══════════════════════════════════════════════════════════════════════════════
# B61-B70: commercial_bundle field assertions
# ═══════════════════════════════════════════════════════════════════════════════

class TestCommercialBundle:

    def setup_method(self):
        self.plan = _apply_plan()
        self.cv = self.plan.commercial_bundle.commercial_version
        self.scopes = self.plan.commercial_bundle.site_scopes

    def test_B61_product_tier_from_snapshot(self):
        assert self.cv.product_tier == _SNAP_DICT["product_tier"]

    def test_B62_pricing_mode_from_snapshot(self):
        assert self.cv.pricing_mode == _SNAP_DICT["pricing_mode"]

    def test_B63_worker_capacity_from_snapshot(self):
        assert self.cv.worker_capacity == _SNAP_DICT["worker"]["capacity"]

    def test_B64_payment_months_from_snapshot(self):
        assert self.cv.payment_months == _SNAP_DICT["payment_months"]

    def test_B65_version_no_is_one(self):
        assert self.cv.version_no == 1

    def test_B66_pricing_result_status_ready(self):
        assert self.cv.pricing_result_status == "READY"

    def test_B67_pricing_policy_version_from_snapshot(self):
        assert self.cv.pricing_policy_version == _SNAP_DICT["policy_version"]

    def test_B68_pricing_snapshot_populated(self):
        assert self.cv.pricing_snapshot is not None

    def test_B69_contract_id_matches_plan(self):
        assert self.cv.contract_id == self.plan.contract_id

    def test_B70_site_scopes_count_matches_snapshot_sites(self):
        assert len(self.scopes) == len(_SNAP_DICT["sites"])


# ═══════════════════════════════════════════════════════════════════════════════
# B71-B82: source guards
# ═══════════════════════════════════════════════════════════════════════════════

class TestSourceGuards:

    def _src(self):
        import inspect
        from services import saas_payment_success_v2_adapter as mod
        return inspect.getsource(mod)

    def test_B71_no_add_vat_in_adapter(self):
        assert "add_vat(" not in self._src()

    def test_B72_no_split_supply_vat_in_adapter(self):
        assert "split_supply_vat(" not in self._src()

    def test_B73_no_vat_multiplication_in_adapter(self):
        assert "* 0.1" not in self._src()

    def test_B74_no_price_master_in_adapter(self):
        assert "price_master" not in self._src()

    def test_B75_no_pricing_resolver_in_adapter(self):
        assert "pricing_resolver" not in self._src()

    def test_B76_no_contracts_write_in_adapter(self):
        assert '"contracts"' not in self._src()

    def test_B77_no_commercial_versions_write_in_adapter(self):
        assert '"saas_contract_commercial_versions"' not in self._src()

    def test_B78_no_subscriptions_in_adapter(self):
        assert '"subscriptions"' not in self._src()

    def test_B79_no_routers_import_in_adapter(self):
        assert "routers" not in self._src()

    def test_B80_product_type_guard_exact_saas(self):
        pay = _valid_pay()
        pay["product_type"] = "SAAS_CONSTRUCTION"
        with pytest.raises(SaasPaymentSuccessV2AdapterError) as exc:
            _apply_plan(pay=pay)
        assert exc.value.code == "PAY_NOT_SAAS_V2"

    def test_B81_amount_guard_is_3way_not_2way(self):
        # pay == snap, item != snap → still caught (3-way, not 2-way)
        quote = _valid_quote()
        item = dict(_ITEM_DICT)
        item["supply_amount"] = 9999999
        quote["items"] = [item]
        with pytest.raises(SaasPaymentSuccessV2AdapterError) as exc:
            _apply_plan(quote=quote)
        assert exc.value.code == "AMOUNT_SNAPSHOT_MISMATCH"

    def test_B82_frozen_snapshot_to_calc_has_ready_status(self):
        from schemas.saas_pricing_v2 import SaasPricingSnapshotV2
        snap = SaasPricingSnapshotV2.model_validate(_SNAP_DICT)
        calc = _frozen_snapshot_to_calc_result(snap)
        assert calc.status == "READY"
        assert calc.snapshot == snap
        assert calc.snapshot.prepaid_supply_amount == _SNAP_DICT["prepaid_supply_amount"]


# ═══════════════════════════════════════════════════════════════════════════════
# B83-B86: PATCH1-A — Payment status boundary
# ═══════════════════════════════════════════════════════════════════════════════

class TestPaymentStatusBoundary:

    def test_B83_pending_payment_rejected(self):
        pay = _valid_pay()
        pay["status_code"] = "PENDING"
        with pytest.raises(SaasPaymentSuccessV2AdapterError) as exc:
            _apply_plan(pay=pay)
        assert exc.value.code == "V2_PAYMENT_NOT_PAID"

    def test_B84_failed_payment_rejected(self):
        pay = _valid_pay()
        pay["status_code"] = "FAILED"
        with pytest.raises(SaasPaymentSuccessV2AdapterError) as exc:
            _apply_plan(pay=pay)
        assert exc.value.code == "V2_PAYMENT_NOT_PAID"

    def test_B85_success_status_accepted(self):
        pay = _valid_pay()
        pay["status_code"] = "SUCCESS"
        plan = _apply_plan(pay=pay)
        assert plan is not None

    def test_B86_paid_status_accepted(self):
        pay = _valid_pay()
        pay["status_code"] = "PAID"
        plan = _apply_plan(pay=pay)
        assert plan is not None


# ═══════════════════════════════════════════════════════════════════════════════
# B87-B88: PATCH1-B — Quote source / service boundary
# ═══════════════════════════════════════════════════════════════════════════════

class TestQuoteSourceServiceBoundary:

    def test_B87_member_custom_source_rejected(self):
        quote = _valid_quote()
        quote["source"] = "member_custom"
        with pytest.raises(SaasPaymentSuccessV2AdapterError) as exc:
            _apply_plan(quote=quote)
        assert exc.value.code == "V2_QUOTE_SOURCE_INVALID"

    def test_B88_non_saas_service_type_rejected(self):
        quote = _valid_quote()
        quote["service_type"] = "DIAGNOSIS"
        with pytest.raises(SaasPaymentSuccessV2AdapterError) as exc:
            _apply_plan(quote=quote)
        assert exc.value.code == "V2_QUOTE_SERVICE_INVALID"


# ═══════════════════════════════════════════════════════════════════════════════
# B89: PATCH1-C — Legacy plan_code prohibition
# ═══════════════════════════════════════════════════════════════════════════════

class TestLegacyPlanCodeProhibition:

    def test_B89_non_none_plan_code_rejected(self):
        pay = _valid_pay()
        pay["plan_code"] = "INDUSTRY_PRO"
        with pytest.raises(SaasPaymentSuccessV2AdapterError) as exc:
            _apply_plan(pay=pay)
        assert exc.value.code == "V2_LEGACY_PLAN_CODE_FORBIDDEN"


# ═══════════════════════════════════════════════════════════════════════════════
# B90-B92: PATCH1-D — paid_at required + parse + effective_from
# ═══════════════════════════════════════════════════════════════════════════════

class TestPaidAtBoundary:

    def test_B90_missing_paid_at_rejected(self):
        pay = _valid_pay()
        pay.pop("paid_at")
        with pytest.raises(SaasPaymentSuccessV2AdapterError) as exc:
            _apply_plan(pay=pay)
        assert exc.value.code == "V2_PAID_AT_REQUIRED"

    def test_B91_malformed_paid_at_rejected(self):
        pay = _valid_pay()
        pay["paid_at"] = "not-a-valid-timestamp"
        with pytest.raises(SaasPaymentSuccessV2AdapterError) as exc:
            _apply_plan(pay=pay)
        assert exc.value.code == "V2_PAID_AT_INVALID"

    def test_B92_paid_at_becomes_commercial_effective_from(self):
        from dateutil import parser as dp
        paid_at_str = "2026-09-28T10:00:00+09:00"
        pay = _valid_pay()
        pay["paid_at"] = paid_at_str
        plan = _apply_plan(pay=pay)
        expected = dp.isoparse(paid_at_str)
        assert plan.commercial_bundle.commercial_version.effective_from == expected


# ═══════════════════════════════════════════════════════════════════════════════
# B93-B95: PATCH1-E — user_id required + UUID + created_by
# ═══════════════════════════════════════════════════════════════════════════════

class TestUserIdBoundary:

    def test_B93_missing_user_id_rejected(self):
        pay = _valid_pay()
        pay.pop("user_id")
        with pytest.raises(SaasPaymentSuccessV2AdapterError) as exc:
            _apply_plan(pay=pay)
        assert exc.value.code == "V2_USER_REQUIRED"

    def test_B94_invalid_uuid_user_id_rejected(self):
        pay = _valid_pay()
        pay["user_id"] = "not-a-uuid"
        with pytest.raises(SaasPaymentSuccessV2AdapterError) as exc:
            _apply_plan(pay=pay)
        assert exc.value.code == "V2_USER_INVALID"

    def test_B95_user_id_becomes_commercial_created_by(self):
        plan = _apply_plan()
        assert plan.commercial_bundle.commercial_version.created_by == uuid.UUID(USER_ID)
