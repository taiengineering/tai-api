"""Phase H2A — Targeted Dispatch API 계약 테스트.

Production QA table write = 0 (mock 전용).

커버리지:
  H2A01  valid scenario_ids → run QUEUED (trigger_type=PR, requested_by=targeted-qa)
  H2A02  empty scenario_ids → 422
  H2A03  >100 scenario_ids → 422
  H2A04  duplicate scenario_ids → 422
  H2A05  unknown scenario_id → 422
  H2A06  disabled scenario → 422
  H2A07  dispatch failure → run_status=ERROR, dispatch="ERROR"
  H2A08  missing secret → 403 (router)
  H2A09  wrong secret → 403 (router)
  H2A10  ordinal preserved — input order 1..N
"""
from __future__ import annotations

import os
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

import services.qa_control_svc as svc


# ─────────────────────────────────────────────────────────────────────────────
# Mock helpers
# ─────────────────────────────────────────────────────────────────────────────

_VALID_RUN_ID = "run-td-001"


class _Q:
    def __init__(self, rows=None):
        self._rows = rows or []
        self.last_insert = None
        self.last_update = None
        self.last_delete_eq = None

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

    def delete(self, **k):
        return self

    def execute(self):
        return type("R", (), {"data": self._rows})()


class _RunQ(_Q):
    """qa_runs: insert returns the canned run row; update is a no-op."""

    def __init__(self, run_row):
        super().__init__(rows=[run_row])

    def insert(self, rows, **k):
        self.last_insert = rows
        return self


def _run_row(status="QUEUED"):
    return {
        "id":           _VALID_RUN_ID,
        "trigger_type": "PR",
        "run_status":   status,
        "requested_by": "targeted-qa",
        "requested_at": "2026-10-06T00:00:00+09:00",
        "started_at":   None,
        "finished_at":  None,
        "error_code":   None,
        "error_summary": None,
        "created_at":   "2026-10-06T00:00:00+09:00",
        "updated_at":   "2026-10-06T00:00:00+09:00",
    }


def _item_row(scenario_id: str, item_id: str, enabled: bool = True) -> Dict[str, Any]:
    return {"id": item_id, "scenario_id": scenario_id, "enabled": enabled}


class _Supabase:
    def __init__(self, table_map):
        self._map = table_map

    def table(self, name):
        return self._map.get(name, _Q())


def _happy_sb(scenario_ids: List[str]) -> _Supabase:
    """Supabase mock for a happy-path call with the given scenario_ids."""
    item_rows = [_item_row(sid, f"item-{i+1}") for i, sid in enumerate(scenario_ids)]
    return _Supabase({
        "qa_items":       _Q(rows=item_rows),
        "qa_runs":        _RunQ(_run_row()),
        "qa_run_targets": _Q(),
    })


# ─────────────────────────────────────────────────────────────────────────────
# H2A01 — valid scenario_ids → QUEUED, trigger_type=PR, requested_by=targeted-qa
# ─────────────────────────────────────────────────────────────────────────────

def test_H2A01_valid_scenario_ids_creates_run():
    sids = ["P0-WWW-001", "P0-ADMIN-002"]
    sb   = _happy_sb(sids)

    result = svc.create_targeted_run(sb, sids)

    assert result["id"] == _VALID_RUN_ID
    assert result["run_status"] == "QUEUED"
    assert result["trigger_type"] == "PR"
    assert result["requested_by"] == "targeted-qa"
    assert result["scenario_ids"] == sids


# ─────────────────────────────────────────────────────────────────────────────
# H2A02 — empty scenario_ids → 422
# ─────────────────────────────────────────────────────────────────────────────

def test_H2A02_empty_scenario_ids_422():
    sb = _happy_sb([])
    with pytest.raises(HTTPException) as exc_info:
        svc.create_targeted_run(sb, [])
    assert exc_info.value.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# H2A03 — >100 scenario_ids → 422
# ─────────────────────────────────────────────────────────────────────────────

def test_H2A03_over_100_scenario_ids_422():
    sids = [f"P0-SCEN-{i:03d}" for i in range(101)]
    sb   = _happy_sb(sids)
    with pytest.raises(HTTPException) as exc_info:
        svc.create_targeted_run(sb, sids)
    assert exc_info.value.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# H2A04 — duplicate scenario_ids → 422
# ─────────────────────────────────────────────────────────────────────────────

def test_H2A04_duplicate_scenario_ids_422():
    sids = ["P0-WWW-001", "P0-WWW-001"]
    sb   = _happy_sb(["P0-WWW-001"])
    with pytest.raises(HTTPException) as exc_info:
        svc.create_targeted_run(sb, sids)
    assert exc_info.value.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# H2A05 — unknown scenario_id → 422
# ─────────────────────────────────────────────────────────────────────────────

def test_H2A05_unknown_scenario_id_422():
    sids = ["P0-WWW-001", "P0-UNKNOWN-999"]
    # Only P0-WWW-001 exists in DB
    sb = _Supabase({
        "qa_items": _Q(rows=[_item_row("P0-WWW-001", "item-1")]),
        "qa_runs":  _RunQ(_run_row()),
    })
    with pytest.raises(HTTPException) as exc_info:
        svc.create_targeted_run(sb, sids)
    assert exc_info.value.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# H2A06 — disabled scenario → 422
# ─────────────────────────────────────────────────────────────────────────────

def test_H2A06_disabled_scenario_422():
    sids = ["P0-WWW-001", "P0-DISABLED-002"]
    sb   = _Supabase({
        "qa_items": _Q(rows=[
            _item_row("P0-WWW-001",    "item-1", enabled=True),
            _item_row("P0-DISABLED-002", "item-2", enabled=False),
        ]),
        "qa_runs": _RunQ(_run_row()),
    })
    with pytest.raises(HTTPException) as exc_info:
        svc.create_targeted_run(sb, sids)
    assert exc_info.value.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# H2A07 — dispatch failure → run_status=ERROR, dispatch="ERROR" (router-level)
# ─────────────────────────────────────────────────────────────────────────────

def test_H2A07_dispatch_failure_returns_error(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers.internal_qa import router

    monkeypatch.setenv("INTERNAL_API_SECRET", "secret")

    sids     = ["P0-WWW-001"]
    run_data = {**_run_row(), "scenario_ids": sids, "targets": []}

    # create_targeted_run returns a canned QUEUED run
    monkeypatch.setattr("routers.internal_qa.svc.create_targeted_run",
                        lambda sb, s: dict(run_data))

    # Fake supabase: update/eq/execute are all no-ops
    monkeypatch.setattr("routers.internal_qa.get_supabase", lambda: _Supabase({
        "qa_runs": _Q(),
    }))

    # dispatch_qa_run raises — patched at the module level so local import picks it up
    import services.github_dispatch_svc as _gd_svc
    monkeypatch.setattr(_gd_svc, "dispatch_qa_run",
                        AsyncMock(side_effect=RuntimeError("GitHub API 오류")))

    # serialize_external_utc + now_kst
    import services.time as _time_svc
    monkeypatch.setattr(_time_svc, "now_kst",
                        lambda: __import__("datetime").datetime(2026, 10, 6, tzinfo=__import__("datetime").timezone.utc))
    monkeypatch.setattr(_time_svc, "serialize_external_utc",
                        lambda dt: "2026-10-06T00:00:00+00:00")

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/internal/qa/targeted-dispatch",
        headers={"X-Internal-Secret": "secret"},
        json={"scenario_ids": sids},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["dispatch"] == "ERROR"
    assert body["data"]["run_status"] == "ERROR"


# ─────────────────────────────────────────────────────────────────────────────
# H2A08 — missing secret → 403 (router)
# ─────────────────────────────────────────────────────────────────────────────

def test_H2A08_missing_secret_403(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers.internal_qa import router

    monkeypatch.setenv("INTERNAL_API_SECRET", "correct")

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/internal/qa/targeted-dispatch",
        json={"scenario_ids": ["P0-WWW-001"]},
    )
    assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# H2A09 — wrong secret → 403 (router)
# ─────────────────────────────────────────────────────────────────────────────

def test_H2A09_wrong_secret_403(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers.internal_qa import router

    monkeypatch.setenv("INTERNAL_API_SECRET", "correct")

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/internal/qa/targeted-dispatch",
        headers={"X-Internal-Secret": "wrong"},
        json={"scenario_ids": ["P0-WWW-001"]},
    )
    assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# H2A10 — ordinal preserved: input order → ordinal 1..N
# ─────────────────────────────────────────────────────────────────────────────

def test_H2A10_ordinal_preserves_input_order():
    sids = ["P0-ZZZ-003", "P0-AAA-001", "P0-MMM-002"]
    sb   = _happy_sb(sids)

    result = svc.create_targeted_run(sb, sids)

    targets = result["targets"]
    assert len(targets) == 3
    for expected_ordinal, (target, sid) in enumerate(zip(targets, sids), start=1):
        assert target["ordinal"] == expected_ordinal
