"""WO-SLACK-EVENT-HUB-001 PR-① · I1..I9

Verifies dispatcher event_type routing, blocks arg, INQUIRY/TAI_WISH via
/internal/inbox/notify (await, no fire-and-forget), removal of direct
Slack sends from inquiries writers, and back-compat of alert/ops/engine.

External Slack HTTP is fully monkey-patched (no real network).
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import os
import pathlib
from typing import Any, Dict, List
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ══════════════════════════════════════════════════════════════
# helpers / recorder
# ══════════════════════════════════════════════════════════════
class SentRecorder:
    """monkey-patched httpx.AsyncClient replacement — records dispatched payloads.

    Configurable per-instance to simulate Slack outcomes:
      * status_code: HTTP status code the fake response returns (default 200)
      * body:        JSON body dict (default {"ok": True})
      * raise_exc:   exception instance to raise inside post() (default None)
    """
    def __init__(self, status_code: int = 200,
                 body: Optional[Dict[str, Any]] = None,
                 raise_exc: Optional[BaseException] = None):
        self.calls: List[Dict[str, Any]] = []
        self.status_code = status_code
        self.body = body if body is not None else {"ok": True}
        self.raise_exc = raise_exc

    def install(self, monkeypatch, module):
        rec = self

        class _Resp:
            status_code = rec.status_code
            def json(self):  # noqa: D401
                return rec.body

        class _Client:
            def __init__(self, *a, **k): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def post(self, url, headers=None, json=None):
                rec.calls.append({"url": url, "headers": headers, "json": json})
                if rec.raise_exc is not None:
                    raise rec.raise_exc
                return _Resp()

        monkeypatch.setattr(module, "httpx", type("H", (), {"AsyncClient": _Client}))


def _prepare_env(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_ENABLED", "true")
    monkeypatch.setenv("SLACK_BOT_TOKEN1", "xoxb-test-token")
    for k in ("SLACK_CH_ALERT", "SLACK_CH_OPS", "SLACK_CH_ENGINE",
              "SLACK_CH_APPROVAL", "SLACK_CH_INQUIRY", "SLACK_CH_FREE_DIAGNOSIS",
              "SLACK_CHANNEL_ID", "SLACK_CHANNEL_ID_INBOX"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SLACK_CH_ALERT", "C_ALERT")
    monkeypatch.setenv("SLACK_CH_OPS", "C_OPS")
    monkeypatch.setenv("SLACK_CH_ENGINE", "C_ENGINE")
    monkeypatch.setenv("SLACK_CH_APPROVAL", "C_APPROVAL")
    monkeypatch.setenv("SLACK_CH_INQUIRY", "C_INQUIRY")
    monkeypatch.setenv("SLACK_CH_FREE_DIAGNOSIS", "C_FREEDIAG")


# ══════════════════════════════════════════════════════════════
# I1 · INQUIRY_CREATED → 1 call, INQUIRY 채널
# ══════════════════════════════════════════════════════════════
def test_i1_inquiry_created_routed_to_inquiry_channel(monkeypatch):
    _prepare_env(monkeypatch)
    from services import slack_dispatcher as sd
    rec = SentRecorder(); rec.install(monkeypatch, sd)
    asyncio.run(sd.send_slack("INQUIRY_CREATED", "INFO", "새 문의", blocks=[{"type": "section"}]))
    assert len(rec.calls) == 1
    body = rec.calls[0]["json"]
    assert body["channel"] == "C_INQUIRY"
    assert body["blocks"] == [{"type": "section"}]
    assert body["text"]  # fallback text present


# ══════════════════════════════════════════════════════════════
# I2 · TAI_WISH_CREATED → 1 call, INQUIRY 채널, "TAI에 바란다" label in blocks
# ══════════════════════════════════════════════════════════════
def test_i2_tai_wish_created_uses_wish_label_and_inquiry_channel(monkeypatch):
    _prepare_env(monkeypatch)
    from services import slack_dispatcher as sd
    from services.inbox_notify_svc import build_blocks
    rec = SentRecorder(); rec.install(monkeypatch, sd)
    record = {"inquiry_type": "FEEDBACK", "category": "fb_bug", "source": "safe",
              "name": "홍길동", "content": "bug!"}
    blocks = build_blocks(record)
    asyncio.run(sd.send_slack("TAI_WISH_CREATED", "INFO", "wish", blocks=blocks))
    assert len(rec.calls) == 1
    body = rec.calls[0]["json"]
    assert body["channel"] == "C_INQUIRY"
    header = body["blocks"][0]
    assert header["type"] == "header"
    assert "TAI에 바란다" in header["text"]["text"]


# ══════════════════════════════════════════════════════════════
# I3 · writer direct-Slack in inquiries writers = 0 (static grep on source)
# ══════════════════════════════════════════════════════════════
def test_i3_inquiries_writers_have_zero_direct_slack():
    for rel in ("routers/member_inquiries.py", "routers/site_public.py"):
        src = pathlib.Path(rel).read_text(encoding="utf-8")
        for needle in ("dispatcher.ops", "dispatcher.alert", "dispatcher.engine",
                       "from services.slack_dispatcher import ops",
                       "from services.slack_dispatcher import alert",
                       "from services.slack_dispatcher import engine",
                       "send_slack(", "send_slack_sync(",
                       "chat.postMessage", "slack.com/api"):
            assert needle not in src, f"{rel} still contains direct Slack: {needle!r}"


# ══════════════════════════════════════════════════════════════
# I4 · inbox_notify_svc has NO direct Slack (formatter-only)
# ══════════════════════════════════════════════════════════════
def test_i4_inbox_notify_svc_is_formatter_only():
    src = pathlib.Path("services/inbox_notify_svc.py").read_text(encoding="utf-8")
    for needle in ("chat.postMessage", "slack.com/api", "SLACK_BOT_TOKEN",
                   "SLACK_CHANNEL_ID_INBOX", "httpx", "import httpx"):
        assert needle not in src, f"inbox_notify_svc still references {needle!r}"
    # sender function must be gone
    assert "def send_inbox_notification" not in src
    # formatter must remain
    assert "def build_blocks" in src


# ══════════════════════════════════════════════════════════════
# I5 · legacy ops()/alert()/engine() 회귀 — 기존 severity routing 유지
# ══════════════════════════════════════════════════════════════
def test_i5_legacy_severity_routing_intact(monkeypatch):
    _prepare_env(monkeypatch)
    from services import slack_dispatcher as sd

    # (a) alert → CHANNEL_ALERT
    rec = SentRecorder(); rec.install(monkeypatch, sd)
    asyncio.run(sd.send_slack("MANUAL_ALERT", "CRITICAL", "boom"))
    assert rec.calls[0]["json"]["channel"] == "C_ALERT"

    # (b) ops (INFO) → CHANNEL_OPS
    rec = SentRecorder(); rec.install(monkeypatch, sd)
    asyncio.run(sd.send_slack("OPS_EVENT", "INFO", "hello"))
    assert rec.calls[0]["json"]["channel"] == "C_OPS"

    # (c) engine event → CHANNEL_ENGINE
    rec = SentRecorder(); rec.install(monkeypatch, sd)
    asyncio.run(sd.send_slack("OBLIGATION_DRIFT_DETECTED", "INFO", "drift"))
    assert rec.calls[0]["json"]["channel"] == "C_ENGINE"


# ══════════════════════════════════════════════════════════════
# I6 · blocks=None vs blocks=[…] 양립
# ══════════════════════════════════════════════════════════════
def test_i6_blocks_optional_backward_compat(monkeypatch):
    _prepare_env(monkeypatch)
    from services import slack_dispatcher as sd

    # (a) blocks None → payload has no 'blocks', text present
    rec = SentRecorder(); rec.install(monkeypatch, sd)
    asyncio.run(sd.send_slack("OPS_EVENT", "INFO", "no-blocks-title", detail="body"))
    body = rec.calls[0]["json"]
    assert "blocks" not in body
    assert "no-blocks-title" in body["text"]
    assert "body" in body["text"]

    # (b) blocks present → payload has 'blocks', text is fallback (no detail appended)
    rec = SentRecorder(); rec.install(monkeypatch, sd)
    asyncio.run(sd.send_slack("INQUIRY_CREATED", "INFO", "title", detail="irrelevant",
                              blocks=[{"type": "section"}]))
    body = rec.calls[0]["json"]
    assert body["blocks"] == [{"type": "section"}]
    assert "title" in body["text"]
    assert "irrelevant" not in body["text"]


# ══════════════════════════════════════════════════════════════
# I7 · /internal/inbox/notify · secret 403 / 정상 200 + INQUIRY 라우팅
# ══════════════════════════════════════════════════════════════
@pytest.fixture()
def notify_client(monkeypatch):
    _prepare_env(monkeypatch)
    monkeypatch.setenv("INTERNAL_API_SECRET", "s3cret")
    from routers.internal_inbox import router as ib_router
    app = FastAPI(); app.include_router(ib_router)
    return TestClient(app)


def test_i7a_notify_bad_secret_returns_403(notify_client, monkeypatch):
    from services import slack_dispatcher as sd
    rec = SentRecorder(); rec.install(monkeypatch, sd)
    r = notify_client.post("/internal/inbox/notify",
                           headers={"X-Internal-Secret": "wrong"},
                           json={"record": {"id": "x", "inquiry_type": "INQUIRY"}})
    assert r.status_code == 403
    assert rec.calls == []  # no Slack call attempted


def test_i7b_notify_inquiry_routes_inquiry_channel(notify_client, monkeypatch):
    from services import slack_dispatcher as sd
    rec = SentRecorder(); rec.install(monkeypatch, sd)
    r = notify_client.post("/internal/inbox/notify",
                           headers={"X-Internal-Secret": "s3cret"},
                           json={"record": {"id": "row1", "inquiry_type": "INQUIRY",
                                            "name": "A", "content": "hi",
                                            "source": "marketing", "category": "saas"}})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["event_type"] == "INQUIRY_CREATED"
    assert body["row_id"] == "row1"
    assert len(rec.calls) == 1
    assert rec.calls[0]["json"]["channel"] == "C_INQUIRY"


def test_i7c_notify_feedback_routes_wish(notify_client, monkeypatch):
    from services import slack_dispatcher as sd
    rec = SentRecorder(); rec.install(monkeypatch, sd)
    r = notify_client.post("/internal/inbox/notify",
                           headers={"X-Internal-Secret": "s3cret"},
                           json={"record": {"id": "row2", "inquiry_type": "FEEDBACK",
                                            "name": "B", "content": "wish!",
                                            "source": "safe", "category": "fb_bug"}})
    assert r.status_code == 200
    assert r.json()["event_type"] == "TAI_WISH_CREATED"
    assert rec.calls[0]["json"]["channel"] == "C_INQUIRY"


# ══════════════════════════════════════════════════════════════
# I8 · fail-safe — Slack 실패해도 200, business rollback 없음, warning 로그
# ══════════════════════════════════════════════════════════════
def test_i8_notify_slack_failure_still_returns_200(notify_client, monkeypatch, caplog):
    import services.slack_dispatcher as sd

    async def _boom(*a, **k):
        raise RuntimeError("simulated slack outage")

    monkeypatch.setattr("routers.internal_inbox.send_slack", _boom)
    caplog.set_level("WARNING", logger="internal_inbox")
    r = notify_client.post("/internal/inbox/notify",
                           headers={"X-Internal-Secret": "s3cret"},
                           json={"record": {"id": "row3", "inquiry_type": "INQUIRY",
                                            "content": "x"}})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["sent"] is False
    assert any("dispatcher call failed" in rec.message for rec in caplog.records)


# ══════════════════════════════════════════════════════════════
# I9 · no fire-and-forget — internal_inbox awaits send_slack
# ══════════════════════════════════════════════════════════════
def test_i9_notify_awaits_send_slack_source_evidence():
    """Source-level assertion: notify_inbox awaits send_slack; no ensure_future/create_task."""
    src = pathlib.Path("routers/internal_inbox.py").read_text(encoding="utf-8")
    assert "await send_slack(" in src, "notify_inbox must await send_slack"
    assert "ensure_future" not in src, "no fire-and-forget allowed here"
    assert "create_task" not in src, "no fire-and-forget allowed here"
    # AST check: notify_inbox is async def
    tree = ast.parse(src)
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.AsyncFunctionDef) and n.name == "notify_inbox"), None)
    assert fn is not None, "notify_inbox must be `async def`"
    # response returned AFTER await (last non-return statement uses await)
    has_await = any(isinstance(node, ast.Await) for node in ast.walk(fn))
    assert has_await, "notify_inbox body must include an `await` before returning"


def test_i9b_notify_response_reflects_send_attempt(notify_client, monkeypatch):
    """Behavior confirms: response.sent reflects real bool from send_slack (not merely 'attempted')."""
    called = {"done": False}

    async def _slow_but_completed(*a, **k):
        called["done"] = True
        return True  # PATCH-1 contract: send_slack returns True on success

    monkeypatch.setattr("routers.internal_inbox.send_slack", _slow_but_completed)
    r = notify_client.post("/internal/inbox/notify",
                           headers={"X-Internal-Secret": "s3cret"},
                           json={"record": {"id": "row4", "inquiry_type": "INQUIRY",
                                            "content": "x"}})
    assert r.status_code == 200
    assert r.json()["sent"] is True
    assert called["done"] is True  # send actually finished before response


# ══════════════════════════════════════════════════════════════
# S1..S7 — send_slack() bool contract (PATCH-1)
# ══════════════════════════════════════════════════════════════
def test_s1_slack_ok_true_returns_true_and_endpoint_sent_true(monkeypatch, notify_client):
    _prepare_env(monkeypatch)
    monkeypatch.setenv("INTERNAL_API_SECRET", "s3cret")
    from services import slack_dispatcher as sd
    rec = SentRecorder(status_code=200, body={"ok": True})
    rec.install(monkeypatch, sd)

    # (a) direct call bool
    result = asyncio.run(sd.send_slack("INQUIRY_CREATED", "INFO", "t", blocks=[{"type": "section"}]))
    assert result is True

    # (b) endpoint sent=true
    rec.calls.clear()
    r = notify_client.post("/internal/inbox/notify",
                           headers={"X-Internal-Secret": "s3cret"},
                           json={"record": {"id": "s1", "inquiry_type": "INQUIRY", "content": "x"}})
    assert r.status_code == 200
    assert r.json()["sent"] is True


def test_s2_channel_missing_returns_false(monkeypatch, notify_client):
    _prepare_env(monkeypatch)
    monkeypatch.setenv("INTERNAL_API_SECRET", "s3cret")
    # remove ALL possible INQUIRY channel sources (env + fallback)
    for k in ("SLACK_CH_INQUIRY", "SLACK_CHANNEL_ID_INBOX", "SLACK_CHANNEL_ID"):
        monkeypatch.delenv(k, raising=False)
    from services import slack_dispatcher as sd
    rec = SentRecorder(status_code=200, body={"ok": True}); rec.install(monkeypatch, sd)

    result = asyncio.run(sd.send_slack("INQUIRY_CREATED", "INFO", "t", blocks=[{"type": "section"}]))
    assert result is False
    assert rec.calls == []  # no HTTP attempted

    r = notify_client.post("/internal/inbox/notify",
                           headers={"X-Internal-Secret": "s3cret"},
                           json={"record": {"id": "s2", "inquiry_type": "INQUIRY", "content": "x"}})
    assert r.status_code == 200
    assert r.json()["sent"] is False


def test_s3_token_missing_returns_false(monkeypatch):
    _prepare_env(monkeypatch)
    monkeypatch.delenv("SLACK_BOT_TOKEN1", raising=False)
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    from services import slack_dispatcher as sd
    rec = SentRecorder(); rec.install(monkeypatch, sd)

    result = asyncio.run(sd.send_slack("INQUIRY_CREATED", "INFO", "t", blocks=[{"type": "section"}]))
    assert result is False
    assert rec.calls == []


def test_s4_slack_api_ok_false_returns_false(monkeypatch):
    _prepare_env(monkeypatch)
    from services import slack_dispatcher as sd
    rec = SentRecorder(status_code=200, body={"ok": False, "error": "invalid_auth"})
    rec.install(monkeypatch, sd)

    result = asyncio.run(sd.send_slack("INQUIRY_CREATED", "INFO", "t", blocks=[{"type": "section"}]))
    assert result is False
    assert len(rec.calls) == 1  # HTTP was attempted


def test_s5_http_non200_returns_false(monkeypatch):
    _prepare_env(monkeypatch)
    from services import slack_dispatcher as sd
    rec = SentRecorder(status_code=500, body={})
    rec.install(monkeypatch, sd)

    result = asyncio.run(sd.send_slack("INQUIRY_CREATED", "INFO", "t", blocks=[{"type": "section"}]))
    assert result is False
    assert len(rec.calls) == 1


def test_s6_network_exception_returns_false(monkeypatch, notify_client):
    _prepare_env(monkeypatch)
    monkeypatch.setenv("INTERNAL_API_SECRET", "s3cret")
    from services import slack_dispatcher as sd
    rec = SentRecorder(raise_exc=RuntimeError("network down"))
    rec.install(monkeypatch, sd)

    # (a) direct
    result = asyncio.run(sd.send_slack("INQUIRY_CREATED", "INFO", "t", blocks=[{"type": "section"}]))
    assert result is False

    # (b) endpoint still 200, sent=false, exception absorbed by dispatcher
    r = notify_client.post("/internal/inbox/notify",
                           headers={"X-Internal-Secret": "s3cret"},
                           json={"record": {"id": "s6", "inquiry_type": "INQUIRY", "content": "x"}})
    assert r.status_code == 200
    assert r.json()["sent"] is False


def test_s7_alert_ops_engine_regression(monkeypatch):
    """S7 restatement: severity-based legacy paths still route/send correctly with bool contract."""
    _prepare_env(monkeypatch)
    from services import slack_dispatcher as sd

    # alert
    rec = SentRecorder(status_code=200, body={"ok": True}); rec.install(monkeypatch, sd)
    result = asyncio.run(sd.send_slack("MANUAL_ALERT", "CRITICAL", "boom"))
    assert result is True
    assert rec.calls[0]["json"]["channel"] == "C_ALERT"

    # ops
    rec = SentRecorder(status_code=200, body={"ok": True}); rec.install(monkeypatch, sd)
    result = asyncio.run(sd.send_slack("OPS_EVENT", "INFO", "hi"))
    assert result is True
    assert rec.calls[0]["json"]["channel"] == "C_OPS"

    # engine event
    rec = SentRecorder(status_code=200, body={"ok": True}); rec.install(monkeypatch, sd)
    result = asyncio.run(sd.send_slack("OBLIGATION_DRIFT_DETECTED", "INFO", "drift"))
    assert result is True
    assert rec.calls[0]["json"]["channel"] == "C_ENGINE"
