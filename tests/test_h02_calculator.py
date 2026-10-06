"""
H02-CALC: occupancy capacity calculator unit tests.
Pure function — no DB, no network.
"""

import pytest
from fractions import Fraction

from services.occupancy_capacity.calculator import (
    build_row_lookup,
    calculate_segment,
    calculate_total,
)
from services.occupancy_capacity.legal_registry import (
    get_table_a_rows,
    get_table_b_na_rows,
)


@pytest.fixture(scope="module")
def lookup():
    return build_row_lookup(get_table_a_rows(), get_table_b_na_rows())


# ─── TABLE A (UNDERGROUND, MULTIPLY) ───────────────────────────────────────

class TestTableA:
    def test_A1_ga_1_seat_count(self, lookup):
        seg = {"scope": "UNDERGROUND", "row_id": "A-1-가-1", "seat_count": 300}
        r = calculate_segment(seg, lookup)
        assert Fraction(r["persons_num"], r["persons_den"]) == Fraction(300)

    def test_A1_ga_1_missing_seat_count_raises(self, lookup):
        seg = {"scope": "UNDERGROUND", "row_id": "A-1-가-1"}
        with pytest.raises(ValueError, match="seat_count"):
            calculate_segment(seg, lookup)

    def test_A5_ga_apartment(self, lookup):
        # (room_count=3 + 1) × dwelling_unit_count=200 = 800
        seg = {"scope": "UNDERGROUND", "row_id": "A-5-가", "room_count": 3, "dwelling_unit_count": 200}
        r = calculate_segment(seg, lookup)
        assert Fraction(r["persons_num"], r["persons_den"]) == Fraction(800)

    def test_A5_ga_missing_room_count_raises(self, lookup):
        seg = {"scope": "UNDERGROUND", "row_id": "A-5-가", "dwelling_unit_count": 100}
        with pytest.raises(ValueError, match="room_count"):
            calculate_segment(seg, lookup)

    def test_A2_ga_standard_multiply(self, lookup):
        # density 0.50, area 1000 → 500 persons
        seg = {"scope": "UNDERGROUND", "row_id": "A-2-가", "area_m2": 1000.0}
        r = calculate_segment(seg, lookup)
        assert Fraction(r["persons_num"], r["persons_den"]) == Fraction(500)

    def test_A1_ga_2_movable_seat(self, lookup):
        # density 1.30, area 200 → 260
        seg = {"scope": "UNDERGROUND", "row_id": "A-1-가-2", "area_m2": 200.0}
        r = calculate_segment(seg, lookup)
        assert Fraction(r["persons_num"], r["persons_den"]) == Fraction(260)

    def test_A4_ga_office_above_60m(self, lookup):
        # density 1.25, area 800 → 1000
        seg = {"scope": "UNDERGROUND", "row_id": "A-4-가", "area_m2": 800.0}
        r = calculate_segment(seg, lookup)
        assert Fraction(r["persons_num"], r["persons_den"]) == Fraction(1000)

    def test_A4_na_office_below_60m(self, lookup):
        # density 0.25, area 4000 → 1000
        seg = {"scope": "UNDERGROUND", "row_id": "A-4-나", "area_m2": 4000.0}
        r = calculate_segment(seg, lookup)
        assert Fraction(r["persons_num"], r["persons_den"]) == Fraction(1000)

    def test_underground_missing_area_raises(self, lookup):
        seg = {"scope": "UNDERGROUND", "row_id": "A-2-가"}
        with pytest.raises(ValueError, match="area_m2"):
            calculate_segment(seg, lookup)

    def test_unknown_row_id_raises(self, lookup):
        seg = {"scope": "UNDERGROUND", "row_id": "NONEXISTENT", "area_m2": 100.0}
        with pytest.raises(ValueError, match="Unknown row_id"):
            calculate_segment(seg, lookup)

    def test_invalid_scope_raises(self, lookup):
        seg = {"scope": "INVALID", "row_id": "A-2-가", "area_m2": 100.0}
        with pytest.raises(ValueError, match="scope"):
            calculate_segment(seg, lookup)


# ─── TABLE B나목 (ABOVE_GROUND, DIVIDE) ────────────────────────────────────

class TestTableBna:
    def test_B_na_문화_3_bench_seat(self, lookup):
        # bench_length_cm=455 / 45.5 = 10
        seg = {"scope": "ABOVE_GROUND", "row_id": "B-나-문화-3", "bench_length_cm": 455.0}
        r = calculate_segment(seg, lookup)
        assert Fraction(r["persons_num"], r["persons_den"]) == Fraction(10)

    def test_B_na_문화_3_missing_bench_length_raises(self, lookup):
        seg = {"scope": "ABOVE_GROUND", "row_id": "B-나-문화-3"}
        with pytest.raises(ValueError, match="bench_length_cm"):
            calculate_segment(seg, lookup)

    def test_B_na_문화_4_fixed_seat(self, lookup):
        # wheelchair=5 + fixed=200 = 205
        seg = {"scope": "ABOVE_GROUND", "row_id": "B-나-문화-4",
               "wheelchair_space_count": 5, "fixed_seat_count": 200}
        r = calculate_segment(seg, lookup)
        assert Fraction(r["persons_num"], r["persons_den"]) == Fraction(205)

    def test_B_na_문화_4_missing_wheelchair_raises(self, lookup):
        seg = {"scope": "ABOVE_GROUND", "row_id": "B-나-문화-4", "fixed_seat_count": 200}
        with pytest.raises(ValueError, match="wheelchair"):
            calculate_segment(seg, lookup)

    def test_B_na_업무_divide(self, lookup):
        # density 9.30, area 930 → 100
        seg = {"scope": "ABOVE_GROUND", "row_id": "B-나-업무", "area_m2": 930.0}
        r = calculate_segment(seg, lookup)
        assert Fraction(r["persons_num"], r["persons_den"]) == Fraction(100)

    def test_B_na_판매_1_divide(self, lookup):
        # density 2.80, area 2800 → 1000
        seg = {"scope": "ABOVE_GROUND", "row_id": "B-나-판매-1", "area_m2": 2800.0}
        r = calculate_segment(seg, lookup)
        assert Fraction(r["persons_num"], r["persons_den"]) == Fraction(1000)

    def test_B_na_주거_1_divide(self, lookup):
        # density 18.6, area 1860 → 100
        seg = {"scope": "ABOVE_GROUND", "row_id": "B-나-주거-1", "area_m2": 1860.0}
        r = calculate_segment(seg, lookup)
        assert Fraction(r["persons_num"], r["persons_den"]) == Fraction(100)

    def test_above_ground_missing_area_raises(self, lookup):
        seg = {"scope": "ABOVE_GROUND", "row_id": "B-나-업무"}
        with pytest.raises(ValueError, match="area_m2"):
            calculate_segment(seg, lookup)


# ─── calculate_total: aggregation + threshold guard ────────────────────────

class TestCalculateTotal:
    def test_total_exactly_5000_meets_threshold(self):
        # 5000 persons exactly
        segments = [
            {"scope": "UNDERGROUND", "row_id": "A-2-가", "area_m2": 10000.0},  # 10000 × 0.50 = 5000
        ]
        result = calculate_total(segments, get_table_a_rows(), get_table_b_na_rows())
        assert result["meets_5000_threshold"] is True
        assert Fraction(result["total_num"], result["total_den"]) == Fraction(5000)

    def test_total_4999_does_not_meet_threshold(self):
        segments = [
            {"scope": "UNDERGROUND", "row_id": "A-2-가", "area_m2": 9998.0},  # 9998 × 0.50 = 4999
        ]
        result = calculate_total(segments, get_table_a_rows(), get_table_b_na_rows())
        assert result["meets_5000_threshold"] is False

    def test_multi_segment_sum(self):
        # A-2-가 1000m2 × 0.50 = 500, B-나-업무 930m2 / 9.30 = 100 → total = 600
        segments = [
            {"scope": "UNDERGROUND", "row_id": "A-2-가", "area_m2": 1000.0},
            {"scope": "ABOVE_GROUND", "row_id": "B-나-업무", "area_m2": 930.0},
        ]
        result = calculate_total(segments, get_table_a_rows(), get_table_b_na_rows())
        assert Fraction(result["total_num"], result["total_den"]) == Fraction(600)
        assert len(result["segment_results"]) == 2

    def test_special_formula_segments_combined(self):
        # A-1-가-1 seat_count=200, B-나-문화-4 wheelchair=5 + fixed=295 = 300 → total 500
        segments = [
            {"scope": "UNDERGROUND", "row_id": "A-1-가-1", "seat_count": 200},
            {"scope": "ABOVE_GROUND", "row_id": "B-나-문화-4",
             "wheelchair_space_count": 5, "fixed_seat_count": 295},
        ]
        result = calculate_total(segments, get_table_a_rows(), get_table_b_na_rows())
        assert Fraction(result["total_num"], result["total_den"]) == Fraction(500)

    def test_exact_rational_bench_seat(self):
        # bench_length_cm=100 / 45.5 = 2000/91 (non-integer)
        segments = [
            {"scope": "ABOVE_GROUND", "row_id": "B-나-문화-3", "bench_length_cm": 100.0},
        ]
        result = calculate_total(segments, get_table_a_rows(), get_table_b_na_rows())
        f = Fraction(result["total_num"], result["total_den"])
        assert f == Fraction(100) / Fraction("45.5")
        assert result["meets_5000_threshold"] is False
