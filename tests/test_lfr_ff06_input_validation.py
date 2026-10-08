"""WO-LFR-FF06-GAP-PATCH-068 — FF-06 입력 검증 contract 테스트.

GAP-01: work_height_m / truck_loading_height_m / manual_handling_weight_kg
        음수·NaN·±Infinity → ValidationError. 0·None·양수 → 허용.
GAP-02: has_truck_loading_unloading / has_manual_heavy_handling Parent/Detail 정합성.
        Parent=None/False + Detail 존재 → ValidationError.
        Parent=True + Detail=None → 허용 (LEG UNKNOWN 보존).
        Parent=True + Detail=값 → 허용 (정상 케이스).
        Parent=None + Detail=None → 허용.
"""
from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from schemas.legal_engine import (
    SafeBuildingConsumerInput,
    SafeConstructionConsumerInput,
    SafeIndustrialConsumerInput,
)

_CLASSES = [
    SafeIndustrialConsumerInput,
    SafeConstructionConsumerInput,
    SafeBuildingConsumerInput,
]

# ── GAP-01: work_height_m ────────────────────────────────────────────────────

@pytest.mark.parametrize("cls", _CLASSES)
@pytest.mark.parametrize("bad", [-1.0, -0.001, float("nan"), float("inf"), float("-inf")])
def test_GAP01_work_height_m_invalid(cls, bad):
    with pytest.raises(ValidationError) as exc:
        cls(work_height_m=bad)
    assert "work_height_m" in str(exc.value)


@pytest.mark.parametrize("cls", _CLASSES)
@pytest.mark.parametrize("ok", [None, 0.0, 0, 1.5, 100.0])
def test_GAP01_work_height_m_valid(cls, ok):
    obj = cls(work_height_m=ok)
    assert obj.work_height_m == ok


# ── GAP-01: truck_loading_height_m ──────────────────────────────────────────

@pytest.mark.parametrize("cls", _CLASSES)
@pytest.mark.parametrize("bad", [-1.0, float("nan"), float("inf"), float("-inf")])
def test_GAP01_truck_loading_height_m_invalid(cls, bad):
    with pytest.raises(ValidationError) as exc:
        cls(has_truck_loading_unloading=True, truck_loading_height_m=bad)
    assert "truck_loading_height_m" in str(exc.value)


@pytest.mark.parametrize("cls", _CLASSES)
@pytest.mark.parametrize("ok", [None, 0.0, 2.0])
def test_GAP01_truck_loading_height_m_valid(cls, ok):
    obj = cls(has_truck_loading_unloading=True, truck_loading_height_m=ok)
    assert obj.truck_loading_height_m == ok


# ── GAP-01: manual_handling_weight_kg ───────────────────────────────────────

@pytest.mark.parametrize("cls", _CLASSES)
@pytest.mark.parametrize("bad", [-5.0, float("nan"), float("-inf"), float("inf")])
def test_GAP01_manual_handling_weight_kg_invalid(cls, bad):
    with pytest.raises(ValidationError) as exc:
        cls(has_manual_heavy_handling=True, manual_handling_weight_kg=bad)
    assert "manual_handling_weight_kg" in str(exc.value)


@pytest.mark.parametrize("cls", _CLASSES)
@pytest.mark.parametrize("ok", [None, 0.0, 5.0, 25.0])
def test_GAP01_manual_handling_weight_kg_valid(cls, ok):
    obj = cls(has_manual_heavy_handling=True, manual_handling_weight_kg=ok)
    assert obj.manual_handling_weight_kg == ok


# ── GAP-02: truck_loading Parent/Detail 정합성 ───────────────────────────────

@pytest.mark.parametrize("cls", _CLASSES)
def test_GAP02_truck_parent_none_detail_present(cls):
    with pytest.raises(ValidationError) as exc:
        cls(truck_loading_height_m=1.5)
    assert "truck_loading_height_m" in str(exc.value)


@pytest.mark.parametrize("cls", _CLASSES)
def test_GAP02_truck_parent_false_detail_present(cls):
    with pytest.raises(ValidationError) as exc:
        cls(has_truck_loading_unloading=False, truck_loading_height_m=2.0)
    assert "truck_loading_height_m" in str(exc.value)


@pytest.mark.parametrize("cls", _CLASSES)
def test_GAP02_truck_parent_true_detail_none_allowed(cls):
    obj = cls(has_truck_loading_unloading=True, truck_loading_height_m=None)
    assert obj.has_truck_loading_unloading is True
    assert obj.truck_loading_height_m is None


@pytest.mark.parametrize("cls", _CLASSES)
def test_GAP02_truck_parent_true_detail_present_allowed(cls):
    obj = cls(has_truck_loading_unloading=True, truck_loading_height_m=2.0)
    assert obj.has_truck_loading_unloading is True
    assert obj.truck_loading_height_m == 2.0


@pytest.mark.parametrize("cls", _CLASSES)
def test_GAP02_truck_both_none_allowed(cls):
    obj = cls()
    assert obj.has_truck_loading_unloading is None
    assert obj.truck_loading_height_m is None


# ── GAP-02: manual_handling Parent/Detail 정합성 ─────────────────────────────

@pytest.mark.parametrize("cls", _CLASSES)
def test_GAP02_manual_parent_none_detail_present(cls):
    with pytest.raises(ValidationError) as exc:
        cls(manual_handling_weight_kg=25.0)
    assert "manual_handling_weight_kg" in str(exc.value)


@pytest.mark.parametrize("cls", _CLASSES)
def test_GAP02_manual_parent_false_detail_present(cls):
    with pytest.raises(ValidationError) as exc:
        cls(has_manual_heavy_handling=False, manual_handling_weight_kg=5.0)
    assert "manual_handling_weight_kg" in str(exc.value)


@pytest.mark.parametrize("cls", _CLASSES)
def test_GAP02_manual_parent_true_detail_none_allowed(cls):
    obj = cls(has_manual_heavy_handling=True, manual_handling_weight_kg=None)
    assert obj.has_manual_heavy_handling is True
    assert obj.manual_handling_weight_kg is None


@pytest.mark.parametrize("cls", _CLASSES)
def test_GAP02_manual_parent_true_detail_present_allowed(cls):
    obj = cls(has_manual_heavy_handling=True, manual_handling_weight_kg=5.0)
    assert obj.has_manual_heavy_handling is True
    assert obj.manual_handling_weight_kg == 5.0


@pytest.mark.parametrize("cls", _CLASSES)
def test_GAP02_manual_both_none_allowed(cls):
    obj = cls()
    assert obj.has_manual_heavy_handling is None
    assert obj.manual_handling_weight_kg is None


# ── 문자열·단위 포함 문자열 실제 Pydantic 처리 확인 ──────────────────────────

@pytest.mark.parametrize("cls", _CLASSES)
def test_string_with_unit_rejected(cls):
    with pytest.raises(ValidationError):
        cls(work_height_m="3.5m")


# ── FALSE / 0 / ABSENT 의미 보존 ─────────────────────────────────────────────

@pytest.mark.parametrize("cls", _CLASSES)
def test_false_preserved(cls):
    obj = cls(has_truck_loading_unloading=False)
    assert obj.has_truck_loading_unloading is False


@pytest.mark.parametrize("cls", _CLASSES)
def test_zero_work_height_preserved(cls):
    obj = cls(work_height_m=0.0)
    assert obj.work_height_m == 0.0


@pytest.mark.parametrize("cls", _CLASSES)
def test_none_work_height_preserved(cls):
    obj = cls(work_height_m=None)
    assert obj.work_height_m is None
