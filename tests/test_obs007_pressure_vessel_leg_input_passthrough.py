"""WO-E2E-OBS007-PRESSURE-VESSEL-MINIMUM-MODIFY-001: exact passthrough, no PV aliases."""
from types import SimpleNamespace

from clients.leg_runtime_client import _LEG_INPUT_FIELDS, build_facility


PV_NEW = (
    "has_air_compressor",
    "has_worker_risk_rotating_parts_on_pressure_vessel_or_air_compressor",
    "supplies_air_to_high_pressure_workroom_or_airlock",
)


def test_pressure_vessel_exact_fields_in_allowlist():
    assert "has_pressure_vessel" in _LEG_INPUT_FIELDS
    for name in PV_NEW:
        assert name in _LEG_INPUT_FIELDS, name
    assert len(_LEG_INPUT_FIELDS) == 187
    assert len(set(_LEG_INPUT_FIELDS)) == 187


def test_has_pressure_vessel_does_not_infer_new_facts():
    body = SimpleNamespace(
        sector="INDUSTRIAL",
        input={"has_pressure_vessel": True, "worker_count": 15},
    )
    fac = build_facility(body)
    assert fac.get("has_pressure_vessel") is True
    for name in PV_NEW:
        assert name not in fac, name


def test_has_high_pressure_gas_does_not_infer_air_compressor():
    body = SimpleNamespace(
        sector="INDUSTRIAL",
        input={"has_high_pressure_gas": True},
    )
    fac = build_facility(body)
    assert fac.get("has_high_pressure_gas") is True
    assert "has_air_compressor" not in fac
    assert "has_pressure_vessel" not in fac


def test_has_high_pressure_work_does_not_infer_air_supply():
    body = SimpleNamespace(
        sector="INDUSTRIAL",
        input={"has_high_pressure_work": True},
    )
    fac = build_facility(body)
    assert fac.get("has_high_pressure_work") is True
    assert "supplies_air_to_high_pressure_workroom_or_airlock" not in fac
    assert "has_air_compressor" not in fac


def test_has_confined_space_does_not_infer_air_supply():
    body = SimpleNamespace(
        sector="INDUSTRIAL",
        input={"has_confined_space": True},
    )
    fac = build_facility(body)
    assert fac.get("has_confined_space") is True
    assert "supplies_air_to_high_pressure_workroom_or_airlock" not in fac


def test_adjacent_names_do_not_alias_pv_facts():
    body = SimpleNamespace(
        sector="INDUSTRIAL",
        input={
            "has_boiler": True,
            "has_high_pressure_gas": True,
            "has_high_pressure_work": True,
            "has_gas": True,
            "has_confined_space": True,
        },
    )
    fac = build_facility(body)
    for name in PV_NEW:
        assert name not in fac, name
    assert "has_pressure_vessel" not in fac


def test_exact_passthrough_without_has_pressure_vessel():
    body = SimpleNamespace(
        sector="INDUSTRIAL",
        input={
            "has_air_compressor": True,
            "has_worker_risk_rotating_parts_on_pressure_vessel_or_air_compressor": True,
            "supplies_air_to_high_pressure_workroom_or_airlock": True,
        },
    )
    fac = build_facility(body)
    assert fac.get("has_air_compressor") is True
    assert fac.get("has_worker_risk_rotating_parts_on_pressure_vessel_or_air_compressor") is True
    assert fac.get("supplies_air_to_high_pressure_workroom_or_airlock") is True
    assert "has_pressure_vessel" not in fac
