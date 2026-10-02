"""WO-COMM-V3-07A-PATCH-003 — Renewal Single-Payment Canonical Wiring.

RVB07  : CUSTOM tier in CV → CUSTOM_REVIEW_REQUIRED (_validate_renewal_router_context)
RVB08  : missing commercial_v3_renewal binding → NOT_RENEWAL_QUOTE
RVB09  : current_version_no mismatch → RENEWAL_VERSION_MISMATCH
P07    : /renewal/vbank/prepare endpoint 존재하지 않음 (소스 검사)
P08    : classify_renewal_runtime_route(RENEWAL+SAAS+Card)=V2
P09    : classify_renewal_runtime_route(RENEWAL+SAAS+DirectBank)=V2
P10    : on_payment_success_sync(payment_type=RENEWAL,pg_method=VBANK) →
         apply_saas_v2_renewal_runtime 호출
P11    : on_payment_success_sync(payment_type=RENEWAL,pg_method=VBANK) →
         apply_saas_v2_initial_payment_runtime 미호출

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

_SUPPLY = 300_000
_VAT = 30_000
_TOTAL = 330_000
_TERM = 6

_NOW = datetime(2026, 9, 1, 10, 0, 0, tzinfo=timezone.utc)
_END_DATE = "2027-04-01"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _valid_renewal_quote():
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


def _make_router_sb(cv_rows=None):
    sb = MagicMock()

    def _table(name):
        t = MagicMock()
        if name == "saas_contract_commercial_versions":
            t.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
                data=cv_rows if cv_rows is not None else [_valid_cv()]
            )
        elif name == "contracts":
            t.select.return_value.eq.return_value.limit.return_value.execute.return_value = SimpleNamespace(
                data=[_valid_contract()]
            )
        return t

    sb.table.side_effect = _table
    return sb


# ── RVB07-RVB09: _validate_renewal_router_context guards ─────────────────────

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
                sb, quote_id=_QUOTE_ID, company_id=_COMPANY_ID, user_id=_USER_ID,
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
                sb, quote_id=_QUOTE_ID, company_id=_COMPANY_ID, user_id=_USER_ID,
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
                sb, quote_id=_QUOTE_ID, company_id=_COMPANY_ID, user_id=_USER_ID,
            )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "RENEWAL_VERSION_MISMATCH"


# ── P07: /renewal/vbank/prepare 엔드포인트 부재 ───────────────────────────────

def test_P07_renewal_vbank_endpoint_removed():
    """P07: POST /renewal/vbank/prepare 엔드포인트가 member_quotes에 존재하지 않음."""
    import inspect
    import routers.member_quotes as mq

    src = inspect.getsource(mq)
    assert "/renewal/vbank/prepare" not in src, (
        "PATCH-003: /renewal/vbank/prepare 엔드포인트는 제거되어야 합니다"
    )


# ── P08-P09: classify_renewal_runtime_route — pg_method 무관 V2 ──────────────

def test_P08_renewal_card_routes_to_v2():
    """P08: payment_type=RENEWAL + product_type=SAAS + pg_method=Card → V2."""
    from services.saas_renewal_runtime_v2 import classify_renewal_runtime_route

    pay = {"payment_type": "RENEWAL", "product_type": "SAAS", "pg_method": "Card"}
    assert classify_renewal_runtime_route(pay) == "V2"


def test_P09_renewal_directbank_routes_to_v2():
    """P09: payment_type=RENEWAL + product_type=SAAS + pg_method=DirectBank → V2."""
    from services.saas_renewal_runtime_v2 import classify_renewal_runtime_route

    pay = {"payment_type": "RENEWAL", "product_type": "SAAS", "pg_method": "DirectBank"}
    assert classify_renewal_runtime_route(pay) == "V2"


# ── P10-P11: on_payment_success_sync RENEWAL+VBANK deposit → renewal runtime ─

def test_P10_renewal_vbank_deposit_routes_to_renewal_runtime():
    """P10: on_payment_success_sync(RENEWAL+pg_method=VBANK) → apply_saas_v2_renewal_runtime."""
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

    def _fake_renewal(sb, pay):
        renewal_called.append(pay.get("payment_type"))
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
    ):
        on_payment_success_sync(_PAY_ID)

    assert len(renewal_called) == 1
    assert renewal_called[0] == "RENEWAL"


def test_P11_renewal_vbank_does_not_call_initial_runtime():
    """P11: on_payment_success_sync(RENEWAL+VBANK) → apply_saas_v2_initial_payment_runtime 미호출."""
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

    initial_called = []

    def _fake_initial(sb, pay):
        initial_called.append(True)
        return {"status": "APPLIED"}

    with (
        patch("services.payment_post_process.get_supabase", return_value=sb),
        patch("services.payment_post_process._bootstrap_buyer_company_admin"),
        patch("services.payment_post_process._fire_automation"),
        patch("services.payment_post_process.send_payment_notification"),
        patch(
            "services.saas_renewal_runtime_v2.apply_saas_v2_renewal_runtime",
            return_value={"status": "APPLIED"},
        ),
        patch(
            "services.saas_initial_payment_runtime_v2.apply_saas_v2_initial_payment_runtime",
            side_effect=_fake_initial,
        ),
    ):
        on_payment_success_sync(_PAY_ID)

    assert len(initial_called) == 0, "apply_saas_v2_initial_payment_runtime 호출 금지"
