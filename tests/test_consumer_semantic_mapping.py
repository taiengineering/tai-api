"""WO-IMPL-001 — Consumer Input Semantic Mapping Layer tests.

Verifies (pytest-discoverable, repo convention):
  * FIELD_MAP mirror in the mapping layer matches the engine FIELD_MAP (drift guard)
  * facility_view(consumer_input), fed to the REAL engine check functions
    (read-only), yields the expected applicability token per axis
  * empty / partial input degrade gracefully

The engine (services.facility_applicability_eval) is imported read-only and
NOT modified. No live path wiring. Run under pytest, or `python tests/…py`
for the human-readable Input→Mapping→Engine→Expected→Actual table.
"""

from __future__ import annotations

from typing import Any, Dict

from services.consumer_semantic_mapping import (
    resolve,
    facility_view,
    _FIELD_MAP_MIRROR,
)
from services.facility_applicability_eval import (
    FIELD_MAP,
    evaluate_numeric_check,
    evaluate_scope_check,
)

# --- fixtures ---------------------------------------------------------------
SAMPLE: Dict[str, Any] = {
    "worker_count": 55,
    "total_floor_area": 4200,
    "electric_capacity": 900,
    "building_use_type": "D-1",
    "ksic_major": "C26",
    "gas_capacity_m3": 30,
    "project_amount": 12,  # eok
    "equipment_list": [{"type": "변압기"}],
}

# (operator, draft_value) for numeric axes
DRAFT_NUM = {
    "employee_count": (">=", 50),
    "area_size": (">=", 3000),
    "power_capacity": (">=", 75),
    "voltage_level": (">=", 22900),
    "storage_capacity": (">=", 5),
    "monetary_value": (">=", 5),
}
SCOPE_AXES = {"facility_type", "process_type", "equipment_type",
              "concentration_level", "distance_value"}

# expected engine result token (result[6]) per axis
EXPECTED = {
    "employee_count": "MATCH_CANDIDATE",
    "area_size": "MATCH_CANDIDATE",
    "power_capacity": "MATCH_CANDIDATE",
    "voltage_level": "MISSING_DATA",       # no input -> fac value null
    "storage_capacity": "AMBIGUOUS",       # delivered, engine AMBIGUOUS (quality)
    "equipment_type": "MISSING_DATA",      # fac_col None
    "facility_type": "POSSIBLE_CANDIDATE",
    "process_type": "POSSIBLE_CANDIDATE",
    "monetary_value": "AMBIGUOUS",         # delivered (eok->won), engine AMBIGUOUS
    "concentration_level": "MISSING_DATA",
    "distance_value": "MISSING_DATA",
}


def _engine_token(fac: Dict[str, Any], binding_field: str) -> str:
    if binding_field in DRAFT_NUM and binding_field not in SCOPE_AXES:
        op, dv = DRAFT_NUM[binding_field]
        return evaluate_numeric_check(
            fac, binding_field=binding_field, operator=op, draft_value=dv
        )[6]
    return evaluate_scope_check(fac, binding_field=binding_field)[6]


# --- tests ------------------------------------------------------------------
def test_field_map_mirror_matches_engine():
    """Drift guard: mapping layer mirror must equal the engine FIELD_MAP."""
    assert _FIELD_MAP_MIRROR == FIELD_MAP


def test_all_axes_match_expected_engine_token():
    fac = facility_view(SAMPLE)
    for bf in FIELD_MAP:
        assert _engine_token(fac, bf) == EXPECTED[bf], bf


def test_delivered_axes_are_exactly_seven():
    bfv, _ = resolve(SAMPLE)
    assert set(bfv) == {
        "employee_count", "area_size", "power_capacity",
        "facility_type", "process_type",
        "storage_capacity", "monetary_value",
    }


def test_monetary_scale_normalized_to_won():
    fac = facility_view(SAMPLE)
    assert fac["construction_amount"] == 12 * 1e8


def test_empty_input_delivers_nothing():
    bfv, _ = resolve({})
    assert bfv == {}
    assert facility_view({}) == {}


def test_partial_input_delivers_only_present():
    bfv, _ = resolve({"worker_count": 10})
    assert bfv == {"employee_count": 10}


# --- human-readable runner (no pytest required) -----------------------------
def _main() -> None:
    from services.consumer_semantic_mapping import format_log
    bfv, trace = resolve(SAMPLE)
    fac = facility_view(SAMPLE)
    print("[LOG] Input -> Semantic Rule -> Output -> Engine 전달")
    print(format_log(trace))
    print("\n{:20}{:>12}{:>14}  {:20}{:20}{}".format(
        "binding_field", "Input", "Engine전달", "Expected", "Actual", "OK"))
    print("-" * 92)
    passed = 0
    for r in trace:
        actual = _engine_token(fac, r.binding_field)
        exp = EXPECTED[r.binding_field]
        ok = actual == exp
        passed += ok
        eng_val = fac.get(r.fac_col) if r.fac_col else None
        print("{:20}{:>12}{:>14}  {:20}{:20}{}".format(
            r.binding_field, str(r.input_value), str(eng_val), exp, actual,
            "OK" if ok else "X"))
    print("-" * 92)
    print(f"RESULT: {passed}/{len(trace)} axes match expected engine behavior")
    assert _FIELD_MAP_MIRROR == FIELD_MAP, "FIELD_MAP drift!"
    print("DRIFT GUARD: mirror == engine FIELD_MAP  OK")


if __name__ == "__main__":
    _main()
