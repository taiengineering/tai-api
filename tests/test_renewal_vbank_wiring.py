"""WO-COMM-V3-07A-RENEWAL-VBANK-WIRING-001 — Renewal VBANK adapter + routing tests.

RVB01  : payment_type=RENEWAL passed to _run_inicis (not VBANK)
RVB02  : pg_method=VBANK stored via payments.update after INSERT
RVB03  : contract_id passed through to _run_inicis
RVB04  : plan_code=None passed to _run_inicis (V3 invariant)
RVB05  : payment_months=1 → VBANK_NOT_SUPPORTED_FOR_RECURRING
RVB06  : payment_months ∈ {3,6,9,12} → success (each value)
RVB07  : CUSTOM tier in CV → CUSTOM_REVIEW_REQUIRED (router context)
RVB08  : missing commercial_v3_renewal binding → NOT_RENEWAL_QUOTE
RVB09  : current_version_no mismatch → RENEWAL_VERSION_MISMATCH
RVB10  : response gopaymethod=Vbank and vbankexpire present
RVB11  : classify_renewal_runtime_route(RENEWAL+SAAS+VBANK)=V2 (pure)
RVB12  : on_payment_success_sync(payment_type=RENEWAL,pg_method=VBANK) →
         apply_saas_v2_renewal_runtime called; apply_saas_v2_initial_payment_runtime NOT called

DB/네트워크 없음 — FakeSupabase + monkeypatch 전용.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("INTERNAL_API_SECRET", "pytest-internal-secret")

_CONTRACT_ID = str(uuid.uuid4())
_COMPANY_ID = str(uuid.uuid4())
_USER_ID = str(uuid.uuid4())
_QUOTE_ID = str(uuid.uuid4())
_CV_ID = str(uuid.uuid4())
_PAY_ID = str(uuid.uuid4())
_ORDER_ID = "RVB-ORD-001"
_SITE_ID = str(uuid.uuid4())

_SUPPLY = 300_000
_VAT = 30_000
_TOTAL = 330_000
_TERM = 6  # single-pay 6 months

_NOW = datetime(2026, 9, 1, 10, 0, 0, tzinfo=timezone.utc)
_END_DATE = "2027-04-01"


# ── Shared Factories ──────────────────────────────────────────────────────────

def _snap(payment_months=_TERM, supply=_SUPPLY, vat=_VAT, total=_TOTAL):
    return SimpleNamespace(
        payment_months=payment_months,
        prepaid_supply_amount=supply,
        vat_amount=vat,
        total_amount=total,
    )


def _item(payment_months=_TERM):
    return SimpleNamespace(
        display_name="TAI Safe 현장참여형 갱신 6개월",
        supply_amount=_SUPPLY,
        vat_amount=_VAT,
        total_amount=_TOTAL,
        pricing_snapshot=_snap(payment_months),
    )


def _make_quote(payment_months=_TERM):
    return {"id": _QUOTE_ID, "company_id": _COMPANY_ID, "status_code": "ISSUED"}


def _fake_run_success(supabase, sign_key, **kw):
    return {
        "status": "success",
        "data": {
            "payment_id": _PAY_ID,
            "oid": _ORDER_ID,
            "price": str(_TOTAL),
            "gopaymethod": "",
        },
    }


def _make_sb():
    sb = MagicMock()
    sb.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
    return sb


def _adapter_patches(payment_months=_TERM, **kw):
    """Context-manager stack for adapter-level tests."""
    snap = _snap(payment_months)
    item = _item(payment_months)
    return (
        patch("services.saas_renewal_v2_adapter._fetch_and_validate_contract", return_value=None),
        patch("services.saas_renewal_v2_adapter._validate_renewal_quote", return_value=(_make_quote(), item, snap)),
        patch("services.saas_renewal_v2_adapter.load_sign_key", return_value="SIGN"),
        patch("services.saas_renewal_v2_adapter._run_inicis_prepare_exact",
              side_effect=kw.get("run_side_effect", _fake_run_success)),
        patch("services.saas_renewal_v2_adapter.now_kst", return_value=_NOW),
        patch("services.saas_renewal_v2_adapter._renewal_now_iso", return_value="2026-09-01T10:00:00Z"),
    )


# ── RVB01-RVB10: Adapter-level tests ─────────────────────────────────────────

def test_RVB01_payment_type_is_renewal_not_vbank():
    """RVB01: _run_inicis_prepare_exact receives payment_type=RENEWAL, not VBANK."""
    from services.saas_renewal_v2_adapter import prepare_saas_v2_renewal_vbank_from_quote
    captured = {}

    def _capture(supabase, sign_key, *, payment_type, **kw):
        captured["payment_type"] = payment_type
        return _fake_run_success(supabase, sign_key)

    patches = _adapter_patches(run_side_effect=_capture)
    sb = _make_sb()
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
        prepare_saas_v2_renewal_vbank_from_quote(
            sb,
            contract_id=_CONTRACT_ID,
            quote_id=_QUOTE_ID,
            company_id=_COMPANY_ID,
            user_id=_USER_ID,
            as_of=_NOW,
        )

    assert captured["payment_type"] == "RENEWAL"


def test_RVB02_pg_method_vbank_stored_via_update():
    """RVB02: payments.update called with pg_method=VBANK after INSERT."""
    from services.saas_renewal_v2_adapter import prepare_saas_v2_renewal_vbank_from_quote
    update_calls = []
    sb = _make_sb()

    original_table = sb.table.side_effect
    def _track_table(name):
        t = MagicMock()
        if name == "payments":
            t.update.side_effect = lambda d: (update_calls.append(d), MagicMock(
                eq=MagicMock(return_value=MagicMock(execute=MagicMock(return_value=MagicMock(data=[]))))
            ))[1]
        return t
    sb.table.side_effect = _track_table

    patches = _adapter_patches()
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
        prepare_saas_v2_renewal_vbank_from_quote(
            sb,
            contract_id=_CONTRACT_ID,
            quote_id=_QUOTE_ID,
            company_id=_COMPANY_ID,
            user_id=_USER_ID,
            as_of=_NOW,
        )

    assert any(c.get("pg_method") == "VBANK" for c in update_calls)


def test_RVB03_contract_id_passed_to_run_inicis():
    """RVB03: contract_id forwarded to _run_inicis_prepare_exact."""
    from services.saas_renewal_v2_adapter import prepare_saas_v2_renewal_vbank_from_quote
    captured = {}

    def _capture(supabase, sign_key, *, contract_id, **kw):
        captured["contract_id"] = contract_id
        return _fake_run_success(supabase, sign_key)

    patches = _adapter_patches(run_side_effect=_capture)
    sb = _make_sb()
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
        prepare_saas_v2_renewal_vbank_from_quote(
            sb,
            contract_id=_CONTRACT_ID,
            quote_id=_QUOTE_ID,
            company_id=_COMPANY_ID,
            user_id=_USER_ID,
            as_of=_NOW,
        )

    assert captured["contract_id"] == _CONTRACT_ID


def test_RVB04_plan_code_none():
    """RVB04: plan_code=None passed to _run_inicis_prepare_exact (V3 invariant)."""
    from services.saas_renewal_v2_adapter import prepare_saas_v2_renewal_vbank_from_quote
    captured = {}

    def _capture(supabase, sign_key, *, plan_code, **kw):
        captured["plan_code"] = plan_code
        return _fake_run_success(supabase, sign_key)

    patches = _adapter_patches(run_side_effect=_capture)
    sb = _make_sb()
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
        prepare_saas_v2_renewal_vbank_from_quote(
            sb,
            contract_id=_CONTRACT_ID,
            quote_id=_QUOTE_ID,
            company_id=_COMPANY_ID,
            user_id=_USER_ID,
            as_of=_NOW,
        )

    assert captured["plan_code"] is None


def test_RVB05_payment_months_1_rejected():
    """RVB05: payment_months=1 → VBANK_NOT_SUPPORTED_FOR_RECURRING."""
    from services.saas_renewal_v2_adapter import (
        prepare_saas_v2_renewal_vbank_from_quote,
        SaasRenewalV2AdapterError,
    )
    patches = _adapter_patches(payment_months=1)
    sb = _make_sb()
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
        with pytest.raises(SaasRenewalV2AdapterError) as exc_info:
            prepare_saas_v2_renewal_vbank_from_quote(
                sb,
                contract_id=_CONTRACT_ID,
                quote_id=_QUOTE_ID,
                company_id=_COMPANY_ID,
                user_id=_USER_ID,
                as_of=_NOW,
            )

    assert exc_info.value.code == "VBANK_NOT_SUPPORTED_FOR_RECURRING"


@pytest.mark.parametrize("months", [3, 6, 9, 12])
def test_RVB06_allowed_payment_months(months):
    """RVB06: payment_months ∈ {3,6,9,12} → succeeds without exception."""
    from services.saas_renewal_v2_adapter import prepare_saas_v2_renewal_vbank_from_quote
    patches = _adapter_patches(payment_months=months)
    sb = _make_sb()
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
        result = prepare_saas_v2_renewal_vbank_from_quote(
            sb,
            contract_id=_CONTRACT_ID,
            quote_id=_QUOTE_ID,
            company_id=_COMPANY_ID,
            user_id=_USER_ID,
            as_of=_NOW,
        )

    assert result["status"] == "success"


def test_RVB10_response_gopaymethod_and_vbankexpire():
    """RVB10: response has gopaymethod=Vbank and vbankexpire field."""
    from services.saas_renewal_v2_adapter import (
        prepare_saas_v2_renewal_vbank_from_quote,
        _RENEWAL_VBANK_EXPIRE_MIN_DEFAULT,
    )
    patches = _adapter_patches()
    sb = _make_sb()
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
        result = prepare_saas_v2_renewal_vbank_from_quote(
            sb,
            contract_id=_CONTRACT_ID,
            quote_id=_QUOTE_ID,
            company_id=_COMPANY_ID,
            user_id=_USER_ID,
            as_of=_NOW,
        )

    assert result["data"]["gopaymethod"] == "Vbank"
    assert "vbankexpire" in result["data"]
    assert result["data"]["vbankexpire"] == _RENEWAL_VBANK_EXPIRE_MIN_DEFAULT


# ── RVB07-RVB09: Router context validation ────────────────────────────────────

def _valid_renewal_quote():
    """Quote with valid commercial_v3_renewal survey binding."""
    return {
        "id": _QUOTE_ID,
        "company_id": _COMPANY_ID,
        "status_code": "ISSUED",
        "service_type": "SAAS",
        "source": "member_auto",
        "survey_data": {
            "commercial_v3_renewal": {
                "contract_id": _CONTRACT_ID,
                "current_version_no": 2,
            }
        },
    }


def _valid_cv(version_no=2, product_tier="FIELD", payment_months=6):
    return {
        "id": _CV_ID,
        "contract_id": _CONTRACT_ID,
        "version_no": version_no,
        "commercial_schema_version": "SAAS_CONTRACT_COMMERCIAL_V2",
        "product_tier": product_tier,
        "pricing_mode": "STANDARD",
        "payment_months": payment_months,
        "effective_from": "2026-04-01T00:00:00+00:00",
        "superseded_at": None,
    }


def _valid_contract():
    return {
        "id": _CONTRACT_ID,
        "status_code": "ACTIVE",
        "service_type": "SAAS",
        "is_active": True,
        "end_date": _END_DATE,
    }


def _make_router_sb(cv_rows=None, contract_row=None):
    """FakeSupabase for router context tests."""
    sb = MagicMock()

    def _table(name):
        t = MagicMock()
        if name == "saas_contract_commercial_versions":
            t.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
                data=cv_rows if cv_rows is not None else [_valid_cv()]
            )
        elif name == "contracts":
            t.select.return_value.eq.return_value.limit.return_value.execute.return_value = SimpleNamespace(
                data=[contract_row] if contract_row else [_valid_contract()]
            )
        return t

    sb.table.side_effect = _table
    return sb


def test_RVB07_custom_tier_rejected():
    """RVB07: CV product_tier=CUSTOM → CUSTOM_REVIEW_REQUIRED (422)."""
    from fastapi import HTTPException
    from routers.member_quotes import _validate_renewal_router_context

    sb = _make_router_sb(cv_rows=[_valid_cv(product_tier="CUSTOM")])

    with (
        patch("services.member_quote_svc.get_member_quote", return_value=_valid_renewal_quote()),
        patch(
            "services.saas_commercial_version_time_v2.select_effective_commercial_version_v2",
            return_value=_valid_cv(product_tier="CUSTOM"),
        ),
        patch("services.time.now_kst", return_value=_NOW),
        patch("services.saas_renewal_payment_guard.check_existing_renewal_payment", return_value=None),
    ):
        with pytest.raises(HTTPException) as exc_info:
            _validate_renewal_router_context(
                sb,
                quote_id=_QUOTE_ID,
                company_id=_COMPANY_ID,
                user_id=_USER_ID,
            )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["code"] == "CUSTOM_REVIEW_REQUIRED"


def test_RVB08_missing_renewal_binding_rejected():
    """RVB08: quote without commercial_v3_renewal → NOT_RENEWAL_QUOTE (422)."""
    from fastapi import HTTPException
    from routers.member_quotes import _validate_renewal_router_context

    quote_no_binding = {
        "id": _QUOTE_ID,
        "company_id": _COMPANY_ID,
        "status_code": "ISSUED",
        "survey_data": {},
    }
    sb = _make_router_sb()

    with (
        patch("services.member_quote_svc.get_member_quote", return_value=quote_no_binding),
        patch("services.time.now_kst", return_value=_NOW),
    ):
        with pytest.raises(HTTPException) as exc_info:
            _validate_renewal_router_context(
                sb,
                quote_id=_QUOTE_ID,
                company_id=_COMPANY_ID,
                user_id=_USER_ID,
            )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["code"] == "NOT_RENEWAL_QUOTE"


def test_RVB09_version_mismatch_rejected():
    """RVB09: CV version_no ≠ quote current_version_no → RENEWAL_VERSION_MISMATCH (409)."""
    from fastapi import HTTPException
    from routers.member_quotes import _validate_renewal_router_context

    quote_v1 = _valid_renewal_quote()
    quote_v1["survey_data"]["commercial_v3_renewal"]["current_version_no"] = 1
    sb = _make_router_sb(cv_rows=[_valid_cv(version_no=2)])

    with (
        patch("services.member_quote_svc.get_member_quote", return_value=quote_v1),
        patch(
            "services.saas_commercial_version_time_v2.select_effective_commercial_version_v2",
            return_value=_valid_cv(version_no=2),
        ),
        patch("services.time.now_kst", return_value=_NOW),
    ):
        with pytest.raises(HTTPException) as exc_info:
            _validate_renewal_router_context(
                sb,
                quote_id=_QUOTE_ID,
                company_id=_COMPANY_ID,
                user_id=_USER_ID,
            )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "RENEWAL_VERSION_MISMATCH"


# ── RVB11-RVB12: Post-process routing ────────────────────────────────────────

def test_RVB11_classify_renewal_runtime_route_vbank_renewal_is_v2():
    """RVB11: payment_type=RENEWAL + product_type=SAAS + pg_method=VBANK → V2 route (pure)."""
    from services.saas_renewal_runtime_v2 import classify_renewal_runtime_route

    pay = {
        "payment_type": "RENEWAL",
        "product_type": "SAAS",
        "pg_method": "VBANK",
    }
    assert classify_renewal_runtime_route(pay) == "V2"


def test_RVB12_on_payment_success_sync_renewal_vbank_routes_to_renewal_runtime():
    """RVB12: on_payment_success_sync(payment_type=RENEWAL, pg_method=VBANK) →
    apply_saas_v2_renewal_runtime called; apply_saas_v2_initial_payment_runtime NOT called.
    """
    from services.payment_post_process import on_payment_success_sync

    payment_row = {
        "id": _PAY_ID,
        "status_code": "SUCCESS",
        "product_type": "SAAS",
        "payment_type": "RENEWAL",
        "pg_method": "VBANK",
        "user_id": _USER_ID,
        "company_id": _COMPANY_ID,
        "quote_id": _QUOTE_ID,
        "plan_code": None,
        "contract_id": _CONTRACT_ID,
        "total_amount": _TOTAL,
    }
    sb = MagicMock()
    sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[payment_row]
    )

    renewal_called = []
    initial_called = []

    def _fake_renewal(sb, pay):
        renewal_called.append(pay.get("payment_type"))
        return {"status": "APPLIED"}

    def _fake_initial(sb, pay):
        initial_called.append(pay.get("payment_type"))
        return {"status": "APPLIED"}

    with (
        patch("services.payment_post_process.get_supabase", return_value=sb),
        patch("services.payment_post_process._bootstrap_buyer_company_admin"),
        patch("services.payment_post_process._fire_automation"),
        patch("services.payment_post_process.send_payment_notification"),
        patch(
            "services.saas_renewal_runtime_v2.apply_saas_v2_renewal_runtime",
            side_effect=_fake_renewal,
        ),
        patch(
            "services.saas_initial_payment_runtime_v2.apply_saas_v2_initial_payment_runtime",
            side_effect=_fake_initial,
        ),
    ):
        on_payment_success_sync(_PAY_ID)

    assert len(renewal_called) == 1, "apply_saas_v2_renewal_runtime 정확히 1회 호출"
    assert renewal_called[0] == "RENEWAL"
    assert len(initial_called) == 0, "apply_saas_v2_initial_payment_runtime 호출 금지"
