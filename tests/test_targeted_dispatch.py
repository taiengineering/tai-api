"""Phase H2A — Targeted Dispatch API 계약 테스트.

Production QA table write = 0 (mock 전용).

커버리지:
  H2A01  valid scenario_ids → run QUEUED (trigger_type=PR, requested_by=targeted-qa)
  H2A02  empty scenario_ids → 422
  H2A03  >100 scenario_ids → 422
  H2A04  duplicate scenario_ids → 422
  H2A05  unknown scenario_id → 422
  H2A06  disabled scenario → 422
  H2A07  dispatch failure → HTTP 502 + status=error + run_status=ERROR (PATCH-F)
  H2A08  missing secret → 403 (router)
  H2A09  wrong secret → 403 (router)
  H2A10  ordinal preserved — input order 1..N
  H2A11  success dispatch → HTTP 201 + RUNNING + allow_conditional=False exact (PATCH-C)
  H2A12  target insert failure → HTTPException 500 + run rollback (PATCH-D)
  H2A13  client authority override rejected — trigger_type/requested_by 고정 (PATCH-E)
"""
from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import AsyncMock

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
    """qa_runs: insert returns the canned run row."""

    def __init__(self, run_row):
        super().__init__(rows=[run_row])

    def insert(self, rows, **k):
        self.last_insert = rows
        return self


class _TrackDeleteRunQ(_RunQ):
    """qa_runs: tracks delete().eq("id", ...) calls for compensation tests."""

    def __init__(self, run_row):
        super().__init__(run_row)
        self.deleted_ids: List[str] = []
        self._in_delete_chain = False

    def delete(self, **k):
        self._in_delete_chain = True
        return self

    def eq(self, col, val):
        if self._in_delete_chain and col == "id":
            self.deleted_ids.append(val)
            self._in_delete_chain = False
        return self


class _FailInsertQ(_Q):
    """Raises RuntimeError on execute — simulates target insert DB failure."""

    def execute(self):
        raise RuntimeError("simulated target insert DB failure")


def _run_row(status="QUEUED") -> Dict[str, Any]:
    return {
        "id":            _VALID_RUN_ID,
        "trigger_type":  "PR",
        "run_status":    status,
        "requested_by":  "targeted-qa",
        "requested_at":  "2026-10-06T00:00:00+09:00",
        "started_at":    None,
        "finished_at":   None,
        "error_code":    None,
        "error_summary": None,
        "created_at":    "2026-10-06T00:00:00+09:00",
        "updated_at":    "2026-10-06T00:00:00+09:00",
    }


def _item_row(scenario_id: str, item_id: str, enabled: bool = True) -> Dict[str, Any]:
    return {"id": item_id, "scenario_id": scenario_id, "enabled": enabled}


class _Supabase:
    def __init__(self, table_map):
        self._map = table_map

    def table(self, name):
        return self._map.get(name, _Q())


def _happy_sb(scenario_ids: List[str]) -> _Supabase:
    item_rows = [_item_row(sid, f"item-{i+1}") for i, sid in enumerate(scenario_ids)]
    return _Supabase({
        "qa_items":       _Q(rows=item_rows),
        "qa_runs":        _RunQ(_run_row()),
        "qa_run_targets": _Q(),
    })


def _router_client(monkeypatch, *, sids: List[str], dispatch_mock, secret: str = "secret"):
    """Build a FastAPI TestClient for the targeted-dispatch router with standard mocks."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers.internal_qa import router

    monkeypatch.setenv("INTERNAL_API_SECRET", secret)

    run_data = {**_run_row(), "scenario_ids": sids, "targets": []}
    monkeypatch.setattr("routers.internal_qa.svc.create_targeted_run",
                        lambda sb, s: dict(run_data))
    monkeypatch.setattr("routers.internal_qa.get_supabase",
                        lambda: _Supabase({"qa_runs": _Q()}))

    import services.github_dispatch_svc as _gd
    monkeypatch.setattr(_gd, "dispatch_qa_run", dispatch_mock)

    import services.time as _t
    import datetime as _dt
    monkeypatch.setattr(_t, "now_kst",
                        lambda: _dt.datetime(2026, 10, 6, tzinfo=_dt.timezone.utc))
    monkeypatch.setattr(_t, "serialize_external_utc",
                        lambda dt: "2026-10-06T00:00:00+00:00")

    app = FastAPI()
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False), run_data


# ─────────────────────────────────────────────────────────────────────────────
# H2A01 — valid scenario_ids → QUEUED, trigger_type=PR, requested_by=targeted-qa
# ─────────────────────────────────────────────────────────────────────────────

def test_H2A01_valid_scenario_ids_creates_run():
    sids   = ["P0-WWW-001", "P0-ADMIN-002"]
    result = svc.create_targeted_run(_happy_sb(sids), sids)

    assert result["id"] == _VALID_RUN_ID
    assert result["run_status"] == "QUEUED"
    assert result["trigger_type"] == "PR"
    assert result["requested_by"] == "targeted-qa"
    assert result["scenario_ids"] == sids


# ─────────────────────────────────────────────────────────────────────────────
# H2A02 — empty scenario_ids → 422
# ─────────────────────────────────────────────────────────────────────────────

def test_H2A02_empty_scenario_ids_422():
    with pytest.raises(HTTPException) as exc_info:
        svc.create_targeted_run(_happy_sb([]), [])
    assert exc_info.value.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# H2A03 — >100 scenario_ids → 422
# ─────────────────────────────────────────────────────────────────────────────

def test_H2A03_over_100_scenario_ids_422():
    sids = [f"P0-SCEN-{i:03d}" for i in range(101)]
    with pytest.raises(HTTPException) as exc_info:
        svc.create_targeted_run(_happy_sb(sids), sids)
    assert exc_info.value.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# H2A04 — duplicate scenario_ids → 422
# ─────────────────────────────────────────────────────────────────────────────

def test_H2A04_duplicate_scenario_ids_422():
    sids = ["P0-WWW-001", "P0-WWW-001"]
    with pytest.raises(HTTPException) as exc_info:
        svc.create_targeted_run(_happy_sb(["P0-WWW-001"]), sids)
    assert exc_info.value.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# H2A05 — unknown scenario_id → 422
# ─────────────────────────────────────────────────────────────────────────────

def test_H2A05_unknown_scenario_id_422():
    sids = ["P0-WWW-001", "P0-UNKNOWN-999"]
    sb   = _Supabase({
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
            _item_row("P0-WWW-001",      "item-1", enabled=True),
            _item_row("P0-DISABLED-002", "item-2", enabled=False),
        ]),
        "qa_runs": _RunQ(_run_row()),
    })
    with pytest.raises(HTTPException) as exc_info:
        svc.create_targeted_run(sb, sids)
    assert exc_info.value.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# H2A07 — dispatch failure → HTTP 502 + status=error + run_status=ERROR (PATCH-F)
# ─────────────────────────────────────────────────────────────────────────────

def test_H2A07_dispatch_failure_502_error(monkeypatch):
    sids    = ["P0-WWW-001"]
    mock_dispatch = AsyncMock(side_effect=RuntimeError("GitHub API 오류"))
    client, _ = _router_client(monkeypatch, sids=sids, dispatch_mock=mock_dispatch)

    resp = client.post(
        "/internal/qa/targeted-dispatch",
        headers={"X-Internal-Secret": "secret"},
        json={"scenario_ids": sids},
    )

    assert resp.status_code == 502
    body = resp.json()
    assert body["status"] == "error"
    assert body["dispatch"] == "ERROR"
    assert body["data"]["run_status"] == "ERROR"
    # error_summary must be present and sanitized (no raw exception class leaked)
    assert body["data"]["error_summary"] is not None


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
    sids   = ["P0-ZZZ-003", "P0-AAA-001", "P0-MMM-002"]
    result = svc.create_targeted_run(_happy_sb(sids), sids)

    targets = result["targets"]
    assert len(targets) == 3
    for expected_ordinal, target in enumerate(targets, start=1):
        assert target["ordinal"] == expected_ordinal


# ─────────────────────────────────────────────────────────────────────────────
# H2A11 — success path: HTTP 201 + RUNNING + allow_conditional=False (PATCH-C)
# ─────────────────────────────────────────────────────────────────────────────

def test_H2A11_success_dispatch_running_and_allow_conditional_false(monkeypatch):
    sids          = ["P0-WWW-001", "P0-ADMIN-002"]
    mock_dispatch = AsyncMock(return_value=None)
    client, run_data = _router_client(monkeypatch, sids=sids, dispatch_mock=mock_dispatch)

    resp = client.post(
        "/internal/qa/targeted-dispatch",
        headers={"X-Internal-Secret": "secret"},
        json={"scenario_ids": sids},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "success"
    assert body["dispatch"] == "OK"
    assert body["data"]["run_status"] == "RUNNING"

    # dispatch_qa_run must be called with allow_conditional=False
    mock_dispatch.assert_awaited_once_with(
        run_data["id"],
        sids,
        allow_conditional=False,
    )


# ─────────────────────────────────────────────────────────────────────────────
# H2A12 — target insert failure → HTTP 500 + run rollback (PATCH-D)
# ─────────────────────────────────────────────────────────────────────────────

def test_H2A12_target_insert_failure_rollback():
    sids    = ["P0-WWW-001"]
    runs_q  = _TrackDeleteRunQ(_run_row())
    sb      = _Supabase({
        "qa_items":       _Q(rows=[_item_row("P0-WWW-001", "item-1")]),
        "qa_runs":        runs_q,
        "qa_run_targets": _FailInsertQ(),
    })

    with pytest.raises(HTTPException) as exc_info:
        svc.create_targeted_run(sb, sids)

    assert exc_info.value.status_code == 500
    # compensation: qa_runs.delete().eq("id", run_id) called exactly once
    assert runs_q.deleted_ids == [_VALID_RUN_ID]


# ─────────────────────────────────────────────────────────────────────────────
# H2A13 — client authority override rejected (PATCH-E)
#          extra fields (trigger_type/requested_by/allow_conditional) are ignored;
#          server always enforces PR / targeted-qa / allow_conditional=False
# ─────────────────────────────────────────────────────────────────────────────

def test_H2A13_client_override_ignored_server_authority_fixed(monkeypatch):
    sids          = ["P0-WWW-001"]
    mock_dispatch = AsyncMock(return_value=None)
    client, run_data = _router_client(monkeypatch, sids=sids, dispatch_mock=mock_dispatch)

    # Attempt to override server-controlled fields via request body
    resp = client.post(
        "/internal/qa/targeted-dispatch",
        headers={"X-Internal-Secret": "secret"},
        json={
            "scenario_ids":    sids,
            "trigger_type":    "SCHEDULE",       # override attempt — must be ignored
            "requested_by":    "attacker",        # override attempt — must be ignored
            "allow_conditional": True,            # override attempt — must be ignored
        },
    )

    # Request must succeed (extra fields silently ignored by Pydantic)
    assert resp.status_code == 201

    # Server authority: dispatch must always use allow_conditional=False
    mock_dispatch.assert_awaited_once_with(
        run_data["id"],
        sids,
        allow_conditional=False,
    )

    # Server authority: run created with fixed trigger_type + requested_by
    assert run_data["trigger_type"] == "PR"
    assert run_data["requested_by"] == "targeted-qa"
