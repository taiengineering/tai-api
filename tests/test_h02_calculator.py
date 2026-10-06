"""
H02-CALC: occupancy capacity calculator unit tests.
Pure function — no DB, no network.
"""

import pytest
from decimal import Decimal
from fractions import Fraction

from services.occupancy_capacity.calculator import (
    build_row_lookup,
    calculate_segment,
    calculate_total,
    deserialize_input_segments_from_storage,
    serialize_input_segments_for_storage,
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

    def test_A1_ga_1_rejects_area_m2(self, lookup):
        seg = {"scope": "UNDERGROUND", "row_id": "A-1-가-1", "seat_count": 100, "area_m2": Decimal("200")}
        with pytest.raises(ValueError, match="must not receive area_m2"):
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

    def test_A5_ga_rejects_area_m2(self, lookup):
        seg = {"scope": "UNDERGROUND", "row_id": "A-5-가", "room_count": 2, "dwelling_unit_count": 50, "area_m2": Decimal("100")}
        with pytest.raises(ValueError, match="must not receive area_m2"):
            calculate_segment(seg, lookup)

    def test_A2_ga_standard_multiply(self, lookup):
        # density 0.50, area 1000 → 500 persons
        seg = {"scope": "UNDERGROUND", "row_id": "A-2-가", "area_m2": Decimal("1000")}
        r = calculate_segment(seg, lookup)
        assert Fraction(r["persons_num"], r["persons_den"]) == Fraction(500)

    def test_A4_ga_office_above_60m_valid(self, lookup):
        # density 1.25, area 800, height 80m → 1000
        seg = {"scope": "UNDERGROUND", "row_id": "A-4-가", "area_m2": Decimal("800"), "office_location_height_m": Decimal("80")}
        r = calculate_segment(seg, lookup)
        assert Fraction(r["persons_num"], r["persons_den"]) == Fraction(1000)

    def test_A4_ga_missing_height_raises(self, lookup):
        seg = {"scope": "UNDERGROUND", "row_id": "A-4-가", "area_m2": Decimal("800")}
        with pytest.raises(ValueError, match="office_location_height_m"):
            calculate_segment(seg, lookup)

    def test_A4_ga_height_not_above_60_raises(self, lookup):
        seg = {"scope": "UNDERGROUND", "row_id": "A-4-가", "area_m2": Decimal("800"), "office_location_height_m": Decimal("55")}
        with pytest.raises(ValueError, match="A-4-나"):
            calculate_segment(seg, lookup)

    def test_A4_na_office_below_60m_valid(self, lookup):
        # density 0.25, area 4000, height 40m → 1000
        seg = {"scope": "UNDERGROUND", "row_id": "A-4-나", "area_m2": Decimal("4000"), "office_location_height_m": Decimal("40")}
        r = calculate_segment(seg, lookup)
        assert Fraction(r["persons_num"], r["persons_den"]) == Fraction(1000)

    def test_A4_na_height_above_60_raises(self, lookup):
        seg = {"scope": "UNDERGROUND", "row_id": "A-4-나", "area_m2": Decimal("4000"), "office_location_height_m": Decimal("70")}
        with pytest.raises(ValueError, match="A-4-가"):
            calculate_segment(seg, lookup)

    def test_underground_missing_area_raises(self, lookup):
        seg = {"scope": "UNDERGROUND", "row_id": "A-2-가"}
        with pytest.raises(ValueError, match="area_m2"):
            calculate_segment(seg, lookup)

    def test_unknown_row_id_raises(self, lookup):
        # NONEXISTENT doesn't start with "A-" so scope firewall fires first
        seg = {"scope": "UNDERGROUND", "row_id": "NONEXISTENT", "area_m2": Decimal("100")}
        with pytest.raises(ValueError):
            calculate_segment(seg, lookup)

    def test_unknown_a_row_id_raises(self, lookup):
        # Passes scope check (A- prefix) but unknown in lookup
        seg = {"scope": "UNDERGROUND", "row_id": "A-99-unknown", "area_m2": Decimal("100")}
        with pytest.raises(ValueError, match="Unknown row_id"):
            calculate_segment(seg, lookup)

    def test_invalid_scope_raises(self, lookup):
        seg = {"scope": "INVALID", "row_id": "A-2-가", "area_m2": Decimal("100")}
        with pytest.raises(ValueError, match="scope"):
            calculate_segment(seg, lookup)

    def test_negative_area_raises(self, lookup):
        seg = {"scope": "UNDERGROUND", "row_id": "A-2-가", "area_m2": Decimal("-1")}
        with pytest.raises(ValueError, match="area_m2"):
            calculate_segment(seg, lookup)

    def test_negative_seat_count_raises(self, lookup):
        seg = {"scope": "UNDERGROUND", "row_id": "A-1-가-1", "seat_count": -5}
        with pytest.raises(ValueError, match="seat_count"):
            calculate_segment(seg, lookup)


# ─── Scope firewall (cross-table row_id rejection) ──────────────────────────

class TestScopeFirewall:
    def test_underground_scope_with_b_row_id_raises(self, lookup):
        seg = {"scope": "UNDERGROUND", "row_id": "B-나-업무", "area_m2": Decimal("100")}
        with pytest.raises(ValueError, match="TABLE A row_id"):
            calculate_segment(seg, lookup)

    def test_above_ground_scope_with_a_row_id_raises(self, lookup):
        seg = {"scope": "ABOVE_GROUND", "row_id": "A-2-가", "area_m2": Decimal("100")}
        with pytest.raises(ValueError, match="TABLE B나목 row_id"):
            calculate_segment(seg, lookup)


# ─── TABLE B나목 (ABOVE_GROUND, DIVIDE) ────────────────────────────────────

class TestTableBna:
    def test_B_na_문화_3_bench_seat(self, lookup):
        # bench_length_cm=455 / 45.5 = 10
        seg = {"scope": "ABOVE_GROUND", "row_id": "B-나-문화-3", "bench_length_cm": Decimal("455")}
        r = calculate_segment(seg, lookup)
        assert Fraction(r["persons_num"], r["persons_den"]) == Fraction(10)

    def test_B_na_문화_3_rejects_area_m2(self, lookup):
        seg = {"scope": "ABOVE_GROUND", "row_id": "B-나-문화-3", "bench_length_cm": Decimal("455"), "area_m2": Decimal("100")}
        with pytest.raises(ValueError, match="must not receive area_m2"):
            calculate_segment(seg, lookup)

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

    def test_B_na_문화_4_rejects_area_m2(self, lookup):
        seg = {"scope": "ABOVE_GROUND", "row_id": "B-나-문화-4",
               "wheelchair_space_count": 5, "fixed_seat_count": 200, "area_m2": Decimal("100")}
        with pytest.raises(ValueError, match="must not receive area_m2"):
            calculate_segment(seg, lookup)

    def test_B_na_문화_4_missing_wheelchair_raises(self, lookup):
        seg = {"scope": "ABOVE_GROUND", "row_id": "B-나-문화-4", "fixed_seat_count": 200}
        with pytest.raises(ValueError, match="wheelchair"):
            calculate_segment(seg, lookup)

    def test_B_na_업무_divide(self, lookup):
        # density 9.30, area 930 → 100
        seg = {"scope": "ABOVE_GROUND", "row_id": "B-나-업무", "area_m2": Decimal("930")}
        r = calculate_segment(seg, lookup)
        assert Fraction(r["persons_num"], r["persons_den"]) == Fraction(100)

    def test_B_na_판매_1_divide(self, lookup):
        # density 2.80, area 2800 → 1000
        seg = {"scope": "ABOVE_GROUND", "row_id": "B-나-판매-1", "area_m2": Decimal("2800")}
        r = calculate_segment(seg, lookup)
        assert Fraction(r["persons_num"], r["persons_den"]) == Fraction(1000)

    def test_above_ground_missing_area_raises(self, lookup):
        seg = {"scope": "ABOVE_GROUND", "row_id": "B-나-업무"}
        with pytest.raises(ValueError, match="area_m2"):
            calculate_segment(seg, lookup)

    def test_negative_bench_length_raises(self, lookup):
        seg = {"scope": "ABOVE_GROUND", "row_id": "B-나-문화-3", "bench_length_cm": Decimal("-10")}
        with pytest.raises(ValueError, match="bench_length_cm"):
            calculate_segment(seg, lookup)


# ─── calculate_total: aggregation + threshold guard ────────────────────────

class TestCalculateTotal:
    def test_total_exactly_5000_meets_threshold(self):
        # 10000 × 0.50 = 5000 exactly
        segments = [
            {"scope": "UNDERGROUND", "row_id": "A-2-가", "area_m2": Decimal("10000")},
        ]
        result = calculate_total(segments, get_table_a_rows(), get_table_b_na_rows())
        assert result["meets_5000_threshold"] is True
        assert Fraction(result["total_num"], result["total_den"]) == Fraction(5000)

    def test_total_4999_does_not_meet_threshold(self):
        segments = [
            {"scope": "UNDERGROUND", "row_id": "A-2-가", "area_m2": Decimal("9998")},  # 9998 × 0.50 = 4999
        ]
        result = calculate_total(segments, get_table_a_rows(), get_table_b_na_rows())
        assert result["meets_5000_threshold"] is False

    def test_multi_segment_sum(self):
        # A-2-가 1000m2 × 0.50 = 500, B-나-업무 930m2 / 9.30 = 100 → total = 600
        segments = [
            {"scope": "UNDERGROUND", "row_id": "A-2-가", "area_m2": Decimal("1000")},
            {"scope": "ABOVE_GROUND", "row_id": "B-나-업무", "area_m2": Decimal("930")},
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

    def test_exact_rational_bench_seat_stored_as_fraction(self):
        # bench_length_cm=100 / 45.5 = 2000/91 (non-integer)
        # canonical_adapter transports denominator!=1 as float(exact), not truncated
        segments = [
            {"scope": "ABOVE_GROUND", "row_id": "B-나-문화-3", "bench_length_cm": Decimal("100")},
        ]
        result = calculate_total(segments, get_table_a_rows(), get_table_b_na_rows())
        f = Fraction(result["total_num"], result["total_den"])
        assert f == Fraction(Decimal("100")) / Fraction(Decimal("45.5"))
        assert result["meets_5000_threshold"] is False
        assert result["total_den"] != 1  # fractional — transported as float by canonical_adapter


# ─── Exact Decimal arithmetic, input contract, reload determinism ──────────

class TestDecimalExact:
    def test_decimal_0_1_exact_no_float_error(self, lookup):
        # Decimal("0.1") must not introduce binary float error in multiplication
        seg = {"scope": "UNDERGROUND", "row_id": "A-2-가", "area_m2": Decimal("0.1")}
        r = calculate_segment(seg, lookup)
        f = Fraction(r["persons_num"], r["persons_den"])
        assert f == Fraction(Decimal("0.1")) * Fraction(Decimal("0.5"))

    def test_bench_45_5_exact_one_person(self, lookup):
        # bench_length_cm=45.5 / 45.5 = exactly 1 person
        seg = {"scope": "ABOVE_GROUND", "row_id": "B-나-문화-3", "bench_length_cm": Decimal("45.5")}
        r = calculate_segment(seg, lookup)
        assert Fraction(r["persons_num"], r["persons_den"]) == Fraction(1)

    def test_sm03_60_0001_rejects_for_na(self, lookup):
        # A-4-나 requires <= 60m; Decimal("60.0001") > 60 must raise
        seg = {"scope": "UNDERGROUND", "row_id": "A-4-나",
               "area_m2": Decimal("100"), "office_location_height_m": Decimal("60.0001")}
        with pytest.raises(ValueError, match="A-4-가"):
            calculate_segment(seg, lookup)

    def test_reload_determinism(self):
        # serialize→deserialize must produce identical calculation result
        seg = {"scope": "ABOVE_GROUND", "row_id": "B-나-업무", "area_m2": Decimal("930")}
        result1 = calculate_total([seg], get_table_a_rows(), get_table_b_na_rows())
        stored = serialize_input_segments_for_storage([seg])
        reloaded = deserialize_input_segments_from_storage(stored)
        result2 = calculate_total(reloaded, get_table_a_rows(), get_table_b_na_rows())
        assert result1["total_num"] == result2["total_num"]
        assert result1["total_den"] == result2["total_den"]

    def test_bool_count_rejected(self, lookup):
        seg = {"scope": "UNDERGROUND", "row_id": "A-1-가-1", "seat_count": True}
        with pytest.raises(ValueError, match="bool"):
            calculate_segment(seg, lookup)

    def test_formula_cross_field_contamination_rejected(self, lookup):
        # A-1-가-1 allows only seat_count; room_count is contamination
        seg = {"scope": "UNDERGROUND", "row_id": "A-1-가-1", "seat_count": 100, "room_count": 3}
        with pytest.raises(ValueError, match="formula field contamination"):
            calculate_segment(seg, lookup)

    def test_general_row_rejects_special_field(self, lookup):
        # A-2-가 is general density row; seat_count is a formula field
        seg = {"scope": "UNDERGROUND", "row_id": "A-2-가", "area_m2": Decimal("100"), "seat_count": 5}
        with pytest.raises(ValueError, match="formula field"):
            calculate_segment(seg, lookup)

    def test_dwelling_unit_count_zero_rejected(self, lookup):
        seg = {"scope": "UNDERGROUND", "row_id": "A-5-가", "room_count": 3, "dwelling_unit_count": 0}
        with pytest.raises(ValueError, match="dwelling_unit_count"):
            calculate_segment(seg, lookup)

    def test_float_area_rejected(self, lookup):
        seg = {"scope": "UNDERGROUND", "row_id": "A-2-가", "area_m2": 1000.0}
        with pytest.raises(ValueError, match="Decimal"):
            calculate_segment(seg, lookup)

    def test_float_bench_rejected(self, lookup):
        seg = {"scope": "ABOVE_GROUND", "row_id": "B-나-문화-3", "bench_length_cm": 100.0}
        with pytest.raises(ValueError, match="Decimal"):
            calculate_segment(seg, lookup)

    def test_office_height_on_non_a4_rejected(self, lookup):
        # office_location_height_m only valid for A-4-가/나
        seg = {"scope": "UNDERGROUND", "row_id": "A-2-가",
               "area_m2": Decimal("100"), "office_location_height_m": Decimal("50")}
        with pytest.raises(ValueError, match="office_location_height_m"):
            calculate_segment(seg, lookup)
