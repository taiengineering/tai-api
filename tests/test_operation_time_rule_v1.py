"""WO-SAFE-OPERATION-TIME-BACKEND-V1-001 / PATCH-R1 focused tests.

Run: pytest tests/test_operation_time_rule_v1.py -q
"""
from __future__ import annotations

import inspect
from datetime import date
from pathlib import Path

import pytest

from schemas.inspection_sets import OperationTimeRuleBody
from services.inspection_sets_helpers import _build_next_schedule_row
from services.inspection_sets_svc import operation_time_rule as OTR
from services.inspection_sets_svc.canonical_writer import _REFRESH_FIELDS
from services.inspection_sets_svc.errors import InspectionSetsSvcError


# ── Fake Supabase ──

class _Table:
    def __init__(self, sb, name):
        self.sb = sb
        self.name = name
        self._filters = {}
        self._payload = None
        self._op = "select"

    def select(self, *_a, **_k):
        self._op = "select"
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def insert(self, row):
        self._op = "insert"
        self._payload = row
        return self

    def eq(self, k, v):
        self._filters[k] = v
        return self

    def limit(self, _n):
        return self

    def execute(self):
        if self.name == "inspection_sets":
            if self._op == "select":
                rows = [r for r in self.sb.sets if all(r.get(k) == v for k, v in self._filters.items())]
                return type("R", (), {"data": rows})()
            if self._op == "update":
                for r in self.sb.sets:
                    if self._filters.get("id") and r.get("id") != self._filters["id"]:
                        continue
                    if self._filters.get("source") and r.get("source") != self._filters["source"]:
                        continue
                    if self._filters.get("id") == r.get("id"):
                        r.update(self._payload)
                        self.sb.updates.append(dict(self._payload))
                        return type("R", (), {"data": [r]})()
                return type("R", (), {"data": []})()
        if self.name == "work_schedules":
            self.sb.schedule_touched = True
            if self._op == "select":
                hits = [
                    s for s in self.sb.schedules
                    if all(s.get(k) == v for k, v in self._filters.items())
                ]
                return type("R", (), {"data": hits})()
            if self._op == "insert":
                self.sb.schedules.append(dict(self._payload))
                self.sb.schedule_inserts.append(dict(self._payload))
                return type("R", (), {"data": [self._payload]})()
        return type("R", (), {"data": []})()


class _SB:
    def __init__(self, sets):
        self.sets = sets
        self.schedules = []
        self.schedule_inserts = []
        self.schedule_touched = False
        self.updates = []

    def table(self, name):
        return _Table(self, name)


def _legal_row(**kw):
    base = {
        "id": "set-1",
        "factory_id": "f1",
        "company_id": "c1",
        "source": "LEGAL_ENGINE",
        "legal_obligation_atom_id": "atom-1",
        "assignee_user_id": "user-1",
        "cycle_unit": None,
        "cycle_value": None,
        "schedule_anchor_date": None,
        "last_inspection_date": None,
        "next_planned_date": None,
        "anchor_confirmed": False,
        "status_code": "PENDING_ANCHOR",
        "inspection_set_name": "경보설비",
        "inspection_category": "ACTION",
        "holiday_process_type": None,
        "operation_time_rule": None,
    }
    base.update(kw)
    return base


def _install(monkeypatch, sb):
    monkeypatch.setattr(OTR, "get_supabase", lambda: sb)


# ── T1 migration file ──

def test_T1_migration_additive():
    p = Path("docs/sql/20260911_inspection_sets_operation_time_rule.sql")
    text = p.read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS operation_time_rule jsonb NULL" in text
    assert "NOT NULL" not in text.split("operation_time_rule")[1].split(";")[0] or "jsonb NULL" in text
    assert "cycle_unit" not in text or "DROP" not in text


# ── CURRENT EVERY recurrence regression (builder unmodified by this PR) ──

def test_T5_every_schedule_regression_builder():
    iset = _legal_row(cycle_unit="month", cycle_value=1)
    row, planned = _build_next_schedule_row(iset, date(2026, 1, 15))
    assert row["repeat_type"] == "monthly"
    assert row["assigned_user_id"] == "user-1"
    assert planned >= date(2026, 2, 15) or planned == date(2026, 2, 15)


# ── normalize / readiness ──

def test_T3_every_normalize():
    body = OperationTimeRuleBody(
        version="v1", source="USER_EDITED", operator="EVERY",
        value=2, unit="week", basis_date="2026-01-15",
    )
    rule = OTR.normalize_operation_time_rule(body)
    assert rule == {
        "version": "v1", "source": "USER_EDITED", "operator": "EVERY",
        "value": 2, "unit": "week", "basis_date": "2026-01-15",
    }


def test_until_feb31_422():
    body = OperationTimeRuleBody(
        version="v1", source="LEGAL_DEFAULT", operator="UNTIL", month=2, day=31,
    )
    with pytest.raises(InspectionSetsSvcError) as ei:
        OTR.normalize_operation_time_rule(body)
    assert ei.value.status_code == 422


def test_T11_before_without_offset_not_ready():
    rule = {"version": "v1", "source": "USER_EDITED", "operator": "BEFORE", "basis_date": "2026-10-10"}
    assert OTR.is_operation_time_ready(rule, "user-1") is False


def test_T14_until_not_ready_even_with_assignee():
    rule = {"version": "v1", "source": "LEGAL_DEFAULT", "operator": "UNTIL", "month": 12, "day": 31}
    assert OTR.is_operation_time_ready(rule, "user-1") is False


@pytest.mark.parametrize(
    "bad",
    [
        "2026-09-11T10:00",
        "2026-09-11abc",
        "2026/09/11",
        "2026-02-30",
        "11-09-2026",
    ],
)
def test_D18_exact_date_validation_422(bad):
    body = OperationTimeRuleBody(
        version="v1", source="USER_EDITED", operator="EVERY",
        value=1, unit="month", basis_date=bad,
    )
    with pytest.raises(InspectionSetsSvcError) as ei:
        OTR.normalize_operation_time_rule(body)
    assert ei.value.status_code == 422


def test_D18_exact_date_pass():
    body = OperationTimeRuleBody(
        version="v1", source="USER_EDITED", operator="EVERY",
        value=1, unit="month", basis_date="2026-09-11",
    )
    rule = OTR.normalize_operation_time_rule(body)
    assert rule["basis_date"] == "2026-09-11"


# ── service persist (save-only) ──

def test_D1_save_writes_zero_schedules(monkeypatch):
    sb = _SB([_legal_row()])
    _install(monkeypatch, sb)
    body = OperationTimeRuleBody(
        version="v1", source="USER_EDITED", operator="EVERY",
        value=1, unit="month", basis_date="2026-01-15",
    )
    out = OTR.set_operation_time_rule("set-1", body)
    assert "schedule_created" not in out["data"]
    assert sb.schedule_inserts == []
    assert sb.schedule_touched is False
    src = inspect.getsource(OTR.set_operation_time_rule)
    assert ".table(\"work_schedules\")" not in src
    assert "insert(" not in src


def test_D2_rule_mutable_after_prior_schedule(monkeypatch):
    sb = _SB([
        _legal_row(
            schedule_anchor_date="2026-01-01",
            next_planned_date="2026-02-01",
            anchor_confirmed=True,
            cycle_unit="month",
            cycle_value=1,
        )
    ])
    sb.schedules.append({
        "id": "ws1", "inspection_set_id": "set-1",
        "planned_date": "2026-02-01", "factory_id": "f1", "status_code": "planned",
    })
    _install(monkeypatch, sb)
    body = OperationTimeRuleBody(
        version="v1", source="USER_EDITED", operator="EVERY",
        value=2, unit="week", basis_date="2026-01-15",
    )
    out = OTR.set_operation_time_rule("set-1", body)
    assert out["data"]["operation_time_rule"]["value"] == 2
    assert out["data"]["operation_time_rule"]["unit"] == "week"
    assert sb.sets[0]["cycle_unit"] == "week"
    assert sb.sets[0]["cycle_value"] == 2
    assert sb.schedule_inserts == []
    assert sb.schedule_touched is False


def test_T3_T4_every_save_projection(monkeypatch):
    sb = _SB([_legal_row()])
    _install(monkeypatch, sb)
    body = OperationTimeRuleBody(
        version="v1", source="USER_EDITED", operator="EVERY",
        value=2, unit="week", basis_date="2026-01-15",
    )
    out = OTR.set_operation_time_rule("set-1", body)
    assert out["data"]["operation_time_rule"]["operator"] == "EVERY"
    assert sb.sets[0]["cycle_unit"] == "week"
    assert sb.sets[0]["cycle_value"] == 2
    assert sb.sets[0]["operation_time_rule"]["value"] == 2
    assert sb.schedule_inserts == []


def test_T6_T7_within_persist_no_fake_cycle(monkeypatch):
    sb = _SB([_legal_row(cycle_unit="month", cycle_value=1)])
    _install(monkeypatch, sb)
    body = OperationTimeRuleBody(
        version="v1", source="USER_EDITED", operator="WITHIN",
        value=1, unit="month", basis_date="2026-01-10",
        basis_text="선임인원 교체",
    )
    out = OTR.set_operation_time_rule("set-1", body)
    assert out["data"]["operation_time_rule"]["operator"] == "WITHIN"
    assert sb.sets[0]["cycle_unit"] is None
    assert sb.sets[0]["cycle_value"] is None
    assert sb.sets[0]["last_inspection_date"] is None
    assert sb.schedule_inserts == []


def test_D5_within_save_only_no_oneshot_insert(monkeypatch):
    sb = _SB([_legal_row()])
    _install(monkeypatch, sb)
    body = OperationTimeRuleBody(
        version="v1", source="USER_EDITED", operator="WITHIN",
        value=1, unit="month", basis_date="2026-01-10",
    )
    out = OTR.set_operation_time_rule("set-1", body)
    assert out["data"]["readiness"] is True
    assert sb.schedule_inserts == []
    assert sb.sets[0]["last_inspection_date"] is None


def test_D6_before_save_with_offset_no_insert(monkeypatch):
    sb = _SB([_legal_row()])
    _install(monkeypatch, sb)
    body = OperationTimeRuleBody(
        version="v1", source="USER_EDITED", operator="BEFORE",
        value=3, unit="day", basis_date="2026-10-10",
        basis_text="작업 시작",
    )
    out = OTR.set_operation_time_rule("set-1", body)
    assert out["data"]["readiness"] is True
    assert sb.schedule_inserts == []


def test_D7_before_draft_persist_not_ready(monkeypatch):
    sb = _SB([_legal_row()])
    _install(monkeypatch, sb)
    body = OperationTimeRuleBody(
        version="v1", source="USER_EDITED", operator="BEFORE",
        basis_date="2026-10-10",
    )
    out = OTR.set_operation_time_rule("set-1", body)
    assert out["data"]["readiness"] is False
    assert sb.schedule_inserts == []


def test_D8_T13_T15_until_persist_schedule_0(monkeypatch):
    sb = _SB([_legal_row()])
    _install(monkeypatch, sb)
    body = OperationTimeRuleBody(
        version="v1", source="LEGAL_DEFAULT", operator="UNTIL",
        month=12, day=31,
    )
    out = OTR.set_operation_time_rule("set-1", body)
    assert out["data"]["operation_time_rule"]["month"] == 12
    assert out["data"]["readiness"] is False
    assert "yearly" not in str(out["data"]["operation_time_rule"]).lower()
    assert sb.schedule_inserts == []


def test_D17_assignee_missing_still_persists(monkeypatch):
    sb = _SB([_legal_row(assignee_user_id=None)])
    _install(monkeypatch, sb)
    body = OperationTimeRuleBody(
        version="v1", source="USER_EDITED", operator="EVERY",
        value=1, unit="month", basis_date="2026-01-15",
    )
    out = OTR.set_operation_time_rule("set-1", body)
    assert out["data"]["readiness"] is False
    assert sb.sets[0]["operation_time_rule"]["operator"] == "EVERY"
    assert sb.schedule_inserts == []


def test_no_create_schedule_field_on_schema():
    fields = OperationTimeRuleBody.model_fields
    assert "create_schedule" not in fields


def test_T19_legal_actor_unused_in_module():
    blob = inspect.getsource(OTR)
    assert "legal_actor" not in blob


def test_T20_rediagnosis_preserves_operation_time_rule():
    assert "operation_time_rule" not in _REFRESH_FIELDS


def test_T21_legal_snapshot_fields_only():
    assert set(_REFRESH_FIELDS) == {
        "law_name", "law_article", "obligation_type",
        "obligation_summary", "description", "legal_operation_presentation",
    }


def test_no_schedule_start_lock_in_module():
    blob = inspect.getsource(OTR.set_operation_time_rule)
    assert "이미 일정이" not in blob
    assert "변경할 수 없습니다" not in blob
    assert "schedule-start" not in blob.lower()
    # never gates on existing schedule columns
    assert "if iset.get(\"schedule_anchor_date\")" not in blob
    assert "if iset.get(\"next_planned_date\")" not in blob
    assert "if iset.get(\"anchor_confirmed\")" not in blob


def test_T23_T26_no_legal_type_auto_in_service():
    blob = inspect.getsource(OTR)
    assert "CONTINUOUS" not in blob
    assert "IMMEDIATE" not in blob
    assert "RAW_ONLY" not in blob
    assert "ONE_TIME" not in blob


def test_endpoint_choice_dedicated_route():
    import routers.inspection_sets as R
    src = inspect.getsource(R)
    assert 'operation-time-rule"' in src or "operation-time-rule" in src
    assert "cycle_unit/value" in src or "운영주기" in src


def test_queries_select_includes_operation_time_rule():
    import services.inspection_sets_svc.queries as Q
    assert "operation_time_rule" in inspect.getsource(Q.get_sets_list)
