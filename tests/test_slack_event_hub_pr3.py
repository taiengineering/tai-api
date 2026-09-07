"""WO-SLACK-EVENT-HUB-001 PR-③ · T1..T7

Verifies dispatcher auto-appends an "어드민에서 보기" button when blocks is not
provided and the event_type has an admin path; and that inbox_notify build_blocks
uses the unified Vue3 admin URL (/inquiry-list).

Slack HTTP is fully monkey-patched.
"""
from __future__ import annotations

import asyncio
import pathlib
from typing import Any, Dict, List, Optional

import pytest


# ══════════════════════════════════════════════════════════════
# helpers
# ══════════════════════════════════════════════════════════════
class SentRecorder:
    """monkey-patched httpx.AsyncClient — records dispatched payloads.

    Signals a successful Slack response by default.
    """
    def __init__(self, status_code: int = 200,
                 body: Optional[Dict[str, Any]] = None):
        self.calls: List[Dict[str, Any]] = []
        self.status_code = status_code
        self.body = body if body is not None else {"ok": True}

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
                return _Resp()

        monkeypatch.setattr(module, "httpx", type("H", (), {"AsyncClient": _Client}))


def _prepare_env(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_ENABLED", "true")
    monkeypatch.setenv("SLACK_BOT_TOKEN1", "xoxb-test")
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


def _extract_button_url(blocks: List[Dict[str, Any]]) -> Optional[str]:
    for b in blocks or []:
        if b.get("type") == "actions":
            for el in b.get("elements", []):
                if el.get("type") == "button" and "url" in el:
                    return el["url"]
    return None


# ══════════════════════════════════════════════════════════════
# T1 · QUOTE_MANUAL_REQUESTED (blocks 없음) → 자동 버튼 blocks + url=/quote-list
# ══════════════════════════════════════════════════════════════
def test_t1_quote_manual_auto_button(monkeypatch):
    _prepare_env(monkeypatch)
    from services import slack_dispatcher as sd
    rec = SentRecorder(); rec.install(monkeypatch, sd)
    asyncio.run(sd.send_slack("QUOTE_MANUAL_REQUESTED", "INFO",
                              "수동 견적요청 · Acme", "detail body"))
    assert len(rec.calls) == 1
    body = rec.calls[0]["json"]
    assert body["channel"] == "C_APPROVAL"
    assert "blocks" in body, "dispatcher must auto-append blocks when event has admin path"
    url = _extract_button_url(body["blocks"])
    assert url == "https://admin.taieng.co.kr/quote-list", url
    # section carries the original text (with severity/title)
    assert any(b.get("type") == "section" and "수동 견적요청" in (
        (b.get("text") or {}).get("text", "")) for b in body["blocks"])
    # fallback text still present
    assert "text" in body and "수동 견적요청" in body["text"]


# ══════════════════════════════════════════════════════════════
# T2 · FREE_DIAGNOSIS_COMPLETED (blocks 없음) → url=/anon-diagnosis-list
# ══════════════════════════════════════════════════════════════
def test_t2_free_diagnosis_auto_button(monkeypatch):
    _prepare_env(monkeypatch)
    from services import slack_dispatcher as sd
    rec = SentRecorder(); rec.install(monkeypatch, sd)
    asyncio.run(sd.send_slack("FREE_DIAGNOSIS_COMPLETED", "INFO",
                              "무료진단 완료 · IND", "detail body"))
    assert len(rec.calls) == 1
    body = rec.calls[0]["json"]
    assert body["channel"] == "C_FREEDIAG"
    url = _extract_button_url(body["blocks"])
    assert url == "https://admin.taieng.co.kr/anon-diagnosis-list", url


# ══════════════════════════════════════════════════════════════
# T3 · INQUIRY blocks-path (호출부가 blocks 제공) → dispatcher 버튼 append 안 함 (중복 0)
# ══════════════════════════════════════════════════════════════
def test_t3_inquiry_blocks_path_no_duplicate_button(monkeypatch):
    _prepare_env(monkeypatch)
    from services import slack_dispatcher as sd
    from services.inbox_notify_svc import build_blocks
    rec = SentRecorder(); rec.install(monkeypatch, sd)
    record = {"inquiry_type": "INQUIRY", "category": "saas", "source": "marketing",
              "name": "홍길동", "content": "hello"}
    blocks = build_blocks(record)
    asyncio.run(sd.send_slack("INQUIRY_CREATED", "INFO", "새 문의", blocks=blocks))
    assert len(rec.calls) == 1
    body = rec.calls[0]["json"]
    assert body["channel"] == "C_INQUIRY"
    # dispatcher must pass build_blocks through unchanged — NOT append extra button block
    assert body["blocks"] == blocks, "dispatcher must not mutate blocks when caller provides them"
    # exactly one actions block (from build_blocks), url = unified /inquiry-list
    action_blocks = [b for b in body["blocks"] if b.get("type") == "actions"]
    assert len(action_blocks) == 1, "must be exactly one actions block (no duplicate)"
    url = _extract_button_url(body["blocks"])
    assert url == "https://admin.taieng.co.kr/inquiry-list", url


# ══════════════════════════════════════════════════════════════
# T4 · build_blocks button URL 통일 — INQUIRY 와 FEEDBACK 양쪽
# ══════════════════════════════════════════════════════════════
def test_t4_build_blocks_button_url_unified():
    from services.inbox_notify_svc import build_blocks, ADMIN_INQUIRY_URL, ADMIN_BASE_URL
    # unified base + path
    assert ADMIN_BASE_URL == "https://admin.taieng.co.kr"
    assert ADMIN_INQUIRY_URL == "https://admin.taieng.co.kr/inquiry-list"
    for it in ("INQUIRY", "FEEDBACK"):
        record = {"inquiry_type": it, "category": "saas" if it == "INQUIRY" else "fb_bug",
                  "source": "marketing", "name": "X", "content": "x"}
        blocks = build_blocks(record)
        url = _extract_button_url(blocks)
        assert url == ADMIN_INQUIRY_URL, f"{it} button url mismatch: {url}"
    # legacy .html path must be gone from module
    src = pathlib.Path("services/inbox_notify_svc.py").read_text(encoding="utf-8")
    assert "inquiry-list.html" not in src, "legacy html path must be removed"


# ══════════════════════════════════════════════════════════════
# T5 · 회귀 — 매핑 없는 event_type + blocks 없음 → payload.blocks 부재, text-only
# ══════════════════════════════════════════════════════════════
def test_t5_unmapped_event_no_button_no_blocks(monkeypatch):
    _prepare_env(monkeypatch)
    from services import slack_dispatcher as sd
    rec = SentRecorder(); rec.install(monkeypatch, sd)
    asyncio.run(sd.send_slack("OPS_EVENT", "INFO", "some ops title", "extra detail"))
    assert len(rec.calls) == 1
    body = rec.calls[0]["json"]
    assert "blocks" not in body, "unmapped event_type must not auto-append blocks"
    assert "some ops title" in body["text"]
    assert "extra detail" in body["text"]


# ══════════════════════════════════════════════════════════════
# T6 · alert/ops/engine severity routing 회귀 (매핑 없는 이벤트, 각 채널 정확)
# ══════════════════════════════════════════════════════════════
def test_t6_legacy_severity_routing_intact(monkeypatch):
    _prepare_env(monkeypatch)
    from services import slack_dispatcher as sd

    # alert
    rec = SentRecorder(); rec.install(monkeypatch, sd)
    asyncio.run(sd.send_slack("MANUAL_ALERT", "CRITICAL", "boom"))
    assert rec.calls[0]["json"]["channel"] == "C_ALERT"
    assert "blocks" not in rec.calls[0]["json"]

    # ops
    rec = SentRecorder(); rec.install(monkeypatch, sd)
    asyncio.run(sd.send_slack("OPS_EVENT", "INFO", "hi"))
    assert rec.calls[0]["json"]["channel"] == "C_OPS"

    # engine
    rec = SentRecorder(); rec.install(monkeypatch, sd)
    asyncio.run(sd.send_slack("OBLIGATION_DRIFT_DETECTED", "INFO", "drift"))
    assert rec.calls[0]["json"]["channel"] == "C_ENGINE"


# ══════════════════════════════════════════════════════════════
# T7 · inbox_notify formatter-only 유지 (PR-① I4 계약 확장 · 여전히 Slack sender 부재)
# ══════════════════════════════════════════════════════════════
def test_t7_inbox_notify_svc_still_formatter_only():
    src = pathlib.Path("services/inbox_notify_svc.py").read_text(encoding="utf-8")
    for needle in ("chat.postMessage", "slack.com/api", "SLACK_BOT_TOKEN",
                   "SLACK_CHANNEL_ID_INBOX", "httpx", "import httpx"):
        assert needle not in src, f"inbox_notify still references {needle!r}"
    assert "def send_inbox_notification" not in src
    assert "def build_blocks" in src
    assert "def resolve_event_type" in src
    assert "def fallback_title" in src
