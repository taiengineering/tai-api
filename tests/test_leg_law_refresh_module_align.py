"""WO-TAI-LEG-REFRESH-MODULE-ALIGN-001 — FINAL SCOPE: BUSINESS_EFFECTS=DISABLED.

_run_leg_law_refresh() passes scope to LEG, returns LEG response (including
changed_law_names) for monitoring. Business side effects (mark_rules_needs_review,
_publish_law_revision_board, _notify_safety_managers_by_law_change,
_mark_inspection_items_law_changed) are NOT called automatically.

Run from /Users/taiwangsim/tai-api/:
    python3 -m pytest tests/test_leg_law_refresh_module_align.py -v

Coverage:
  M01  changed_law_names present in LEG response → no business effects called
  M02  changed_law_names empty → no business effects called
  M03  changed_law_names passed through in return body
  M04  outcome ERROR → RuntimeError raised (no effects)
  M05  outcome PARTIAL_HOLD → RuntimeError raised (no effects)
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch
import pytest


_LAW_A = "산업안전보건법"
_LAW_B = "화학물질관리법"

_EFFECT_FNS = [
    "mark_rules_needs_review",
    "_publish_law_revision_board",
    "_notify_safety_managers_by_law_change",
    "_mark_inspection_items_law_changed",
]


def _make_sb(law_names=None):
    law_names = law_names or [_LAW_A]
    sb = MagicMock()
    is_data = MagicMock()
    is_data.data = [{"law_name": n} for n in law_names]
    cct_data = MagicMock()
    cct_data.data = []
    lm_data = MagicMock()
    lm_data.data = [
        {"law_name": n, "law_api_id": str(i + 10000), "law_mst_no": ""}
        for i, n in enumerate(law_names)
    ]

    def table_side_effect(table_name):
        m = MagicMock()
        if table_name == "inspection_sets":
            m.select.return_value.eq.return_value.execute.return_value = is_data
        elif table_name == "construction_check_templates":
            m.select.return_value.eq.return_value.execute.return_value = cct_data
        elif table_name == "law_master":
            m.select.return_value.eq.return_value.not_.is_.return_value.execute.return_value = lm_data
        return m

    sb.table.side_effect = table_side_effect
    return sb


def _run_handler(response_body, law_names=None):
    from services.scheduler.handlers import _run_leg_law_refresh
    sb = _make_sb(law_names or [_LAW_A])
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = response_body
    mock_lc = MagicMock()
    with patch("services.scheduler.handlers._sb", return_value=sb), \
         patch("requests.post", return_value=mock_resp), \
         patch("os.environ.get", side_effect=lambda k, d="": {
             "LEG_RUNTIME_URL": "https://leg.test",
             "LEG_INTERNAL_API_KEY": "test-token",
         }.get(k, d)), \
         patch.dict(sys.modules, {"routers.law_collector": mock_lc}):
        result = _run_leg_law_refresh({})
    return result, mock_lc


# ---------------------------------------------------------------------------
# M01: changed_law_names present → no business effects called
# ---------------------------------------------------------------------------

class TestM01NoEffectsWhenChangedLawNamesPresent:
    """M01: LEG returns changed_law_names → business side effects NOT called."""

    def test_mark_rules_not_called(self):
        result, mock_lc = _run_handler({
            "outcome": "SUCCESS",
            "changed_law_names": [_LAW_A],
            "run_id": "run-001",
        })
        mock_lc.mark_rules_needs_review.assert_not_called()

    def test_publish_board_not_called(self):
        result, mock_lc = _run_handler({
            "outcome": "SUCCESS",
            "changed_law_names": [_LAW_A, _LAW_B],
            "run_id": "run-001",
        })
        mock_lc._publish_law_revision_board.assert_not_called()

    def test_notify_not_called(self):
        result, mock_lc = _run_handler({
            "outcome": "SUCCESS",
            "changed_law_names": [_LAW_A],
            "run_id": "run-001",
        })
        mock_lc._notify_safety_managers_by_law_change.assert_not_called()

    def test_inspection_items_not_called(self):
        result, mock_lc = _run_handler({
            "outcome": "SUCCESS",
            "changed_law_names": [_LAW_A],
            "run_id": "run-001",
        })
        mock_lc._mark_inspection_items_law_changed.assert_not_called()


# ---------------------------------------------------------------------------
# M02: changed_law_names empty → no effects (trivially confirmed)
# ---------------------------------------------------------------------------

class TestM02NoEffectsOnEmptyNames:
    """M02: empty changed_law_names → effects not called."""

    def test_no_effects_on_no_change(self):
        result, mock_lc = _run_handler({
            "outcome": "NO_CHANGE",
            "changed_law_names": [],
            "run_id": "",
        })
        for fn in _EFFECT_FNS:
            getattr(mock_lc, fn).assert_not_called()


# ---------------------------------------------------------------------------
# M03: changed_law_names passthrough in return body
# ---------------------------------------------------------------------------

class TestM03ChangedLawNamesPassthrough:
    """M03: changed_law_names from LEG is accessible in the returned body."""

    def test_changed_law_names_in_body(self):
        result, _ = _run_handler({
            "outcome": "SUCCESS",
            "changed_law_names": [_LAW_A, _LAW_B],
            "run_id": "run-001",
        })
        assert result["body"]["changed_law_names"] == [_LAW_A, _LAW_B]

    def test_scope_sent_in_result(self):
        result, _ = _run_handler({
            "outcome": "NO_CHANGE",
            "changed_law_names": [],
            "run_id": "",
        })
        assert "scope_sent" in result


# ---------------------------------------------------------------------------
# M04–M05: ERROR / PARTIAL_HOLD → RuntimeError (no effects, no passthrough)
# ---------------------------------------------------------------------------

class TestM04ErrorOutcomeRaises:
    """M04: outcome ERROR → RuntimeError raised."""

    def test_error_raises(self):
        from services.scheduler.handlers import _run_leg_law_refresh
        sb = _make_sb()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"outcome": "ERROR", "error": "fetch failed"}
        with patch("services.scheduler.handlers._sb", return_value=sb), \
             patch("requests.post", return_value=mock_resp), \
             patch("os.environ.get", side_effect=lambda k, d="": {
                 "LEG_RUNTIME_URL": "https://leg.test",
                 "LEG_INTERNAL_API_KEY": "test-token",
             }.get(k, d)):
            with pytest.raises(RuntimeError, match="ERROR"):
                _run_leg_law_refresh({})


class TestM05PartialHoldRaises:
    """M05: outcome PARTIAL_HOLD → RuntimeError raised."""

    def test_partial_hold_raises(self):
        from services.scheduler.handlers import _run_leg_law_refresh
        sb = _make_sb()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"outcome": "PARTIAL_HOLD"}
        with patch("services.scheduler.handlers._sb", return_value=sb), \
             patch("requests.post", return_value=mock_resp), \
             patch("os.environ.get", side_effect=lambda k, d="": {
                 "LEG_RUNTIME_URL": "https://leg.test",
                 "LEG_INTERNAL_API_KEY": "test-token",
             }.get(k, d)):
            with pytest.raises(RuntimeError, match="PARTIAL_HOLD"):
                _run_leg_law_refresh({})
