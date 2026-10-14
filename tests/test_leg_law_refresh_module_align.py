"""WO-TAI-LEG-REFRESH-MODULE-ALIGN-001 — _apply_law_change_effects unit tests.

Single detection responsibility: LEG detect_changed_laws() (lsHstInf) is the sole
detection point. _apply_law_change_effects() applies TAI business side effects
using law names returned by LEG — no re-detection, no data.go.kr call.

Run from /Users/taiwangsim/tai-api/:
    python3 -m pytest tests/test_leg_law_refresh_module_align.py -v

Coverage:
  A01  changed_law_names → mark_rules_needs_review called per law
  A02  changed_law_names → _notify_safety_managers_by_law_change called per law
  A03  changed_law_names → _mark_inspection_items_law_changed called per law
  A04  law_id in lm_by_name → _publish_law_revision_board called
  A05  law_id NOT in lm_by_name → _publish_law_revision_board NOT called
  A06  individual law exception → caught, logged, other laws continue
  A07  empty changed_law_names → effects not called, empty details
  A08  _run_leg_law_refresh: changed_law_names in LEG response → effects called
  A09  _run_leg_law_refresh: empty changed_law_names → effects NOT called

Note: routers.law_collector cannot be imported directly in tests because of a
stale _get_cfg dependency in routers.messaging. We inject a mock via sys.modules
so that the local `from routers.law_collector import ...` in _apply_law_change_effects
receives the mock module.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch, call
import pytest


_LAW_A = "산업안전보건법"
_LAW_B = "화학물질관리법"
_LAW_ID_A = "uuid-law-a"
_LAW_ID_B = "uuid-law-b"

_LM_BY_NAME = {
    _LAW_A: {"id": _LAW_ID_A, "law_api_id": "22072", "law_mst_no": "21000"},
    _LAW_B: {"id": _LAW_ID_B, "law_api_id": "55555", "law_mst_no": ""},
}


def _make_mock_lc(rules_rv=2, notify_rv=3, items_rv=4, rules_side_effect=None):
    """Build a mock routers.law_collector module with configurable return values."""
    m = MagicMock()
    if rules_side_effect:
        m.mark_rules_needs_review.side_effect = rules_side_effect
    else:
        m.mark_rules_needs_review.return_value = rules_rv
    m._publish_law_revision_board.return_value = None
    m._notify_safety_managers_by_law_change.return_value = notify_rv
    m._mark_inspection_items_law_changed.return_value = items_rv
    return m


def _run_apply(changed_law_names, lm_by_name=None, sb=None, mock_lc=None):
    """Call _apply_law_change_effects with a mocked routers.law_collector module."""
    from services.scheduler.handlers import _apply_law_change_effects
    sb = sb or MagicMock()
    lm = lm_by_name if lm_by_name is not None else _LM_BY_NAME
    lc = mock_lc or _make_mock_lc()
    with patch.dict(sys.modules, {"routers.law_collector": lc}):
        result = _apply_law_change_effects(changed_law_names, lm, sb)
    return (
        result,
        lc.mark_rules_needs_review,
        lc._publish_law_revision_board,
        lc._notify_safety_managers_by_law_change,
        lc._mark_inspection_items_law_changed,
    )


# ---------------------------------------------------------------------------
# A01–A03: Core side effects called for each law
# ---------------------------------------------------------------------------

class TestA01MarkRulesNeedsReview:
    """A01: mark_rules_needs_review called once per changed law."""

    def test_called_once_for_single_law(self):
        result, m_rules, _, _, _ = _run_apply([_LAW_A])
        m_rules.assert_called_once()
        assert m_rules.call_args.args[0] == _LAW_A

    def test_called_for_each_law(self):
        result, m_rules, _, _, _ = _run_apply([_LAW_A, _LAW_B])
        assert m_rules.call_count == 2
        names_called = [c.args[0] for c in m_rules.call_args_list]
        assert _LAW_A in names_called
        assert _LAW_B in names_called


class TestA02NotifySafetyManagers:
    """A02: _notify_safety_managers_by_law_change called once per changed law."""

    def test_called_once_for_single_law(self):
        result, _, _, m_notify, _ = _run_apply([_LAW_A])
        m_notify.assert_called_once()
        assert m_notify.call_args.args[0] == _LAW_A

    def test_called_for_each_law(self):
        result, _, _, m_notify, _ = _run_apply([_LAW_A, _LAW_B])
        assert m_notify.call_count == 2


class TestA03MarkInspectionItems:
    """A03: _mark_inspection_items_law_changed called once per changed law."""

    def test_called_once_for_single_law(self):
        result, _, _, _, m_items = _run_apply([_LAW_A])
        m_items.assert_called_once()
        assert m_items.call_args.args[0] == _LAW_A

    def test_result_contains_items_count(self):
        result, _, _, _, _ = _run_apply([_LAW_A])
        assert result["details"][0]["items_law_changed"] == 4


# ---------------------------------------------------------------------------
# A04–A05: _publish_law_revision_board conditional on law_id
# ---------------------------------------------------------------------------

class TestA04PublishBoardWithLawId:
    """A04: law_id found in lm_by_name → _publish_law_revision_board called."""

    def test_board_called_when_law_id_found(self):
        result, _, m_board, _, _ = _run_apply([_LAW_A])
        m_board.assert_called_once()
        assert m_board.call_args.args[0] == _LAW_ID_A
        assert m_board.call_args.args[1] == _LAW_A

    def test_law_id_found_flag_true(self):
        result, _, _, _, _ = _run_apply([_LAW_A])
        assert result["details"][0]["law_id_found"] is True


class TestA05PublishBoardSkippedWithoutLawId:
    """A05: law not in lm_by_name → _publish_law_revision_board NOT called."""

    def test_board_not_called_when_law_missing(self):
        result, _, m_board, _, _ = _run_apply([_LAW_A], lm_by_name={})
        m_board.assert_not_called()

    def test_law_id_found_flag_false(self):
        result, _, _, _, _ = _run_apply([_LAW_A], lm_by_name={})
        assert result["details"][0]["law_id_found"] is False

    def test_other_effects_still_called(self):
        """Even without law_id, the other three effects still run."""
        result, m_rules, _, m_notify, m_items = _run_apply([_LAW_A], lm_by_name={})
        m_rules.assert_called_once()
        m_notify.assert_called_once()
        m_items.assert_called_once()


# ---------------------------------------------------------------------------
# A06: Exception for one law does not block others
# ---------------------------------------------------------------------------

class TestA06PartialException:
    """A06: Exception on first law → caught and logged, second law still processed."""

    def test_exception_does_not_block_remaining_laws(self):
        from services.scheduler.handlers import _apply_law_change_effects
        sb = MagicMock()

        def rules_side_effect(law_name, change_summary, supabase):
            if law_name == _LAW_A:
                raise RuntimeError("DB write failed")
            return 1

        lc = _make_mock_lc(rules_side_effect=rules_side_effect)
        with patch.dict(sys.modules, {"routers.law_collector": lc}):
            result = _apply_law_change_effects([_LAW_A, _LAW_B], _LM_BY_NAME, sb)

        assert result["law_effects_applied"] == 2
        error_detail = next(d for d in result["details"] if d["law_name"] == _LAW_A)
        ok_detail = next(d for d in result["details"] if d["law_name"] == _LAW_B)
        assert "error" in error_detail
        assert "error" not in ok_detail


# ---------------------------------------------------------------------------
# A07: Empty input
# ---------------------------------------------------------------------------

class TestA07EmptyInput:
    """A07: empty changed_law_names → effects not called, details=[]."""

    def test_empty_list_returns_zero_effects(self):
        result, m_rules, m_board, m_notify, m_items = _run_apply([])
        assert result["law_effects_applied"] == 0
        assert result["details"] == []
        m_rules.assert_not_called()
        m_board.assert_not_called()
        m_notify.assert_not_called()
        m_items.assert_not_called()


# ---------------------------------------------------------------------------
# A08–A09: _run_leg_law_refresh integration
# ---------------------------------------------------------------------------

class TestA08RunLegLawRefreshEffectsTriggered:
    """A08: LEG response includes changed_law_names → _apply_law_change_effects called."""

    def test_effects_called_when_changed_law_names_present(self):
        from services.scheduler.handlers import _run_leg_law_refresh

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "outcome": "SUCCESS",
            "changed_law_names": [_LAW_A],
            "run_id": "run-001",
        }

        sb = MagicMock()
        is_data = MagicMock()
        is_data.data = [{"law_name": _LAW_A}]
        cct_data = MagicMock()
        cct_data.data = []
        lm_data = MagicMock()
        lm_data.data = [{"id": _LAW_ID_A, "law_name": _LAW_A, "law_api_id": "22072", "law_mst_no": "21000"}]

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

        with patch("services.scheduler.handlers._sb", return_value=sb), \
             patch("requests.post", return_value=mock_response), \
             patch("os.environ.get", side_effect=lambda k, d="": {
                 "LEG_RUNTIME_URL": "https://leg.test",
                 "LEG_INTERNAL_API_KEY": "test-token",
             }.get(k, d)), \
             patch("services.scheduler.handlers._apply_law_change_effects", return_value={
                 "law_effects_applied": 1, "details": [],
             }) as mock_effects:
            result = _run_leg_law_refresh({})

        mock_effects.assert_called_once()
        call_names = mock_effects.call_args.args[0]
        assert _LAW_A in call_names
        assert result["law_effects"]["law_effects_applied"] == 1


class TestA09RunLegLawRefreshNoEffectsOnEmpty:
    """A09: LEG response has no changed_law_names → _apply_law_change_effects NOT called."""

    def test_effects_not_called_when_no_changed_laws(self):
        from services.scheduler.handlers import _run_leg_law_refresh

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "outcome": "NO_CHANGE",
            "changed_law_names": [],
            "run_id": "",
        }

        sb = MagicMock()

        def table_side_effect(table_name):
            m = MagicMock()
            m.select.return_value.eq.return_value.execute.return_value.data = []
            m.select.return_value.eq.return_value.not_.is_.return_value.execute.return_value.data = []
            return m

        sb.table.side_effect = table_side_effect

        with patch("services.scheduler.handlers._sb", return_value=sb), \
             patch("requests.post", return_value=mock_response), \
             patch("os.environ.get", side_effect=lambda k, d="": {
                 "LEG_RUNTIME_URL": "https://leg.test",
                 "LEG_INTERNAL_API_KEY": "test-token",
             }.get(k, d)), \
             patch("services.scheduler.handlers._apply_law_change_effects") as mock_effects:
            result = _run_leg_law_refresh({})

        mock_effects.assert_not_called()
        assert result["law_effects"] == {}
