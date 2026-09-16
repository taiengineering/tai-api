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


OBS009A_NEW7 = [
    "performs_confined_space_work",
    "confined_space_has_always_on_supply_exhaust_ventilation",
    "oxygen_deficiency_or_hazardous_gas_fall_risk",
    "oxygen_deficiency_or_hazardous_gas_asphyxiation_fire_or_explosion_risk",
    "confined_space_work_with_exposed_live_parts_in_manhole_or_basement",
    "work_in_basement_or_pit_with_piping_through_confined_space",
    "performs_confined_space_rescue_work",
]
OBS009A_DETAILS = OBS009A_NEW7[1:]
OBS009A_EXCEPTION = (
    "confined_space_ventilation_impracticable_due_to_explosion_oxidation_or_work_nature"
)


def test_obs009a_T1_all_true_passthrough():
    inp = {name: True for name in OBS009A_NEW7}
    fac = build_facility(DiagnoseStep1Body(sector="CONSTRUCTION", input=inp))
    for name in OBS009A_NEW7:
        assert fac[name] is True, name
    assert OBS009A_EXCEPTION not in fac


def test_obs009a_T2_false_preservation():
    inp = {name: False for name in OBS009A_NEW7}
    fac = build_facility(DiagnoseStep1Body(sector="CONSTRUCTION", input=inp))
    for name in OBS009A_NEW7:
        assert name in fac, name
        assert fac[name] is False, name


def test_obs009a_T3_location_does_not_synthesize_work():
    fac = build_facility(DiagnoseStep1Body(
        sector="CONSTRUCTION",
        input={"has_confined_space": True},
    ))
    assert fac["has_confined_space"] is True
    assert "performs_confined_space_work" not in fac
    for name in OBS009A_DETAILS:
        assert name not in fac, name


def test_obs009a_T4_work_does_not_synthesize_detail():
    fac = build_facility(DiagnoseStep1Body(
        sector="CONSTRUCTION",
        input={
            "has_confined_space": True,
            "performs_confined_space_work": True,
        },
    ))
    assert fac["has_confined_space"] is True
    assert fac["performs_confined_space_work"] is True
    for name in OBS009A_DETAILS:
        assert name not in fac, name


def test_obs009a_T5_one_detail_stays_one_detail():
    fac = build_facility(DiagnoseStep1Body(
        sector="CONSTRUCTION",
        input={
            "has_confined_space": True,
            "performs_confined_space_work": True,
            "oxygen_deficiency_or_hazardous_gas_fall_risk": True,
        },
    ))
    assert fac["has_confined_space"] is True
    assert fac["performs_confined_space_work"] is True
    assert fac["oxygen_deficiency_or_hazardous_gas_fall_risk"] is True
    for name in OBS009A_DETAILS:
        if name == "oxygen_deficiency_or_hazardous_gas_fall_risk":
            continue
        assert name not in fac, name


def test_obs009a_T6_unregistered_exception_no_passthrough():
    fac = build_facility(DiagnoseStep1Body(
        sector="CONSTRUCTION",
        input={
            "has_confined_space": True,
            OBS009A_EXCEPTION: True,
        },
    ))
    assert fac["has_confined_space"] is True
    assert OBS009A_EXCEPTION not in _LEG_INPUT_FIELDS
    assert OBS009A_EXCEPTION not in fac


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
