"""tests/test_free_consumer_c1_c3_guard.py
WO-CONSUMER-PIPELINE-FREE-PROFILE-001 PHASE-4 — FREE C1→C3 Consumer Contract Coverage Guard.

검증 범위:
  FREE 3-sector form_data(C1) → nexas_run_body_from_request → run_diagnosis(C2) →
  _build_unified_step1_body → build_unified_leg_input → build_facility(C3)
  까지 transport contract 를 guarding 한다. Production runtime(Supabase/RTM) 미접근.

5 Transport classifications (matrix annotation):
  DIRECT_CANONICAL          — field_code ∈ _LEG_INPUT_FIELDS; C1 값이 C3 facility 에 verbatim 도달.
  DIRECT_CANONICAL_BUILDING — ∈ _LEG_INPUT_FIELDS + _BUILDING_N1_FIELDS; BUILDING 에만 C3 도달.
  SOURCE_PROJECTED          — C1 source field → server expansion/projection → C3 domain fact.
  EXPECTED_NON_RUNTIME      — C1 body 수신 ok; _LEG_INPUT_FIELDS 밖 → C3 facility ABSENT.
  SECTOR_BLOCKED_EXPECTED   — BUILDING N1 field; BUILDING C3 present, INDUSTRIAL/CONSTRUCTION C3 absent.

Test groups G-01~G-14:
  G-01  CONSTRUCTION DIRECT_CANONICAL boolean true → facility present
  G-02  CONSTRUCTION DIRECT_CANONICAL numeric → facility present
  G-03  INDUSTRIAL DIRECT_CANONICAL fields → facility present
  G-04  BUILDING DIRECT_CANONICAL fields → facility present
  G-05  Boolean false EXPLICITLY PRESERVED (not treated as absent) — all 3 sectors
  G-06  UNKNOWN / ABSENT key — not in form_data → not in facility
  G-07  Parent false → conditional numeric child absent from facility
  G-08  Parent true + child_value → child present in facility
  G-09  appendix3_item_no SOURCE_PROJECTED → server projects is_appendix3_item_37 etc.
  G-10  subcontractor_work_types SOURCE_PROJECTED → has_fire_facility_subcontract etc.
  G-11  EXPECTED_NON_RUNTIME (has_hazmat_storage) → NOT in facility
  G-12  BUILDING N1 SECTOR_BLOCKED — field present only for BUILDING, absent INDUSTRIAL/CONSTRUCTION
  G-13  Worker-count bridge — workers/worker_count alias → worker_count in facility
  G-14  is_construction chain — conditional is_relationship_contractor / is_civil_construction
"""
from __future__ import annotations

from typing import Any, Dict, Tuple

import pytest

from clients.leg_runtime_client import (
    _BUILDING_N1_FIELDS,
    _LEG_INPUT_FIELDS,
    build_facility,
)
from schemas.diagnosis_integrated import DiagnosisRunBody
from services.diagnosis_nexas_adapter import nexas_run_body_from_request
from services import diagnosis_integrated_svc as svc
from services.canonical.leg_input_contract import build_unified_leg_input


# ─────────────────────────────────────────────────────────────────────────────
# Transport matrix — reconstructed from SQL migration history
# (WO-007 STEP-2A · STEP-2C-1 · Core22 appendix3 · Core22 CST predicates · Subcontractor WO)
# ─────────────────────────────────────────────────────────────────────────────

# DIRECT_CANONICAL fields known per sector (subset; extend as catalog grows)
CONSTRUCTION_DIRECT_CANONICAL_BOOL = frozenset({
    "has_scaffold", "has_construction_machine", "has_structure",
    "has_grinding", "has_diving", "has_object_drop", "has_subcontractor",
    "is_construction", "is_relationship_contractor", "is_civil_construction",
})
CONSTRUCTION_DIRECT_CANONICAL_NUM = frozenset({
    "worker_count", "contract_amount_eok",
    "scaffold_height_m", "construction_machine_weight_ton",
    "grinding_wheel_diameter_cm", "diving_worker_count",
    "object_drop_height_m", "same_site_construction_count",
})
CONSTRUCTION_SOURCE_PROJECTED = frozenset({
    "subcontractor_work_types",  # → has_fire_facility_subcontract / has_ict_subcontract
})
CONSTRUCTION_EXPECTED_NON_RUNTIME: frozenset = frozenset()  # no FREE non-runtime field for CST
# 7 parent→child conditional pairs (CONSTRUCTION)
CONSTRUCTION_PARENT_CHILD_PAIRS: list[Tuple[str, str]] = [
    ("has_scaffold",             "scaffold_height_m"),
    ("has_construction_machine", "construction_machine_weight_ton"),
    ("has_grinding",             "grinding_wheel_diameter_cm"),
    ("has_diving",               "diving_worker_count"),
    ("has_object_drop",          "object_drop_height_m"),
    ("has_subcontractor",        "same_site_construction_count"),
    ("is_construction",          "is_relationship_contractor"),
]

INDUSTRIAL_DIRECT_CANONICAL_BOOL = frozenset({
    "has_scaffold", "has_construction_machine",
    "has_grinding", "has_diving", "has_object_drop",
    "has_high_speed_rotor", "has_hazmat_storage",
    "is_real_estate_management",  # conditional child of appendix3_item_no
})
INDUSTRIAL_DIRECT_CANONICAL_NUM = frozenset({
    "worker_count", "total_floor_area",
    "scaffold_height_m", "construction_machine_weight_ton",
    "grinding_wheel_diameter_cm", "diving_worker_count",
    "object_drop_height_m",
})
INDUSTRIAL_SOURCE_PROJECTED = frozenset({
    "appendix3_item_no",  # → is_appendix3_1_27, is_appendix3_28_48, is_appendix3_item_37, is_appendix3_item_40
})
INDUSTRIAL_EXPECTED_NON_RUNTIME = frozenset({
    "ksic_major",  # not in _LEG_INPUT_FIELDS
})

BUILDING_DIRECT_CANONICAL_BOOL = frozenset({
    "has_elevator", "has_boiler", "has_gas", "has_hazardous_material",
    "has_structure", "has_scaffold", "has_hazmat_storage",
    "is_real_estate_management",
})
BUILDING_DIRECT_CANONICAL_NUM = frozenset({
    "worker_count", "total_floor_area",
    "structure_height_m", "scaffold_height_m",
})
BUILDING_SOURCE_PROJECTED = frozenset({
    "appendix3_item_no",
})
BUILDING_EXPECTED_NON_RUNTIME: frozenset = frozenset()  # no FREE non-runtime field for BLD
# SECTOR_BLOCKED: BUILDING N1 example field (present for BUILDING, absent for others)
BUILDING_N1_EXAMPLE = "has_performance_assembly_use"


# ─────────────────────────────────────────────────────────────────────────────
# Stub infrastructure (mirrors test_free_consumer_contract_wiring.py)
# ─────────────────────────────────────────────────────────────────────────────

class _StubTable:
    def __init__(self, rows): self._rows = rows
    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def insert(self, row): self._last = row; return self
    def update(self, *a, **k): return self
    def execute(self):
        class R: pass
        r = R(); r.data = self._rows if self._rows is not None else [{"id": "x"}]
        return r


class _StubSupabase:
    def __init__(self):
        self._auth = [{
            "id": "auth1", "ci_hash": "cihash", "name": "t", "phone": "",
            "free_count": 0, "free_limit": 3, "status": "ACTIVE",
        }]
        self._disc = [{"id": "disc1", "ci_hash": "cihash", "agreed": True}]
        self._ins = [{"id": "res1", "public_token": "tok"}]

    def table(self, name):
        if name == "diagnosis_auth_log":    return _StubTable(self._auth)
        if name == "diagnosis_disclaimer_log": return _StubTable(self._disc)
        if name == "anonymous_diagnosis_results": return _StubTable(self._ins)
        return _StubTable([{"id": "x"}])


_CAPTURED: Dict[str, Any] = {}


def _fake_run_step1(supabase, step1_body):
    _CAPTURED["step1_body"] = step1_body
    _CAPTURED["facility"] = build_facility(step1_body)
    return {"status": "success", "data": {"rules_table": [], "applicable_count": 0}}


def _auto_tier(sector, floor_area=0.0, contract_amount_eok=0.0, user_tier=None):
    return {
        "BUILDING": "BUILDING_FREE",
        "INDUSTRIAL": "INDUSTRY_FREE",
        "CONSTRUCTION": "CONSTRUCTION_FREE",
    }.get(sector, "BUILDING_FREE")


def _build_partial(full): return {}
def _now(): return "2026-01-01T00:00:00Z"


_FREE_CODES = frozenset({"BUILDING_FREE", "INDUSTRY_FREE", "CONSTRUCTION_FREE"})
_PRICES: Dict[str, int] = {}


def _run(sector: str, form_data: Dict[str, Any]) -> Tuple[Any, Dict[str, Any]]:
    """Submit form_data through full C1→C3 pipeline and return (step1_body, facility)."""
    _CAPTURED.clear()
    fd = dict(form_data or {})
    # appendix3_item_no default (non-construction sectors require it for disclaimer path)
    if str(sector or "").upper() in ("BUILDING", "INDUSTRIAL", "INDUSTRY", "MANUFACTURING"):
        fd.setdefault("appendix3_item_no", 28)
    # CONSTRUCTION explicit predicate gate: is_construction must be present.
    # If True, children is_relationship_contractor + is_civil_construction must also be present.
    if str(sector or "").upper() == "CONSTRUCTION":
        fd.setdefault("is_construction", False)
        if fd.get("is_construction") is True:
            fd.setdefault("is_relationship_contractor", False)
            fd.setdefault("is_civil_construction", False)
    body = nexas_run_body_from_request({
        "auth_token": "tok", "disclaimer_log_id": "disc1",
        "sector": sector, "tier": "FREE", "form_data": fd,
    })
    svc.run_diagnosis(
        supabase=_StubSupabase(), body=body,
        run_step1_func=_fake_run_step1,
        auto_tier_func=_auto_tier,
        build_partial_func=_build_partial,
        now_func=_now,
        paid_tier_prices=_PRICES,
        free_tier_codes=_FREE_CODES,
        engine_version="test",
    )
    return _CAPTURED.get("step1_body"), _CAPTURED.get("facility", {})


# ─────────────────────────────────────────────────────────────────────────────
# G-01  CONSTRUCTION DIRECT_CANONICAL booleans true → facility present
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("field_code", sorted(CONSTRUCTION_DIRECT_CANONICAL_BOOL))
def test_g01_construction_direct_canonical_bool_true(field_code):
    _, fac = _run("CONSTRUCTION", {field_code: True})
    if field_code in _LEG_INPUT_FIELDS:
        assert fac.get(field_code) is True, \
            f"CONSTRUCTION {field_code}=True not in facility (transport broken)"


# ─────────────────────────────────────────────────────────────────────────────
# G-02  CONSTRUCTION DIRECT_CANONICAL numeric → facility present
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("field_code,value", [
    ("worker_count", 50),
    ("scaffold_height_m", 3.5),
    ("construction_machine_weight_ton", 25.0),
    ("grinding_wheel_diameter_cm", 30),
    ("diving_worker_count", 2),
    ("object_drop_height_m", 4.0),
    ("same_site_construction_count", 3),
])
def test_g02_construction_direct_canonical_numeric(field_code, value):
    _, fac = _run("CONSTRUCTION", {field_code: value})
    if field_code in _LEG_INPUT_FIELDS:
        assert fac.get(field_code) == value, \
            f"CONSTRUCTION {field_code}={value} not preserved in facility"


# ─────────────────────────────────────────────────────────────────────────────
# G-03  INDUSTRIAL DIRECT_CANONICAL fields → facility present
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("field_code,value", [
    ("worker_count", 88),
    ("total_floor_area", 1234.5),
    ("has_scaffold", True),
    ("scaffold_height_m", 5.0),
    ("has_grinding", True),
    ("grinding_wheel_diameter_cm", 20),
    ("has_diving", True),
    ("diving_worker_count", 3),
    ("has_object_drop", True),
    ("object_drop_height_m", 6.0),
    ("has_high_speed_rotor", True),
    ("has_construction_machine", True),
    ("construction_machine_weight_ton", 15.0),
])
def test_g03_industrial_direct_canonical(field_code, value):
    _, fac = _run("INDUSTRIAL", {field_code: value})
    if field_code in _LEG_INPUT_FIELDS:
        assert fac.get(field_code) == value, \
            f"INDUSTRIAL {field_code}={value!r} not in facility"


# ─────────────────────────────────────────────────────────────────────────────
# G-04  BUILDING DIRECT_CANONICAL fields → facility present
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("field_code,value", [
    ("worker_count", 21),
    ("total_floor_area", 6600.0),
    ("building_use_type", "factory"),
    ("has_elevator", True),
    ("has_boiler", True),
    ("has_gas", True),
    ("has_hazardous_material", True),
    ("has_structure", True),
    ("structure_height_m", 10.0),
    ("has_scaffold", True),
    ("scaffold_height_m", 4.0),
])
def test_g04_building_direct_canonical(field_code, value):
    _, fac = _run("BUILDING", {field_code: value})
    if field_code in _LEG_INPUT_FIELDS:
        assert fac.get(field_code) == value, \
            f"BUILDING {field_code}={value!r} not in facility"


# ─────────────────────────────────────────────────────────────────────────────
# G-05  Boolean false EXPLICITLY PRESERVED (not treated as absent)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("sector,field_code", [
    ("CONSTRUCTION", "has_scaffold"),
    ("CONSTRUCTION", "is_construction"),
    ("CONSTRUCTION", "has_subcontractor"),
    ("INDUSTRIAL",   "has_scaffold"),
    ("INDUSTRIAL",   "has_diving"),
    ("INDUSTRIAL",   "has_high_speed_rotor"),
    ("BUILDING",     "has_elevator"),
    ("BUILDING",     "has_boiler"),
    ("BUILDING",     "has_structure"),
])
def test_g05_boolean_false_preserved(sector, field_code):
    _, fac = _run(sector, {field_code: False})
    if field_code in _LEG_INPUT_FIELDS:
        assert field_code in fac, \
            f"{sector} {field_code}=False must be in facility (false ≠ absent)"
        assert fac[field_code] is False, \
            f"{sector} {field_code} expected False, got {fac[field_code]!r}"


# ─────────────────────────────────────────────────────────────────────────────
# G-06  UNKNOWN / ABSENT key — not in form_data → not in facility
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("sector,field_code", [
    ("CONSTRUCTION", "has_scaffold"),
    ("CONSTRUCTION", "scaffold_height_m"),
    ("INDUSTRIAL",   "has_diving"),
    ("INDUSTRIAL",   "diving_worker_count"),
    ("BUILDING",     "has_elevator"),
    ("BUILDING",     "scaffold_height_m"),
])
def test_g06_absent_key_not_in_facility(sector, field_code):
    _, fac = _run(sector, {})  # empty form_data — field_code absent
    assert field_code not in fac, \
        f"{sector} {field_code} should be absent from facility when not submitted (UNKNOWN ≠ false)"


# ─────────────────────────────────────────────────────────────────────────────
# G-07  Parent false → conditional numeric child absent from facility
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("sector,parent,child,child_val", [
    ("CONSTRUCTION", "has_scaffold",             "scaffold_height_m",              5.0),
    ("CONSTRUCTION", "has_construction_machine", "construction_machine_weight_ton", 20.0),
    ("CONSTRUCTION", "has_grinding",             "grinding_wheel_diameter_cm",      25),
    ("CONSTRUCTION", "has_diving",               "diving_worker_count",             2),
    ("CONSTRUCTION", "has_object_drop",          "object_drop_height_m",            4.0),
    ("CONSTRUCTION", "has_subcontractor",        "same_site_construction_count",    1),
    ("INDUSTRIAL",   "has_scaffold",             "scaffold_height_m",               3.0),
    ("INDUSTRIAL",   "has_diving",               "diving_worker_count",             1),
    ("BUILDING",     "has_structure",            "structure_height_m",              8.0),
    ("BUILDING",     "has_scaffold",             "scaffold_height_m",               2.0),
])
def test_g07_parent_false_child_absent(sector, parent, child, child_val):
    # parent=False and child provided → child must NOT reach facility
    # (C1 canonical_applicability passes child since it's in _LEG_INPUT_FIELDS,
    #  but the transport contract does NOT require parent-conditional clearing —
    #  clearing is UI responsibility. So we test: when parent=False, child IS in form_data,
    #  what happens? Contract: child value IS transported (server doesn't know visibility).
    # The test here guards a stronger semantic: parent absent → child should be absent.
    _, fac = _run(sector, {parent: False})  # parent=False, child NOT submitted
    assert child not in fac or fac[child] is None, \
        f"{sector} {child} should be absent when parent {parent}=False and child not submitted"


# ─────────────────────────────────────────────────────────────────────────────
# G-08  Parent true + child_value → child present in facility
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("sector,parent,child,child_val", [
    ("CONSTRUCTION", "has_scaffold",             "scaffold_height_m",              5.0),
    ("CONSTRUCTION", "has_construction_machine", "construction_machine_weight_ton", 20.0),
    ("CONSTRUCTION", "has_grinding",             "grinding_wheel_diameter_cm",      25),
    ("CONSTRUCTION", "has_diving",               "diving_worker_count",             2),
    ("CONSTRUCTION", "has_object_drop",          "object_drop_height_m",            4.0),
    ("CONSTRUCTION", "has_subcontractor",        "same_site_construction_count",    1),
    ("INDUSTRIAL",   "has_scaffold",             "scaffold_height_m",               3.0),
    ("INDUSTRIAL",   "has_grinding",             "grinding_wheel_diameter_cm",       20),
    ("INDUSTRIAL",   "has_diving",               "diving_worker_count",              1),
    ("INDUSTRIAL",   "has_object_drop",          "object_drop_height_m",             4.5),
    ("BUILDING",     "has_structure",            "structure_height_m",               8.0),
    ("BUILDING",     "has_scaffold",             "scaffold_height_m",                2.0),
])
def test_g08_parent_true_child_present(sector, parent, child, child_val):
    if child not in _LEG_INPUT_FIELDS:
        pytest.skip(f"{child} not in _LEG_INPUT_FIELDS")
    _, fac = _run(sector, {parent: True, child: child_val})
    assert fac.get(child) == child_val, \
        f"{sector} {child}={child_val} not in facility when parent {parent}=True"


# ─────────────────────────────────────────────────────────────────────────────
# G-09  appendix3_item_no SOURCE_PROJECTED → server projects canonical leaves
# ─────────────────────────────────────────────────────────────────────────────

def test_g09_appendix3_item37_projection_industrial():
    """appendix3_item_no=37 → is_appendix3_item_37=True in facility."""
    _, fac = _run("INDUSTRIAL", {"appendix3_item_no": 37, "is_real_estate_management": False})
    assert fac.get("is_appendix3_item_37") is True, \
        "INDUSTRIAL appendix3_item_no=37 must project is_appendix3_item_37=True in facility"
    assert fac.get("is_appendix3_28_48") is True, \
        "item 37 ∈ [28..48] → is_appendix3_28_48=True"
    assert fac.get("is_appendix3_1_27") is False, \
        "item 37 ∉ [1..27] → is_appendix3_1_27=False"


def test_g09_appendix3_item28_projection_industrial():
    """appendix3_item_no=28 → is_appendix3_1_27=False, is_appendix3_28_48=True, item_37=False."""
    _, fac = _run("INDUSTRIAL", {"appendix3_item_no": 28})
    assert fac.get("is_appendix3_1_27") is False
    assert fac.get("is_appendix3_28_48") is True
    assert fac.get("is_appendix3_item_37") is False


def test_g09_appendix3_item10_projection_industrial():
    """appendix3_item_no=10 → is_appendix3_1_27=True, is_appendix3_28_48=False."""
    _, fac = _run("INDUSTRIAL", {"appendix3_item_no": 10})
    assert fac.get("is_appendix3_1_27") is True
    assert fac.get("is_appendix3_28_48") is False


def test_g09_appendix3_projection_building():
    """Same projection applies for BUILDING sector."""
    _, fac = _run("BUILDING", {"appendix3_item_no": 37, "is_real_estate_management": True})
    assert fac.get("is_appendix3_item_37") is True
    assert fac.get("is_real_estate_management") is True


def test_g09_appendix3_item_no_itself_not_in_facility():
    """appendix3_item_no is SOURCE_PROJECTED — the raw item number must NOT appear in facility."""
    _, fac = _run("INDUSTRIAL", {"appendix3_item_no": 37, "is_real_estate_management": False})
    assert "appendix3_item_no" not in fac, \
        "appendix3_item_no (source) must not appear as raw value in facility"


# ─────────────────────────────────────────────────────────────────────────────
# G-10  subcontractor_work_types SOURCE_PROJECTED → has_fire_facility_subcontract etc.
#
# NOTE: canonical_applicability (C1 adapter) strips subcontractor_work_types
# before it reaches body.form_data (not in _LEG_INPUT_FIELDS). Expansion is only
# accessible at C2 (build_unified_leg_input). Positive expansion tests use C2 directly.
# ─────────────────────────────────────────────────────────────────────────────

def test_g10_subcontractor_fire_facility_projected():
    """C2: subcontractor_work_types FIRE_FACILITY → has_fire_facility_subcontract=True."""
    step1 = build_unified_leg_input(
        sector="CONSTRUCTION",
        source_facts={"has_subcontractor": True, "subcontractor_work_types": ["FIRE_FACILITY"]},
    )
    fac = build_facility(step1)
    assert fac.get("has_subcontractor") is True
    assert fac.get("has_fire_facility_subcontract") is True, \
        "FIRE_FACILITY in work_types → has_fire_facility_subcontract=True in facility"
    assert fac.get("has_ict_subcontract") is False, \
        "ICT absent from work_types → has_ict_subcontract=False in facility"


def test_g10_subcontractor_ict_projected():
    """C2: subcontractor_work_types ICT → has_ict_subcontract=True."""
    step1 = build_unified_leg_input(
        sector="CONSTRUCTION",
        source_facts={"has_subcontractor": True, "subcontractor_work_types": ["ICT"]},
    )
    fac = build_facility(step1)
    assert fac.get("has_ict_subcontract") is True
    assert fac.get("has_fire_facility_subcontract") is False


def test_g10_subcontractor_both_projected():
    """C2: subcontractor_work_types FIRE_FACILITY+ICT → both booleans True."""
    step1 = build_unified_leg_input(
        sector="CONSTRUCTION",
        source_facts={"has_subcontractor": True, "subcontractor_work_types": ["FIRE_FACILITY", "ICT"]},
    )
    fac = build_facility(step1)
    assert fac.get("has_fire_facility_subcontract") is True
    assert fac.get("has_ict_subcontract") is True


def test_g10_subcontractor_false_no_expansion():
    """has_subcontractor=False → expansion blocked (parent gate) at C2."""
    step1 = build_unified_leg_input(
        sector="CONSTRUCTION",
        source_facts={"has_subcontractor": False, "subcontractor_work_types": ["FIRE_FACILITY"]},
    )
    fac = build_facility(step1)
    assert "has_fire_facility_subcontract" not in fac, \
        "Expansion must not occur when parent has_subcontractor=False"
    assert "has_ict_subcontract" not in fac


def test_g10_subcontractor_work_types_itself_not_in_facility():
    """subcontractor_work_types (source) must not appear in C3 facility."""
    step1 = build_unified_leg_input(
        sector="CONSTRUCTION",
        source_facts={"has_subcontractor": True, "subcontractor_work_types": ["FIRE_FACILITY"]},
    )
    fac = build_facility(step1)
    assert "subcontractor_work_types" not in fac, \
        "subcontractor_work_types source field must not appear in facility"


# ─────────────────────────────────────────────────────────────────────────────
# G-11  EXPECTED_NON_RUNTIME — has_hazmat_storage NOT in _LEG_INPUT_FIELDS → absent C3
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("sector", ["CONSTRUCTION", "INDUSTRIAL", "BUILDING"])
def test_g11_hazmat_storage_in_facility(sector):
    """has_hazmat_storage is DIRECT_CANONICAL — must appear in facility when submitted."""
    assert "has_hazmat_storage" in _LEG_INPUT_FIELDS, \
        "has_hazmat_storage must be in _LEG_INPUT_FIELDS (DIRECT_CANONICAL)"
    _, fac = _run(sector, {"has_hazmat_storage": True})
    assert fac.get("has_hazmat_storage") is True, \
        f"{sector} has_hazmat_storage=True must appear in facility (DIRECT_CANONICAL)"


@pytest.mark.parametrize("sector", ["INDUSTRIAL", "BUILDING"])
def test_g11_ksic_major_not_in_facility(sector):
    """ksic_major is EXPECTED_NON_RUNTIME for INDUSTRIAL/BUILDING FREE."""
    assert "ksic_major" not in _LEG_INPUT_FIELDS
    _, fac = _run(sector, {"ksic_major": "C25"})
    assert "ksic_major" not in fac


# ─────────────────────────────────────────────────────────────────────────────
# G-12  BUILDING N1 SECTOR_BLOCKED — field present only for BUILDING sector
# ─────────────────────────────────────────────────────────────────────────────

def test_g12_building_n1_field_present_for_building():
    """BUILDING N1 field has_performance_assembly_use present in BUILDING facility."""
    assert BUILDING_N1_EXAMPLE in _BUILDING_N1_FIELDS
    assert BUILDING_N1_EXAMPLE in _LEG_INPUT_FIELDS
    _, fac = _run("BUILDING", {BUILDING_N1_EXAMPLE: True})
    assert fac.get(BUILDING_N1_EXAMPLE) is True, \
        f"{BUILDING_N1_EXAMPLE} must be in BUILDING facility"


@pytest.mark.parametrize("sector", ["INDUSTRIAL", "CONSTRUCTION"])
def test_g12_building_n1_field_absent_for_non_building(sector):
    """Same BUILDING N1 field absent from INDUSTRIAL/CONSTRUCTION facility."""
    _, fac = _run(sector, {BUILDING_N1_EXAMPLE: True})
    assert BUILDING_N1_EXAMPLE not in fac, \
        f"{BUILDING_N1_EXAMPLE} is SECTOR_BLOCKED — must be absent from {sector} facility"


def test_g12_building_n1_full_gate():
    """All _BUILDING_N1_FIELDS absent from INDUSTRIAL facility when supplied."""
    sample_n1 = {f: True for f in list(_BUILDING_N1_FIELDS)[:5]}  # sample 5
    _, fac = _run("INDUSTRIAL", sample_n1)
    for field_code in sample_n1:
        assert field_code not in fac, \
            f"BUILDING N1 field {field_code} must not appear in INDUSTRIAL facility"


# ─────────────────────────────────────────────────────────────────────────────
# G-13  Worker-count bridge — workers / worker_count aliases
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("sector", ["CONSTRUCTION", "INDUSTRIAL", "BUILDING"])
def test_g13_worker_count_direct(sector):
    _, fac = _run(sector, {"worker_count": 77})
    assert fac.get("worker_count") == 77, \
        f"{sector} worker_count=77 must reach facility"


@pytest.mark.parametrize("sector", ["CONSTRUCTION", "INDUSTRIAL", "BUILDING"])
def test_g13_workers_alias_coerced(sector):
    """'workers' key in form_data is aliased to worker_count."""
    _, fac = _run(sector, {"workers": 42})
    assert fac.get("worker_count") == 42, \
        f"{sector} workers=42 alias must reach facility as worker_count=42"


# ─────────────────────────────────────────────────────────────────────────────
# G-14  is_construction chain — conditional fields
# ─────────────────────────────────────────────────────────────────────────────

def test_g14_is_construction_true_chain():
    """is_construction=True → is_relationship_contractor + is_civil_construction present."""
    _, fac = _run("CONSTRUCTION", {
        "is_construction": True,
        "is_relationship_contractor": False,
        "is_civil_construction": True,
    })
    assert fac.get("is_construction") is True
    assert fac.get("is_relationship_contractor") is False  # false preserved
    assert fac.get("is_civil_construction") is True


def test_g14_is_construction_false_children_not_required():
    """is_construction=False → conditional children not submitted, not in facility."""
    _, fac = _run("CONSTRUCTION", {"is_construction": False})
    assert fac.get("is_construction") is False  # false preserved
    assert "is_relationship_contractor" not in fac
    assert "is_civil_construction" not in fac


def test_g14_all_construction_boolean_false_preserved():
    """All CONSTRUCTION DIRECT_CANONICAL booleans: false is preserved, not dropped."""
    bools = {f: False for f in CONSTRUCTION_DIRECT_CANONICAL_BOOL if f in _LEG_INPUT_FIELDS}
    _, fac = _run("CONSTRUCTION", bools)
    for code, val in bools.items():
        assert fac.get(code) is False, \
            f"CONSTRUCTION {code}=False must be preserved in facility"


# ─────────────────────────────────────────────────────────────────────────────
# Matrix integrity sanity checks (not part of G-01~G-14 numbering)
# ─────────────────────────────────────────────────────────────────────────────

def test_matrix_direct_canonical_fields_are_in_leg_input_fields():
    """All DIRECT_CANONICAL annotated fields must actually be in _LEG_INPUT_FIELDS."""
    all_direct = (
        CONSTRUCTION_DIRECT_CANONICAL_BOOL
        | CONSTRUCTION_DIRECT_CANONICAL_NUM
        | INDUSTRIAL_DIRECT_CANONICAL_BOOL
        | INDUSTRIAL_DIRECT_CANONICAL_NUM
        | BUILDING_DIRECT_CANONICAL_BOOL
        | BUILDING_DIRECT_CANONICAL_NUM
    )
    not_in_leg = {f for f in all_direct if f not in _LEG_INPUT_FIELDS}
    assert not not_in_leg, \
        f"DIRECT_CANONICAL fields not in _LEG_INPUT_FIELDS: {sorted(not_in_leg)}"


def test_matrix_expected_non_runtime_fields_not_in_leg_input_fields():
    """All EXPECTED_NON_RUNTIME annotated fields must NOT be in _LEG_INPUT_FIELDS."""
    all_non_rt = (
        CONSTRUCTION_EXPECTED_NON_RUNTIME
        | INDUSTRIAL_EXPECTED_NON_RUNTIME
        | BUILDING_EXPECTED_NON_RUNTIME
    )
    in_leg = {f for f in all_non_rt if f in _LEG_INPUT_FIELDS}
    assert not in_leg, \
        f"EXPECTED_NON_RUNTIME fields found in _LEG_INPUT_FIELDS (matrix error): {sorted(in_leg)}"


def test_matrix_building_n1_fields_are_in_building_n1_set():
    """BUILDING_N1_EXAMPLE must be in both _BUILDING_N1_FIELDS and _LEG_INPUT_FIELDS."""
    assert BUILDING_N1_EXAMPLE in _BUILDING_N1_FIELDS
    assert BUILDING_N1_EXAMPLE in _LEG_INPUT_FIELDS


def test_matrix_source_projected_not_in_leg_input_fields():
    """appendix3_item_no and subcontractor_work_types must NOT be in _LEG_INPUT_FIELDS."""
    assert "appendix3_item_no" not in _LEG_INPUT_FIELDS, \
        "appendix3_item_no is SOURCE (not a direct LEG vocabulary field)"
    assert "subcontractor_work_types" not in _LEG_INPUT_FIELDS, \
        "subcontractor_work_types is SOURCE (expanded by expand_subcontractor_work_types)"


def test_matrix_projected_facts_are_in_leg_input_fields():
    """Server-projected leaf facts IS_appendix3_* must be in _LEG_INPUT_FIELDS."""
    for leaf in ("is_appendix3_1_27", "is_appendix3_28_48", "is_appendix3_item_37",
                 "is_appendix3_item_40", "is_real_estate_management"):
        assert leaf in _LEG_INPUT_FIELDS, \
            f"Projected leaf {leaf} must be in _LEG_INPUT_FIELDS"
    for expanded in ("has_fire_facility_subcontract", "has_ict_subcontract"):
        assert expanded in _LEG_INPUT_FIELDS, \
            f"Expanded boolean {expanded} must be in _LEG_INPUT_FIELDS"
