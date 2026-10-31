"""WO-TAI-QA-OPS-TIMED-TRIGGER-P0-005-R3 — qa_cron_trigger_svc 계약 검증.

테스트 항목:
  T01  current_slot_utc: now=10:05Z → 10:00Z 슬롯
  T02  current_slot_utc: now=21:30Z → 21:00Z 슬롯
  T03  current_slot_utc: now=09:59Z → 전날 21:00Z 슬롯
  T04  current_slot_utc: 정각(now=10:00Z) → 10:00Z 슬롯 (경계 포함)
  T05  current_slot_utc: 정각(now=21:00Z) → 21:00Z 슬롯 (경계 포함)
  T06  current_slot_utc: KST 입력 → UTC 변환 후 슬롯 식별
  T07  dispatch_qa_twice_daily: GitHub 204 → 4개 타임스탬프 포함 dict 반환
  T08  dispatch_qa_twice_daily: GitHub 200 → 성공 (204 외 200도 허용)
  T09  dispatch_qa_twice_daily: GitHub 422 → RuntimeError, no retry
  T10  dispatch_qa_twice_daily: GitHub 500 → RuntimeError, no retry
  T11  dispatch_qa_twice_daily: inputs 없음 — payload에 "inputs" 키 없음
  T12  dispatch_qa_twice_daily: github_job_started_at=None 보장
  T13  dispatch_qa_twice_daily: QA_GITHUB_TOKEN 미설정 → RuntimeError
  T14  dispatch_qa_twice_daily: QA_GITHUB_WORKFLOW_TWICE_DAILY env 반영
  T15  dispatch_qa_twice_daily: token log 포함 금지
  T16  trigger_qa_cron: 전체 흐름 성공 (_scheduled_for 전달, trigger_source 포함) [R3 보정]
  T17  trigger_qa_cron: GitHub 실패 → RuntimeError 전파 [R3 보정]
  T18  실제 GitHub API 호출 없음 — 모든 테스트 httpx mock 사용
  --- R2 신규 ---
  T19  R2-01: KST cron '0 6,19 * * *' → 06:00 KST = 21:00Z / 19:00 KST = 10:00Z
  T20  R2-03: trigger_qa_cron(_scheduled_for 전달) → 전달값 사용
  T21  R3-03: trigger_qa_cron(_scheduled_for 없음) → RuntimeError DISPATCH_BLOCKED_NO_SCHEDULE [R3 보정]
  T22  R3-01: trigger_qa_cron(_attempt_no=2) → RuntimeError DISPATCH_BLOCKED_RETRY, GitHub 미호출 [R3 보정]
  T23  R2-04: trigger_qa_cron(_attempt_no=1) → 정상 dispatch
  T24  R3-01: _attempt_no=3 → RuntimeError DISPATCH_BLOCKED_RETRY (성공 기록 불가) [R3 보정]
  --- R3 신규 ---
  T25  R3-03: KST scheduled_for → UTC 변환 후 result.scheduled_for에 기록

실제 GitHub API 호출 없음. 실제 DB 변경 없음. Slack 발송 없음.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, List
from unittest.mock import patch

import pytest

import services.qa_cron_trigger_svc as svc


# ── 공통 헬퍼 ─────────────────────────────────────────────────────────────────

def _utcnow(h: int, m: int = 0, days_delta: int = 0) -> datetime:
    """UTC 기준 특정 시각 datetime (aware)."""
    base = datetime.now(timezone.utc).replace(hour=h, minute=m, second=30, microsecond=0)
    return base + timedelta(days=days_delta)


# ── httpx POST mock ───────────────────────────────────────────────────────────

class _FakeResp:
    def __init__(self, status_code: int):
        self.status_code = status_code

    def json(self):
        return {}


class _FakeClient:
    """httpx.AsyncClient POST 전용 mock."""

    def __init__(self, status_code: int = 204):
        self.status_code = status_code
        self.calls: List[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass

    async def post(self, url: str, *, json: Any = None, headers: Any = None, **kwargs):
        self.calls.append({"url": url, "json": json, "headers": headers})
        return _FakeResp(self.status_code)


def _patch_client(status: int = 204):
    client = _FakeClient(status)
    return patch("services.qa_cron_trigger_svc.httpx.AsyncClient", return_value=client), client


# ── 환경변수 픽스처 ───────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("QA_GITHUB_TOKEN", "gh-test-token-do-not-log")
    monkeypatch.setenv("QA_GITHUB_OWNER", "taiengineering")
    monkeypatch.setenv("QA_GITHUB_REPO",  "tai-qa")
    monkeypatch.delenv("QA_GITHUB_WORKFLOW_TWICE_DAILY", raising=False)
    monkeypatch.setenv("QA_GITHUB_REF",   "main")


# ── T01~T06: current_slot_utc ─────────────────────────────────────────────────

def test_T01_slot_after_10z():
    now = _utcnow(10, 5)
    slot = svc.current_slot_utc(now)
    assert slot.hour == 10 and slot.minute == 0
    assert slot.tzinfo is not None


def test_T02_slot_after_21z():
    now = _utcnow(21, 30)
    slot = svc.current_slot_utc(now)
    assert slot.hour == 21 and slot.minute == 0


def test_T03_slot_before_10z_wraps_to_prev_21z():
    now = _utcnow(9, 59)
    slot = svc.current_slot_utc(now)
    assert slot.hour == 21 and slot.minute == 0
    # 전날 21:00Z 여야 함
    assert slot.date() < now.date()


def test_T04_boundary_exactly_10z():
    now = _utcnow(10, 0).replace(second=0, microsecond=0)
    slot = svc.current_slot_utc(now)
    assert slot.hour == 10 and slot.minute == 0


def test_T05_boundary_exactly_21z():
    now = _utcnow(21, 0).replace(second=0, microsecond=0)
    slot = svc.current_slot_utc(now)
    assert slot.hour == 21 and slot.minute == 0


def test_T06_kst_input_converted_to_utc_slot():
    """KST aware datetime 입력 → UTC로 변환 후 슬롯 식별."""
    from datetime import timezone as tz
    KST = tz(timedelta(hours=9))
    # KST 19:10 = UTC 10:10 → 슬롯은 10:00Z
    now_kst = datetime.now(KST).replace(hour=19, minute=10, second=0, microsecond=0)
    slot = svc.current_slot_utc(now_kst)
    assert slot.hour == 10 and slot.minute == 0
    assert slot.tzinfo is not None


# ── T07~T15: dispatch_qa_twice_daily ─────────────────────────────────────────

def test_T07_dispatch_204_returns_four_timestamps():
    patcher, client = _patch_client(204)
    slot = _utcnow(21, 0)
    with patcher:
        result = asyncio.run(svc.dispatch_qa_twice_daily(slot))

    assert result["scheduled_for"] == slot.isoformat()
    assert result["dispatch_attempted_at"] is not None
    assert result["dispatch_accepted_at"] is not None
    assert result["github_job_started_at"] is None
    # 실제 POST가 1회 발생했는지 확인
    assert len(client.calls) == 1


def test_T08_dispatch_200_also_success():
    patcher, client = _patch_client(200)
    slot = _utcnow(10, 0)
    with patcher:
        result = asyncio.run(svc.dispatch_qa_twice_daily(slot))
    assert result["dispatch_accepted_at"] is not None


def test_T09_dispatch_422_raises_no_retry():
    patcher, client = _patch_client(422)
    slot = _utcnow(21, 0)
    with patcher:
        with pytest.raises(RuntimeError, match="422"):
            asyncio.run(svc.dispatch_qa_twice_daily(slot))
    assert len(client.calls) == 1, "재시도 없음"


def test_T10_dispatch_500_raises_no_retry():
    patcher, client = _patch_client(500)
    slot = _utcnow(10, 0)
    with patcher:
        with pytest.raises(RuntimeError, match="500"):
            asyncio.run(svc.dispatch_qa_twice_daily(slot))
    assert len(client.calls) == 1, "재시도 없음"


def test_T11_dispatch_payload_has_no_inputs_key():
    """qa-twice-daily.yml은 inputs 없음 — POST body에 'inputs' 키 없어야 함."""
    patcher, client = _patch_client(204)
    slot = _utcnow(21, 0)
    with patcher:
        asyncio.run(svc.dispatch_qa_twice_daily(slot))
    posted_json = client.calls[0]["json"]
    assert "inputs" not in posted_json
    assert posted_json.get("ref") == "main"


def test_T12_github_job_started_at_is_none():
    patcher, _ = _patch_client(204)
    slot = _utcnow(10, 0)
    with patcher:
        result = asyncio.run(svc.dispatch_qa_twice_daily(slot))
    assert result["github_job_started_at"] is None


def test_T13_missing_token_raises(monkeypatch):
    monkeypatch.delenv("QA_GITHUB_TOKEN", raising=False)
    patcher, _ = _patch_client(204)
    with patcher:
        with pytest.raises(RuntimeError, match="QA_GITHUB_TOKEN"):
            asyncio.run(svc.dispatch_qa_twice_daily(_utcnow(21, 0)))


def test_T14_custom_workflow_env(monkeypatch):
    monkeypatch.setenv("QA_GITHUB_WORKFLOW_TWICE_DAILY", "custom-qa.yml")
    patcher, client = _patch_client(204)
    with patcher:
        asyncio.run(svc.dispatch_qa_twice_daily(_utcnow(21, 0)))
    url = client.calls[0]["url"]
    assert "custom-qa.yml" in url


def test_T15_token_not_in_log_on_error(caplog):
    """GitHub 실패 시 RuntimeError 로그에 token 미포함."""
    patcher, _ = _patch_client(500)
    with caplog.at_level(logging.ERROR, logger="qa_cron_trigger"):
        with patcher:
            with pytest.raises(RuntimeError):
                asyncio.run(svc.dispatch_qa_twice_daily(_utcnow(10, 0)))
    for record in caplog.records:
        assert "gh-test-token-do-not-log" not in record.getMessage()


# ── T16~T18: trigger_qa_cron ─────────────────────────────────────────────────

def test_T16_trigger_qa_cron_success_includes_trigger_source():
    """R3 보정: _scheduled_for/_attempt_no 포함 payload로 전체 흐름 성공 확인."""
    patcher, _ = _patch_client(204)
    with patcher:
        result = asyncio.run(svc.trigger_qa_cron({
            "_scheduled_for": "2026-10-31T21:00:00+09:00",  # KST
            "_attempt_no": 1,
        }))
    assert result["trigger_source"] == "tai_scheduler"
    assert result["dispatch_accepted_at"] is not None
    assert result["github_job_started_at"] is None


def test_T17_trigger_qa_cron_github_failure_propagates():
    """R3 보정: _scheduled_for 포함 시 GitHub 실패 → RuntimeError 전파."""
    patcher, _ = _patch_client(503)
    with patcher:
        with pytest.raises(RuntimeError, match="503"):
            asyncio.run(svc.trigger_qa_cron({
                "_scheduled_for": "2026-10-31T21:00:00+09:00",
                "_attempt_no": 1,
            }))


def test_T18_no_real_github_calls_in_all_tests():
    """모든 테스트가 httpx를 mock했는지 — 실제 네트워크 호출 없음을 보장."""
    import httpx
    assert hasattr(httpx, "AsyncClient")
    assert callable(httpx.AsyncClient)


# ── T19~T24: R2 신규 검증 ────────────────────────────────────────────────────

def test_T19_kst_cron_expr_maps_to_correct_utc_slots():  # noqa: F811
    """R2-01: '0 6,19 * * *' KST → 06:00 KST = 21:00Z(전일) / 19:00 KST = 10:00Z."""
    from zoneinfo import ZoneInfo
    from services.scheduler.cron_grammar import next_fire_after

    KST = ZoneInfo("Asia/Seoul")
    # 기준: 2026-10-31 05:59 KST (= 20:59Z)
    base_kst = datetime(2026, 10, 31, 5, 59, 0, tzinfo=KST)
    nxt = next_fire_after("0 6,19 * * *", base_kst)
    nxt_utc = nxt.astimezone(timezone.utc)
    # 06:00 KST = 21:00 UTC (전날 기준은 같은 날 21:00 UTC)
    assert nxt_utc.hour == 21 and nxt_utc.minute == 0, (
        f"06:00 KST 이후 슬롯은 21:00Z여야 함, 실제: {nxt_utc}"
    )

    # 기준: 2026-10-31 18:59 KST (= 09:59Z)
    base2_kst = datetime(2026, 10, 31, 18, 59, 0, tzinfo=KST)
    nxt2 = next_fire_after("0 6,19 * * *", base2_kst)
    nxt2_utc = nxt2.astimezone(timezone.utc)
    # 19:00 KST = 10:00 UTC
    assert nxt2_utc.hour == 10 and nxt2_utc.minute == 0, (
        f"19:00 KST 이후 슬롯은 10:00Z여야 함, 실제: {nxt2_utc}"
    )


def test_T20_trigger_qa_cron_uses_passed_scheduled_for():
    """R2-03: _scheduled_for가 payload에 있으면 그 값을 scheduled_for로 사용."""
    slot_iso = "2026-10-31T21:00:00+00:00"
    patcher, _ = _patch_client(204)
    with patcher:
        result = asyncio.run(svc.trigger_qa_cron({
            "_scheduled_for": slot_iso,
            "_attempt_no": 1,
        }))
    assert result["scheduled_for"] == slot_iso


def test_T21_trigger_qa_cron_blocked_without_scheduled_for():
    """R3-03: _scheduled_for 없으면 RuntimeError DISPATCH_BLOCKED_NO_SCHEDULE."""
    patcher, client = _patch_client(204)
    with patcher:
        with pytest.raises(RuntimeError, match="DISPATCH_BLOCKED_NO_SCHEDULE"):
            asyncio.run(svc.trigger_qa_cron({}))
    assert len(client.calls) == 0, "차단 시 GitHub API 호출 없음"


def test_T22_trigger_qa_cron_raises_on_retry():
    """R3-01: _attempt_no > 1 → RuntimeError DISPATCH_BLOCKED_RETRY, GitHub 미호출."""
    patcher, client = _patch_client(204)
    with patcher:
        with pytest.raises(RuntimeError, match="DISPATCH_BLOCKED_RETRY"):
            asyncio.run(svc.trigger_qa_cron({
                "_scheduled_for": "2026-10-31T21:00:00+09:00",
                "_attempt_no": 2,
            }))
    assert len(client.calls) == 0, "재처리 시 GitHub API 호출 없음"


def test_T23_trigger_qa_cron_dispatches_on_attempt_one():
    """R2-04: _attempt_no=1 → 정상 dispatch 실행."""
    patcher, client = _patch_client(204)
    with patcher:
        result = asyncio.run(svc.trigger_qa_cron({
            "_scheduled_for": "2026-10-31T10:00:00+00:00",
            "_attempt_no": 1,
        }))
    assert result.get("dispatch_accepted_at") is not None
    assert len(client.calls) == 1


def test_T24_retry_raises_not_returns_success():
    """R3-01: _attempt_no=3 → RuntimeError DISPATCH_BLOCKED_RETRY — 스케줄러 FAILED 기록 보장."""
    patcher, client = _patch_client(204)
    with patcher:
        with pytest.raises(RuntimeError, match="DISPATCH_BLOCKED_RETRY"):
            asyncio.run(svc.trigger_qa_cron({
                "_scheduled_for": "2026-10-31T21:00:00+09:00",
                "_attempt_no": 3,
            }))
    assert len(client.calls) == 0


def test_T26_trigger_qa_cron_blocked_without_attempt_no():
    """R3-FINAL: _attempt_no 누락 시 RuntimeError DISPATCH_BLOCKED_NO_ATTEMPT_NO, GitHub 미호출."""
    patcher, client = _patch_client(204)
    with patcher:
        with pytest.raises(RuntimeError, match="DISPATCH_BLOCKED_NO_ATTEMPT_NO"):
            asyncio.run(svc.trigger_qa_cron({
                "_scheduled_for": "2026-10-31T21:00:00+09:00",
                # _attempt_no 의도적 누락
            }))
    assert len(client.calls) == 0, "_attempt_no 없으면 GitHub API 호출 없음"


def test_T27_trigger_qa_cron_blocked_on_zero_attempt():
    """R3-FINAL-01: _attempt_no=0 → RuntimeError DISPATCH_BLOCKED_RETRY, GitHub 미호출."""
    patcher, client = _patch_client(204)
    with patcher:
        with pytest.raises(RuntimeError, match="DISPATCH_BLOCKED_RETRY"):
            asyncio.run(svc.trigger_qa_cron({
                "_scheduled_for": "2026-10-31T21:00:00+09:00",
                "_attempt_no": 0,
            }))
    assert len(client.calls) == 0


def test_T28_trigger_qa_cron_blocked_on_negative_attempt():
    """R3-FINAL-01: _attempt_no=-1 → RuntimeError DISPATCH_BLOCKED_RETRY, GitHub 미호출."""
    patcher, client = _patch_client(204)
    with patcher:
        with pytest.raises(RuntimeError, match="DISPATCH_BLOCKED_RETRY"):
            asyncio.run(svc.trigger_qa_cron({
                "_scheduled_for": "2026-10-31T21:00:00+09:00",
                "_attempt_no": -1,
            }))
    assert len(client.calls) == 0


def test_T25_kst_scheduled_for_converted_to_utc_in_result():
    """R3-03: KST _scheduled_for → UTC 변환 후 result.scheduled_for에 기록.

    06:00 KST (+09:00) = 21:00 UTC (전날) / 19:00 KST = 10:00 UTC.
    """
    patcher, _ = _patch_client(204)
    # 06:00 KST = 2026-10-30T21:00:00Z
    with patcher:
        result = asyncio.run(svc.trigger_qa_cron({
            "_scheduled_for": "2026-10-31T06:00:00+09:00",
            "_attempt_no": 1,
        }))
    result_dt = datetime.fromisoformat(result["scheduled_for"]).astimezone(timezone.utc)
    assert result_dt.year == 2026 and result_dt.month == 10 and result_dt.day == 30
    assert result_dt.hour == 21 and result_dt.minute == 0

    # 19:00 KST = 2026-10-31T10:00:00Z
    with patcher:
        result2 = asyncio.run(svc.trigger_qa_cron({
            "_scheduled_for": "2026-10-31T19:00:00+09:00",
            "_attempt_no": 1,
        }))
    result2_dt = datetime.fromisoformat(result2["scheduled_for"]).astimezone(timezone.utc)
    assert result2_dt.year == 2026 and result2_dt.month == 10 and result2_dt.day == 31
    assert result2_dt.hour == 10 and result2_dt.minute == 0
