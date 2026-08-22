"""WO-LEG-ELEVATOR-OPTION-A: build_facility 승강기법 축분리 테스트.

sector==BUILDING AND elevator_count>0 → has_building_elevator=True.
INDUSTRIAL/CONSTRUCTION 오염 금지. has_elevator(산업 리프트) 무접촉.
"""
import sys
import types

if "httpx" not in sys.modules:
    sys.modules["httpx"] = types.ModuleType("httpx")

from clients.leg_runtime_client import build_facility


class _Body:
    def __init__(self, **kw):
        self.input = kw.pop("input", {})
        for k, v in kw.items():
            setattr(self, k, v)

    def __getattr__(self, n):
        return None


def test_building_ec1_true():
    assert build_facility(_Body(sector="BUILDING", elevator_count=1)).get("has_building_elevator") is True


def test_building_ec6_true():
    assert build_facility(_Body(sector="BUILDING", elevator_count=6)).get("has_building_elevator") is True


def test_building_ec0_absent():
    assert "has_building_elevator" not in build_facility(_Body(sector="BUILDING", elevator_count=0))


def test_building_missing_absent():
    assert "has_building_elevator" not in build_facility(_Body(sector="BUILDING"))


def test_industrial_ec5_absent():
    # 핵심: INDUSTRIAL(MANUFACTURING) elevator_count>0 오염 금지
    assert "has_building_elevator" not in build_facility(_Body(sector="MANUFACTURING", elevator_count=5))


def test_industrial_has_elevator_untouched():
    f = build_facility(_Body(sector="MANUFACTURING", has_elevator=True))
    assert f.get("has_elevator") is True
    assert "has_building_elevator" not in f


def test_construction_ec5_absent():
    assert "has_building_elevator" not in build_facility(_Body(sector="CONSTRUCTION", elevator_count=5))


def test_safety3_unchanged():
    f = build_facility(_Body(sector="MANUFACTURING", work_height_m=2.5,
                             has_truck_loading_unloading=True, truck_loading_height_m=3.0))
    assert f.get("work_height_m") == 2.5
    assert f.get("has_truck_loading_unloading") is True
    assert f.get("truck_loading_height_m") == 3.0


def test_building_no_generic_has_elevator():
    # BUILDING에서 has_elevator 자동 생성 금지
    assert "has_elevator" not in build_facility(_Body(sector="BUILDING", elevator_count=3))


def test_bool_not_numeric():
    # elevator_count=True(bool) 방어
    assert "has_building_elevator" not in build_facility(_Body(sector="BUILDING", elevator_count=True))


def test_input_dict_path():
    # input dict 경로도 동작
    assert build_facility(_Body(sector="BUILDING", input={"elevator_count": 2})).get("has_building_elevator") is True
