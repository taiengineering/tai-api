"""tests/test_bizinfo_handler.py — handlers._run_bizinfo_daily_sync 단위 검증.

WO-TAI-BIZINFO-DAILY-SYNC-SLACK-001-R2
Production DB·API·Slack 호출 = 0 (전부 모의 주입).

커버리지:
  HND-01  신규 이벤트 0건 → 핸들러 정상 반환 (AttributeError 없음)
  HND-02  Slack 이벤트 접수 성공 → 반환 dict에 slack_event_accepted 필드 포함
  HND-03  PROGRAM API 실패 → RuntimeError 발생 (스케줄러 FAILED 기록)
  HND-04  EVENT API 실패 → RuntimeError 발생 (스케줄러 FAILED 기록)
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

import services.bizinfo.daily_sync as daily_sync_mod
import services.scheduler.handlers as handlers_mod
from services.bizinfo.daily_sync import BizinfoDailySyncResult


_NOW = datetime(2026, 11, 5, 4, 0, 0, tzinfo=timezone.utc)


def _make_result(
    program_api_errors: list | None = None,
    event_api_errors: list | None = None,
    slack_event_accepted: bool = False,
    slack_event_id: str | None = None,
    slack_skipped_reason: str | None = "no_events",
) -> BizinfoDailySyncResult:
    r = BizinfoDailySyncResult(run_at=_NOW)
    r.program.api_errors = program_api_errors or []
    r.event.api_errors = event_api_errors or []
    r.slack_event_accepted = slack_event_accepted
    r.slack_event_id = slack_event_id
    r.slack_skipped_reason = slack_skipped_reason
    return r


def _invoke(monkeypatch, mock_result: BizinfoDailySyncResult) -> dict:
    """mock_result를 반환하도록 패치한 뒤 핸들러를 호출."""
    monkeypatch.setattr(handlers_mod, "_sb", lambda: MagicMock())
    monkeypatch.setattr(
        daily_sync_mod, "run_bizinfo_daily_sync",
        lambda *a, **kw: mock_result,
    )
    return handlers_mod._run_bizinfo_daily_sync({})


# ---------------------------------------------------------------------------
# HND-01: 신규 이벤트 0건 → 핸들러 정상 반환
# ---------------------------------------------------------------------------

def test_HND01_no_events_handler_returns_cleanly(monkeypatch):
    """신규 이벤트가 없을 때 핸들러가 AttributeError 없이 정상 반환한다."""
    result = _invoke(monkeypatch, _make_result(slack_skipped_reason="no_events"))

    assert isinstance(result, dict)
    assert result["slack_event_accepted"] is False
    assert result["slack_skipped_reason"] == "no_events"
    # 이전 필드명이 반환 dict에 포함되지 않아야 함
    assert "slack_sent" not in result


# ---------------------------------------------------------------------------
# HND-02: Slack 이벤트 접수 성공 → 올바른 필드명 반환
# ---------------------------------------------------------------------------

def test_HND02_slack_accepted_field_in_return_dict(monkeypatch):
    """Slack relay 접수 성공 시 반환 dict에 slack_event_accepted=True가 포함된다."""
    mock_result = _make_result(
        slack_event_accepted=True,
        slack_event_id="bizinfo_daily_sync_2026-11-05_abc12345",
        slack_skipped_reason=None,
    )
    result = _invoke(monkeypatch, mock_result)

    assert result["slack_event_accepted"] is True
    assert result["slack_event_id"] == "bizinfo_daily_sync_2026-11-05_abc12345"
    assert result.get("slack_skipped_reason") is None
    assert "slack_sent" not in result


# ---------------------------------------------------------------------------
# HND-03: PROGRAM API 실패 → RuntimeError 발생
# ---------------------------------------------------------------------------

def test_HND03_program_api_error_raises(monkeypatch):
    """PROGRAM API 오류가 있으면 RuntimeError를 발생시켜 스케줄러에 FAILED를 기록한다."""
    mock_result = _make_result(
        program_api_errors=["page=1 error_code=HTTP_500"],
    )

    with pytest.raises(RuntimeError, match="API 오류"):
        _invoke(monkeypatch, mock_result)


# ---------------------------------------------------------------------------
# HND-04: EVENT API 실패 → RuntimeError 발생
# ---------------------------------------------------------------------------

def test_HND04_event_api_error_raises(monkeypatch):
    """EVENT API 오류가 있으면 RuntimeError를 발생시켜 스케줄러에 FAILED를 기록한다."""
    mock_result = _make_result(
        event_api_errors=["page=2 error_code=TIMEOUT"],
    )

    with pytest.raises(RuntimeError, match="API 오류"):
        _invoke(monkeypatch, mock_result)
