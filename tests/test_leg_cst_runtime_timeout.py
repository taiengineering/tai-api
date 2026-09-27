"""WO-LEG-CST-RUNTIME-TIMEOUT-001

CONSTRUCTION-specific /rtm/evaluate timeout policy tests.

Test registry:
  T1  CONSTRUCTION context → evaluate_rtm receives dedicated construction timeout
  T2  BUILDING context → evaluate_rtm receives timeout=None (client default used)
  T3  INDUSTRIAL context → evaluate_rtm receives timeout=None (client default used)
  T4  facility object passed through unchanged
  T5  context dict passed through unchanged (no extra keys)
  T6  retry zero — LegRuntimeError propagates, call count=1
  T7  fallback zero — no Compiler Core / legacy engine call on failure
  T8  full_result contract unchanged when evaluate_rtm returns normal response
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, call

import services.leg_diagnosis_svc as svc
from services.leg_diagnosis_svc import (
    LEG_RTM_CONSTRUCTION_TIMEOUT,
    LegDiagnosisError,
    run_leg_diagnosis,
)
from clients.leg_runtime_client import LegRuntimeError


# ── helpers ──────────────────────────────────────────────────────────────────

def _step1(sector: str) -> MagicMock:
    body = MagicMock()
    body.sector = sector
    return body


def _ok_response(obligation_count: int = 5) -> dict:
    obligations = [
        {
            "law_name": "산업안전보건법",
            "law_article": "제38조",
            "evidence": "has_diving",
            "triggered_by": ["has_diving"],
            "atom_id": f"atom-{i}",
            "source_atom_ids": [f"atom-{i}"],
            "applicability": "APPLICABLE",
        }
        for i in range(obligation_count)
    ]
    return {
        "status": "OK",
        "obligation_count": obligation_count,
        "obligations": obligations,
        "review_required": [],
        "trace_id": "test-trace",
        "provenance": None,
        "contract": None,
    }


# ── T1: CONSTRUCTION → dedicated timeout ────────────────────────────────────

def test_t1_construction_uses_dedicated_timeout():
    """T1: CONSTRUCTION context → evaluate_rtm called with LEG_RTM_CONSTRUCTION_TIMEOUT."""
    step1 = _step1("CONSTRUCTION")
    fake_facility = {"has_diving": True}
    fake_context = {"sector": "CONSTRUCTION"}

    with patch("services.leg_diagnosis_svc.leg_client") as mock_client:
        mock_client.build_facility.return_value = fake_facility
        mock_client.build_engine_context.return_value = fake_context
        mock_client.evaluate_rtm.return_value = _ok_response()

        run_leg_diagnosis(step1)

        _, kwargs = mock_client.evaluate_rtm.call_args
        assert kwargs["timeout"] == LEG_RTM_CONSTRUCTION_TIMEOUT
        assert kwargs["timeout"] == 30.0


# ── T2: BUILDING → timeout=None ─────────────────────────────────────────────

def test_t2_building_timeout_none():
    """T2: BUILDING context → evaluate_rtm called with timeout=None (client default)."""
    step1 = _step1("BUILDING")
    fake_context = {"sector": "BUILDING"}

    with patch("services.leg_diagnosis_svc.leg_client") as mock_client:
        mock_client.build_facility.return_value = {}
        mock_client.build_engine_context.return_value = fake_context
        mock_client.evaluate_rtm.return_value = _ok_response()

        run_leg_diagnosis(step1)

        _, kwargs = mock_client.evaluate_rtm.call_args
        assert kwargs["timeout"] is None


# ── T3: INDUSTRIAL → timeout=None ───────────────────────────────────────────

def test_t3_industrial_timeout_none():
    """T3: INDUSTRIAL context → evaluate_rtm called with timeout=None (client default)."""
    step1 = _step1("INDUSTRIAL")
    fake_context = {"sector": "INDUSTRIAL"}

    with patch("services.leg_diagnosis_svc.leg_client") as mock_client:
        mock_client.build_facility.return_value = {}
        mock_client.build_engine_context.return_value = fake_context
        mock_client.evaluate_rtm.return_value = _ok_response()

        run_leg_diagnosis(step1)

        _, kwargs = mock_client.evaluate_rtm.call_args
        assert kwargs["timeout"] is None


# ── T4: facility unchanged ───────────────────────────────────────────────────

def test_t4_facility_passed_unchanged():
    """T4: facility object from build_facility is passed verbatim to evaluate_rtm."""
    step1 = _step1("CONSTRUCTION")
    original_facility = {"has_diving": True, "worker_count": 80, "contract_amount_eok": 120.0}

    with patch("services.leg_diagnosis_svc.leg_client") as mock_client:
        mock_client.build_facility.return_value = original_facility
        mock_client.build_engine_context.return_value = {"sector": "CONSTRUCTION"}
        mock_client.evaluate_rtm.return_value = _ok_response()

        run_leg_diagnosis(step1)

        positional_args, _ = mock_client.evaluate_rtm.call_args
        assert positional_args[0] is original_facility


# ── T5: context unchanged ────────────────────────────────────────────────────

def test_t5_context_passed_unchanged():
    """T5: context from build_engine_context is passed verbatim; no extra keys injected."""
    step1 = _step1("CONSTRUCTION")
    original_context = {"sector": "CONSTRUCTION"}

    with patch("services.leg_diagnosis_svc.leg_client") as mock_client:
        mock_client.build_facility.return_value = {}
        mock_client.build_engine_context.return_value = original_context
        mock_client.evaluate_rtm.return_value = _ok_response()

        run_leg_diagnosis(step1)

        _, kwargs = mock_client.evaluate_rtm.call_args
        # context or None → non-empty dict passes through as-is
        assert kwargs["context"] is original_context
        assert set(kwargs["context"].keys()) == {"sector"}


# ── T6: retry zero ───────────────────────────────────────────────────────────

def test_t6_retry_zero_on_leg_runtime_error():
    """T6: LegRuntimeError propagates immediately; evaluate_rtm called exactly once."""
    step1 = _step1("CONSTRUCTION")

    with patch("services.leg_diagnosis_svc.leg_client") as mock_client:
        mock_client.build_facility.return_value = {}
        mock_client.build_engine_context.return_value = {"sector": "CONSTRUCTION"}
        mock_client.evaluate_rtm.side_effect = LegRuntimeError("request failed: timed out")

        with pytest.raises(LegRuntimeError, match="timed out"):
            run_leg_diagnosis(step1)

        assert mock_client.evaluate_rtm.call_count == 1


# ── T7: fallback zero ────────────────────────────────────────────────────────

def test_t7_fallback_zero_on_failure():
    """T7: LegRuntimeError propagates; no fallback to Compiler Core or legacy engine."""
    step1 = _step1("CONSTRUCTION")

    with patch("services.leg_diagnosis_svc.leg_client") as mock_client:
        mock_client.build_facility.return_value = {}
        mock_client.build_engine_context.return_value = {"sector": "CONSTRUCTION"}
        mock_client.evaluate_rtm.side_effect = LegRuntimeError("request failed: timed out")

        with pytest.raises(LegRuntimeError):
            run_leg_diagnosis(step1)

        # No other LEG client methods beyond build_facility / build_engine_context / evaluate_rtm
        called_methods = {c[0] for c in mock_client.method_calls}
        unexpected = called_methods - {"build_facility", "build_engine_context", "evaluate_rtm"}
        assert unexpected == set(), f"unexpected fallback calls: {unexpected}"


# ── T8: full_result unchanged ────────────────────────────────────────────────

def test_t8_full_result_contract_unchanged():
    """T8: normal response → full_result contract fields present; no timeout key injected."""
    step1 = _step1("CONSTRUCTION")
    step1.sector = "CONSTRUCTION"

    with patch("services.leg_diagnosis_svc.leg_client") as mock_client:
        mock_client.build_facility.return_value = {"has_diving": True}
        mock_client.build_engine_context.return_value = {"sector": "CONSTRUCTION"}
        mock_client.evaluate_rtm.return_value = _ok_response(obligation_count=90)

        result = run_leg_diagnosis(step1)

    # Core contract fields
    assert result["engine_family"] == "LEG"
    assert result["engine_version"] == svc.LEG_ENGINE_VERSION
    assert result["leg_status"] == "OK"
    assert result["applicable_count"] == 90
    assert len(result["key_obligations"]) == 90
    assert result["fallback_used"] is False

    # No timeout-related key leaking into full_result
    assert "rtm_timeout" not in result
    assert "timeout" not in result
    assert "construction_timeout" not in result
