"""tests/test_free_consumer_c1_c3_guard.py
WO-CONSUMER-PIPELINE-FREE-PROFILE-001 PHASE-4 CORRECTION —
FREE C1→C3 Consumer Contract Coverage Guard.

TEST CONTRACT SNAPSHOT ONLY
Operational SoT = public.diagnosis_input_fields
Snapshot date  = 2026-10-04

Assembly path: official /diagnosis/run-leg
  C1 form_data (raw DiagnosisRunBody.form_data)
  → run_diagnosis(..., unified_step1_factory_func=build_unified_leg_input)
  → canonical_applicability / appendix3 projection
  → _build_unified_step1_body → build_unified_leg_input
  → build_facility → C3 facility dict

5 Transport classifications:
  DIRECT_CANONICAL              — ∈ _LEG_INPUT_FIELDS; C1 value verbatim in C3 facility.
  DIRECT_CANONICAL_BUILDING_SECTOR — ∈ _LEG_INPUT_FIELDS + _BUILDING_N1_FIELDS; BUILDING only.
  SOURCE_PROJECTED              — C1 source → server projection → C3 domain fact.
  EXPECTED_NON_RUNTIME          — NOT ∈ _LEG_INPUT_FIELDS; C3 facility ABSENT.
  SECTOR_BLOCKED_EXPECTED       — ∈ _BUILDING_N1_FIELDS; BUILDING present, others absent.

Test groups G-01~G-14:
  G-01  BUILDING DIRECT_CANONICAL → facility present
  G-02  INDUSTRIAL DIRECT_CANONICAL → facility present
  G-03  CONSTRUCTION DIRECT_CANONICAL → facility present
  G-04  Boolean false EXPLICITLY PRESERVED (false ≠ absent)
  G-05  EXPECTED_NON_RUNTIME fields absent from facility
  G-06  Absent key (not submitted) → absent from facility
  G-07  SECTOR_BLOCKED: floor_count BUILDING present / INDUSTRIAL absent
  G-08  appendix3_item_no DIRECT_CANONICAL + canonical leaf projection
  G-09  project_amount SOURCE_PROJECTED → contract_amount_eok (CONSTRUCTION)
  G-10  subcontractor_work_types SOURCE_PROJECTED → domain booleans (full C1 path)
  G-11  Parent false → conditional numeric child absent from facility
  G-12  Parent true + child value → child present in facility
  G-13  is_construction explicit predicate chain
  G-14  Matrix integrity: 59/59 FREE snapshot classified exactly once
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

import pytest

from clients.leg_runtime_client import (
    _BUILDING_N1_FIELDS,
    _LEG_INPUT_FIELDS,
    build_facility,
)
from schemas.diagnosis_integrated import DiagnosisRunBody
from services import diagnosis_integrated_svc as svc
from services.canonical.leg_input_contract import build_unified_leg_input


# ─────────────────────────────────────────────────────────────────────────────
# FREE SNAPSHOT — 2026-10-04
# Tuple: (source_field_code, classification, representative_test_value)
# Classification: DIRECT_CANONICAL / DIRECT_CANONICAL_BUILDING_SECTOR /
#                 SOURCE_PROJECTED / EXPECTED_NON_RUNTIME / SECTOR_BLOCKED_EXPECTED
# ─────────────────────────────────────────────────────────────────────────────

BUILDING_FREE_SNAPSHOT: List[Tuple[str, str, Any]] = [
    # (field_code,                     classification,                      test_value)
    ("address",                        "EXPECTED_NON_RUNTIME",              "서울시 강남구"),
    ("total_floor_area",               "DIRECT_CANONICAL",                  5000.0),
    ("floor_count",                    "DIRECT_CANONICAL_BUILDING_SECTOR",  7),
    ("basement_count",                 "EXPECTED_NON_RUNTIME",              2),
    ("building_use_type",              "DIRECT_CANONICAL",                  "factory"),
    ("built_year",                     "EXPECTED_NON_RUNTIME",              2010),
    ("main_structure",                 "EXPECTED_NON_RUNTIME",              "철근콘크리트"),
    ("worker_count",                   "DIRECT_CANONICAL",                  30),
    ("appendix3_item_no",              "DIRECT_CANONICAL",                  28),
    ("is_real_estate_management",      "DIRECT_CANONICAL",                  False),
    ("has_structure",                  "DIRECT_CANONICAL",                  True),
    ("structure_height_m",             "DIRECT_CANONICAL",                  8.0),
    ("has_hazmat_storage",             "DIRECT_CANONICAL",                  True),
    ("has_scaffold",                   "DIRECT_CANONICAL",                  True),
    ("scaffold_height_m",              "DIRECT_CANONICAL",                  3.0),
]  # 15 rows

INDUSTRIAL_FREE_SNAPSHOT: List[Tuple[str, str, Any]] = [
    ("address",                        "EXPECTED_NON_RUNTIME",              "서울시 강남구"),
    ("ksic_major",                     "EXPECTED_NON_RUNTIME",              "C25"),
    ("worker_count",                   "DIRECT_CANONICAL",                  50),
    ("total_floor_area",               "DIRECT_CANONICAL",                  2000.0),
    ("floor_count",                    "SECTOR_BLOCKED_EXPECTED",           5),
    ("basement_count",                 "EXPECTED_NON_RUNTIME",              1),
    ("building_use_type",              "DIRECT_CANONICAL",                  "factory"),
    ("built_year",                     "EXPECTED_NON_RUNTIME",              2015),
    ("main_structure",                 "EXPECTED_NON_RUNTIME",              "철근콘크리트"),
    ("appendix3_item_no",              "DIRECT_CANONICAL",                  28),
    ("is_real_estate_management",      "DIRECT_CANONICAL",                  False),
    ("has_scaffold",                   "DIRECT_CANONICAL",                  True),
    ("scaffold_height_m",              "DIRECT_CANONICAL",                  4.0),
    ("has_grinding",                   "DIRECT_CANONICAL",                  True),
    ("grinding_wheel_diameter_cm",     "DIRECT_CANONICAL",                  20),
    ("has_diving",                     "DIRECT_CANONICAL",                  True),
    ("diving_worker_count",            "DIRECT_CANONICAL",                  2),
    ("has_object_drop",                "DIRECT_CANONICAL",                  True),
    ("object_drop_height_m",           "DIRECT_CANONICAL",                  5.0),
    ("has_high_speed_rotor",           "DIRECT_CANONICAL",                  True),
    ("has_construction_machine",       "DIRECT_CANONICAL",                  True),
    ("construction_machine_weight_ton","DIRECT_CANONICAL",                  15.0),
    ("has_hazmat_storage",             "DIRECT_CANONICAL",                  True),
]  # 23 rows

CONSTRUCTION_FREE_SNAPSHOT: List[Tuple[str, str, Any]] = [
    ("project_address",                "EXPECTED_NON_RUNTIME",              "경기도 성남시"),
    ("project_amount",                 "SOURCE_PROJECTED",                  50.0),
    ("worker_count",                   "DIRECT_CANONICAL",                  40),
    ("appendix3_item_no",              "DIRECT_CANONICAL",                  48),
    ("is_construction",                "DIRECT_CANONICAL",                  False),
    ("is_relationship_contractor",     "DIRECT_CANONICAL",                  False),
    ("is_civil_construction",          "DIRECT_CANONICAL",                  False),
    ("has_construction_machine",       "DIRECT_CANONICAL",                  True),
    ("construction_machine_weight_ton","DIRECT_CANONICAL",                  25.0),
    ("has_hazmat_storage",             "DIRECT_CANONICAL",                  True),
    ("has_scaffold",                   "DIRECT_CANONICAL",                  True),
    ("scaffold_height_m",              "DIRECT_CANONICAL",                  5.0),
    ("has_grinding",                   "DIRECT_CANONICAL",                  True),
    ("grinding_wheel_diameter_cm",     "DIRECT_CANONICAL",                  30),
    ("has_diving",                     "DIRECT_CANONICAL",                  True),
    ("diving_worker_count",            "DIRECT_CANONICAL",                  3),
    ("has_subcontractor",              "DIRECT_CANONICAL",                  True),
    ("same_site_construction_count",   "DIRECT_CANONICAL",                  2),
    ("has_object_drop",                "DIRECT_CANONICAL",                  True),
    ("object_drop_height_m",           "DIRECT_CANONICAL",                  4.0),
    ("subcontractor_work_types",       "SOURCE_PROJECTED",                  ["FIRE_FACILITY"]),
]  # 21 rows


def _by_class(snapshot: List[Tuple[str, str, Any]], classification: str) -> List[Tuple[str, Any]]:
    return [(f, v) for f, c, v in snapshot if c == classification]


# ─────────────────────────────────────────────────────────────────────────────
# Stub infrastructure
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
        if name == "diagnosis_auth_log":       return _StubTable(self._auth)
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
    """Official /diagnosis/run-leg assembly path: raw DiagnosisRunBody + build_unified_leg_input.

    Mirrors: routers/diagnosis_integrated_leg.py _run_leg_impl()
      body = DiagnosisRunBody (no nexas adapter)
      run_diagnosis(..., unified_step1_factory_func=build_unified_leg_input)

    Test baseline pre-conditions (NOT production defaults, NOT server synthesized):
      CONSTRUCTION: appendix3_item_no=48 required by appendix3 validation gate.
        If appendix3_item_no=49 is explicitly set, is_relationship_contractor
        and is_civil_construction must also be supplied.
      BUILDING/INDUSTRIAL: appendix3_item_no=28 required by appendix3 validation gate.
    """
    _CAPTURED.clear()
    fd = dict(form_data or {})

    # TEST BASELINE REQUIRED INPUT — NOT production default, NOT server synthesized fact.
    if str(sector or "").upper() in ("BUILDING", "INDUSTRIAL", "INDUSTRY", "MANUFACTURING"):
        fd.setdefault("appendix3_item_no", 28)
    if str(sector or "").upper() == "CONSTRUCTION":
        fd.setdefault("appendix3_item_no", 48)   # TEST BASELINE REQUIRED INPUT
        if fd.get("appendix3_item_no") == 49:
            fd.setdefault("is_relationship_contractor", False)   # TEST BASELINE REQUIRED INPUT
            fd.setdefault("is_civil_construction", False)        # TEST BASELINE REQUIRED INPUT

    # Official /run-leg path: raw DiagnosisRunBody, no nexas adapter
    body = DiagnosisRunBody(
        auth_token="tok",
        disclaimer_log_id="disc1",
        sector=sector,
        form_data=fd,
    )
    svc.run_diagnosis(
        supabase=_StubSupabase(),
        body=body,
        run_step1_func=_fake_run_step1,
        auto_tier_func=_auto_tier,
        build_partial_func=_build_partial,
        now_func=_now,
        paid_tier_prices=_PRICES,
        free_tier_codes=_FREE_CODES,
        engine_version="test",
        unified_step1_factory_func=build_unified_leg_input,
    )
    return _CAPTURED.get("step1_body"), _CAPTURED.get("facility", {})


# ─────────────────────────────────────────────────────────────────────────────
# G-01  BUILDING DIRECT_CANONICAL → facility present
# ─────────────────────────────────────────────────────────────────────────────

# is_real_estate_management tested separately in G-08 (requires appendix3_item_no=37 context)
_BUILDING_DC_SIMPLE = [
    (f, v) for f, v in _by_class(BUILDING_FREE_SNAPSHOT, "DIRECT_CANONICAL")
    if f != "is_real_estate_management"
]


@pytest.mark.parametrize("field_code,value", _BUILDING_DC_SIMPLE)
def test_g01_building_direct_canonical(field_code, value):
    _, fac = _run("BUILDING", {field_code: value})
    assert fac.get(field_code) == value, \
        f"BUILDING {field_code}={value!r} must appear in C3 facility (DIRECT_CANONICAL)"


# ─────────────────────────────────────────────────────────────────────────────
# G-02  INDUSTRIAL DIRECT_CANONICAL → facility present
# ─────────────────────────────────────────────────────────────────────────────

# is_real_estate_management tested in G-08; floor_count tested in G-07
_INDUSTRIAL_DC_SIMPLE = [
    (f, v) for f, v in _by_class(INDUSTRIAL_FREE_SNAPSHOT, "DIRECT_CANONICAL")
    if f != "is_real_estate_management"
]


@pytest.mark.parametrize("field_code,value", _INDUSTRIAL_DC_SIMPLE)
def test_g02_industrial_direct_canonical(field_code, value):
    _, fac = _run("INDUSTRIAL", {field_code: value})
    assert fac.get(field_code) == value, \
        f"INDUSTRIAL {field_code}={value!r} must appear in C3 facility (DIRECT_CANONICAL)"


# ─────────────────────────────────────────────────────────────────────────────
# G-03  CONSTRUCTION DIRECT_CANONICAL → facility present
# ─────────────────────────────────────────────────────────────────────────────

# project_amount / subcontractor_work_types tested in G-09 / G-10 (SOURCE_PROJECTED)
_CONSTRUCTION_DC = _by_class(CONSTRUCTION_FREE_SNAPSHOT, "DIRECT_CANONICAL")


@pytest.mark.parametrize("field_code,value", _CONSTRUCTION_DC)
def test_g03_construction_direct_canonical(field_code, value):
    _, fac = _run("CONSTRUCTION", {field_code: value})
    assert fac.get(field_code) == value, \
        f"CONSTRUCTION {field_code}={value!r} must appear in C3 facility (DIRECT_CANONICAL)"


# ─────────────────────────────────────────────────────────────────────────────
# G-04  Boolean false EXPLICITLY PRESERVED (false ≠ absent) — all 3 sectors
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("sector,field_code", [
    ("BUILDING",     "has_structure"),
    ("BUILDING",     "has_hazmat_storage"),
    ("BUILDING",     "has_scaffold"),
    ("INDUSTRIAL",   "has_scaffold"),
    ("INDUSTRIAL",   "has_diving"),
    ("INDUSTRIAL",   "has_high_speed_rotor"),
    ("INDUSTRIAL",   "has_hazmat_storage"),
    ("CONSTRUCTION", "has_scaffold"),
    ("CONSTRUCTION", "has_subcontractor"),
    ("CONSTRUCTION", "has_hazmat_storage"),
    ("CONSTRUCTION", "is_construction"),
])
def test_g04_boolean_false_preserved(sector, field_code):
    _, fac = _run(sector, {field_code: False})
    assert field_code in fac, \
        f"{sector} {field_code}=False must be in facility (false ≠ absent)"
    assert fac[field_code] is False, \
        f"{sector} {field_code} expected False in facility, got {fac[field_code]!r}"


# ─────────────────────────────────────────────────────────────────────────────
# G-05  EXPECTED_NON_RUNTIME → NOT in facility
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("sector,field_code,value", [
    # BUILDING EXPECTED_NON_RUNTIME (4 fields)
    ("BUILDING",      "address",       "서울시 강남구"),
    ("BUILDING",      "basement_count", 2),
    ("BUILDING",      "built_year",    2010),
    ("BUILDING",      "main_structure","철근콘크리트"),
    # INDUSTRIAL EXPECTED_NON_RUNTIME (5 fields)
    ("INDUSTRIAL",    "address",       "서울시 강남구"),
    ("INDUSTRIAL",    "ksic_major",    "C25"),
    ("INDUSTRIAL",    "basement_count", 1),
    ("INDUSTRIAL",    "built_year",    2015),
    ("INDUSTRIAL",    "main_structure","철근콘크리트"),
    # CONSTRUCTION EXPECTED_NON_RUNTIME (1 field)
    ("CONSTRUCTION",  "project_address","경기도 성남시"),
])
def test_g05_expected_non_runtime_absent(sector, field_code, value):
    _, fac = _run(sector, {field_code: value})
    assert field_code not in fac, \
        f"{sector} {field_code} is EXPECTED_NON_RUNTIME — must NOT appear in C3 facility"


# ─────────────────────────────────────────────────────────────────────────────
# G-06  Absent key (not submitted) → absent from facility
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("sector,field_code", [
    ("BUILDING",      "has_scaffold"),
    ("BUILDING",      "scaffold_height_m"),
    ("INDUSTRIAL",    "has_diving"),
    ("INDUSTRIAL",    "diving_worker_count"),
    ("CONSTRUCTION",  "has_scaffold"),
    ("CONSTRUCTION",  "scaffold_height_m"),
])
def test_g06_absent_key_not_in_facility(sector, field_code):
    _, fac = _run(sector, {})  # field_code deliberately NOT submitted
    assert field_code not in fac, \
        f"{sector} {field_code} should be absent when not submitted (UNKNOWN ≠ false)"


# ─────────────────────────────────────────────────────────────────────────────
# G-07  SECTOR_BLOCKED: floor_count BUILDING present / INDUSTRIAL absent
#       (floor_count ∈ _BUILDING_N1_FIELDS → DIRECT_CANONICAL_BUILDING_SECTOR for BUILDING,
#        SECTOR_BLOCKED_EXPECTED for INDUSTRIAL)
# ─────────────────────────────────────────────────────────────────────────────

def test_g07_floor_count_present_for_building():
    """floor_count submitted to BUILDING → appears in facility (DIRECT_CANONICAL_BUILDING_SECTOR)."""
    _, fac = _run("BUILDING", {"floor_count": 7})
    assert fac.get("floor_count") == 7, \
        "BUILDING floor_count=7 must reach C3 facility (DIRECT_CANONICAL_BUILDING_SECTOR)"


def test_g07_floor_count_absent_for_industrial():
    """floor_count submitted to INDUSTRIAL → absent from facility (SECTOR_BLOCKED_EXPECTED)."""
    _, fac = _run("INDUSTRIAL", {"floor_count": 5})
    assert "floor_count" not in fac, \
        "INDUSTRIAL floor_count is SECTOR_BLOCKED_EXPECTED — must be absent from facility"


def test_g07_floor_count_absent_for_construction():
    """floor_count not in CONSTRUCTION FREE snapshot and blocked by N1 gate."""
    _, fac = _run("CONSTRUCTION", {"floor_count": 3})
    assert "floor_count" not in fac, \
        "CONSTRUCTION floor_count must be absent (BUILDING N1 gate)"


# ─────────────────────────────────────────────────────────────────────────────
# G-08  appendix3_item_no DIRECT_CANONICAL + canonical leaf projection
# ─────────────────────────────────────────────────────────────────────────────

def test_g08_appendix3_item37_projected_building():
    """BUILDING: item_no=37 → is_appendix3_item_37=True, is_real_estate_management=False."""
    _, fac = _run("BUILDING", {"appendix3_item_no": 37, "is_real_estate_management": False})
    assert fac.get("is_appendix3_item_37") is True
    assert fac.get("is_appendix3_28_48") is True
    assert fac.get("is_appendix3_1_27") is False
    assert fac.get("is_real_estate_management") is False


def test_g08_appendix3_item37_projected_industrial():
    """INDUSTRIAL: item_no=37 + is_real_estate_management=True → projected correctly."""
    _, fac = _run("INDUSTRIAL", {"appendix3_item_no": 37, "is_real_estate_management": True})
    assert fac.get("is_appendix3_item_37") is True
    assert fac.get("is_real_estate_management") is True


def test_g08_appendix3_item28_projected_industrial():
    """INDUSTRIAL: item_no=28 → is_appendix3_1_27=False, is_appendix3_28_48=True."""
    _, fac = _run("INDUSTRIAL", {"appendix3_item_no": 28})
    assert fac.get("is_appendix3_1_27") is False
    assert fac.get("is_appendix3_28_48") is True
    assert fac.get("is_appendix3_item_37") is False


def test_g08_appendix3_item10_projected_industrial():
    """INDUSTRIAL: item_no=10 → is_appendix3_1_27=True, is_appendix3_28_48=False."""
    _, fac = _run("INDUSTRIAL", {"appendix3_item_no": 10})
    assert fac.get("is_appendix3_1_27") is True
    assert fac.get("is_appendix3_28_48") is False


def test_g08_appendix3_item_no_in_facility():
    """appendix3_item_no is DIRECT_CANONICAL (∈ _LEG_INPUT_FIELDS) — appears in facility as integer."""
    _, fac = _run("INDUSTRIAL", {"appendix3_item_no": 37, "is_real_estate_management": False})
    assert "appendix3_item_no" in fac, \
        "appendix3_item_no is DIRECT_CANONICAL — must appear in facility"
    assert fac["appendix3_item_no"] == 37


# ─────────────────────────────────────────────────────────────────────────────
# G-09  project_amount SOURCE_PROJECTED → contract_amount_eok (CONSTRUCTION)
# ─────────────────────────────────────────────────────────────────────────────

def test_g09_project_amount_projects_to_contract_amount():
    """CONSTRUCTION C1 project_amount=50 → C3 contract_amount_eok=50.0."""
    _, fac = _run("CONSTRUCTION", {"project_amount": 50})
    assert fac.get("contract_amount_eok") == 50.0, \
        "CONSTRUCTION project_amount=50 must project to contract_amount_eok=50.0 in facility"


def test_g09_project_amount_itself_not_in_facility():
    """project_amount (source) must NOT appear in facility."""
    _, fac = _run("CONSTRUCTION", {"project_amount": 50})
    assert "project_amount" not in fac, \
        "project_amount source must not appear in C3 facility"


def test_g09_project_amount_zero_projects():
    """CONSTRUCTION project_amount=0 → contract_amount_eok=0.0 (zero preserved)."""
    _, fac = _run("CONSTRUCTION", {"project_amount": 0})
    assert fac.get("contract_amount_eok") == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# G-10  subcontractor_work_types SOURCE_PROJECTED — full C1 path
#       body.form_data (raw) → _build_unified_step1_body seed → expand → C3
# ─────────────────────────────────────────────────────────────────────────────

def test_g10_subcontractor_fire_facility_projected():
    """Full C1→C3: FIRE_FACILITY in work_types → has_fire_facility_subcontract=True."""
    _, fac = _run("CONSTRUCTION", {
        "has_subcontractor": True,
        "subcontractor_work_types": ["FIRE_FACILITY"],
    })
    assert fac.get("has_subcontractor") is True
    assert fac.get("has_fire_facility_subcontract") is True, \
        "FIRE_FACILITY in work_types must project has_fire_facility_subcontract=True (C1→C3)"
    assert fac.get("has_ict_subcontract") is False


def test_g10_subcontractor_ict_projected():
    """Full C1→C3: ICT in work_types → has_ict_subcontract=True."""
    _, fac = _run("CONSTRUCTION", {
        "has_subcontractor": True,
        "subcontractor_work_types": ["ICT"],
    })
    assert fac.get("has_ict_subcontract") is True
    assert fac.get("has_fire_facility_subcontract") is False


def test_g10_subcontractor_both_projected():
    """Full C1→C3: FIRE_FACILITY+ICT → both domain booleans True."""
    _, fac = _run("CONSTRUCTION", {
        "has_subcontractor": True,
        "subcontractor_work_types": ["FIRE_FACILITY", "ICT"],
    })
    assert fac.get("has_fire_facility_subcontract") is True
    assert fac.get("has_ict_subcontract") is True


def test_g10_subcontractor_false_blocks_expansion():
    """Full C1→C3: has_subcontractor=False → parent gate blocks expansion."""
    _, fac = _run("CONSTRUCTION", {
        "has_subcontractor": False,
        "subcontractor_work_types": ["FIRE_FACILITY"],
    })
    assert "has_fire_facility_subcontract" not in fac, \
        "Expansion must not fire when parent has_subcontractor=False"
    assert "has_ict_subcontract" not in fac


def test_g10_subcontractor_work_types_not_in_facility():
    """subcontractor_work_types source field must NOT appear in C3 facility."""
    _, fac = _run("CONSTRUCTION", {
        "has_subcontractor": True,
        "subcontractor_work_types": ["FIRE_FACILITY"],
    })
    assert "subcontractor_work_types" not in fac, \
        "subcontractor_work_types source must not appear in C3 facility"


# ─────────────────────────────────────────────────────────────────────────────
# G-11  Parent false → conditional numeric child absent
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("sector,parent,child", [
    ("CONSTRUCTION", "has_scaffold",             "scaffold_height_m"),
    ("CONSTRUCTION", "has_construction_machine", "construction_machine_weight_ton"),
    ("CONSTRUCTION", "has_grinding",             "grinding_wheel_diameter_cm"),
    ("CONSTRUCTION", "has_diving",               "diving_worker_count"),
    ("CONSTRUCTION", "has_object_drop",          "object_drop_height_m"),
    ("CONSTRUCTION", "has_subcontractor",        "same_site_construction_count"),
    ("INDUSTRIAL",   "has_scaffold",             "scaffold_height_m"),
    ("INDUSTRIAL",   "has_diving",               "diving_worker_count"),
    ("BUILDING",     "has_structure",            "structure_height_m"),
    ("BUILDING",     "has_scaffold",             "scaffold_height_m"),
])
def test_g11_parent_false_child_absent(sector, parent, child):
    # parent=False, child NOT submitted → child must not appear in facility
    _, fac = _run(sector, {parent: False})
    assert child not in fac, \
        f"{sector} {child} must be absent when parent {parent}=False and child not submitted"


# ─────────────────────────────────────────────────────────────────────────────
# G-12  Parent true + child value → child present in facility
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
    ("BUILDING",     "has_structure",            "structure_height_m",               8.0),
    ("BUILDING",     "has_scaffold",             "scaffold_height_m",                2.0),
])
def test_g12_parent_true_child_present(sector, parent, child, child_val):
    _, fac = _run(sector, {parent: True, child: child_val})
    assert fac.get(child) == child_val, \
        f"{sector} {child}={child_val} must appear in facility when parent {parent}=True"


# ─────────────────────────────────────────────────────────────────────────────
# G-13  is_construction explicit predicate chain (CONSTRUCTION)
# ─────────────────────────────────────────────────────────────────────────────

def test_g13_is_construction_true_chain():
    """is_construction=True + children → all three booleans in facility (false preserved)."""
    _, fac = _run("CONSTRUCTION", {
        "is_construction": True,
        "is_relationship_contractor": False,
        "is_civil_construction": True,
    })
    assert fac.get("is_construction") is True
    assert fac.get("is_relationship_contractor") is False  # false preserved
    assert fac.get("is_civil_construction") is True


def test_g13_is_construction_false_children_absent():
    """is_construction=False → predicate gate passes, children not required."""
    _, fac = _run("CONSTRUCTION", {"is_construction": False})
    assert fac.get("is_construction") is False
    assert "is_relationship_contractor" not in fac
    assert "is_civil_construction" not in fac


def test_g13_all_construction_booleans_false_preserved():
    """All CONSTRUCTION DIRECT_CANONICAL booleans: false is preserved, not dropped."""
    cst_bools = [
        "is_construction", "is_relationship_contractor", "is_civil_construction",
        "has_construction_machine", "has_hazmat_storage", "has_scaffold",
        "has_grinding", "has_diving", "has_subcontractor", "has_object_drop",
    ]
    # Submit all as False (is_construction=False satisfies predicate gate)
    form_data = {f: False for f in cst_bools}
    _, fac = _run("CONSTRUCTION", form_data)
    for code in cst_bools:
        assert fac.get(code) is False, \
            f"CONSTRUCTION {code}=False must be preserved in facility"


# ─────────────────────────────────────────────────────────────────────────────
# G-14  Matrix integrity — 59/59 FREE snapshot classified exactly once
# ─────────────────────────────────────────────────────────────────────────────

_VALID_CLASSES = {
    "DIRECT_CANONICAL",
    "DIRECT_CANONICAL_BUILDING_SECTOR",
    "SOURCE_PROJECTED",
    "EXPECTED_NON_RUNTIME",
    "SECTOR_BLOCKED_EXPECTED",
}


def _check_snapshot_integrity(snapshot: List[Tuple[str, str, Any]], label: str) -> None:
    fields = [f for f, _, _ in snapshot]
    assert len(fields) == len(set(fields)), \
        f"{label}: duplicate fields in snapshot"
    for f, c, _ in snapshot:
        assert c in _VALID_CLASSES, \
            f"{label}: unknown classification '{c}' for field '{f}'"


def test_g14_building_snapshot_15rows():
    """BUILDING FREE snapshot = exactly 15 rows."""
    assert len(BUILDING_FREE_SNAPSHOT) == 15, \
        f"BUILDING FREE snapshot must have 15 rows, got {len(BUILDING_FREE_SNAPSHOT)}"
    _check_snapshot_integrity(BUILDING_FREE_SNAPSHOT, "BUILDING")


def test_g14_industrial_snapshot_23rows():
    """INDUSTRIAL FREE snapshot = exactly 23 rows."""
    assert len(INDUSTRIAL_FREE_SNAPSHOT) == 23, \
        f"INDUSTRIAL FREE snapshot must have 23 rows, got {len(INDUSTRIAL_FREE_SNAPSHOT)}"
    _check_snapshot_integrity(INDUSTRIAL_FREE_SNAPSHOT, "INDUSTRIAL")


def test_g14_construction_snapshot_21rows():
    """CONSTRUCTION FREE snapshot = exactly 21 rows."""
    assert len(CONSTRUCTION_FREE_SNAPSHOT) == 21, \
        f"CONSTRUCTION FREE snapshot must have 21 rows, got {len(CONSTRUCTION_FREE_SNAPSHOT)}"
    _check_snapshot_integrity(CONSTRUCTION_FREE_SNAPSHOT, "CONSTRUCTION")


def test_g14_direct_canonical_fields_in_leg_input_fields():
    """All DIRECT_CANONICAL fields must be in _LEG_INPUT_FIELDS."""
    all_snapshots = BUILDING_FREE_SNAPSHOT + INDUSTRIAL_FREE_SNAPSHOT + CONSTRUCTION_FREE_SNAPSHOT
    not_in_leg = {
        f for f, c, _ in all_snapshots
        if c == "DIRECT_CANONICAL" and f not in _LEG_INPUT_FIELDS
    }
    assert not not_in_leg, \
        f"DIRECT_CANONICAL fields not in _LEG_INPUT_FIELDS: {sorted(not_in_leg)}"


def test_g14_expected_non_runtime_not_in_leg_input_fields():
    """All EXPECTED_NON_RUNTIME fields must NOT be in _LEG_INPUT_FIELDS."""
    all_snapshots = BUILDING_FREE_SNAPSHOT + INDUSTRIAL_FREE_SNAPSHOT + CONSTRUCTION_FREE_SNAPSHOT
    in_leg = {
        f for f, c, _ in all_snapshots
        if c == "EXPECTED_NON_RUNTIME" and f in _LEG_INPUT_FIELDS
    }
    assert not in_leg, \
        f"EXPECTED_NON_RUNTIME fields found in _LEG_INPUT_FIELDS: {sorted(in_leg)}"


def test_g14_source_projected_not_in_leg_input_fields():
    """SOURCE_PROJECTED source fields must NOT be in _LEG_INPUT_FIELDS."""
    all_snapshots = BUILDING_FREE_SNAPSHOT + INDUSTRIAL_FREE_SNAPSHOT + CONSTRUCTION_FREE_SNAPSHOT
    in_leg = {
        f for f, c, _ in all_snapshots
        if c == "SOURCE_PROJECTED" and f in _LEG_INPUT_FIELDS
    }
    assert not in_leg, \
        f"SOURCE_PROJECTED source fields must not be in _LEG_INPUT_FIELDS: {sorted(in_leg)}"


def test_g14_building_sector_fields_in_n1_set():
    """DIRECT_CANONICAL_BUILDING_SECTOR and SECTOR_BLOCKED_EXPECTED fields in _BUILDING_N1_FIELDS."""
    all_snapshots = BUILDING_FREE_SNAPSHOT + INDUSTRIAL_FREE_SNAPSHOT + CONSTRUCTION_FREE_SNAPSHOT
    sector_classes = {"DIRECT_CANONICAL_BUILDING_SECTOR", "SECTOR_BLOCKED_EXPECTED"}
    not_in_n1 = {
        f for f, c, _ in all_snapshots
        if c in sector_classes and f not in _BUILDING_N1_FIELDS
    }
    assert not not_in_n1, \
        f"BUILDING_SECTOR fields not in _BUILDING_N1_FIELDS: {sorted(not_in_n1)}"


def test_g14_projected_leaf_facts_in_leg_input_fields():
    """Server-projected leaf facts must be in _LEG_INPUT_FIELDS (they reach C3)."""
    expected_in_leg = [
        "is_appendix3_1_27", "is_appendix3_28_48",
        "is_appendix3_item_37", "is_appendix3_item_40",
        "is_real_estate_management",
        "has_fire_facility_subcontract", "has_ict_subcontract",
        "contract_amount_eok",
    ]
    not_in_leg = [f for f in expected_in_leg if f not in _LEG_INPUT_FIELDS]
    assert not not_in_leg, \
        f"Projected leaf facts not in _LEG_INPUT_FIELDS: {not_in_leg}"
