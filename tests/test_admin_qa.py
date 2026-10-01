"""WO-QA-CONTROL-PHASE2B-001 PATCH-1 — Admin QA API 계약 테스트.

Production QA table write = 0 (mock 전용).

커버리지:
  AQ-01  summary — total/enabled/status_counts/sites 반환
  AQ-02  summary — FLAKY 항목 포함 status_counts
  AQ-03  list_items — schedule bulk join
  AQ-04  list_items — schedule None when absent
  AQ-05  list_items — effective_status projection (NEVER_RUN)
  AQ-06  list_items — effective_status filter 적용
  AQ-07  list_items — category filter 전달
  AQ-08  update_item — enabled=False 수정
  AQ-09  update_item — enabled=None → 422
  AQ-10  update_item — item not found → 404
  AQ-11  update_schedule — next_run_at 항상 NULL 강제
  AQ-12  update_schedule — MANUAL enabled=True → 400
  AQ-13  update_schedule — DAILY without anchor_time → 400
  AQ-14  update_schedule — WEEKLY without day_of_week → 400
  AQ-15  update_schedule — MINUTES without frequency_value → 400
  AQ-16  update_schedule — invalid timezone → 400
  AQ-17  update_schedule — empty patch → 422
  AQ-18  update_schedule — not found → 404
  AQ-19  list_runs — from_date/to_date filter
  AQ-20  list_runs — target_count/result_count/effective_counts 포함
  AQ-21  get_run — targets에 scenario_id/site_code/name 포함
  AQ-22  get_run — FLAKY 파생: attempt1=FAIL, attempt2=PASS
  AQ-23  get_run — FLAKY 파생: attempt1=PASS, attempt2=FAIL, attempt3=PASS
  AQ-24  get_run — not found → 404
  AQ-25  create_run — server-fixed trigger_type=MANUAL, ordinal=1..N
  AQ-26  create_run — empty ids → 422
  AQ-27  create_run — >100 ids → 422
  AQ-28  create_run — duplicate ids → 422
  AQ-29  create_run — disabled item → 422
  AQ-30  create_run — compensating DELETE on target failure
  AQ-31  admin router — no token → 401
  AQ-32  admin router — non-admin → 403
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

import services.qa_control_svc as svc
from services.qa_control_svc import derive_effective_status


# ─────────────────────────────────────────────────────────────────────────────
# Mock helpers
# ─────────────────────────────────────────────────────────────────────────────

class _Q:
    def __init__(self, rows=None, count=None):
        self._rows = rows or []
        self._count = count if count is not None else len(self._rows)
        self.inserted = None
        self.updated = None

    def select(self, *a, **k): return self
    def eq(self, *a, **k):     return self
    def neq(self, *a, **k):    return self
    def in_(self, *a, **k):    return self
    def gte(self, *a, **k):    return self
    def lte(self, *a, **k):    return self
    def order(self, *a, **k):  return self
    def range(self, *a, **k):  return self
    def limit(self, *a, **k):  return self

    def update(self, data, **k):
        self.updated = data
        return self

    def insert(self, rows, **k):
        self.inserted = rows
        return self

    def delete(self, *a, **k): return self

    def execute(self):
        return type("R", (), {"data": self._rows, "count": self._count})()


class _Supabase:
    def __init__(self, table_map: dict):
        self._map = table_map

    def table(self, name):
        return self._map.get(name, _Q())


def _item(id_="item-1", priority="P0", site_code="WWW", enabled=True, category="auth"):
    return {
        "id": id_, "scenario_id": f"P0-WWW-{id_[-1:]}", "site_code": site_code,
        "category": category, "name": f"Test {id_}", "description": None,
        "expected_summary": None, "priority": priority,
        "runner_type": "PLAYWRIGHT", "enabled": enabled,
        "created_at": "2026-10-01T00:00:00+09:00",
        "updated_at": "2026-10-01T00:00:00+09:00",
    }


def _sched(qa_item_id="item-1"):
    return {
        "id": "sched-1", "qa_item_id": qa_item_id,
        "enabled": False, "frequency_type": "MANUAL",
        "frequency_value": None, "anchor_time": None, "day_of_week": None,
        "timezone": "Asia/Seoul", "next_run_at": None, "last_scheduled_at": None,
        "created_at": "2026-10-01T00:00:00+09:00",
        "updated_at": "2026-10-01T00:00:00+09:00",
    }


def _run(id_="run-1", status="QUEUED"):
    return {
        "id": id_, "trigger_type": "MANUAL", "run_status": status,
        "github_run_id": None, "github_run_attempt": None,
        "head_sha": None, "branch_name": None,
        "requested_by": "user-admin", "requested_at": "2026-10-01T00:00:00+09:00",
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
# AQ-01: summary — total/enabled/status_counts/sites
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ01_summary_structure():
    items = [_item("i1", enabled=True), _item("i2", enabled=False)]
    sb = _Supabase({
        "qa_items":        _Q(rows=items),
        "qa_run_results":  _Q(rows=[]),
    })
    result = svc.get_summary(sb)
    assert result["total"] == 2
    assert result["enabled"] == 1
    assert "status_counts" in result
    assert "sites" in result


# ─────────────────────────────────────────────────────────────────────────────
# AQ-02: summary — FLAKY 항목 포함
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ02_summary_includes_flaky():
    items = [_item("i1")]
    results = [
        _result(item_id="i1", status="FAIL", attempt=1),
        _result(item_id="i1", status="PASS", attempt=2),
    ]
    sb = _Supabase({
        "qa_items":        _Q(rows=items),
        "qa_run_results":  _Q(rows=results),
    })
    result = svc.get_summary(sb)
    assert result["status_counts"].get("FLAKY") == 1


# ─────────────────────────────────────────────────────────────────────────────
# AQ-03: list_items — schedule bulk join
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ03_list_items_joins_schedule():
    item = _item()
    schedule = _sched(qa_item_id="item-1")
    sb = _Supabase({
        "qa_items":        _Q(rows=[item]),
        "qa_schedules":    _Q(rows=[schedule]),
        "qa_run_results":  _Q(rows=[]),
    })
    result = svc.list_items(sb)
    assert result["items"][0]["schedule"]["id"] == "sched-1"


# ─────────────────────────────────────────────────────────────────────────────
# AQ-04: list_items — schedule None when absent
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ04_list_items_schedule_none():
    sb = _Supabase({
        "qa_items":        _Q(rows=[_item()]),
        "qa_schedules":    _Q(rows=[]),
        "qa_run_results":  _Q(rows=[]),
    })
    result = svc.list_items(sb)
    assert result["items"][0]["schedule"] is None


# ─────────────────────────────────────────────────────────────────────────────
# AQ-05: list_items — effective_status NEVER_RUN when no results
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ05_list_items_never_run():
    sb = _Supabase({
        "qa_items":        _Q(rows=[_item()]),
        "qa_schedules":    _Q(rows=[]),
        "qa_run_results":  _Q(rows=[]),
    })
    result = svc.list_items(sb)
    assert result["items"][0]["effective_status"] == "NEVER_RUN"


# ─────────────────────────────────────────────────────────────────────────────
# AQ-06: list_items — effective_status filter
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ06_list_items_effective_status_filter():
    items = [_item("i1"), _item("i2")]
    # i1 has a PASS result, i2 has no results
    sb = _Supabase({
        "qa_items":        _Q(rows=items),
        "qa_schedules":    _Q(rows=[]),
        "qa_run_results":  _Q(rows=[_result(item_id="i1", status="PASS")]),
    })
    result = svc.list_items(sb, effective_status="NEVER_RUN")
    assert len(result["items"]) == 1
    assert result["items"][0]["id"] == "i2"


# ─────────────────────────────────────────────────────────────────────────────
# AQ-07: list_items — category filter forwarded
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ07_list_items_category_filter():
    item = _item(category="login")
    sb = _Supabase({
        "qa_items":        _Q(rows=[item]),
        "qa_schedules":    _Q(rows=[]),
        "qa_run_results":  _Q(rows=[]),
    })
    result = svc.list_items(sb, category="login")
    assert len(result["items"]) == 1


# ─────────────────────────────────────────────────────────────────────────────
# AQ-08: update_item — enabled=False
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ08_update_item_enabled():
    updated = dict(_item(), enabled=False)

    class _UQ(_Q):
        def update(self, *a, **k): return _Q(rows=[updated])

    sb = _Supabase({"qa_items": _UQ()})
    result = svc.update_item(sb, "item-1", enabled=False)
    assert result["enabled"] is False


# ─────────────────────────────────────────────────────────────────────────────
# AQ-09: update_item — enabled=None → 422
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ09_update_item_none_422():
    sb = _Supabase({"qa_items": _Q()})
    with pytest.raises(HTTPException) as exc:
        svc.update_item(sb, "item-1", enabled=None)
    assert exc.value.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# AQ-10: update_item — not found → 404
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ10_update_item_not_found():
    class _NullQ(_Q):
        def update(self, *a, **k): return _Q(rows=[])

    sb = _Supabase({"qa_items": _NullQ()})
    with pytest.raises(HTTPException) as exc:
        svc.update_item(sb, "item-none", enabled=False)
    assert exc.value.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# AQ-11: update_schedule — next_run_at 항상 NULL 강제
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ11_update_schedule_next_run_at_forced_null():
    captured = {}

    class _SQ(_Q):
        def update(self, data, **k):
            captured.update(data)
            return _Q(rows=[dict(_sched(), **data)])

    sb = _Supabase({"qa_schedules": _SQ()})
    svc.update_schedule(sb, "item-1", {"enabled": False})
    assert captured.get("next_run_at") is None


# ─────────────────────────────────────────────────────────────────────────────
# AQ-12: update_schedule — MANUAL + enabled=True → 400
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ12_update_schedule_manual_enabled_true_400():
    sb = _Supabase({"qa_schedules": _Q()})
    with pytest.raises(HTTPException) as exc:
        svc.update_schedule(sb, "item-1", {"frequency_type": "MANUAL", "enabled": True})
    assert exc.value.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# AQ-13: update_schedule — DAILY without anchor_time → 400
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ13_update_schedule_daily_no_anchor_400():
    sb = _Supabase({"qa_schedules": _Q()})
    with pytest.raises(HTTPException) as exc:
        svc.update_schedule(sb, "item-1", {"frequency_type": "DAILY"})
    assert exc.value.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# AQ-14: update_schedule — WEEKLY without day_of_week → 400
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ14_update_schedule_weekly_no_dow_400():
    sb = _Supabase({"qa_schedules": _Q()})
    with pytest.raises(HTTPException) as exc:
        svc.update_schedule(sb, "item-1", {"frequency_type": "WEEKLY", "anchor_time": "09:00:00"})
    assert exc.value.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# AQ-15: update_schedule — MINUTES without frequency_value → 400
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ15_update_schedule_minutes_no_value_400():
    sb = _Supabase({"qa_schedules": _Q()})
    with pytest.raises(HTTPException) as exc:
        svc.update_schedule(sb, "item-1", {"frequency_type": "MINUTES"})
    assert exc.value.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# AQ-16: update_schedule — invalid timezone → 400
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ16_update_schedule_invalid_timezone_400():
    sb = _Supabase({"qa_schedules": _Q()})
    with pytest.raises(HTTPException) as exc:
        svc.update_schedule(sb, "item-1", {"timezone": "UTC"})
    assert exc.value.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# AQ-17: update_schedule — empty patch → 422
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ17_update_schedule_empty_422():
    sb = _Supabase({"qa_schedules": _Q()})
    with pytest.raises(HTTPException) as exc:
        svc.update_schedule(sb, "item-1", {})
    assert exc.value.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# AQ-18: update_schedule — not found → 404
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ18_update_schedule_not_found_404():
    class _NullSQ(_Q):
        def update(self, *a, **k): return _Q(rows=[])

    sb = _Supabase({"qa_schedules": _NullSQ()})
    with pytest.raises(HTTPException) as exc:
        svc.update_schedule(sb, "item-none", {"enabled": False})
    assert exc.value.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# AQ-19: list_runs — from_date/to_date filter (パラメータ転達確認)
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ19_list_runs_date_filters():
    run = _run(status="COMPLETED")
    sb = _Supabase({
        "qa_runs":         _Q(rows=[run], count=1),
        "qa_run_targets":  _Q(rows=[]),
        "qa_run_results":  _Q(rows=[]),
    })
    result = svc.list_runs(sb, from_date="2026-10-01", to_date="2026-10-31")
    assert result["total"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# AQ-20: list_runs — target_count/result_count/effective_counts 포함
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ20_list_runs_counts():
    run = _run()
    target = {"run_id": "run-1"}
    result_row = {"run_id": "run-1", "qa_item_id": "item-1", "result_status": "PASS", "attempt": 1}
    sb = _Supabase({
        "qa_runs":         _Q(rows=[run], count=1),
        "qa_run_targets":  _Q(rows=[target]),
        "qa_run_results":  _Q(rows=[result_row]),
    })
    result = svc.list_runs(sb)
    assert result["items"][0]["target_count"] == 1
    assert result["items"][0]["result_count"] == 1
    assert result["items"][0]["effective_counts"].get("PASS") == 1


# ─────────────────────────────────────────────────────────────────────────────
# AQ-21: get_run — targets에 scenario_id/site_code/name 포함
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ21_get_run_target_enriched():
    run = _run()
    target = {"id": "tgt-1", "run_id": "run-1", "qa_item_id": "item-1", "ordinal": 1, "created_at": "2026-10-01"}
    item_info = {"id": "item-1", "scenario_id": "P0-WWW-001", "site_code": "WWW", "name": "Login"}
    sb = _Supabase({
        "qa_runs":         _Q(rows=[run]),
        "qa_run_targets":  _Q(rows=[target]),
        "qa_run_results":  _Q(rows=[]),
        "qa_items":        _Q(rows=[item_info]),
    })
    data = svc.get_run(sb, "run-1")
    t = data["targets"][0]
    assert t["scenario_id"] == "P0-WWW-001"
    assert t["site_code"] == "WWW"
    assert t["name"] == "Login"
    assert t["effective_status"] == "NEVER_RUN"


# ─────────────────────────────────────────────────────────────────────────────
# AQ-22: get_run — FLAKY: attempt1=FAIL + attempt2=PASS
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ22_get_run_flaky_simple():
    run = _run()
    attempt1 = _result(status="FAIL", attempt=1)
    attempt2 = _result(status="PASS", attempt=2)
    sb = _Supabase({
        "qa_runs":         _Q(rows=[run]),
        "qa_run_targets":  _Q(rows=[]),
        "qa_run_results":  _Q(rows=[attempt1, attempt2]),
        "qa_items":        _Q(rows=[]),
    })
    data = svc.get_run(sb, "run-1")
    assert all(r.get("flaky") is True for r in data["results"])


# ─────────────────────────────────────────────────────────────────────────────
# AQ-23: get_run — FLAKY: PASS→FAIL→PASS
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ23_get_run_flaky_interleaved():
    """attempt1=PASS, attempt2=FAIL, attempt3=PASS → FLAKY (final=PASS + earlier FAIL)."""
    run = _run()
    a1 = _result(status="PASS", attempt=1)
    a2 = _result(status="FAIL", attempt=2)
    a3 = _result(status="PASS", attempt=3)
    sb = _Supabase({
        "qa_runs":         _Q(rows=[run]),
        "qa_run_targets":  _Q(rows=[]),
        "qa_run_results":  _Q(rows=[a1, a2, a3]),
        "qa_items":        _Q(rows=[]),
    })
    data = svc.get_run(sb, "run-1")
    assert all(r.get("flaky") is True for r in data["results"])


# ─────────────────────────────────────────────────────────────────────────────
# AQ-24: get_run — not found → 404
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ24_get_run_not_found_404():
    sb = _Supabase({"qa_runs": _Q(rows=[])})
    with pytest.raises(HTTPException) as exc:
        svc.get_run(sb, "run-none")
    assert exc.value.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# AQ-25: create_run — server-fixed trigger_type/requested_by/ordinal
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ25_create_run_server_fixed_fields():
    inserted_run_data = {}
    inserted_targets = []

    class _RunQ(_Q):
        def insert(self, data, **k):
            inserted_run_data.update(data)
            return _Q(rows=[dict(data, id="new-run")])

    class _TargetQ(_Q):
        def insert(self, rows, **k):
            inserted_targets.extend(rows)
            return _Q(rows=rows)

    sb = _Supabase({
        "qa_items":        _Q(rows=[{"id": "item-1", "enabled": True}, {"id": "item-2", "enabled": True}]),
        "qa_runs":         _RunQ(),
        "qa_run_targets":  _TargetQ(),
    })
    result = svc.create_run(sb, "admin-user-id", ["item-1", "item-2"])

    assert inserted_run_data["trigger_type"] == "MANUAL"
    assert inserted_run_data["requested_by"] == "admin-user-id"
    assert inserted_run_data["run_status"] == "QUEUED"

    ordinals = [t["ordinal"] for t in inserted_targets]
    assert ordinals == [1, 2]


# ─────────────────────────────────────────────────────────────────────────────
# AQ-26: create_run — empty ids → 422
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ26_create_run_empty_422():
    sb = _Supabase({})
    with pytest.raises(HTTPException) as exc:
        svc.create_run(sb, "admin", [])
    assert exc.value.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# AQ-27: create_run — >100 ids → 422
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ27_create_run_over_100_422():
    sb = _Supabase({})
    with pytest.raises(HTTPException) as exc:
        svc.create_run(sb, "admin", [f"item-{i}" for i in range(101)])
    assert exc.value.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# AQ-28: create_run — duplicate ids → 422
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ28_create_run_duplicate_422():
    sb = _Supabase({})
    with pytest.raises(HTTPException) as exc:
        svc.create_run(sb, "admin", ["item-1", "item-1"])
    assert exc.value.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# AQ-29: create_run — disabled item → 422
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ29_create_run_disabled_item_422():
    sb = _Supabase({"qa_items": _Q(rows=[{"id": "item-1", "enabled": False}])})
    with pytest.raises(HTTPException) as exc:
        svc.create_run(sb, "admin", ["item-1"])
    assert exc.value.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# AQ-30: create_run — target failure → 500 + compensating DELETE
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ30_create_run_compensating_delete():
    deleted = []

    class _RunQ(_Q):
        def insert(self, *a, **k): return _Q(rows=[{"id": "run-fail", "trigger_type": "MANUAL", "run_status": "QUEUED", "requested_by": "a", "requested_at": "2026-10-01T00:00:00+09:00", "started_at": None, "finished_at": None, "error_code": None, "error_summary": None, "created_at": "2026-10-01T00:00:00+09:00", "updated_at": "2026-10-01T00:00:00+09:00", "github_run_id": None, "github_run_attempt": None, "head_sha": None, "branch_name": None}])
        def delete(self, *a, **k):
            deleted.append(True)
            return self

    class _TargetQ(_Q):
        def insert(self, *a, **k): raise Exception("DB error")

    sb = _Supabase({
        "qa_items":        _Q(rows=[{"id": "item-1", "enabled": True}]),
        "qa_runs":         _RunQ(),
        "qa_run_targets":  _TargetQ(),
    })
    with pytest.raises(HTTPException) as exc:
        svc.create_run(sb, "admin", ["item-1"])
    assert exc.value.status_code == 500
    assert deleted, "compensating DELETE must execute"


# ─────────────────────────────────────────────────────────────────────────────
# AQ-31: admin router — no token → 401
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ31_no_token_401():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers.admin_qa import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/admin/qa/summary")
    assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# AQ-32: admin router — non-admin → 403
# ─────────────────────────────────────────────────────────────────────────────

def test_AQ32_non_admin_403(monkeypatch):
    from fastapi import FastAPI, HTTPException as FHTTPEx
    from fastapi.testclient import TestClient
    from routers.admin_qa import router
    from routers.auth import get_current_user

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "role_code": "099"}

    def _deny(*a, **k):
        raise FHTTPEx(status_code=403, detail="권한이 없습니다")

    monkeypatch.setattr("routers.admin_qa._require_admin", _deny)
    monkeypatch.setattr("routers.admin_qa.get_supabase", lambda: None)

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/admin/qa/summary", headers={"Authorization": "Bearer fake"})
    assert resp.status_code == 403
    app.dependency_overrides.clear()
