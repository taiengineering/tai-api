"""WO-006 PATCH-2A — build_facility passthrough for numeric 11 + trigger 4 (U7/U8)."""
from schemas.legal_engine import DiagnoseStep1Body
from clients.leg_runtime_client import build_facility, _LEG_INPUT_FIELDS

NEW15 = [
    "scaffold_height_m", "grinding_wheel_diameter_cm", "breathing_gas_cylinder_pressure_kgf_cm2",
    "structure_height_m", "object_drop_height_m", "construction_machine_weight_ton",
    "hazmat_designated_quantity_multiple", "rotor_peripheral_speed_m_s", "rotor_shaft_weight_ton",
    "same_site_construction_count", "diving_worker_count",
    "has_structure", "has_object_drop", "has_construction_machine", "has_high_speed_rotor",
]


def test_U7_new15_in_leg_input_fields():
    for f in NEW15:
        assert f in _LEG_INPUT_FIELDS


def test_U7_passthrough_and_omit():
    fac = build_facility(DiagnoseStep1Body(
        sector="MANUFACTURING",
        input={
            "has_scaffold": True,
            "scaffold_height_m": 6.0,
            "has_structure": True,
            "structure_height_m": 20,
            "has_high_speed_rotor": True,
            "rotor_shaft_weight_ton": 1.5,
            "rotor_peripheral_speed_m_s": 120,
            "scaffold_height_m_blank_should_not_exist": "",  # not a registered field
        },
    ))
    assert fac["scaffold_height_m"] == 6.0
    assert fac["has_structure"] is True
    assert fac["structure_height_m"] == 20
    assert fac["has_high_speed_rotor"] is True
    assert fac["rotor_shaft_weight_ton"] == 1.5
    assert "object_drop_height_m" not in fac  # absent → omit
    # no alias/derivation: scaffold_height does not invent has_scaffold from height alone
    fac2 = build_facility(DiagnoseStep1Body(
        sector="MANUFACTURING",
        input={"scaffold_height_m": 6.0},
    ))
    assert fac2["scaffold_height_m"] == 6.0
    assert "has_scaffold" not in fac2


def test_U7_none_and_blank_omitted():
    fac = build_facility(DiagnoseStep1Body(
        sector="MANUFACTURING",
        input={
            "scaffold_height_m": None,
            "diving_worker_count": "",
            "has_object_drop": True,
        },
    ))
    assert "scaffold_height_m" not in fac
    assert "diving_worker_count" not in fac
    assert fac["has_object_drop"] is True


def test_U8_complete_input_regression_existing_keys():
    base = {
        "has_scaffold": True,
        "has_diving": True,
        "has_grinding": True,
        "worker_count": 10,
        "total_floor_area": 1000,
    }
    fac = build_facility(DiagnoseStep1Body(sector="MANUFACTURING", input=dict(base)))
    for k, v in base.items():
        assert fac[k] == v
    # new axes absent when not provided
    for f in NEW15:
        assert f not in fac
