"""WO-QA-CONTROL-PHASE2C-001 — QA Slack Notification 계약 테스트.

Production QA table write = 0. Real Slack dispatch = 0.

QC-01..14  item status transition events
QR-01..04  run error notification
QS-01..07  channel routing + admin link
QF-01..05  fail-safe + source static checks
"""
from __future__ import annotations

import asyncio
import pathlib
from typing import Any, Dict, List, Optional

import pytest
import services.qa_control_svc as svc
import services.qa_notify_svc as notify
from services.slack_dispatcher import (
    CHANNEL_ALERT, CHANNEL_OPS, CHANNEL_QA,
    EVENT_TYPE_ADMIN_PATH, EVENT_TYPE_CHANNEL,
    _get_channel_id, _resolve_channel,
)


# ─────────────────────────────────────────────────────────────────────────────
# Mock helpers
# ─────────────────────────────────────────────────────────────────────────────

class _Q:
    def __init__(self, rows=None, count=None):
        self._rows = rows or []
        self._count = count if count is not None else len(self._rows)
    def select(self, *a, **k): return self
    def eq(self, *a, **k):     return self
    def in_(self, *a, **k):    return self
    def order(self, *a, **k):  return self
    def limit(self, *a, **k):  return self
    def insert(self, rows, **k): return self
    def update(self, *a, **k): return self
    def delete(self, *a, **k): return self
    def execute(self):
        return type("R", (), {"data": self._rows, "count": self._count})()


class _ResultsQ:
    """Stateful mock: SELECT eq(run_id) → current, SELECT in_(qa_item_id) → history."""
    def __init__(self, current=None, history=None):
        self._current  = current or []
        self._history  = history or []
        self._mode     = "current"
        self.last_insert = None

    def select(self, *a, **k): return self
    def eq(self, field, val, **k):
        if field == "run_id":
            self._mode = "current"
        return self
    def in_(self, field, val, **k):
        if field == "qa_item_id":
            self._mode = "history"
        return self
    def order(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def insert(self, rows, **k):
        self.last_insert = rows
        self._mode = "insert"
        return self
    def execute(self):
        if self._mode == "history":
            return type("R", (), {"data": self._history})()
        if self._mode == "insert":
            return type("R", (), {"data": self.last_insert or []})()
        return type("R", (), {"data": self._current})()


class _Supabase:
    def __init__(self, table_map):
        self._map = table_map
    def table(self, name):
        return self._map.get(name, _Q())


def _run_row(status="QUEUED", started=None, finished=None, gri=None, gra=None):
    return {
        "id": "run-1", "trigger_type": "MANUAL", "run_status": status,
        "github_run_id": gri, "github_run_attempt": gra,
        "head_sha": None, "branch_name": None,
        "requested_by": None, "requested_at": "2026-10-01T00:00:00+09:00",
        "started_at": started, "finished_at": finished,
        "error_code": None, "error_summary": None,
        "created_at": "2026-10-01T00:00:00+09:00",
        "updated_at": "2026-10-01T00:00:00+09:00",
    }


def _mutable_run_q(status="RUNNING"):
    class _MQ(_Q):
        def update(self, *a, **k): return _Q(rows=[_run_row(status)])
    return _MQ(rows=[_run_row(status)])


def _qa_items_q(scenario_id="P0-WWW-001", item_id="item-1"):
    return _Q(rows=[{
        "id": item_id, "scenario_id": scenario_id,
        "site_code": "WWW", "name": "Login flow", "enabled": True,
    }])


def _targets_q(item_id="item-1"):
    return _Q(rows=[{"qa_item_id": item_id}])


def _call(sb, results=None, new_status=None, run_error_summary=None):
    return svc.apply_results(
        sb,
        run_id="run-1",
        new_status=new_status,
        github_run_id=None,
        github_run_attempt=None,
        head_sha=None,
        branch_name=None,
        run_started_at=None,
        run_finished_at=None,
        run_error_code=None,
        run_error_summary=run_error_summary,
        results=results or [],
    )


def _hist_row(run_id="run-prev", item_id="item-1", status="PASS",
              attempt=1, checked_at="2026-10-01T00:00:00+09:00"):
    return {
        "run_id": run_id, "qa_item_id": item_id,
        "result_status": status, "attempt": attempt,
        "checked_at": checked_at,
    }


def _new_result(status="FAIL", attempt=1):
    return {"scenario_id": "P0-WWW-001", "result_status": status, "attempt": attempt}


# ─────────────────────────────────────────────────────────────────────────────
# QC-01: NEVER_RUN → FAIL → QA_FAIL_DETECTED
# ─────────────────────────────────────────────────────────────────────────────

def test_QC01_never_run_to_fail():
    sb = _Supabase({
        "qa_runs":        _mutable_run_q(),
        "qa_items":       _qa_items_q(),
        "qa_run_targets": _targets_q(),
        "qa_run_results": _ResultsQ(current=[], history=[]),
    })
    data = _call(sb, results=[_new_result("FAIL")])
    assert any(n["event_type"] == "QA_FAIL_DETECTED" for n in data["notifications"])


# ─────────────────────────────────────────────────────────────────────────────
# QC-02: PASS → FAIL → QA_FAIL_DETECTED
# ─────────────────────────────────────────────────────────────────────────────

def test_QC02_pass_to_fail():
    hist = [_hist_row(status="PASS")]
    sb = _Supabase({
        "qa_runs":        _mutable_run_q(),
        "qa_items":       _qa_items_q(),
        "qa_run_targets": _targets_q(),
        "qa_run_results": _ResultsQ(current=[], history=hist),
    })
    data = _call(sb, results=[_new_result("FAIL")])
    events = [n["event_type"] for n in data["notifications"]]
    assert events == ["QA_FAIL_DETECTED"]


# ─────────────────────────────────────────────────────────────────────────────
# QC-03: FAIL → FAIL → notification 0
# ─────────────────────────────────────────────────────────────────────────────

def test_QC03_fail_to_fail_no_notify():
    hist = [_hist_row(status="FAIL")]
    sb = _Supabase({
        "qa_runs":        _mutable_run_q(),
        "qa_items":       _qa_items_q(),
        "qa_run_targets": _targets_q(),
        "qa_run_results": _ResultsQ(current=[], history=hist),
    })
    data = _call(sb, results=[_new_result("FAIL")])
    assert data["notifications"] == []


# ─────────────────────────────────────────────────────────────────────────────
# QC-04: PASS → BLOCKED → QA_BLOCKED_DETECTED
# ─────────────────────────────────────────────────────────────────────────────

def test_QC04_pass_to_blocked():
    hist = [_hist_row(status="PASS")]
    sb = _Supabase({
        "qa_runs":        _mutable_run_q(),
        "qa_items":       _qa_items_q(),
        "qa_run_targets": _targets_q(),
        "qa_run_results": _ResultsQ(current=[], history=hist),
    })
    data = _call(sb, results=[_new_result("BLOCKED")])
    assert any(n["event_type"] == "QA_BLOCKED_DETECTED" for n in data["notifications"])


# ─────────────────────────────────────────────────────────────────────────────
# QC-05: BLOCKED → BLOCKED → notification 0
# ─────────────────────────────────────────────────────────────────────────────

def test_QC05_blocked_to_blocked_no_notify():
    hist = [_hist_row(status="BLOCKED")]
    sb = _Supabase({
        "qa_runs":        _mutable_run_q(),
        "qa_items":       _qa_items_q(),
        "qa_run_targets": _targets_q(),
        "qa_run_results": _ResultsQ(current=[], history=hist),
    })
    data = _call(sb, results=[_new_result("BLOCKED")])
    assert data["notifications"] == []


# ─────────────────────────────────────────────────────────────────────────────
# QC-06: PASS → FLAKY → QA_FLAKY_DETECTED
# ─────────────────────────────────────────────────────────────────────────────

def test_QC06_pass_to_flaky():
    hist = [_hist_row(status="PASS")]
    sb = _Supabase({
        "qa_runs":        _mutable_run_q(),
        "qa_items":       _qa_items_q(),
        "qa_run_targets": _targets_q(),
        "qa_run_results": _ResultsQ(current=[], history=hist),
    })
    # FAIL attempt=1 + PASS attempt=2 → FLAKY
    data = _call(sb, results=[_new_result("FAIL", 1), _new_result("PASS", 2)])
    assert any(n["event_type"] == "QA_FLAKY_DETECTED" for n in data["notifications"])


# ─────────────────────────────────────────────────────────────────────────────
# QC-07: FAIL → FLAKY → QA_FLAKY_DETECTED
# ─────────────────────────────────────────────────────────────────────────────

def test_QC07_fail_to_flaky():
    hist = [_hist_row(status="FAIL")]
    sb = _Supabase({
        "qa_runs":        _mutable_run_q(),
        "qa_items":       _qa_items_q(),
        "qa_run_targets": _targets_q(),
        "qa_run_results": _ResultsQ(current=[], history=hist),
    })
    data = _call(sb, results=[_new_result("FAIL", 1), _new_result("PASS", 2)])
    assert any(n["event_type"] == "QA_FLAKY_DETECTED" for n in data["notifications"])


# ─────────────────────────────────────────────────────────────────────────────
# QC-08: FAIL → PASS → QA_RECOVERED
# ─────────────────────────────────────────────────────────────────────────────

def test_QC08_fail_to_pass_recovered():
    hist = [_hist_row(status="FAIL")]
    sb = _Supabase({
        "qa_runs":        _mutable_run_q(),
        "qa_items":       _qa_items_q(),
        "qa_run_targets": _targets_q(),
        "qa_run_results": _ResultsQ(current=[], history=hist),
    })
    data = _call(sb, results=[_new_result("PASS")])
    assert any(n["event_type"] == "QA_RECOVERED" for n in data["notifications"])


# ─────────────────────────────────────────────────────────────────────────────
# QC-09: BLOCKED → PASS → QA_RECOVERED
# ─────────────────────────────────────────────────────────────────────────────

def test_QC09_blocked_to_pass_recovered():
    hist = [_hist_row(status="BLOCKED")]
    sb = _Supabase({
        "qa_runs":        _mutable_run_q(),
        "qa_items":       _qa_items_q(),
        "qa_run_targets": _targets_q(),
        "qa_run_results": _ResultsQ(current=[], history=hist),
    })
    data = _call(sb, results=[_new_result("PASS")])
    assert any(n["event_type"] == "QA_RECOVERED" for n in data["notifications"])


# ─────────────────────────────────────────────────────────────────────────────
# QC-10: FLAKY → PASS → QA_RECOVERED
# ─────────────────────────────────────────────────────────────────────────────

def test_QC10_flaky_to_pass_recovered():
    # prev run had FAIL+PASS → FLAKY
    hist = [
        _hist_row(run_id="run-prev", status="FAIL",  attempt=1, checked_at="2026-09-30T09:00:00+09:00"),
        _hist_row(run_id="run-prev", status="PASS",  attempt=2, checked_at="2026-09-30T09:00:01+09:00"),
    ]
    sb = _Supabase({
        "qa_runs":        _mutable_run_q(),
        "qa_items":       _qa_items_q(),
        "qa_run_targets": _targets_q(),
        "qa_run_results": _ResultsQ(current=[], history=hist),
    })
    data = _call(sb, results=[_new_result("PASS")])
    assert any(n["event_type"] == "QA_RECOVERED" for n in data["notifications"])


# ─────────────────────────────────────────────────────────────────────────────
# QC-11: PASS → PASS → 0
# ─────────────────────────────────────────────────────────────────────────────

def test_QC11_pass_to_pass_no_notify():
    hist = [_hist_row(status="PASS")]
    sb = _Supabase({
        "qa_runs":        _mutable_run_q(),
        "qa_items":       _qa_items_q(),
        "qa_run_targets": _targets_q(),
        "qa_run_results": _ResultsQ(current=[], history=hist),
    })
    data = _call(sb, results=[_new_result("PASS")])
    assert data["notifications"] == []


# ─────────────────────────────────────────────────────────────────────────────
# QC-12: anomaly → SKIPPED → 0
# ─────────────────────────────────────────────────────────────────────────────

def test_QC12_anomaly_to_skipped_no_notify():
    hist = [_hist_row(status="FAIL")]
    sb = _Supabase({
        "qa_runs":        _mutable_run_q(),
        "qa_items":       _qa_items_q(),
        "qa_run_targets": _targets_q(),
        "qa_run_results": _ResultsQ(current=[], history=hist),
    })
    data = _call(sb, results=[_new_result("SKIPPED")])
    assert data["notifications"] == []


# ─────────────────────────────────────────────────────────────────────────────
# QC-13: stale callback — latest status unchanged → 0
# ─────────────────────────────────────────────────────────────────────────────

def test_QC13_stale_callback_no_notify():
    # run-latest is PASS (far future checked_at). Callback is for run-stale (old).
    hist = [
        _hist_row(run_id="run-latest", status="PASS", checked_at="2099-01-01T00:00:00+09:00"),
    ]
    sb = _Supabase({
        "qa_runs":        _mutable_run_q(),  # run-1 = run-stale, status=RUNNING
        "qa_items":       _qa_items_q(),
        "qa_run_targets": _targets_q(),
        "qa_run_results": _ResultsQ(current=[], history=hist),
    })
    # New FAIL result for run-1 (stale), but run-latest (PASS, 2099) is still latest
    data = _call(sb, results=[_new_result("FAIL")])
    assert data["notifications"] == []


# ─────────────────────────────────────────────────────────────────────────────
# QC-14: exact callback replay → Slack 0
# ─────────────────────────────────────────────────────────────────────────────

def test_QC14_exact_replay_no_notify():
    existing = {
        "id": "res-1", "run_id": "run-1", "qa_item_id": "item-1",
        "result_status": "FAIL", "attempt": 1,
        "duration_ms": None, "http_status": None, "error_code": None,
        "error_summary": None, "artifact_ref": None,
        "started_at": None, "finished_at": None,
        "checked_at": "2026-10-01T00:00:00+09:00", "created_at": "2026-10-01T00:00:00+09:00",
    }
    sb = _Supabase({
        "qa_runs":        _mutable_run_q(),
        "qa_items":       _qa_items_q(),
        "qa_run_targets": _targets_q(),
        "qa_run_results": _ResultsQ(current=[existing], history=[]),
    })
    # Same payload → skipped
    data = _call(sb, results=[_new_result("FAIL")])
    assert data["skipped"] == 1
    assert data["notifications"] == []


# ─────────────────────────────────────────────────────────────────────────────
# QR-01: QUEUED → ERROR → QA_RUN_ERROR 1
# ─────────────────────────────────────────────────────────────────────────────

def test_QR01_queued_to_error_run_notification():
    sb = _Supabase({
        "qa_runs":        _mutable_run_q("QUEUED"),
        "qa_items":       _Q(rows=[]),
        "qa_run_targets": _Q(rows=[]),
        "qa_run_results": _ResultsQ(),
    })
    data = _call(sb, new_status="ERROR")
    assert data["run_notification"] is not None
    assert data["run_notification"]["event_type"] == "QA_RUN_ERROR"


# ─────────────────────────────────────────────────────────────────────────────
# QR-02: RUNNING → ERROR → QA_RUN_ERROR 1
# ─────────────────────────────────────────────────────────────────────────────

def test_QR02_running_to_error_run_notification():
    sb = _Supabase({
        "qa_runs":        _mutable_run_q("RUNNING"),
        "qa_items":       _Q(rows=[]),
        "qa_run_targets": _Q(rows=[]),
        "qa_run_results": _ResultsQ(),
    })
    data = _call(sb, new_status="ERROR")
    assert data["run_notification"] is not None
    assert data["run_notification"]["event_type"] == "QA_RUN_ERROR"


# ─────────────────────────────────────────────────────────────────────────────
# QR-03: ERROR exact replay → QA_RUN_ERROR 0
# ─────────────────────────────────────────────────────────────────────────────

def test_QR03_error_exact_replay_no_notify():
    class _EQ(_Q):
        def update(self, *a, **k): return _Q(rows=[_run_row("ERROR")])

    sb = _Supabase({
        "qa_runs":        _EQ(rows=[_run_row("ERROR")]),
        "qa_items":       _Q(rows=[]),
        "qa_run_targets": _Q(rows=[]),
        "qa_run_results": _ResultsQ(),
    })
    data = _call(sb, new_status="ERROR")
    assert data["run_notification"] is None


# ─────────────────────────────────────────────────────────────────────────────
# QR-04: CANCELED → Slack 0
# ─────────────────────────────────────────────────────────────────────────────

def test_QR04_canceled_no_notify():
    sb = _Supabase({
        "qa_runs":        _mutable_run_q("RUNNING"),
        "qa_items":       _Q(rows=[]),
        "qa_run_targets": _Q(rows=[]),
        "qa_run_results": _ResultsQ(),
    })
    data = _call(sb, new_status="CANCELED")
    assert data["run_notification"] is None
    assert data["notifications"] == []


# ─────────────────────────────────────────────────────────────────────────────
# QS-01: QA_FAIL_DETECTED HIGH → alert channel
# ─────────────────────────────────────────────────────────────────────────────

def test_QS01_fail_detected_routes_qa():
    assert _resolve_channel("QA_FAIL_DETECTED", "HIGH") == CHANNEL_QA


# ─────────────────────────────────────────────────────────────────────────────
# QS-02: QA_BLOCKED_DETECTED HIGH → alert channel
# ─────────────────────────────────────────────────────────────────────────────

def test_QS02_blocked_detected_routes_qa():
    assert _resolve_channel("QA_BLOCKED_DETECTED", "HIGH") == CHANNEL_QA


# ─────────────────────────────────────────────────────────────────────────────
# QS-03: QA_FLAKY_DETECTED WARNING → ops channel
# ─────────────────────────────────────────────────────────────────────────────

def test_QS03_flaky_detected_routes_qa():
    assert _resolve_channel("QA_FLAKY_DETECTED", "WARNING") == CHANNEL_QA


# ─────────────────────────────────────────────────────────────────────────────
# QS-04: QA_RECOVERED INFO → ops channel
# ─────────────────────────────────────────────────────────────────────────────

def test_QS04_recovered_routes_qa():
    assert _resolve_channel("QA_RECOVERED", "INFO") == CHANNEL_QA


# ─────────────────────────────────────────────────────────────────────────────
# QS-05: QA_RUN_ERROR HIGH → alert channel
# ─────────────────────────────────────────────────────────────────────────────

def test_QS05_run_error_routes_qa():
    assert _resolve_channel("QA_RUN_ERROR", "HIGH") == CHANNEL_QA


# ─────────────────────────────────────────────────────────────────────────────
# QS-06: QA events admin button → /qa/dashboard (Phase 2-D Admin QA Console)
# ─────────────────────────────────────────────────────────────────────────────

def test_QS06_admin_button_path():
    for evt in ("QA_FAIL_DETECTED", "QA_BLOCKED_DETECTED", "QA_FLAKY_DETECTED",
                "QA_RECOVERED", "QA_RUN_ERROR"):
        assert EVENT_TYPE_ADMIN_PATH.get(evt) == "/qa/dashboard", f"{evt} missing"


# ─────────────────────────────────────────────────────────────────────────────
# QS-07: QA events → EVENT_TYPE_CHANNEL에 CHANNEL_QA로 등록됨
# ─────────────────────────────────────────────────────────────────────────────

def test_QS07_qa_events_in_event_type_channel():
    qa_events = {"QA_FAIL_DETECTED", "QA_BLOCKED_DETECTED",
                 "QA_FLAKY_DETECTED", "QA_RECOVERED", "QA_RUN_ERROR"}
    for evt in qa_events:
        assert evt in EVENT_TYPE_CHANNEL, f"{evt} must be in EVENT_TYPE_CHANNEL"
        assert EVENT_TYPE_CHANNEL[evt] == CHANNEL_QA, f"{evt} must map to CHANNEL_QA"


# ─────────────────────────────────────────────────────────────────────────────
# QS-08: QA_FAIL_DETECTED blocks → actual payload contains admin button
# ─────────────────────────────────────────────────────────────────────────────

def test_QS08_qa_admin_button_in_payload(monkeypatch):
    import asyncio
    captured: dict = {}

    class _FakeResp:
        status_code = 200
        def json(self): return {"ok": True}

    class _FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def post(self, url, *, headers, json):
            captured["payload"] = json
            return _FakeResp()

    monkeypatch.setattr("services.slack_dispatcher.httpx.AsyncClient", lambda **k: _FakeClient())
    monkeypatch.setenv("SLACK_BOT_TOKEN1", "xoxb-test")
    monkeypatch.setenv("SLACK_CH_QA", "C_QA")
    monkeypatch.setenv("SLACK_WEBHOOK_ENABLED", "true")

    from services.slack_dispatcher import send_slack
    from services.qa_notify_svc import build_qa_slack_payload

    for evt in ("QA_FAIL_DETECTED", "QA_FLAKY_DETECTED"):
        captured.clear()
        notif = {
            "event_type": evt, "qa_item_id": "item-1",
            "scenario_id": "P0-001", "site_code": "WWW", "name": "Login",
            "previous_status": "PASS", "new_status": "FAIL",
            "run_id": "run-1", "trigger_type": "MANUAL",
            "github_run_id": None, "head_sha": None,
            "error_summary": None, "duration_ms": None,
        }
        payload = build_qa_slack_payload(notif)
        asyncio.run(send_slack(**payload))

        blocks = captured["payload"]["blocks"]
        action_blocks = [b for b in blocks if b.get("type") == "actions"]
        assert len(action_blocks) == 1, f"{evt}: actions block must exist"
        btn = action_blocks[0]["elements"][0]
        assert btn["url"].endswith("/qa/dashboard"), f"{evt}: wrong URL"
        assert btn["text"]["text"] == "어드민에서 보기", f"{evt}: wrong button text"


# ─────────────────────────────────────────────────────────────────────────────
# QS-09: INQUIRY_CREATED blocks (already has actions) → no duplicate button
# ─────────────────────────────────────────────────────────────────────────────

def test_QS09_inquiry_blocks_no_button_duplicate(monkeypatch):
    import asyncio
    captured: dict = {}

    class _FakeResp:
        status_code = 200
        def json(self): return {"ok": True}

    class _FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def post(self, url, *, headers, json):
            captured["payload"] = json
            return _FakeResp()

    monkeypatch.setattr("services.slack_dispatcher.httpx.AsyncClient", lambda **k: _FakeClient())
    monkeypatch.setenv("SLACK_BOT_TOKEN1", "xoxb-test")
    monkeypatch.setenv("SLACK_CH_INQUIRY", "C_INQUIRY")
    monkeypatch.setenv("SLACK_WEBHOOK_ENABLED", "true")

    from services.slack_dispatcher import send_slack

    existing_blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": "inquiry text"}},
        {"type": "actions", "elements": [{
            "type": "button",
            "text": {"type": "plain_text", "text": "바로가기"},
            "url": "https://admin.taieng.co.kr/inquiry-list",
        }]},
    ]
    asyncio.run(send_slack(
        event_type="INQUIRY_CREATED", severity="HIGH",
        title="New Inquiry", blocks=existing_blocks,
    ))

    blocks = captured["payload"]["blocks"]
    action_blocks = [b for b in blocks if b.get("type") == "actions"]
    assert len(action_blocks) == 1, "must not duplicate actions block"


# ─────────────────────────────────────────────────────────────────────────────
# QF-01: Slack success → callback 200, sent=1
# ─────────────────────────────────────────────────────────────────────────────

def test_QF01_slack_success_callback_200(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers.internal_qa import router

    monkeypatch.setenv("INTERNAL_API_SECRET", "correct")
    fake_data = {
        "run_id": "run-1", "inserted": 1, "skipped": 0,
        "notifications": [
            {"event_type": "QA_FAIL_DETECTED", "qa_item_id": "item-1",
             "scenario_id": "P0-WWW-001", "site_code": "WWW", "name": "Login",
             "previous_status": "PASS", "new_status": "FAIL",
             "run_id": "run-1", "trigger_type": "MANUAL",
             "github_run_id": None, "head_sha": None,
             "error_summary": None, "duration_ms": None}
        ],
        "run_notification": None,
    }

    async def _fake_send(**k): return True

    monkeypatch.setattr("routers.internal_qa.svc.apply_results", lambda *a, **k: fake_data)
    monkeypatch.setattr("routers.internal_qa.get_supabase", lambda: None)
    monkeypatch.setattr("routers.internal_qa.send_slack", _fake_send)

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/internal/qa/runs/run-1/results",
        headers={"X-Internal-Secret": "correct"},
        json={"results": []},
    )
    assert resp.status_code == 200
    assert resp.json()["slack"]["sent"] == 1
    assert resp.json()["slack"]["failed"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# QF-02: Slack returns False → callback 200, DB result 유지, failed=1
# ─────────────────────────────────────────────────────────────────────────────

def test_QF02_slack_false_callback_200(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers.internal_qa import router

    monkeypatch.setenv("INTERNAL_API_SECRET", "correct")
    fake_data = {
        "run_id": "run-1", "inserted": 1, "skipped": 0,
        "notifications": [
            {"event_type": "QA_FAIL_DETECTED", "qa_item_id": "item-1",
             "scenario_id": None, "site_code": None, "name": None,
             "previous_status": "PASS", "new_status": "FAIL",
             "run_id": "run-1", "trigger_type": "MANUAL",
             "github_run_id": None, "head_sha": None,
             "error_summary": None, "duration_ms": None}
        ],
        "run_notification": None,
    }

    async def _fake_send(**k): return False

    monkeypatch.setattr("routers.internal_qa.svc.apply_results", lambda *a, **k: fake_data)
    monkeypatch.setattr("routers.internal_qa.get_supabase", lambda: None)
    monkeypatch.setattr("routers.internal_qa.send_slack", _fake_send)

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/internal/qa/runs/run-1/results",
        headers={"X-Internal-Secret": "correct"},
        json={"results": []},
    )
    assert resp.status_code == 200
    assert resp.json()["slack"]["failed"] == 1
    assert resp.json()["data"]["inserted"] == 1  # DB result 유지


# ─────────────────────────────────────────────────────────────────────────────
# QF-03: Slack exception → callback 200, DB result 유지
# ─────────────────────────────────────────────────────────────────────────────

def test_QF03_slack_exception_callback_200(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers.internal_qa import router

    monkeypatch.setenv("INTERNAL_API_SECRET", "correct")
    fake_data = {
        "run_id": "run-1", "inserted": 1, "skipped": 0,
        "notifications": [
            {"event_type": "QA_FAIL_DETECTED", "qa_item_id": "item-1",
             "scenario_id": None, "site_code": None, "name": None,
             "previous_status": "PASS", "new_status": "FAIL",
             "run_id": "run-1", "trigger_type": "MANUAL",
             "github_run_id": None, "head_sha": None,
             "error_summary": None, "duration_ms": None}
        ],
        "run_notification": None,
    }

    async def _fake_send(**k): raise RuntimeError("network error")

    monkeypatch.setattr("routers.internal_qa.svc.apply_results", lambda *a, **k: fake_data)
    monkeypatch.setattr("routers.internal_qa.get_supabase", lambda: None)
    monkeypatch.setattr("routers.internal_qa.send_slack", _fake_send)

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/internal/qa/runs/run-1/results",
        headers={"X-Internal-Secret": "correct"},
        json={"results": []},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["inserted"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# QF-04: source — internal_qa uses await send_slack, no fire-and-forget
# ─────────────────────────────────────────────────────────────────────────────

def test_QF04_no_fire_and_forget():
    src = pathlib.Path("routers/internal_qa.py").read_text()
    assert "ensure_future" not in src
    assert "create_task" not in src
    assert "await send_slack" in src


# ─────────────────────────────────────────────────────────────────────────────
# QF-05: qa_notify_svc is formatter-only (no Slack API calls)
# ─────────────────────────────────────────────────────────────────────────────

def test_QF05_notify_formatter_only():
    src = pathlib.Path("services/qa_notify_svc.py").read_text()
    assert "httpx" not in src
    assert "SLACK_BOT_TOKEN" not in src
    assert "SLACK_CH_" not in src
    assert "chat.postMessage" not in src
    assert "slack.com/api" not in src


# ─────────────────────────────────────────────────────────────────────────────
# Regression: legacy Slack Event Hub blocks contract (PR1/2/3 회귀 방지)
# ─────────────────────────────────────────────────────────────────────────────

def _make_slack_interceptor(monkeypatch, channel_env_key: str, channel_env_val: str):
    """Returns captured dict; installs httpx mock + required env."""
    import services.slack_dispatcher as sd
    captured: dict = {}

    class _FakeResp:
        status_code = 200
        def json(self): return {"ok": True}

    class _FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def post(self, url, *, headers, json):
            captured["payload"] = json
            return _FakeResp()

    monkeypatch.setattr("services.slack_dispatcher.httpx.AsyncClient", lambda **k: _FakeClient())
    monkeypatch.setenv("SLACK_BOT_TOKEN1", "xoxb-test")
    monkeypatch.setenv(channel_env_key, channel_env_val)
    monkeypatch.setenv("SLACK_WEBHOOK_ENABLED", "true")
    return captured


def test_R1_inquiry_section_blocks_unchanged(monkeypatch):
    """INQUIRY_CREATED + section-only blocks → payload.blocks unchanged (no button inject)."""
    captured = _make_slack_interceptor(monkeypatch, "SLACK_CH_INQUIRY", "C_INQUIRY")
    from services.slack_dispatcher import send_slack
    input_blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": "inquiry"}}]
    asyncio.run(send_slack(
        event_type="INQUIRY_CREATED", severity="INFO",
        title="New Inquiry", blocks=input_blocks,
    ))
    assert captured["payload"]["blocks"] == input_blocks


def test_R2_inquiry_existing_actions_no_duplicate(monkeypatch):
    """INQUIRY_CREATED + blocks with actions → exactly 1 actions block (no duplicate)."""
    captured = _make_slack_interceptor(monkeypatch, "SLACK_CH_INQUIRY", "C_INQUIRY")
    from services.slack_dispatcher import send_slack
    input_blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": "text"}},
        {"type": "actions", "elements": [
            {"type": "button", "text": {"type": "plain_text", "text": "바로가기"},
             "url": "https://admin.taieng.co.kr/inquiry-list"},
        ]},
    ]
    asyncio.run(send_slack(
        event_type="INQUIRY_CREATED", severity="INFO",
        title="New Inquiry", blocks=input_blocks,
    ))
    action_blocks = [b for b in captured["payload"]["blocks"] if b.get("type") == "actions"]
    assert len(action_blocks) == 1


def test_R3_qa_fail_section_blocks_gets_admin_button(monkeypatch):
    """QA_FAIL_DETECTED + section-only blocks → payload contains admin actions button."""
    captured = _make_slack_interceptor(monkeypatch, "SLACK_CH_QA", "C_QA")
    from services.slack_dispatcher import send_slack
    from services.qa_notify_svc import build_qa_slack_payload
    notif = {
        "event_type": "QA_FAIL_DETECTED", "qa_item_id": "item-1",
        "scenario_id": "P0-001", "site_code": "WWW", "name": "Login",
        "previous_status": "PASS", "new_status": "FAIL",
        "run_id": "run-1", "trigger_type": "MANUAL",
        "github_run_id": None, "head_sha": None,
        "error_summary": None, "duration_ms": None,
    }
    payload = build_qa_slack_payload(notif)
    asyncio.run(send_slack(**payload))
    action_blocks = [b for b in captured["payload"]["blocks"] if b.get("type") == "actions"]
    assert len(action_blocks) == 1
    assert action_blocks[0]["elements"][0]["url"].endswith("/qa/dashboard")


def test_R4_qa_flaky_section_blocks_gets_admin_button(monkeypatch):
    """QA_FLAKY_DETECTED + section-only blocks → payload contains admin actions button."""
    captured = _make_slack_interceptor(monkeypatch, "SLACK_CH_QA", "C_QA")
    from services.slack_dispatcher import send_slack
    from services.qa_notify_svc import build_qa_slack_payload
    notif = {
        "event_type": "QA_FLAKY_DETECTED", "qa_item_id": "item-1",
        "scenario_id": "P0-002", "site_code": "WWW", "name": "Search",
        "previous_status": "PASS", "new_status": "FLAKY",
        "run_id": "run-1", "trigger_type": "MANUAL",
        "github_run_id": None, "head_sha": None,
        "error_summary": None, "duration_ms": None,
    }
    payload = build_qa_slack_payload(notif)
    asyncio.run(send_slack(**payload))
    action_blocks = [b for b in captured["payload"]["blocks"] if b.get("type") == "actions"]
    assert len(action_blocks) == 1
    assert action_blocks[0]["elements"][0]["url"].endswith("/qa/dashboard")


# ─────────────────────────────────────────────────────────────────────────────
# QS-10: SLACK_CH_QA env var → _get_channel_id("qa") 해석
# ─────────────────────────────────────────────────────────────────────────────

def test_QS10_slack_ch_qa_env_resolution(monkeypatch):
    monkeypatch.setenv("SLACK_CH_QA", "C0C6EV30CBG")
    assert _get_channel_id(CHANNEL_QA) == "C0C6EV30CBG"


def test_QS10b_slack_ch_qa_env_missing(monkeypatch):
    monkeypatch.delenv("SLACK_CH_QA", raising=False)
    assert _get_channel_id(CHANNEL_QA) is None


# ─────────────────────────────────────────────────────────────────────────────
# QS-11: 5종 QA 이벤트 전부 CHANNEL_QA로 라우팅 (severity 무관)
# ─────────────────────────────────────────────────────────────────────────────

def test_QS11_all_qa_events_route_to_channel_qa():
    qa_events = [
        ("QA_FAIL_DETECTED",    "CRITICAL"),
        ("QA_FAIL_DETECTED",    "HIGH"),
        ("QA_BLOCKED_DETECTED", "HIGH"),
        ("QA_FLAKY_DETECTED",   "WARNING"),
        ("QA_RECOVERED",        "INFO"),
        ("QA_RUN_ERROR",        "HIGH"),
    ]
    for evt, sev in qa_events:
        result = _resolve_channel(evt, sev)
        assert result == CHANNEL_QA, f"{evt}/{sev} → {result!r} (expected CHANNEL_QA)"


# ─────────────────────────────────────────────────────────────────────────────
# QN formatter contract (WO-QA-SLACK-DIAGNOSTIC-CONTEXT-001)
# ─────────────────────────────────────────────────────────────────────────────

def _notif(**kwargs):
    base = {
        "event_type":       "QA_FAIL_DETECTED",
        "previous_status":  "PASS",
        "new_status":       "FAIL",
    }
    base.update(kwargs)
    return base


def test_QN01_payload_keys():
    payload = notify.build_qa_slack_payload(_notif())
    assert payload["event_type"] == "QA_FAIL_DETECTED"
    assert payload["severity"]   == "HIGH"
    assert payload["title"]      == "QA 이상 감지"
    assert payload["detail"]     == ""
    assert isinstance(payload["blocks"], list)
    assert payload["blocks"][0]["type"] == "section"
    assert payload["blocks"][0]["text"]["type"] == "mrkdwn"


def test_QN02_severity_emoji_title():
    cases = [
        ("QA_FAIL_DETECTED",    "🔴", "QA 이상 감지"),
        ("QA_BLOCKED_DETECTED", "🔴", "QA BLOCKED 감지"),
        ("QA_FLAKY_DETECTED",   "🟡", "QA FLAKY 감지"),
        ("QA_RECOVERED",        "✅", "QA 정상 복구"),
        ("QA_RUN_ERROR",        "🔴", "QA 실행 시스템 오류"),
    ]
    for event_type, emoji, title in cases:
        payload = notify.build_qa_slack_payload({
            "event_type": event_type,
            "previous_status": "PASS", "new_status": "FAIL",
        })
        text = payload["blocks"][0]["text"]["text"]
        assert emoji in text,  f"{event_type}: missing emoji {emoji}"
        assert title in text,  f"{event_type}: missing title {title}"


def test_QN03_location_section():
    payload = notify.build_qa_slack_payload(_notif(
        service_code="WWW",
        area_code="AUTH",
        site_code="prod-kr-1",
    ))
    text = payload["blocks"][0]["text"]["text"]
    assert "위치" in text
    assert "웹사이트" in text
    assert "인증" in text
    assert "실행 Host" in text
    assert "prod-kr-1" in text


def test_QN04_test_section():
    payload = notify.build_qa_slack_payload(_notif(
        scenario_id="P0-WWW-001",
        name="로그인 플로우",
        qa_type="E2E",
    ))
    text = payload["blocks"][0]["text"]["text"]
    assert "QA ID" in text
    assert "P0-WWW-001" in text
    assert "테스트" in text
    assert "로그인 플로우" in text
    assert "종류" in text
    assert "전체 흐름" in text


def test_QN05_description_expected():
    payload = notify.build_qa_slack_payload(_notif(
        description="로그인 API 응답 검증",
        expected_summary="HTTP 200 + JWT 반환",
    ))
    text = payload["blocks"][0]["text"]["text"]
    assert "검증 대상" in text
    assert "로그인 API 응답 검증" in text
    assert "기대 결과" in text
    assert "HTTP 200 + JWT 반환" in text


def test_QN06_error_section_for_fail():
    payload = notify.build_qa_slack_payload(_notif(
        error_summary="locator '.btn-login' not found",
        http_status=None,
        error_code=None,
    ))
    text = payload["blocks"][0]["text"]["text"]
    assert "실제 오류" in text
    assert "locator '.btn-login' not found" in text


def test_QN07_no_error_section_for_recovered():
    payload = notify.build_qa_slack_payload({
        "event_type":      "QA_RECOVERED",
        "previous_status": "FAIL",
        "new_status":      "PASS",
        "error_summary":   "should be ignored",
    })
    text = payload["blocks"][0]["text"]["text"]
    assert "실제 오류" not in text


# ─────────────────────────────────────────────────────────────────────────────
# QN-08: http_status-only → error section rendered (PATCH1)
# ─────────────────────────────────────────────────────────────────────────────

def test_QN08_http_only_shows_error_section():
    payload = notify.build_qa_slack_payload(_notif(
        error_summary=None,
        http_status=500,
        error_code="INTERNAL_SERVER_ERROR",
    ))
    text = payload["blocks"][0]["text"]["text"]
    assert "실제 오류" in text, "error section must appear when http_status is set"
    assert "500" in text
    assert "INTERNAL_SERVER_ERROR" in text


# ─────────────────────────────────────────────────────────────────────────────
# QN-09: FLAKY error preservation via apply_results (PATCH1)
# attempt 1 = FAIL (error_summary="locator timeout"), attempt 2 = PASS
# → notification.error_summary == "locator timeout"
# ─────────────────────────────────────────────────────────────────────────────

def test_QN09_flaky_preserves_fail_error_summary():
    hist = [_hist_row(run_id="run-prev", status="PASS", checked_at="2026-10-01T00:00:00+09:00")]
    sb = _Supabase({
        "qa_runs":        _mutable_run_q(),
        "qa_items":       _qa_items_q(),
        "qa_run_targets": _targets_q(),
        "qa_run_results": _ResultsQ(current=[], history=hist),
    })
    results = [
        {"scenario_id": "P0-WWW-001", "result_status": "FAIL", "attempt": 1,
         "error_summary": "locator timeout"},
        {"scenario_id": "P0-WWW-001", "result_status": "PASS", "attempt": 2},
    ]
    data = _call(sb, results=results)
    notifs = data["notifications"]
    assert len(notifs) == 1
    assert notifs[0]["event_type"] == "QA_FLAKY_DETECTED"
    assert notifs[0]["error_summary"] == "locator timeout", (
        "FLAKY must carry error_summary from the FAIL attempt, not from the final PASS"
    )
