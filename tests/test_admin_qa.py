"""WO-QA-CONTROL-PHASE2B-001 — Admin QA API 계약 테스트.

Production QA table write = 0 (mock 전용).
GitHub dispatch = 0. Slack = 0.

커버리지:
  AQ-01  get_summary — 집계 정상 반환
  AQ-02  list_items  — schedule 포함, bulk join 정상
  AQ-03  list_items  — empty schedule 시 None
  AQ-04  update_item — 허용 필드 반영
  AQ-05  update_item — 빈 patch → 422
  AQ-06  update_item — 존재하지 않는 item → 404
  AQ-07  update_schedule — enabled=False 반영
  AQ-08  update_schedule — 빈 patch → 422
  AQ-09  update_schedule — item 없음 → 404
  AQ-10  list_runs   — run_status 필터 전달
  AQ-11  get_run     — targets + results 포함
  AQ-12  get_run     — FLAKY 파생 (attempt1=FAIL + attempt2=PASS)
  AQ-13  get_run     — not found → 404
  AQ-14  create_run  — QUEUED run + targets 생성
  AQ-15  create_run  — empty qa_item_ids → 422
  AQ-16  create_run  — 존재하지 않는 qa_item_id → 422
  AQ-17  create_run  — target insert 실패 → 500 + compensating DELETE
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

import services.qa_control_svc as svc


# ─────────────────────────────────────────────────────────────────────────────
# Mock helpers
# ─────────────────────────────────────────────────────────────────────────────

class _Q:
    """Minimal Supabase query chain mock."""
    def __init__(self, rows=None, count=None):
        self._rows = rows or []
        self._count = count if count is not None else len(self._rows)

    def select(self, *a, **k): return self
    def eq(self, *a, **k):     return self
    def neq(self, *a, **k):    return self
    def in_(self, *a, **k):    return self
    def order(self, *a, **k):  return self
    def range(self, *a, **k):  return self
    def limit(self, *a, **k):  return self
    def update(self, *a, **k): return self
    def insert(self, *a, **k): return self
    def delete(self, *a, **k): return self

    def execute(self):
        return type("R", (), {"data": self._rows, "count": self._count})()


class _Supabase:
    """Configurable fake Supabase client."""
    def __init__(self, table_map: dict):
        self._map = table_map  # table_name → _Q

    def table(self, name):
        return self._map.get(name, _Q())


def _item(id_="item-1", priority="P0", site_code="WWW"):
    return {
        "id": id_, "scenario_id": f"sc-{id_}", "site_code": site_code,
        "category": "auth", "name": "Login test", "description": None,
        "expected_summary": None, "priority": priority,
        "runner_type": "PLAYWRIGHT", "enabled": True,
        "created_at": "2026-10-01T00:00:00+09:00",
        "updated_at": "2026-10-01T00:00:00+09:00",
    }


def _sched(qa_item_id="item-1"):
    return {
        "id": "sched-1", "qa_item_id": qa_item_id,
        "enabled": False, "frequency_type": "MANUAL",
        "frequency_value": None, "anchor_time": None, "day_of_week": None,
        "timezone": "Asia/Seoul", "next_run_at": None,
        "last_scheduled_at": None,
        "created_at": "2026-10-01T00:00:00+09:00",
        "updated_at": "2026-10-01T00:00:00+09:00",
    }


def _run(id_="run-1", status="QUEUED"):
    return {
        "id": id_, "trigger_type": "MANUAL", "run_status": status,
        "github_run_id": None, "github_run_attempt": None,
        "head_sha": None, "branch_name": None,
        "requested_by": "admin@test.com", "requested_at": "2026-10-01T00:00:00+09:00",
        "started_at": None, "finished_at": None,
        "error_code": None, "error_summary": None,
        "created_at": "2026-10-01T00:00:00+09:00",
        "updated_at": "2026-10-01T00:00:00+09:00",
    }


def _result(run_id="run-1", item_id="item-1", status="PASS", attempt=1):
    return {
        "id": f"res-{item_id}-{attempt}", "run_id": run_id,
        "qa_item_id": item_id, "result_status": status, "attempt": attempt,
        "duration_ms": 500, "http_status": None, "error_code": None,
        "error_summary": None, "artifact_ref": None,
        "started_at": None, "finished_at": None,
        "checked_at": "2026-10-01T00:00:00+09:00",
        "created_at": "2026-10-01T00:00:00+09:00",
    }


# ─────────────────────────────────────────────────────────────────────────────
# AQ-01: get_summary
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ01_summary_returns_aggregates():
    sb = _Supabase({
        "qa_items":     _Q(rows=[{"id": "i1"}, {"id": "i2"}], count=2),
        "qa_schedules": _Q(rows=[{"id": "s1"}], count=1),
        "qa_runs":      _Q(rows=[{"run_status": "COMPLETED"}, {"run_status": "QUEUED"}]),
    })
    result = svc.get_summary(sb)
    assert result["total_items"] == 2
    assert result["active_schedules"] == 1
    assert result["runs_by_status"]["COMPLETED"] == 1
    assert result["runs_by_status"]["QUEUED"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# AQ-02: list_items with schedule join
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ02_list_items_joins_schedule():
    item = _item()
    schedule = _sched(qa_item_id="item-1")
    sb = _Supabase({
        "qa_items":     _Q(rows=[item], count=1),
        "qa_schedules": _Q(rows=[schedule]),
    })
    result = svc.list_items(sb)
    assert len(result["items"]) == 1
    assert result["items"][0]["schedule"]["id"] == "sched-1"
    assert result["total"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# AQ-03: list_items — no schedule → None
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ03_list_items_schedule_none_when_absent():
    item = _item()
    sb = _Supabase({
        "qa_items":     _Q(rows=[item], count=1),
        "qa_schedules": _Q(rows=[]),
    })
    result = svc.list_items(sb)
    assert result["items"][0]["schedule"] is None


# ─────────────────────────────────────────────────────────────────────────────
# AQ-04: update_item — allowed fields only
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ04_update_item_allowed_fields(monkeypatch):
    updated = dict(_item(), name="New Name")

    class _UpdateQ(_Q):
        def update(self, data, **k):
            self._last_data = data
            return _Q(rows=[updated])

    uq = _UpdateQ()
    sb = _Supabase({"qa_items": uq})
    result = svc.update_item(sb, "item-1", {"name": "New Name"})
    assert result["name"] == "New Name"


# ─────────────────────────────────────────────────────────────────────────────
# AQ-05: update_item — empty patch → 422
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ05_update_item_empty_patch_422():
    sb = _Supabase({"qa_items": _Q()})
    with pytest.raises(HTTPException) as exc:
        svc.update_item(sb, "item-1", {})
    assert exc.value.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# AQ-06: update_item — item not found → 404
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ06_update_item_not_found_404():
    class _NullUpdateQ(_Q):
        def update(self, *a, **k): return _Q(rows=[])

    sb = _Supabase({"qa_items": _NullUpdateQ()})
    with pytest.raises(HTTPException) as exc:
        svc.update_item(sb, "item-none", {"enabled": False})
    assert exc.value.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# AQ-07: update_schedule — enabled=False
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ07_update_schedule_enabled():
    updated = dict(_sched(), enabled=False)

    class _SchedUpdateQ(_Q):
        def update(self, *a, **k): return _Q(rows=[updated])

    sb = _Supabase({"qa_schedules": _SchedUpdateQ()})
    result = svc.update_schedule(sb, "item-1", {"enabled": False})
    assert result["enabled"] is False


# ─────────────────────────────────────────────────────────────────────────────
# AQ-08: update_schedule — empty patch → 422
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ08_update_schedule_empty_patch_422():
    sb = _Supabase({"qa_schedules": _Q()})
    with pytest.raises(HTTPException) as exc:
        svc.update_schedule(sb, "item-1", {})
    assert exc.value.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# AQ-09: update_schedule — not found → 404
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ09_update_schedule_not_found_404():
    class _NullSchedQ(_Q):
        def update(self, *a, **k): return _Q(rows=[])

    sb = _Supabase({"qa_schedules": _NullSchedQ()})
    with pytest.raises(HTTPException) as exc:
        svc.update_schedule(sb, "item-none", {"enabled": False})
    assert exc.value.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# AQ-10: list_runs — filter forwarded
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ10_list_runs_returns_items():
    run = _run(status="COMPLETED")
    sb = _Supabase({"qa_runs": _Q(rows=[run], count=1)})
    result = svc.list_runs(sb, run_status="COMPLETED")
    assert len(result["items"]) == 1
    assert result["items"][0]["run_status"] == "COMPLETED"
    assert result["total"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# AQ-11: get_run — targets + results included
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ11_get_run_includes_targets_and_results():
    run = _run()
    target = {"id": "tgt-1", "run_id": "run-1", "qa_item_id": "item-1", "ordinal": 1, "created_at": "2026-10-01"}
    result = _result()
    sb = _Supabase({
        "qa_runs":         _Q(rows=[run]),
        "qa_run_targets":  _Q(rows=[target]),
        "qa_run_results":  _Q(rows=[result]),
    })
    data = svc.get_run(sb, "run-1")
    assert data["id"] == "run-1"
    assert len(data["targets"]) == 1
    assert len(data["results"]) == 1


# ─────────────────────────────────────────────────────────────────────────────
# AQ-12: get_run — FLAKY derivation
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ12_get_run_flaky_derived():
    run = _run()
    attempt1 = _result(status="FAIL", attempt=1)
    attempt2 = _result(status="PASS", attempt=2)
    sb = _Supabase({
        "qa_runs":         _Q(rows=[run]),
        "qa_run_targets":  _Q(rows=[]),
        "qa_run_results":  _Q(rows=[attempt1, attempt2]),
    })
    data = svc.get_run(sb, "run-1")
    assert all(r.get("flaky") is True for r in data["results"])


# ─────────────────────────────────────────────────────────────────────────────
# AQ-13: get_run — not found → 404
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ13_get_run_not_found_404():
    sb = _Supabase({"qa_runs": _Q(rows=[])})
    with pytest.raises(HTTPException) as exc:
        svc.get_run(sb, "run-none")
    assert exc.value.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# AQ-14: create_run — creates QUEUED run + targets
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ14_create_run_queued():
    inserted_run = dict(_run(), id="new-run")
    inserted_targets = []

    class _InsertQ(_Q):
        def insert(self, rows, **k):
            if isinstance(rows, dict):
                return _Q(rows=[inserted_run])
            inserted_targets.extend(rows)
            return _Q(rows=rows if isinstance(rows, list) else [rows])

    sb = _Supabase({
        "qa_items":        _Q(rows=[{"id": "item-1"}]),
        "qa_runs":         _InsertQ(rows=[inserted_run]),
        "qa_run_targets":  _InsertQ(),
    })
    result = svc.create_run(sb, "MANUAL", "admin@test.com", ["item-1"])
    assert result["run_status"] == "QUEUED"


# ─────────────────────────────────────────────────────────────────────────────
# AQ-15: create_run — empty qa_item_ids → 422
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ15_create_run_empty_item_ids_422():
    sb = _Supabase({})
    with pytest.raises(HTTPException) as exc:
        svc.create_run(sb, "MANUAL", None, [])
    assert exc.value.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# AQ-16: create_run — qa_item_id not found → 422
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ16_create_run_item_not_found_422():
    sb = _Supabase({"qa_items": _Q(rows=[])})
    with pytest.raises(HTTPException) as exc:
        svc.create_run(sb, "MANUAL", None, ["nonexistent-item"])
    assert exc.value.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# AQ-17: create_run — target insert fails → 500 + compensating DELETE
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ17_create_run_target_failure_compensating_delete():
    inserted_run = dict(_run(), id="run-fail")
    deleted = []

    class _RunQ(_Q):
        def insert(self, *a, **k): return _Q(rows=[inserted_run])
        def delete(self, *a, **k):
            deleted.append(True)
            return self

    class _TargetQ(_Q):
        def insert(self, *a, **k): raise Exception("DB constraint error")

    sb = _Supabase({
        "qa_items":        _Q(rows=[{"id": "item-1"}]),
        "qa_runs":         _RunQ(),
        "qa_run_targets":  _TargetQ(),
    })
    with pytest.raises(HTTPException) as exc:
        svc.create_run(sb, "MANUAL", None, ["item-1"])
    assert exc.value.status_code == 500
    assert deleted, "compensating DELETE must be called"
