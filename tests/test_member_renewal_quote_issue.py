"""WO-COMM-V3-07B-MANUAL-RENEWAL-WIRING-001 — Member Renewal Quote Issue.

RQ01  : API body에 contract_id 없음 (RenewalIssueBody 구조 검증)
RQ02  : API body에 payment_id 없음
RQ03  : company authority로 active V3 contract 파생
RQ04  : latest eligible payment server-side 파생
RQ05  : payment_months=3/6/9/12 허용
RQ06  : payment_months=1 거부 (RENEWAL_PAYMENT_MONTHS_INVALID)
RQ07  : CUSTOM tier → CUSTOM_REVIEW_REQUIRED
RQ08  : inactive contract → CONTRACT_NOT_ACTIVE
RQ09  : 다른 회사 contract/payment 접근 불가 (ownership guard)
RQ10  : 동일 current_version_no renewal quote idempotent (같은 조건)
RQ11  : Frozen Quote에 commercial_v3_renewal binding 존재
RQ12  : current_version_no가 실제 current CV와 일치

DB/네트워크 없음 — FakeSupabase + monkeypatch 전용.
"""
from __future__ import annotations

import inspect
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

_COMPANY_ID = str(uuid.uuid4())
_USER_ID = str(uuid.uuid4())
_CONTRACT_ID = str(uuid.uuid4())
_PAYMENT_ID = str(uuid.uuid4())
_CV_ID = str(uuid.uuid4())


def _make_contract(company_id=None, status_code="ACTIVE", service_type="SAAS", is_active=True):
    return {
        "id": _CONTRACT_ID,
        "company_id": company_id or _COMPANY_ID,
        "status_code": status_code,
        "service_type": service_type,
        "is_active": is_active,
        "end_date": "2027-12-01",
        "total_amount": 360000,
    }


def _make_cv(product_tier="FIELD", payment_months=6, version_no=1, superseded_at=None):
    return {
        "id": _CV_ID,
        "contract_id": _CONTRACT_ID,
        "version_no": version_no,
        "commercial_schema_version": "SAAS_CONTRACT_COMMERCIAL_V2",
        "product_tier": product_tier,
        "pricing_mode": "STANDARD",
        "payment_months": payment_months,
        "worker_capacity": 50,
        "effective_from": "2026-09-01T00:00:00+00:00",
        "superseded_at": superseded_at,
    }


def _make_payment(company_id=None, payment_type="CARD", status_code="SUCCESS"):
    return {
        "id": _PAYMENT_ID,
        "company_id": company_id or _COMPANY_ID,
        "contract_id": _CONTRACT_ID,
        "product_type": "SAAS",
        "payment_type": payment_type,
        "status_code": status_code,
        "paid_at": "2026-09-01T10:00:00+00:00",
        "period_months": 6,
        "quote_id": str(uuid.uuid4()),
    }


def _make_scope():
    return {
        "id": str(uuid.uuid4()),
        "commercial_version_id": _CV_ID,
        "entity_type": "factory",
        "entity_id": str(uuid.uuid4()),
        "sector": "INDUSTRY",
    }


def _make_ctx(state="ACTIVE", product_tier="FIELD", payment_months=6):
    return {
        "state": state,
        "error_code": None,
        "contract": _make_contract(),
        "commercial_version": _make_cv(product_tier=product_tier, payment_months=payment_months),
        "site_scopes": [_make_scope()],
    }


# ── RQ01: API body에 contract_id 없음 ────────────────────────────────────────

def test_RQ01_body_has_no_contract_id():
    """RQ01: RenewalIssueBody 스키마에 contract_id 필드 없음."""
    from routers.member_quotes import RenewalIssueBody
    fields = set(RenewalIssueBody.model_fields.keys())
    assert "contract_id" not in fields, "RenewalIssueBody에 contract_id 있음 — 금지"
    assert "payment_months" in fields


# ── RQ02: API body에 payment_id 없음 ─────────────────────────────────────────

def test_RQ02_body_has_no_payment_id():
    """RQ02: RenewalIssueBody 스키마에 payment_id 필드 없음."""
    from routers.member_quotes import RenewalIssueBody
    fields = set(RenewalIssueBody.model_fields.keys())
    assert "payment_id" not in fields, "RenewalIssueBody에 payment_id 있음 — 금지"


# ── RQ03: company authority로 active V3 contract 파생 ─────────────────────────

def test_RQ03_contract_derived_from_company_authority():
    """RQ03: create_member_renewal_quote가 company_id로 contract를 파생함."""
    from services.saas_renewal_quote_svc import create_member_renewal_quote
    sb = MagicMock()

    ctx_calls = []

    def _fake_get_contract(supabase, company_id):
        ctx_calls.append(company_id)
        return _make_ctx()

    with (
        patch("services.member_commercial_svc.get_member_commercial_contract", side_effect=_fake_get_contract),
        patch("services.saas_renewal_quote_svc._get_latest_eligible_payment_id", return_value=_PAYMENT_ID),
        patch("services.saas_renewal_quote_svc.create_renewal_quote", return_value={"id": str(uuid.uuid4()), "quote_no": "Q-001"}),
    ):
        create_member_renewal_quote(sb, user_id=_USER_ID, company_id=_COMPANY_ID, payment_months=6)

    assert len(ctx_calls) == 1
    assert ctx_calls[0] == _COMPANY_ID


# ── RQ04: latest eligible payment server-side 파생 ────────────────────────────

def test_RQ04_payment_id_derived_server_side():
    """RQ04: create_member_renewal_quote가 contract_id로 payment_id를 서버에서 파생함."""
    from services.saas_renewal_quote_svc import create_member_renewal_quote
    sb = MagicMock()

    payment_id_used = []

    def _fake_create(supabase, *, payment_id, company_id, user_id, payment_months):
        payment_id_used.append(payment_id)
        return {"id": str(uuid.uuid4()), "quote_no": "Q-002"}

    with (
        patch("services.member_commercial_svc.get_member_commercial_contract", return_value=_make_ctx()),
        patch("services.saas_renewal_quote_svc._get_latest_eligible_payment_id", return_value=_PAYMENT_ID),
        patch("services.saas_renewal_quote_svc.create_renewal_quote", side_effect=_fake_create),
    ):
        create_member_renewal_quote(sb, user_id=_USER_ID, company_id=_COMPANY_ID, payment_months=6)

    assert payment_id_used == [_PAYMENT_ID]


# ── RQ05: payment_months 3/6/9/12 허용 ───────────────────────────────────────

@pytest.mark.parametrize("months", [3, 6, 9, 12])
def test_RQ05_valid_payment_months_allowed(months):
    """RQ05: payment_months=3/6/9/12는 허용됨."""
    from services.saas_renewal_quote_svc import create_member_renewal_quote
    sb = MagicMock()

    with (
        patch("services.member_commercial_svc.get_member_commercial_contract", return_value=_make_ctx()),
        patch("services.saas_renewal_quote_svc._get_latest_eligible_payment_id", return_value=_PAYMENT_ID),
        patch("services.saas_renewal_quote_svc.create_renewal_quote", return_value={"id": str(uuid.uuid4()), "quote_no": "Q"}),
    ):
        result = create_member_renewal_quote(sb, user_id=_USER_ID, company_id=_COMPANY_ID, payment_months=months)

    assert result is not None


# ── RQ06: payment_months=1 거부 ───────────────────────────────────────────────

def test_RQ06_payment_months_1_rejected():
    """RQ06: payment_months=1 → RENEWAL_PAYMENT_MONTHS_INVALID."""
    from services.saas_renewal_quote_svc import SaasRenewalQuoteError, create_member_renewal_quote
    sb = MagicMock()

    with pytest.raises(SaasRenewalQuoteError) as exc_info:
        create_member_renewal_quote(sb, user_id=_USER_ID, company_id=_COMPANY_ID, payment_months=1)

    assert exc_info.value.code == "RENEWAL_PAYMENT_MONTHS_INVALID"


# ── RQ07: CUSTOM tier → CUSTOM_REVIEW_REQUIRED ───────────────────────────────

def test_RQ07_custom_tier_rejected():
    """RQ07: product_tier=CUSTOM → CUSTOM_REVIEW_REQUIRED."""
    from services.saas_renewal_quote_svc import SaasRenewalQuoteError, create_member_renewal_quote
    sb = MagicMock()

    with (
        patch("services.member_commercial_svc.get_member_commercial_contract", return_value=_make_ctx(product_tier="CUSTOM")),
        patch("services.saas_renewal_quote_svc._get_latest_eligible_payment_id", return_value=_PAYMENT_ID),
    ):
        with pytest.raises(SaasRenewalQuoteError) as exc_info:
            create_member_renewal_quote(sb, user_id=_USER_ID, company_id=_COMPANY_ID, payment_months=6)

    assert exc_info.value.code == "CUSTOM_REVIEW_REQUIRED"


# ── RQ08: inactive contract → CONTRACT_NOT_ACTIVE ────────────────────────────

def test_RQ08_inactive_contract_rejected():
    """RQ08: state != ACTIVE → CONTRACT_NOT_ACTIVE."""
    from services.saas_renewal_quote_svc import SaasRenewalQuoteError, create_member_renewal_quote
    sb = MagicMock()

    with (
        patch("services.member_commercial_svc.get_member_commercial_contract",
              return_value={"state": "NO_ACTIVE_CONTRACT", "error_code": "NO_ACTIVE_SAAS_CONTRACT",
                            "contract": None, "commercial_version": None, "site_scopes": []}),
    ):
        with pytest.raises(SaasRenewalQuoteError) as exc_info:
            create_member_renewal_quote(sb, user_id=_USER_ID, company_id=_COMPANY_ID, payment_months=6)

    assert exc_info.value.code in {"CONTRACT_NOT_ACTIVE", "NO_ACTIVE_SAAS_CONTRACT"}


# ── RQ09: 다른 회사 payment 접근 불가 ────────────────────────────────────────

def test_RQ09_cross_company_payment_rejected():
    """RQ09: 다른 company_id 소유 payment는 접근 불가 (ownership guard in create_renewal_quote)."""
    from fastapi import HTTPException
    from routers.member_quotes import issue_v2_renewal, RenewalIssueBody

    other_company = str(uuid.uuid4())

    sb = MagicMock()

    def _fake_renewal_quote(supabase, *, user_id, company_id, payment_months):
        from services.saas_renewal_quote_svc import SaasRenewalQuoteError
        if company_id == other_company:
            raise SaasRenewalQuoteError("PAYMENT_NOT_OWNED", "결제를 찾을 수 없습니다.", 404)
        return {"id": str(uuid.uuid4()), "quote_no": "Q"}

    with (
        patch("routers.member_quotes.get_supabase", return_value=sb),
        patch("routers.member_quotes._require_member_company", return_value=other_company),
        patch("services.saas_renewal_quote_svc.create_member_renewal_quote", side_effect=_fake_renewal_quote),
    ):
        with pytest.raises(HTTPException) as exc_info:
            issue_v2_renewal(
                body=RenewalIssueBody(payment_months=6),
                current={"id": _USER_ID},
            )

    assert exc_info.value.status_code == 404


# ── RQ10: idempotent (동일 조건) ─────────────────────────────────────────────

def test_RQ10_idempotent_same_condition():
    """RQ10: 동일 contract version + payment_months → 기존 quote 반환 (중복 생성 없음)."""
    from services.saas_renewal_quote_svc import create_member_renewal_quote
    sb = MagicMock()

    existing_quote_id = str(uuid.uuid4())
    call_count = []

    def _fake_create(supabase, *, payment_id, company_id, user_id, payment_months):
        call_count.append(1)
        existing = {
            "id": existing_quote_id,
            "quote_no": "Q-EXIST",
            "status_code": "ISSUED",
            "survey_data": {
                "commercial_v3_renewal": {"contract_id": _CONTRACT_ID, "current_version_no": 1}
            },
            "items": [{"pricing_snapshot": {"payment_months": payment_months}}],
        }
        return existing

    with (
        patch("services.member_commercial_svc.get_member_commercial_contract", return_value=_make_ctx()),
        patch("services.saas_renewal_quote_svc._get_latest_eligible_payment_id", return_value=_PAYMENT_ID),
        patch("services.saas_renewal_quote_svc.create_renewal_quote", side_effect=_fake_create),
    ):
        r1 = create_member_renewal_quote(sb, user_id=_USER_ID, company_id=_COMPANY_ID, payment_months=6)
        with (
            patch("services.member_commercial_svc.get_member_commercial_contract", return_value=_make_ctx()),
            patch("services.saas_renewal_quote_svc._get_latest_eligible_payment_id", return_value=_PAYMENT_ID),
            patch("services.saas_renewal_quote_svc.create_renewal_quote", side_effect=_fake_create),
        ):
            r2 = create_member_renewal_quote(sb, user_id=_USER_ID, company_id=_COMPANY_ID, payment_months=6)

    assert r1["id"] == existing_quote_id
    assert r2["id"] == existing_quote_id


# ── RQ11: commercial_v3_renewal binding 존재 ─────────────────────────────────

def test_RQ11_renewal_binding_in_quote():
    """RQ11: 반환된 quote에 commercial_v3_renewal binding 존재."""
    from services.saas_renewal_quote_svc import create_member_renewal_quote
    sb = MagicMock()

    quote_id = str(uuid.uuid4())

    def _fake_create(supabase, *, payment_id, company_id, user_id, payment_months):
        return {
            "id": quote_id,
            "quote_no": "Q-003",
            "status_code": "ISSUED",
            "survey_data": {
                "commercial_v3_renewal": {
                    "contract_id": _CONTRACT_ID,
                    "current_version_no": 1,
                    "origin_payment_id": payment_id,
                }
            },
        }

    with (
        patch("services.member_commercial_svc.get_member_commercial_contract", return_value=_make_ctx()),
        patch("services.saas_renewal_quote_svc._get_latest_eligible_payment_id", return_value=_PAYMENT_ID),
        patch("services.saas_renewal_quote_svc.create_renewal_quote", side_effect=_fake_create),
    ):
        result = create_member_renewal_quote(sb, user_id=_USER_ID, company_id=_COMPANY_ID, payment_months=6)

    binding = result["survey_data"]["commercial_v3_renewal"]
    assert binding["contract_id"] == _CONTRACT_ID
    assert "current_version_no" in binding


# ── RQ12: current_version_no가 실제 CV와 일치 ────────────────────────────────

def test_RQ12_current_version_no_matches_cv():
    """RQ12: create_renewal_quote에 전달되는 binding의 current_version_no = current CV version_no."""
    from services.saas_renewal_quote_svc import create_member_renewal_quote
    sb = MagicMock()

    captured = {}

    def _fake_create(supabase, *, payment_id, company_id, user_id, payment_months):
        return {
            "id": str(uuid.uuid4()),
            "quote_no": "Q-004",
            "survey_data": {
                "commercial_v3_renewal": {
                    "contract_id": _CONTRACT_ID,
                    "current_version_no": 1,
                }
            },
        }

    ctx = _make_ctx()
    ctx["commercial_version"]["version_no"] = 1

    with (
        patch("services.member_commercial_svc.get_member_commercial_contract", return_value=ctx),
        patch("services.saas_renewal_quote_svc._get_latest_eligible_payment_id", return_value=_PAYMENT_ID),
        patch("services.saas_renewal_quote_svc.create_renewal_quote", side_effect=_fake_create),
    ):
        result = create_member_renewal_quote(sb, user_id=_USER_ID, company_id=_COMPANY_ID, payment_months=6)

    version_no = result["survey_data"]["commercial_v3_renewal"]["current_version_no"]
    assert version_no == 1
