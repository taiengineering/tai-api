"""
H02 canonical adapter: load a CONFIRMED assessment → occupancy_capacity for LEG runtime.

C1 Source → C2 Canonical transport contract:
  Source-of-truth: result_numerator / result_denominator (exact Fraction)
  Transport to LEG evaluator:
    denominator == 1  → int(exact)
    denominator != 1  → float(exact)   [fractional legal result IS valid]
  No rounding / floor / ceil / truncation allowed.

No-floor/ceil/round contract:
  A fractional result (e.g. 200/91 from bench_length_cm=100/45.5) is a valid canonical
  legal source. It must be transported as float(exact), not discarded or truncated.

Float validity guard:
  math.isfinite(float_value) must be True. Infinite/NaN → SourceUnresolved.

Threshold preservation guard:
  exact >= Fraction(5000)  must equal  float(exact) >= 5000.0
  If they disagree (boundary edge case) → SourceUnresolved.

Historical scan firewall (strictly enforced):
  Only exact assessment_id lookup is allowed.
  No "get latest CONFIRMED for factory_id" scan.
  No "get any CONFIRMED" scan.

Return:
  occupancy_capacity: int | float
    int   if exact.denominator == 1 (whole-number result)
    float if exact.denominator != 1 (fractional result, exact transport)
"""

from __future__ import annotations

import math
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

    # C1→C2 transport: whole number → int, fractional → float (no rounding/truncation)
    if exact.denominator == 1:
        occupancy_capacity: int | float = int(exact)
    else:
        float_val = float(exact)
        if not math.isfinite(float_val):
            raise SourceUnresolved(
                f"Assessment result {exact} produces non-finite float — cannot transport"
            )
        occupancy_capacity = float_val

    # Threshold preservation guard
    threshold = Fraction(5000)
    exact_meets = exact >= threshold
    float_meets = float(exact) >= 5000.0

    if exact_meets != float_meets:
        raise SourceUnresolved(
            f"Threshold preservation guard: exact({exact_meets}) ≠ float({float_meets}) "
            f"for value {exact}. Cannot safely inject occupancy_capacity."
        )

    return {
        "occupancy_capacity": occupancy_capacity,
        "assessment_id": assessment_id,
        "meets_5000_threshold": exact_meets,
        "exact_fraction": str(exact),
    }
