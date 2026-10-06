"""
H02 occupancy capacity calculator — pure function, exact arithmetic.

Unit directions (CRITICAL):
  TABLE A  (UNDERGROUND):   명/㎡  → persons = area_m2 × density      (MULTIPLY)
  TABLE B나목 (ABOVE_GROUND): ㎡/명  → persons = area_m2 / density      (DIVIDE)

Special formulas:
  A-1-가-1  (underground, fixed seat):  persons = seat_count
  A-5-가    (underground, apartment):   persons = (room_count + 1) × dwelling_unit_count
  B-가-1    (above-ground, bench seat): persons = bench_length_cm / 45.5
  B-가-2    (above-ground, fixed seat): persons = wheelchair_space_count + fixed_seat_count

SM-03 guard (TABLE A 업무용도 60m 분기):
  floor_height_above_ground_m is required for A-4 rows; caller must supply correct row_id.

Rounding rule: NOT_FOUND in both law texts → result returned as exact Fraction.
  Threshold comparison must use exact arithmetic before any float conversion.

Input segment schema (per segment):
  {
    "scope": "UNDERGROUND" | "ABOVE_GROUND",
    "row_id": str,           # e.g. "A-1-가-1", "B-나-업무"
    "area_m2": float | null, # null for pure-count specials
    "seat_count": int | null,
    "room_count": int | null,
    "dwelling_unit_count": int | null,
    "bench_length_cm": float | null,
    "wheelchair_space_count": int | null,
    "fixed_seat_count": int | null
  }
"""

from __future__ import annotations

from fractions import Fraction
from typing import Any


def _frac(v: float | int | str) -> Fraction:
    if isinstance(v, float):
        return Fraction(v).limit_denominator(10**9)
    return Fraction(v)


def calculate_segment(segment: dict[str, Any], row_lookup: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """
    Calculate persons for a single segment.
    Returns {"persons_num": int, "persons_den": int, "trace": {...}}.
    Raises ValueError for missing required fields or unknown row_id.
    """
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

    area_m2 = seg.get("area_m2")
    if area_m2 is None:
        raise ValueError(f"TABLE A row {row_id!r} requires area_m2")
    if density is None or not isinstance(density, (int, float)):
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
        return _frac(bench_length_cm) / _frac("45.5")

    if row_id == "B-나-문화-4":
        wheelchair = seg.get("wheelchair_space_count")
        fixed = seg.get("fixed_seat_count")
        if wheelchair is None or fixed is None:
            raise ValueError("B-나-문화-4 (fixed seat) requires wheelchair_space_count and fixed_seat_count")
        return Fraction(int(wheelchair)) + Fraction(int(fixed))

    area_m2 = seg.get("area_m2")
    if area_m2 is None:
        raise ValueError(f"TABLE B나목 row {row_id!r} requires area_m2")
    if density is None or not isinstance(density, (int, float)):
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
    No rounding applied (NOT_FOUND in law texts).
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
