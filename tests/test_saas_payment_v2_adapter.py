"""Tests for WO-PRICING-V2-BE-OBJ10-A — Quote V2 → Existing INICIS Payment Adapter.

Coverage: A01-A43
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("INTERNAL_API_SECRET", "pytest-internal-secret")

from schemas.payment import PrepareBody
from services.payment_svc import (
    PaymentPrepareError,
    _run_inicis_prepare_exact,
    run_inicis_prepare,
)
from services.saas_payment_v2_adapter import (
    SaasPaymentV2AdapterError,
    prepare_saas_v2_payment_from_quote,
)

_SVC_SRC = Path(__file__).parent.parent / "services" / "saas_payment_v2_adapter.py"
_PAYMENT_SVC_SRC = Path(__file__).parent.parent / "services" / "payment_svc.py"

_QUOTE_ID = str(uuid.uuid4())
_COMPANY_ID = "C-PAY-TEST"
_USER_ID = "U-PAY-TEST"
_SITE_ID = str(uuid.uuid4())


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers / Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

def _fake_sb_insert(result_id="pay-test-id"):
    sb = MagicMock()
    insert_mock = MagicMock()
    insert_mock.execute.return_value = MagicMock(data=[{"id": result_id}])
    sb.table.return_value.insert.return_value = insert_mock
    return sb


def _capturing_sb():
    """INSERT를 캡처하고 row를 반환하는 FakeSupabase."""
    calls = []

    class _Res:
        def __init__(self, row):
            self.data = [row]

    class _Insert:
        def __init__(self, row):
            self._row = row

        def execute(self):
            calls.append(dict(self._row))
            return _Res({**self._row, "id": "pay-captured"})

    class _Table:
        def insert(self, row):
            return _Insert(row)

    class _CapturingSb:
        def table(self, _name):
            return _Table()

        @property
        def captured(self):
            return calls

    sb = _CapturingSb()
    return sb


def _minimal_snap_dict(supply=100_000, vat=10_000, total=110_000, term=1):
    return {
        "schema_version": "SAAS_PRICING_V2",
        "policy_version": "TEST",
        "product_tier": "MANAGER",
        "pricing_mode": "STANDARD",
        "sites": [{
            "entity_type": "factory",
            "entity_id": _SITE_ID,
            "sector": "INDUSTRY",
            "base_band_code": "STANDARD",
            "base_amount": supply,
            "is_primary": True,
            "applied_rate_bps": 10_000,
            "final_site_amount": supply,
        }],
        "worker": {"capacity": 0, "amount": 0, "brackets": []},
        "payment_months": term,
        "term_discount_rate_bps": 0,
        "monthly_supply_amount": supply,
        "prepaid_supply_amount": supply,
        "vat_rate_bps": 1_000,
        "vat_amount": vat,
        "total_amount": total,
    }


def _minimal_item_dict(supply=100_000, vat=10_000, total=110_000, term=1):
    return {
        "quote_schema_version": "SAAS_QUOTE_V2",
        "display_name": "TAI Safe 관리자형",
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
        "product_tier": "MANAGER",
        "pricing_mode": "STANDARD",
        "policy_version": "TEST",
        "worker_capacity": 0,
        "payment_months": term,
        "vat_rate": 0.1,
        "vat_rate_bps": 1_000,
        "pricing_input": {
            "product_tier": "MANAGER",
            "worker_capacity": 0,
            "payment_months": term,
            "sites": [{"entity_id": _SITE_ID, "sector": "INDUSTRY", "criteria_value": 10}],
        },
        "pricing_snapshot": _minimal_snap_dict(supply, vat, total, term),
    }


def _valid_v2_quote(
    quote_id=_QUOTE_ID,
    company_id=_COMPANY_ID,
    status_code="ISSUED",
    service_type="SAAS",
    supply=100_000,
    vat=10_000,
    total=110_000,
    term=1,
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


def _fake_prepare_exact(calls):
    """_run_inicis_prepare_exact 호출을 캡처하는 stub."""
    def _stub(supabase, sign_key, **kwargs):
        calls.append(kwargs)
        return {"status": "success", "data": {"payment_id": "pay-stub"}}
    return _stub


# ═══════════════════════════════════════════════════════════════════════════════
# A01–A10: Existing run_inicis_prepare Regression
# ═══════════════════════════════════════════════════════════════════════════════

def test_A01_run_inicis_prepare_still_callable():
    """run_inicis_prepare 시그니처 유지."""
    import inspect
    sig = inspect.signature(run_inicis_prepare)
    params = list(sig.parameters.keys())
    assert "body" in params


def test_A02_v1_supply_is_body_amount(monkeypatch):
    """V1: supply_amount = body.amount (add_vat 이전)."""
    sb = _capturing_sb()
    monkeypatch.setattr("services.payment_svc.get_supabase", lambda: sb)
    monkeypatch.setattr("services.payment_svc.load_sign_key", lambda: "TEST_SIGN_KEY")
    body = PrepareBody(user_id=str(uuid.uuid4()), product_type="DIAGNOSIS", amount=99_000, goodname="법령진단")
    run_inicis_prepare(body)
    assert sb.captured[0]["supply_amount"] == 99_000


def test_A03_v1_vat_is_total_minus_supply(monkeypatch):
    """V1: vat_amount = total - supply."""
    sb = _capturing_sb()
    monkeypatch.setattr("services.payment_svc.get_supabase", lambda: sb)
    monkeypatch.setattr("services.payment_svc.load_sign_key", lambda: "TEST_SIGN_KEY")
    body = PrepareBody(user_id=str(uuid.uuid4()), product_type="DIAGNOSIS", amount=99_000, goodname="법령진단")
    run_inicis_prepare(body)
    row = sb.captured[0]
    assert row["vat_amount"] == row["total_amount"] - row["supply_amount"]


def test_A04_v1_total_is_add_vat_of_amount(monkeypatch):
    """V1: total_amount = add_vat(body.amount) = amount * 1.1."""
    from services.payment_helpers import add_vat
    sb = _capturing_sb()
    monkeypatch.setattr("services.payment_svc.get_supabase", lambda: sb)
    monkeypatch.setattr("services.payment_svc.load_sign_key", lambda: "TEST_SIGN_KEY")
    body = PrepareBody(user_id=str(uuid.uuid4()), product_type="DIAGNOSIS", amount=99_000, goodname="법령진단")
    run_inicis_prepare(body)
    assert sb.captured[0]["total_amount"] == add_vat(99_000)


def test_A05_v1_price_str_is_total(monkeypatch):
    """V1: INICIS price = str(total_amount)."""
    from services.payment_helpers import add_vat
    sb = _fake_sb_insert()
    monkeypatch.setattr("services.payment_svc.get_supabase", lambda: sb)
    monkeypatch.setattr("services.payment_svc.load_sign_key", lambda: "TEST_SIGN_KEY")
    body = PrepareBody(user_id=str(uuid.uuid4()), product_type="DIAGNOSIS", amount=99_000, goodname="법령진단")
    result = run_inicis_prepare(body)
    assert result["data"]["price"] == str(add_vat(99_000))


def test_A06_v1_quote_id_passthrough(monkeypatch):
    """V1: quote_id → payments row."""
    sb = _capturing_sb()
    monkeypatch.setattr("services.payment_svc.get_supabase", lambda: sb)
    monkeypatch.setattr("services.payment_svc.load_sign_key", lambda: "TEST_SIGN_KEY")
    qid = str(uuid.uuid4())
    body = PrepareBody(user_id=str(uuid.uuid4()), product_type="DIAGNOSIS", amount=10_000,
                       goodname="진단", quote_id=qid)
    run_inicis_prepare(body)
    assert sb.captured[0].get("quote_id") == qid


def test_A07_v1_contract_id_passthrough(monkeypatch):
    """V1: contract_id → payments row."""
    sb = _capturing_sb()
    monkeypatch.setattr("services.payment_svc.get_supabase", lambda: sb)
    monkeypatch.setattr("services.payment_svc.load_sign_key", lambda: "TEST_SIGN_KEY")
    cid = str(uuid.uuid4())
    body = PrepareBody(user_id=str(uuid.uuid4()), product_type="DIAGNOSIS", amount=10_000,
                       goodname="진단", contract_id=cid)
    run_inicis_prepare(body)
    assert sb.captured[0].get("contract_id") == cid


def test_A08_v1_plan_code_passthrough(monkeypatch):
    """V1: plan_code → payments row."""
    sb = _capturing_sb()
    monkeypatch.setattr("services.payment_svc.get_supabase", lambda: sb)
    monkeypatch.setattr("services.payment_svc.load_sign_key", lambda: "TEST_SIGN_KEY")
    body = PrepareBody(user_id=str(uuid.uuid4()), product_type="DIAGNOSIS", amount=10_000,
                       goodname="진단", plan_code="INDUSTRY_STARTER")
    run_inicis_prepare(body)
    assert sb.captured[0].get("plan_code") == "INDUSTRY_STARTER"


def test_A09_v1_period_months_passthrough(monkeypatch):
    """V1: period_months → payments row."""
    sb = _capturing_sb()
    monkeypatch.setattr("services.payment_svc.get_supabase", lambda: sb)
    monkeypatch.setattr("services.payment_svc.load_sign_key", lambda: "TEST_SIGN_KEY")
    body = PrepareBody(user_id=str(uuid.uuid4()), product_type="SAAS_INDUSTRY", amount=10_000,
                       goodname="진단", period_months=12)
    run_inicis_prepare(body)
    assert sb.captured[0].get("period_months") == 12


def test_A10_v1_proof_type_passthrough(monkeypatch):
    """V1: proof_type → payments row."""
    sb = _capturing_sb()
    monkeypatch.setattr("services.payment_svc.get_supabase", lambda: sb)
    monkeypatch.setattr("services.payment_svc.load_sign_key", lambda: "TEST_SIGN_KEY")
    body = PrepareBody(user_id=str(uuid.uuid4()), product_type="DIAGNOSIS", amount=10_000,
                       goodname="진단", proof_type="TAX_INVOICE")
    run_inicis_prepare(body)
    assert sb.captured[0].get("proof_type") == "TAX_INVOICE"


# ═══════════════════════════════════════════════════════════════════════════════
# A11–A14: Exact Prepare Core Tests
# ═══════════════════════════════════════════════════════════════════════════════

def test_A11_exact_helper_accepts_server_amounts():
    """_run_inicis_prepare_exact: supply/vat/total 직접 수신."""
    sb = _fake_sb_insert()
    result = _run_inicis_prepare_exact(
        sb, "TEST_KEY",
        supply_amount=100_000, vat_amount=10_000, total_amount=110_000,
        product_type="SAAS", goodname="TAI Safe 관리자형", user_id=_USER_ID,
    )
    assert result["status"] == "success"
    assert result["data"]["price"] == "110000"


def test_A12_exact_helper_does_not_call_add_vat():
    """_run_inicis_prepare_exact 소스에 add_vat 호출 없음."""
    src = _PAYMENT_SVC_SRC.read_text()
    # _run_inicis_prepare_exact 함수 본문만 추출
    start = src.index("def _run_inicis_prepare_exact(")
    end = src.index("\ndef run_inicis_prepare(", start)
    body = src[start:end]
    assert "add_vat(" not in body


def test_A13_supply_plus_vat_not_equal_total_rejected():
    """supply + vat != total → PaymentPrepareError."""
    sb = _fake_sb_insert()
    with pytest.raises(PaymentPrepareError):
        _run_inicis_prepare_exact(
            sb, "TEST_KEY",
            supply_amount=100_000, vat_amount=10_000, total_amount=115_000,
            product_type="SAAS", goodname="test", user_id=_USER_ID,
        )


def test_A14_total_zero_rejected():
    """total_amount <= 0 → PaymentPrepareError."""
    sb = _fake_sb_insert()
    with pytest.raises(PaymentPrepareError):
        _run_inicis_prepare_exact(
            sb, "TEST_KEY",
            supply_amount=0, vat_amount=0, total_amount=0,
            product_type="SAAS", goodname="test", user_id=_USER_ID,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# A15–A19: Quote Loader Tests
# ═══════════════════════════════════════════════════════════════════════════════

def test_A15_get_member_quote_reused(monkeypatch):
    """member_quote_svc.get_member_quote를 직접 재사용한다 (신규 쿼리 없음)."""
    src = _SVC_SRC.read_text()
    assert "get_member_quote" in src
    assert "member_quote_svc.get_member_quote" in src


def test_A16_quote_not_found_raises(monkeypatch):
    """get_member_quote → None → QUOTE_NOT_FOUND."""
    monkeypatch.setattr("services.member_quote_svc.get_member_quote", lambda *a: None)
    monkeypatch.setattr("services.saas_payment_v2_adapter.load_sign_key", lambda: "K")
    with pytest.raises(SaasPaymentV2AdapterError) as exc:
        prepare_saas_v2_payment_from_quote(None, _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert exc.value.code == "QUOTE_NOT_FOUND"


def test_A17_company_mismatch_raises(monkeypatch):
    """quote.company_id != auth company_id → QUOTE_NOT_OWNED."""
    quote = _valid_v2_quote(company_id="OTHER-COMPANY")
    monkeypatch.setattr("services.member_quote_svc.get_member_quote", lambda *a: quote)
    monkeypatch.setattr("services.saas_payment_v2_adapter.load_sign_key", lambda: "K")
    with pytest.raises(SaasPaymentV2AdapterError) as exc:
        prepare_saas_v2_payment_from_quote(None, _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert exc.value.code == "QUOTE_NOT_OWNED"


def test_A18_non_issued_quote_raises(monkeypatch):
    """status_code != ISSUED → QUOTE_NOT_ISSUED."""
    quote = _valid_v2_quote(status_code="DRAFT")
    monkeypatch.setattr("services.member_quote_svc.get_member_quote", lambda *a: quote)
    monkeypatch.setattr("services.saas_payment_v2_adapter.load_sign_key", lambda: "K")
    with pytest.raises(SaasPaymentV2AdapterError) as exc:
        prepare_saas_v2_payment_from_quote(None, _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert exc.value.code == "QUOTE_NOT_ISSUED"


def test_A19_non_saas_service_type_raises(monkeypatch):
    """service_type != SAAS → QUOTE_NOT_SAAS."""
    quote = _valid_v2_quote(service_type="CONSULTING")
    monkeypatch.setattr("services.member_quote_svc.get_member_quote", lambda *a: quote)
    monkeypatch.setattr("services.saas_payment_v2_adapter.load_sign_key", lambda: "K")
    with pytest.raises(SaasPaymentV2AdapterError) as exc:
        prepare_saas_v2_payment_from_quote(None, _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert exc.value.code == "QUOTE_NOT_SAAS"


# ═══════════════════════════════════════════════════════════════════════════════
# A20–A24: V2 Quote Contract Tests
# ═══════════════════════════════════════════════════════════════════════════════

def test_A20_no_items_raises(monkeypatch):
    """items=[] → QUOTE_NOT_V2."""
    quote = _valid_v2_quote(items=[])
    monkeypatch.setattr("services.member_quote_svc.get_member_quote", lambda *a: quote)
    monkeypatch.setattr("services.saas_payment_v2_adapter.load_sign_key", lambda: "K")
    with pytest.raises(SaasPaymentV2AdapterError) as exc:
        prepare_saas_v2_payment_from_quote(None, _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert exc.value.code == "QUOTE_NOT_V2"


def test_A21_multiple_items_raises(monkeypatch):
    """items 2개 → QUOTE_NOT_V2."""
    quote = _valid_v2_quote(items=[_minimal_item_dict(), _minimal_item_dict()])
    monkeypatch.setattr("services.member_quote_svc.get_member_quote", lambda *a: quote)
    monkeypatch.setattr("services.saas_payment_v2_adapter.load_sign_key", lambda: "K")
    with pytest.raises(SaasPaymentV2AdapterError) as exc:
        prepare_saas_v2_payment_from_quote(None, _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert exc.value.code == "QUOTE_NOT_V2"


def test_A22_wrong_schema_version_raises(monkeypatch):
    """quote_schema_version != SAAS_QUOTE_V2 → QUOTE_NOT_V2."""
    item = {**_minimal_item_dict(), "quote_schema_version": "SAAS_QUOTE_V1"}
    quote = _valid_v2_quote(items=[item])
    monkeypatch.setattr("services.member_quote_svc.get_member_quote", lambda *a: quote)
    monkeypatch.setattr("services.saas_payment_v2_adapter.load_sign_key", lambda: "K")
    with pytest.raises(SaasPaymentV2AdapterError) as exc:
        prepare_saas_v2_payment_from_quote(None, _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert exc.value.code == "QUOTE_NOT_V2"


def test_A23_malformed_item_raises(monkeypatch):
    """SaasQuoteSnapshotItemV2 검증 실패 → QUOTE_ITEM_INVALID."""
    item = {"quote_schema_version": "SAAS_QUOTE_V2", "display_name": "invalid"}
    quote = _valid_v2_quote(items=[item])
    monkeypatch.setattr("services.member_quote_svc.get_member_quote", lambda *a: quote)
    monkeypatch.setattr("services.saas_payment_v2_adapter.load_sign_key", lambda: "K")
    with pytest.raises(SaasPaymentV2AdapterError) as exc:
        prepare_saas_v2_payment_from_quote(None, _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert exc.value.code == "QUOTE_ITEM_INVALID"


def test_A24_malformed_pricing_snapshot_raises(monkeypatch):
    """SaasPricingSnapshotV2 검증 실패 → QUOTE_ITEM_INVALID."""
    item = {**_minimal_item_dict(), "pricing_snapshot": {"schema_version": "bad"}}
    quote = _valid_v2_quote(items=[item])
    monkeypatch.setattr("services.member_quote_svc.get_member_quote", lambda *a: quote)
    monkeypatch.setattr("services.saas_payment_v2_adapter.load_sign_key", lambda: "K")
    with pytest.raises(SaasPaymentV2AdapterError) as exc:
        prepare_saas_v2_payment_from_quote(None, _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert exc.value.code == "QUOTE_ITEM_INVALID"


# ═══════════════════════════════════════════════════════════════════════════════
# A25–A28: Amount Integrity Tests
# ═══════════════════════════════════════════════════════════════════════════════

def _setup_for_amount_test(monkeypatch, quote):
    monkeypatch.setattr("services.member_quote_svc.get_member_quote", lambda *a: quote)
    monkeypatch.setattr("services.saas_payment_v2_adapter.load_sign_key", lambda: "K")
    calls = []
    monkeypatch.setattr("services.saas_payment_v2_adapter._run_inicis_prepare_exact",
                        _fake_prepare_exact(calls))
    return calls


def test_A25_quote_supply_ne_item_supply_rejected(monkeypatch):
    """quote.supply != item.supply → QUOTE_PAYMENT_SNAPSHOT_INVALID, INSERT 0."""
    item = _minimal_item_dict(supply=100_000, vat=10_000, total=110_000)
    quote = _valid_v2_quote(supply=99_000, vat=10_000, total=110_000, items=[item])
    calls = _setup_for_amount_test(monkeypatch, quote)
    with pytest.raises(SaasPaymentV2AdapterError) as exc:
        prepare_saas_v2_payment_from_quote(None, _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert exc.value.code == "QUOTE_PAYMENT_SNAPSHOT_INVALID"
    assert len(calls) == 0


def test_A26_item_supply_ne_snapshot_prepaid_rejected(monkeypatch):
    """item.supply != snapshot.prepaid_supply → QUOTE_PAYMENT_SNAPSHOT_INVALID."""
    snap = {**_minimal_snap_dict(supply=100_000, vat=10_000, total=110_000), "prepaid_supply_amount": 90_000}
    item = {**_minimal_item_dict(supply=100_000, vat=10_000, total=110_000), "pricing_snapshot": snap}
    quote = _valid_v2_quote(supply=100_000, vat=10_000, total=110_000, items=[item])
    calls = _setup_for_amount_test(monkeypatch, quote)
    with pytest.raises(SaasPaymentV2AdapterError) as exc:
        prepare_saas_v2_payment_from_quote(None, _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert exc.value.code == "QUOTE_PAYMENT_SNAPSHOT_INVALID"
    assert len(calls) == 0


def test_A27_quote_vat_ne_snapshot_vat_rejected(monkeypatch):
    """quote.vat != snapshot.vat → QUOTE_PAYMENT_SNAPSHOT_INVALID."""
    item = _minimal_item_dict(supply=100_000, vat=10_000, total=110_000)
    quote = _valid_v2_quote(supply=100_000, vat=9_000, total=110_000, items=[item])
    calls = _setup_for_amount_test(monkeypatch, quote)
    with pytest.raises(SaasPaymentV2AdapterError) as exc:
        prepare_saas_v2_payment_from_quote(None, _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert exc.value.code == "QUOTE_PAYMENT_SNAPSHOT_INVALID"
    assert len(calls) == 0


def test_A28_quote_total_ne_snapshot_total_rejected(monkeypatch):
    """quote.total != snapshot.total → QUOTE_PAYMENT_SNAPSHOT_INVALID."""
    item = _minimal_item_dict(supply=100_000, vat=10_000, total=110_000)
    quote = _valid_v2_quote(supply=100_000, vat=10_000, total=105_000, items=[item])
    calls = _setup_for_amount_test(monkeypatch, quote)
    with pytest.raises(SaasPaymentV2AdapterError) as exc:
        prepare_saas_v2_payment_from_quote(None, _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert exc.value.code == "QUOTE_PAYMENT_SNAPSHOT_INVALID"
    assert len(calls) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# A29–A38: Valid V2 Prepare — Field Contract Tests
# ═══════════════════════════════════════════════════════════════════════════════

def _setup_valid_v2(monkeypatch, supply=100_000, vat=10_000, total=110_000, term=1):
    quote = _valid_v2_quote(supply=supply, vat=vat, total=total, term=term)
    monkeypatch.setattr("services.member_quote_svc.get_member_quote", lambda *a: quote)
    monkeypatch.setattr("services.saas_payment_v2_adapter.load_sign_key", lambda: "TEST_KEY")
    calls = []
    monkeypatch.setattr("services.saas_payment_v2_adapter._run_inicis_prepare_exact",
                        _fake_prepare_exact(calls))
    return quote, calls


def test_A29_valid_v2_quote_calls_exact_core_once(monkeypatch):
    """정상 V2 Quote → _run_inicis_prepare_exact 1회 호출."""
    _, calls = _setup_valid_v2(monkeypatch)
    prepare_saas_v2_payment_from_quote(None, _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert len(calls) == 1


def test_A30_payment_supply_equals_snapshot_prepaid(monkeypatch):
    """payment.supply_amount = snapshot.prepaid_supply_amount."""
    _, calls = _setup_valid_v2(monkeypatch, supply=100_000)
    prepare_saas_v2_payment_from_quote(None, _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert calls[0]["supply_amount"] == 100_000


def test_A31_payment_vat_equals_snapshot_vat(monkeypatch):
    """payment.vat_amount = snapshot.vat_amount."""
    _, calls = _setup_valid_v2(monkeypatch, vat=10_000)
    prepare_saas_v2_payment_from_quote(None, _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert calls[0]["vat_amount"] == 10_000


def test_A32_payment_total_equals_snapshot_total(monkeypatch):
    """payment.total_amount = snapshot.total_amount."""
    _, calls = _setup_valid_v2(monkeypatch, total=110_000)
    prepare_saas_v2_payment_from_quote(None, _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert calls[0]["total_amount"] == 110_000


def test_A33_payment_quote_id_is_quote_id(monkeypatch):
    """payment.quote_id = quote.id."""
    _, calls = _setup_valid_v2(monkeypatch)
    prepare_saas_v2_payment_from_quote(None, _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert calls[0].get("quote_id") == _QUOTE_ID


def test_A34_payment_company_id_is_auth_company(monkeypatch):
    """payment.company_id = auth company_id (클라이언트 입력 0)."""
    _, calls = _setup_valid_v2(monkeypatch)
    prepare_saas_v2_payment_from_quote(None, _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert calls[0].get("company_id") == _COMPANY_ID


def test_A35_payment_user_id_is_auth_user(monkeypatch):
    """payment.user_id = auth user_id."""
    _, calls = _setup_valid_v2(monkeypatch)
    prepare_saas_v2_payment_from_quote(None, _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert calls[0].get("user_id") == _USER_ID


def test_A36_period_months_is_snapshot_term(monkeypatch):
    """period_months = snapshot.payment_months."""
    _, calls = _setup_valid_v2(monkeypatch, term=12)
    quote = _valid_v2_quote(
        supply=100_000, vat=10_000, total=110_000,
        items=[_minimal_item_dict(supply=100_000, vat=10_000, total=110_000, term=12)],
    )
    monkeypatch.setattr("services.member_quote_svc.get_member_quote", lambda *a: quote)
    monkeypatch.setattr("services.saas_payment_v2_adapter.load_sign_key", lambda: "K")
    new_calls = []
    monkeypatch.setattr("services.saas_payment_v2_adapter._run_inicis_prepare_exact",
                        _fake_prepare_exact(new_calls))
    prepare_saas_v2_payment_from_quote(None, _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert new_calls[0].get("period_months") == 12


def test_A37_plan_code_is_none(monkeypatch):
    """plan_code = None (base_band_code 등 V1 구조 사용 금지)."""
    _, calls = _setup_valid_v2(monkeypatch)
    prepare_saas_v2_payment_from_quote(None, _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert calls[0].get("plan_code") is None


def test_A38_product_type_is_saas(monkeypatch):
    """product_type = SAAS (internal only, Public PrepareBody 추가 0)."""
    _, calls = _setup_valid_v2(monkeypatch)
    prepare_saas_v2_payment_from_quote(None, _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert calls[0].get("product_type") == "SAAS"


# ═══════════════════════════════════════════════════════════════════════════════
# A39–A43: Source Guards
# ═══════════════════════════════════════════════════════════════════════════════

def _adapter_code_lines():
    lines = _SVC_SRC.read_text().splitlines()
    return "\n".join(ln for ln in lines if not ln.lstrip().startswith(("#", '"""', "- ")))


def test_A39_no_vat_formula_in_adapter():
    """Adapter 소스에 VAT 계산식 없음."""
    code = _adapter_code_lines()
    assert "add_vat(" not in code
    assert "split_supply_vat(" not in code
    assert "* 0.1" not in code
    assert "* 1.1" not in code


def test_A40_no_pricing_engine_import():
    """Adapter가 pricing engine을 직접 import하지 않음."""
    code = _adapter_code_lines()
    assert "price_master" not in code
    assert "pricing_resolver" not in code
    assert "pricing_composer" not in code
    assert "preview_saas_price" not in code


def test_A41_no_contract_write():
    """Adapter 소스에 contracts/subscriptions write 없음."""
    code = _adapter_code_lines()
    assert '"contracts"' not in code
    assert "'contracts'" not in code
    assert '"subscriptions"' not in code
    assert "'subscriptions'" not in code


def test_A42_runtime_consumer_zero():
    """Adapter를 payment 런타임 라우터(routers/payment.py)에서 import하지 않는다.
    member_quotes.py의 prepare 엔드포인트는 유일한 허용 소비자.
    """
    import subprocess
    result = subprocess.run(
        ["grep", "-r", "saas_payment_v2_adapter", "routers/"],
        capture_output=True, text=True,
        cwd=Path(__file__).parent.parent,
    )
    # Filter: allow only member_quotes.py (prepare endpoint) — exclude binary .pyc
    hits = [
        line for line in result.stdout.splitlines()
        if "member_quotes.py" not in line and not line.startswith("Binary")
    ]
    assert hits == [], f"payment 런타임 라우터에서 adapter import 감지: {hits}"


def test_A43_public_preparebody_saas_not_added():
    """Public PrepareBody 허용 product_type에 SAAS 추가 안 됨."""
    from schemas.payment import PrepareBody as PB
    import inspect
    src = inspect.getsource(PB.product_type_valid)
    assert "SAAS" not in src or '"SAAS"' not in src and "'SAAS'" not in src
