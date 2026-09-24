"""OBJ08B Canonical Marketing Business Outcomes — B01–B21.

실 DB·네트워크 0. _count_exact_strict 인터셉트로 쿼리 조건 검증.
Router auth는 FastAPI TestClient 로 검증.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import services.stats_dashboard_svc as svc
from services.stats_dashboard_svc import _parse_date_token, get_marketing_business_outcomes
import routers.stats_provider as provider_mod

_KST = timezone(timedelta(hours=9))
_NOW = datetime(2026, 9, 24, 12, 0, 0, tzinfo=_KST)
_VALID_TOKEN = "test-mkt-stats-token-value"


# ── Recording query builder ───────────────────────────────────────────────────

class _NotAccessor:
    def __init__(self, q: "_RecQ"):
        self._q = q

    def is_(self, col, val):
        self._q._calls.append(("not_is_", col, val))
        return self._q


class _RecQ:
    """Records all filter calls for assertion."""

    def __init__(self):
        self._calls: list[tuple] = []

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

    def has(self, method, col, val) -> bool:
        return (method, col, val) in self._calls


# ── Intercept helper ─────────────────────────────────────────────────────────

def _intercept_run(date_from: str | None, date_to: str | None, return_val: int = 1):
    """Run get_marketing_business_outcomes with _count_exact_strict intercepted.
    Returns (result, list_of_(table, RecQ)) tuples."""
    captured: list[tuple[str, _RecQ]] = []

    def _fake_count(table, build=None):
        q = _RecQ()
        if build:
            build(q)
        captured.append((table, q))
        return return_val

    with patch.object(svc, "_count_exact_strict", side_effect=_fake_count):
        with patch.object(svc, "now_kst", return_value=_NOW):
            result = get_marketing_business_outcomes(date_from=date_from, date_to=date_to)
    return result, captured


def _calls_for_table(captured, table_name: str) -> list[_RecQ]:
    return [q for t, q in captured if t == table_name]


# ── B01–B06 Canonical filter conditions ─────────────────────────────────────

def test_b01_free_diagnosis_uses_anonymous_diagnosis_results():
    _, captured = _intercept_run("2026-09-01", "2026-09-23", return_val=5)
    tables = [t for t, _ in captured]
    assert "anonymous_diagnosis_results" in tables


def test_b02_signup_identity_verified_filter():
    _, captured = _intercept_run("2026-09-01", "2026-09-23")
    users_qs = _calls_for_table(captured, "users")
    assert users_qs, "users 테이블 쿼리 없음"
    q = users_qs[0]
    assert q.has("eq", "identity_verified", True), "identity_verified=True 필터 없음"


def test_b03_signup_excludes_workers_via_identity_ci_not_null():
    _, captured = _intercept_run("2026-09-01", "2026-09-23")
    users_qs = _calls_for_table(captured, "users")
    assert users_qs
    q = users_qs[0]
    assert q.has("not_is_", "identity_ci", "null"), "identity_ci IS NOT NULL 필터 없음"


def test_b04_paid_diagnosis_canonical_filter():
    _, captured = _intercept_run("2026-09-01", "2026-09-23")
    pay_qs = _calls_for_table(captured, "payments")
    assert pay_qs, "payments 테이블 쿼리 없음"
    diagnosis_q = next(
        (q for q in pay_qs if q.has("eq", "product_type", "DIAGNOSIS")),
        None,
    )
    assert diagnosis_q is not None, "product_type=DIAGNOSIS 필터 없음"
    assert diagnosis_q.has("eq", "status_code", "SUCCESS"), "status_code=SUCCESS 필터 없음"
    assert diagnosis_q.has("not_is_", "paid_at", "null"), "paid_at IS NOT NULL 필터 없음"


def test_b05_saas_payment_canonical_filter():
    _, captured = _intercept_run("2026-09-01", "2026-09-23")
    pay_qs = _calls_for_table(captured, "payments")
    saas_q = next(
        (q for q in pay_qs if q.has("like", "product_type", "SAAS%")),
        None,
    )
    assert saas_q is not None, "product_type LIKE SAAS% 필터 없음"
    assert saas_q.has("eq", "status_code", "SUCCESS")
    assert saas_q.has("not_is_", "paid_at", "null")


def test_b06_saas_service_active_no_date_filter():
    _, captured = _intercept_run("2026-09-01", "2026-09-23")
    contract_qs = _calls_for_table(captured, "contracts")
    assert contract_qs, "contracts 테이블 쿼리 없음"
    q = contract_qs[0]
    assert q.has("eq", "service_type", "SAAS")
    assert q.has("eq", "status_code", "ACTIVE")
    assert q.has("eq", "is_active", True)
    # 날짜 필터 없어야 함(point-in-time)
    date_calls = [c for c in q._calls if c[0] in ("gte", "lt")]
    assert not date_calls, "contracts 에 날짜 필터가 있으면 안 됨"


# ── B07–B11 Date parsing ──────────────────────────────────────────────────────

def test_b07_date_from_inclusive_boundary():
    """from=2026-09-01 → from_iso 에 00:00:00+09:00 포함."""
    with patch.object(svc, "now_kst", return_value=_NOW):
        dt = _parse_date_token("2026-09-01")
    assert dt is not None
    assert dt.year == 2026 and dt.month == 9 and dt.day == 1
    assert dt.hour == 0 and dt.minute == 0 and dt.second == 0


def test_b08_date_to_exclusive_next_day():
    """to=2026-09-23 → to_exclusive = 2026-09-24 00:00:00."""
    with patch.object(svc, "now_kst", return_value=_NOW):
        to_dt = _parse_date_token("2026-09-23")
    assert to_dt is not None
    to_excl = to_dt + timedelta(days=1)
    assert to_excl.day == 24


def test_b09_n_days_ago_token():
    with patch.object(svc, "now_kst", return_value=_NOW):
        dt = _parse_date_token("28daysAgo")
    assert dt is not None
    expected = (_NOW - timedelta(days=28)).replace(hour=0, minute=0, second=0, microsecond=0)
    assert dt.date() == expected.date()


def test_b10_invalid_token_raises_value_error():
    with patch.object(svc, "now_kst", return_value=_NOW):
        with pytest.raises(ValueError):
            get_marketing_business_outcomes(date_from="not-a-date", date_to="today")


def test_b11_from_after_to_raises_value_error():
    with patch.object(svc, "now_kst", return_value=_NOW):
        with pytest.raises(ValueError):
            get_marketing_business_outcomes(date_from="2026-09-23", date_to="2026-09-01")


# ── B12–B14 Fail-closed / zero semantics ─────────────────────────────────────

def test_b12_zero_count_is_valid():
    result, _ = _intercept_run("2026-09-01", "2026-09-23", return_val=0)
    assert result["available"] is True
    assert result["flows"]["free_diagnosis_completed"] == 0
    assert result["flows"]["signup_complete"] == 0


def test_b13_db_error_returns_available_false():
    def _raise(table, build=None):
        raise RuntimeError("DB_CONN_FAIL")

    with patch.object(svc, "_count_exact_strict", side_effect=_raise):
        with patch.object(svc, "now_kst", return_value=_NOW):
            result = get_marketing_business_outcomes(date_from="2026-09-01", date_to="2026-09-23")

    assert result["available"] is False
    assert result["flows"] is None
    assert result["current_stock"] is None


def test_b14_no_partial_output_on_db_error():
    """부분 성공 금지 — flows/current_stock 둘 다 None 이어야 한다."""
    call_count = 0

    def _fail_on_third(table, build=None):
        nonlocal call_count
        call_count += 1
        if call_count >= 3:
            raise RuntimeError("partial failure")
        return 1

    with patch.object(svc, "_count_exact_strict", side_effect=_fail_on_third):
        with patch.object(svc, "now_kst", return_value=_NOW):
            result = get_marketing_business_outcomes(date_from="2026-09-01", date_to="2026-09-23")

    assert result["available"] is False
    assert result["flows"] is None
    assert result["current_stock"] is None


# ── B15–B18 Auth (router) ────────────────────────────────────────────────────

def _make_client(env_token: str | None = _VALID_TOKEN):
    app = FastAPI()
    app.include_router(provider_mod.router)
    env = {"MKT_STATS_SHARED_TOKEN": env_token} if env_token is not None else {}

    def _fake_outcomes(**kw):
        return {
            "available": True,
            "date_from": "2026-09-01",
            "date_to": "2026-09-23",
            "timezone": "Asia/Seoul",
            "flows": {"free_diagnosis_completed": 0, "signup_complete": 0,
                      "paid_diagnosis_purchased": 0, "saas_payment_success": 0},
            "current_stock": {"saas_service_active": 0, "snapshot_at": "2026-09-24T03:00:00Z"},
            "rates": None,
            "cohort_joined": False,
            "semantics": "independent_business_facts_not_cohort",
        }

    return app, env, _fake_outcomes


def _client_request(token_header: str | None = _VALID_TOKEN, env_token: str | None = _VALID_TOKEN):
    app, env, fake_fn = _make_client(env_token)
    client = TestClient(app, raise_server_exceptions=False)
    headers = {}
    if token_header is not None:
        headers["X-MKT-Stats-Token"] = token_header
    with patch.dict(os.environ, env, clear=False):
        with patch.object(provider_mod, "get_marketing_business_outcomes", side_effect=fake_fn):
            resp = client.get(
                "/stats/marketing-outcomes",
                headers=headers,
                params={"from": "2026-09-01", "to": "2026-09-23"},
            )
    return resp


def test_b15_missing_env_token_returns_503():
    resp = _client_request(token_header=_VALID_TOKEN, env_token=None)
    assert resp.status_code == 503


def test_b16_missing_header_returns_403():
    resp = _client_request(token_header=None, env_token=_VALID_TOKEN)
    assert resp.status_code == 403


def test_b17_wrong_token_returns_403():
    resp = _client_request(token_header="wrong-token", env_token=_VALID_TOKEN)
    assert resp.status_code == 403


def test_b18_valid_token_returns_200():
    resp = _client_request(token_header=_VALID_TOKEN, env_token=_VALID_TOKEN)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["data"]["available"] is True


# ── B19–B21 Schema invariants ─────────────────────────────────────────────────

_PII_FIELDS = {"user_id", "email", "phone", "identity_ci", "auth_id",
               "public_token", "client_id", "name"}


def test_b19_no_pii_in_output():
    result, _ = _intercept_run("2026-09-01", "2026-09-23", return_val=1)
    result_str = str(result)
    for field in _PII_FIELDS:
        assert field not in result_str, f"PII 필드 '{field}' 가 응답에 있으면 안 됨"


def test_b20_rates_always_none():
    result, _ = _intercept_run("2026-09-01", "2026-09-23", return_val=3)
    assert result["rates"] is None, "rates 는 None 이어야 함 (cohort join 금지)"


def test_b21_cohort_joined_always_false():
    result, _ = _intercept_run("2026-09-01", "2026-09-23", return_val=3)
    assert result["cohort_joined"] is False
    assert result["semantics"] == "independent_business_facts_not_cohort"
