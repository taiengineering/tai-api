"""WO-E2E-OBS007-WELDING-MINIMUM-MODIFY-001: exact-name passthrough, no welding aliases."""
from types import SimpleNamespace

from clients.leg_runtime_client import _LEG_INPUT_FIELDS, build_facility


WELDING_DETAILS = (
    "uses_gases_for_welding_cutting_heating",
    "handles_gas_cylinders_for_welding_cutting_heating",
    "uses_acetylene_welding_equipment",
    "installs_acetylene_generator",
    "stores_unused_mobile_acetylene_welding_equipment",
    "has_acetylene_welding_equipment",
    "acetylene_generator_and_gas_cylinder_separated",
    "pipes_gas_manifold_welding_equipment",
    "has_dissolved_acetylene_gas_manifold_welding_equipment",
    "uses_gas_manifold_welding_equipment",
    "has_nonautomatic_arc_welding",
    "has_nonautomatic_ac_arc_welder",
    "welding_in_conductive_enclosed_place",
    "welding_at_height_ge_2m_with_conductive_contact_risk",
    "welding_in_wet_conductive_condition",
    "has_tunnel_construction_work",
    "performs_welding_cutting_heating_inside_tunnel",
)


def test_welding_detail_fields_in_allowlist():
    assert "has_welding" in _LEG_INPUT_FIELDS
    assert "has_high_pressure_work" in _LEG_INPUT_FIELDS
    for name in WELDING_DETAILS:
        assert name in _LEG_INPUT_FIELDS, name
    assert len(_LEG_INPUT_FIELDS) == 212  # WO-...-ART57B-FASTLANE-IMPLEMENT-001: 206→207
    assert len(set(_LEG_INPUT_FIELDS)) == 212  # WO-...-ART57B-FASTLANE-IMPLEMENT-001: 206→207


def test_has_welding_does_not_infer_details():
    body = SimpleNamespace(
        sector="CONSTRUCTION",
        input={"has_welding": True, "worker_count": 10},
    )
    fac = build_facility(body)
    assert fac.get("has_welding") is True
    for name in WELDING_DETAILS:
        assert name not in fac, name
    assert "has_high_pressure_work" not in fac
    assert "has_gas" not in fac
    assert "has_high_pressure_gas" not in fac
    assert "has_confined_space" not in fac
    assert "has_tunnel" not in fac
    assert "construction_tunnel" not in fac


def test_high_pressure_work_not_aliased_from_high_pressure_gas():
    body = SimpleNamespace(
        sector="CONSTRUCTION",
        input={"has_high_pressure_gas": True},
    )
    fac = build_facility(body)
    assert fac.get("has_high_pressure_gas") is True
    assert "has_high_pressure_work" not in fac


def test_detail_passthrough_without_parent():
    body = SimpleNamespace(
        sector="CONSTRUCTION",
        input={"uses_acetylene_welding_equipment": True},
    )
    fac = build_facility(body)
    assert fac.get("uses_acetylene_welding_equipment") is True
    assert "has_welding" not in fac
