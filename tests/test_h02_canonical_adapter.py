"""
H02-CA: canonical_adapter unit tests.
Uses MagicMock for supabase — no DB required.
"""

import pytest
from fractions import Fraction
from unittest.mock import MagicMock, patch

from services.occupancy_capacity.canonical_adapter import (
    SourceUnresolved,
    load_confirmed_assessment_context,
)
from services.occupancy_capacity.legal_registry import (
    RULESET_VERSION,
    get_ruleset_sha256,
)


def _mock_supabase(row_override: dict | None = None):
    """Build a supabase mock that returns row_override via get_assessment path."""
    supabase = MagicMock()
    return supabase, row_override


def _confirmed_row(factory_id="fac-1", assessment_id="asmnt-1",
                   num=5000, den=1, sha=None):
    return {
        "id": assessment_id,
        "factory_id": factory_id,
        "status": "CONFIRMED",
        "ruleset_version": RULESET_VERSION,
        "ruleset_sha256": sha or get_ruleset_sha256(),
        "result_numerator": str(num),
        "result_denominator": str(den),
        "coverage_attested": True,
    }


class TestLoadConfirmedAssessmentContext:
    def test_happy_path_exact_5000(self):
        row = _confirmed_row(num=5000, den=1)
        with patch("services.occupancy_capacity.canonical_adapter.get_assessment", return_value=row):
            ctx = load_confirmed_assessment_context(
                MagicMock(), assessment_id="asmnt-1", factory_id="fac-1"
            )
        assert ctx["occupancy_capacity"] == 5000
        assert ctx["meets_5000_threshold"] is True

    def test_exact_4999_does_not_meet(self):
        row = _confirmed_row(num=4999, den=1)
        with patch("services.occupancy_capacity.canonical_adapter.get_assessment", return_value=row):
            ctx = load_confirmed_assessment_context(
                MagicMock(), assessment_id="asmnt-1", factory_id="fac-1"
            )
        assert ctx["occupancy_capacity"] == 4999
        assert ctx["meets_5000_threshold"] is False

    def test_not_found_raises(self):
        with patch("services.occupancy_capacity.canonical_adapter.get_assessment", return_value=None):
            with pytest.raises(SourceUnresolved, match="not found"):
                load_confirmed_assessment_context(
                    MagicMock(), assessment_id="missing", factory_id="fac-1"
                )

    def test_wrong_factory_raises(self):
        row = _confirmed_row(factory_id="fac-OTHER")
        with patch("services.occupancy_capacity.canonical_adapter.get_assessment", return_value=row):
            with pytest.raises(SourceUnresolved, match="fac-OTHER"):
                load_confirmed_assessment_context(
                    MagicMock(), assessment_id="asmnt-1", factory_id="fac-1"
                )

    def test_draft_status_raises(self):
        row = _confirmed_row()
        row["status"] = "DRAFT"
        with patch("services.occupancy_capacity.canonical_adapter.get_assessment", return_value=row):
            with pytest.raises(SourceUnresolved, match="DRAFT"):
                load_confirmed_assessment_context(
                    MagicMock(), assessment_id="asmnt-1", factory_id="fac-1"
                )

    def test_void_status_raises(self):
        row = _confirmed_row()
        row["status"] = "VOID"
        with patch("services.occupancy_capacity.canonical_adapter.get_assessment", return_value=row):
            with pytest.raises(SourceUnresolved, match="VOID"):
                load_confirmed_assessment_context(
                    MagicMock(), assessment_id="asmnt-1", factory_id="fac-1"
                )

    def test_stale_ruleset_version_raises(self):
        row = _confirmed_row()
        row["ruleset_version"] = "H02-1990-01-01-v0"
        with patch("services.occupancy_capacity.canonical_adapter.get_assessment", return_value=row):
            with pytest.raises(SourceUnresolved, match="ruleset"):
                load_confirmed_assessment_context(
                    MagicMock(), assessment_id="asmnt-1", factory_id="fac-1"
                )

    def test_stale_ruleset_sha_raises(self):
        row = _confirmed_row(sha="deadbeef" * 8)
        with patch("services.occupancy_capacity.canonical_adapter.get_assessment", return_value=row):
            with pytest.raises(SourceUnresolved, match="SHA"):
                load_confirmed_assessment_context(
                    MagicMock(), assessment_id="asmnt-1", factory_id="fac-1"
                )

    def test_no_calculation_attached_raises(self):
        row = _confirmed_row()
        row["result_numerator"] = None
        with patch("services.occupancy_capacity.canonical_adapter.get_assessment", return_value=row):
            with pytest.raises(SourceUnresolved, match="calculation"):
                load_confirmed_assessment_context(
                    MagicMock(), assessment_id="asmnt-1", factory_id="fac-1"
                )

    def test_historical_scan_firewall(self):
        """
        H02 canonical adapter must use EXACT assessment_id only.
        Confirm get_assessment is called with the exact ID, not a factory scan.
        """
        row = _confirmed_row()
        with patch("services.occupancy_capacity.canonical_adapter.get_assessment", return_value=row) as mock_get:
            load_confirmed_assessment_context(
                MagicMock(), assessment_id="asmnt-exact-id", factory_id="fac-1"
            )
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert call_args.args[1] == "asmnt-exact-id"

    def test_exact_integer_result(self):
        row = _confirmed_row(num=3000, den=1)
        with patch("services.occupancy_capacity.canonical_adapter.get_assessment", return_value=row):
            ctx = load_confirmed_assessment_context(
                MagicMock(), assessment_id="asmnt-1", factory_id="fac-1"
            )
        assert ctx["occupancy_capacity"] == 3000
        assert isinstance(ctx["occupancy_capacity"], int)
