"""WO-E2E-OBS008-DEMOLITION-MINIMUM-MODIFY-001: exact passthrough, no demolition aliases."""
from types import SimpleNamespace

from clients.leg_runtime_client import _LEG_INPUT_FIELDS, build_facility


DEMO_NEW = (
    "management_entity_bans_use_closes_or_demolishes_childrens_play_facility",
    "performs_structure_toppling_work_during_demolition",
    "has_structure_overturn_explosion_or_collapse_risk_due_to_loads_snow_wind_seismic_vibration_or_impact",
)


def test_demolition_exact_fields_in_allowlist():
    assert "has_demolition" in _LEG_INPUT_FIELDS
    for name in DEMO_NEW:
        assert name in _LEG_INPUT_FIELDS, name
    assert len(_LEG_INPUT_FIELDS) == 202
    assert len(set(_LEG_INPUT_FIELDS)) == 202


def test_has_demolition_does_not_infer_new_facts():
    body = SimpleNamespace(
        sector="CONSTRUCTION",
        input={"has_demolition": True, "worker_count": 75},
    )
    fac = build_facility(body)
    assert fac.get("has_demolition") is True
    for name in DEMO_NEW:
        assert name not in fac, name


def test_adjacent_fields_do_not_infer_demo_facts():
    body = SimpleNamespace(
        sector="CONSTRUCTION",
        input={
            "has_demolition": True,
            "has_asbestos_demo": True,
            "has_asbestos": True,
            "has_structure": True,
            "has_building_construction_activity": True,
            "has_hazardous_material": True,
        },
    )
    fac = build_facility(body)
    for name in DEMO_NEW:
        assert name not in fac, name


def test_exact_passthrough_without_has_demolition():
    body = SimpleNamespace(
        sector="CONSTRUCTION",
        input={
            "management_entity_bans_use_closes_or_demolishes_childrens_play_facility": True,
            "performs_structure_toppling_work_during_demolition": True,
            "has_structure_overturn_explosion_or_collapse_risk_due_to_loads_snow_wind_seismic_vibration_or_impact": True,
        },
    )
    fac = build_facility(body)
    for name in DEMO_NEW:
        assert fac.get(name) is True, name
    assert "has_demolition" not in fac
