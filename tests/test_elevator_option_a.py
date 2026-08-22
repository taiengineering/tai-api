"""WO-LEG-ELEVATOR-OPTION-A: build_facility 승강기법 축분리 테스트.

sector==BUILDING AND elevator_count>0 → has_building_elevator=True.
has_building_elevator는 derived-only canonical field (consumer passthrough 금지).
INDUSTRIAL/CONSTRUCTION 오염 및 direct injection 금지. has_elevator(산업 리프트) 무접촉.
"""
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
    # INDUSTRIAL(MANUFACTURING) elevator_count>0 오염 금지
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
    # input dict의 elevator_count 경로도 동작 (BUILDING만)
    assert build_facility(_Body(sector="BUILDING", input={"elevator_count": 2})).get("has_building_elevator") is True


# ── REV-1: derived-only 계약 — has_building_elevator direct injection 차단 ──
def test_manufacturing_direct_injection_absent():
    # sector=MANUFACTURING에서 input으로 has_building_elevator 주입 시도 → 차단
    assert "has_building_elevator" not in build_facility(
        _Body(sector="MANUFACTURING", input={"has_building_elevator": True})
    )


def test_construction_direct_injection_absent():
    assert "has_building_elevator" not in build_facility(
        _Body(sector="CONSTRUCTION", input={"has_building_elevator": True})
    )


def test_building_ec0_direct_injection_absent():
    # BUILDING이라도 elevator_count=0이면 input 주입으로 생성 불가
    assert "has_building_elevator" not in build_facility(
        _Body(sector="BUILDING", elevator_count=0, input={"has_building_elevator": True})
    )
