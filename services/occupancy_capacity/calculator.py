"""
H02 occupancy capacity calculator — pure function, exact arithmetic.

Input contract:
  area_m2, bench_length_cm, office_location_height_m: Decimal (not float)
  count fields (seat_count, room_count, dwelling_unit_count,
                wheelchair_space_count, fixed_seat_count): int (bool rejected)
  Density values from legal_registry are loaded as Decimal (parse_float=Decimal).

float is FORBIDDEN as input to _frac(). Decimal/str/int → Fraction is exact.
Binary float → Fraction introduces representation error and is banned.

Unit directions (CRITICAL):
  TABLE A  (UNDERGROUND):   명/㎡  → persons = area_m2 × density      (MULTIPLY)
  TABLE B나목 (ABOVE_GROUND): ㎡/명  → persons = area_m2 / density      (DIVIDE)

Special formulas:
  A-1-가-1  (underground, fixed seat):  persons = seat_count
  A-5-가    (underground, apartment):   persons = (room_count + 1) × dwelling_unit_count
  B-가-1    (above-ground, bench seat): persons = bench_length_cm / Decimal("45.5")
  B-가-2    (above-ground, fixed seat): persons = wheelchair_space_count + fixed_seat_count

SM-03 guard (TABLE A 업무용도 60m 분기):
  A-4-가 requires office_location_height_m > Decimal("60")
  A-4-나 requires office_location_height_m <= Decimal("60")

Scope firewall:
  UNDERGROUND segments must use TABLE A row_ids (prefix "A-")
  ABOVE_GROUND segments must use TABLE B나목 row_ids (prefix "B-나-")

Rounding rule: NOT_FOUND in law texts → result returned as exact Fraction.
  No floor/ceil/round/int() truncation on non-integer results.
  Calculator stores numerator/denominator; canonical_adapter handles C2 transport.

dwelling_unit_count must be >= 1 (zero apartments yields 0 occupants, invalid).
"""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Any

_TABLE_A_PREFIX = "A-"
_TABLE_B_PREFIX = "B-나-"
_BENCH_45_5 = Fraction(Decimal("45.5"))
_60M = Decimal("60")

# Special formula row_ids and their exclusively-allowed fields
_SPECIAL_ALLOWED: dict[str, set[str]] = {
    "A-1-가-1": {"seat_count"},
    "A-5-가": {"room_count", "dwelling_unit_count"},
    "B-나-문화-3": {"bench_length_cm"},
    "B-나-문화-4": {"wheelchair_space_count", "fixed_seat_count"},
}

_FORMULA_FIELDS = {
    "seat_count", "room_count", "dwelling_unit_count",
    "bench_length_cm", "wheelchair_space_count", "fixed_seat_count",
}

# Scalar fields that are decimal (not int)
_DECIMAL_FIELDS = {"area_m2", "bench_length_cm", "office_location_height_m"}

# Count fields — must be int, not bool
_COUNT_FIELDS = {
    "seat_count", "room_count", "dwelling_unit_count",
    "wheelchair_space_count", "fixed_seat_count",
}


def _frac(v: Decimal | str | int) -> Fraction:
    """Exact conversion: Decimal/str/int only. float is forbidden."""
    if isinstance(v, float):
        raise TypeError(
            f"float is forbidden as calculator input (binary float is not exact). "
            f"Use Decimal or str instead. Got: {v!r}"
        )
    if isinstance(v, Decimal):
        return Fraction(v)
    if isinstance(v, int) and not isinstance(v, bool):
        return Fraction(v)
    if isinstance(v, str):
        return Fraction(Decimal(v))
    raise TypeError(f"Unsupported type for exact fraction: {type(v).__name__!r}")


def _require_non_negative(name: str, value: Any) -> None:
    if value is not None and value < 0:
        raise ValueError(f"{name} must be >= 0, got {value}")


def _reject_bool(name: str, value: Any) -> None:
    if isinstance(value, bool):
        raise ValueError(
            f"{name} must be int, not bool (True/False are not valid occupancy counts)"
        )


def _validate_segment_inputs(segment: dict[str, Any]) -> None:
    """Reject invalid inputs: scope↔table mismatches, negatives, bools, field exclusivity."""
    scope = segment.get("scope", "")
    row_id = segment.get("row_id", "")

    # Scope firewall
    if scope == "UNDERGROUND" and not row_id.startswith(_TABLE_A_PREFIX):
        raise ValueError(
            f"UNDERGROUND segment must use a TABLE A row_id (prefix 'A-'), got {row_id!r}"
        )
    if scope == "ABOVE_GROUND" and not row_id.startswith(_TABLE_B_PREFIX):
        raise ValueError(
            f"ABOVE_GROUND segment must use a TABLE B나목 row_id (prefix 'B-나-'), got {row_id!r}"
        )

    # Bool rejection for count fields
    for f in _COUNT_FIELDS:
        _reject_bool(f, segment.get(f))

    # Negative value rejection
    _require_non_negative("area_m2", segment.get("area_m2"))
    _require_non_negative("seat_count", segment.get("seat_count"))
    _require_non_negative("room_count", segment.get("room_count"))
    _require_non_negative("dwelling_unit_count", segment.get("dwelling_unit_count"))
    _require_non_negative("bench_length_cm", segment.get("bench_length_cm"))
    _require_non_negative("wheelchair_space_count", segment.get("wheelchair_space_count"))
    _require_non_negative("fixed_seat_count", segment.get("fixed_seat_count"))

    # dwelling_unit_count >= 1 (0 apartments is invalid)
    duc = segment.get("dwelling_unit_count")
    if duc is not None and duc < 1:
        raise ValueError(f"dwelling_unit_count must be >= 1 (got {duc})")

    # Float input for decimal fields → reject
    for f in _DECIMAL_FIELDS:
        v = segment.get(f)
        if isinstance(v, float):
            raise ValueError(
                f"{f} must be Decimal (not float) — use Decimal('{v}') for exact arithmetic"
            )

    # office_location_height_m must not appear on non-A-4 rows
    if segment.get("office_location_height_m") is not None:
        if row_id not in ("A-4-가", "A-4-나"):
            raise ValueError(
                f"office_location_height_m is only valid for A-4-가 and A-4-나, "
                f"got row_id={row_id!r}"
            )

    # Formula field exclusivity
    if row_id in _SPECIAL_ALLOWED:
        allowed = _SPECIAL_ALLOWED[row_id]
        disallowed = _FORMULA_FIELDS - allowed
        for f in disallowed:
            if segment.get(f) is not None:
                raise ValueError(
                    f"Row {row_id!r} uses formula {allowed}; "
                    f"field {f!r} is not allowed (formula field contamination)"
                )
        # Also reject area_m2 for all special rows
        if segment.get("area_m2") is not None:
            raise ValueError(
                f"Row {row_id!r} (special formula) must not receive area_m2"
            )
    else:
        # General density row: must not receive formula-specific fields
        for f in _FORMULA_FIELDS:
            if segment.get(f) is not None:
                raise ValueError(
                    f"General density row {row_id!r} must not receive formula field {f!r}"
                )


def calculate_segment(segment: dict[str, Any], row_lookup: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """
    Calculate persons for a single segment.
    Returns {"persons_num": int, "persons_den": int, "trace": {...}}.
    Raises ValueError for missing required fields or unknown row_id.
    """
    _validate_segment_inputs(segment)

    row_id: str = segment["row_id"]
    row = row_lookup.get(row_id)
    if row is None:
        raise ValueError(f"Unknown row_id: {row_id!r}")

    scope: str = segment.get("scope", "")
    special: bool = row.get("special_formula", False)
    density = row.get("거주밀도") or row.get("재실자밀도")

    if scope == "UNDERGROUND":
        persons = _calc_underground(row_id, row, segment, special, density)
    elif scope == "ABOVE_GROUND":
        persons = _calc_above_ground(row_id, row, segment, special, density)
    else:
        raise ValueError(f"segment.scope must be UNDERGROUND or ABOVE_GROUND, got {scope!r}")

    return {
        "row_id": row_id,
        "scope": scope,
        "persons_num": persons.numerator,
        "persons_den": persons.denominator,
        "trace": {
            "formula": _describe_formula(row_id, row, segment, scope),
        },
    }


def _calc_underground(
    row_id: str,
    row: dict[str, Any],
    seg: dict[str, Any],
    special: bool,
    density: Any,
) -> Fraction:
    if row_id == "A-1-가-1":
        seat_count = seg.get("seat_count")
        if seat_count is None:
            raise ValueError("A-1-가-1 requires seat_count")
        return Fraction(int(seat_count))

    if row_id == "A-5-가":
        room_count = seg.get("room_count")
        dwelling_unit_count = seg.get("dwelling_unit_count")
        if room_count is None or dwelling_unit_count is None:
            raise ValueError("A-5-가 requires room_count and dwelling_unit_count")
        return Fraction(int(room_count) + 1) * Fraction(int(dwelling_unit_count))

    # SM-03 guard: A-4-가/나 require office_location_height_m for Decimal comparison
    if row_id == "A-4-가":
        h = seg.get("office_location_height_m")
        if h is None:
            raise ValueError("A-4-가 (above 60m office) requires office_location_height_m")
        if not isinstance(h, Decimal):
            raise ValueError("office_location_height_m must be Decimal for A-4-가")
        if h <= _60M:
            raise ValueError(
                f"A-4-가 requires office_location_height_m > 60m, got {h}m. "
                "Use A-4-나 for <= 60m office."
            )

    if row_id == "A-4-나":
        h = seg.get("office_location_height_m")
        if h is None:
            raise ValueError("A-4-나 (at or below 60m office) requires office_location_height_m")
        if not isinstance(h, Decimal):
            raise ValueError("office_location_height_m must be Decimal for A-4-나")
        if h > _60M:
            raise ValueError(
                f"A-4-나 requires office_location_height_m <= 60m, got {h}m. "
                "Use A-4-가 for > 60m office."
            )

    area_m2 = seg.get("area_m2")
    if area_m2 is None:
        raise ValueError(f"TABLE A row {row_id!r} requires area_m2")
    if density is None:
        raise ValueError(f"TABLE A row {row_id!r} has no numeric density (special_formula={special})")
    return _frac(area_m2) * _frac(density)


def _calc_above_ground(
    row_id: str,
    row: dict[str, Any],
    seg: dict[str, Any],
    special: bool,
    density: Any,
) -> Fraction:
    if row_id == "B-나-문화-3":
        bench_length_cm = seg.get("bench_length_cm")
        if bench_length_cm is None:
            raise ValueError("B-나-문화-3 (bench seat) requires bench_length_cm")
        return _frac(bench_length_cm) / _BENCH_45_5

    if row_id == "B-나-문화-4":
        wheelchair = seg.get("wheelchair_space_count")
        fixed = seg.get("fixed_seat_count")
        if wheelchair is None or fixed is None:
            raise ValueError("B-나-문화-4 (fixed seat) requires wheelchair_space_count and fixed_seat_count")
        return Fraction(int(wheelchair)) + Fraction(int(fixed))

    area_m2 = seg.get("area_m2")
    if area_m2 is None:
        raise ValueError(f"TABLE B나목 row {row_id!r} requires area_m2")
    if density is None:
        raise ValueError(f"TABLE B나목 row {row_id!r} has no numeric density (special_formula={special})")
    return _frac(area_m2) / _frac(density)


def _describe_formula(
    row_id: str, row: dict[str, Any], seg: dict[str, Any], scope: str
) -> str:
    if row_id == "A-1-가-1":
        return f"persons = seat_count({seg.get('seat_count')})"
    if row_id == "A-5-가":
        return f"persons = (room_count({seg.get('room_count')}) + 1) × dwelling_unit_count({seg.get('dwelling_unit_count')})"
    if row_id == "B-나-문화-3":
        return f"persons = bench_length_cm({seg.get('bench_length_cm')}) / 45.5"
    if row_id == "B-나-문화-4":
        return f"persons = wheelchair({seg.get('wheelchair_space_count')}) + fixed({seg.get('fixed_seat_count')})"
    density = row.get("거주밀도") or row.get("재실자밀도")
    area = seg.get("area_m2")
    if scope == "UNDERGROUND":
        return f"persons = area_m2({area}) × density({density})  [명/㎡ MULTIPLY]"
    return f"persons = area_m2({area}) / density({density})  [㎡/명 DIVIDE]"


def build_row_lookup(
    table_a_rows: list[dict[str, Any]],
    table_b_na_rows: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for row in table_a_rows:
        lookup[row["id"]] = row
    for row in table_b_na_rows:
        lookup[row["id"]] = row
    return lookup


def calculate_total(
    segments: list[dict[str, Any]],
    table_a_rows: list[dict[str, Any]],
    table_b_na_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Calculate total occupancy capacity from all segments.
    Returns:
      {
        "total_num": int,    # exact rational numerator
        "total_den": int,    # exact rational denominator
        "segment_results": [...],
        "meets_5000_threshold": bool,  # exact comparison (no float)
      }
    No rounding. Decimal/int inputs only — float forbidden.
    """
    lookup = build_row_lookup(table_a_rows, table_b_na_rows)
    total = Fraction(0)
    segment_results = []

    for seg in segments:
        result = calculate_segment(seg, lookup)
        seg_persons = Fraction(result["persons_num"], result["persons_den"])
        total += seg_persons
        segment_results.append(result)

    threshold = Fraction(5000)
    meets_5000 = total >= threshold

    return {
        "total_num": total.numerator,
        "total_den": total.denominator,
        "segment_results": segment_results,
        "meets_5000_threshold": meets_5000,
    }


def serialize_input_segments_for_storage(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Canonical DB serialization: Decimal → non-scientific decimal string, int → int, None → None.
    Ensures stored input_segments can be reloaded and produce identical Fraction results.
    """
    out = []
    for seg in segments:
        row: dict[str, Any] = {}
        for k, v in seg.items():
            if isinstance(v, Decimal):
                row[k] = str(v)
            elif isinstance(v, bool):
                raise ValueError(f"bool is not a valid segment value for field {k!r}")
            elif isinstance(v, (int, str, type(None))):
                row[k] = v
            elif isinstance(v, float):
                raise ValueError(
                    f"float is not allowed in segment storage (field {k!r}). Use Decimal."
                )
            else:
                row[k] = v
        out.append(row)
    return out


def deserialize_input_segments_from_storage(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Reload serialized segments: decimal strings → Decimal for calculator fields.
    int fields stay int. Ensures reload determinism.
    """
    out = []
    for seg in segments:
        row: dict[str, Any] = {}
        for k, v in seg.items():
            if k in _DECIMAL_FIELDS and isinstance(v, str):
                try:
                    row[k] = Decimal(v)
                except InvalidOperation:
                    row[k] = v
            else:
                row[k] = v
        out.append(row)
    return out
