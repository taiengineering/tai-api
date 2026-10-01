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
    CHANNEL_ALERT, CHANNEL_OPS,
    EVENT_TYPE_ADMIN_PATH, EVENT_TYPE_CHANNEL,
    _resolve_channel,
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

def test_QS01_fail_detected_routes_alert():
    assert _resolve_channel("QA_FAIL_DETECTED", "HIGH") == CHANNEL_ALERT


# ─────────────────────────────────────────────────────────────────────────────
# QS-02: QA_BLOCKED_DETECTED HIGH → alert channel
# ─────────────────────────────────────────────────────────────────────────────

def test_QS02_blocked_detected_routes_alert():
    assert _resolve_channel("QA_BLOCKED_DETECTED", "HIGH") == CHANNEL_ALERT


# ─────────────────────────────────────────────────────────────────────────────
# QS-03: QA_FLAKY_DETECTED WARNING → ops channel
# ─────────────────────────────────────────────────────────────────────────────

def test_QS03_flaky_detected_routes_ops():
    assert _resolve_channel("QA_FLAKY_DETECTED", "WARNING") == CHANNEL_OPS


# ─────────────────────────────────────────────────────────────────────────────
# QS-04: QA_RECOVERED INFO → ops channel
# ─────────────────────────────────────────────────────────────────────────────

def test_QS04_recovered_routes_ops():
    assert _resolve_channel("QA_RECOVERED", "INFO") == CHANNEL_OPS


# ─────────────────────────────────────────────────────────────────────────────
# QS-05: QA_RUN_ERROR HIGH → alert channel
# ─────────────────────────────────────────────────────────────────────────────

def test_QS05_run_error_routes_alert():
    assert _resolve_channel("QA_RUN_ERROR", "HIGH") == CHANNEL_ALERT


# ─────────────────────────────────────────────────────────────────────────────
# QS-06: QA events admin button → /auto-qa-dashboard
# ─────────────────────────────────────────────────────────────────────────────

def test_QS06_admin_button_path():
    for evt in ("QA_FAIL_DETECTED", "QA_BLOCKED_DETECTED", "QA_FLAKY_DETECTED",
                "QA_RECOVERED", "QA_RUN_ERROR"):
        assert EVENT_TYPE_ADMIN_PATH.get(evt) == "/auto-qa-dashboard", f"{evt} missing"


# ─────────────────────────────────────────────────────────────────────────────
# QS-07: 신규 SLACK_CH_QA env 없음 — QA는 severity 라우팅 재사용
# ─────────────────────────────────────────────────────────────────────────────

def test_QS07_no_qa_channel_override():
    qa_events = {"QA_FAIL_DETECTED", "QA_BLOCKED_DETECTED",
                 "QA_FLAKY_DETECTED", "QA_RECOVERED", "QA_RUN_ERROR"}
    for evt in qa_events:
        assert evt not in EVENT_TYPE_CHANNEL, f"{evt} must not override channel"


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
