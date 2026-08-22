"""WO-LEG-SAFETY-3-CONSUMER-INPUT-IMPLEMENT-01: 신규 5축 lossless 전달 회귀 테스트.

산안49/187/665 소비자 입력 5축이 clients.leg_runtime_client._LEG_INPUT_FIELDS 화이트리스트를
통과해 build_facility까지 손실 없이 전달되는지, 그리고 canonical_applicability(nexas 보존 경로)가
float/bool/null/missing 계약을 보존하는지 검증한다.

핵심 계약:
- numeric 3축(work_height_m, truck_loading_height_m, manual_handling_weight_kg)은 VERBATIM 보존
  (Nexas _NUMERIC_FIELDS 미등록 → int 절삭 없음).
- false ≠ missing (187/665 3치 AND: false→NOT_APPLICABLE, missing→UNKNOWN).
"""
from __future__ import annotations

from clients.leg_runtime_client import _LEG_INPUT_FIELDS, build_facility
from services.canonical.materialization import canonical_applicability
from services.diagnosis_nexas_adapter import _NUMERIC_FIELDS


_NEW5 = (
    "work_height_m", "has_truck_loading_unloading", "truck_loading_height_m",
    "has_manual_heavy_handling", "manual_handling_weight_kg",
)
_NEW3_NUMERIC = ("work_height_m", "truck_loading_height_m", "manual_handling_weight_kg")


class _Body:
    """DiagnoseStep1Body 최소 대역: input dict만 노출."""
    def __init__(self, inp):
        self.input = inp


def test_allowlist_contains_new5():
    for f in _NEW5:
        assert f in _LEG_INPUT_FIELDS, f"{f} 누락"
    # 기존 49 + 신규 5 = 54, 중복 없음
    assert len(_LEG_INPUT_FIELDS) == len(set(_LEG_INPUT_FIELDS))
    assert len(_LEG_INPUT_FIELDS) == 54


def test_new3_not_in_nexas_numeric():
    # 소수 절삭 방지: 신규 numeric 3축은 nexas coercion 목록에 없어야 한다.
    for f in _NEW3_NUMERIC:
        assert f not in _NUMERIC_FIELDS, f"{f} 가 _NUMERIC_FIELDS에 있음(int 절삭 위험)"


def test_float_preserved_through_facility():
    payload = {
        "work_height_m": 1.9, "has_truck_loading_unloading": False,
        "truck_loading_height_m": 2.1, "has_manual_heavy_handling": True,
        "manual_handling_weight_kg": 4.9,
    }
    inp = canonical_applicability(payload)
    fac = build_facility(_Body(inp))
    assert fac["work_height_m"] == 1.9 and isinstance(fac["work_height_m"], float)
    assert fac["truck_loading_height_m"] == 2.1 and isinstance(fac["truck_loading_height_m"], float)
    assert fac["manual_handling_weight_kg"] == 4.9 and isinstance(fac["manual_handling_weight_kg"], float)
    assert fac["has_truck_loading_unloading"] is False
    assert fac["has_manual_heavy_handling"] is True


def test_false_key_present():
    fac = build_facility(_Body(canonical_applicability({"has_truck_loading_unloading": False})))
    assert "has_truck_loading_unloading" in fac
    assert fac["has_truck_loading_unloading"] is False


def test_missing_key_absent():
    fac = build_facility(_Body(canonical_applicability({})))
    assert "has_truck_loading_unloading" not in fac
    assert "work_height_m" not in fac


def test_null_not_coerced_to_false():
    # null은 false/0으로 강제되지 않고 미포함 처리되어야 한다.
    fac = build_facility(_Body(canonical_applicability({"has_truck_loading_unloading": None})))
    assert "has_truck_loading_unloading" not in fac
    fac2 = build_facility(_Body(canonical_applicability({"work_height_m": None})))
    assert "work_height_m" not in fac2


def test_zero_distinct_from_missing():
    # 0/0.0은 명시적 값이므로 facility에 존재해야 한다(미입력과 구분).
    fac = build_facility(_Body(canonical_applicability({"work_height_m": 0})))
    assert fac.get("work_height_m") == 0
    fac2 = build_facility(_Body(canonical_applicability({"work_height_m": 0.0})))
    assert fac2.get("work_height_m") == 0.0


def test_existing_fields_unaffected():
    # 기존 축은 신규 추가와 무관하게 그대로 전달되어야 한다.
    fac = build_facility(_Body({"worker_count": 50, "has_tower_crane": True, "total_floor_area": 400.0}))
    assert fac["worker_count"] == 50
    assert fac["total_floor_area"] == 400.0
    # has_tower_crane는 allowlist에 없으므로(별도 축) 전달 안 됨 — 기존 계약 그대로
    assert "has_tower_crane" not in fac
