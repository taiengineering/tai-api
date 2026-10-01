"""WO-QA-CONTROL-PHASE2B-001 PATCH-1 — Internal QA Result Callback 계약 테스트.

Production QA table write = 0 (mock 전용).

커버리지:
  IQ-01  신규 result INSERT (scenario_id → qa_item_id resolve)
  IQ-02  동일 payload 재전송 → skipped (idempotent)
  IQ-03  다른 result_status 동일 key → 409 RESULT_CONFLICT
  IQ-04  duration_ms 다름 동일 key → 409 RESULT_CONFLICT (evidence 전체 비교)
  IQ-05  run not found → 404
  IQ-06  QUEUED→RUNNING — started_at 기록
  IQ-07  QUEUED→ERROR — 허용 (QUEUED→ERROR 추가)
  IQ-08  RUNNING→COMPLETED — finished_at 기록
  IQ-09  final+동일status replay → 200 (IQ-07과 다름: 이미 COMPLETED인 상태)
  IQ-10  final+다른status 전이 → 409
  IQ-11  invalid transition QUEUED→COMPLETED → 422
  IQ-12  GitHub identity 최초 binding
  IQ-13  GitHub identity 동일 replay 허용
  IQ-14  GitHub identity 다름 → 409 GITHUB_IDENTITY_MISMATCH
  IQ-15  github_run_id만 제공 (attempt 없음) → 422
  IQ-16  target 아닌 item → 409 RESULT_NOT_TARGETED
  IQ-17  scenario_id not found → 422
  IQ-18  final state + new result → 409
  IQ-19  run-level fields (head_sha/branch_name) 업데이트
  IQ-20  error_summary redaction
  IQ-21  artifact_ref signed URL → 400
  IQ-22  missing secret → 403 (router)
  IQ-23  wrong secret → 403 (router)
  IQ-24  correct secret → PASS (router)
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

import services.qa_control_svc as svc
from services.qa_control_svc import redact_error_summary


# ─────────────────────────────────────────────────────────────────────────────
# Mock helpers
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


def _result_row(item_id="item-1", status="PASS", attempt=1, duration_ms=None, error_summary=None):
    return {
        "id": f"res-{item_id}-{attempt}", "run_id": "run-1",
        "qa_item_id": item_id, "result_status": status, "attempt": attempt,
        "duration_ms": duration_ms, "http_status": None,
        "error_code": None, "error_summary": error_summary, "artifact_ref": None,
        "started_at": None, "finished_at": None,
        "checked_at": "2026-10-01T00:00:00+09:00",
        "created_at": "2026-10-01T00:00:00+09:00",
    }


class _Supabase:
    def __init__(self, table_map):
        self._map = table_map

    def table(self, name):
        return self._map.get(name, _Q())


def _call(
    sb,
    results=None,
    new_status=None,
    github_run_id=None,
    github_run_attempt=None,
    head_sha=None,
    branch_name=None,
    run_error_code=None,
    run_error_summary=None,
):
    return svc.apply_results(
        sb,
        run_id="run-1",
        new_status=new_status,
        github_run_id=github_run_id,
        github_run_attempt=github_run_attempt,
        head_sha=head_sha,
        branch_name=branch_name,
        run_started_at=None,
        run_finished_at=None,
        run_error_code=run_error_code,
        run_error_summary=run_error_summary,
        results=results or [],
    )


def _qa_items_q(scenario_id="P0-WWW-001", item_id="item-1"):
    return _Q(rows=[{"id": item_id, "scenario_id": scenario_id, "enabled": True}])


def _targets_q(item_id="item-1"):
    return _Q(rows=[{"qa_item_id": item_id}])


def _mutable_run_q(status="QUEUED", started=None, finished=None, gri=None, gra=None):
    class _MQ(_Q):
        def update(self, *a, **k): return _Q(rows=[_run_row(status)])

    return _MQ(rows=[_run_row(status, started, finished, gri, gra)])


# ─────────────────────────────────────────────────────────────────────────────
# IQ-01: 신규 result INSERT (scenario_id → qa_item_id)
# ─────────────────────────────────────────────────────────────────────────────

def test_IQ01_new_result_inserted():
    sb = _Supabase({
        "qa_runs":        _mutable_run_q(),
        "qa_items":       _qa_items_q(),
        "qa_run_targets": _targets_q(),
        "qa_run_results": _Q(rows=[]),
    })
    data = _call(sb, results=[{"scenario_id": "P0-WWW-001", "result_status": "PASS", "attempt": 1}])
    assert data["inserted"] == 1
    assert data["skipped"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# IQ-02: 동일 payload → skipped
# ─────────────────────────────────────────────────────────────────────────────

def test_IQ02_duplicate_same_payload_skipped():
    existing = _result_row(status="PASS", attempt=1)
    sb = _Supabase({
        "qa_runs":        _mutable_run_q(),
        "qa_items":       _qa_items_q(),
        "qa_run_targets": _targets_q(),
        "qa_run_results": _Q(rows=[existing]),
    })
    data = _call(sb, results=[{"scenario_id": "P0-WWW-001", "result_status": "PASS", "attempt": 1}])
    assert data["inserted"] == 0
    assert data["skipped"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# IQ-03: 다른 result_status 동일 key → 409
# ─────────────────────────────────────────────────────────────────────────────

def test_IQ03_conflict_different_status_409():
    existing = _result_row(status="PASS", attempt=1)
    sb = _Supabase({
        "qa_runs":        _Q(rows=[_run_row()]),
        "qa_items":       _qa_items_q(),
        "qa_run_targets": _targets_q(),
        "qa_run_results": _Q(rows=[existing]),
    })
    with pytest.raises(HTTPException) as exc:
        _call(sb, results=[{"scenario_id": "P0-WWW-001", "result_status": "FAIL", "attempt": 1}])
    assert exc.value.status_code == 409


# ─────────────────────────────────────────────────────────────────────────────
# IQ-04: duration_ms 다름 → 409 (evidence 전체 비교)
# ─────────────────────────────────────────────────────────────────────────────

def test_IQ04_conflict_different_duration_409():
    existing = _result_row(status="PASS", attempt=1, duration_ms=500)
    sb = _Supabase({
        "qa_runs":        _Q(rows=[_run_row()]),
        "qa_items":       _qa_items_q(),
        "qa_run_targets": _targets_q(),
        "qa_run_results": _Q(rows=[existing]),
    })
    with pytest.raises(HTTPException) as exc:
        _call(sb, results=[{"scenario_id": "P0-WWW-001", "result_status": "PASS", "attempt": 1, "duration_ms": 999}])
    assert exc.value.status_code == 409


# ─────────────────────────────────────────────────────────────────────────────
# IQ-05: run not found → 404
# ─────────────────────────────────────────────────────────────────────────────

def test_IQ05_run_not_found_404():
    sb = _Supabase({"qa_runs": _Q(rows=[])})
    with pytest.raises(HTTPException) as exc:
        _call(sb)
    assert exc.value.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# IQ-06: QUEUED→RUNNING — started_at 기록
# ─────────────────────────────────────────────────────────────────────────────

def test_IQ06_queued_to_running_started_at():
    captured = {}

    class _TQ(_Q):
        def update(self, data, **k):
            captured.update(data)
            return _Q(rows=[_run_row("RUNNING")])

    sb = _Supabase({
        "qa_runs":        _TQ(rows=[_run_row("QUEUED")]),
        "qa_items":       _qa_items_q(),
        "qa_run_targets": _targets_q(),
        "qa_run_results": _Q(rows=[]),
    })
    _call(sb, new_status="RUNNING")
    assert captured.get("run_status") == "RUNNING"
    assert captured.get("started_at") is not None


# ─────────────────────────────────────────────────────────────────────────────
# IQ-07: QUEUED→ERROR — 허용 (PATCH-1 추가)
# ─────────────────────────────────────────────────────────────────────────────

def test_IQ07_queued_to_error_allowed():
    captured = {}

    class _TQ(_Q):
        def update(self, data, **k):
            captured.update(data)
            return _Q(rows=[_run_row("ERROR")])

    sb = _Supabase({
        "qa_runs":        _TQ(rows=[_run_row("QUEUED")]),
        "qa_items":       _Q(rows=[]),
        "qa_run_targets": _Q(rows=[]),
        "qa_run_results": _Q(rows=[]),
    })
    data = _call(sb, new_status="ERROR")
    assert captured.get("run_status") == "ERROR"
    assert captured.get("finished_at") is not None


# ─────────────────────────────────────────────────────────────────────────────
# IQ-08: RUNNING→COMPLETED — finished_at 기록
# ─────────────────────────────────────────────────────────────────────────────

def test_IQ08_running_to_completed_finished_at():
    captured = {}

    class _TQ(_Q):
        def update(self, data, **k):
            captured.update(data)
            return _Q(rows=[_run_row("COMPLETED")])

    sb = _Supabase({
        "qa_runs":        _TQ(rows=[_run_row("RUNNING", started="2026-10-01T00:00:00+09:00")]),
        "qa_items":       _Q(rows=[]),
        "qa_run_targets": _Q(rows=[]),
        "qa_run_results": _Q(rows=[]),
    })
    _call(sb, new_status="COMPLETED")
    assert captured.get("run_status") == "COMPLETED"
    assert captured.get("finished_at") is not None


# ─────────────────────────────────────────────────────────────────────────────
# IQ-09: final + 동일 status replay → 200 idempotent
# ─────────────────────────────────────────────────────────────────────────────

def test_IQ09_final_same_status_idempotent():
    class _TQ(_Q):
        def update(self, *a, **k): return _Q(rows=[_run_row("COMPLETED")])

    sb = _Supabase({
        "qa_runs":        _TQ(rows=[_run_row("COMPLETED")]),
        "qa_items":       _Q(rows=[]),
        "qa_run_targets": _Q(rows=[]),
        "qa_run_results": _Q(rows=[]),
    })
    data = _call(sb, new_status="COMPLETED")
    assert data["inserted"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# IQ-10: final + 다른 status → 409
# ─────────────────────────────────────────────────────────────────────────────

def test_IQ10_final_different_status_409():
    sb = _Supabase({
        "qa_runs":        _Q(rows=[_run_row("COMPLETED")]),
        "qa_run_results": _Q(rows=[]),
    })
    with pytest.raises(HTTPException) as exc:
        _call(sb, new_status="RUNNING")
    assert exc.value.status_code == 409


# ─────────────────────────────────────────────────────────────────────────────
# IQ-11: invalid transition QUEUED→COMPLETED → 422
# ─────────────────────────────────────────────────────────────────────────────

def test_IQ11_invalid_transition_422():
    sb = _Supabase({
        "qa_runs":        _Q(rows=[_run_row("QUEUED")]),
        "qa_run_results": _Q(rows=[]),
    })
    with pytest.raises(HTTPException) as exc:
        _call(sb, new_status="COMPLETED")
    assert exc.value.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# IQ-12: GitHub identity 최초 binding
# ─────────────────────────────────────────────────────────────────────────────

def test_IQ12_github_identity_first_binding():
    captured = {}

    class _TQ(_Q):
        def update(self, data, **k):
            captured.update(data)
            return _Q(rows=[_run_row("RUNNING")])

    sb = _Supabase({
        "qa_runs":        _TQ(rows=[_run_row("QUEUED")]),
        "qa_items":       _Q(rows=[]),
        "qa_run_targets": _Q(rows=[]),
        "qa_run_results": _Q(rows=[]),
    })
    _call(sb, new_status="RUNNING", github_run_id=123, github_run_attempt=1)
    assert captured.get("github_run_id") == 123
    assert captured.get("github_run_attempt") == 1


# ─────────────────────────────────────────────────────────────────────────────
# IQ-13: GitHub identity 동일 replay → allowed
# ─────────────────────────────────────────────────────────────────────────────

def test_IQ13_github_identity_same_replay():
    class _TQ(_Q):
        def update(self, *a, **k): return _Q(rows=[_run_row("RUNNING", gri=123, gra=1)])

    sb = _Supabase({
        "qa_runs":        _TQ(rows=[_run_row("RUNNING", gri=123, gra=1)]),
        "qa_items":       _Q(rows=[]),
        "qa_run_targets": _Q(rows=[]),
        "qa_run_results": _Q(rows=[]),
    })
    data = _call(sb, github_run_id=123, github_run_attempt=1)
    assert data["run_id"] == "run-1"


# ─────────────────────────────────────────────────────────────────────────────
# IQ-14: GitHub identity 다름 → 409 GITHUB_IDENTITY_MISMATCH
# ─────────────────────────────────────────────────────────────────────────────

def test_IQ14_github_identity_mismatch_409():
    sb = _Supabase({
        "qa_runs":        _Q(rows=[_run_row("RUNNING", gri=123, gra=1)]),
        "qa_run_results": _Q(rows=[]),
    })
    with pytest.raises(HTTPException) as exc:
        _call(sb, github_run_id=999, github_run_attempt=1)
    assert exc.value.status_code == 409
    assert "GITHUB_IDENTITY_MISMATCH" in str(exc.value.detail)


# ─────────────────────────────────────────────────────────────────────────────
# IQ-15: github_run_id만 제공 (attempt 없음) → 422
# ─────────────────────────────────────────────────────────────────────────────

def test_IQ15_github_id_without_attempt_422():
    sb = _Supabase({"qa_runs": _Q(rows=[_run_row()])})
    with pytest.raises(HTTPException) as exc:
        _call(sb, github_run_id=123, github_run_attempt=None)
    assert exc.value.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# IQ-16: result_not_targeted → 409 RESULT_NOT_TARGETED
# ─────────────────────────────────────────────────────────────────────────────

def test_IQ16_result_not_targeted_409():
    sb = _Supabase({
        "qa_runs":        _Q(rows=[_run_row()]),
        "qa_items":       _qa_items_q(item_id="item-1"),
        "qa_run_targets": _Q(rows=[{"qa_item_id": "other-item"}]),  # item-1 not in targets
        "qa_run_results": _Q(rows=[]),
    })
    with pytest.raises(HTTPException) as exc:
        _call(sb, results=[{"scenario_id": "P0-WWW-001", "result_status": "PASS", "attempt": 1}])
    assert exc.value.status_code == 409
    assert "RESULT_NOT_TARGETED" in str(exc.value.detail)


# ─────────────────────────────────────────────────────────────────────────────
# IQ-17: scenario_id not found → 422
# ─────────────────────────────────────────────────────────────────────────────

def test_IQ17_scenario_id_not_found_422():
    sb = _Supabase({
        "qa_runs":  _Q(rows=[_run_row()]),
        "qa_items": _Q(rows=[]),  # empty
    })
    with pytest.raises(HTTPException) as exc:
        _call(sb, results=[{"scenario_id": "P0-NONEXISTENT-001", "result_status": "PASS", "attempt": 1}])
    assert exc.value.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# IQ-18: final state + new result INSERT → 409
# ─────────────────────────────────────────────────────────────────────────────

def test_IQ18_final_state_new_result_409():
    sb = _Supabase({
        "qa_runs":        _Q(rows=[_run_row("COMPLETED")]),
        "qa_items":       _qa_items_q(),
        "qa_run_targets": _targets_q(),
        "qa_run_results": _Q(rows=[]),  # No existing results
    })
    with pytest.raises(HTTPException) as exc:
        _call(sb, results=[{"scenario_id": "P0-WWW-001", "result_status": "PASS", "attempt": 1}])
    assert exc.value.status_code == 409


# ─────────────────────────────────────────────────────────────────────────────
# IQ-19: run-level fields 업데이트 (head_sha, branch_name)
# ─────────────────────────────────────────────────────────────────────────────

def test_IQ19_run_level_fields_updated():
    captured = {}

    class _TQ(_Q):
        def update(self, data, **k):
            captured.update(data)
            return _Q(rows=[_run_row("RUNNING")])

    sb = _Supabase({
        "qa_runs":        _TQ(rows=[_run_row("QUEUED")]),
        "qa_items":       _Q(rows=[]),
        "qa_run_targets": _Q(rows=[]),
        "qa_run_results": _Q(rows=[]),
    })
    _call(sb, new_status="RUNNING", head_sha="abc123", branch_name="main")
    assert captured.get("head_sha") == "abc123"
    assert captured.get("branch_name") == "main"


# ─────────────────────────────────────────────────────────────────────────────
# IQ-20: error_summary redaction
# ─────────────────────────────────────────────────────────────────────────────

def test_IQ20_error_summary_redaction():
    text = "Error: Authorization: Bearer eyJhbGc.secret leaked"
    result = redact_error_summary(text)
    assert "eyJhbGc" not in result
    assert "[REDACTED]" in result


def test_IQ20b_error_summary_truncation():
    long_text = "x" * 2000
    assert len(redact_error_summary(long_text)) == 1000


# ─────────────────────────────────────────────────────────────────────────────
# IQ-21: artifact_ref signed URL → 400
# ─────────────────────────────────────────────────────────────────────────────

def test_IQ21_artifact_ref_signed_url_400():
    sb = _Supabase({
        "qa_runs":        _Q(rows=[_run_row()]),
        "qa_items":       _qa_items_q(),
        "qa_run_targets": _targets_q(),
        "qa_run_results": _Q(rows=[]),
    })
    with pytest.raises(HTTPException) as exc:
        _call(sb, results=[{
            "scenario_id": "P0-WWW-001",
            "result_status": "PASS",
            "attempt": 1,
            "artifact_ref": "https://s3.example.com/path?X-Amz-Signature=abc123",
        }])
    assert exc.value.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# IQ-22: missing secret → 403 (router)
# ─────────────────────────────────────────────────────────────────────────────

def test_IQ22_missing_secret_403(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers.internal_qa import router

    monkeypatch.setenv("INTERNAL_API_SECRET", "correct")

    app = FastAPI()
    app.include_router(router)

    def _fake_sb():
        return _Supabase({"qa_runs": _Q(rows=[_run_row()])})

    monkeypatch.setattr("routers.internal_qa.get_supabase", _fake_sb)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/internal/qa/runs/run-1/results", json={"results": []})
    assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# IQ-23: wrong secret → 403 (router)
# ─────────────────────────────────────────────────────────────────────────────

def test_IQ23_wrong_secret_403(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers.internal_qa import router

    monkeypatch.setenv("INTERNAL_API_SECRET", "correct")

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/internal/qa/runs/run-1/results",
        headers={"X-Internal-Secret": "wrong"},
        json={"results": []},
    )
    assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# IQ-24: correct secret → PASS (router)
# ─────────────────────────────────────────────────────────────────────────────

def test_IQ24_correct_secret_pass(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers.internal_qa import router

    monkeypatch.setenv("INTERNAL_API_SECRET", "correct")

    fake_data = {"run_id": "run-1", "inserted": 0, "skipped": 0}
    monkeypatch.setattr("routers.internal_qa.svc.apply_results", lambda *a, **k: fake_data)
    monkeypatch.setattr("routers.internal_qa.get_supabase", lambda: None)

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/internal/qa/runs/run-1/results",
        headers={"X-Internal-Secret": "correct"},
        json={"results": []},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["run_id"] == "run-1"
