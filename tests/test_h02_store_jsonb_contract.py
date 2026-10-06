"""
H02 store JSONB native payload contract tests.

Verifies that Supabase receives native Python objects (list/dict), NOT JSON strings.
PostgREST/Supabase handles JSONB serialization internally.

JSONB-01: create_draft passes input_segments as list (not str)
JSONB-02: update_assessment_draft passes input_segments as list (not str)
JSONB-03: attach_calculation passes calculation_trace as dict (not str)
JSONB-04: Decimal fields stored as canonical decimal string inside the native list
JSONB-05: reload determinism — native list → deserialize → same Fraction result
JSONB-06: double serialization absent (no JSON string wrapper around the array)
"""
from __future__ import annotations

from decimal import Decimal
from fractions import Fraction
from unittest.mock import MagicMock, call, patch

import pytest

from services.occupancy_capacity.calculator import (
    deserialize_input_segments_from_storage,
    serialize_input_segments_for_storage,
)
from services.occupancy_capacity.store import (
    attach_calculation,
    create_draft,
    update_assessment_draft,
)


def _make_supabase_insert_capture():
    """Return (supabase_mock, captured_payloads list).
    supabase.table(...).insert(payload).execute() appends payload to captured.
    """
    captured = []

    class _Exec:
        data = [{"id": "new-id", "factory_id": "fac-1", "status": "DRAFT",
                 "input_segments": [], "coverage_attested": False}]

    class _Insert:
        def __init__(self, payload):
            captured.append(payload)
        def execute(self):
            return _Exec()

    class _Table:
        def insert(self, payload):
            return _Insert(payload)

    sub = MagicMock()
    sub.table.return_value = _Table()
    return sub, captured


def _make_supabase_update_capture():
    """Return (supabase_mock, captured_payloads list).
    supabase.table(...).update(payload).eq(...).eq(...).execute() appends payload.
    """
    captured = []

    class _Exec:
        data = [{"id": "asmnt-1", "status": "DRAFT"}]

    class _EqChain:
        def eq(self, *a, **kw):
            return self
        def execute(self):
            return _Exec()

    class _Update:
        def __init__(self, payload):
            captured.append(payload)
        def eq(self, *a, **kw):
            return _EqChain()

    class _Table:
        def update(self, payload):
            return _Update(payload)

    sub = MagicMock()
    sub.table.return_value = _Table()
    return sub, captured


# ─── JSONB-01 create_draft passes native list ───────────────────────────────

class TestCreateDraftJsonb:
    def test_input_segments_is_list_not_str(self):
        """JSONB-01: create_draft payload['input_segments'] must be list."""
        sub, captured = _make_supabase_insert_capture()
        segments = [{"scope": "UNDERGROUND", "row_id": "A-1-가-1", "seat_count": 100}]
        stored = serialize_input_segments_for_storage(segments)

        create_draft(sub, "fac-1", stored)

        assert len(captured) == 1
        payload = captured[0]
        assert isinstance(payload["input_segments"], list), (
            f"input_segments must be list, got {type(payload['input_segments']).__name__}"
        )
        assert not isinstance(payload["input_segments"], str)

    def test_no_double_serialization(self):
        """JSONB-06: payload must not be a JSON string wrapper."""
        sub, captured = _make_supabase_insert_capture()
        stored = serialize_input_segments_for_storage(
            [{"scope": "UNDERGROUND", "row_id": "A-1-가-1", "seat_count": 50}]
        )
        create_draft(sub, "fac-1", stored)

        payload = captured[0]
        val = payload["input_segments"]
        assert not isinstance(val, str), (
            "Double serialization detected: input_segments is a JSON string, not a native list"
        )


# ─── JSONB-02 update_assessment_draft passes native list ───────────────────

class TestUpdateDraftJsonb:
    def test_input_segments_is_list_not_str(self):
        """JSONB-02: update_assessment_draft payload['input_segments'] must be list."""
        sub, captured = _make_supabase_update_capture()
        segments = [{"scope": "ABOVE_GROUND", "row_id": "B-나-업무", "area_m2": "930"}]

        update_assessment_draft(sub, "asmnt-1", segments)

        assert len(captured) == 1
        payload = captured[0]
        assert isinstance(payload["input_segments"], list)
        assert not isinstance(payload["input_segments"], str)


# ─── JSONB-03 attach_calculation passes native dict ────────────────────────

class TestAttachCalculationJsonb:
    def test_calculation_trace_is_dict_not_str(self):
        """JSONB-03: attach_calculation payload['calculation_trace'] must be dict."""
        sub, captured = _make_supabase_update_capture()
        trace = {
            "segment_results": [],
            "meets_5000_threshold": False,
            "total_exact": "2000/91",
        }

        attach_calculation(sub, "asmnt-1", 2000, 91, trace)

        assert len(captured) == 1
        payload = captured[0]
        assert isinstance(payload["calculation_trace"], dict), (
            f"calculation_trace must be dict, got {type(payload['calculation_trace']).__name__}"
        )
        assert not isinstance(payload["calculation_trace"], str)

    def test_no_double_serialization_trace(self):
        """JSONB-06 (trace): calculation_trace must not be a JSON string."""
        sub, captured = _make_supabase_update_capture()
        trace = {"segment_results": [{"row_id": "A-1-가-1"}], "meets_5000_threshold": True}

        attach_calculation(sub, "asmnt-1", 5000, 1, trace)

        payload = captured[0]
        val = payload["calculation_trace"]
        assert not isinstance(val, str), (
            "Double serialization: calculation_trace is a JSON string, not a native dict"
        )
        assert val["meets_5000_threshold"] is True


# ─── JSONB-04 Decimal stored as canonical string inside native list ─────────

class TestDecimalCanonicalStorage:
    def test_decimal_stored_as_string_in_native_list(self):
        """JSONB-04: Decimal("1000.25") → area_m2='1000.25' inside native list."""
        sub, captured = _make_supabase_insert_capture()
        segments = [{"scope": "UNDERGROUND", "row_id": "A-2-가", "area_m2": Decimal("1000.25")}]
        stored = serialize_input_segments_for_storage(segments)

        create_draft(sub, "fac-1", stored)

        payload = captured[0]
        native_list = payload["input_segments"]
        assert isinstance(native_list, list)
        assert native_list[0]["area_m2"] == "1000.25"
        assert isinstance(native_list[0]["area_m2"], str)

    def test_bench_decimal_stored_as_string(self):
        segments = [{"scope": "ABOVE_GROUND", "row_id": "B-나-문화-3", "bench_length_cm": Decimal("45.5")}]
        stored = serialize_input_segments_for_storage(segments)
        sub, captured = _make_supabase_insert_capture()
        create_draft(sub, "fac-1", stored)

        native_list = captured[0]["input_segments"]
        assert native_list[0]["bench_length_cm"] == "45.5"
        assert isinstance(native_list[0]["bench_length_cm"], str)


# ─── JSONB-05 Reload determinism via native list ────────────────────────────

class TestReloadDeterminismNative:
    def test_native_list_roundtrip_preserves_fraction(self):
        """JSONB-05: serialize → native list → deserialize → same Fraction result."""
        from services.occupancy_capacity.calculator import calculate_total
        from services.occupancy_capacity.legal_registry import get_table_a_rows, get_table_b_na_rows

        seg = {"scope": "UNDERGROUND", "row_id": "A-2-가", "area_m2": Decimal("930")}
        stored = serialize_input_segments_for_storage([seg])

        # stored is the native list that would be written to DB
        assert isinstance(stored, list)
        assert stored[0]["area_m2"] == "930"

        # simulate reading back from DB (native list, no JSON string)
        reloaded = deserialize_input_segments_from_storage(stored)
        assert reloaded[0]["area_m2"] == Decimal("930")

        result1 = calculate_total([seg], get_table_a_rows(), get_table_b_na_rows())
        result2 = calculate_total(reloaded, get_table_a_rows(), get_table_b_na_rows())

        assert result1["total_num"] == result2["total_num"]
        assert result1["total_den"] == result2["total_den"]
