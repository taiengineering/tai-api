"""WO-SAAS-OPERATION-CYCLE-SETTER-001 STEP 4B-4D-A — set_operation_cycle 계약 고정.

canonical row 에만 cycle_unit/value 기록, 일정 시작 시 409, legacy/MANUAL 거부, unit/value 검증,
성공 시 cycle 외 컬럼 무변경. supabase mock. DB/network 불필요.
"""
from __future__ import annotations

import pytest

from schemas.inspection_sets import OperationCycleBody
from services.inspection_sets_svc.errors import InspectionSetsSvcError
from services.inspection_sets_svc.operation_cycle import (
    ALLOWED_CYCLE_UNITS,
    set_operation_cycle,
)


def _canon(**over):
    r = {
        "id": "set-1",
        "source": "LEGAL_ENGINE",
        "legal_obligation_atom_id": "atom-A",
        "schedule_anchor_date": None,
        "next_planned_date": None,
        "anchor_confirmed": False,
    }
    r.update(over)
    return r


class _Q:
    def __init__(self, sb):
        self.sb = sb; self._op = "select"; self._payload = None

    def select(self, *a, **k): self._op = "select"; return self
    def eq(self, *a, **k): return self
    def limit(self, n): return self
    def update(self, patch): self._op = "update"; self._payload = patch; return self

    def execute(self):
        class R: pass
        r = R()
        if self._op == "update":
            self.sb.updates.append(self._payload)
            r.data = [] if self.sb.update_fail else [{"id": "set-1", **self._payload}]
        else:
            r.data = [dict(self.sb.row)] if self.sb.row is not None else []
        return r


class _SB:
    def __init__(self, row, update_fail=False):
        self.row = row; self.update_fail = update_fail; self.updates = []
    def table(self, name):
        assert name == "inspection_sets"; return _Q(self)


def _run(monkeypatch, row, unit="year", value=1, update_fail=False):
    import services.inspection_sets_svc.operation_cycle as M
    sb = _SB(row, update_fail=update_fail)
    monkeypatch.setattr(M, "get_supabase", lambda: sb)
    out = set_operation_cycle("set-1", OperationCycleBody(cycle_unit=unit, cycle_value=value))
    return out, sb


# ── 성공 (canonical + no anchor) ──
def test_canonical_year_1_pass(monkeypatch):
    out, sb = _run(monkeypatch, _canon(), "year", 1)
    assert out["status"] == "success"
    assert sb.updates == [{"cycle_unit": "year", "cycle_value": 1}]   # cycle 만


def test_canonical_quarter_2_pass(monkeypatch):
    out, sb = _run(monkeypatch, _canon(), "quarter", 2)
    assert out["data"] == {"inspection_set_id": "set-1", "cycle_unit": "quarter", "cycle_value": 2}
    assert sb.updates[0] == {"cycle_unit": "quarter", "cycle_value": 2}


def test_all_six_units_pass(monkeypatch):
    for u in ("day", "week", "month", "quarter", "half_year", "year"):
        out, sb = _run(monkeypatch, _canon(), u, 3)
        assert out["data"]["cycle_unit"] == u and out["data"]["cycle_value"] == 3
    assert ALLOWED_CYCLE_UNITS == {"day", "week", "month", "quarter", "half_year", "year"}


def test_unit_case_insensitive(monkeypatch):
    out, sb = _run(monkeypatch, _canon(), "YEAR", 1)
    assert sb.updates[0]["cycle_unit"] == "year"


# ── value/unit 검증 (422) ──
def test_value_zero_negative_422(monkeypatch):
    for v in (0, -1, -5):
        with pytest.raises(InspectionSetsSvcError) as ei:
            _run(monkeypatch, _canon(), "year", v)
        assert ei.value.status_code == 422


def test_value_non_int_422(monkeypatch):
    import services.inspection_sets_svc.operation_cycle as M
    sb = _SB(_canon()); monkeypatch.setattr(M, "get_supabase", lambda: sb)
    # bool 은 int 서브클래스 → 명시 거부
    with pytest.raises(InspectionSetsSvcError) as ei:
        set_operation_cycle("set-1", OperationCycleBody(cycle_unit="year", cycle_value=True))
    assert ei.value.status_code == 422
    assert sb.updates == []


def test_bad_unit_422(monkeypatch):
    for u in ("years", "d", "biweekly", ""):
        with pytest.raises(InspectionSetsSvcError) as ei:
            _run(monkeypatch, _canon(), u, 1)
        assert ei.value.status_code == 422


# ── 대상 거부 ──
def test_legacy_atom_null_rejected(monkeypatch):
    with pytest.raises(InspectionSetsSvcError) as ei:
        _run(monkeypatch, _canon(legal_obligation_atom_id=None))
    assert ei.value.status_code == 409


def test_manual_source_rejected(monkeypatch):
    with pytest.raises(InspectionSetsSvcError) as ei:
        _run(monkeypatch, _canon(source="MANUAL"))
    assert ei.value.status_code == 409


def test_not_found_404(monkeypatch):
    with pytest.raises(InspectionSetsSvcError) as ei:
        _run(monkeypatch, None)
    assert ei.value.status_code == 404


# ── 일정 시작 가드 (409) ──
def test_schedule_anchor_present_409(monkeypatch):
    with pytest.raises(InspectionSetsSvcError) as ei:
        _run(monkeypatch, _canon(schedule_anchor_date="2026-01-01"))
    assert ei.value.status_code == 409


def test_next_planned_present_409(monkeypatch):
    with pytest.raises(InspectionSetsSvcError) as ei:
        _run(monkeypatch, _canon(next_planned_date="2026-02-01"))
    assert ei.value.status_code == 409


def test_anchor_confirmed_true_409(monkeypatch):
    with pytest.raises(InspectionSetsSvcError) as ei:
        _run(monkeypatch, _canon(anchor_confirmed=True))
    assert ei.value.status_code == 409


def test_guard_blocks_update(monkeypatch):
    import services.inspection_sets_svc.operation_cycle as M
    sb = _SB(_canon(anchor_confirmed=True)); monkeypatch.setattr(M, "get_supabase", lambda: sb)
    with pytest.raises(InspectionSetsSvcError):
        set_operation_cycle("set-1", OperationCycleBody(cycle_unit="year", cycle_value=1))
    assert sb.updates == []   # write 0


# ── 성공 시 cycle 외 컬럼 무변경 ──
def test_only_cycle_written(monkeypatch):
    out, sb = _run(monkeypatch, _canon(), "month", 6)
    patch = sb.updates[0]
    assert set(patch.keys()) == {"cycle_unit", "cycle_value"}
    for banned in ("status_code", "anchor_confirmed", "schedule_anchor_date",
                   "next_planned_date", "last_inspection_date"):
        assert banned not in patch


def test_update_failure_500(monkeypatch):
    with pytest.raises(InspectionSetsSvcError) as ei:
        _run(monkeypatch, _canon(), "year", 1, update_fail=True)
    assert ei.value.status_code == 500


# ── 정적 경계: schedules/anchors/canonical_writer 미참조 ──
def test_static_no_schedule_side_effects():
    import inspect
    import services.inspection_sets_svc.operation_cycle as M
    src = inspect.getsource(M)
    for banned in ("work_schedules", "generate_schedules", "_build_next_schedule_row",
                   "canonical_writer", "DELTA_MAP", "relativedelta"):
        assert banned not in src
