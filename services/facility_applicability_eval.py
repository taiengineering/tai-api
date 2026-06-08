"""Facility applicability evaluation — pure logic (no DB I/O).

Extracted from scripts/run_facility_applicability.py for reuse by
batch scripts and (future) on-demand API evaluation.

Principle: condition satisfaction possibility only — not legal conclusions.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

# binding_field → (factories column, match quality)
FIELD_MAP: Dict[str, Tuple[Optional[str], str]] = {
    "employee_count": ("employee_count", "DIRECT"),
    "area_size": ("building_area", "DIRECT"),
    "power_capacity": ("electrical_capacity_kw", "DIRECT"),
    "voltage_level": ("transformer_capacity_kva", "AMBIGUOUS"),
    "storage_capacity": ("gas_capacity_m3", "AMBIGUOUS"),
    "equipment_type": (None, "EQUIPMENT_JOIN"),
    "facility_type": ("site_type", "AMBIGUOUS"),
    "process_type": ("ksic_code", "AMBIGUOUS"),
    "monetary_value": ("construction_amount", "AMBIGUOUS"),
    "concentration_level": (None, "MISSING"),
    "distance_value": (None, "MISSING"),
}

CheckResult = Tuple[str, str, Optional[str], Optional[str], Any, Any, str, str]


def compare_numeric(operator: str, draft_val: Any, facility_val: Any) -> str:
    """Numeric comparison — returns applicability detail result token."""
    if draft_val is None or facility_val is None:
        return "MISSING_DATA"
    try:
        dv = float(draft_val)
        fv = float(facility_val)
    except (TypeError, ValueError):
        return "MISSING_DATA"

    op = (operator or "").strip()
    if op == ">=":
        return "MATCH_CANDIDATE" if fv >= dv else "NOT_MATCHED"
    if op == "<=":
        return "MATCH_CANDIDATE" if fv <= dv else "NOT_MATCHED"
    if op == ">":
        return "MATCH_CANDIDATE" if fv > dv else "NOT_MATCHED"
    if op == "<":
        return "MATCH_CANDIDATE" if fv < dv else "NOT_MATCHED"
    return "AMBIGUOUS"


def aggregate_applicability_status(results: Set[str]) -> str:
    """Combine per-check results into overall applicability_status."""
    if not results:
        return "MISSING_DATA"
    if "MATCH_CANDIDATE" in results and "NOT_MATCHED" not in results:
        return "MATCH_CANDIDATE"
    if "MATCH_CANDIDATE" in results and "NOT_MATCHED" in results:
        return "AMBIGUOUS"
    if "POSSIBLE_CANDIDATE" in results:
        return "POSSIBLE_CANDIDATE"
    if "AMBIGUOUS" in results:
        return "AMBIGUOUS"
    if results == {"NOT_MATCHED"}:
        return "NOT_MATCHED"
    return "MISSING_DATA"


def evaluate_numeric_check(
    facility: Dict[str, Any],
    *,
    binding_field: str,
    operator: str,
    draft_value: Any,
) -> CheckResult:
    """Single IF_NUMERIC draft_slot vs facility row."""
    fmap = FIELD_MAP.get(binding_field)
    if not fmap:
        return (
            "NUMERIC_CHECK",
            binding_field,
            None,
            operator,
            draft_value,
            None,
            "MISSING_DATA",
            "NO_FIELD_MAP",
        )
    fac_col, quality = fmap
    if fac_col is None:
        return (
            "NUMERIC_CHECK",
            binding_field,
            None,
            operator,
            draft_value,
            None,
            "MISSING_DATA",
            "NO_FACILITY_COLUMN",
        )
    fac_val = facility.get(fac_col)
    if fac_val is None:
        return (
            "NUMERIC_CHECK",
            binding_field,
            fac_col,
            operator,
            draft_value,
            None,
            "MISSING_DATA",
            "FACILITY_VALUE_NULL",
        )
    if quality == "AMBIGUOUS":
        return (
            "NUMERIC_CHECK",
            binding_field,
            fac_col,
            operator,
            draft_value,
            fac_val,
            "AMBIGUOUS",
            "UNIT_MISMATCH_POSSIBLE",
        )
    result = compare_numeric(operator, draft_value, fac_val)
    return (
        "NUMERIC_CHECK",
        binding_field,
        fac_col,
        operator,
        draft_value,
        fac_val,
        result,
        "DIRECT_COMPARE",
    )


def evaluate_scope_check(
    facility: Dict[str, Any],
    *,
    binding_field: str,
) -> CheckResult:
    """Single IF_SCOPE draft_slot — field presence only."""
    fmap = FIELD_MAP.get(binding_field)
    if not fmap or fmap[0] is None:
        return (
            "SCOPE_CHECK",
            binding_field,
            None,
            None,
            None,
            None,
            "MISSING_DATA",
            "NO_FACILITY_COLUMN",
        )
    fac_col = fmap[0]
    fac_val = facility.get(fac_col)
    if fac_val is None:
        return (
            "SCOPE_CHECK",
            binding_field,
            fac_col,
            None,
            None,
            None,
            "MISSING_DATA",
            "FACILITY_VALUE_NULL",
        )
    return (
        "SCOPE_CHECK",
        binding_field,
        fac_col,
        None,
        None,
        fac_val,
        "POSSIBLE_CANDIDATE",
        "SCOPE_FIELD_EXISTS",
    )


def evaluate_draft_for_facility(
    facility: Dict[str, Any],
    draft_id: str,
    numeric_slots: List[Dict[str, Any]],
    scope_slots: List[Dict[str, Any]],
) -> Optional[Tuple[str, str, List[CheckResult]]]:
    """
    Evaluate one facility × one executable_draft.

    Returns (overall_status, part_id, check_results) or None if no checks.
    """
    part_id: Optional[str] = None
    check_results: List[CheckResult] = []

    for ns in numeric_slots:
        part_id = ns.get("part_id") or part_id
        check_results.append(
            evaluate_numeric_check(
                facility,
                binding_field=ns["binding_field"],
                operator=ns.get("operator") or "",
                draft_value=ns.get("value"),
            )
        )

    for ss in scope_slots:
        part_id = part_id or ss.get("part_id")
        check_results.append(
            evaluate_scope_check(facility, binding_field=ss["binding_field"])
        )

    if not check_results or part_id is None:
        return None

    results_set = {r[6] for r in check_results}
    overall = aggregate_applicability_status(results_set)
    return overall, str(part_id), check_results
