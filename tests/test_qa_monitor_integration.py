"""WO-016 — QA Monitor Integration 계약 검증.

WP-A Cron Service (T01-T06):
  T01  run_monitor_cron — requires_alert=False → outbox 미삽입, outbox_status=None
  T02  run_monitor_cron — requires_alert=True + slack_enabled + dry_run=False → SENT
  T03  run_monitor_cron — requires_alert=True + slack_enabled + dry_run=True → 발송 없음
  T04  run_monitor_cron — requires_alert=True + slack_disabled → 발송 없음
  T05  run_monitor_cron — scheduled_for 지정 → Slot 역산 후 monitor_twice_daily 에 전달
  T06  run_monitor_cron — 중복 호출 → DEDUPED (dedupe_key UNIQUE 억제)

WP-B Slack Event Type (T07-T10):
  T07  QA_WORKFLOW_MONITOR_ALERT → EVENT_TYPE_CHANNEL[...] == CHANNEL_QA
  T08  QA_WORKFLOW_MONITOR_ALERT → QA_ADMIN_BUTTON_EVENTS 포함 확인
  T09  QA_WORKFLOW_MONITOR_ALERT → EVENT_TYPE_ADMIN_PATH[...] == "/qa/dashboard"
  T10  _resolve_channel QA_WORKFLOW_MONITOR_ALERT → CHANNEL_QA

WP-C Outbox Service (T11-T18):
  T11  accept_monitor_notification — 신규 삽입 → (True, row_id)
  T12  accept_monitor_notification — 중복 dedupe_key → (False, None)
  T13  _claim — PENDING → CLAIMED (claim_token 반환)
  T14  _claim — CAS 실패 → None
  T15  send_monitor_notification — SENT 경로
  T16  send_monitor_notification — send_slack False → UNKNOWN
  T17  send_monitor_notification — send_slack 예외 → UNKNOWN
  T18  send_monitor_notification — Claim 실패 → SKIPPED

WP-D Fail-Closed Gate (T19-T21):
  T19  requires_alert + env=true + dry_run=False → outbox 삽입·발송
  T20  requires_alert + env 미설정 + dry_run=False → 발송 없음
  T21  requires_alert + env=true + dry_run=True → 발송 없음 (dry_run 우선)

Regression (T22-T24):
  T22  기존 QA 이벤트 5종 채널 매핑 회귀 없음
  T23  run_stale_scan_cron — WP-E 계약 보존 (Slack 없음, detection-only)
  T24  monitor_twice_daily requires_alert=False → outbox 미삽입 (dry_run/env 무관)

실제 외부 호출 없음 — 모든 httpx/supabase/send_slack 완전 mock.
asyncio.run() 패턴 사용 (pytest-asyncio 미사용 — 기존 테스트 패턴 준수).
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import services.slack_dispatcher as dispatcher
import services.qa_monitor_outbox_svc as outbox_svc
import services.qa_monitor_cron_svc as cron_svc


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────

def _make_supabase_mock(*, insert_data=None, update_data=None):
    """Supabase 클라이언트 체인 mock 빌더."""
    sb = MagicMock()

    def _chain(data):
        result = MagicMock()
        result.data = data if data is not None else []
        chain = MagicMock()
        chain.execute.return_value = result
        chain.eq.return_value = chain
        chain.or_.return_value = chain
        chain.lt.return_value = chain
        chain.in_.return_value = chain
        chain.limit.return_value = chain
        chain.order.return_value = chain
        chain.select.return_value = chain
        return chain

    sb.table.return_value.upsert.return_value = _chain(
        insert_data if insert_data is not None else [{"id": "row-001"}]
    )
    sb.table.return_value.update.return_value = _chain(
        update_data if update_data is not None else [{"id": "row-001"}]
    )
    return sb


def _make_monitor_result(requires_alert: bool, status_code: str = "WORKFLOW_NOT_OBSERVED"):
    slot_utc = "2026-10-30T10:00:00Z"
    slack_msg = None
    if requires_alert:
        slack_msg = {
            "text": f"⚠️ {status_code} — qa-twice-daily.yml",
            "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": "test"}}],
        }
    return {
        "slot_utc":       slot_utc,
        "status_code":    status_code,
        "requires_alert": requires_alert,
        "run_id":         None,
        "evidence":       {},
        "slack_message":  slack_msg,
        "slack_sent":     False,
        "detected_at":    "2026-10-30T11:05:00Z",
    }


# ── WP-A Cron Service (T01-T06) ───────────────────────────────────────────────

class TestCronService:
    def test_t01_no_alert_no_outbox(self):
        """T01: requires_alert=False → outbox 미삽입, outbox_status=None."""
        with patch(
            "services.qa_monitor_cron_svc.monitor_twice_daily",
            new_callable=AsyncMock,
            return_value=_make_monitor_result(requires_alert=False),
        ):
            result = asyncio.run(cron_svc.run_monitor_cron(dry_run=False))
        assert result["requires_alert"] is False
        assert result["outbox_status"] is None

    def test_t02_alert_slack_enabled_dry_run_false_sent(self, monkeypatch):
        """T02: requires_alert=True + slack_enabled + dry_run=False → SENT."""
        monkeypatch.setenv("QA_MONITOR_SLACK_ENABLED", "true")
        sb = _make_supabase_mock()

        with (
            patch(
                "services.qa_monitor_cron_svc.monitor_twice_daily",
                new_callable=AsyncMock,
                return_value=_make_monitor_result(requires_alert=True),
            ),
            patch(
                "services.qa_monitor_cron_svc.accept_monitor_notification",
                return_value=(True, "row-001"),
            ),
            patch(
                "services.qa_monitor_cron_svc.send_monitor_notification",
                new_callable=AsyncMock,
                return_value="SENT",
            ),
        ):
            result = asyncio.run(cron_svc.run_monitor_cron(supabase=sb, dry_run=False))

        assert result["outbox_status"] == "SENT"
        assert result["slack_enabled"] is True

    def test_t03_alert_slack_enabled_dry_run_true_no_send(self, monkeypatch):
        """T03: dry_run=True → Slack 발송 없음."""
        monkeypatch.setenv("QA_MONITOR_SLACK_ENABLED", "true")
        with patch(
            "services.qa_monitor_cron_svc.monitor_twice_daily",
            new_callable=AsyncMock,
            return_value=_make_monitor_result(requires_alert=True),
        ):
            result = asyncio.run(cron_svc.run_monitor_cron(dry_run=True))
        assert result["outbox_status"] is None
        assert result["slack_sent"] is False

    def test_t04_alert_slack_disabled_no_send(self, monkeypatch):
        """T04: QA_MONITOR_SLACK_ENABLED 미설정 → Slack 발송 없음."""
        monkeypatch.delenv("QA_MONITOR_SLACK_ENABLED", raising=False)
        with patch(
            "services.qa_monitor_cron_svc.monitor_twice_daily",
            new_callable=AsyncMock,
            return_value=_make_monitor_result(requires_alert=True),
        ):
            result = asyncio.run(cron_svc.run_monitor_cron(dry_run=False))
        assert result["outbox_status"] is None
        assert result["slack_enabled"] is False

    def test_t05_scheduled_for_converted_to_slot(self, monkeypatch):
        """T05: scheduled_for=11:00Z → Slot=10:00Z 역산 후 monitor_twice_daily 에 전달."""
        monkeypatch.delenv("QA_MONITOR_SLACK_ENABLED", raising=False)
        mock_monitor = AsyncMock(return_value=_make_monitor_result(requires_alert=False))
        with patch("services.qa_monitor_cron_svc.monitor_twice_daily", mock_monitor):
            asyncio.run(cron_svc.run_monitor_cron(scheduled_for="2026-10-30T11:00:00Z"))

        mock_monitor.assert_called_once()
        assert mock_monitor.call_args.kwargs.get("scheduled_slot_utc") == "2026-10-30T10:00:00Z"

    def test_t06_duplicate_call_deduped(self, monkeypatch):
        """T06: 중복 dedupe_key → DEDUPED, send_monitor_notification 미호출."""
        monkeypatch.setenv("QA_MONITOR_SLACK_ENABLED", "true")
        sb = _make_supabase_mock()

        with (
            patch(
                "services.qa_monitor_cron_svc.monitor_twice_daily",
                new_callable=AsyncMock,
                return_value=_make_monitor_result(requires_alert=True),
            ),
            patch(
                "services.qa_monitor_cron_svc.accept_monitor_notification",
                return_value=(False, None),
            ),
            patch(
                "services.qa_monitor_cron_svc.send_monitor_notification",
                new_callable=AsyncMock,
            ) as mock_send,
        ):
            result = asyncio.run(cron_svc.run_monitor_cron(supabase=sb, dry_run=False))

        assert result["outbox_status"] == "DEDUPED"
        mock_send.assert_not_called()


# ── WP-B Slack Event Type (T07-T10) ──────────────────────────────────────────

class TestSlackEventType:
    def test_t07_event_type_channel_mapping(self):
        """T07: QA_WORKFLOW_MONITOR_ALERT → CHANNEL_QA."""
        assert dispatcher.EVENT_TYPE_CHANNEL.get("QA_WORKFLOW_MONITOR_ALERT") == dispatcher.CHANNEL_QA

    def test_t08_in_admin_button_events(self):
        """T08: QA_WORKFLOW_MONITOR_ALERT → QA_ADMIN_BUTTON_EVENTS 포함."""
        assert "QA_WORKFLOW_MONITOR_ALERT" in dispatcher.QA_ADMIN_BUTTON_EVENTS

    def test_t09_admin_path_set(self):
        """T09: QA_WORKFLOW_MONITOR_ALERT → EVENT_TYPE_ADMIN_PATH '/qa/dashboard'."""
        assert dispatcher.EVENT_TYPE_ADMIN_PATH.get("QA_WORKFLOW_MONITOR_ALERT") == "/qa/dashboard"

    def test_t10_resolve_channel(self):
        """T10: _resolve_channel → CHANNEL_QA."""
        assert dispatcher._resolve_channel("QA_WORKFLOW_MONITOR_ALERT", "WARNING") == dispatcher.CHANNEL_QA


# ── WP-C Outbox Service (T11-T18) ────────────────────────────────────────────

class TestOutboxService:
    def test_t11_accept_new_insertion(self):
        """T11: 신규 삽입 → (True, row_id)."""
        sb = _make_supabase_mock(insert_data=[{"id": "row-abc"}])
        inserted, row_id = outbox_svc.accept_monitor_notification(
            sb,
            dedupe_key="2026-10-30T10:00:00Z|WORKFLOW_NOT_OBSERVED",
            slot_utc="2026-10-30T10:00:00Z",
            status_code="WORKFLOW_NOT_OBSERVED",
            slack_payload={"event_type": "QA_WORKFLOW_MONITOR_ALERT"},
        )
        assert inserted is True
        assert row_id == "row-abc"

    def test_t12_accept_duplicate_returns_false(self):
        """T12: 중복 dedupe_key (upsert ignore_duplicates) → (False, None)."""
        sb = _make_supabase_mock(insert_data=[])
        inserted, row_id = outbox_svc.accept_monitor_notification(
            sb,
            dedupe_key="2026-10-30T10:00:00Z|WORKFLOW_NOT_OBSERVED",
            slot_utc="2026-10-30T10:00:00Z",
            status_code="WORKFLOW_NOT_OBSERVED",
            slack_payload={},
        )
        assert inserted is False
        assert row_id is None

    def test_t13_claim_pending_returns_token(self):
        """T13: PENDING 행 update 성공 → claim_token(str) 반환."""
        sb = _make_supabase_mock(update_data=[{"id": "row-001"}])
        token = outbox_svc._claim(sb, "row-001")
        assert token is not None and isinstance(token, str)

    def test_t14_claim_failure_returns_none(self):
        """T14: CAS 경쟁 실패 (update 0건) → None."""
        sb = _make_supabase_mock(update_data=[])
        assert outbox_svc._claim(sb, "row-001") is None

    def test_t15_send_notification_sent(self):
        """T15: send_slack=True → SENT."""
        sb = _make_supabase_mock()
        with (
            patch.object(outbox_svc, "_claim", return_value="tok-001"),
            patch.object(outbox_svc, "_start_sending", return_value=True),
            patch.object(outbox_svc, "_finish", return_value=True),
            patch(
                "services.qa_monitor_outbox_svc.send_slack",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            result = asyncio.run(outbox_svc.send_monitor_notification(
                sb, "row-001",
                {"event_type": "QA_WORKFLOW_MONITOR_ALERT", "severity": "WARNING",
                 "title": "test", "detail": ""},
            ))
        assert result == "SENT"

    def test_t16_send_notification_slack_false_unknown(self):
        """T16: send_slack=False → UNKNOWN."""
        sb = _make_supabase_mock()
        with (
            patch.object(outbox_svc, "_claim", return_value="tok-001"),
            patch.object(outbox_svc, "_start_sending", return_value=True),
            patch.object(outbox_svc, "_finish", return_value=True),
            patch(
                "services.qa_monitor_outbox_svc.send_slack",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            result = asyncio.run(outbox_svc.send_monitor_notification(
                sb, "row-001",
                {"event_type": "QA_WORKFLOW_MONITOR_ALERT", "severity": "WARNING",
                 "title": "test", "detail": ""},
            ))
        assert result == "UNKNOWN"

    def test_t17_send_notification_exception_unknown(self):
        """T17: send_slack 예외 → UNKNOWN."""
        sb = _make_supabase_mock()
        with (
            patch.object(outbox_svc, "_claim", return_value="tok-001"),
            patch.object(outbox_svc, "_start_sending", return_value=True),
            patch.object(outbox_svc, "_finish", return_value=True),
            patch(
                "services.qa_monitor_outbox_svc.send_slack",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Slack down"),
            ),
        ):
            result = asyncio.run(outbox_svc.send_monitor_notification(
                sb, "row-001",
                {"event_type": "QA_WORKFLOW_MONITOR_ALERT", "severity": "WARNING",
                 "title": "test", "detail": ""},
            ))
        assert result == "UNKNOWN"

    def test_t18_send_notification_claim_fail_skipped(self):
        """T18: Claim 실패 → SKIPPED."""
        sb = _make_supabase_mock()
        with patch.object(outbox_svc, "_claim", return_value=None):
            result = asyncio.run(outbox_svc.send_monitor_notification(
                sb, "row-001",
                {"event_type": "QA_WORKFLOW_MONITOR_ALERT", "severity": "WARNING",
                 "title": "test", "detail": ""},
            ))
        assert result == "SKIPPED"


# ── WP-D Fail-Closed Gate (T19-T21) ──────────────────────────────────────────

class TestFailClosedGate:
    def test_t19_all_conditions_met_queues(self, monkeypatch):
        """T19: env=true + dry_run=False → accept + send 호출."""
        monkeypatch.setenv("QA_MONITOR_SLACK_ENABLED", "true")
        sb = _make_supabase_mock()

        with (
            patch(
                "services.qa_monitor_cron_svc.monitor_twice_daily",
                new_callable=AsyncMock,
                return_value=_make_monitor_result(requires_alert=True),
            ),
            patch(
                "services.qa_monitor_cron_svc.accept_monitor_notification",
                return_value=(True, "row-t19"),
            ) as mock_accept,
            patch(
                "services.qa_monitor_cron_svc.send_monitor_notification",
                new_callable=AsyncMock,
                return_value="SENT",
            ) as mock_send,
        ):
            result = asyncio.run(cron_svc.run_monitor_cron(supabase=sb, dry_run=False))

        mock_accept.assert_called_once()
        mock_send.assert_called_once()
        assert result["outbox_status"] == "SENT"

    def test_t20_env_not_set_no_send(self, monkeypatch):
        """T20: env 미설정 + dry_run=False → accept 미호출."""
        monkeypatch.delenv("QA_MONITOR_SLACK_ENABLED", raising=False)
        with (
            patch(
                "services.qa_monitor_cron_svc.monitor_twice_daily",
                new_callable=AsyncMock,
                return_value=_make_monitor_result(requires_alert=True),
            ),
            patch(
                "services.qa_monitor_cron_svc.accept_monitor_notification"
            ) as mock_accept,
        ):
            result = asyncio.run(cron_svc.run_monitor_cron(dry_run=False))

        mock_accept.assert_not_called()
        assert result["outbox_status"] is None
        assert result["slack_enabled"] is False

    def test_t21_dry_run_true_no_send(self, monkeypatch):
        """T21: env=true + dry_run=True → accept 미호출."""
        monkeypatch.setenv("QA_MONITOR_SLACK_ENABLED", "true")
        with (
            patch(
                "services.qa_monitor_cron_svc.monitor_twice_daily",
                new_callable=AsyncMock,
                return_value=_make_monitor_result(requires_alert=True),
            ),
            patch(
                "services.qa_monitor_cron_svc.accept_monitor_notification"
            ) as mock_accept,
        ):
            result = asyncio.run(cron_svc.run_monitor_cron(dry_run=True))

        mock_accept.assert_not_called()
        assert result["outbox_status"] is None


# ── Regression (T22-T24) ─────────────────────────────────────────────────────

class TestRegression:
    def test_t22_existing_qa_events_unchanged(self):
        """T22: 기존 QA_RUN_ERROR 등 5종 채널 매핑 회귀 없음."""
        for et in ["QA_FAIL_DETECTED", "QA_BLOCKED_DETECTED", "QA_FLAKY_DETECTED",
                   "QA_RECOVERED", "QA_RUN_ERROR"]:
            assert dispatcher.EVENT_TYPE_CHANNEL.get(et) == dispatcher.CHANNEL_QA, (
                f"{et} 채널 매핑 회귀"
            )

    def test_t23_stale_scan_no_slack(self):
        """T23: run_stale_scan_cron — WP-E 계약 보존 (send_slack 미호출)."""
        mock_supabase = MagicMock()
        mock_scan_result = {"queued_stale": [], "running_stale": []}

        with (
            patch(
                "services.qa_monitor_cron_svc.get_supabase",
                return_value=mock_supabase,
            ),
            patch(
                "services.qa_monitor_cron_svc.scan_stale_runs",
                new_callable=AsyncMock,
                return_value=mock_scan_result,
            ),
            patch("services.slack_dispatcher.send_slack") as mock_slack,
        ):
            result = asyncio.run(cron_svc.run_stale_scan_cron())

        mock_slack.assert_not_called()
        assert "queued_stale" in result

    def test_t24_no_alert_no_outbox_regardless_of_gate(self, monkeypatch):
        """T24: requires_alert=False → accept 미호출 (env=true, dry_run=False 무관)."""
        monkeypatch.setenv("QA_MONITOR_SLACK_ENABLED", "true")
        sb = _make_supabase_mock()

        with (
            patch(
                "services.qa_monitor_cron_svc.monitor_twice_daily",
                new_callable=AsyncMock,
                return_value=_make_monitor_result(requires_alert=False),
            ),
            patch(
                "services.qa_monitor_cron_svc.accept_monitor_notification"
            ) as mock_accept,
        ):
            result = asyncio.run(cron_svc.run_monitor_cron(supabase=sb, dry_run=False))

        mock_accept.assert_not_called()
        assert result["outbox_status"] is None
