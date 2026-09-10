"""WO-COMMON-TIER-PAYMENT-GATE-MODULARIZE-001 / B7-A1.

Secure tier-upgrade provider launch. DB mutation 0 · second prepare 0.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from services.payment_helpers import DEFAULT_RETURN_URL
from services.payment_launch_svc import (
    PROVIDER_FIELDS,
    PaymentLaunchConfigError,
    PaymentLaunchTokenError,
    attach_tier_upgrade_launch,
    create_payment_launch_token,
    render_launch_success,
    verify_payment_launch_token,
)
import services.payment_launch_svc as launch_svc

LAUNCH_SVC = Path(__file__).resolve().parents[1] / "services" / "payment_launch_svc.py"
PAY_TPL = Path(__file__).resolve().parents[1] / "templates" / "payment" / "tier_upgrade_pay.html"
PAY_HTML = Path(__file__).resolve().parents[1] / "templates" / "payment" / "pay.html"
BILLING_HTML = Path(__file__).resolve().parents[1] / "templates" / "payment" / "billing_pay.html"
ROUTER = Path(__file__).resolve().parents[1] / "routers" / "payment.py"

SECRET = "test-payment-launch-secret-value-32b"


def _provider(**over):
    row = {
        "mid": "taieng4350",
        "mKey": "mkeyhash",
        "oid": "TAIOID1",
        "price": "165000",
        "goodname": "SaaS 업그레이드 A → B",
        "buyername": "고객",
        "buyertel": "00000000000",
        "buyeremail": "buyer@taieng.co.kr",
        "timestamp": "1710000000000",
        "signature": "sighex",
        "verification": "verhex",
        "use_chkfake": "Y",
        "returnUrl": DEFAULT_RETURN_URL,
        "closeUrl": "https://taieng.co.kr/_api/payments/result?resultCode=CLOSE",
        "charset": "UTF-8",
        "gopaymethod": "",
    }
    row.update(over)
    return row


def _sign_envelope(envelope: dict) -> str:
    encoded = launch_svc._b64url_encode(launch_svc._canonical_json(envelope).encode("utf-8"))
    mac = hmac.new(SECRET.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
    return encoded + "." + launch_svc._b64url_encode(mac)


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setenv("PAYMENT_LAUNCH_SECRET", SECRET)
    monkeypatch.setenv("PAYMENT_LAUNCH_URL", "https://taieng.co.kr/_api/payments/tier-upgrade/pay")
    monkeypatch.setenv("PAYMENT_LAUNCH_TTL_SECONDS", "300")


def test_token_valid_roundtrip():
    token = create_payment_launch_token(payment_id="pay-1", provider=_provider(), now=1_700_000_000)
    env = verify_payment_launch_token(token, now=1_700_000_010)
    assert env["v"] == 1
    assert env["purpose"] == "SAAS_TIER_UPGRADE"
    assert env["payment_id"] == "pay-1"
    assert env["provider"]["oid"] == "TAIOID1"
    assert env["provider"]["price"] == "165000"


def test_token_payload_tamper_rejected():
    token = create_payment_launch_token(payment_id="pay-1", provider=_provider(), now=1_700_000_000)
    encoded, mac = token.split(".", 1)
    raw = launch_svc._b64url_decode(encoded)
    body = raw.decode("utf-8").replace("pay-1", "pay-9")
    tampered = launch_svc._b64url_encode(body.encode("utf-8")) + "." + mac
    with pytest.raises(PaymentLaunchTokenError):
        verify_payment_launch_token(tampered, now=1_700_000_010)


def test_token_mac_tamper_rejected():
    token = create_payment_launch_token(payment_id="pay-1", provider=_provider(), now=1_700_000_000)
    encoded, mac = token.split(".", 1)
    flip = ("A" if mac[-1] != "A" else "B")
    with pytest.raises(PaymentLaunchTokenError):
        verify_payment_launch_token(encoded + "." + mac[:-1] + flip, now=1_700_000_010)


def test_token_expired_rejected():
    token = create_payment_launch_token(payment_id="pay-1", provider=_provider(), now=1_000)
    with pytest.raises(PaymentLaunchTokenError) as ei:
        verify_payment_launch_token(token, now=1_000 + 301)
    assert ei.value.code == "TOKEN_EXPIRED"


def test_token_future_iat_rejected():
    token = create_payment_launch_token(payment_id="pay-1", provider=_provider(), now=9_000)
    with pytest.raises(PaymentLaunchTokenError) as ei:
        verify_payment_launch_token(token, now=1_000)
    assert ei.value.code == "TOKEN_IAT_FUTURE"


def test_token_invalid_iat_rejected():
    env = {
        "v": 1,
        "purpose": "SAAS_TIER_UPGRADE",
        "iat": "nope",
        "exp": 2_000,
        "payment_id": "pay-1",
        "provider": _provider(),
    }
    with pytest.raises(PaymentLaunchTokenError):
        verify_payment_launch_token(_sign_envelope(env), now=1_500)


def test_token_wrong_version_rejected():
    env = {
        "v": 2,
        "purpose": "SAAS_TIER_UPGRADE",
        "iat": 1_000,
        "exp": 1_300,
        "payment_id": "pay-1",
        "provider": _provider(),
    }
    with pytest.raises(PaymentLaunchTokenError) as ei:
        verify_payment_launch_token(_sign_envelope(env), now=1_010)
    assert ei.value.code == "TOKEN_VERSION"


def test_token_wrong_purpose_rejected():
    env = {
        "v": 1,
        "purpose": "BILLING",
        "iat": 1_000,
        "exp": 1_300,
        "payment_id": "pay-1",
        "provider": _provider(),
    }
    with pytest.raises(PaymentLaunchTokenError) as ei:
        verify_payment_launch_token(_sign_envelope(env), now=1_010)
    assert ei.value.code == "TOKEN_PURPOSE"


def test_token_missing_secret_fail_closed(monkeypatch):
    monkeypatch.delenv("PAYMENT_LAUNCH_SECRET", raising=False)
    with pytest.raises(PaymentLaunchConfigError):
        create_payment_launch_token(payment_id="pay-1", provider=_provider(), now=1_000)
    with pytest.raises(PaymentLaunchConfigError):
        verify_payment_launch_token("a.b", now=1_000)


def test_token_weak_secret_fail_closed(monkeypatch):
    monkeypatch.setenv("PAYMENT_LAUNCH_SECRET", "short")
    with pytest.raises(PaymentLaunchConfigError):
        create_payment_launch_token(payment_id="pay-1", provider=_provider(), now=1_000)


def test_token_malformed_rejected():
    for raw in ("", "abc", "a.b.c", ".", "aaa.", ".bbb"):
        with pytest.raises((PaymentLaunchTokenError, PaymentLaunchConfigError)):
            verify_payment_launch_token(raw, now=1_000)


def test_token_missing_payment_id_rejected():
    env = {
        "v": 1,
        "purpose": "SAAS_TIER_UPGRADE",
        "iat": 1_000,
        "exp": 1_300,
        "payment_id": "",
        "provider": _provider(),
    }
    with pytest.raises(PaymentLaunchTokenError):
        verify_payment_launch_token(_sign_envelope(env), now=1_010)


def test_token_missing_provider_field_rejected():
    prov = _provider()
    del prov["oid"]
    env = {
        "v": 1,
        "purpose": "SAAS_TIER_UPGRADE",
        "iat": 1_000,
        "exp": 1_300,
        "payment_id": "pay-1",
        "provider": prov,
    }
    with pytest.raises(PaymentLaunchTokenError):
        verify_payment_launch_token(_sign_envelope(env), now=1_010)


def test_static_launch_svc_no_pricing_or_prepare():
    src = LAUNCH_SVC.read_text()
    assert "run_inicis_prepare" not in src
    assert "prepare_saas_tier_upgrade" not in src
    assert "resolve_plan" not in src
    assert "evaluate_saas_tier_gate" not in src
    assert "apply_saas_tier_upgrade" not in src
    assert "jwt" not in src.lower()
    assert "INICIS_SIGN_KEY" not in src
    assert "SUPABASE" not in src


def test_static_template_is_renderer_only():
    src = PAY_TPL.read_text()
    assert "INIStdPay.js" in src
    assert "SendPayForm_id" in src
    assert "INIStdPay.pay('SendPayForm_id')" in src
    assert "fetch(" not in src
    assert "prepare" not in src
    assert "vat" not in src.lower()
    assert "plan_code" not in src


def test_html_render_required_fields_and_xss():
    html = render_launch_success(
        _provider(
            goodname="<script>alert(1)</script>",
            buyername='"><img onerror>',
        )
    )
    assert "INIStdPay.js" in html
    assert "SendPayForm_id" in html
    assert "INIStdPay.pay('SendPayForm_id')" in html
    assert "TAIOID1" in html
    assert "165000" in html
    assert "sighex" in html
    assert "1710000000000" in html
    assert DEFAULT_RETURN_URL in html
    assert "resultCode=CLOSE" in html
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert '"><img onerror>' not in html
    assert "&lt;img" in html


class _FakeResponse:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, table: str, sb: "_LaunchSB"):
        self._table = table
        self._sb = sb
        self._filters = []
        self._limit = None
        self._op = "select"
        self._payload = None

    def select(self, *_a, **_k):
        self._op = "select"
        return self

    def eq(self, col, val):
        self._filters.append((col, val))
        return self

    def limit(self, n):
        self._limit = n
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def execute(self):
        if self._op == "insert":
            self._sb.writes.append(("insert", self._table, self._payload))
            return _FakeResponse([])
        if self._op == "update":
            self._sb.writes.append(("update", self._table, self._payload))
            return _FakeResponse([])
        rows = list(self._sb.store.get(self._table, []))
        for col, val in self._filters:
            rows = [r for r in rows if r.get(col) == val]
        if self._limit is not None:
            rows = rows[: self._limit]
        return _FakeResponse(rows)


class _LaunchSB:
    def __init__(self, store: dict):
        self.store = store
        self.writes = []

    def table(self, name: str):
        return _FakeQuery(name, self)


def _ready_store(**pay_over):
    pay = {
        "id": "pay-1",
        "status_code": "PENDING",
        "payment_type": "UPGRADE",
        "inicis_order_id": "TAIOID1",
        "total_amount": 165000,
    }
    pay.update(pay_over)
    return {
        "payments": [pay],
        "saas_tier_upgrade_transitions": [
            {"payment_id": "pay-1", "status": "PREPARED"},
        ],
    }


try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    _HAS_CLIENT = True
except Exception:  # noqa: BLE001
    _HAS_CLIENT = False

requires_client = pytest.mark.skipif(not _HAS_CLIENT, reason="httpx/TestClient 미설치")


def _client(monkeypatch, sb):
    import routers.payment as pay_mod

    monkeypatch.setattr(pay_mod, "get_supabase", lambda: sb)
    app = FastAPI()
    app.include_router(pay_mod.router)
    return TestClient(app)


def _post_pay(client, token: str):
    return client.post("/payments/tier-upgrade/pay", data={"token": token})


@requires_client
def test_launch_valid_pending_prepared_200_html(monkeypatch):
    sb = _LaunchSB(_ready_store())
    token = create_payment_launch_token(payment_id="pay-1", provider=_provider())
    r = _post_pay(_client(monkeypatch, sb), token)
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    assert r.headers.get("Cache-Control") == "no-store"
    assert "INIStdPay.pay('SendPayForm_id')" in r.text
    assert "TAIOID1" in r.text
    assert sb.writes == []


@requires_client
def test_launch_invalid_token_403_no_pay(monkeypatch):
    sb = _LaunchSB(_ready_store())
    r = _post_pay(_client(monkeypatch, sb), "not-a-token")
    assert r.status_code == 403
    assert "INIStdPay.pay" not in r.text
    assert "결제를 시작할 수 없습니다" in r.text
    assert "pay-1" not in r.text


@requires_client
def test_launch_expired_token_403_no_pay(monkeypatch):
    sb = _LaunchSB(_ready_store())
    token = create_payment_launch_token(payment_id="pay-1", provider=_provider(), now=1_000)
    monkeypatch.setattr(launch_svc.time, "time", lambda: 1_000 + 301)
    r = _post_pay(_client(monkeypatch, sb), token)
    assert r.status_code == 403
    assert "INIStdPay.pay" not in r.text


@requires_client
def test_launch_payment_not_found_404(monkeypatch):
    sb = _LaunchSB({"payments": [], "saas_tier_upgrade_transitions": []})
    token = create_payment_launch_token(payment_id="pay-missing", provider=_provider())
    r = _post_pay(_client(monkeypatch, sb), token)
    assert r.status_code == 404
    assert "INIStdPay.pay" not in r.text


@pytest.mark.parametrize(
    "over,code",
    [
        ({"status_code": "SUCCESS"}, 409),
        ({"status_code": "FAILED"}, 409),
        ({"status_code": "CANCELLED"}, 409),
        ({"status_code": "REFUNDED"}, 409),
        ({"payment_type": "CARD"}, 409),
        ({"inicis_order_id": "OTHER"}, 409),
        ({"total_amount": 1}, 409),
    ],
)
@requires_client
def test_launch_payment_mismatch_409(monkeypatch, over, code):
    sb = _LaunchSB(_ready_store(**over))
    token = create_payment_launch_token(payment_id="pay-1", provider=_provider())
    r = _post_pay(_client(monkeypatch, sb), token)
    assert r.status_code == code
    assert "INIStdPay.pay" not in r.text


@requires_client
def test_launch_transition_missing_409(monkeypatch):
    store = _ready_store()
    store["saas_tier_upgrade_transitions"] = []
    sb = _LaunchSB(store)
    token = create_payment_launch_token(payment_id="pay-1", provider=_provider())
    r = _post_pay(_client(monkeypatch, sb), token)
    assert r.status_code == 409
    assert "INIStdPay.pay" not in r.text


@requires_client
def test_launch_transition_not_prepared_409(monkeypatch):
    store = _ready_store()
    store["saas_tier_upgrade_transitions"] = [{"payment_id": "pay-1", "status": "APPLIED"}]
    sb = _LaunchSB(store)
    token = create_payment_launch_token(payment_id="pay-1", provider=_provider())
    r = _post_pay(_client(monkeypatch, sb), token)
    assert r.status_code == 409


@requires_client
def test_launch_no_side_effect_and_no_second_prepare(monkeypatch):
    calls = {"run": 0, "prep": 0}

    def boom_run(*_a, **_k):
        calls["run"] += 1
        raise AssertionError("run_inicis_prepare")

    def boom_prep(*_a, **_k):
        calls["prep"] += 1
        raise AssertionError("prepare_saas_tier_upgrade")

    monkeypatch.setattr("services.payment_svc.run_inicis_prepare", boom_run)
    monkeypatch.setattr("services.tier_upgrade_svc.prepare_saas_tier_upgrade", boom_prep)
    monkeypatch.setattr("routers.payment.prepare_saas_tier_upgrade", boom_prep)
    monkeypatch.setattr("routers.payment.run_inicis_prepare", boom_run)

    sb = _LaunchSB(_ready_store())
    before = list(sb.writes)
    token = create_payment_launch_token(payment_id="pay-1", provider=_provider())
    r = _post_pay(_client(monkeypatch, sb), token)
    assert r.status_code == 200
    assert calls == {"run": 0, "prep": 0}
    assert sb.writes == before


@requires_client
def test_prepare_contract_adds_launch(monkeypatch):
    from tests.test_tier_upgrade_svc import CALLER, FAC_IND, _FakeSB, _base_store

    store = _base_store()
    sb = _FakeSB(store)
    monkeypatch.setattr("services.payment_svc.get_supabase", lambda: sb)
    import routers.payment as pay_mod

    monkeypatch.setattr(pay_mod, "get_supabase", lambda: sb)
    monkeypatch.setattr(pay_mod, "get_current_user", lambda authorization=None: CALLER)
    app = FastAPI()
    app.include_router(pay_mod.router)
    with TestClient(app) as c:
        r = c.post("/payments/tier-upgrade/prepare", json={"factory_id": FAC_IND})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert body["launch"]["method"] == "POST"
    assert body["launch"]["url"] == "https://taieng.co.kr/_api/payments/tier-upgrade/pay"
    assert body["launch"]["token"]
    env = verify_payment_launch_token(body["launch"]["token"])
    assert env["payment_id"] == body["data"]["payment_id"]
    assert env["provider"]["oid"] == body["data"]["oid"]
    assert env["provider"]["price"] == body["data"]["price"]
    pay_writes = [w for w in sb.writes if w[0] == "insert" and w[1] == "payments"]
    tr_writes = [w for w in sb.writes if w[0] == "insert" and w[1] == "saas_tier_upgrade_transitions"]
    assert len(pay_writes) == 1
    assert len(tr_writes) == 1


@requires_client
def test_prepare_return_url_allowed_and_rejected(monkeypatch):
    from tests.test_tier_upgrade_svc import CALLER, CO_OWN, FAC_IND, _FakeSB, _base_store

    store = _base_store()
    fac2 = "fac-ind-root"
    store["factories"].append(
        {"id": fac2, "company_id": CO_OWN, "employee_count": 80, "building_area": 500}
    )
    sb = _FakeSB(store)
    monkeypatch.setattr("services.payment_svc.get_supabase", lambda: sb)
    import routers.payment as pay_mod

    monkeypatch.setattr(pay_mod, "get_supabase", lambda: sb)
    monkeypatch.setattr(pay_mod, "get_current_user", lambda authorization=None: CALLER)
    app = FastAPI()
    app.include_router(pay_mod.router)
    with TestClient(app) as c:
        ok = c.post(
            "/payments/tier-upgrade/prepare",
            json={"factory_id": FAC_IND, "return_url": "https://safe.taieng.co.kr/app"},
        )
        bad_ext = c.post(
            "/payments/tier-upgrade/prepare",
            json={"factory_id": FAC_IND, "return_url": "https://evil.example/x"},
        )
        bad_js = c.post(
            "/payments/tier-upgrade/prepare",
            json={"factory_id": FAC_IND, "return_url": "javascript:alert(1)"},
        )
        bad_mal = c.post(
            "/payments/tier-upgrade/prepare",
            json={"factory_id": FAC_IND, "return_url": "not a url"},
        )
        ok_root = c.post(
            "/payments/tier-upgrade/prepare",
            json={"factory_id": fac2, "return_url": "https://taieng.co.kr/ok"},
        )
    assert ok.status_code == 200
    env = verify_payment_launch_token(ok.json()["launch"]["token"])
    parsed = urlparse(env["provider"]["returnUrl"])
    assert parsed.netloc == urlparse(DEFAULT_RETURN_URL).netloc
    assert parse_qs(parsed.query).get("front") == ["https://safe.taieng.co.kr/app"]
    assert bad_ext.status_code == 422
    assert bad_js.status_code == 422
    assert bad_mal.status_code == 422
    assert ok_root.status_code == 200


def test_attach_preserves_prepare_contract():
    prepared = {
        "status": "success",
        "data": {"payment_id": "pay-1", **_provider()},
        "upgrade": {"from_plan_code": "A", "target_plan_code": "B"},
    }
    out = attach_tier_upgrade_launch(prepared, now=1_700_000_000)
    assert out["status"] == "success"
    assert out["upgrade"]["target_plan_code"] == "B"
    assert out["data"]["oid"] == "TAIOID1"
    assert out["launch"]["method"] == "POST"


def test_all_provider_fields_listed():
    assert PROVIDER_FIELDS == (
        "mid",
        "mKey",
        "oid",
        "price",
        "goodname",
        "buyername",
        "buyertel",
        "buyeremail",
        "timestamp",
        "signature",
        "verification",
        "use_chkfake",
        "returnUrl",
        "closeUrl",
        "charset",
        "gopaymethod",
    )


def test_pay_html_untouched_marker():
    # 기존 pay.html / billing_pay.html 무수정 — fetch/prepare 페이지 역할 유지.
    assert "fetch(BASE + '/payments/inicis/prepare'" in PAY_HTML.read_text()
    assert BILLING_HTML.exists()
    router_src = ROUTER.read_text()
    assert "inicis_return" in router_src
    assert "process_card_success" in router_src
    assert "/tier-upgrade/pay" in router_src
    assert "run_inicis_prepare" in router_src
