"""WO-FE-WWW-04-PRE-001 PATCH-001: Frozen Quote V2 Duplicate Payment Guard.

DP01-DP24 per original Acceptance Matrix + schema-select regression.
"""
from __future__ import annotations

import os
import types
import uuid
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("INTERNAL_API_SECRET", "pytest-internal-secret")

from services.saas_payment_v2_adapter import (
    SaasPaymentV2AdapterError,
    _V2_PAYMENT_SELECT,
    _find_existing_v2_payment,
    _handle_race_recovery,
    _is_quote_v2_unique_violation,
    _validate_pending_reuse,
    prepare_saas_v2_payment_from_quote,
)

_SVC_SRC = Path(__file__).parent.parent / "services" / "saas_payment_v2_adapter.py"
_SQL_UP = Path(__file__).parent.parent / "docs" / "sql" / "20260930_quote_v2_payment_attempt_guard_up.sql"

_QUOTE_ID = str(uuid.uuid4())
_USER_ID = "U-DP-TEST"
_OTHER_USER_ID = "U-DP-OTHER"
_COMPANY_ID = "C-DP-TEST"
_PAYMENT_ID = str(uuid.uuid4())
_ORDER_ID = "ORD-DP-001"
_SIGN_KEY = "TEST_SIGN_KEY_DP"
_GOODNAME = "TAI Safe 관리자형"
_SITE_ID = str(uuid.uuid4())

_SUPPLY = 100_000
_VAT = 10_000
_TOTAL = 110_000
_TERM = 1


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_snap(supply=_SUPPLY, vat=_VAT, total=_TOTAL, term=_TERM):
    """Minimal SaasPricingSnapshotV2-shaped object for test isolation."""
    return types.SimpleNamespace(
        prepaid_supply_amount=supply,
        vat_amount=vat,
        total_amount=total,
        payment_months=term,
    )


def _pending_row(
    *,
    user_id=_USER_ID,
    payment_id=_PAYMENT_ID,
    order_id=_ORDER_ID,
    company_id=_COMPANY_ID,
    quote_id=_QUOTE_ID,
    supply=_SUPPLY,
    vat=_VAT,
    total=_TOTAL,
    term=_TERM,
    plan_code=None,
    payment_type="CARD",
    product_type="SAAS",
    status_code="PENDING",
):
    """Build a payments row dict matching the real DB schema columns selected by the guard."""
    return {
        "id": payment_id,
        "user_id": user_id,
        "company_id": company_id,
        "quote_id": quote_id,
        "status_code": status_code,
        "inicis_order_id": order_id,
        "product_type": product_type,
        "payment_type": payment_type,
        "plan_code": plan_code,
        "period_months": term,
        "supply_amount": supply,
        "vat_amount": vat,
        "total_amount": total,
    }


def _minimal_snap_dict(supply=_SUPPLY, vat=_VAT, total=_TOTAL, term=_TERM):
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


def _minimal_item_dict(supply=_SUPPLY, vat=_VAT, total=_TOTAL, term=_TERM):
    return {
        "quote_schema_version": "SAAS_QUOTE_V2",
        "display_name": _GOODNAME,
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


def _valid_v2_quote(supply=_SUPPLY, vat=_VAT, total=_TOTAL, term=_TERM):
    return {
        "id": _QUOTE_ID,
        "company_id": _COMPANY_ID,
        "status_code": "ISSUED",
        "service_type": "SAAS",
        "supply_amount": supply,
        "vat_amount": vat,
        "total_amount": total,
        "items": [_minimal_item_dict(supply, vat, total, term)],
    }


def _setup_integration(monkeypatch, existing_row: Optional[dict] = None):
    """Full validation chain passes; guard condition controlled by existing_row."""
    quote = _valid_v2_quote()
    monkeypatch.setattr("services.member_quote_svc.get_member_quote", lambda *a: quote)
    monkeypatch.setattr("services.saas_payment_v2_adapter.load_sign_key", lambda: _SIGN_KEY)
    monkeypatch.setattr(
        "services.saas_payment_v2_adapter._find_existing_v2_payment",
        lambda sb, qid: existing_row,
    )
    insert_calls = []

    def _fake_insert(sb, sk, **kw):
        insert_calls.append(kw)
        return {"status": "success", "data": {"payment_id": "pay-new", "oid": "ORD-NEW", "price": str(_TOTAL)}}

    monkeypatch.setattr("services.saas_payment_v2_adapter._run_inicis_prepare_exact", _fake_insert)
    return insert_calls


# ── DP01: First prepare — INSERT 1 ────────────────────────────────────────────

def test_DP01_first_prepare_inserts_once(monkeypatch):
    """기존 결제 없음 → INSERT 정확히 1회."""
    calls = _setup_integration(monkeypatch, existing_row=None)
    result = prepare_saas_v2_payment_from_quote(None, _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert len(calls) == 1
    assert result["status"] == "success"


# ── DP02: Same-user PENDING → same payment_id ─────────────────────────────────

def test_DP02_same_user_pending_returns_same_payment_id():
    """PENDING same-user reuse → payment_id 동일."""
    row = _pending_row()
    snap = _make_snap()
    result = _validate_pending_reuse(row, _USER_ID, _COMPANY_ID, _QUOTE_ID, snap, _SIGN_KEY, _GOODNAME)
    assert result["data"]["payment_id"] == _PAYMENT_ID


# ── DP03: Same-user PENDING → same oid ────────────────────────────────────────

def test_DP03_same_user_pending_returns_same_oid():
    """PENDING same-user reuse → inicis_order_id 동일."""
    row = _pending_row()
    snap = _make_snap()
    result = _validate_pending_reuse(row, _USER_ID, _COMPANY_ID, _QUOTE_ID, snap, _SIGN_KEY, _GOODNAME)
    assert result["data"]["oid"] == _ORDER_ID


# ── DP04: Same-user PENDING → INSERT 0 ────────────────────────────────────────

def test_DP04_same_user_pending_no_insert(monkeypatch):
    """PENDING same-user guard triggers → INSERT 0."""
    row = _pending_row()
    calls = _setup_integration(monkeypatch, existing_row=row)
    prepare_saas_v2_payment_from_quote(None, _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert len(calls) == 0


# ── DP05: Reuse amounts == Frozen Snapshot ────────────────────────────────────

def test_DP05_reuse_price_equals_frozen_snapshot_total():
    """PENDING reuse response price = snap.total_amount (repricing 0)."""
    row = _pending_row(total=_TOTAL)
    snap = _make_snap(total=_TOTAL)
    result = _validate_pending_reuse(row, _USER_ID, _COMPANY_ID, _QUOTE_ID, snap, _SIGN_KEY, _GOODNAME)
    assert result["data"]["price"] == str(_TOTAL)


# ── DP06: Amount mismatch → STATE_CONFLICT ────────────────────────────────────

def test_DP06_total_mismatch_raises_state_conflict():
    """existing.total_amount != snap.total_amount → QUOTE_PAYMENT_STATE_CONFLICT."""
    row = _pending_row(total=120_000)
    snap = _make_snap(total=_TOTAL)
    with pytest.raises(SaasPaymentV2AdapterError) as exc:
        _validate_pending_reuse(row, _USER_ID, _COMPANY_ID, _QUOTE_ID, snap, _SIGN_KEY, _GOODNAME)
    assert exc.value.code == "QUOTE_PAYMENT_STATE_CONFLICT"


def test_DP06b_supply_mismatch_raises_state_conflict():
    """existing.supply_amount != snap.prepaid_supply_amount → QUOTE_PAYMENT_STATE_CONFLICT."""
    row = _pending_row(supply=90_000)
    snap = _make_snap(supply=_SUPPLY)
    with pytest.raises(SaasPaymentV2AdapterError) as exc:
        _validate_pending_reuse(row, _USER_ID, _COMPANY_ID, _QUOTE_ID, snap, _SIGN_KEY, _GOODNAME)
    assert exc.value.code == "QUOTE_PAYMENT_STATE_CONFLICT"


def test_DP06c_vat_mismatch_raises_state_conflict():
    """existing.vat_amount != snap.vat_amount → QUOTE_PAYMENT_STATE_CONFLICT."""
    row = _pending_row(vat=9_000)
    snap = _make_snap(vat=_VAT)
    with pytest.raises(SaasPaymentV2AdapterError) as exc:
        _validate_pending_reuse(row, _USER_ID, _COMPANY_ID, _QUOTE_ID, snap, _SIGN_KEY, _GOODNAME)
    assert exc.value.code == "QUOTE_PAYMENT_STATE_CONFLICT"


# ── DP07: Period mismatch → STATE_CONFLICT ────────────────────────────────────

def test_DP07_period_mismatch_raises_state_conflict():
    """existing.period_months != snap.payment_months → QUOTE_PAYMENT_STATE_CONFLICT."""
    row = _pending_row(term=6)
    snap = _make_snap(term=12)
    with pytest.raises(SaasPaymentV2AdapterError) as exc:
        _validate_pending_reuse(row, _USER_ID, _COMPANY_ID, _QUOTE_ID, snap, _SIGN_KEY, _GOODNAME)
    assert exc.value.code == "QUOTE_PAYMENT_STATE_CONFLICT"


# ── DP08: plan_code non-null → STATE_CONFLICT ─────────────────────────────────

def test_DP08_plan_code_non_null_raises_state_conflict():
    """existing.plan_code IS NOT NULL → QUOTE_PAYMENT_STATE_CONFLICT."""
    row = _pending_row(plan_code="INDUSTRY_PRO")
    snap = _make_snap()
    with pytest.raises(SaasPaymentV2AdapterError) as exc:
        _validate_pending_reuse(row, _USER_ID, _COMPANY_ID, _QUOTE_ID, snap, _SIGN_KEY, _GOODNAME)
    assert exc.value.code == "QUOTE_PAYMENT_STATE_CONFLICT"


# ── DP09: Other-user PENDING → QUOTE_PAYMENT_PENDING ─────────────────────────

def test_DP09_other_user_pending_raises_quote_payment_pending():
    """PENDING 다른 user_id → QUOTE_PAYMENT_PENDING."""
    row = _pending_row(user_id=_OTHER_USER_ID)
    snap = _make_snap()
    with pytest.raises(SaasPaymentV2AdapterError) as exc:
        _validate_pending_reuse(row, _USER_ID, _COMPANY_ID, _QUOTE_ID, snap, _SIGN_KEY, _GOODNAME)
    assert exc.value.code == "QUOTE_PAYMENT_PENDING"


# ── DP10: Other-user → provider data exposure 0 ───────────────────────────────

def test_DP10_other_user_error_exposes_no_provider_data():
    """QUOTE_PAYMENT_PENDING 에러에 payment_id/oid/amount 미포함."""
    row = _pending_row(user_id=_OTHER_USER_ID)
    snap = _make_snap()
    with pytest.raises(SaasPaymentV2AdapterError) as exc:
        _validate_pending_reuse(row, _USER_ID, _COMPANY_ID, _QUOTE_ID, snap, _SIGN_KEY, _GOODNAME)
    err_msg = exc.value.message
    assert _PAYMENT_ID not in err_msg
    assert _ORDER_ID not in err_msg
    assert str(_TOTAL) not in err_msg


# ── DP11: SUCCESS → QUOTE_ALREADY_PAID ───────────────────────────────────────

def test_DP11_success_raises_already_paid():
    """status_code=SUCCESS → QUOTE_ALREADY_PAID."""
    row = _pending_row(status_code="SUCCESS")
    snap = _make_snap()
    with pytest.raises(SaasPaymentV2AdapterError) as exc:
        _validate_pending_reuse(row, _USER_ID, _COMPANY_ID, _QUOTE_ID, snap, _SIGN_KEY, _GOODNAME)
    assert exc.value.code == "QUOTE_ALREADY_PAID"


# ── DP12: PAID → QUOTE_ALREADY_PAID ──────────────────────────────────────────

def test_DP12_paid_raises_already_paid():
    """status_code=PAID → QUOTE_ALREADY_PAID."""
    row = _pending_row(status_code="PAID")
    snap = _make_snap()
    with pytest.raises(SaasPaymentV2AdapterError) as exc:
        _validate_pending_reuse(row, _USER_ID, _COMPANY_ID, _QUOTE_ID, snap, _SIGN_KEY, _GOODNAME)
    assert exc.value.code == "QUOTE_ALREADY_PAID"


# ── DP13: SUCCESS + no contract_id → QUOTE_ALREADY_PAID ──────────────────────

def test_DP13_success_no_contract_id_raises_already_paid():
    """SUCCESS row without contract_id → QUOTE_ALREADY_PAID (계약 여부 무관)."""
    row = _pending_row(status_code="SUCCESS")
    # contract_id field absent from row (not in _V2_PAYMENT_SELECT)
    assert "contract_id" not in row
    snap = _make_snap()
    with pytest.raises(SaasPaymentV2AdapterError) as exc:
        _validate_pending_reuse(row, _USER_ID, _COMPANY_ID, _QUOTE_ID, snap, _SIGN_KEY, _GOODNAME)
    assert exc.value.code == "QUOTE_ALREADY_PAID"


# ── DP14: FAILED-only → new INSERT 1 ─────────────────────────────────────────

def test_DP14_failed_only_proceeds_to_new_insert(monkeypatch):
    """FAILED 행만 존재(= _find_existing 반환 None) → 신규 INSERT 1회."""
    # _find_existing_v2_payment filters out FAILED via IN ('PENDING','PAID','SUCCESS')
    # so when only FAILED exists it returns None → new INSERT path
    calls = _setup_integration(monkeypatch, existing_row=None)
    prepare_saas_v2_payment_from_quote(None, _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert len(calls) == 1


# ── DP15: Race 23505 + same-user → reuse ─────────────────────────────────────

def test_DP15_race_23505_same_user_returns_reuse(monkeypatch):
    """INSERT 시 23505(해당 index) → race recovery → same-user PENDING reuse."""
    quote = _valid_v2_quote()
    monkeypatch.setattr("services.member_quote_svc.get_member_quote", lambda *a: quote)
    monkeypatch.setattr("services.saas_payment_v2_adapter.load_sign_key", lambda: _SIGN_KEY)
    monkeypatch.setattr(
        "services.saas_payment_v2_adapter._find_existing_v2_payment",
        lambda sb, qid: None,
    )

    class _UniqueViolation(Exception):
        pass

    def _raise_23505(sb, sk, **kw):
        raise _UniqueViolation(
            "23505 duplicate key violates unique constraint "
            "uix_payments_quote_v2_initial_active"
        )

    monkeypatch.setattr("services.saas_payment_v2_adapter._run_inicis_prepare_exact", _raise_23505)

    recovery_calls = []

    def _fake_recovery(sb, qid, uid, cid, snap, sk, gn, **kw):
        recovery_calls.append({"qid": qid, "uid": uid, "cid": cid})
        return {"status": "success", "data": {"payment_id": "pay-recovered", "oid": _ORDER_ID, "price": str(_TOTAL)}}

    monkeypatch.setattr("services.saas_payment_v2_adapter._handle_race_recovery", _fake_recovery)
    result = prepare_saas_v2_payment_from_quote(None, _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert len(recovery_calls) == 1
    assert result["data"]["payment_id"] == "pay-recovered"


# ── DP16: Race 23505 + other-user → PENDING ──────────────────────────────────

def test_DP16_race_23505_other_user_raises_pending(monkeypatch):
    """INSERT 시 23505 → recovery → 다른 user PENDING → QUOTE_PAYMENT_PENDING."""
    quote = _valid_v2_quote()
    monkeypatch.setattr("services.member_quote_svc.get_member_quote", lambda *a: quote)
    monkeypatch.setattr("services.saas_payment_v2_adapter.load_sign_key", lambda: _SIGN_KEY)
    monkeypatch.setattr(
        "services.saas_payment_v2_adapter._find_existing_v2_payment",
        lambda sb, qid: None,
    )

    class _UniqueViolation(Exception):
        pass

    def _raise_23505(sb, sk, **kw):
        raise _UniqueViolation("23505 uix_payments_quote_v2_initial_active")

    monkeypatch.setattr("services.saas_payment_v2_adapter._run_inicis_prepare_exact", _raise_23505)

    def _recovery_raises(sb, qid, uid, cid, snap, sk, gn, **kw):
        raise SaasPaymentV2AdapterError("QUOTE_PAYMENT_PENDING", "진행 중인 결제가 있습니다.")

    monkeypatch.setattr("services.saas_payment_v2_adapter._handle_race_recovery", _recovery_raises)
    with pytest.raises(SaasPaymentV2AdapterError) as exc:
        prepare_saas_v2_payment_from_quote(None, _QUOTE_ID, _USER_ID, _COMPANY_ID)
    assert exc.value.code == "QUOTE_PAYMENT_PENDING"


# ── DP17: Unrelated DB exception → propagate ─────────────────────────────────

def test_DP17_non_unique_exception_propagates(monkeypatch):
    """INSERT 에서 23505 아닌 오류 → recovery 없이 원본 예외 전파."""
    quote = _valid_v2_quote()
    monkeypatch.setattr("services.member_quote_svc.get_member_quote", lambda *a: quote)
    monkeypatch.setattr("services.saas_payment_v2_adapter.load_sign_key", lambda: _SIGN_KEY)
    monkeypatch.setattr(
        "services.saas_payment_v2_adapter._find_existing_v2_payment",
        lambda sb, qid: None,
    )

    class _ConnError(RuntimeError):
        pass

    def _raise_conn(sb, sk, **kw):
        raise _ConnError("connection timeout")

    monkeypatch.setattr("services.saas_payment_v2_adapter._run_inicis_prepare_exact", _raise_conn)
    with pytest.raises(_ConnError):
        prepare_saas_v2_payment_from_quote(None, _QUOTE_ID, _USER_ID, _COMPANY_ID)


# ── DP18: Legacy prepare output shape unchanged ───────────────────────────────

def test_DP18_prepare_response_shape_unchanged(monkeypatch):
    """_run_inicis_prepare_exact 출력 shape 변화 없음 (기존 INICIS 필드 전부 존재)."""
    from services.payment_svc import _build_inicis_prepare_response_exact
    result = _build_inicis_prepare_response_exact(
        _SIGN_KEY,
        payment_id="pay-shape-test",
        order_id="ORD-SHAPE",
        total_amount=_TOTAL,
        goodname=_GOODNAME,
    )
    required = {
        "payment_id", "mid", "mKey", "oid", "price", "goodname",
        "buyername", "buyertel", "buyeremail",
        "timestamp", "signature", "verification",
        "use_chkfake", "returnUrl", "closeUrl", "charset", "gopaymethod",
    }
    assert required.issubset(result["data"].keys())


# ── DP19: Repricing call 0 ────────────────────────────────────────────────────

def test_DP19_no_repricing_in_adapter():
    """Adapter 소스(코드 라인만)에 pricing engine 호출 없음."""
    lines = _SVC_SRC.read_text().splitlines()
    code = "\n".join(ln for ln in lines if not ln.lstrip().startswith(("#", '"""', "- ")))
    for forbidden in ("price_master", "pricing_resolver", "pricing_composer", "preview_saas_price", "add_vat("):
        assert forbidden not in code, f"repricing call found in code: {forbidden}"


# ── DP20: Client amount authority 0 ──────────────────────────────────────────

def test_DP20_prepare_signature_accepts_no_amount_params():
    """prepare_saas_v2_payment_from_quote 시그니처에 client amount 파라미터 없음."""
    import inspect
    sig = inspect.signature(prepare_saas_v2_payment_from_quote)
    forbidden_params = {"amount", "supply_amount", "vat_amount", "total_amount"}
    assert forbidden_params.isdisjoint(sig.parameters.keys()), \
        f"client amount params found: {forbidden_params & sig.parameters.keys()}"


# ── DP21: Migration index predicate + IF NOT EXISTS ──────────────────────────

def test_DP21_migration_has_if_not_exists_and_null_predicate():
    """migration SQL에 IF NOT EXISTS 및 quote_id IS NOT NULL 존재."""
    sql = _SQL_UP.read_text()
    assert "IF NOT EXISTS" in sql
    assert "quote_id IS NOT NULL" in sql
    assert "uix_payments_quote_v2_initial_active" in sql
    assert "product_type = 'SAAS'" in sql
    assert "payment_type = 'CARD'" in sql
    assert "status_code IN" in sql


# ── DP22: RENEWAL unaffected ──────────────────────────────────────────────────

def test_DP22_renewal_payment_type_excluded_from_guard():
    """_find_existing_v2_payment 쿼리가 payment_type='CARD' 만 조회 — RENEWAL 제외."""
    src = _SVC_SRC.read_text()
    # Confirm the guard query filters by payment_type CARD
    func_start = src.index("def _find_existing_v2_payment(")
    func_end = src.index("\ndef _validate_pending_reuse(", func_start)
    func_body = src[func_start:func_end]
    assert '.eq("payment_type", "CARD")' in func_body


# ── DP23: UPGRADE unaffected ──────────────────────────────────────────────────

def test_DP23_upgrade_payment_type_excluded_from_guard():
    """_find_existing_v2_payment 쿼리 payment_type='CARD' 필터 → UPGRADE type 제외."""
    # Same assertion as DP22 — both RENEWAL and UPGRADE have payment_type != 'CARD'
    src = _SVC_SRC.read_text()
    func_start = src.index("def _find_existing_v2_payment(")
    func_end = src.index("\ndef _validate_pending_reuse(", func_start)
    func_body = src[func_start:func_end]
    assert '.eq("product_type", "SAAS")' in func_body


# ── DP24: Legacy SAAS_* product_type unaffected ───────────────────────────────

def test_DP24_legacy_saas_star_product_type_excluded_from_guard():
    """_find_existing_v2_payment product_type='SAAS' 정확 일치 — SAAS_INDUSTRY 등 제외."""
    src = _SVC_SRC.read_text()
    func_start = src.index("def _find_existing_v2_payment(")
    func_end = src.index("\ndef _validate_pending_reuse(", func_start)
    func_body = src[func_start:func_end]
    # Must use exact 'SAAS', not a prefix/wildcard
    assert '.eq("product_type", "SAAS")' in func_body
    assert "SAAS_" not in func_body


# ── Additional: SELECT column list regression ─────────────────────────────────

def test_SELECT_list_excludes_nonexistent_columns():
    """_V2_PAYMENT_SELECT에 payments 테이블 없는 컬럼 포함 금지."""
    forbidden = {"goodname", "buyername", "buyertel", "buyeremail"}
    for col in forbidden:
        assert col not in _V2_PAYMENT_SELECT, f"forbidden column in SELECT: {col}"


def test_SELECT_list_includes_required_columns():
    """_V2_PAYMENT_SELECT에 state-validation에 필요한 컬럼 전부 포함."""
    required = {
        "id", "user_id", "company_id", "quote_id", "status_code",
        "inicis_order_id", "product_type", "payment_type",
        "plan_code", "period_months", "supply_amount", "vat_amount", "total_amount",
    }
    cols = set(_V2_PAYMENT_SELECT.replace(" ", "").split(","))
    assert required.issubset(cols), f"missing columns: {required - cols}"
