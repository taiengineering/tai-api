"""WO-QA-CONTROL-PHASE2B-001 — Internal QA Result Callback 계약 테스트.

Production QA table write = 0 (mock 전용).

커버리지:
  IQ-01  apply_results — 신규 result INSERT
  IQ-02  apply_results — 동일 payload 재전송 → skipped (멱등성)
  IQ-03  apply_results — 다른 result_status 동일 key → 409 conflict
  IQ-04  apply_results — run not found → 404
  IQ-05  apply_results — QUEUED → RUNNING 전이 (started_at 기록)
  IQ-06  apply_results — RUNNING → COMPLETED 전이 (finished_at 기록)
  IQ-07  apply_results — final status 재진입 → 409
  IQ-08  apply_results — invalid transition QUEUED → COMPLETED → 422
  IQ-09  apply_results — github_run_id / attempt 업데이트
  IQ-10  internal auth — 잘못된 secret → 403 (router 레벨)
"""
from __future__ import annotations

import os
from typing import Optional
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import services.qa_control_svc as svc


# ─────────────────────────────────────────────────────────────────────────────
# Mock helpers (동일 패턴)
# ─────────────────────────────────────────────────────────────────────────────

class _Q:
    def __init__(self, rows=None, count=None):
        self._rows = rows or []
        self._count = count if count is not None else len(self._rows)
        self.last_insert = None
        self.last_update = None

    def select(self, *a, **k): return self
    def eq(self, *a, **k):     return self
    def in_(self, *a, **k):    return self
    def order(self, *a, **k):  return self
    def limit(self, *a, **k):  return self

    def insert(self, rows, **k):
        self.last_insert = rows
        return self

    def update(self, data, **k):
        self.last_update = data
        return self

    def execute(self):
        return type("R", (), {"data": self._rows, "count": self._count})()


def _run_row(status="QUEUED", started=None, finished=None):
    return {
        "id": "run-1", "trigger_type": "MANUAL", "run_status": status,
        "github_run_id": None, "github_run_attempt": None,
        "head_sha": None, "branch_name": None,
        "requested_by": None, "requested_at": "2026-10-01T00:00:00+09:00",
        "started_at": started, "finished_at": finished,
        "error_code": None, "error_summary": None,
        "created_at": "2026-10-01T00:00:00+09:00",
        "updated_at": "2026-10-01T00:00:00+09:00",
    }


def _result_row(item_id="item-1", status="PASS", attempt=1):
    return {
        "id": f"res-{item_id}-{attempt}", "run_id": "run-1",
        "qa_item_id": item_id, "result_status": status, "attempt": attempt,
        "duration_ms": None, "http_status": None,
        "error_code": None, "error_summary": None, "artifact_ref": None,
        "started_at": None, "finished_at": None,
        "checked_at": "2026-10-01T00:00:00+09:00",
        "created_at": "2026-10-01T00:00:00+09:00",
    }


class _Supabase:
    def __init__(self, table_map):
        self._map = table_map

    def table(self, name):
        return self._map.get(name, _Q())


# ─────────────────────────────────────────────────────────────────────────────
# IQ-01: 신규 result INSERT
# ─────────────────────────────────────────────────────────────────────────────

def test_IQ01_new_result_inserted():
    results_q = _Q(rows=[])  # no existing results
    runs_q = _Q(rows=[_run_row()])

    class _MutableRunQ(_Q):
        def update(self, *a, **k): return _Q(rows=[_run_row()])

    sb = _Supabase({
        "qa_runs":        _MutableRunQ(rows=[_run_row()]),
        "qa_run_results": results_q,
    })

    data = svc.apply_results(
        sb, "run-1",
        new_status=None, github_run_id=None, github_run_attempt=None,
        results=[{"qa_item_id": "item-1", "result_status": "PASS", "attempt": 1}],
    )
    assert data["inserted"] == 1
    assert data["skipped"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# IQ-02: 동일 payload 재전송 → skipped
# ─────────────────────────────────────────────────────────────────────────────

def test_IQ02_duplicate_same_payload_skipped():
    existing = _result_row(status="PASS", attempt=1)

    class _MutableRunQ(_Q):
        def update(self, *a, **k): return _Q(rows=[_run_row()])

    sb = _Supabase({
        "qa_runs":        _MutableRunQ(rows=[_run_row()]),
        "qa_run_results": _Q(rows=[existing]),
    })

    data = svc.apply_results(
        sb, "run-1",
        new_status=None, github_run_id=None, github_run_attempt=None,
        results=[{"qa_item_id": "item-1", "result_status": "PASS", "attempt": 1}],
    )
    assert data["inserted"] == 0
    assert data["skipped"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# IQ-03: 다른 result_status 동일 key → 409
# ─────────────────────────────────────────────────────────────────────────────

def test_IQ03_conflict_different_status_409():
    existing = _result_row(status="PASS", attempt=1)
    sb = _Supabase({
        "qa_runs":        _Q(rows=[_run_row()]),
        "qa_run_results": _Q(rows=[existing]),
    })

    with pytest.raises(HTTPException) as exc:
        svc.apply_results(
            sb, "run-1",
            new_status=None, github_run_id=None, github_run_attempt=None,
            results=[{"qa_item_id": "item-1", "result_status": "FAIL", "attempt": 1}],
        )
    assert exc.value.status_code == 409


# ─────────────────────────────────────────────────────────────────────────────
# IQ-04: run not found → 404
# ─────────────────────────────────────────────────────────────────────────────

def test_IQ04_run_not_found_404():
    sb = _Supabase({"qa_runs": _Q(rows=[])})
    with pytest.raises(HTTPException) as exc:
        svc.apply_results(sb, "run-none", None, None, None, [])
    assert exc.value.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# IQ-05: QUEUED → RUNNING — started_at 기록
# ─────────────────────────────────────────────────────────────────────────────

def test_IQ05_queued_to_running_sets_started_at():
    updated_data = {}

    class _TrackRunQ(_Q):
        def update(self, data, **k):
            updated_data.update(data)
            return _Q(rows=[_run_row(status="RUNNING")])

    sb = _Supabase({
        "qa_runs":        _TrackRunQ(rows=[_run_row(status="QUEUED")]),
        "qa_run_results": _Q(rows=[]),
    })

    svc.apply_results(sb, "run-1", new_status="RUNNING", github_run_id=None, github_run_attempt=None, results=[])
    assert updated_data.get("run_status") == "RUNNING"
    assert updated_data.get("started_at") is not None


# ─────────────────────────────────────────────────────────────────────────────
# IQ-06: RUNNING → COMPLETED — finished_at 기록
# ─────────────────────────────────────────────────────────────────────────────

def test_IQ06_running_to_completed_sets_finished_at():
    updated_data = {}

    class _TrackRunQ(_Q):
        def update(self, data, **k):
            updated_data.update(data)
            return _Q(rows=[_run_row(status="COMPLETED")])

    sb = _Supabase({
        "qa_runs":        _TrackRunQ(rows=[_run_row(status="RUNNING", started="2026-10-01T00:00:00+09:00")]),
        "qa_run_results": _Q(rows=[]),
    })

    svc.apply_results(sb, "run-1", new_status="COMPLETED", github_run_id=None, github_run_attempt=None, results=[])
    assert updated_data.get("run_status") == "COMPLETED"
    assert updated_data.get("finished_at") is not None


# ─────────────────────────────────────────────────────────────────────────────
# IQ-07: final status 재진입 → 409
# ─────────────────────────────────────────────────────────────────────────────

def test_IQ07_final_status_reentry_409():
    sb = _Supabase({
        "qa_runs":        _Q(rows=[_run_row(status="COMPLETED")]),
        "qa_run_results": _Q(rows=[]),
    })
    with pytest.raises(HTTPException) as exc:
        svc.apply_results(sb, "run-1", new_status="COMPLETED", github_run_id=None, github_run_attempt=None, results=[])
    assert exc.value.status_code == 409


# ─────────────────────────────────────────────────────────────────────────────
# IQ-08: invalid transition QUEUED → COMPLETED → 422
# ─────────────────────────────────────────────────────────────────────────────

def test_IQ08_invalid_transition_422():
    sb = _Supabase({
        "qa_runs":        _Q(rows=[_run_row(status="QUEUED")]),
        "qa_run_results": _Q(rows=[]),
    })
    with pytest.raises(HTTPException) as exc:
        svc.apply_results(sb, "run-1", new_status="COMPLETED", github_run_id=None, github_run_attempt=None, results=[])
    assert exc.value.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# IQ-09: github_run_id / attempt 업데이트
# ─────────────────────────────────────────────────────────────────────────────

def test_IQ09_github_identity_updated():
    updated_data = {}

    class _TrackRunQ(_Q):
        def update(self, data, **k):
            updated_data.update(data)
            return _Q(rows=[_run_row(status="RUNNING")])

    sb = _Supabase({
        "qa_runs":        _TrackRunQ(rows=[_run_row(status="QUEUED")]),
        "qa_run_results": _Q(rows=[]),
    })

    svc.apply_results(
        sb, "run-1",
        new_status="RUNNING",
        github_run_id=123456789,
        github_run_attempt=1,
        results=[],
    )
    assert updated_data.get("github_run_id") == 123456789
    assert updated_data.get("github_run_attempt") == 1


# ─────────────────────────────────────────────────────────────────────────────
# IQ-10: router level — invalid secret → 403
# ─────────────────────────────────────────────────────────────────────────────

def test_IQ10_router_invalid_secret_403(monkeypatch):
    from fastapi import FastAPI
    from routers.internal_qa import router
    from db.supabase_client import get_supabase

    app = FastAPI()
    app.include_router(router)

    monkeypatch.setenv("INTERNAL_API_SECRET", "correct-secret")

    def _fake_sb():
        return _Supabase({"qa_runs": _Q(rows=[_run_row()])})

    monkeypatch.setattr("db.supabase_client.get_supabase", _fake_sb)

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/internal/qa/runs/run-1/results",
        headers={"X-Internal-Secret": "wrong-secret"},
        json={"results": []},
    )
    assert resp.status_code == 403
