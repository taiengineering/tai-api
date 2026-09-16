"""WO-E2E-OBS007-BOILER-MINIMUM-MODIFY-001: exact-name passthrough, no boiler aliases."""
from types import SimpleNamespace

from clients.leg_runtime_client import _LEG_INPUT_FIELDS, build_facility


BOILER_REROUTE = (
    "performs_welding_or_cutting_in_insufficiently_ventilated_place",
    "works_in_place_with_appendix18_item13_inert_gas_discharge_piping",
)


def test_boiler_exact_fields_in_allowlist():
    assert "has_boiler" in _LEG_INPUT_FIELDS
    assert "has_gas_boiler_heating_system" in _LEG_INPUT_FIELDS
    for name in BOILER_REROUTE:
        assert name in _LEG_INPUT_FIELDS, name
    assert len(_LEG_INPUT_FIELDS) == 205
    assert len(set(_LEG_INPUT_FIELDS)) == 205


def test_has_boiler_does_not_infer_reroute_facts():
    body = SimpleNamespace(
        sector="INDUSTRIAL",
        input={"has_boiler": True, "worker_count": 15},
    )
    fac = build_facility(body)
    assert fac.get("has_boiler") is True
    for name in BOILER_REROUTE:
        assert name not in fac, name
    assert "has_gas_boiler_heating_system" not in fac


def test_has_welding_does_not_infer_art629():
    body = SimpleNamespace(
        sector="INDUSTRIAL",
        input={"has_welding": True},
    )
    fac = build_facility(body)
    assert fac.get("has_welding") is True
    assert "performs_welding_or_cutting_in_insufficiently_ventilated_place" not in fac
    assert "has_boiler" not in fac


def test_has_confined_space_does_not_infer_art629():
    body = SimpleNamespace(
        sector="INDUSTRIAL",
        input={"has_confined_space": True},
    )
    fac = build_facility(body)
    assert fac.get("has_confined_space") is True
    assert "performs_welding_or_cutting_in_insufficiently_ventilated_place" not in fac


def test_has_gas_does_not_infer_art630():
    body = SimpleNamespace(
        sector="INDUSTRIAL",
        input={"has_gas": True},
    )
    fac = build_facility(body)
    assert fac.get("has_gas") is True
    assert "works_in_place_with_appendix18_item13_inert_gas_discharge_piping" not in fac
    assert "has_boiler" not in fac


def test_has_high_pressure_gas_does_not_infer_art630():
    body = SimpleNamespace(
        sector="INDUSTRIAL",
        input={"has_high_pressure_gas": True},
    )
    fac = build_facility(body)
    assert fac.get("has_high_pressure_gas") is True
    assert "works_in_place_with_appendix18_item13_inert_gas_discharge_piping" not in fac


def test_exact_reroute_passthrough_without_has_boiler():
    body = SimpleNamespace(
        sector="INDUSTRIAL",
        input={
            "performs_welding_or_cutting_in_insufficiently_ventilated_place": True,
            "works_in_place_with_appendix18_item13_inert_gas_discharge_piping": True,
        },
    )
    fac = build_facility(body)
    assert fac.get("performs_welding_or_cutting_in_insufficiently_ventilated_place") is True
    assert fac.get("works_in_place_with_appendix18_item13_inert_gas_discharge_piping") is True
    assert "has_boiler" not in fac
    assert "has_gas_boiler_heating_system" not in fac
