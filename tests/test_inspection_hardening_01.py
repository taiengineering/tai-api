"""WO-INSPECTION-HARDENING-01 — worker history IDOR lock + /complete anchor freeze.

실 DB / 네트워크 0. AUTH 는 TestClient + dependency override, COMPLETION/REPAIR 는
MemDB 직접 호출.
"""
from __future__ import annotations

import asyncio
import os
import sys

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.dirname(__file__))

import routers.inspection_checklist as ic
import routers.worker_check as wc
from routers.auth import get_current_user
from test_inspection_rolling import MemDB, _seed
from test_worker_check_effective_history import FakeSB, _records, USERS, _patch

CALLER = {"id": "u-1", "phone": "01012345678"}
OTHER = {"id": "u-other"}
CUR = {"id": "user-1", "company_id": "c1", "role_code": "SAFETY_MANAGER"}
D1 = "2026-03-01"
D2 = "2026-04-15"


def _hist_app(user):
    app = FastAPI()
    app.include_router(wc.router)
    if user is False:
        def _deny():
            raise HTTPException(status_code=401, detail="토큰이 없습니다")
        app.dependency_overrides[get_current_user] = _deny
    else:
        app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


@pytest.fixture
def hist_wired(monkeypatch):
    fake = FakeSB(USERS, _records())
    monkeypatch.setattr(wc, "get_supabase", lambda: fake)
    return fake


# ── AUTH ──────────────────────────────────────────────────────────────────

def test_a1_history_no_token_401():
    client = _hist_app(False)
    r = client.get("/worker-check/history")
    assert r.status_code == 401


def test_a1_recent_no_token_401():
    client = _hist_app(False)
    r = client.get("/worker-check/recent")
    assert r.status_code == 401


def test_a2_history_no_query_uses_caller(hist_wired):
    out = wc.get_check_history(current=CALLER)
    assert out["status"] == "success"
    assert len(out["data"]["items"]) == 4
    assert hist_wired.rpc_calls[0][1]["p_inspector_id"] == "u-1"


def test_a3_own_worker_id_200(hist_wired):
    out = wc.get_check_history(worker_id="u-1", current=CALLER)
    assert out["status"] == "success"
    assert len(out["data"]["items"]) == 4


def test_a4_other_worker_id_403(hist_wired):
    with pytest.raises(HTTPException) as ei:
        wc.get_check_history(worker_id="u-other", current=CALLER)
    assert ei.value.status_code == 403
    assert ei.value.detail == {"error": "FORBIDDEN_IDENTITY"}
    assert hist_wired.rpc_calls == []


def test_a5_own_phone_200(hist_wired):
    out = wc.get_check_history(phone="010-1234-5678", current=CALLER)
    assert out["status"] == "success"
    assert len(out["data"]["items"]) == 4


def test_a6_other_phone_403(hist_wired):
    with pytest.raises(HTTPException) as ei:
        wc.get_check_history(phone="01099999999", current=CALLER)
    assert ei.value.status_code == 403
    assert ei.value.detail == {"error": "FORBIDDEN_IDENTITY"}
    assert hist_wired.rpc_calls == []


def test_a7_auth_no_records_200_empty():
    fake = FakeSB(USERS, [])
    with _patch(fake):
        out = wc.get_check_history(current=CALLER)
    assert out == {"status": "success", "data": {"items": []}}
    assert fake.rpc_calls  # identity ok → adapter 호출, 빈 목록


def test_a8_recent_same_matrix(hist_wired):
    out = wc.get_recent_checks(current=CALLER)
    assert out["status"] == "success" and len(out["data"]["items"]) == 4
    out = wc.get_recent_checks(phone="01012345678", current=CALLER)
    assert out["status"] == "success"
    with pytest.raises(HTTPException) as ei:
        wc.get_recent_checks(phone="01099999999", current=CALLER)
    assert ei.value.status_code == 403
    fake = FakeSB(USERS, [])
    with _patch(fake):
        empty = wc.get_recent_checks(current=CALLER)
    assert empty["data"]["items"] == []


# ── COMPLETION / REPAIR helpers ───────────────────────────────────────────

class _Bridge:
    def __init__(self):
        self.calls = []
        self._done = set()

    def __call__(self, supabase, inspection_id, *, actor_id, reason):
        first = inspection_id not in self._done
        self._done.add(inspection_id)
        self.calls.append({
            "inspection_id": inspection_id, "actor_id": actor_id,
            "reason": reason, "changed": first, "noop": not first,
        })
        return {"status": "COMPLETED", "changed": first, "noop": not first}


def _ws_updates(db, field=None):
    out = []
    for t, op, p, _f in db.log:
        if t == "work_schedules" and op == "update" and p:
            if field is None or field in p:
                out.append(p)
    return out


def _complete(db, spy, body, ws_id="WS-1"):
    orig = (ic.get_supabase, ic._ensure_ws_own, ic.complete_inspection_status)
    ic.get_supabase = lambda: db
    ic._ensure_ws_own = lambda *a, **k: None
    ic.complete_inspection_status = spy
    try:
        return asyncio.run(
            ic.complete_inspection(ws_id, body=body, current=CUR))
    finally:
        (ic.get_supabase, ic._ensure_ws_own, ic.complete_inspection_status) = orig


def _w3(db, spy, results):
    orig = (ic.get_supabase, ic._ensure_inspection_own, ic.record_safe_result_batch,
            ic.complete_inspection_status)
    ic.get_supabase = lambda: db
    ic._ensure_inspection_own = lambda *a, **k: None
    ic.record_safe_result_batch = lambda *a, **k: {"mode": "CREATED", "count": len(results)}
    ic.complete_inspection_status = spy
    try:
        return asyncio.run(
            ic.record_inspection_results("INS", {"results": results}, CUR))
    finally:
        (ic.get_supabase, ic._ensure_inspection_own, ic.record_safe_result_batch,
         ic.complete_inspection_status) = orig


def _next_rows(db, planned="2026-01-15"):
    return [r for r in db.tables["work_schedules"] if r.get("planned_date") != planned]


# ── COMPLETION ────────────────────────────────────────────────────────────

def test_b1_first_complete_sets_d1():
    db = _seed(MemDB())
    spy = _Bridge()
    out = _complete(db, spy, {"completed_at": D1})
    ws = db.tables["work_schedules"][0]
    assert ws["completed_at"] == D1
    assert out["data"]["completed_at"] == D1
    assert "mode" not in out["data"]
    assert _ws_updates(db, "completed_at") == [
        {"status_code": "completed", "completed_at": D1, "summary": ""}
    ]


def test_b2_d1_replay_physical_delta_0():
    db = _seed(MemDB())
    spy = _Bridge()
    _complete(db, spy, {"completed_at": D1})
    n = len(_ws_updates(db, "completed_at"))
    out = _complete(db, spy, {"completed_at": D1})
    assert out["data"]["mode"] == "REPLAY"
    assert out["data"]["completed_at"] == D1
    assert len(_ws_updates(db, "completed_at")) == n
    assert db.tables["work_schedules"][0]["completed_at"] == D1


def test_b3_d2_replay_keeps_d1_delta_0():
    db = _seed(MemDB())
    spy = _Bridge()
    _complete(db, spy, {"completed_at": D1})
    n = len(_ws_updates(db, "completed_at"))
    out = _complete(db, spy, {"completed_at": D2})
    assert out["data"]["completed_at"] == D1
    assert out["data"]["mode"] == "REPLAY"
    assert out["data"]["warning"] == {"code": "COMPLETION_DATE_IGNORED"}
    assert db.tables["work_schedules"][0]["completed_at"] == D1
    assert len(_ws_updates(db, "completed_at")) == n


def test_b4_w3_d1_then_complete_d2_keeps_d1():
    db = _seed(MemDB(), completed_at=None)
    spy = _Bridge()
    db.tables["work_schedules"][0]["completed_at"] = D1
    db.tables["work_schedules"][0]["status_code"] = "completed"
    out = _complete(db, spy, {"completed_at": D2})
    assert out["data"]["completed_at"] == D1
    assert db.tables["work_schedules"][0]["completed_at"] == D1
    assert _ws_updates(db, "completed_at") == []


def test_b5_complete_d1_then_w3_later_keeps_d1():
    db = _seed(MemDB())
    spy = _Bridge()
    _complete(db, spy, {"completed_at": D1})
    _w3(db, spy, [{"result": "NORMAL"}])
    assert db.tables["work_schedules"][0]["completed_at"] == D1


def test_b6_rolling_exactly_one():
    db = _seed(MemDB())
    spy = _Bridge()
    _complete(db, spy, {"completed_at": D1})
    _complete(db, spy, {"completed_at": D1})
    nxt = _next_rows(db)
    assert len(nxt) == 1
    assert nxt[0]["planned_date"] == "2027-03-01"


def test_b7_d2_replay_next_planned_date_unchanged():
    db = _seed(MemDB())
    spy = _Bridge()
    _complete(db, spy, {"completed_at": D1})
    before = db.tables["inspection_sets"][0]["next_planned_date"]
    _complete(db, spy, {"completed_at": D2})
    assert db.tables["inspection_sets"][0]["next_planned_date"] == before


def test_b8_status_change_dup_0_on_replay():
    db = _seed(MemDB())
    spy = _Bridge()
    _complete(db, spy, {"completed_at": D1})
    assert spy.calls[0]["changed"] is True
    _complete(db, spy, {"completed_at": D1})
    assert spy.calls[-1]["changed"] is False
    assert spy.calls[-1]["noop"] is True
    assert all(c["reason"] == "SAFE_COMPLETE" for c in spy.calls)


# ── REPAIR ────────────────────────────────────────────────────────────────

def test_c1_replay_repairs_missing_journal():
    db = _seed(MemDB())
    spy = _Bridge()
    _complete(db, spy, {"completed_at": D1})
    spy.calls.clear()
    spy._done.clear()  # journal 누락 시뮬
    _complete(db, spy, {"completed_at": D1})
    assert len(spy.calls) == 1
    assert spy.calls[0]["changed"] is True


def test_c2_replay_creates_exactly_one_missing_rolling():
    db = _seed(MemDB())
    spy = _Bridge()
    _complete(db, spy, {"completed_at": D1})
    db.tables["work_schedules"][:] = [
        r for r in db.tables["work_schedules"] if r.get("id") == "WS-1"
    ]
    assert _next_rows(db) == []
    _complete(db, spy, {"completed_at": D1})
    assert len(_next_rows(db)) == 1


def test_c3_replay_restores_forward_next_planned_date():
    db = _seed(MemDB())
    spy = _Bridge()
    _complete(db, spy, {"completed_at": D1})
    db.tables["inspection_sets"][0]["next_planned_date"] = "2026-01-15"  # partial / behind
    _complete(db, spy, {"completed_at": D1})
    assert db.tables["inspection_sets"][0]["next_planned_date"] == "2027-03-01"


def test_c4_repeat_repair_physical_delta_0():
    db = _seed(MemDB())
    spy = _Bridge()
    _complete(db, spy, {"completed_at": D1})
    n_ca = len(_ws_updates(db, "completed_at"))
    n_next = len(_next_rows(db))
    _complete(db, spy, {"completed_at": D2})
    _complete(db, spy, {"completed_at": D2})
    assert len(_ws_updates(db, "completed_at")) == n_ca
    assert len(_next_rows(db)) == n_next
    assert db.tables["work_schedules"][0]["completed_at"] == D1


# ── REV-1 concurrent first-completion CAS ─────────────────────────────────

def test_r1_concurrent_d1_d2_single_winner():
    db = _seed(MemDB())
    db.concurrent_preread_null = True
    spy = _Bridge()
    out1 = _complete(db, spy, {"completed_at": D1})
    out2 = _complete(db, spy, {"completed_at": D2, "summary": "loser-summary"})
    winner = D1
    assert len(_ws_updates(db, "completed_at")) == 1
    assert db.tables["work_schedules"][0]["completed_at"] == winner
    assert out1["data"]["completed_at"] == winner
    assert out2["data"]["completed_at"] == winner
    assert out1["data"].get("mode") is None
    assert out2["data"]["mode"] == "REPLAY"


def test_r2_loser_other_date_no_second_completed_at_write():
    db = _seed(MemDB())
    db.concurrent_preread_null = True
    spy = _Bridge()
    _complete(db, spy, {"completed_at": D1})
    n = len(_ws_updates(db, "completed_at"))
    out = _complete(db, spy, {"completed_at": D2, "summary": "loser-summary"})
    assert len(_ws_updates(db, "completed_at")) == n == 1
    assert db.tables["work_schedules"][0]["completed_at"] == D1
    assert out["data"]["summary"] != "loser-summary"
    assert out["data"]["warning"] == {"code": "COMPLETION_DATE_IGNORED"}


def test_r3_rolling_next_schedule_exactly_one_winner_anchor():
    db = _seed(MemDB())
    db.concurrent_preread_null = True
    spy = _Bridge()
    _complete(db, spy, {"completed_at": D1})
    _complete(db, spy, {"completed_at": D2})
    nxt = _next_rows(db)
    assert len(nxt) == 1
    assert nxt[0]["planned_date"] == "2027-03-01"


def test_r4_next_planned_date_is_winner_plus_cycle():
    db = _seed(MemDB())
    db.concurrent_preread_null = True
    spy = _Bridge()
    _complete(db, spy, {"completed_at": D1})
    _complete(db, spy, {"completed_at": D2})
    assert db.tables["inspection_sets"][0]["next_planned_date"] == "2027-03-01"


def test_r5_status_change_dup_0_on_race_loser():
    db = _seed(MemDB())
    db.concurrent_preread_null = True
    spy = _Bridge()
    _complete(db, spy, {"completed_at": D1})
    assert spy.calls[0]["changed"] is True
    _complete(db, spy, {"completed_at": D2})
    assert spy.calls[-1]["changed"] is False
    assert spy.calls[-1]["noop"] is True


def test_r6_race_loser_still_runs_rolling_and_journal_repair():
    db = _seed(MemDB())
    db.concurrent_preread_null = True
    spy = _Bridge()
    _complete(db, spy, {"completed_at": D1})
    db.tables["work_schedules"][:] = [
        r for r in db.tables["work_schedules"] if r.get("id") == "WS-1"
    ]
    spy.calls.clear()
    spy._done.clear()
    out = _complete(db, spy, {"completed_at": D2})
    assert out["data"]["mode"] == "REPLAY"
    assert len(spy.calls) == 1
    assert spy.calls[0]["reason"] == "SAFE_COMPLETE"
    assert len(_next_rows(db)) == 1
