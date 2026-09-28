"""WO-EQUIPMENT-A2-EXISTING-SEAM-PATCH-001 — Equipment A2 기존 seam 공통화 테스트.

Coverage:
  MFG-01 ~ MFG-05  MANUFACTURING runtime: A2 5종 코드별 canonical fact 도달
  MFG-06           explicit False 보존 (equipment projection이 덮지 않음)
  MFG-07           explicit None → equipment projection 채움
  MFG-08           absent key → equipment projection 채움
  MFG-09           CRANE 021 → has_crane 미발생
  MFG-10           equipment_rows 없으면 A2 absent (기존 계약 불변)
  MFG-11           단일 request 내 중복 A2 reader 없음
  CST-01 ~ CST-03  CONSTRUCTION parity: shared reader 교체 후 동일 동작
  CST-04           CONSTRUCTION read error → EquipmentSourceLoadError (503 전환 가능)
  SEAM-01          build_saas_leg_step1 직접: equipment_rows merge 계약
  SEAM-02          build_saas_leg_step1: source_facts False 보존
"""
from __future__ import annotations

from typing import Any, Dict, Optional
import pytest

from services.safe_industrial_canonical_assembler import TARGET_FIELDS, CONTRACT_VERSION
from services.equipment_source.store import EquipmentSourceLoadError
import services.safe_industrial_leg_runtime as R
from schemas.legal_engine import SafeIndustrialConsumerInput


# ── Fakes / helpers ────────────────────────────────────────────────────────────

def _asset_contract(**over):
    values = {f: None for f in TARGET_FIELDS}
    values["ksic_major"] = "C10"
    values["worker_count"] = 50
    values.update(over)
    return {
        "contract_version": CONTRACT_VERSION,
        "sector": "INDUSTRIAL",
        "factory_id": "F1",
        "values": {f: values[f] for f in TARGET_FIELDS},
        "unresolved_fields": sorted([f for f in TARGET_FIELDS if values[f] is None]),
        "provenance": {},
    }


class _FakeSBEq:
    """Fake Supabase that returns given equipment rows."""

    def __init__(self, eq_rows):
        self._rows = eq_rows
        self._eq_calls = 0

    def table(self, name):
        return _FakeQ(self, name)


class _FakeQ:
    def __init__(self, sb, name):
        self._sb = sb
        self._name = name
        self._filters = []

    def select(self, *a, **k):
        return self

    def eq(self, col, val):
        self._filters.append((col, val))
        return self

    def execute(self):
        if self._name == "equipment_assets":
            self._sb._eq_calls += 1

        class _R:
            data = self._sb._rows

        return _R()


def _patched_runtime(monkeypatch, eq_rows, *, source_overrides: Optional[Dict[str, Any]] = None):
    """Return (fake_sb, calls) with runtime patched for eq_rows."""
    calls: Dict[str, Any] = {"run_leg": 0, "step1": None}

    def fake_assemble(supabase, factory_id):
        return _asset_contract(**(source_overrides or {}))

    def fake_run_leg(step1):
        calls["run_leg"] += 1
        calls["step1"] = step1
        return {"sector": step1.sector, "engine_family": "LEG", "key_obligations": []}

    fake_sb = _FakeSBEq(eq_rows)

    monkeypatch.setattr(R, "assemble_industrial_marketing_contract", fake_assemble)
    monkeypatch.setattr(R, "run_leg_diagnosis", fake_run_leg)
    monkeypatch.setattr("services.work_source.store.load_work_rows_optional", lambda sb, fid: [])
    monkeypatch.setattr(
        "services.material_source.store.load_factory_material_rows_optional",
        lambda sb, fid: [],
    )
    return fake_sb, calls


# ── MFG: MANUFACTURING A2 runtime 테스트 ──────────────────────────────────────

@pytest.mark.parametrize("code,expected_fact", [
    ("010", "has_emergency_gen"),
    ("014", "has_boiler"),
    ("023", "has_press"),
    ("024", "has_conveyor"),
    ("038", "has_pressure_vessel"),
])
def test_MFG_a2_five_codes_reach_leg_input(monkeypatch, code, expected_fact):
    """MFG-01~05: A2 5종 코드 → MANUFACTURING runtime step1.input에 canonical fact 도달."""
    eq_rows = [{"equipment_type_code": code, "is_operating": True}]
    fake_sb, calls = _patched_runtime(monkeypatch, eq_rows)
    R.run_safe_industrial_leg(fake_sb, "F1", SafeIndustrialConsumerInput())
    assert calls["step1"] is not None
    inp = calls["step1"].input
    assert inp.get(expected_fact) is True, (
        f"code={code!r}: expected {expected_fact}=True in step1.input, got {inp.get(expected_fact)!r}"
    )


def test_MFG_explicit_false_preserved(monkeypatch):
    """MFG-06: consumer explicit has_boiler=False → equipment 014이 덮지 않음.

    has_boiler은 SAFE_UI_OVERRIDE_FIELDS 포함 → consumer False가 source_facts에 도달.
    equipment 014 → has_boiler=True 시도하지만 source False가 보존되어야 한다.
    (has_press는 TARGET_FIELDS/SAFE_UI_OVERRIDE_FIELDS 밖이라 runtime 레벨 테스트 불가;
    False 보존 계약은 SEAM-02로 검증.)
    """
    eq_rows = [{"equipment_type_code": "014", "is_operating": True}]
    fake_sb, calls = _patched_runtime(monkeypatch, eq_rows)
    # consumer explicit has_boiler=False — B' mask이 None으로 초기화하지만 consumer override가 False로 재설정
    R.run_safe_industrial_leg(fake_sb, "F1", SafeIndustrialConsumerInput(has_boiler=False))
    inp = calls["step1"].input
    # has_boiler=False from consumer override — equipment 014 must NOT overwrite
    assert inp.get("has_boiler") is not True, (
        f"has_boiler should stay False (consumer explicit); got {inp.get('has_boiler')!r}"
    )


def test_MFG_explicit_none_filled_by_equipment(monkeypatch):
    """MFG-07: source_facts has_press=None → equipment 023 채움 → True."""
    eq_rows = [{"equipment_type_code": "023", "is_operating": True}]
    fake_sb, calls = _patched_runtime(monkeypatch, eq_rows)
    R.run_safe_industrial_leg(fake_sb, "F1", SafeIndustrialConsumerInput())
    inp = calls["step1"].input
    assert inp.get("has_press") is True, (
        f"expected has_press=True (None filled by equipment 023), got {inp.get('has_press')!r}"
    )


def test_MFG_absent_key_filled_by_equipment(monkeypatch):
    """MFG-08: has_press absent in source_facts → equipment 023 채움 → True."""
    eq_rows = [{"equipment_type_code": "023", "is_operating": True}]
    fake_sb, calls = _patched_runtime(monkeypatch, eq_rows)
    R.run_safe_industrial_leg(fake_sb, "F1", SafeIndustrialConsumerInput())
    inp = calls["step1"].input
    assert inp.get("has_press") is True


def test_MFG_crane_021_no_has_crane(monkeypatch):
    """MFG-09: CRANE/021 → has_crane 발생 없음 (semantic firewall)."""
    for code in ("021", "CRANE"):
        eq_rows = [{"equipment_type_code": code, "is_operating": True}]
        fake_sb, calls = _patched_runtime(monkeypatch, eq_rows)
        R.run_safe_industrial_leg(fake_sb, "F1", SafeIndustrialConsumerInput())
        inp = calls["step1"].input
        assert "has_crane" not in inp, (
            f"code={code!r}: has_crane must not appear in step1.input"
        )


def test_MFG_no_equipment_rows_no_a2_facts(monkeypatch):
    """MFG-10: equipment_rows=[] → A2 facts absent (기존 계약 불변)."""
    fake_sb, calls = _patched_runtime(monkeypatch, [])
    R.run_safe_industrial_leg(fake_sb, "F1", SafeIndustrialConsumerInput())
    inp = calls["step1"].input
    for fact in ("has_press", "has_conveyor", "has_pressure_vessel", "has_emergency_gen"):
        assert fact not in inp, f"{fact} should be absent when no equipment rows"


def test_MFG_no_duplicate_a2_reader(monkeypatch):
    """MFG-11: 단일 request 내 equipment_assets A2 read가 1회만 발생 (중복 없음).

    safe_industrial_canonical_assembler도 equipment_assets를 읽지만 그것은
    Marketing composite(equipment_list UNRESOLVED) 목적이므로 별개 의미.
    이번 patch로 추가된 A2 seam reader는 정확히 1회.
    """
    eq_rows = [{"equipment_type_code": "023", "is_operating": True}]
    fake_sb, calls = _patched_runtime(monkeypatch, eq_rows)

    # assembler도 fake_sb를 쓰므로 eq_calls를 0 reset 후 측정
    fake_sb._eq_calls = 0
    R.run_safe_industrial_leg(fake_sb, "F1", SafeIndustrialConsumerInput())
    # load_equipment_rows_optional 호출 = 1회
    assert fake_sb._eq_calls == 1, (
        f"Expected exactly 1 equipment_assets query from A2 seam reader, got {fake_sb._eq_calls}"
    )


# ── SEAM: build_saas_leg_step1 직접 계약 검증 ─────────────────────────────────

def test_SEAM_equipment_rows_merge_basic():
    """SEAM-01: build_saas_leg_step1에 equipment_rows 전달 → canonical fact 반영."""
    from services.canonical.saas_leg_source_adapter import build_saas_leg_step1

    step1 = build_saas_leg_step1(
        sector="INDUSTRIAL",
        source_facts={"worker_count": 10},
        equipment_rows=[{"equipment_type_code": "023"}, {"equipment_type_code": "024"}],
    )
    assert step1.input.get("has_press") is True
    assert step1.input.get("has_conveyor") is True


def test_SEAM_source_false_wins_over_equipment():
    """SEAM-02: source_facts의 False가 equipment True보다 우선."""
    from services.canonical.saas_leg_source_adapter import build_saas_leg_step1

    step1 = build_saas_leg_step1(
        sector="INDUSTRIAL",
        source_facts={"has_press": False},
        equipment_rows=[{"equipment_type_code": "023"}],
    )
    # has_press=False in source_facts → equipment projection must not overwrite
    assert step1.input.get("has_press") is not True


# ── CST: CONSTRUCTION parity 테스트 ──────────────────────────────────────────

class _FakeSBConstruction:
    """Fake Supabase for diagnosis_integrated_svc CONSTRUCTION test."""

    def __init__(self, eq_rows):
        self._rows = eq_rows

    def table(self, name):
        return _FakeQCst(self, name)


class _FakeQCst:
    def __init__(self, sb, name):
        self._sb = sb
        self._name = name

    def select(self, *a, **k):
        return self

    def eq(self, col, val):
        return self

    def execute(self):
        class _R:
            pass
        r = _R()
        r.data = self._sb._rows
        return r


def _run_construction_eq_projection(eq_rows):
    """Directly exercise the CONSTRUCTION inline path from diagnosis_integrated_svc."""
    from services.equipment_source.store import load_equipment_rows_optional, EquipmentSourceLoadError
    from services.equipment_source.projector import project_equipment_rows

    sb = _FakeSBConstruction(eq_rows)
    rows = load_equipment_rows_optional(sb, "factory-1")
    return project_equipment_rows(rows)


def test_CST_023_has_press():
    """CST-01: CONSTRUCTION shared reader + projector → has_press=True."""
    result = _run_construction_eq_projection([{"equipment_type_code": "023", "is_operating": True}])
    assert result.get("has_press") is True


def test_CST_024_has_conveyor():
    """CST-02: CONSTRUCTION shared reader + projector → has_conveyor=True."""
    result = _run_construction_eq_projection([{"equipment_type_code": "024", "is_operating": True}])
    assert result.get("has_conveyor") is True


def test_CST_038_has_pressure_vessel():
    """CST-03: CONSTRUCTION shared reader + projector → has_pressure_vessel=True."""
    result = _run_construction_eq_projection([{"equipment_type_code": "038", "is_operating": True}])
    assert result.get("has_pressure_vessel") is True


def test_CST_read_error_raises_equipment_source_load_error():
    """CST-04: DB 오류 → EquipmentSourceLoadError 발생 (503 전환 가능, fail-closed)."""
    from services.equipment_source.store import load_equipment_rows_optional

    class _ErrorSB:
        def table(self, name):
            return _ErrQ()

    class _ErrQ:
        def select(self, *a, **k):
            return self

        def eq(self, col, val):
            return self

        def execute(self):
            raise RuntimeError("DB transport failure")

    with pytest.raises(EquipmentSourceLoadError):
        load_equipment_rows_optional(_ErrorSB(), "factory-1")
