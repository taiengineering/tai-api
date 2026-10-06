"""
H02 canonical adapter: load a CONFIRMED assessment → occupancy_capacity for LEG runtime.

Firewall rules (historical scan strictly prohibited):
  - Only exact assessment_id lookup is allowed.
  - No "get latest CONFIRMED for factory_id" scan.
  - No "get any CONFIRMED" scan.

No-rounding contract (ROUNDING_RULE_NOT_FOUND):
  - If the exact Fraction result is not a whole number, SourceUnresolved is raised.
  - floor / ceil / round / int() truncation are ALL prohibited.
  - Caller must ensure segments produce whole-number results, or the assessment
    cannot be used as a canonical source.

Threshold preservation guard:
  - exact ≥ 5000 (Fraction comparison) must equal float ≥ 5000.
  - If they differ (boundary edge case), raise SOURCE_UNRESOLVED instead of injecting.

Return:
  occupancy_capacity: int
    Whole-number persons count, exact (denominator == 1 verified).
"""

from __future__ import annotations

from fractions import Fraction
from typing import Any

from services.occupancy_capacity.legal_registry import RULESET_VERSION, get_ruleset_sha256
from services.occupancy_capacity.store import get_assessment


class SourceUnresolved(Exception):
    pass


def load_confirmed_assessment_context(
    supabase,
    assessment_id: str,
    factory_id: str,
) -> dict[str, Any]:
    """
    Validate and return the canonical occupancy_capacity from an exact CONFIRMED assessment.
    Raises SourceUnresolved on any validation failure.
    """
    row = get_assessment(supabase, assessment_id)

    if row is None:
        raise SourceUnresolved(f"Assessment {assessment_id!r} not found")
    if row["factory_id"] != factory_id:
        raise SourceUnresolved(
            f"Assessment {assessment_id!r} belongs to factory {row['factory_id']!r}, "
            f"not {factory_id!r}"
        )
    if row["status"] != "CONFIRMED":
        raise SourceUnresolved(
            f"Assessment {assessment_id!r} is {row['status']!r}, must be CONFIRMED"
        )
    if row["ruleset_version"] != RULESET_VERSION:
        raise SourceUnresolved(
            f"Assessment ruleset {row['ruleset_version']!r} does not match current {RULESET_VERSION!r}"
        )
    if row["ruleset_sha256"] != get_ruleset_sha256():
        raise SourceUnresolved(
            f"Assessment ruleset SHA mismatch (code file changed since confirmation)"
        )
    if row["result_numerator"] is None or row["result_denominator"] is None:
        raise SourceUnresolved("Assessment has no calculation result")

    num = int(row["result_numerator"])
    den = int(row["result_denominator"])
    exact = Fraction(num, den)

    # No-rounding contract: non-whole result cannot be emitted as canonical integer.
    # Rounding rule is NOT_FOUND in both law texts — truncation/rounding is prohibited.
    if exact.denominator != 1:
        raise SourceUnresolved(
            f"Assessment result {exact} is not a whole number. "
            "Rounding rule is NOT_FOUND in law texts — cannot emit canonical integer. "
            "Re-calculate with segments that produce whole-number results."
        )

    threshold = Fraction(5000)
    exact_meets = exact >= threshold
    float_val = float(exact)
    float_meets = float_val >= 5000.0

    if exact_meets != float_meets:
        raise SourceUnresolved(
            f"Threshold preservation guard: exact({exact_meets}) ≠ float({float_meets}) "
            f"for value {exact}. Cannot safely inject occupancy_capacity."
        )

    return {
        "occupancy_capacity": int(exact),
        "assessment_id": assessment_id,
        "meets_5000_threshold": exact_meets,
        "exact_fraction": str(exact),
    }
