"""tests/test_admin_law_updates.py — OBJ-LAU-05B 60% Admin + Slack tests

T_DC: Dispatcher return contract — send_slack_sync returns None, _post_slack_direct returns dict
T7:   Admin 미인증 거부 — unauthenticated 401
T8:   Slack 성공 → 전송 기록 (slack_collected_notified_at + ts set)
T9:   Slack 실패 → 저장 유지 (DB update not called)
T10:  Slack 재시도 → 중복 방지 (send not called when already notified)
"""
from __future__ import annotations

import importlib
import os
import uuid
from unittest.mock import MagicMock, patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# T_DC: Dispatcher return contract
# send_slack_sync returns None (fire-and-forget).
# _post_slack_direct returns dict — new code must NOT rely on send_slack_sync.
# ─────────────────────────────────────────────────────────────────────────────

class TestTDC_DispatcherContract:
    def test_send_slack_sync_returns_none(self):
        """Verify send_slack_sync has no return value (returns None)."""
        from services.slack_dispatcher import send_slack_sync
        import inspect
        src = inspect.getsource(send_slack_sync)
        # send_slack_sync has no `return <value>` — only fire-and-forget calls.
        assert "return True" not in src
        assert "return False" not in src

    def test_post_slack_direct_returns_dict_on_http_error(self):
        """_post_slack_direct always returns a dict — never None."""
        from services import law_update_slack as mod
        import httpx
        with patch.object(httpx, "post", side_effect=ConnectionError("timeout")):
            result = mod._post_slack_direct("C_TEST", "xoxb-fake", "hello")
        assert isinstance(result, dict)
        assert result.get("ok") is False
        assert "error" in result

    def test_post_slack_direct_returns_ts_on_success(self):
        """_post_slack_direct returns ts when Slack API ok=true."""
        from services import law_update_slack as mod
        import httpx
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {"ok": True, "ts": "1234567890.000001", "channel": "C_X"}
        with patch.object(httpx, "post", return_value=fake_resp):
            result = mod._post_slack_direct("C_X", "xoxb-fake", "hello")
        assert result["ok"] is True
        assert result["ts"] == "1234567890.000001"


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
        assert any("/admin/law-updates" in p for p in endpoints), (
            "expected /admin/law-updates route"
        )

        for route in router.routes:
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
        from routers.admin_law_updates import list_cases
        fake_user = {"id": "user-1", "role": "member"}
        fake_supabase = MagicMock()
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
        leg = MagicMock()
        mock_result = MagicMock()
        mock_result.data = [{"case_id": case["case_id"]}]  # 1 row updated → not a race
        leg.table.return_value.update.return_value.eq.return_value.is_.return_value.execute.return_value = mock_result

        with patch.dict(os.environ, {
            "LAW_UPDATE_SLACK_TEST_CHANNEL": "C_TEST123",
            "SLACK_BOT_TOKEN1": "xoxb-fake-token",
        }):
            importlib.reload(mod)
            with patch("services.law_update_slack._post_slack_direct",
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
                            def is_(self___, *a): return self___
                            def execute(self___): pass
                        return _E()
                return _T()

        with patch.dict(os.environ, {
            "LAW_UPDATE_SLACK_TEST_CHANNEL": "C_TEST456",
            "SLACK_BOT_TOKEN1": "xoxb-fake-token",
        }):
            importlib.reload(mod)
            with patch("services.law_update_slack._post_slack_direct",
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
    def _base_case(self):
        return {
            "case_id": str(uuid.uuid4()),
            "application_status": "COLLECTED",
            "law_name": "테스트법",
            "new_mst": "MST-300",
            "announcement_date": None,
            "enforcement_date": None,
            "new_version_id": "ver-003",
            "slack_collected_notified_at": None,
        }

    def test_slack_error_no_db_write(self):
        from services import law_update_slack as mod
        case = self._base_case()
        db_update_calls = []
        leg = MagicMock()
        leg.table.return_value.update.side_effect = lambda d: db_update_calls.append(d)

        with patch.dict(os.environ, {
            "LAW_UPDATE_SLACK_TEST_CHANNEL": "C_TEST789",
            "SLACK_BOT_TOKEN1": "xoxb-fake-token",
        }):
            importlib.reload(mod)
            with patch("services.law_update_slack._post_slack_direct",
                       return_value={"ok": False, "error": "channel_not_found"}):
                sent, detail = mod.notify_collected(case["case_id"], case, leg)

        assert sent is False
        assert "SLACK_ERROR" in detail
        assert len(db_update_calls) == 0

    def test_slack_http_error_no_db_write(self):
        from services import law_update_slack as mod
        case = self._base_case()
        db_update_calls = []
        leg = MagicMock()
        leg.table.return_value.update.side_effect = lambda d: db_update_calls.append(d)

        with patch.dict(os.environ, {
            "LAW_UPDATE_SLACK_TEST_CHANNEL": "C_TESTX",
            "SLACK_BOT_TOKEN1": "xoxb-fake-token",
        }):
            importlib.reload(mod)
            with patch("services.law_update_slack._post_slack_direct",
                       return_value={"ok": False, "error": "network error"}):
                sent, detail = mod.notify_collected(case["case_id"], case, leg)

        assert sent is False
        assert "SLACK_ERROR" in detail
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
        leg = MagicMock()
        send_calls = []

        with patch.dict(os.environ, {
            "LAW_UPDATE_SLACK_TEST_CHANNEL": "C_IDEM",
            "SLACK_BOT_TOKEN1": "xoxb-fake",
        }):
            importlib.reload(mod)
            with patch("services.law_update_slack._post_slack_direct",
                       side_effect=lambda *a, **kw: send_calls.append(a)):
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

        with patch.dict(os.environ, {
            "LAW_UPDATE_SLACK_TEST_CHANNEL": "C_IDEM2",
            "SLACK_BOT_TOKEN1": "xoxb-fake",
        }):
            importlib.reload(mod)
            with patch("services.law_update_slack._post_slack_direct") as mock_send:
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
            with patch("services.law_update_slack._post_slack_direct") as mock_send:
                sent, detail = mod.notify_collected(case["case_id"], case, leg)

        assert sent is False
        assert detail == "NO_CHANNEL_CONFIGURED"
        mock_send.assert_not_called()

    def test_no_token_no_send(self):
        """When both SLACK_BOT_TOKEN1 and SLACK_BOT_TOKEN are unset, skip send."""
        from services import law_update_slack as mod
        case = {
            "case_id": str(uuid.uuid4()),
            "application_status": "COLLECTED",
            "law_name": "산업안전보건법",
            "slack_collected_notified_at": None,
        }
        leg = MagicMock()

        env = {
            k: v for k, v in os.environ.items()
            if k not in ("SLACK_BOT_TOKEN1", "SLACK_BOT_TOKEN", "LAW_UPDATE_SLACK_TEST_CHANNEL")
        }
        env["LAW_UPDATE_SLACK_TEST_CHANNEL"] = "C_NOTOKEN"
        with patch.dict(os.environ, env, clear=True):
            importlib.reload(mod)
            with patch("services.law_update_slack._post_slack_direct") as mock_send:
                sent, detail = mod.notify_collected(case["case_id"], case, leg)

        assert sent is False
        assert detail == "NO_SLACK_TOKEN"
        mock_send.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# T_P2: PATCH-2 — Slack 중복 전송 방지 (conditional UPDATE + race detection)
#
# BLOCKER NOTE (for GPT):
#   조건부 UPDATE (WHERE slack_collected_notified_at IS NULL)로 DB 레코드 정합성은 보호됩니다.
#   단, Slack 메시지 정확히 1건 보장(true serialization)은 SELECT FOR UPDATE 또는
#   별도 claim 컬럼이 필요하며, 두 방법 모두 migration이 필요합니다.
#   현재 구현: 중복 DB 기록 방지(SENT_RACE_DUPLICATE). 중복 Slack 전송 가능성 존재.
# ─────────────────────────────────────────────────────────────────────────────

class TestTP2_SlackRaceDuplicate:
    def _make_case(self):
        return {
            "case_id": str(uuid.uuid4()),
            "application_status": "COLLECTED",
            "law_name": "테스트법",
            "new_mst": "MST-RACE",
            "announcement_date": None,
            "enforcement_date": None,
            "new_version_id": "ver-race",
            "slack_collected_notified_at": None,
            "slack_collected_message_ts": None,
        }

    def test_race_detected_returns_sent_race_duplicate(self):
        """Conditional UPDATE matches 0 rows → SENT_RACE_DUPLICATE (DB already written by other request)."""
        from services import law_update_slack as mod
        case = self._make_case()

        class _FakeResult:
            data = []  # 0 rows updated → race condition detected

        class _FakeLeg:
            def table(self_, name):
                class _T:
                    def update(self__, data):
                        class _E:
                            def eq(self___, *a): return self___
                            def is_(self___, *a): return self___
                            def execute(self___): return _FakeResult()
                        return _E()
                return _T()

        with patch.dict(os.environ, {
            "LAW_UPDATE_SLACK_TEST_CHANNEL": "C_RACE",
            "SLACK_BOT_TOKEN1": "xoxb-fake",
        }):
            importlib.reload(mod)
            with patch("services.law_update_slack._post_slack_direct",
                       return_value={"ok": True, "ts": "1234567890.000001"}):
                sent, detail = mod.notify_collected(case["case_id"], case, _FakeLeg())

        assert sent is True
        assert detail == "SENT_RACE_DUPLICATE"

    def test_normal_update_returns_sent(self):
        """Conditional UPDATE affects rows → SENT (winner, no race)."""
        from services import law_update_slack as mod
        case = self._make_case()

        class _FakeResult:
            data = [{"case_id": case["case_id"]}]  # 1 row updated → winner

        class _FakeLeg:
            def table(self_, name):
                class _T:
                    def update(self__, data):
                        class _E:
                            def eq(self___, *a): return self___
                            def is_(self___, *a): return self___
                            def execute(self___): return _FakeResult()
                        return _E()
                return _T()

        with patch.dict(os.environ, {
            "LAW_UPDATE_SLACK_TEST_CHANNEL": "C_WIN",
            "SLACK_BOT_TOKEN1": "xoxb-fake",
        }):
            importlib.reload(mod)
            with patch("services.law_update_slack._post_slack_direct",
                       return_value={"ok": True, "ts": "9999999999.000001"}):
                sent, detail = mod.notify_collected(case["case_id"], case, _FakeLeg())

        assert sent is True
        assert detail == "SENT"

    def test_db_update_exception_returns_sent_but_db_failed(self):
        """DB update raises → SENT_BUT_DB_UPDATE_FAILED (Slack sent, DB not recorded)."""
        from services import law_update_slack as mod
        case = self._make_case()

        class _RaisingLeg:
            def table(self_, name):
                class _T:
                    def update(self__, data):
                        raise RuntimeError("DB connection lost")
                return _T()

        with patch.dict(os.environ, {
            "LAW_UPDATE_SLACK_TEST_CHANNEL": "C_DBERR",
            "SLACK_BOT_TOKEN1": "xoxb-fake",
        }):
            importlib.reload(mod)
            with patch("services.law_update_slack._post_slack_direct",
                       return_value={"ok": True, "ts": "1111111111.000001"}):
                sent, detail = mod.notify_collected(case["case_id"], case, _RaisingLeg())

        assert sent is True
        assert "SENT_BUT_DB_UPDATE_FAILED" in detail

    def test_conditional_update_uses_null_filter(self):
        """Verify .is_('slack_collected_notified_at', 'null') is called."""
        from services import law_update_slack as mod
        case = self._make_case()
        is_calls = []

        class _FakeLeg:
            def table(self_, name):
                class _T:
                    def update(self__, data):
                        class _E:
                            def eq(self___, *a): return self___
                            def is_(self___, col, val):
                                is_calls.append((col, val))
                                return self___
                            def execute(self___): pass
                        return _E()
                return _T()

        with patch.dict(os.environ, {
            "LAW_UPDATE_SLACK_TEST_CHANNEL": "C_COND",
            "SLACK_BOT_TOKEN1": "xoxb-fake",
        }):
            importlib.reload(mod)
            with patch("services.law_update_slack._post_slack_direct",
                       return_value={"ok": True, "ts": "2222222222.000001"}):
                mod.notify_collected(case["case_id"], case, _FakeLeg())

        assert len(is_calls) == 1
        assert is_calls[0] == ("slack_collected_notified_at", "null")


# ─────────────────────────────────────────────────────────────────────────────
# T_P3: PATCH-3 — Admin 목록 전체 건수
# ─────────────────────────────────────────────────────────────────────────────

class TestTP3_AdminListCount:
    def test_list_uses_res_count_when_available(self):
        """list_cases uses res.count (total) when Supabase returns count."""
        from routers.admin_law_updates import list_cases

        class _FakeResult:
            data = [{"case_id": "c1"}, {"case_id": "c2"}]
            count = 42  # total across all pages

        class _FakeLeg:
            def table(self_, name):
                class _Q:
                    def select(self__, *a, **kw): return self__
                    def order(self__, *a, **kw): return self__
                    def limit(self__, *a): return self__
                    def offset(self__, *a): return self__
                    def eq(self__, *a): return self__
                    def execute(self__): return _FakeResult()
                return _Q()

        with patch("routers.admin_law_updates._require_admin"), \
             patch("routers.admin_law_updates.get_supabase", return_value=MagicMock()), \
             patch("routers.admin_law_updates._get_leg_client", return_value=_FakeLeg()):
            result = list_cases(current={"id": "admin-1"})

        assert result["count"] == 42
        assert len(result["data"]) == 2

    def test_list_falls_back_to_data_length_when_no_count(self):
        """list_cases falls back to len(data) when res.count is None."""
        from routers.admin_law_updates import list_cases

        class _FakeResultNoCount:
            data = [{"case_id": "c1"}, {"case_id": "c2"}, {"case_id": "c3"}]
            count = None  # Supabase didn't return count

        class _FakeLeg:
            def table(self_, name):
                class _Q:
                    def select(self__, *a, **kw): return self__
                    def order(self__, *a, **kw): return self__
                    def limit(self__, *a): return self__
                    def offset(self__, *a): return self__
                    def eq(self__, *a): return self__
                    def execute(self__): return _FakeResultNoCount()
                return _Q()

        with patch("routers.admin_law_updates._require_admin"), \
             patch("routers.admin_law_updates.get_supabase", return_value=MagicMock()), \
             patch("routers.admin_law_updates._get_leg_client", return_value=_FakeLeg()):
            result = list_cases(current={"id": "admin-1"})

        assert result["count"] == 3

    def test_list_select_passes_count_exact(self):
        """list_cases passes count='exact' to .select() for Supabase total-count header."""
        from routers.admin_law_updates import list_cases
        select_kwargs = []

        class _FakeLeg:
            def table(self_, name):
                class _Q:
                    def select(self__, cols, **kw):
                        select_kwargs.append(kw)
                        return self__
                    def order(self__, *a, **kw): return self__
                    def limit(self__, *a): return self__
                    def offset(self__, *a): return self__
                    def eq(self__, *a): return self__
                    def execute(self__):
                        class R:
                            data = []
                            count = 0
                        return R()
                return _Q()

        with patch("routers.admin_law_updates._require_admin"), \
             patch("routers.admin_law_updates.get_supabase", return_value=MagicMock()), \
             patch("routers.admin_law_updates._get_leg_client", return_value=_FakeLeg()):
            list_cases(current={"id": "admin-1"})

        assert any(kw.get("count") == "exact" for kw in select_kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# T_P4: PATCH-4 — Admin 상세 계약 검증
# ─────────────────────────────────────────────────────────────────────────────

class TestTP4_AdminDetail:
    def test_notify_slack_returns_sent_false_detail(self):
        """notify_slack endpoint returns sent=false + detail without raising."""
        from routers.admin_law_updates import notify_slack

        case_row = {
            "case_id": "case-p4-001",
            "application_status": "COLLECTED",
            "law_name": "테스트법",
            "new_mst": "MST-P4",
            "announcement_date": None,
            "enforcement_date": None,
            "new_version_id": "ver-p4",
            "slack_collected_notified_at": "2026-10-09T00:00:00+00:00",
            "slack_collected_message_ts": "1234567890.000001",
        }

        class _FakeLeg:
            def table(self_, name):
                class _Q:
                    def select(self__, *a, **kw): return self__
                    def eq(self__, *a): return self__
                    def execute(self__):
                        class R:
                            data = [case_row]
                        return R()
                return _Q()

        with patch("routers.admin_law_updates._require_admin"), \
             patch("routers.admin_law_updates.get_supabase", return_value=MagicMock()), \
             patch("routers.admin_law_updates._get_leg_client", return_value=_FakeLeg()):
            result = notify_slack(case_id="case-p4-001", current={"id": "admin-1"})

        assert result["status"] == "success"
        assert result["sent"] is False
        assert result["detail"] == "ALREADY_NOTIFIED"

    def test_notify_slack_404_on_missing_case(self):
        """notify_slack raises 404 when case not found."""
        from routers.admin_law_updates import notify_slack
        from fastapi import HTTPException

        class _EmptyLeg:
            def table(self_, name):
                class _Q:
                    def select(self__, *a, **kw): return self__
                    def eq(self__, *a): return self__
                    def execute(self__):
                        class R:
                            data = []
                        return R()
                return _Q()

        with patch("routers.admin_law_updates._require_admin"), \
             patch("routers.admin_law_updates.get_supabase", return_value=MagicMock()), \
             patch("routers.admin_law_updates._get_leg_client", return_value=_EmptyLeg()):
            with pytest.raises(HTTPException) as exc_info:
                notify_slack(case_id="nonexistent", current={"id": "admin-1"})
        assert exc_info.value.status_code == 404
