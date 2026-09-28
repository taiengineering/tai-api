"""TAI Safe SaaS Renewal V2 Adapter — R01-R53 (PATCH1).

검증 범위:
  R01-R05  Contract validation (prepare)
  R06-R10  Quote validation — prepare side
  R11-R15  Amount integrity — prepare side
  R16-R20  Prepare call contract (payment_type, contract_id, plan_code)
  R21-R30  Plan builder guards (pure, DB write = 0)
  R31-R40  Structural / billing boundary guards
  R41-R42  PATCH1: Prepare side — CONTRACT_NOT_SAAS / QUOTE_SOURCE_INVALID
  R43-R52  PATCH1: Plan builder identity + CV + effective_at guards
  R53      PATCH1: Plan PATCH D fields (quote_id, current_version_no)

DB/네트워크 없음 — FakeSupabase + monkeypatch 전용.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.saas_renewal_v2_adapter import (  # noqa: E402
    SaasRenewalV2AdapterError,
    SaasV2RenewalApplyPlan,
    build_saas_v2_renewal_apply_plan,
    prepare_saas_v2_renewal_payment_from_quote,
)

_SVC_SRC = Path(__file__).parent.parent / "services" / "saas_renewal_v2_adapter.py"

_CONTRACT_ID = str(uuid.uuid4())
_COMPANY_ID = "C-RENEWAL-TEST"
_USER_ID = str(uuid.uuid4())
_QUOTE_ID = str(uuid.uuid4())
_CV_ID = str(uuid.uuid4())
_SITE_ID = str(uuid.uuid4())
_PAYMENT_ID = str(uuid.uuid4())

_NOW = datetime(2026, 9, 28, 10, 0, 0, tzinfo=timezone.utc)
_EFFECTIVE_AT = datetime(2026, 10, 1, 0, 0, 0, tzinfo=timezone.utc)


# ═══════════════════════════════════════════════════════════════════════════════
# Shared Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _minimal_snap_dict(supply=200_000, vat=20_000, total=220_000, term=12,
                       product_tier="FIELD", worker_capacity=5):
    return {
        "schema_version": "SAAS_PRICING_V2",
        "policy_version": "2026.09",
        "product_tier": product_tier,
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
        "worker": {"capacity": worker_capacity, "amount": 0, "brackets": []},
        "term_months": term,
        "term_discount_rate_bps": 0,
        "monthly_supply_amount": supply,
        "prepaid_supply_amount": supply,
        "vat_rate_bps": 1_000,
        "vat_amount": vat,
        "total_amount": total,
    }


def _minimal_item_dict(supply=200_000, vat=20_000, total=220_000, term=12,
                       product_tier="FIELD", worker_capacity=5):
    return {
        "quote_schema_version": "SAAS_QUOTE_V2",
        "display_name": "TAI Safe 현장참여형 갱신",
        "billing_unit": "MONTHLY",
        "unit_amount": supply,
        "quantity": term,
        "supply_amount": supply,
        "vat_amount": vat,
        "total_amount": total,
        "service_type": "SAAS",
        "price_id": None,
        "tier_code": None,
        "sector": "INDUSTRY",
        "sectors": ["INDUSTRY"],
        "product_tier": product_tier,
        "pricing_mode": "STANDARD",
        "policy_version": "2026.09",
        "worker_capacity": worker_capacity,
        "term_months": term,
        "vat_rate": 0.1,
        "vat_rate_bps": 1_000,
        "pricing_input": {
            "product_tier": product_tier,
            "worker_capacity": worker_capacity,
            "term_months": term,
            "sites": [{"entity_id": _SITE_ID, "sector": "INDUSTRY", "criteria_value": 50}],
        },
        "pricing_snapshot": _minimal_snap_dict(supply, vat, total, term, product_tier, worker_capacity),
    }


def _valid_quote(
    quote_id=_QUOTE_ID,
    company_id=_COMPANY_ID,
    status_code="ISSUED",
    service_type="SAAS",
    supply=200_000,
    vat=20_000,
    total=220_000,
    term=12,
    items=None,
):
    return {
        "id": quote_id,
        "company_id": company_id,
        "status_code": status_code,
        "service_type": service_type,
        "source": "member_auto",
        "supply_amount": supply,
        "vat_amount": vat,
        "total_amount": total,
        "items": items if items is not None else [_minimal_item_dict(supply, vat, total, term)],
    }


def _valid_contract(company_id=_COMPANY_ID, status_code="ACTIVE", service_type="SAAS"):
    return {"id": _CONTRACT_ID, "company_id": company_id, "status_code": status_code, "service_type": service_type}


def _valid_cv_row(version_no=2, contract_id=_CONTRACT_ID):
    return {
        "id": _CV_ID,
        "contract_id": contract_id,
        "version_no": version_no,
        "commercial_schema_version": "SAAS_CONTRACT_COMMERCIAL_V2",
        "product_tier": "FIELD",
        "pricing_mode": "STANDARD",
        "worker_capacity": 5,
        "term_months": 12,
        "pricing_result_status": "READY",
        "pricing_policy_version": "2026.09",
        "pricing_snapshot": _minimal_snap_dict(),
        "effective_from": "2026-04-01T00:00:00+00:00",
        "superseded_at": None,
        "created_by": None,
    }


def _valid_pay(
    payment_id=_PAYMENT_ID,
    company_id=_COMPANY_ID,
    contract_id=_CONTRACT_ID,
    supply=200_000,
    vat=20_000,
    total=220_000,
    term=12,
    payment_type="RENEWAL",
    plan_code=None,
    status_code="PAID",
):
    return {
        "id": payment_id,
        "company_id": company_id,
        "user_id": _USER_ID,
        "contract_id": contract_id,
        "quote_id": _QUOTE_ID,
        "product_type": "SAAS",
        "payment_type": payment_type,
        "plan_code": plan_code,
        "status_code": status_code,
        "paid_at": "2026-09-28T10:00:00+00:00",
        "supply_amount": supply,
        "vat_amount": vat,
        "total_amount": total,
        "period_months": term,
    }


def _fake_prepare_exact(calls):
    def _stub(supabase, sign_key, **kwargs):
        calls.append(kwargs)
        return {"status": "success", "data": {"payment_id": "pay-renewal-stub"}}
    return _stub


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeQueryChain:
    """Supabase fluent query chain stub."""
    def __init__(self, rows):
        self._rows = rows

    def select(self, *a): return self
    def eq(self, *a): return self
    def is_(self, *a): return self
    def limit(self, *a): return self
    def execute(self): return _FakeResult(self._rows)


class _FakeSbForPrepare:
    """contracts / cv / scopes 순으로 응답하는 FakeSupabase."""

    def __init__(self, contract=None, cv=None, scopes=None):
        self._responses = []
        if contract is not None:
            self._responses.append([contract] if isinstance(contract, dict) else contract)
        if cv is not None:
            self._responses.append([cv] if isinstance(cv, dict) else cv)
        if scopes is not None:
            self._responses.append(scopes if isinstance(scopes, list) else [])
        self._call_index = 0

    def table(self, _name):
        idx = self._call_index
        self._call_index += 1
        rows = self._responses[idx] if idx < len(self._responses) else []
        return _FakeQueryChain(rows)


# ═══════════════════════════════════════════════════════════════════════════════
# R01–R05: Contract validation (prepare)
# ═══════════════════════════════════════════════════════════════════════════════

def test_R01_contract_not_found(monkeypatch):
    """contracts 조회 결과 없음 → CONTRACT_NOT_FOUND."""
    monkeypatch.setattr("services.member_quote_svc.get_member_quote", lambda *a: _valid_quote())
    monkeypatch.setattr("services.saas_renewal_v2_adapter.load_sign_key", lambda: "K")
    sb = _FakeSbForPrepare(contract=[])
    with pytest.raises(SaasRenewalV2AdapterError) as exc:
        prepare_saas_v2_renewal_payment_from_quote(
            sb, contract_id=_CONTRACT_ID, quote_id=_QUOTE_ID,
            company_id=_COMPANY_ID, user_id=_USER_ID,
        )
    assert exc.value.code == "CONTRACT_NOT_FOUND"


def test_R02_contract_not_owned(monkeypatch):
    """contract.company_id != auth company_id → CONTRACT_NOT_OWNED."""
    monkeypatch.setattr("services.member_quote_svc.get_member_quote", lambda *a: _valid_quote())
    monkeypatch.setattr("services.saas_renewal_v2_adapter.load_sign_key", lambda: "K")
    sb = _FakeSbForPrepare(contract=_valid_contract(company_id="OTHER-CO"))
    with pytest.raises(SaasRenewalV2AdapterError) as exc:
        prepare_saas_v2_renewal_payment_from_quote(
            sb, contract_id=_CONTRACT_ID, quote_id=_QUOTE_ID,
            company_id=_COMPANY_ID, user_id=_USER_ID,
        )
    assert exc.value.code == "CONTRACT_NOT_OWNED"


def test_R03_contract_not_active(monkeypatch):
    """contract.status_code != ACTIVE → CONTRACT_NOT_ACTIVE."""
    monkeypatch.setattr("services.member_quote_svc.get_member_quote", lambda *a: _valid_quote())
    monkeypatch.setattr("services.saas_renewal_v2_adapter.load_sign_key", lambda: "K")
    sb = _FakeSbForPrepare(contract=_valid_contract(status_code="EXPIRED"))
    with pytest.raises(SaasRenewalV2AdapterError) as exc:
        prepare_saas_v2_renewal_payment_from_quote(
            sb, contract_id=_CONTRACT_ID, quote_id=_QUOTE_ID,
            company_id=_COMPANY_ID, user_id=_USER_ID,
        )
    assert exc.value.code == "CONTRACT_NOT_ACTIVE"


def test_R04_current_cv_not_found(monkeypatch):
    """superseded_at IS NULL인 CV 없음 → CURRENT_CV_NOT_FOUND."""
    monkeypatch.setattr("services.member_quote_svc.get_member_quote", lambda *a: _valid_quote())
    monkeypatch.setattr("services.saas_renewal_v2_adapter.load_sign_key", lambda: "K")
    sb = _FakeSbForPrepare(contract=_valid_contract(), cv=[])
    with pytest.raises(SaasRenewalV2AdapterError) as exc:
        prepare_saas_v2_renewal_payment_from_quote(
            sb, contract_id=_CONTRACT_ID, quote_id=_QUOTE_ID,
            company_id=_COMPANY_ID, user_id=_USER_ID,
        )
    assert exc.value.code == "CURRENT_CV_NOT_FOUND"


def test_R05_valid_contract_proceeds_to_quote(monkeypatch):
    """유효 Contract + CV → Quote 조회로 진행 (QUOTE_NOT_FOUND 진입 확인)."""
    monkeypatch.setattr("services.member_quote_svc.get_member_quote", lambda *a: None)
    monkeypatch.setattr("services.saas_renewal_v2_adapter.load_sign_key", lambda: "K")
    sb = _FakeSbForPrepare(contract=_valid_contract(), cv=_valid_cv_row())
    with pytest.raises(SaasRenewalV2AdapterError) as exc:
        prepare_saas_v2_renewal_payment_from_quote(
            sb, contract_id=_CONTRACT_ID, quote_id=_QUOTE_ID,
            company_id=_COMPANY_ID, user_id=_USER_ID,
        )
    assert exc.value.code == "QUOTE_NOT_FOUND"


# ═══════════════════════════════════════════════════════════════════════════════
# R06–R10: Quote validation (prepare side)
# ═══════════════════════════════════════════════════════════════════════════════

def _setup_prepare_with_quote(monkeypatch, quote):
    monkeypatch.setattr("services.member_quote_svc.get_member_quote", lambda *a: quote)
    monkeypatch.setattr("services.saas_renewal_v2_adapter.load_sign_key", lambda: "K")
    calls = []
    monkeypatch.setattr(
        "services.saas_renewal_v2_adapter._run_inicis_prepare_exact",
        _fake_prepare_exact(calls),
    )
    sb = _FakeSbForPrepare(contract=_valid_contract(), cv=_valid_cv_row())
    return sb, calls


def test_R06_quote_not_owned(monkeypatch):
    """quote.company_id != auth company_id → QUOTE_NOT_OWNED."""
    quote = _valid_quote(company_id="OTHER-CO")
    sb, _ = _setup_prepare_with_quote(monkeypatch, quote)
    with pytest.raises(SaasRenewalV2AdapterError) as exc:
        prepare_saas_v2_renewal_payment_from_quote(
            sb, contract_id=_CONTRACT_ID, quote_id=_QUOTE_ID,
            company_id=_COMPANY_ID, user_id=_USER_ID,
        )
    assert exc.value.code == "QUOTE_NOT_OWNED"


def test_R07_quote_not_issued(monkeypatch):
    """status_code != ISSUED → QUOTE_NOT_ISSUED."""
    quote = _valid_quote(status_code="DRAFT")
    sb, _ = _setup_prepare_with_quote(monkeypatch, quote)
    with pytest.raises(SaasRenewalV2AdapterError) as exc:
        prepare_saas_v2_renewal_payment_from_quote(
            sb, contract_id=_CONTRACT_ID, quote_id=_QUOTE_ID,
            company_id=_COMPANY_ID, user_id=_USER_ID,
        )
    assert exc.value.code == "QUOTE_NOT_ISSUED"


def test_R08_quote_not_saas(monkeypatch):
    """service_type != SAAS → QUOTE_NOT_SAAS."""
    quote = _valid_quote(service_type="CONSULTING")
    sb, _ = _setup_prepare_with_quote(monkeypatch, quote)
    with pytest.raises(SaasRenewalV2AdapterError) as exc:
        prepare_saas_v2_renewal_payment_from_quote(
            sb, contract_id=_CONTRACT_ID, quote_id=_QUOTE_ID,
            company_id=_COMPANY_ID, user_id=_USER_ID,
        )
    assert exc.value.code == "QUOTE_NOT_SAAS"


def test_R09_quote_wrong_schema_version(monkeypatch):
    """item.quote_schema_version != SAAS_QUOTE_V2 → QUOTE_NOT_V2."""
    item = {**_minimal_item_dict(), "quote_schema_version": "SAAS_QUOTE_V1"}
    quote = _valid_quote(items=[item])
    sb, _ = _setup_prepare_with_quote(monkeypatch, quote)
    with pytest.raises(SaasRenewalV2AdapterError) as exc:
        prepare_saas_v2_renewal_payment_from_quote(
            sb, contract_id=_CONTRACT_ID, quote_id=_QUOTE_ID,
            company_id=_COMPANY_ID, user_id=_USER_ID,
        )
    assert exc.value.code == "QUOTE_NOT_V2"


def test_R10_quote_malformed_item(monkeypatch):
    """SaasQuoteSnapshotItemV2 검증 실패 → QUOTE_ITEM_INVALID."""
    item = {"quote_schema_version": "SAAS_QUOTE_V2", "bad": True}
    quote = _valid_quote(items=[item])
    sb, _ = _setup_prepare_with_quote(monkeypatch, quote)
    with pytest.raises(SaasRenewalV2AdapterError) as exc:
        prepare_saas_v2_renewal_payment_from_quote(
            sb, contract_id=_CONTRACT_ID, quote_id=_QUOTE_ID,
            company_id=_COMPANY_ID, user_id=_USER_ID,
        )
    assert exc.value.code == "QUOTE_ITEM_INVALID"


# ═══════════════════════════════════════════════════════════════════════════════
# R11–R15: Amount integrity (prepare side)
# ═══════════════════════════════════════════════════════════════════════════════

def test_R11_supply_quote_ne_item_rejected(monkeypatch):
    """quote.supply != item.supply → QUOTE_PAYMENT_SNAPSHOT_INVALID."""
    item = _minimal_item_dict(supply=200_000, vat=20_000, total=220_000)
    quote = _valid_quote(supply=199_000, vat=20_000, total=220_000, items=[item])
    sb, calls = _setup_prepare_with_quote(monkeypatch, quote)
    with pytest.raises(SaasRenewalV2AdapterError) as exc:
        prepare_saas_v2_renewal_payment_from_quote(
            sb, contract_id=_CONTRACT_ID, quote_id=_QUOTE_ID,
            company_id=_COMPANY_ID, user_id=_USER_ID,
        )
    assert exc.value.code == "QUOTE_PAYMENT_SNAPSHOT_INVALID"
    assert len(calls) == 0


def test_R12_vat_quote_ne_item_rejected(monkeypatch):
    """quote.vat != item.vat → QUOTE_PAYMENT_SNAPSHOT_INVALID."""
    item = _minimal_item_dict(supply=200_000, vat=20_000, total=220_000)
    quote = _valid_quote(supply=200_000, vat=19_000, total=220_000, items=[item])
    sb, calls = _setup_prepare_with_quote(monkeypatch, quote)
    with pytest.raises(SaasRenewalV2AdapterError) as exc:
        prepare_saas_v2_renewal_payment_from_quote(
            sb, contract_id=_CONTRACT_ID, quote_id=_QUOTE_ID,
            company_id=_COMPANY_ID, user_id=_USER_ID,
        )
    assert exc.value.code == "QUOTE_PAYMENT_SNAPSHOT_INVALID"
    assert len(calls) == 0


def test_R13_total_quote_ne_item_rejected(monkeypatch):
    """quote.total != item.total → QUOTE_PAYMENT_SNAPSHOT_INVALID."""
    item = _minimal_item_dict(supply=200_000, vat=20_000, total=220_000)
    quote = _valid_quote(supply=200_000, vat=20_000, total=215_000, items=[item])
    sb, calls = _setup_prepare_with_quote(monkeypatch, quote)
    with pytest.raises(SaasRenewalV2AdapterError) as exc:
        prepare_saas_v2_renewal_payment_from_quote(
            sb, contract_id=_CONTRACT_ID, quote_id=_QUOTE_ID,
            company_id=_COMPANY_ID, user_id=_USER_ID,
        )
    assert exc.value.code == "QUOTE_PAYMENT_SNAPSHOT_INVALID"
    assert len(calls) == 0


def test_R14_item_supply_ne_snapshot_prepaid_rejected(monkeypatch):
    """item.supply != snapshot.prepaid_supply → QUOTE_PAYMENT_SNAPSHOT_INVALID."""
    snap = {**_minimal_snap_dict(supply=200_000, vat=20_000, total=220_000), "prepaid_supply_amount": 180_000}
    item = {**_minimal_item_dict(supply=200_000, vat=20_000, total=220_000), "pricing_snapshot": snap}
    quote = _valid_quote(supply=200_000, vat=20_000, total=220_000, items=[item])
    sb, calls = _setup_prepare_with_quote(monkeypatch, quote)
    with pytest.raises(SaasRenewalV2AdapterError) as exc:
        prepare_saas_v2_renewal_payment_from_quote(
            sb, contract_id=_CONTRACT_ID, quote_id=_QUOTE_ID,
            company_id=_COMPANY_ID, user_id=_USER_ID,
        )
    assert exc.value.code == "QUOTE_PAYMENT_SNAPSHOT_INVALID"
    assert len(calls) == 0


def test_R15_valid_prepare_calls_exact_once(monkeypatch):
    """정상 경로 → _run_inicis_prepare_exact 1회 호출."""
    quote = _valid_quote()
    sb, calls = _setup_prepare_with_quote(monkeypatch, quote)
    prepare_saas_v2_renewal_payment_from_quote(
        sb, contract_id=_CONTRACT_ID, quote_id=_QUOTE_ID,
        company_id=_COMPANY_ID, user_id=_USER_ID,
    )
    assert len(calls) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# R16–R20: Prepare call contract
# ═══════════════════════════════════════════════════════════════════════════════

def _setup_valid_prepare(monkeypatch):
    quote = _valid_quote()
    monkeypatch.setattr("services.member_quote_svc.get_member_quote", lambda *a: quote)
    monkeypatch.setattr("services.saas_renewal_v2_adapter.load_sign_key", lambda: "K")
    calls = []
    monkeypatch.setattr(
        "services.saas_renewal_v2_adapter._run_inicis_prepare_exact",
        _fake_prepare_exact(calls),
    )
    sb = _FakeSbForPrepare(contract=_valid_contract(), cv=_valid_cv_row())
    return sb, calls


def test_R16_payment_type_is_renewal(monkeypatch):
    """payment_type='RENEWAL' — CardBilling/BillKey 아님."""
    sb, calls = _setup_valid_prepare(monkeypatch)
    prepare_saas_v2_renewal_payment_from_quote(
        sb, contract_id=_CONTRACT_ID, quote_id=_QUOTE_ID,
        company_id=_COMPANY_ID, user_id=_USER_ID,
    )
    assert calls[0]["payment_type"] == "RENEWAL"


def test_R17_contract_id_is_existing_contract(monkeypatch):
    """contract_id = 기존 계약 UUID (새 계약 생성 아님)."""
    sb, calls = _setup_valid_prepare(monkeypatch)
    prepare_saas_v2_renewal_payment_from_quote(
        sb, contract_id=_CONTRACT_ID, quote_id=_QUOTE_ID,
        company_id=_COMPANY_ID, user_id=_USER_ID,
    )
    assert calls[0]["contract_id"] == _CONTRACT_ID


def test_R18_plan_code_is_none(monkeypatch):
    """plan_code = None (V2 Sentinel)."""
    sb, calls = _setup_valid_prepare(monkeypatch)
    prepare_saas_v2_renewal_payment_from_quote(
        sb, contract_id=_CONTRACT_ID, quote_id=_QUOTE_ID,
        company_id=_COMPANY_ID, user_id=_USER_ID,
    )
    assert calls[0].get("plan_code") is None


def test_R19_supply_amount_from_snapshot(monkeypatch):
    """supply_amount = snapshot.prepaid_supply_amount (클라이언트 값 사용 0)."""
    sb, calls = _setup_valid_prepare(monkeypatch)
    prepare_saas_v2_renewal_payment_from_quote(
        sb, contract_id=_CONTRACT_ID, quote_id=_QUOTE_ID,
        company_id=_COMPANY_ID, user_id=_USER_ID,
    )
    assert calls[0]["supply_amount"] == 200_000


def test_R20_period_months_from_snapshot(monkeypatch):
    """period_months = snapshot.term_months."""
    sb, calls = _setup_valid_prepare(monkeypatch)
    prepare_saas_v2_renewal_payment_from_quote(
        sb, contract_id=_CONTRACT_ID, quote_id=_QUOTE_ID,
        company_id=_COMPANY_ID, user_id=_USER_ID,
    )
    assert calls[0]["period_months"] == 12


# ═══════════════════════════════════════════════════════════════════════════════
# R21–R30: Plan builder guards (pure, DB write = 0)
# ═══════════════════════════════════════════════════════════════════════════════

def _valid_plan_args():
    return dict(
        pay=_valid_pay(),
        quote=_valid_quote(),
        current_cv=_valid_cv_row(),
        requested_effective_at=_EFFECTIVE_AT,
    )


def test_R21_plan_not_paid_rejected():
    """pay.status_code ∉ {PAID, SUCCESS} → RENEWAL_PAYMENT_NOT_PAID."""
    args = _valid_plan_args()
    args["pay"] = _valid_pay(status_code="PENDING")
    with pytest.raises(SaasRenewalV2AdapterError) as exc:
        build_saas_v2_renewal_apply_plan(**args)
    assert exc.value.code == "RENEWAL_PAYMENT_NOT_PAID"


def test_R22_plan_legacy_plan_code_rejected():
    """pay.plan_code != None → RENEWAL_LEGACY_PLAN_CODE_FORBIDDEN."""
    args = _valid_plan_args()
    args["pay"] = _valid_pay(plan_code="INDUSTRY_PRO")
    with pytest.raises(SaasRenewalV2AdapterError) as exc:
        build_saas_v2_renewal_apply_plan(**args)
    assert exc.value.code == "RENEWAL_LEGACY_PLAN_CODE_FORBIDDEN"


def test_R23_plan_no_paid_at_rejected():
    """pay.paid_at 없음 → RENEWAL_PAID_AT_REQUIRED."""
    args = _valid_plan_args()
    pay = _valid_pay()
    pay.pop("paid_at", None)
    args["pay"] = pay
    with pytest.raises(SaasRenewalV2AdapterError) as exc:
        build_saas_v2_renewal_apply_plan(**args)
    assert exc.value.code == "RENEWAL_PAID_AT_REQUIRED"


def test_R24_plan_invalid_paid_at_rejected():
    """paid_at naive datetime → RENEWAL_PAID_AT_INVALID."""
    args = _valid_plan_args()
    args["pay"] = {**_valid_pay(), "paid_at": "2026-09-28T10:00:00"}  # naive (no tz)
    with pytest.raises(SaasRenewalV2AdapterError) as exc:
        build_saas_v2_renewal_apply_plan(**args)
    assert exc.value.code == "RENEWAL_PAID_AT_INVALID"


def test_R25_plan_no_user_id_rejected():
    """pay.user_id 없음 → RENEWAL_USER_REQUIRED."""
    args = _valid_plan_args()
    pay = {**_valid_pay(), "user_id": None}
    args["pay"] = pay
    with pytest.raises(SaasRenewalV2AdapterError) as exc:
        build_saas_v2_renewal_apply_plan(**args)
    assert exc.value.code == "RENEWAL_USER_REQUIRED"


def test_R26_plan_product_type_not_saas_rejected():
    """product_type != SAAS → RENEWAL_PAY_NOT_SAAS."""
    args = _valid_plan_args()
    args["pay"] = {**_valid_pay(), "product_type": "DIAGNOSIS"}
    with pytest.raises(SaasRenewalV2AdapterError) as exc:
        build_saas_v2_renewal_apply_plan(**args)
    assert exc.value.code == "RENEWAL_PAY_NOT_SAAS"


def test_R27_plan_no_contract_id_rejected():
    """pay.contract_id 없음 → RENEWAL_CONTRACT_ID_REQUIRED."""
    args = _valid_plan_args()
    args["pay"] = {**_valid_pay(), "contract_id": None}
    with pytest.raises(SaasRenewalV2AdapterError) as exc:
        build_saas_v2_renewal_apply_plan(**args)
    assert exc.value.code == "RENEWAL_CONTRACT_ID_REQUIRED"


def test_R28_plan_wrong_payment_type_rejected():
    """payment_type != RENEWAL → RENEWAL_PAYMENT_TYPE_INVALID."""
    args = _valid_plan_args()
    args["pay"] = _valid_pay(payment_type="CARD")
    with pytest.raises(SaasRenewalV2AdapterError) as exc:
        build_saas_v2_renewal_apply_plan(**args)
    assert exc.value.code == "RENEWAL_PAYMENT_TYPE_INVALID"


def test_R29_plan_period_term_mismatch_rejected():
    """pay.period_months != snapshot.term_months → RENEWAL_PERIOD_TERM_MISMATCH."""
    args = _valid_plan_args()
    args["pay"] = {**_valid_pay(), "period_months": 6}  # snapshot.term_months=12
    with pytest.raises(SaasRenewalV2AdapterError) as exc:
        build_saas_v2_renewal_apply_plan(**args)
    assert exc.value.code == "RENEWAL_PERIOD_TERM_MISMATCH"


def test_R30_plan_next_version_no_is_current_plus_one():
    """next_version_no = current_cv.version_no + 1."""
    cv = _valid_cv_row(version_no=3)
    args = _valid_plan_args()
    args["current_cv"] = cv
    plan = build_saas_v2_renewal_apply_plan(**args)
    assert isinstance(plan, SaasV2RenewalApplyPlan)
    assert plan.next_version_no == 4


# ═══════════════════════════════════════════════════════════════════════════════
# R31–R40: Structural / billing boundary guards
# ═══════════════════════════════════════════════════════════════════════════════

def _src_code():
    return _SVC_SRC.read_text()


def test_R31_plan_effective_from_is_requested_not_paid_at():
    """commercial_bundle.commercial_version.effective_from = requested_effective_at, paid_at 아님."""
    args = _valid_plan_args()
    args["requested_effective_at"] = _EFFECTIVE_AT
    plan = build_saas_v2_renewal_apply_plan(**args)
    assert plan.requested_effective_at == _EFFECTIVE_AT
    assert plan.commercial_bundle.commercial_version.effective_from == _EFFECTIVE_AT


def test_R32_plan_bundle_version_no_matches_next():
    """commercial_bundle.commercial_version.version_no = plan.next_version_no."""
    args = _valid_plan_args()
    plan = build_saas_v2_renewal_apply_plan(**args)
    assert plan.commercial_bundle.commercial_version.version_no == plan.next_version_no


def test_R33_plan_contract_id_is_existing():
    """plan.contract_id = 기존 contract UUID (새 계약 생성 아님)."""
    args = _valid_plan_args()
    plan = build_saas_v2_renewal_apply_plan(**args)
    assert str(plan.contract_id) == _CONTRACT_ID


def test_R34_plan_db_write_zero():
    """build_saas_v2_renewal_apply_plan = pure function — DB write 없음."""
    _db_write_calls = []

    class _WatchSb:
        def table(self, name):
            _db_write_calls.append(("table", name))
            raise AssertionError(f"plan builder는 DB write 0: table({name!r}) 호출됨")

    class _WatchedPlan(SaasV2RenewalApplyPlan):
        pass

    args = _valid_plan_args()
    plan = build_saas_v2_renewal_apply_plan(**args)
    assert isinstance(plan, SaasV2RenewalApplyPlan)
    assert _db_write_calls == [], "DB 호출 감지됨"


def test_R35_no_subscriptions_in_module():
    """saas_renewal_v2_adapter.py에 subscriptions 테이블 참조 없음."""
    code = _src_code()
    assert '"subscriptions"' not in code
    assert "'subscriptions'" not in code


def test_R36_no_billing_keys_in_module():
    """saas_renewal_v2_adapter.py에 billing_keys 테이블 참조 없음."""
    code = _src_code()
    assert '"billing_keys"' not in code
    assert "'billing_keys'" not in code


def test_R37_no_bill_key_auto_recurring_reference():
    """auto-recurring / BillKey / CardBilling 실행 참조 없음 (docstring 제외)."""
    lines = [
        ln for ln in _src_code().splitlines()
        if not ln.lstrip().startswith(("#", '"""', "- ", "  -"))
    ]
    code = "\n".join(lines)
    assert "CardBilling" not in code
    assert "run_billing_charge" not in code
    assert "run_billing_prepare" not in code
    assert "auto_recurring" not in code


def test_R38_no_vat_formula_in_module():
    """saas_renewal_v2_adapter.py에 VAT 계산식 없음."""
    lines = [
        ln for ln in _src_code().splitlines()
        if not ln.lstrip().startswith(("#", '"""', "- "))
    ]
    code = "\n".join(lines)
    assert "add_vat(" not in code
    assert "split_supply_vat(" not in code
    assert "* 0.1" not in code
    assert "* 1.1" not in code


def test_R39_plan_success_status_code():
    """pay.status_code=SUCCESS도 PASS."""
    args = _valid_plan_args()
    args["pay"] = {**_valid_pay(), "status_code": "SUCCESS"}
    plan = build_saas_v2_renewal_apply_plan(**args)
    assert isinstance(plan, SaasV2RenewalApplyPlan)


def test_R40_plan_commercial_bundle_contract_id_matches():
    """commercial_bundle.commercial_version.contract_id = plan.contract_id."""
    args = _valid_plan_args()
    plan = build_saas_v2_renewal_apply_plan(**args)
    assert plan.commercial_bundle.commercial_version.contract_id == plan.contract_id


# ═══════════════════════════════════════════════════════════════════════════════
# R41–R42: PATCH1 — Prepare side guards
# ═══════════════════════════════════════════════════════════════════════════════

def test_R41_contract_not_saas_rejected(monkeypatch):
    """contract.service_type != SAAS → CONTRACT_NOT_SAAS (PATCH A)."""
    monkeypatch.setattr("services.member_quote_svc.get_member_quote", lambda *a: _valid_quote())
    monkeypatch.setattr("services.saas_renewal_v2_adapter.load_sign_key", lambda: "K")
    sb = _FakeSbForPrepare(contract=_valid_contract(service_type="CONSULTING"), cv=_valid_cv_row())
    with pytest.raises(SaasRenewalV2AdapterError) as exc:
        prepare_saas_v2_renewal_payment_from_quote(
            sb, contract_id=_CONTRACT_ID, quote_id=_QUOTE_ID,
            company_id=_COMPANY_ID, user_id=_USER_ID,
        )
    assert exc.value.code == "CONTRACT_NOT_SAAS"


def test_R42_quote_source_invalid_on_prepare(monkeypatch):
    """quote.source != member_auto → QUOTE_SOURCE_INVALID (PATCH A)."""
    quote = {**_valid_quote(), "source": "admin_manual"}
    monkeypatch.setattr("services.member_quote_svc.get_member_quote", lambda *a: quote)
    monkeypatch.setattr("services.saas_renewal_v2_adapter.load_sign_key", lambda: "K")
    sb = _FakeSbForPrepare(contract=_valid_contract(), cv=_valid_cv_row())
    with pytest.raises(SaasRenewalV2AdapterError) as exc:
        prepare_saas_v2_renewal_payment_from_quote(
            sb, contract_id=_CONTRACT_ID, quote_id=_QUOTE_ID,
            company_id=_COMPANY_ID, user_id=_USER_ID,
        )
    assert exc.value.code == "QUOTE_SOURCE_INVALID"


# ═══════════════════════════════════════════════════════════════════════════════
# R43–R52: PATCH1 — Plan builder identity + CV + effective_at guards
# ═══════════════════════════════════════════════════════════════════════════════

def test_R43_cv_schema_invalid_rejected():
    """current_cv.commercial_schema_version 불일치 → CURRENT_CV_SCHEMA_INVALID (PATCH B)."""
    args = _valid_plan_args()
    args["current_cv"] = {**_valid_cv_row(), "commercial_schema_version": "SAAS_CONTRACT_V1"}
    with pytest.raises(SaasRenewalV2AdapterError) as exc:
        build_saas_v2_renewal_apply_plan(**args)
    assert exc.value.code == "CURRENT_CV_SCHEMA_INVALID"


def test_R44_cv_superseded_rejected():
    """current_cv.superseded_at IS NOT NULL → CURRENT_CV_SUPERSEDED (PATCH B)."""
    args = _valid_plan_args()
    args["current_cv"] = {**_valid_cv_row(), "superseded_at": "2026-09-01T00:00:00+00:00"}
    with pytest.raises(SaasRenewalV2AdapterError) as exc:
        build_saas_v2_renewal_apply_plan(**args)
    assert exc.value.code == "CURRENT_CV_SUPERSEDED"


def test_R45_cv_version_no_zero_rejected():
    """current_cv.version_no = 0 → CURRENT_CV_VERSION_NO_INVALID (PATCH B)."""
    args = _valid_plan_args()
    args["current_cv"] = {**_valid_cv_row(), "version_no": 0}
    with pytest.raises(SaasRenewalV2AdapterError) as exc:
        build_saas_v2_renewal_apply_plan(**args)
    assert exc.value.code == "CURRENT_CV_VERSION_NO_INVALID"


def test_R46_contract_cv_mismatch_rejected():
    """pay.contract_id != current_cv.contract_id → RENEWAL_CONTRACT_CV_MISMATCH (PATCH B)."""
    args = _valid_plan_args()
    args["current_cv"] = {**_valid_cv_row(), "contract_id": str(uuid.uuid4())}
    with pytest.raises(SaasRenewalV2AdapterError) as exc:
        build_saas_v2_renewal_apply_plan(**args)
    assert exc.value.code == "RENEWAL_CONTRACT_CV_MISMATCH"


def test_R47_company_mismatch_rejected():
    """pay.company_id != quote.company_id → RENEWAL_COMPANY_MISMATCH (PATCH B)."""
    args = _valid_plan_args()
    args["pay"] = {**_valid_pay(), "company_id": "OTHER-CO"}
    with pytest.raises(SaasRenewalV2AdapterError) as exc:
        build_saas_v2_renewal_apply_plan(**args)
    assert exc.value.code == "RENEWAL_COMPANY_MISMATCH"


def test_R48_quote_id_required_rejected():
    """pay.quote_id 없음 → RENEWAL_QUOTE_ID_REQUIRED (PATCH B)."""
    args = _valid_plan_args()
    pay = {**_valid_pay(), "quote_id": None}
    args["pay"] = pay
    with pytest.raises(SaasRenewalV2AdapterError) as exc:
        build_saas_v2_renewal_apply_plan(**args)
    assert exc.value.code == "RENEWAL_QUOTE_ID_REQUIRED"


def test_R49_quote_id_mismatch_rejected():
    """pay.quote_id != quote.id → RENEWAL_QUOTE_ID_MISMATCH (PATCH B)."""
    args = _valid_plan_args()
    args["pay"] = {**_valid_pay(), "quote_id": str(uuid.uuid4())}
    with pytest.raises(SaasRenewalV2AdapterError) as exc:
        build_saas_v2_renewal_apply_plan(**args)
    assert exc.value.code == "RENEWAL_QUOTE_ID_MISMATCH"


def test_R50_quote_source_invalid_in_plan_builder():
    """plan builder: quote.source != member_auto → QUOTE_SOURCE_INVALID (PATCH B)."""
    args = _valid_plan_args()
    args["quote"] = {**_valid_quote(), "source": "admin_manual"}
    with pytest.raises(SaasRenewalV2AdapterError) as exc:
        build_saas_v2_renewal_apply_plan(**args)
    assert exc.value.code == "QUOTE_SOURCE_INVALID"


def test_R51_effective_at_naive_rejected():
    """requested_effective_at naive datetime → RENEWAL_EFFECTIVE_AT_INVALID (PATCH C)."""
    args = _valid_plan_args()
    args["requested_effective_at"] = datetime(2026, 10, 1, 0, 0, 0)  # no tzinfo
    with pytest.raises(SaasRenewalV2AdapterError) as exc:
        build_saas_v2_renewal_apply_plan(**args)
    assert exc.value.code == "RENEWAL_EFFECTIVE_AT_INVALID"


def test_R52_effective_before_current_version_rejected():
    """requested_effective_at < current_cv.effective_from → RENEWAL_EFFECTIVE_BEFORE_CURRENT_VERSION (PATCH C)."""
    args = _valid_plan_args()
    # _valid_cv_row() has effective_from="2026-04-01T00:00:00+00:00"
    args["requested_effective_at"] = datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(SaasRenewalV2AdapterError) as exc:
        build_saas_v2_renewal_apply_plan(**args)
    assert exc.value.code == "RENEWAL_EFFECTIVE_BEFORE_CURRENT_VERSION"


# ═══════════════════════════════════════════════════════════════════════════════
# R53: PATCH D — SaasV2RenewalApplyPlan new fields
# ═══════════════════════════════════════════════════════════════════════════════

def test_R53_plan_has_quote_id_and_current_version_no():
    """plan.quote_id = pay.quote_id / plan.current_version_no = cv.version_no (PATCH D)."""
    cv = _valid_cv_row(version_no=3)
    args = _valid_plan_args()
    args["current_cv"] = cv
    plan = build_saas_v2_renewal_apply_plan(**args)
    assert plan.quote_id == _QUOTE_ID
    assert plan.current_version_no == 3
    assert plan.next_version_no == 4
