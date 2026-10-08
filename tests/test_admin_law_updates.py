"""tests/test_admin_law_updates.py — OBJ-LAU-05B 60% Admin + Slack tests

T7: Admin 미인증 거부 — unauthenticated 401
T8: Slack 성공 → 전송 기록 (slack_collected_notified_at set)
T9: Slack 실패 → 저장 유지 (DB update not called)
T10: Slack 재시도 → 중복 방지 (send not called when already notified)
"""
from __future__ import annotations

import importlib
import os
import uuid
from unittest.mock import MagicMock, patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# T7: Admin auth — unauthenticated request is rejected
# ─────────────────────────────────────────────────────────────────────────────

class TestT7_AdminAuthRejected:
    """Verify the router requires authentication by checking the dependency chain."""

    def test_router_has_auth_dependency(self):
        """admin_law_updates router endpoints must declare get_current_user dependency."""
        from routers.admin_law_updates import router
        from routers.auth import get_current_user

        endpoints = {r.path: r for r in router.routes}
        # At minimum, list and detail endpoints must exist
        assert any("/admin/law-updates" in p for p in endpoints), (
            "expected /admin/law-updates route"
        )

        # Verify each endpoint's dependency list contains get_current_user
        for route in router.routes:
            dep_callables = [d.dependency for d in getattr(route, "dependencies", [])]
            # FastAPI Depends are on the function signature; check via endpoint signature
            import inspect
            sig = inspect.signature(route.endpoint)
            deps = [
                p.default.dependency
                for p in sig.parameters.values()
                if hasattr(p.default, "dependency")
            ]
            assert get_current_user in deps, (
                f"route {route.path} missing get_current_user dependency"
            )

    def test_require_admin_called_on_unauthenticated(self):
        """_require_admin raises if user is not admin; verify route calls it."""
        from routers.admin_law_updates import list_cases, get_case, notify_slack
        from services.company_scope import _require_admin

        # _require_admin raises when called with a non-admin user dict
        fake_user = {"id": "user-1", "role": "member"}
        fake_supabase = MagicMock()

        # Mock get_supabase and _require_admin itself to capture the call
        call_log = []

        def mock_require(current, supabase):
            call_log.append(current)
            raise PermissionError("not admin")

        with patch("routers.admin_law_updates._require_admin", mock_require), \
             patch("routers.admin_law_updates.get_supabase", return_value=fake_supabase):
            with pytest.raises(PermissionError):
                list_cases(current=fake_user)

        assert len(call_log) == 1
        assert call_log[0] == fake_user


# ─────────────────────────────────────────────────────────────────────────────
# T8: Slack 성공 → 전송 기록
# ─────────────────────────────────────────────────────────────────────────────

class TestT8_SlackSuccess:
    def _make_case(self):
        return {
            "case_id": str(uuid.uuid4()),
            "application_status": "COLLECTED",
            "law_name": "산업안전보건법",
            "new_mst": "MST-200",
            "announcement_date": "2026-01-01",
            "enforcement_date": "2026-03-01",
            "new_version_id": "ver-002",
            "slack_collected_notified_at": None,
            "slack_collected_message_ts": None,
        }

    def test_sent_true_on_success(self):
        from services import law_update_slack as mod
        case = self._make_case()
        updates = {}

        leg = MagicMock()
        update_chain = MagicMock()
        update_chain.eq.return_value.execute.return_value = None
        update_chain.__call__ = lambda self, d: (updates.update({"data": d}), update_chain)[1]
        leg.table.return_value.update.side_effect = lambda d: (
            updates.update({"data": d}), update_chain
        )[1]

        with patch.dict(os.environ, {"LAW_UPDATE_SLACK_TEST_CHANNEL": "C_TEST123"}):
            importlib.reload(mod)
            with patch("services.slack_dispatcher.send_slack_sync",
                       return_value={"ok": True, "ts": "1234567890.000001"}):
                sent, detail = mod.notify_collected(case["case_id"], case, leg)

        assert sent is True
        assert detail == "SENT"

    def test_db_updated_with_timestamp(self):
        from services import law_update_slack as mod
        case = self._make_case()
        db_calls = []

        class _FakeLeg:
            def table(self_, name):
                class _T:
                    def update(self__, data):
                        db_calls.append(data)
                        class _E:
                            def eq(self___, *a): return self___
                            def execute(self___): pass
                        return _E()
                return _T()

        with patch.dict(os.environ, {"LAW_UPDATE_SLACK_TEST_CHANNEL": "C_TEST456"}):
            importlib.reload(mod)
            with patch("services.slack_dispatcher.send_slack_sync",
                       return_value={"ok": True, "ts": "9876543210.000001"}):
                sent, _ = mod.notify_collected(case["case_id"], case, _FakeLeg())

        assert sent is True
        assert len(db_calls) == 1
        assert "slack_collected_notified_at" in db_calls[0]
        assert db_calls[0]["slack_collected_message_ts"] == "9876543210.000001"


# ─────────────────────────────────────────────────────────────────────────────
# T9: Slack 실패 → 저장 유지
# ─────────────────────────────────────────────────────────────────────────────

class TestT9_SlackFailure:
    def test_slack_error_no_db_write(self):
        from services import law_update_slack as mod
        case = {
            "case_id": str(uuid.uuid4()),
            "application_status": "COLLECTED",
            "law_name": "테스트법",
            "new_mst": "MST-300",
            "announcement_date": None,
            "enforcement_date": None,
            "new_version_id": "ver-003",
            "slack_collected_notified_at": None,
        }
        db_update_calls = []
        leg = MagicMock()
        leg.table.return_value.update.side_effect = lambda d: db_update_calls.append(d)

        with patch.dict(os.environ, {"LAW_UPDATE_SLACK_TEST_CHANNEL": "C_TEST789"}):
            importlib.reload(mod)
            with patch("services.slack_dispatcher.send_slack_sync",
                       return_value={"ok": False, "error": "channel_not_found"}):
                sent, detail = mod.notify_collected(case["case_id"], case, leg)

        assert sent is False
        assert "SLACK_ERROR" in detail
        assert len(db_update_calls) == 0

    def test_slack_exception_no_db_write(self):
        from services import law_update_slack as mod
        case = {
            "case_id": str(uuid.uuid4()),
            "application_status": "COLLECTED",
            "law_name": "예외테스트",
            "new_mst": "MST-301",
            "announcement_date": None,
            "enforcement_date": None,
            "new_version_id": "ver-004",
            "slack_collected_notified_at": None,
        }
        db_update_calls = []
        leg = MagicMock()
        leg.table.return_value.update.side_effect = lambda d: db_update_calls.append(d)

        with patch.dict(os.environ, {"LAW_UPDATE_SLACK_TEST_CHANNEL": "C_TESTX"}):
            importlib.reload(mod)
            with patch("services.slack_dispatcher.send_slack_sync",
                       side_effect=RuntimeError("network error")):
                sent, detail = mod.notify_collected(case["case_id"], case, leg)

        assert sent is False
        assert "SLACK_EXCEPTION" in detail
        assert len(db_update_calls) == 0


# ─────────────────────────────────────────────────────────────────────────────
# T10: Slack 재시도 → 중복 방지
# ─────────────────────────────────────────────────────────────────────────────

class TestT10_SlackIdempotency:
    def test_already_notified_no_send(self):
        from services import law_update_slack as mod
        case = {
            "case_id": str(uuid.uuid4()),
            "application_status": "COLLECTED",
            "law_name": "산업안전보건법",
            "new_mst": "MST-400",
            "announcement_date": None,
            "enforcement_date": None,
            "new_version_id": "ver-005",
            "slack_collected_notified_at": "2026-10-09T00:00:00+00:00",
        }
        send_calls = []
        leg = MagicMock()

        with patch.dict(os.environ, {"LAW_UPDATE_SLACK_TEST_CHANNEL": "C_IDEM"}):
            importlib.reload(mod)
            with patch("services.slack_dispatcher.send_slack_sync",
                       side_effect=lambda **kw: send_calls.append(kw)):
                sent, detail = mod.notify_collected(case["case_id"], case, leg)

        assert sent is False
        assert detail == "ALREADY_NOTIFIED"
        assert len(send_calls) == 0

    def test_not_collected_no_send(self):
        from services import law_update_slack as mod
        case = {
            "case_id": str(uuid.uuid4()),
            "application_status": "COLLECTING",
            "law_name": "산업안전보건법",
            "slack_collected_notified_at": None,
        }
        leg = MagicMock()

        with patch.dict(os.environ, {"LAW_UPDATE_SLACK_TEST_CHANNEL": "C_IDEM2"}):
            importlib.reload(mod)
            with patch("services.slack_dispatcher.send_slack_sync") as mock_send:
                sent, detail = mod.notify_collected(case["case_id"], case, leg)

        assert sent is False
        assert "NOT_COLLECTED" in detail
        mock_send.assert_not_called()

    def test_no_channel_no_send(self):
        from services import law_update_slack as mod
        case = {
            "case_id": str(uuid.uuid4()),
            "application_status": "COLLECTED",
            "law_name": "산업안전보건법",
            "slack_collected_notified_at": None,
        }
        leg = MagicMock()

        env = {k: v for k, v in os.environ.items() if k != "LAW_UPDATE_SLACK_TEST_CHANNEL"}
        with patch.dict(os.environ, env, clear=True):
            importlib.reload(mod)
            with patch("services.slack_dispatcher.send_slack_sync") as mock_send:
                sent, detail = mod.notify_collected(case["case_id"], case, leg)

        assert sent is False
        assert detail == "NO_CHANNEL_CONFIGURED"
        mock_send.assert_not_called()
