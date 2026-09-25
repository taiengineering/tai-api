"""OBJ13 LINKED_BUSINESS_JOURNEY_SEGMENTS — J01–J24.

Real DB=0. Intercepts _count_exact_strict and mocks get_marketing_business_outcomes.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import services.stats_marketing_journey_svc as journey_svc
from services.stats_marketing_journey_svc import get_marketing_journey
import routers.stats_provider as provider_mod

_KST = timezone(timedelta(hours=9))
_NOW = datetime(2026, 9, 25, 12, 0, 0, tzinfo=_KST)
_VALID_TOKEN = "test-mkt-stats-token-j01"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _fake_outcomes(available=True, **overrides):
    base = {
        "available": available,
        "date_from": "2026-08-28",
        "date_to": "2026-09-25",
        "timezone": "Asia/Seoul",
        "flows": {
            "free_diagnosis_completed": 10,
            "free_diagnosis_claimed": 4,
            "signup_complete": 6,
            "paid_diagnosis_purchased": 3,
            "saas_payment_success": 2,
        },
        "current_stock": {
            "saas_service_active": 5,
            "subscription_active": 7,
            "snapshot_at": "2026-09-25T12:00:00+09:00",
        },
        "rates": None,
        "cohort_joined": False,
        "semantics": "independent_business_facts_not_cohort",
    }
    base.update(overrides)
    return base


def _make_link_counts(
    paid_diag_linked=3,
    saas_user=2,
    saas_co=2,
    sub_user=7,
    sub_co=5,
    svc_co=5,
):
    return [paid_diag_linked, saas_user, saas_co, sub_user, sub_co, svc_co]


class _RecQ:
    def __init__(self):
        self._calls: list = []

    @property
    def not_(self):
        return _NotAccessor(self)

    def eq(self, col, val):
        self._calls.append(("eq", col, val))
        return self

    def gte(self, col, val):
        self._calls.append(("gte", col, val))
        return self

    def lt(self, col, val):
        self._calls.append(("lt", col, val))
        return self

    def like(self, col, val):
        self._calls.append(("like", col, val))
        return self

    def is_(self, col, val):
        self._calls.append(("is_", col, val))
        return self

    def has(self, method, col, val):
        return (method, col, val) in self._calls


class _NotAccessor:
    def __init__(self, q):
        self._q = q

    def is_(self, col, val):
        self._q._calls.append(("not_is_", col, val))
        return self._q


def _run_journey(date_from="2026-09-01", date_to="2026-09-25",
                 link_counts=None, outcomes=None):
    if outcomes is None:
        outcomes = _fake_outcomes()
    if link_counts is None:
        link_counts = _make_link_counts()
    counts_iter = iter(link_counts)

    with (
        patch.object(journey_svc, "get_marketing_business_outcomes", return_value=outcomes),
        patch("services.stats_marketing_journey_svc._count_exact_strict",
              side_effect=lambda table, build=None: next(counts_iter)),
        patch("services.stats_marketing_journey_svc._parse_date_token",
              side_effect=lambda t: _parse_token(t)),
    ):
        return get_marketing_journey(date_from=date_from, date_to=date_to)


def _parse_token(token):
    if token == "today":
        return _NOW.replace(hour=0, minute=0, second=0, microsecond=0)
    if token == "28daysAgo":
        return (_NOW - timedelta(days=28)).replace(hour=0, minute=0, second=0, microsecond=0)
    from datetime import date as _date
    try:
        d = _date.fromisoformat(token)
        return datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=_KST)
    except Exception:
        return None


# ── J01 OBJ08B reuse ──────────────────────────────────────────────────────────

def test_j01_obj08b_reused():
    """J01: get_marketing_business_outcomes called with same date args."""
    called_with = {}
    fake = _fake_outcomes()

    def _capture(date_from=None, date_to=None):
        called_with["date_from"] = date_from
        called_with["date_to"] = date_to
        return fake

    counts_iter = iter(_make_link_counts())

    with (
        patch.object(journey_svc, "get_marketing_business_outcomes", side_effect=_capture),
        patch("services.stats_marketing_journey_svc._count_exact_strict",
              side_effect=lambda table, build=None: next(counts_iter)),
        patch("services.stats_marketing_journey_svc._parse_date_token",
              side_effect=_parse_token),
    ):
        get_marketing_journey(date_from="2026-09-01", date_to="2026-09-25")

    assert called_with["date_from"] == "2026-09-01"
    assert called_with["date_to"] == "2026-09-25"


# ── J02-J06 Diagnosis segment ─────────────────────────────────────────────────

def test_j02_diagnosis_completed():
    """J02: diagnosis.completed = free_diagnosis_completed from OBJ08B."""
    r = _run_journey()
    assert r["segments"]["diagnosis"]["completed"] == 10


def test_j03_diagnosis_claimed():
    """J03: diagnosis.claimed = free_diagnosis_claimed from OBJ08B."""
    r = _run_journey()
    assert r["segments"]["diagnosis"]["claimed"] == 4


def test_j04_diagnosis_user_linked_equals_claimed():
    """J04: diagnosis.user_linked = claimed (claimed_user_id IS the user link)."""
    r = _run_journey()
    assert r["segments"]["diagnosis"]["user_linked"] == r["segments"]["diagnosis"]["claimed"]


def test_j05_claim_timestamp_available_false():
    """J05: claim_timestamp_available=false (no claimed_at column)."""
    r = _run_journey()
    assert r["segments"]["diagnosis"]["claim_timestamp_available"] is False


def test_j06_timestamp_basis_diagnosis_created_at():
    """J06: timestamp_basis=DIAGNOSIS_CREATED_AT."""
    r = _run_journey()
    assert r["segments"]["diagnosis"]["timestamp_basis"] == "DIAGNOSIS_CREATED_AT"


# ── J07-J08 Account segment ───────────────────────────────────────────────────

def test_j07_signup_complete_preserved():
    """J07: account.signup_complete = signup_complete from OBJ08B."""
    r = _run_journey()
    assert r["segments"]["account"]["signup_complete"] == 6


def test_j08_signup_timestamp_exact_false():
    """J08: signup_timestamp_exact=false."""
    r = _run_journey()
    assert r["segments"]["account"]["signup_timestamp_exact"] is False
    assert r["segments"]["account"]["timestamp_basis"] == "USER_ROW_CREATED_AT"


# ── J09-J13 Paid diagnosis segment ───────────────────────────────────────────

def test_j09_paid_diag_canonical_predicate():
    """J09: paid_diagnosis.purchased = paid_diagnosis_purchased from OBJ08B."""
    r = _run_journey()
    assert r["segments"]["paid_diagnosis"]["purchased"] == 3


def test_j10_paid_diag_user_linked_not_null_predicate():
    """J10: user_linked uses separate _count_exact_strict with user_id NOT NULL."""
    captured_builds = []

    def _fake_count(table, build=None):
        q = _RecQ()
        if build:
            build(q)
        captured_builds.append((table, q))
        return 2

    fake = _fake_outcomes()
    with (
        patch.object(journey_svc, "get_marketing_business_outcomes", return_value=fake),
        patch("services.stats_marketing_journey_svc._count_exact_strict",
              side_effect=_fake_count),
        patch("services.stats_marketing_journey_svc._parse_date_token",
              side_effect=_parse_token),
    ):
        r = get_marketing_journey(date_from="2026-09-01", date_to="2026-09-25")

    # First call is paid_diag_user_linked → payments table with user_id NOT NULL
    tbl, q = captured_builds[0]
    assert tbl == "payments"
    assert q.has("not_is_", "user_id", "null")
    assert q.has("eq", "product_type", "DIAGNOSIS")
    assert q.has("eq", "status_code", "SUCCESS")


def test_j11_anonymous_vbank_not_masquerade_linked():
    """J11: user_unlinked = purchased - user_linked (anonymous vbank path)."""
    # purchased=3, user_linked=2 (1 anonymous vbank)
    r = _run_journey(link_counts=_make_link_counts(paid_diag_linked=2))
    assert r["segments"]["paid_diagnosis"]["user_unlinked"] == 1
    assert r["segments"]["paid_diagnosis"]["user_linked"] == 2
    assert r["segments"]["paid_diagnosis"]["purchased"] == 3


def test_j12_user_unlinked_equals_purchased_minus_linked():
    """J12: user_unlinked arithmetic is correct."""
    r = _run_journey(link_counts=_make_link_counts(paid_diag_linked=3))
    assert r["segments"]["paid_diagnosis"]["user_unlinked"] == 0  # all linked


def test_j13_paid_diag_grain_payment():
    """J13: grain=PAYMENT (not USER+FACTORY)."""
    r = _run_journey()
    assert r["segments"]["paid_diagnosis"]["grain"] == "PAYMENT"


# ── J14-J16 SaaS payment segment ─────────────────────────────────────────────

def test_j14_saas_payment_canonical_predicate():
    """J14: saas_payment.success = saas_payment_success from OBJ08B."""
    r = _run_journey()
    assert r["segments"]["saas_payment"]["success"] == 2


def test_j15_saas_user_linked_actual_count():
    """J15: saas_payment.user_linked verified from DB (not hardcoded)."""
    r = _run_journey(link_counts=_make_link_counts(saas_user=1))
    assert r["segments"]["saas_payment"]["user_linked"] == 1


def test_j16_saas_company_linked_actual_count():
    """J16: saas_payment.company_linked verified from DB."""
    r = _run_journey(link_counts=_make_link_counts(saas_co=0))
    assert r["segments"]["saas_payment"]["company_linked"] == 0


# ── J17-J19 Subscription segment ─────────────────────────────────────────────

def test_j17_subscription_active_preserved():
    """J17: subscription.active = subscription_active from OBJ08B stock."""
    r = _run_journey()
    assert r["segments"]["subscription"]["active"] == 7


def test_j18_subscription_linked_counts():
    """J18: subscription user/company linked are verified DB counts."""
    r = _run_journey(link_counts=_make_link_counts(sub_user=6, sub_co=4))
    assert r["segments"]["subscription"]["user_linked"] == 6
    assert r["segments"]["subscription"]["company_linked"] == 4


def test_j19_subscription_timestamp_basis_snapshot():
    """J19: subscription timestamp_basis=SNAPSHOT."""
    r = _run_journey()
    assert r["segments"]["subscription"]["timestamp_basis"] == "SNAPSHOT"
    assert r["segments"]["subscription"]["kind"] == "STOCK"


# ── J20-J23 SaaS service + bridges ───────────────────────────────────────────

def test_j20_saas_service_active_preserved():
    """J20: saas_service.active = saas_service_active from OBJ08B stock."""
    r = _run_journey()
    assert r["segments"]["saas_service"]["active"] == 5


def test_j21_saas_service_company_linked():
    """J21: saas_service.company_linked is a real DB count."""
    r = _run_journey(link_counts=_make_link_counts(svc_co=3))
    assert r["segments"]["saas_service"]["company_linked"] == 3


def test_j22_factory_mapping_not_proven():
    """J22: factory_mapping=NOT_PROVEN."""
    r = _run_journey()
    assert r["segments"]["saas_service"]["factory_mapping"] == "NOT_PROVEN"
    assert r["segments"]["saas_service"]["grain"] == "CONTRACT"


def test_j23_subscription_to_saas_contract_not_proven():
    """J23: bridges.subscription_to_saas_contract=NOT_PROVEN."""
    r = _run_journey()
    assert r["bridges"]["subscription_to_saas_contract"] == "NOT_PROVEN"
    assert r["bridges"]["marketing_to_business"] == "UNLINKED"


# ── J24 No PII / no write ─────────────────────────────────────────────────────

def test_j24_no_pii_no_write():
    """J24: response contains no PII fields; only aggregates."""
    r = _run_journey()
    forbidden = {"user_id", "email", "phone", "auth_id", "company_id", "factory_id",
                 "public_token", "payment_id"}
    def _check(obj, path=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                assert k not in forbidden, f"PII key '{k}' found at {path}.{k}"
                _check(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                _check(v, f"{path}[{i}]")
    _check(r)
    # confirm it is aggregate-only integers at leaf level
    segs = r["segments"]
    assert isinstance(segs["diagnosis"]["completed"], int)
    assert isinstance(segs["paid_diagnosis"]["purchased"], int)


# ── Fail-closed tests ─────────────────────────────────────────────────────────

def test_fail_closed_when_obj08b_unavailable():
    """OBJ08B unavailable → available=False, segments=None."""
    with patch.object(journey_svc, "get_marketing_business_outcomes",
                      return_value=_fake_outcomes(available=False)):
        r = get_marketing_journey(date_from="2026-09-01", date_to="2026-09-25")
    assert r["available"] is False
    assert r["segments"] is None


def test_fail_closed_when_link_query_fails():
    """Any linked-count failure → available=False."""
    fake = _fake_outcomes()
    with (
        patch.object(journey_svc, "get_marketing_business_outcomes", return_value=fake),
        patch("services.stats_marketing_journey_svc._count_exact_strict",
              side_effect=RuntimeError("DB down")),
        patch("services.stats_marketing_journey_svc._parse_date_token",
              side_effect=_parse_token),
    ):
        r = get_marketing_journey(date_from="2026-09-01", date_to="2026-09-25")
    assert r["available"] is False
    assert r["segments"] is None


# ── HTTP endpoint tests (auth guard) ─────────────────────────────────────────

@pytest.fixture
def client():
    os.environ["MKT_STATS_SHARED_TOKEN"] = _VALID_TOKEN
    app = FastAPI()
    app.include_router(provider_mod.router)
    return TestClient(app)


def test_journey_endpoint_no_token(client):
    resp = client.get("/stats/marketing-journey", params={"from": "2026-09-01", "to": "2026-09-25"})
    assert resp.status_code == 403


def test_journey_endpoint_wrong_token(client):
    resp = client.get("/stats/marketing-journey",
                      params={"from": "2026-09-01", "to": "2026-09-25"},
                      headers={"X-MKT-Stats-Token": "wrong"})
    assert resp.status_code == 403


def test_journey_endpoint_valid_token(client):
    """Valid token with mocked service → 200."""
    fake_data = {"available": True, "scope": "LINKED_BUSINESS_JOURNEY_SEGMENTS",
                 "date_from": "2026-09-01", "date_to": "2026-09-25",
                 "timezone": "Asia/Seoul", "segments": {}, "bridges": {},
                 "marketing_link": {"available": False, "reason": "NO_GA4_TAI_IDENTITY_BRIDGE"},
                 "business_outcome_attribution": None, "cross_source_estimate": None,
                 "cohort_joined": False, "rates": None, "safe_to_sum": False}
    with patch("services.stats_marketing_journey_svc.get_marketing_journey",
               return_value=fake_data):
        resp = client.get(
            "/stats/marketing-journey",
            params={"from": "2026-09-01", "to": "2026-09-25"},
            headers={"X-MKT-Stats-Token": _VALID_TOKEN},
        )
    assert resp.status_code == 200
