"""WO-E2E-OBS009-COMMON-WORK-SOURCE-IMPLEMENT-001.

W1–W10 semantic tests. Family-specific engines are forbidden.
OBS007 / OBS008 / OBS009-A / KSIC / welding remain untouched.
"""
from __future__ import annotations

from types import SimpleNamespace

from clients.leg_runtime_client import (
    _LEG_CODE_TO_CONSUMER,
    _LEG_INPUT_FIELDS,
    build_facility,
)
from services.work_source.merge import (
    WorkSourceMergeConflict,
    merge_or_raise,
    merge_projected_into_facts,
)
from services.work_source.projector import project_work_row, project_work_rows
from services.work_source.registry import ALLOWED_WORK_TYPES, registry_public
from services.work_source.store import (
    WorkSourceLoadError,
    WorkSourceValidationError,
    load_work_rows_optional,
    validate_payload,
)


OBS009_CWS_FACTS = (
    "uses_forklift",
    "performs_work_with_fall_risk",
    "performs_work_on_roof",
    "performs_spray_work_with_flammable_liquid_in_enclosed_space",
    "performs_powered_machinery_maintenance_or_servicing",
    "performs_electrical_work",
    "performs_deenergized_circuit_electrical_work",
    "performs_electrical_work_near_deenergized_circuit",
    "performs_energized_circuit_electrical_work",
)

WELDING_DETAILS = (
    "uses_gases_for_welding_cutting_heating",
    "has_welding",
)
OBS007_CRANE = ("crane_repair_work", "has_crane")
OBS007_LIFT = ("lift_repair_work",)
OBS008 = ("performs_structure_toppling_work_during_demolition", "has_demolition")
OBS009A = ("has_confined_space", "performs_confined_space_work")
KSIC_NOT_IN_TRANSPORT = "ksic_major"


def _row(**kwargs):
    base = {
        "work_type": "FORKLIFT",
        "work_subtype": None,
        "attributes": {},
        "active": True,
    }
    base.update(kwargs)
    return base


# ── W1: possession is not use ─────────────────────────────────────────────
def test_W1_has_forklift_only_uses_forklift_absent():
    fac = build_facility(
        SimpleNamespace(sector="INDUSTRIAL", input={"has_forklift": True})
    )
    assert fac.get("has_forklift") is True
    assert "uses_forklift" not in fac
    assert project_work_rows([]) == {}


# ── W2: FORKLIFT active work → uses_forklift ──────────────────────────────
def test_W2_forklift_active_work_projects_use():
    facts = project_work_row(_row(work_type="FORKLIFT", active=True))
    assert facts == {"uses_forklift": True}
    assert "has_forklift" not in facts


def test_W2_inactive_forklift_emits_nothing():
    assert project_work_row(_row(work_type="FORKLIFT", active=False)) == {}


# ── W3: generic has_high_work does not produce MEWP ───────────────────────
def test_W3_generic_high_work_does_not_alias_mewp():
    assert "has_high_place_work" not in _LEG_CODE_TO_CONSUMER
    fac = build_facility(
        SimpleNamespace(
            sector="INDUSTRIAL",
            input={},
            has_high_work=True,
        )
    )
    assert "has_high_place_work" not in fac
    high_place = project_work_row(_row(work_type="HIGH_PLACE", active=True))
    assert "has_high_place_work" not in high_place


def test_W3_explicit_mewp_still_passthrough():
    fac = build_facility(
        SimpleNamespace(
            sector="INDUSTRIAL",
            input={"has_high_place_work": True},
        )
    )
    assert fac.get("has_high_place_work") is True


# ── W4: fall risk ─────────────────────────────────────────────────────────
def test_W4_fall_risk_attribute():
    facts = project_work_row(
        _row(work_type="HIGH_PLACE", attributes={"fall_risk": True})
    )
    assert facts == {"performs_work_with_fall_risk": True}


# ── W5: roof ──────────────────────────────────────────────────────────────
def test_W5_roof_subtype_and_attribute():
    by_subtype = project_work_row(
        _row(work_type="HIGH_PLACE", work_subtype="ROOF")
    )
    by_attr = project_work_row(
        _row(work_type="HIGH_PLACE", attributes={"roof": True})
    )
    assert by_subtype == {"performs_work_on_roof": True}
    assert by_attr == {"performs_work_on_roof": True}


# ── W6: painting exact conjunction ────────────────────────────────────────
def test_W6_painting_requires_all_three():
    full = project_work_row(
        _row(
            work_type="PAINTING",
            attributes={
                "spray": True,
                "flammable_liquid": True,
                "enclosed_space": True,
            },
        )
    )
    assert full == {
        "performs_spray_work_with_flammable_liquid_in_enclosed_space": True
    }
    partials = [
        {"spray": True},
        {"spray": True, "flammable_liquid": True},
        {"spray": True, "enclosed_space": True},
        {"flammable_liquid": True, "enclosed_space": True},
        {},
    ]
    for attrs in partials:
        facts = project_work_row(_row(work_type="PAINTING", attributes=attrs))
        assert facts == {}, attrs
        assert "performs_spray_work_with_flammable_liquid_in_enclosed_space" not in facts


# ── W7: maintenance powered machinery exact ───────────────────────────────
def test_W7_powered_machinery_maintenance():
    by_subtype = project_work_row(
        _row(work_type="MAINTENANCE", work_subtype="POWERED_MACHINERY")
    )
    by_attr = project_work_row(
        _row(work_type="MAINTENANCE", attributes={"powered_machinery": True})
    )
    generic = project_work_row(_row(work_type="MAINTENANCE"))
    assert by_subtype == {
        "performs_powered_machinery_maintenance_or_servicing": True
    }
    assert by_attr == {
        "performs_powered_machinery_maintenance_or_servicing": True
    }
    assert generic == {}
    assert "crane_repair_work" not in by_subtype
    assert "lift_repair_work" not in by_subtype


# ── W8: electrical subtype isolation ──────────────────────────────────────
def test_W8_electrical_deenergized_only():
    facts = project_work_row(
        _row(work_type="ELECTRICAL", work_subtype="DEENERGIZED")
    )
    assert facts == {"performs_deenergized_circuit_electrical_work": True}
    assert "performs_energized_circuit_electrical_work" not in facts
    assert "performs_electrical_work_near_deenergized_circuit" not in facts
    assert "performs_electrical_work" not in facts


def test_W8_electrical_parent_without_subtype():
    facts = project_work_row(_row(work_type="ELECTRICAL"))
    assert facts == {"performs_electrical_work": True}
    assert "performs_deenergized_circuit_electrical_work" not in facts
    assert "performs_energized_circuit_electrical_work" not in facts


# ── W9: missing != false ──────────────────────────────────────────────────
def test_W9_missing_attributes_not_false():
    facts = project_work_row(_row(work_type="HIGH_PLACE", attributes={}))
    assert facts == {}
    assert facts.get("performs_work_with_fall_risk") is not False
    assert "performs_work_with_fall_risk" not in facts
    fac = build_facility(SimpleNamespace(sector="INDUSTRIAL", input={}))
    for name in OBS009_CWS_FACTS:
        assert name not in fac


# ── W10: no broad family expansion ────────────────────────────────────────
def test_W10_one_family_does_not_emit_others():
    forklift = project_work_row(_row(work_type="FORKLIFT"))
    assert set(forklift) == {"uses_forklift"}
    painting = project_work_row(
        _row(
            work_type="PAINTING",
            attributes={
                "spray": True,
                "flammable_liquid": True,
                "enclosed_space": True,
            },
        )
    )
    assert "uses_forklift" not in painting
    assert "performs_work_with_fall_risk" not in painting
    electrical = project_work_row(
        _row(work_type="ELECTRICAL", work_subtype="DEENERGIZED")
    )
    for name in WELDING_DETAILS + OBS007_CRANE + OBS007_LIFT + OBS008 + OBS009A:
        assert name not in electrical
        assert name not in forklift
        assert name not in painting


def test_chemical_alias_untouched_high_work_alias_removed():
    assert _LEG_CODE_TO_CONSUMER == {
        "has_chemical": "has_chemical_substance",
    }
    fac = build_facility(
        SimpleNamespace(
            sector="INDUSTRIAL",
            input={},
            has_chemical_substance=True,
        )
    )
    assert fac.get("has_chemical") is True


def test_transport_allowlist_appends_work_facts_only():
    for name in OBS009_CWS_FACTS:
        assert name in _LEG_INPUT_FIELDS
    # WO-OBS009-MATERIAL-CANONICAL-RUNTIME-WIRING-PATCH-001: +3 chemical canonical
    # booleans (is_managed_/is_permit_required_/is_special_management_hazardous_substance)
    # were appended by that patch. Baseline 202 → 205.
    # WO-E2E-OBJ01-SEM002-ART57A-CONSUMER-INPUT-WIRING-001: +1 canonical
    # existential fact for Art.57 first sentence. Baseline 205 → 206.
    # WO-E2E-OBJ01-DIVING-COVERAGE-BACKLOG-FASTLANE-IMPLEMENT-001: +3 stable
    # diving-coverage inputs (diving_depth_m / diving_surface_ascent_restricted /
    # diving_decompression_stop_required). Baseline 212 → 215.
    # WO-E2E-OBJ01-HIGH-PRESSURE-COMMON-COVERAGE-INTEGRATED-IMPLEMENT-001: +1
    # has_caisson_work (Art.540/543 잠함공법). Baseline 215 → 216.
    # Uniqueness invariant preserved.
    assert len(_LEG_INPUT_FIELDS) == 216
    assert len(set(_LEG_INPUT_FIELDS)) == 216
    assert KSIC_NOT_IN_TRANSPORT not in _LEG_INPUT_FIELDS
    assert "has_welding" in _LEG_INPUT_FIELDS
    assert "has_demolition" in _LEG_INPUT_FIELDS
    assert "performs_confined_space_work" in _LEG_INPUT_FIELDS
    assert (
        "performs_scaffold_assembly_dismantle_or_modification_on_dalbi_or_ge5m_scaffold"
        in _LEG_INPUT_FIELDS
    )


def test_passthrough_projected_facts_do_not_invent_siblings():
    fac = build_facility(
        SimpleNamespace(
            sector="INDUSTRIAL",
            input={"uses_forklift": True},
        )
    )
    assert fac.get("uses_forklift") is True
    assert "has_forklift" not in fac
    assert "performs_work_with_fall_risk" not in fac


def test_merge_does_not_overwrite_explicit():
    merged, conflicts = merge_projected_into_facts(
        {"uses_forklift": False},
        work_rows=[_row(work_type="FORKLIFT")],
    )
    assert merged["uses_forklift"] is False
    assert conflicts and conflicts[0]["field"] == "uses_forklift"


def test_merge_or_raise_on_conflict():
    try:
        merge_or_raise(
            {"uses_forklift": False},
            work_rows=[_row(work_type="FORKLIFT")],
        )
    except WorkSourceMergeConflict as exc:
        assert exc.conflicts
    else:
        raise AssertionError("expected WorkSourceMergeConflict")


def test_merge_fills_absent_explicit():
    merged = merge_or_raise({}, work_rows=[_row(work_type="FORKLIFT")])
    assert merged == {"uses_forklift": True}


def test_registry_is_common_only():
    data = registry_public()
    codes = {item["code"] for item in data["work_types"]}
    assert codes == ALLOWED_WORK_TYPES
    # WO-E2E-OBJ01-SEM002-ART57A-CONSUMER-INPUT-WIRING-001: SCAFFOLD family
    # added (still a COMMON work family — one work_type per family, not per law).
    assert codes == {
        "ELECTRICAL",
        "HIGH_PLACE",
        "FORKLIFT",
        "PAINTING",
        "MAINTENANCE",
        "SCAFFOLD",
    }


def test_validate_rejects_canonical_booleans():
    try:
        validate_payload(
            {"work_type": "FORKLIFT", "attributes": {"uses_forklift": True}}
        )
    except WorkSourceValidationError:
        return
    raise AssertionError("canonical boolean must be rejected")


def test_validate_rejects_unknown_family_table_style_type():
    try:
        validate_payload({"work_type": "electrical_work_table"})
    except WorkSourceValidationError:
        return
    raise AssertionError("unknown work_type must be rejected")


class _OkQuery:
    def __init__(self, data, error=None):
        self._data = data
        self._error = error

    def table(self, name):
        return self

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def order(self, *a, **k):
        return self

    def execute(self):
        return SimpleNamespace(data=self._data, error=self._error)


class _BoomQuery:
    def table(self, name):
        raise RuntimeError("relation factory_work_facts does not exist")


def test_query_failure_is_not_empty_work():
    try:
        load_work_rows_optional(_BoomQuery(), "F1")
    except WorkSourceLoadError as exc:
        assert exc.code == "WORK_SOURCE_UNAVAILABLE"
        return
    raise AssertionError("query failure must not become []")


def test_successful_empty_list_is_no_work_not_error():
    assert load_work_rows_optional(_OkQuery([]), "F1") == []


def test_missing_factory_id_skips_query():
    class MustNotQuery:
        def table(self, name):
            raise AssertionError("no query without factory_id")

    assert load_work_rows_optional(MustNotQuery(), None) == []
    assert load_work_rows_optional(MustNotQuery(), "") == []


def test_non_list_payload_is_load_error():
    try:
        load_work_rows_optional(_OkQuery({"rows": []}), "F1")
    except WorkSourceLoadError:
        return
    raise AssertionError("non-list payload must not become []")


def test_query_error_field_is_load_error():
    try:
        load_work_rows_optional(_OkQuery([], error="permission denied"), "F1")
    except WorkSourceLoadError:
        return
    raise AssertionError("res.error must not become []")


def test_runtime_load_error_does_not_call_leg(monkeypatch):
    from schemas.legal_engine import SafeIndustrialConsumerInput
    from services import safe_industrial_leg_runtime as R
    from services.safe_industrial_canonical_assembler import TARGET_FIELDS, CONTRACT_VERSION

    calls = {"leg": 0}
    values = {f: None for f in TARGET_FIELDS}
    values["worker_count"] = 50
    monkeypatch.setattr(
        R,
        "assemble_industrial_marketing_contract",
        lambda supabase, factory_id: {
            "contract_version": CONTRACT_VERSION,
            "sector": "INDUSTRIAL",
            "factory_id": factory_id,
            "values": {f: values[f] for f in TARGET_FIELDS},
            "unresolved_fields": [],
            "provenance": {},
        },
    )
    monkeypatch.setattr(
        R,
        "run_leg_diagnosis",
        lambda step1: calls.__setitem__("leg", calls["leg"] + 1) or {},
    )
    monkeypatch.setattr(
        "services.work_source.store.load_work_rows_optional",
        lambda *a, **k: (_ for _ in ()).throw(
            WorkSourceLoadError("db down", factory_id="F1")
        ),
    )
    try:
        R.run_safe_industrial_leg(object(), "F1", SafeIndustrialConsumerInput())
    except WorkSourceLoadError:
        assert calls["leg"] == 0
        return
    raise AssertionError("diagnosis must abort on work source load error")


def test_industrial_leg_route_maps_load_error_to_503(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import routers.legal_engine as LE

    monkeypatch.setattr(LE, "get_supabase", lambda: object())
    monkeypatch.setattr(LE, "get_current_user", lambda auth: {"id": "u1"})
    monkeypatch.setattr(LE, "_ensure_factory_own", lambda sb, fid, cur: None)
    monkeypatch.setattr(
        LE,
        "evaluate_saas_tier_gate",
        lambda *a, **k: {
            "status": "FIT",
            "sector": "INDUSTRY",
            "current_plan": {"tier_code": "TEST_CURRENT"},
            "required_plan": {"tier_code": "TEST_REQUIRED"},
            "metric": {},
        },
    )
    monkeypatch.setattr(LE.leg_runtime_client, "is_enabled", lambda: True)
    monkeypatch.setattr(
        LE,
        "run_safe_industrial_leg",
        lambda sb, fid, ci: (_ for _ in ()).throw(
            WorkSourceLoadError("db down", factory_id=fid)
        ),
    )
    app = FastAPI()
    app.include_router(LE.router)
    client = TestClient(app, raise_server_exceptions=False)
    res = client.post(
        "/legal-engine/diagnose/industrial-leg",
        json={"factory_id": "F1", "input": {}},
    )
    assert res.status_code == 503
    assert res.json()["detail"]["code"] == "WORK_SOURCE_UNAVAILABLE"
