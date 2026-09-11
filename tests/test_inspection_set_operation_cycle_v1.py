"""WO-SAAS-OPERATION-CYCLE-SETTER-001 STEP 4B-4D-A (+PATCH-1) — set_operation_cycle 계약.

canonical row 에만 cycle_unit/value, 일정 시작 시 409(TOCTOU 포함), legacy/MANUAL 거부, strict int,
성공 시 cycle 외 컬럼 무변경. supabase mock. DB/network 불필요.

PATCH-1: schema strict int(P1~P3) + conditional atomic UPDATE 0행 → 409(P4~P5) + eligible 1행(P6).
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

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
    """inspection_sets query mock. update 는 조건필터를 수집해 sb.update_eligible 로 0/1행 결정."""
    def __init__(self, sb):
        self.sb = sb; self._op = "select"; self._payload = None
        self._eq = {}; self._isnull = set(); self._notnull = set(); self._not = False

    def select(self, *a, **k): self._op = "select"; return self
    def update(self, patch): self._op = "update"; self._payload = patch; return self
    def eq(self, c, v): self._eq[c] = v; return self

    @property
    def not_(self): self._not = True; return self

    def is_(self, c, v):
        if self._not:
            self._notnull.add(c); self._not = False
        else:
            self._isnull.add(c)
        return self

    def limit(self, n): return self

    def execute(self):
        class R: pass
        r = R()
        if self._op == "update":
            self.sb.updates.append(self._payload)
            # conditional atomic update: sb.update_eligible False 면 0행(그 사이 상태 변경 모사)
            r.data = [{"id": "set-1", **self._payload}] if self.sb.update_eligible else []
        else:
            r.data = [dict(self.sb.row)] if self.sb.row is not None else []
        return r


class _SB:
    def __init__(self, row, update_eligible=True):
        self.row = row; self.update_eligible = update_eligible; self.updates = []
    def table(self, name):
        assert name == "inspection_sets"; return _Q(self)


def _run(monkeypatch, row, unit="year", value=1, update_eligible=True):
    import services.inspection_sets_svc.operation_cycle as M
    sb = _SB(row, update_eligible=update_eligible)
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


def test_all_six_units_pass(monkeypatch):
    for u in ("day", "week", "month", "quarter", "half_year", "year"):
        out, sb = _run(monkeypatch, _canon(), u, 3)
        assert out["data"]["cycle_unit"] == u and out["data"]["cycle_value"] == 3
    assert ALLOWED_CYCLE_UNITS == {"day", "week", "month", "quarter", "half_year", "year"}


def test_unit_case_insensitive(monkeypatch):
    out, sb = _run(monkeypatch, _canon(), "YEAR", 1)
    assert sb.updates[0]["cycle_unit"] == "year"


# ── PATCH-1A: strict int (schema 단계 실패) ──
def test_P1_bool_rejected_by_schema():
    # true/false → schema ValidationError (service 도달 전)
    with pytest.raises(ValidationError):
        OperationCycleBody(cycle_unit="year", cycle_value=True)
    with pytest.raises(ValidationError):
        OperationCycleBody(cycle_unit="year", cycle_value=False)


def test_P2_str_rejected_by_schema():
    with pytest.raises(ValidationError):
        OperationCycleBody(cycle_unit="year", cycle_value="1")


def test_P3_float_rejected_by_schema():
    with pytest.raises(ValidationError):
        OperationCycleBody(cycle_unit="year", cycle_value=1.0)


def test_P_zero_negative_rejected_by_schema():
    for v in (0, -1, -5):
        with pytest.raises(ValidationError):
            OperationCycleBody(cycle_unit="year", cycle_value=v)


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


# ── 선 SELECT guard (409) ──
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


# ── PATCH-1B: conditional atomic UPDATE TOCTOU (P4~P6) ──
def test_P4_toctou_anchor_appeared_409(monkeypatch):
    # SELECT 시 eligible → UPDATE 직전 anchor 생김(update_eligible=False) → 0행 → 409
    with pytest.raises(InspectionSetsSvcError) as ei:
        _run(monkeypatch, _canon(), "year", 1, update_eligible=False)
    assert ei.value.status_code == 409


def test_P5_toctou_next_planned_appeared_409(monkeypatch):
    with pytest.raises(InspectionSetsSvcError) as ei:
        _run(monkeypatch, _canon(), "month", 3, update_eligible=False)
    assert ei.value.status_code == 409


def test_P6_eligible_conditional_update_writes_cycle_only(monkeypatch):
    out, sb = _run(monkeypatch, _canon(), "month", 6, update_eligible=True)
    patch = sb.updates[0]
    assert out["status"] == "success"
    assert set(patch.keys()) == {"cycle_unit", "cycle_value"}
    for banned in ("status_code", "anchor_confirmed", "schedule_anchor_date",
                   "next_planned_date", "last_inspection_date"):
        assert banned not in patch


# ── 정적 경계: schedules/anchors/canonical_writer 미참조 ──
def test_static_no_schedule_side_effects():
    import inspect
    import services.inspection_sets_svc.operation_cycle as M
    # Module docstring may mention write-0 boundaries; assert against executable body only.
    body = inspect.getsource(M.set_operation_cycle)
    for banned in ("work_schedules", "generate_schedules", "_build_next_schedule_row",
                   "canonical_writer", "DELTA_MAP", "relativedelta"):
        assert banned not in body
    # Top-level imports / constants must also stay schedule-free.
    mod_src = inspect.getsource(M)
    assert "from services.inspection_sets_helpers" not in mod_src
    assert "import relativedelta" not in mod_src
    assert "canonical_writer" not in mod_src
    assert "generate_schedules" not in mod_src
    assert "table(\"work_schedules\")" not in mod_src
    assert "table('work_schedules')" not in mod_src
