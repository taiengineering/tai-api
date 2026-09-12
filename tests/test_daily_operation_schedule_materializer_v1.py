"""WO-SAFE-DAILY-SCHEDULE-MATERIALIZER-V1-001 focused tests.

Run: pytest tests/test_daily_operation_schedule_materializer_v1.py -q
"""
from __future__ import annotations

import inspect
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import pytest

import services.inspection_sets_svc.law_engine as LE
import services.inspection_sets_svc.schedules as S
from services.inspection_sets_helpers import (
    ONESHOT_REPEAT_TYPE,
    _build_operation_schedule_row,
    _operation_planned_date,
)
from services.inspection_rolling import CONFLICT_KEY
from services.status_vocab import ws_write_scheduled


# ── Fake Supabase ──────────────────────────────────────────────────


class _Resp:
    def __init__(self, data):
        self.data = data


class _Q:
    def __init__(self, sb: "_SB", name: str):
        self.sb = sb
        self.name = name
        self._op = "select"
        self._payload: Any = None
        self._filters: Dict[str, Any] = {}
        self._gte: Dict[str, Any] = {}
        self._neq: Dict[str, Any] = {}
        self._limit: Optional[int] = None
        self._on_conflict: Optional[str] = None
        self._ignore_dup = False

    def select(self, *_a, **_k):
        self._op = "select"
        return self

    def insert(self, row):
        self._op = "insert"
        self._payload = row
        return self

    def upsert(self, row, on_conflict=None, ignore_duplicates=False):
        self._op = "upsert"
        self._payload = row
        self._on_conflict = on_conflict
        self._ignore_dup = ignore_duplicates
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def delete(self):
        self._op = "delete"
        self.sb.deletes.append({"table": self.name})
        return self

    def eq(self, k, v):
        self._filters[k] = v
        return self

    def neq(self, k, v):
        self._neq[k] = v
        return self

    def gte(self, k, v):
        self._gte[k] = v
        return self

    def limit(self, n):
        self._limit = n
        return self

    def _match(self, row: dict) -> bool:
        for k, v in self._filters.items():
            if row.get(k) != v:
                return False
        for k, v in self._neq.items():
            if row.get(k) == v:
                return False
        for k, v in self._gte.items():
            if str(row.get(k) or "") < str(v):
                return False
        return True

    def execute(self):
        rows: List[dict] = getattr(self.sb, self.name, [])
        if self._op == "select":
            hits = [r for r in rows if self._match(r)]
            if self._limit is not None:
                hits = hits[: self._limit]
            return _Resp(hits)

        if self._op == "upsert":
            self.sb.upsert_calls.append(
                {
                    "row": dict(self._payload),
                    "on_conflict": self._on_conflict,
                    "ignore_duplicates": self._ignore_dup,
                }
            )
            if getattr(self.sb, "block_upsert", False):
                return _Resp([])
            row = dict(self._payload)
            if "id" not in row:
                row["id"] = f"gen-{len(rows)+1}"
            key = (row.get("inspection_set_id"), row.get("planned_date"), row.get("factory_id"))
            for existing in rows:
                ekey = (
                    existing.get("inspection_set_id"),
                    existing.get("planned_date"),
                    existing.get("factory_id"),
                )
                if ekey == key:
                    if self._ignore_dup:
                        return _Resp([])  # DO NOTHING
                    existing.update(row)
                    return _Resp([existing])
            rows.append(row)
            self.sb.inserts.append(row)
            return _Resp([row])

        if self._op == "insert":
            payload = self._payload
            batch = payload if isinstance(payload, list) else [payload]
            out = []
            for row in batch:
                r = dict(row)
                if "id" not in r:
                    r["id"] = f"ins-{len(rows)+1}"
                rows.append(r)
                self.sb.inserts.append(dict(r))
                out.append(dict(r))
            return _Resp(out)

        if self._op == "update":
            updated = []
            for r in rows:
                if self._match(r):
                    rid = r.get("id")
                    if rid in getattr(self.sb, "fail_update_ids", set()):
                        raise RuntimeError("injected update failure")
                    # assignee-only / active_yn-only sync — fake applies payload as-is.
                    r.update(dict(self._payload))
                    updated.append(r)
                    self.sb.updates.append({"id": rid, "payload": dict(self._payload)})
            return _Resp(updated)

        if self._op == "delete":
            self.sb.delete_ops += 1
            kept = [r for r in rows if not self._match(r)]
            setattr(self.sb, self.name, kept)
            return _Resp([])

        return _Resp([])


class _SB:
    def __init__(self):
        self.inspection_sets: List[dict] = []
        self.work_schedules: List[dict] = []
        self.work_assignments: List[dict] = []
        self.safety_inspections: List[dict] = []
        self.equipment_checkins: List[dict] = []
        self.factories: List[dict] = []
        self.inserts: List[dict] = []
        self.updates: List[dict] = []
        self.upsert_calls: List[dict] = []
        self.deletes: List[dict] = []
        self.delete_ops = 0
        self.fail_update_ids: set = set()
        self.block_upsert = False

    def table(self, name: str):
        return _Q(self, name)


def _iset(**kw) -> dict:
    base = {
        "id": "set-1",
        "factory_id": "f1",
        "company_id": "c1",
        "source": "LEGAL_ENGINE",
        "is_active": True,
        "legal_obligation_atom_id": "atom-1",
        "assignee_user_id": "user-1",
        "inspection_set_name": "정기점검",
        "inspection_category": "INSPECT",
        "description": "desc",
        "holiday_process_type": None,
        "operation_time_rule": None,
        "cycle_unit": "month",
        "cycle_value": 1,
    }
    base.update(kw)
    return base


def _every(basis="2026-01-15", value=1, unit="month") -> dict:
    return {
        "version": "v1",
        "source": "USER_EDITED",
        "operator": "EVERY",
        "value": value,
        "unit": unit,
        "basis_date": basis,
    }


def _within(basis="2026-10-01", value=1, unit="month") -> dict:
    return {
        "version": "v1",
        "source": "USER_EDITED",
        "operator": "WITHIN",
        "value": value,
        "unit": unit,
        "basis_date": basis,
    }


def _before(basis="2026-10-10", value=3, unit="day") -> dict:
    return {
        "version": "v1",
        "source": "USER_EDITED",
        "operator": "BEFORE",
        "value": value,
        "unit": unit,
        "basis_date": basis,
    }



def _ws(**kw) -> dict:
    """Canonical LEGAL active schedule row for Stage2 fixtures."""
    base = {
        "factory_id": "f1",
        "inspection_set_id": "set-1",
        "status_code": "scheduled",
        "source_type": "LEGAL",
        "assigned_user_id": "user-1",
        "active_yn": True,
        "is_excluded": False,
        "excluded_reason": None,
    }
    base.update(kw)
    return base


@pytest.fixture
def freeze_today(monkeypatch):
    """Pin business_today to 2026-09-12 for deterministic date math."""
    fixed = date(2026, 9, 12)

    def _today(*_a, **_k):
        return fixed

    monkeypatch.setattr("services.inspection_sets_helpers.business_today", _today)
    monkeypatch.setattr("services.inspection_sets_svc.law_engine.business_today", _today)
    return fixed


# ── Pure helpers ───────────────────────────────────────────────────


def test_T4_T5_every_uses_otr_not_cycle(freeze_today):
    rule = _every(basis="2026-01-15", value=2, unit="week")
    planned, reason = _operation_planned_date(rule)
    assert reason is None
    # fast-forward from basis+2w until >= today
    assert planned >= freeze_today
    # cycle_* must not be consulted — rule alone drives result
    assert planned == _operation_planned_date(rule)[0]


def test_T9_within_basis_plus_delta_no_ff(freeze_today):
    rule = _within(basis="2026-10-01", value=1, unit="month")
    planned, reason = _operation_planned_date(rule)
    assert reason is None
    assert planned == date(2026, 11, 1)


def test_T10_within_no_fast_forward(freeze_today):
    # future date stays exact — not advanced by recurring loop
    rule = _within(basis="2026-09-20", value=5, unit="day")
    planned, _ = _operation_planned_date(rule)
    assert planned == date(2026, 9, 25)


def test_T11_within_past_due_write_0(freeze_today):
    rule = _within(basis="2026-01-01", value=1, unit="month")
    planned, reason = _operation_planned_date(rule)
    assert planned is None
    assert reason == "PAST_DUE_ONE_SHOT"


def test_T12_before_basis_minus_delta(freeze_today):
    rule = _before(basis="2026-10-10", value=3, unit="day")
    planned, reason = _operation_planned_date(rule)
    assert reason is None
    assert planned == date(2026, 10, 7)


def test_T14_before_past_due(freeze_today):
    rule = _before(basis="2026-09-10", value=3, unit="day")
    planned, reason = _operation_planned_date(rule)
    assert planned is None
    assert reason == "PAST_DUE_ONE_SHOT"


def test_T6_T7_T8_canonical_row(freeze_today):
    iset = _iset(operation_time_rule=_every())
    row = _build_operation_schedule_row(iset, date(2026, 10, 15), _every())
    assert row["status_code"] == ws_write_scheduled() == "scheduled"
    assert row["source_type"] == "LEGAL"
    assert row["assigned_user_id"] == "user-1"
    assert "PENDING" not in row["status_code"]
    assert "SCHEDULED" != row["status_code"]
    assert row["source_type"] != "LAW_ENGINE"


def test_T9_once_repeat_type(freeze_today):
    iset = _iset()
    row = _build_operation_schedule_row(iset, date(2026, 11, 1), _within())
    assert row["repeat_type"] == ONESHOT_REPEAT_TYPE == "once"


# ── Materializer integration ───────────────────────────────────────


def test_T1_T2_factory_scoped_legal_engine_only(freeze_today):
    sb = _SB()
    sb.inspection_sets = [
        _iset(id="ok", factory_id="f1", source="LEGAL_ENGINE", operation_time_rule=_every()),
        _iset(id="manual", factory_id="f1", source="MANUAL", operation_time_rule=_every()),
        _iset(id="other", factory_id="f2", source="LEGAL_ENGINE", operation_time_rule=_every()),
    ]
    out = LE.run_generate_operation_schedules("f1", sb)
    assert out["total_sets"] == 1
    assert out["created"] == 1
    assert all(r["inspection_set_id"] == "ok" for r in sb.inserts)


def test_T3_otr_missing_even_with_cycle(freeze_today):
    sb = _SB()
    sb.inspection_sets = [
        _iset(operation_time_rule=None, cycle_unit="month", cycle_value=1),
    ]
    out = LE.run_generate_operation_schedules("f1", sb)
    assert out["created"] == 0
    assert out["skipped_no_condition"] == 1
    assert sb.inserts == []


def test_T13_before_incomplete_schedule_0(freeze_today):
    sb = _SB()
    rule = {"version": "v1", "source": "USER_EDITED", "operator": "BEFORE", "basis_date": "2026-10-10"}
    sb.inspection_sets = [_iset(operation_time_rule=rule)]
    out = LE.run_generate_operation_schedules("f1", sb)
    assert out["created"] == 0
    assert sb.inserts == []


def test_T15_until_schedule_0(freeze_today):
    sb = _SB()
    rule = {"version": "v1", "source": "LEGAL_DEFAULT", "operator": "UNTIL", "month": 12, "day": 31}
    sb.inspection_sets = [_iset(operation_time_rule=rule)]
    out = LE.run_generate_operation_schedules("f1", sb)
    assert out["created"] == 0
    assert sb.inserts == []


def test_T18_T19_exact_identity_duplicate_and_conflict(freeze_today):
    sb = _SB()
    rule = _within(basis="2026-10-01", value=1, unit="month")  # → 2026-11-01
    sb.inspection_sets = [_iset(operation_time_rule=rule)]
    planned = "2026-11-01"
    sb.work_schedules = [_ws(
        id="ws-exist",
        planned_date=planned,
        assigned_user_id="user-1",
    )]
    out = LE.run_generate_operation_schedules("f1", sb)
    assert out["created"] == 0
    assert out["skipped_dup"] == 1
    assert len(sb.inserts) == 0


def test_T19_upsert_conflict_key(freeze_today):
    sb = _SB()
    sb.inspection_sets = [_iset(operation_time_rule=_within(basis="2026-10-01", value=1, unit="month"))]
    LE.run_generate_operation_schedules("f1", sb)
    assert sb.upsert_calls
    assert sb.upsert_calls[0]["on_conflict"] == CONFLICT_KEY
    assert sb.upsert_calls[0]["ignore_duplicates"] is True


def test_T20_completed_preserve(freeze_today):
    sb = _SB()
    rule = _within(basis="2026-10-01", value=1, unit="month")
    sb.inspection_sets = [_iset(operation_time_rule=rule)]
    sb.work_schedules = [_ws(
        id="ws-c", planned_date="2026-11-01", status_code="completed",
        assigned_user_id="old",
    )]
    out = LE.run_generate_operation_schedules("f1", sb)
    assert out["created"] == 0
    assert out["preserved_existing"] == 1
    assert sb.updates == []


def test_T21_in_progress_preserve(freeze_today):
    sb = _SB()
    rule = _within(basis="2026-10-01", value=1, unit="month")
    sb.inspection_sets = [_iset(operation_time_rule=rule)]
    sb.work_schedules = [_ws(
        id="ws-i", planned_date="2026-11-01", status_code="in_progress",
        assigned_user_id="old",
    )]
    out = LE.run_generate_operation_schedules("f1", sb)
    assert out["preserved_existing"] == 1
    assert sb.updates == []


def test_T22_child_linked_preserve(freeze_today):
    sb = _SB()
    rule = _within(basis="2026-10-01", value=1, unit="month")
    sb.inspection_sets = [_iset(operation_time_rule=rule, assignee_user_id="user-NEW")]
    sb.work_schedules = [_ws(
        id="ws-ch", planned_date="2026-11-01", assigned_user_id="old",
    )]
    sb.work_assignments = [{"id": "wa1", "schedule_id": "ws-ch", "factory_id": "f1"}]
    out = LE.run_generate_operation_schedules("f1", sb)
    assert out["preserved_child_linked"] == 1
    assert sb.updates == []
    assert out["created"] == 0
    assert out["assignee_synced"] == 0


def test_T23_T24_child_free_assignee_sync_only(freeze_today):
    sb = _SB()
    rule = _within(basis="2026-10-01", value=1, unit="month")
    sb.inspection_sets = [_iset(operation_time_rule=rule, assignee_user_id="user-NEW")]
    sb.work_schedules = [_ws(
        id="ws-cf", planned_date="2026-11-01", assigned_user_id="old",
        repeat_type="once", repeat_interval=1,
    )]
    out = LE.run_generate_operation_schedules("f1", sb)
    assert out["assignee_synced"] == 1
    assert sb.updates
    assert set(sb.updates[0]["payload"].keys()) == {"assigned_user_id"}
    assert sb.updates[0]["payload"]["assigned_user_id"] == "user-NEW"
    ws = sb.work_schedules[0]
    assert ws["planned_date"] == "2026-11-01"
    assert ws["status_code"] == "scheduled"
    assert ws["source_type"] == "LEGAL"


def test_R8_stale_child_free_future_preserved_and_latest_created(freeze_today):
    """Stage2: old 12/01 physically preserved + active_yn=false; latest 11/01 created."""
    sb = _SB()
    rule = _within(basis="2026-10-01", value=1, unit="month")  # → 2026-11-01
    sb.inspection_sets = [_iset(operation_time_rule=rule)]
    sb.work_schedules = [_ws(id="ws-old", planned_date="2026-12-01")]
    out = LE.run_generate_operation_schedules("f1", sb)
    assert out["created"] == 1
    assert out["stale_inactivated"] == 1
    assert out["stale_preserved"] == 0
    assert sb.deletes == []
    assert not any("planned_date" in (u.get("payload") or {}) for u in sb.updates)
    old = next(r for r in sb.work_schedules if r["id"] == "ws-old")
    assert old["planned_date"] == "2026-12-01"
    assert old["active_yn"] is False
    dates = {r["planned_date"] for r in sb.work_schedules if r.get("inspection_set_id") == "set-1"}
    assert dates == {"2026-12-01", "2026-11-01"}
    assert any(r.get("planned_date") == "2026-11-01" and r["id"] != "ws-old" for r in sb.work_schedules)


def test_R8b_exact_plus_stale_both_preserved(freeze_today):
    """Stage2: exact latest already active; leftover stale inactivated (DELETE 0)."""
    sb = _SB()
    rule = _within(basis="2026-10-01", value=1, unit="month")
    sb.inspection_sets = [_iset(operation_time_rule=rule)]
    sb.work_schedules = [
        _ws(id="ws-new", planned_date="2026-11-01"),
        _ws(id="ws-old", planned_date="2026-12-01"),
    ]
    out = LE.run_generate_operation_schedules("f1", sb)
    assert out["created"] == 0
    assert out["stale_inactivated"] == 1
    assert out["stale_preserved"] == 0
    assert sb.deletes == []
    old = next(r for r in sb.work_schedules if r["id"] == "ws-old")
    assert old["active_yn"] is False
    assert old["planned_date"] == "2026-12-01"
    dates = {r["planned_date"] for r in sb.work_schedules if r.get("inspection_set_id") == "set-1"}
    assert dates == {"2026-11-01", "2026-12-01"}


def test_T27_T28_T29_static_guards_official_source():
    src = inspect.getsource(LE)
    assert '"PENDING"' not in src
    assert "'PENDING'" not in src
    assert '"SCHEDULED"' not in src
    assert "'SCHEDULED'" not in src
    assert '"LAW_ENGINE"' not in src
    assert "'LAW_ENGINE'" not in src
    assert 'status_code": "cancel' not in src
    assert "status_code': 'cancel" not in src
    assert "legal_actor" not in src
    assert "source_text" not in src
    assert "def _delete_stale" not in src
    assert "def _converge_payload" not in src
    assert ".delete(" not in src
    sync_src = inspect.getsource(LE._sync_assignee_only)
    assert "planned_date" not in sync_src
    assert "start_date" not in sync_src
    assert "end_date" not in sync_src
    assert "status_code" not in sync_src
    assert "source_type" not in sync_src
    assert '{"assigned_user_id":assignee_user_id}' in sync_src.replace(" ", "")


def test_R8c_non_legal_exact_identity_preserved_no_takeover(freeze_today):
    """LEGAL materializer must not rewrite MANUAL exact-identity rows."""
    sb = _SB()
    rule = _within(basis="2026-10-01", value=1, unit="month")
    sb.inspection_sets = [_iset(operation_time_rule=rule, assignee_user_id="user-NEW")]
    sb.work_schedules = [_ws(
        id="ws-man", planned_date="2026-11-01", source_type="MANUAL",
        assigned_user_id="user-OLD",
    )]
    out = LE.run_generate_operation_schedules("f1", sb)
    assert out["created"] == 0
    assert out["assignee_synced"] == 0
    assert out["preserved_existing"] == 1
    assert out["latest_not_secured"] == 1
    assert out["stale_inactivated"] == 0
    assert sb.updates == []
    assert sb.deletes == []
    ws = sb.work_schedules[0]
    assert ws["source_type"] == "MANUAL"
    assert ws["assigned_user_id"] == "user-OLD"
    assert ws["planned_date"] == "2026-11-01"


def test_T30_factory_id_predicates_in_queries(freeze_today):
    sb = _SB()
    rule = _within(basis="2026-10-01", value=1, unit="month")
    sb.inspection_sets = [_iset(operation_time_rule=rule)]
    # Existing exact identity so update path with factory_id is exercised too
    sb.work_schedules = [_ws(
        id="ws-x", planned_date="2026-11-01", status_code="planned",
        assigned_user_id="old",
    )]
    LE.run_generate_operation_schedules("f1", sb)
    src = inspect.getsource(LE)
    assert '.eq("factory_id"' in src or ".eq('factory_id'" in src
    assert src.count("factory_id") >= 5


def test_T31_T32_generate_schedules_all_factory_loop(freeze_today, monkeypatch):
    calls = []

    def fake_op(fid, sb):
        calls.append(fid)
        return {
            "total_sets": 1, "created": 1, "skipped_dup": 0, "skipped_no_condition": 0,
            "assignee_synced": 0, "preserved_existing": 0,
            "preserved_child_linked": 0, "stale_preserved": 0,
            "reactivated": 0, "stale_inactivated": 0, "latest_not_secured": 0,
        }

    sb = _SB()
    sb.factories = [{"id": "f1", "is_active": True}, {"id": "f2", "is_active": True}]
    monkeypatch.setattr(S, "get_supabase", lambda: sb)
    monkeypatch.setattr(S, "run_generate_operation_schedules", fake_op)
    out = S.generate_schedules_all()
    assert calls == ["f1", "f2"]
    assert out["data"]["total_created"] == 2
    assert "LAW_ENGINE" not in out["message"]
    # official path must not import/call legacy PENDING builder
    src = inspect.getsource(S.generate_schedules_all)
    assert "_build_law_engine_row" not in src
    assert "_meets_4_conditions" not in src


def test_T33_mode_law_engine_delegates(freeze_today, monkeypatch):
    seen = {}

    def fake_op(fid, sb):
        seen["fid"] = fid
        return {
            "total_sets": 2, "created": 1, "skipped_dup": 0, "skipped_no_condition": 1,
            "assignee_synced": 0, "preserved_existing": 0,
            "preserved_child_linked": 0, "stale_preserved": 0,
            "reactivated": 0, "stale_inactivated": 0, "latest_not_secured": 0,
        }

    sb = _SB()
    monkeypatch.setattr(S, "get_supabase", lambda: sb)
    monkeypatch.setattr(S, "run_generate_operation_schedules", fake_op)
    out = S.generate_schedules_for_factory("f1", "law_engine", False)
    assert seen["fid"] == "f1"
    assert out["data"]["created"] == 1
    assert "LEGAL/operation" in out["message"]


def test_T34_no_new_endpoint():
    import routers.inspection_sets as R
    src = inspect.getsource(R)
    assert "/daily" not in src
    assert "generate-operation" not in src
    assert "@router.post(\"/materializer" not in src
    assert "@router.post('/materializer" not in src


def test_T35_wrapper_compat():
    assert LE.run_generate_law_engine is not None
    # thin wrapper body
    src = inspect.getsource(LE.run_generate_law_engine)
    assert "run_generate_operation_schedules" in src


def test_T16_T17_no_legal_parse_or_obligation_timing():
    src = inspect.getsource(LE)
    assert "source_text" not in src
    assert "legal_time_normalizer" not in src
    # obligation_type must not gate membership — only used as row field via category
    assert "obligation_type" not in inspect.getsource(LE.run_generate_operation_schedules)


def test_empty_sets_compat_keys(freeze_today):
    sb = _SB()
    out = LE.run_generate_law_engine("f1", sb)
    assert out["total_sets"] == 0
    assert out["created"] == 0
    assert out["skipped_dup"] == 0
    assert out["skipped_no_condition"] == 0


def test_atom_missing_skip(freeze_today):
    sb = _SB()
    sb.inspection_sets = [
        _iset(legal_obligation_atom_id=None, operation_time_rule=_every()),
        _iset(id="set-2", legal_obligation_atom_id="  ", operation_time_rule=_every()),
    ]
    out = LE.run_generate_operation_schedules("f1", sb)
    assert out["created"] == 0
    assert out["skipped_no_condition"] == 2


def test_legacy_aliases_pending_scheduled_read_as_preserve_or_sync(freeze_today):
    """Read aliases: PENDING→planned, SCHEDULED→scheduled — child-free → assignee sync."""
    sb = _SB()
    rule = _within(basis="2026-10-01", value=1, unit="month")
    sb.inspection_sets = [_iset(operation_time_rule=rule, assignee_user_id="u2")]
    sb.work_schedules = [_ws(
        id="ws-legacy", planned_date="2026-11-01", status_code="SCHEDULED",
        assigned_user_id="u1",
    )]
    out = LE.run_generate_operation_schedules("f1", sb)
    assert out["assignee_synced"] == 1


def test_R7_legal_engine_excluded_from_anchor(freeze_today, monkeypatch):
    sb = _SB()
    sb.inspection_sets = [
        _iset(
            id="leg-1",
            source="LEGAL_ENGINE",
            schedule_anchor_date="2026-01-01",
            cycle_unit="month",
            cycle_value=1,
            assignee_user_id="user-1",
            operation_time_rule=None,
            anchor_confirmed=True,
        ),
    ]
    # Fake needs anchor_confirmed filter — add to sets and filter in _match via eq chain
    for r in sb.inspection_sets:
        r["anchor_confirmed"] = True
        r["is_active"] = True
    monkeypatch.setattr(S, "get_supabase", lambda: sb)
    out = S.generate_schedules_for_factory("f1", "anchor", False)
    assert out["data"]["created"] == 0
    assert any(
        x.get("reason") == "LEGAL_ENGINE_REQUIRES_OTR_MATERIALIZER"
        for x in out["data"]["results"]
    )
    assert sb.inserts == []
    assert sb.delete_ops == 0


def test_R9_completed_old_date_preserved_while_creating_latest(freeze_today):
    sb = _SB()
    rule = _within(basis="2026-10-01", value=1, unit="month")
    sb.inspection_sets = [_iset(operation_time_rule=rule)]
    sb.work_schedules = [_ws(
        id="ws-done", planned_date="2026-12-01", status_code="completed",
    )]
    out = LE.run_generate_operation_schedules("f1", sb)
    assert out["created"] == 1
    assert sb.deletes == []
    assert sb.delete_ops == 0
    assert any(r["id"] == "ws-done" and r["planned_date"] == "2026-12-01" for r in sb.work_schedules)
    assert any(r.get("planned_date") == "2026-11-01" for r in sb.inserts)


def test_R10_in_progress_old_date_preserved(freeze_today):
    sb = _SB()
    rule = _within(basis="2026-10-01", value=1, unit="month")
    sb.inspection_sets = [_iset(operation_time_rule=rule)]
    sb.work_schedules = [_ws(
        id="ws-ip", planned_date="2026-12-01", status_code="in_progress",
    )]
    out = LE.run_generate_operation_schedules("f1", sb)
    assert sb.deletes == []
    assert sb.delete_ops == 0
    assert any(r["id"] == "ws-ip" for r in sb.work_schedules)
    assert out["created"] == 1


def test_R11_wa_linked_stale_preserved(freeze_today):
    sb = _SB()
    rule = _within(basis="2026-10-01", value=1, unit="month")
    sb.inspection_sets = [_iset(operation_time_rule=rule)]
    sb.work_schedules = [_ws(id="ws-wa", planned_date="2026-12-01")]
    sb.work_assignments = [{"id": "wa1", "schedule_id": "ws-wa", "factory_id": "f1"}]
    out = LE.run_generate_operation_schedules("f1", sb)
    assert sb.deletes == []
    assert sb.delete_ops == 0
    stale = next(r for r in sb.work_schedules if r["id"] == "ws-wa")
    assert stale["planned_date"] == "2026-12-01"
    assert stale["active_yn"] is True
    assert out["created"] == 1  # latest identity still created
    assert out["stale_preserved"] == 1
    assert out["stale_inactivated"] == 0


def test_R12_equipment_child_linked_preserved(freeze_today):
    sb = _SB()
    rule = _within(basis="2026-10-01", value=1, unit="month")
    sb.inspection_sets = [_iset(operation_time_rule=rule)]
    sb.work_schedules = [_ws(id="ws-ec", planned_date="2026-12-01")]
    sb.equipment_checkins = [{"id": "ec1", "schedule_id": "ws-ec", "factory_id": "f1"}]
    out = LE.run_generate_operation_schedules("f1", sb)
    assert sb.deletes == []
    assert sb.delete_ops == 0
    stale = next(r for r in sb.work_schedules if r["id"] == "ws-ec")
    assert stale["active_yn"] is True
    assert out["stale_preserved"] == 1
    assert out["stale_inactivated"] == 0


def test_R13_R14_idempotent_second_run(freeze_today):
    sb = _SB()
    rule = _within(basis="2026-10-01", value=1, unit="month")
    sb.inspection_sets = [_iset(operation_time_rule=rule)]
    sb.work_schedules = [_ws(id="ws-old", planned_date="2026-12-01")]
    out1 = LE.run_generate_operation_schedules("f1", sb)
    assert out1["created"] == 1
    assert out1["stale_inactivated"] == 1
    n = len(sb.work_schedules)
    updates_before = len(sb.updates)
    deletes_before = sb.delete_ops
    out2 = LE.run_generate_operation_schedules("f1", sb)
    assert out2["created"] == 0
    assert out2["reactivated"] == 0
    assert out2["stale_inactivated"] == 0
    assert out2["stale_preserved"] == 0
    assert sb.delete_ops == deletes_before == 0
    assert len(sb.work_schedules) == n
    assert not any("planned_date" in (u.get("payload") or {}) for u in sb.updates)
    # second run: no new active_yn mutations on already-inactive stale
    assert len([u for u in sb.updates[updates_before:] if "active_yn" in (u.get("payload") or {})]) == 0


def test_R15_R16_R17_canonical_write_and_no_cancelled(freeze_today):
    sb = _SB()
    sb.inspection_sets = [_iset(operation_time_rule=_within(basis="2026-10-01", value=1, unit="month"))]
    LE.run_generate_operation_schedules("f1", sb)
    row = sb.inserts[0]
    assert row["status_code"] == "scheduled"
    assert row["source_type"] == "LEGAL"
    assert row["status_code"] not in ("PENDING", "SCHEDULED")
    assert row["source_type"] != "LAW_ENGINE"
    assert row["status_code"] != "cancelled"
    assert 'status_code": "cancel' not in inspect.getsource(LE)
    assert "status_code': 'cancel" not in inspect.getsource(LE)


# ── Stage2 contract matrix (PATCH-R3) ──────────────────────────────


def test_P3_exact_inactive_eligible_reactivate_then_stale(freeze_today):
    sb = _SB()
    rule = _within(basis="2026-10-01", value=1, unit="month")
    sb.inspection_sets = [_iset(operation_time_rule=rule, assignee_user_id="user-NEW")]
    sb.work_schedules = [
        _ws(
            id="ws-exact", planned_date="2026-11-01", active_yn=False,
            assigned_user_id="user-OLD",
        ),
        _ws(id="ws-old", planned_date="2026-12-01"),
    ]
    out = LE.run_generate_operation_schedules("f1", sb)
    assert out["created"] == 0
    assert out["reactivated"] == 1
    assert out["stale_inactivated"] == 1
    exact = next(r for r in sb.work_schedules if r["id"] == "ws-exact")
    assert exact["active_yn"] is True
    assert exact["assigned_user_id"] == "user-NEW"
    assert exact["planned_date"] == "2026-11-01"
    stale = next(r for r in sb.work_schedules if r["id"] == "ws-old")
    assert stale["active_yn"] is False
    assert sb.deletes == []


def test_P4_exact_inactive_is_excluded_no_reactivate(freeze_today):
    sb = _SB()
    rule = _within(basis="2026-10-01", value=1, unit="month")
    sb.inspection_sets = [_iset(operation_time_rule=rule)]
    sb.work_schedules = [
        _ws(id="ws-exact", planned_date="2026-11-01", active_yn=False, is_excluded=True),
        _ws(id="ws-old", planned_date="2026-12-01"),
    ]
    out = LE.run_generate_operation_schedules("f1", sb)
    assert out["reactivated"] == 0
    assert out["latest_not_secured"] == 1
    assert out["stale_inactivated"] == 0
    assert next(r for r in sb.work_schedules if r["id"] == "ws-exact")["active_yn"] is False
    assert next(r for r in sb.work_schedules if r["id"] == "ws-old")["active_yn"] is True


def test_P5_exact_inactive_excluded_reason_no_reactivate(freeze_today):
    sb = _SB()
    rule = _within(basis="2026-10-01", value=1, unit="month")
    sb.inspection_sets = [_iset(operation_time_rule=rule)]
    sb.work_schedules = [
        _ws(
            id="ws-exact", planned_date="2026-11-01", active_yn=False,
            excluded_reason="manual_hold",
        ),
        _ws(id="ws-old", planned_date="2026-12-01"),
    ]
    out = LE.run_generate_operation_schedules("f1", sb)
    assert out["reactivated"] == 0
    assert out["latest_not_secured"] == 1
    assert out["stale_inactivated"] == 0
    assert next(r for r in sb.work_schedules if r["id"] == "ws-old")["active_yn"] is True


def test_P6_exact_active_yn_null_no_reactivate(freeze_today):
    sb = _SB()
    rule = _within(basis="2026-10-01", value=1, unit="month")
    sb.inspection_sets = [_iset(operation_time_rule=rule)]
    sb.work_schedules = [
        _ws(id="ws-exact", planned_date="2026-11-01", active_yn=None),
        _ws(id="ws-old", planned_date="2026-12-01"),
    ]
    out = LE.run_generate_operation_schedules("f1", sb)
    assert out["reactivated"] == 0
    assert out["latest_not_secured"] == 1
    assert out["stale_inactivated"] == 0
    assert next(r for r in sb.work_schedules if r["id"] == "ws-old")["active_yn"] is True


def test_P7_exact_inactive_child_linked_no_reactivate(freeze_today):
    sb = _SB()
    rule = _within(basis="2026-10-01", value=1, unit="month")
    sb.inspection_sets = [_iset(operation_time_rule=rule)]
    sb.work_schedules = [
        _ws(id="ws-exact", planned_date="2026-11-01", active_yn=False),
        _ws(id="ws-old", planned_date="2026-12-01"),
    ]
    sb.work_assignments = [{"id": "wa1", "schedule_id": "ws-exact", "factory_id": "f1"}]
    out = LE.run_generate_operation_schedules("f1", sb)
    assert out["reactivated"] == 0
    assert out["latest_not_secured"] == 1
    assert out["stale_inactivated"] == 0
    assert next(r for r in sb.work_schedules if r["id"] == "ws-old")["active_yn"] is True


def test_P10_child_query_exception_fail_close_preserve(freeze_today):
    class BoomSB(_SB):
        def table(self, name: str):
            if name in ("work_assignments", "safety_inspections", "equipment_checkins"):
                raise RuntimeError("child table boom")
            return _Q(self, name)

    sb2 = BoomSB()
    rule = _within(basis="2026-10-01", value=1, unit="month")
    sb2.inspection_sets = [_iset(operation_time_rule=rule)]
    sb2.work_schedules = [
        _ws(id="ws-new", planned_date="2026-11-01"),
        _ws(id="ws-old", planned_date="2026-12-01"),
    ]
    out = LE.run_generate_operation_schedules("f1", sb2)
    assert out["created"] == 0
    assert out["stale_preserved"] == 1
    assert out["stale_inactivated"] == 0
    assert next(r for r in sb2.work_schedules if r["id"] == "ws-old")["active_yn"] is True


def test_P11_latest_insert_verify_failure_stale_remains_active(freeze_today):
    sb = _SB()
    rule = _within(basis="2026-10-01", value=1, unit="month")
    sb.inspection_sets = [_iset(operation_time_rule=rule)]
    sb.work_schedules = [_ws(id="ws-old", planned_date="2026-12-01")]
    sb.block_upsert = True
    out = LE.run_generate_operation_schedules("f1", sb)
    assert out["created"] == 0
    assert out["latest_not_secured"] == 1
    assert out["stale_inactivated"] == 0
    assert next(r for r in sb.work_schedules if r["id"] == "ws-old")["active_yn"] is True


def test_P12_latest_reactivation_failure_stale_remains_active(freeze_today):
    sb = _SB()
    rule = _within(basis="2026-10-01", value=1, unit="month")
    sb.inspection_sets = [_iset(operation_time_rule=rule)]
    sb.work_schedules = [
        _ws(id="ws-exact", planned_date="2026-11-01", active_yn=False),
        _ws(id="ws-old", planned_date="2026-12-01"),
    ]
    sb.fail_update_ids.add("ws-exact")
    try:
        LE.run_generate_operation_schedules("f1", sb)
        raised = False
    except RuntimeError:
        raised = True
    assert raised is True
    assert next(r for r in sb.work_schedules if r["id"] == "ws-old")["active_yn"] is True
    assert next(r for r in sb.work_schedules if r["id"] == "ws-exact")["active_yn"] is False


def test_P13_partial_stale_update_failure_latest_remains(freeze_today):
    sb = _SB()
    rule = _within(basis="2026-10-01", value=1, unit="month")
    sb.inspection_sets = [_iset(operation_time_rule=rule)]
    sb.work_schedules = [
        _ws(id="ws-new", planned_date="2026-11-01"),
        _ws(id="ws-old-a", planned_date="2026-12-01"),
        _ws(id="ws-old-b", planned_date="2026-12-15"),
    ]
    sb.fail_update_ids.add("ws-old-a")
    try:
        LE.run_generate_operation_schedules("f1", sb)
        raised = False
    except RuntimeError:
        raised = True
    assert raised is True
    latest = next(r for r in sb.work_schedules if r["id"] == "ws-new")
    assert latest["active_yn"] is True


def test_P15_completed_stale_preserve(freeze_today):
    sb = _SB()
    rule = _within(basis="2026-10-01", value=1, unit="month")
    sb.inspection_sets = [_iset(operation_time_rule=rule)]
    sb.work_schedules = [
        _ws(id="ws-new", planned_date="2026-11-01"),
        _ws(id="ws-done", planned_date="2026-12-01", status_code="completed"),
    ]
    out = LE.run_generate_operation_schedules("f1", sb)
    assert out["stale_inactivated"] == 0
    assert next(r for r in sb.work_schedules if r["id"] == "ws-done")["active_yn"] is True


def test_P16_in_progress_stale_preserve(freeze_today):
    sb = _SB()
    rule = _within(basis="2026-10-01", value=1, unit="month")
    sb.inspection_sets = [_iset(operation_time_rule=rule)]
    sb.work_schedules = [
        _ws(id="ws-new", planned_date="2026-11-01"),
        _ws(id="ws-ip", planned_date="2026-12-01", status_code="in_progress"),
    ]
    out = LE.run_generate_operation_schedules("f1", sb)
    assert out["stale_inactivated"] == 0
    assert next(r for r in sb.work_schedules if r["id"] == "ws-ip")["active_yn"] is True


def test_P17_unknown_stale_preserve(freeze_today):
    sb = _SB()
    rule = _within(basis="2026-10-01", value=1, unit="month")
    sb.inspection_sets = [_iset(operation_time_rule=rule)]
    sb.work_schedules = [
        _ws(id="ws-new", planned_date="2026-11-01"),
        _ws(id="ws-unk", planned_date="2026-12-01", status_code="unknown_status"),
    ]
    out = LE.run_generate_operation_schedules("f1", sb)
    assert out["stale_inactivated"] == 0
    assert next(r for r in sb.work_schedules if r["id"] == "ws-unk")["active_yn"] is True


def test_P18_non_legal_exact_no_takeover_stale_zero(freeze_today):
    sb = _SB()
    rule = _within(basis="2026-10-01", value=1, unit="month")
    sb.inspection_sets = [_iset(operation_time_rule=rule)]
    sb.work_schedules = [
        _ws(id="ws-man", planned_date="2026-11-01", source_type="MANUAL"),
        _ws(id="ws-old", planned_date="2026-12-01"),
    ]
    out = LE.run_generate_operation_schedules("f1", sb)
    assert out["created"] == 0
    assert out["latest_not_secured"] == 1
    assert out["stale_inactivated"] == 0
    assert next(r for r in sb.work_schedules if r["id"] == "ws-old")["active_yn"] is True


def test_P19_force_true_legal_anchor_delete_0(freeze_today, monkeypatch):
    sb = _SB()
    sb.inspection_sets = [
        _iset(
            id="leg-1",
            source="LEGAL_ENGINE",
            schedule_anchor_date="2026-01-01",
            cycle_unit="month",
            cycle_value=1,
            assignee_user_id="user-1",
            operation_time_rule=None,
            anchor_confirmed=True,
        ),
    ]
    for r in sb.inspection_sets:
        r["anchor_confirmed"] = True
        r["is_active"] = True
    monkeypatch.setattr(S, "get_supabase", lambda: sb)
    out = S.generate_schedules_for_factory("f1", "anchor", True)
    assert sb.delete_ops == 0
    assert sb.deletes == []
    assert out["data"]["created"] == 0


def test_P20_static_guards_stage2(freeze_today):
    src = inspect.getsource(LE)
    assert ".delete(" not in src
    assert "def _delete_stale" not in src
    assert "def _converge_payload" not in src
    react = inspect.getsource(LE._reactivate_exact)
    assert '{"active_yn": True}' in react
    assert "planned_date" not in react
    assert "start_date" not in react
    assert "end_date" not in react
    inac = inspect.getsource(LE._inactivate_stale)
    assert '{"active_yn": False}' in inac
    assert "planned_date" not in inac
    assert "start_date" not in inac
    assert "end_date" not in inac
    assert "status_code" not in inac
