"""WO-E2E-OBS007-DUST-WORK-MINIMUM-MODIFY-001: exact-name passthrough, no dust aliases."""
from types import SimpleNamespace

from clients.leg_runtime_client import _LEG_INPUT_FIELDS, build_facility


DUST_DETAILS = (
    "dust_heavily_airborne_in_workplace",
    "has_appendix16_item_5_25_dust_work",
    "dust_work_in_indoor_workplace",
    "dust_work_in_mine_workplace",
    "has_regular_dust_work",
    "has_dust_work_other_than_appendix16_item26",
)
REROUTE_FACTS = (
    "has_harmful_airborne_substance_local_exhaust_system",
    "has_fixed_harmful_airborne_substance_local_exhaust_system",
    "has_nonexempt_harmful_airborne_substance_local_exhaust_system",
    "has_harmful_airborne_substance_discharge_equipment",
    "has_harmful_airborne_substance_general_ventilation_system",
    "has_harmful_airborne_substance_work",
    "has_indoor_harmful_airborne_substance_emission",
    "prepares_explosion_hazard_area_classification_drawing",
    "manufactures_handles_or_uses_flammable_liquid_vapor_or_gas",
    "manufactures_or_uses_flammable_solid",
    "has_flammable_substance_explosion_fire_risk_location",
    "tunnel_visibility_significantly_limited_by_exhaust_or_dust",
    "handles_managed_hazardous_substance_in_indoor_workplace",
    "has_beryllium_manufacturing_or_use_work",
    "has_office_workplace",
    "has_pesticide_raw_material_mixing_work",
)


def test_dust_exact_fields_in_allowlist():
    assert "has_dust_work" in _LEG_INPUT_FIELDS
    assert "has_tunnel_construction_work" in _LEG_INPUT_FIELDS
    for name in DUST_DETAILS + REROUTE_FACTS:
        assert name in _LEG_INPUT_FIELDS, name
    assert len(_LEG_INPUT_FIELDS) == 202
    assert len(set(_LEG_INPUT_FIELDS)) == 202


def test_has_dust_work_does_not_infer_details():
    body = SimpleNamespace(
        sector="INDUSTRIAL",
        input={"has_dust_work": True, "worker_count": 15},
    )
    fac = build_facility(body)
    assert fac.get("has_dust_work") is True
    for name in DUST_DETAILS + REROUTE_FACTS:
        assert name not in fac, name
    assert "has_grinding" not in fac
    assert "has_cutting" not in fac
    assert "has_blasting" not in fac
    assert "has_confined_space" not in fac
    assert "has_chemical" not in fac
    assert "has_mixing_process" not in fac
    assert "has_tunnel" not in fac
    assert "construction_tunnel" not in fac


def test_adjacent_names_do_not_alias_dust_facts():
    body = SimpleNamespace(
        sector="INDUSTRIAL",
        input={
            "has_grinding": True,
            "has_blasting": True,
            "has_confined_space": True,
            "has_chemical": True,
        },
    )
    fac = build_facility(body)
    assert fac.get("has_grinding") is True
    assert fac.get("has_blasting") is True
    assert fac.get("has_confined_space") is True
    assert fac.get("has_chemical") is True
    assert "has_dust_work" not in fac
    assert "dust_work_in_mine_workplace" not in fac
    assert "handles_managed_hazardous_substance_in_indoor_workplace" not in fac
    assert "has_dust_work_other_than_appendix16_item26" not in fac


def test_item26_absence_does_not_infer_other_than_item26():
    body = SimpleNamespace(
        sector="INDUSTRIAL",
        input={"has_dust_work": True},
    )
    fac = build_facility(body)
    assert "has_dust_work_other_than_appendix16_item26" not in fac


def test_detail_passthrough_without_parent():
    body = SimpleNamespace(
        sector="INDUSTRIAL",
        input={"dust_work_in_indoor_workplace": True},
    )
    fac = build_facility(body)
    assert fac.get("dust_work_in_indoor_workplace") is True
    assert "has_dust_work" not in fac


def test_tunnel_construction_not_aliased_from_has_tunnel():
    body = SimpleNamespace(
        sector="CONSTRUCTION",
        input={"has_tunnel_construction_work": True},
    )
    fac = build_facility(body)
    assert fac.get("has_tunnel_construction_work") is True
    assert "tunnel_visibility_significantly_limited_by_exhaust_or_dust" not in fac
    assert "has_dust_work" not in fac


def test_art230_place_fact_does_not_infer_drawing():
    body = SimpleNamespace(
        sector="INDUSTRIAL",
        input={"manufactures_handles_or_uses_flammable_liquid_vapor_or_gas": True},
    )
    fac = build_facility(body)
    assert fac.get("manufactures_handles_or_uses_flammable_liquid_vapor_or_gas") is True
    assert "prepares_explosion_hazard_area_classification_drawing" not in fac
    assert "has_dust_work" not in fac
