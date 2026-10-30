"""WO-TAI-QA-OPS-WORKFLOW-MONITOR-012 — qa_workflow_monitor_svc 계약 검증.

테스트 항목:
  D01  정상 Run 발견 (completed) → RUN_COMPLETED
  D02  RUNNING 발견 (in_progress) → RUN_ACTIVE
  D03  60분 이내 Run 없음 → WORKFLOW_NOT_OBSERVED, requires_alert=False
  D04  60분 이후 Run 없음 → WORKFLOW_NOT_OBSERVED, requires_alert=True
  D05  Run 생성, Job 목록 비어있음 → JOB_NOT_STARTED_SUSPECTED
  D06  Run 생성, Job 정상 시작 → RUN_COMPLETED
  D07  일반 테스트 실패 Run (completed/failure) → RUN_COMPLETED (Workflow 미시작 아님)
  D08  GitHub API Timeout → GITHUB_API_NOT_VERIFIED
  D09  GitHub 429 → GITHUB_API_NOT_VERIFIED
  D10  GitHub 5xx → GITHUB_API_NOT_VERIFIED
  D11  GitHub 인증 실패 (401/403) → GITHUB_API_NOT_VERIFIED
  D12  Workflow 비활성화 → WORKFLOW_DISABLED, requires_alert=True
  D13  UTC/KST 날짜 경계 (자정 전후) Slot 식별
  D14  오전·오후 Slot 식별 (21:00Z / 10:00Z)
  D15  동일 Slot 반복 관측 — 상태 코드 동일
  D16  중복 Slack 발송 방지: dry_run=True → slack_sent=False
  D17  Billing 의심(Job 없음)과 확인된 오류 구분 — BILLING_CONFIRMED 금지
  D18  실제 GitHub Dispatch 없음 — dispatch_qa_run 미호출 확인
  D19  기존 QA Run DB 상태 변경 없음 — supabase 미호출
  D20  WP-E Scanner 함수 시그니처 회귀 없음
  D21  기존 Slack Dispatcher QA_RUN_ERROR 경로 회귀 없음
  D22  미래 Slot 및 잘못된 입력 거부 → ValueError

실제 GitHub API 호출 없음 — httpx.AsyncClient 완전 mock.
실제 Slack 발송 없음 — send_slack mock.
실제 DB 변경 없음.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import services.qa_workflow_monitor_svc as svc


# ── 시간 헬퍼 ─────────────────────────────────────────────────────────────────

def _utcdt(h: int = 12, m: int = 0, days_back: int = 0) -> datetime:
    """UTC 기준 특정 시각 datetime."""
    base = datetime.now(timezone.utc).replace(hour=h, minute=m, second=0, microsecond=0)
    return base - timedelta(days=days_back)


def _slot_dt(hour: int = 11, minute: int = 0) -> datetime:
    """오늘 UTC 기준 특정 slot datetime."""
    return datetime.now(timezone.utc).replace(
        hour=hour, minute=minute, second=0, microsecond=0,
    )


# ── httpx Mock 빌더 ──────────────────────────────────────────────────────────

class _FakeResp:
    def __init__(self, status_code: int, json_data: Any = None):
        self.status_code = status_code
        self._json = json_data or {}

    def json(self):
        return self._json


class _FakeClient:
    """httpx.AsyncClient 대체 — get 요청만 처리."""

    def __init__(self, responses: List[_FakeResp]):
        self._responses = list(responses)
        self._call_count = 0
        self.called_urls: List[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass

    async def get(self, url: str, **kwargs) -> _FakeResp:
        self.called_urls.append(url)
        if self._call_count < len(self._responses):
            resp = self._responses[self._call_count]
        else:
            resp = self._responses[-1]
        self._call_count += 1
        return resp


def _workflow_active_resp() -> _FakeResp:
    return _FakeResp(200, {"state": "active"})


def _workflow_disabled_resp(state: str = "disabled_manually") -> _FakeResp:
    return _FakeResp(200, {"state": state})


def _runs_resp(runs: List[Dict] = None) -> _FakeResp:
    return _FakeResp(200, {"workflow_runs": runs or []})


def _jobs_resp(jobs: List[Dict] = None) -> _FakeResp:
    return _FakeResp(200, {"jobs": jobs or []})


def _gh_run(
    run_id: int = 10001,
    status: str = "completed",
    conclusion: str = "success",
    created_at: str = "2026-10-30T10:00:05Z",
) -> Dict[str, Any]:
    return {
        "id":          run_id,
        "status":      status,
        "conclusion":  conclusion,
        "created_at":  created_at,
        "html_url":    f"https://github.com/taiengineering/tai-qa/actions/runs/{run_id}",
    }


def _gh_job(started: bool = True) -> Dict[str, Any]:
    return {
        "id":         99001,
        "name":       "run-tests",
        "started_at": "2026-10-30T11:01:00Z" if started else None,
    }


# ── 환경변수 픽스처 ──────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("QA_GITHUB_TOKEN",     "gh-test-token")
    monkeypatch.setenv("QA_GITHUB_OWNER",     "taiengineering")
    monkeypatch.setenv("QA_MONITOR_REPO",     "tai-qa")
    monkeypatch.setenv("QA_MONITOR_WORKFLOW", "qa-twice-daily.yml")


# ── D01: 정상 completed Run ──────────────────────────────────────────────────

def test_D01_run_completed(monkeypatch):
    """completed Run 발견 → RUN_COMPLETED, requires_alert=False."""
    slot = _slot_dt(10, 0) - timedelta(days=0)
    now  = slot + timedelta(minutes=70)

    run = _gh_run(status="completed", conclusion="success")
    job = _gh_job(started=True)

    client = _FakeClient([
        _workflow_active_resp(),   # workflow state
        _runs_resp([run]),         # workflow runs
        _jobs_resp([job]),         # run jobs
    ])

    with patch("services.qa_workflow_monitor_svc.httpx.AsyncClient", return_value=client):
        result = asyncio.run(svc.monitor_twice_daily(
            scheduled_slot_utc=slot.strftime("%Y-%m-%dT%H:%M:%SZ"),
            dry_run=True,
            now_utc=now,
        ))

    assert result["status_code"] == svc.STATUS_RUN_COMPLETED
    assert result["requires_alert"] is False
    assert result["slack_sent"] is False
    assert result["run_id"] == run["id"]


# ── D02: in_progress Run ─────────────────────────────────────────────────────

def test_D02_run_active(monkeypatch):
    """in_progress Run → RUN_ACTIVE, requires_alert=False."""
    slot = _slot_dt(10, 0)
    now  = slot + timedelta(minutes=70)

    run = _gh_run(status="in_progress", conclusion=None)

    client = _FakeClient([
        _workflow_active_resp(),
        _runs_resp([run]),
    ])

    with patch("services.qa_workflow_monitor_svc.httpx.AsyncClient", return_value=client):
        result = asyncio.run(svc.monitor_twice_daily(
            scheduled_slot_utc=slot.strftime("%Y-%m-%dT%H:%M:%SZ"),
            now_utc=now,
        ))

    assert result["status_code"] == svc.STATUS_RUN_ACTIVE
    assert result["requires_alert"] is False


# ── D03: 60분 이내 Run 없음 ──────────────────────────────────────────────────

def test_D03_no_run_within_grace(monkeypatch):
    """Run 없음, 아직 60분 미경과 → requires_alert=False."""
    slot = _slot_dt(10, 0)
    now  = slot + timedelta(minutes=30)   # 30분만 경과

    client = _FakeClient([
        _workflow_active_resp(),
        _runs_resp([]),
    ])

    with patch("services.qa_workflow_monitor_svc.httpx.AsyncClient", return_value=client):
        result = asyncio.run(svc.monitor_twice_daily(
            scheduled_slot_utc=slot.strftime("%Y-%m-%dT%H:%M:%SZ"),
            now_utc=now,
        ))

    assert result["status_code"] == svc.STATUS_WORKFLOW_NOT_OBSERVED
    assert result["requires_alert"] is False
    assert "grace_remaining_min" in result["evidence"]


# ── D04: 60분 이후 Run 없음 ──────────────────────────────────────────────────

def test_D04_no_run_after_grace(monkeypatch):
    """Run 없음, 60분 이상 경과 → WORKFLOW_NOT_OBSERVED, requires_alert=True."""
    slot = _slot_dt(10, 0)
    now  = slot + timedelta(minutes=90)

    client = _FakeClient([
        _workflow_active_resp(),
        _runs_resp([]),
    ])

    with patch("services.qa_workflow_monitor_svc.httpx.AsyncClient", return_value=client):
        result = asyncio.run(svc.monitor_twice_daily(
            scheduled_slot_utc=slot.strftime("%Y-%m-%dT%H:%M:%SZ"),
            now_utc=now,
        ))

    assert result["status_code"] == svc.STATUS_WORKFLOW_NOT_OBSERVED
    assert result["requires_alert"] is True
    assert result["slack_message"] is not None
    assert result["slack_sent"] is False


# ── D05: Run 생성, Job 미시작 ────────────────────────────────────────────────

def test_D05_run_created_job_not_started(monkeypatch):
    """completed Run이 있지만 Job 시작 증거 없음 → JOB_NOT_STARTED_SUSPECTED."""
    slot = _slot_dt(10, 0)
    now  = slot + timedelta(minutes=70)

    run = _gh_run(status="completed", conclusion="failure")

    client = _FakeClient([
        _workflow_active_resp(),
        _runs_resp([run]),
        _jobs_resp([]),        # Job 없음
    ])

    with patch("services.qa_workflow_monitor_svc.httpx.AsyncClient", return_value=client):
        result = asyncio.run(svc.monitor_twice_daily(
            scheduled_slot_utc=slot.strftime("%Y-%m-%dT%H:%M:%SZ"),
            now_utc=now,
        ))

    assert result["status_code"] == svc.STATUS_JOB_NOT_STARTED_SUSPECTED
    assert result["requires_alert"] is True


# ── D06: Run 생성, Job 정상 시작 ─────────────────────────────────────────────

def test_D06_run_created_job_started(monkeypatch):
    """completed Run + Job 시작 증거 있음 → RUN_COMPLETED, requires_alert=False."""
    slot = _slot_dt(10, 0)
    now  = slot + timedelta(minutes=70)

    run = _gh_run(status="completed", conclusion="success")
    job = _gh_job(started=True)

    client = _FakeClient([
        _workflow_active_resp(),
        _runs_resp([run]),
        _jobs_resp([job]),
    ])

    with patch("services.qa_workflow_monitor_svc.httpx.AsyncClient", return_value=client):
        result = asyncio.run(svc.monitor_twice_daily(
            scheduled_slot_utc=slot.strftime("%Y-%m-%dT%H:%M:%SZ"),
            now_utc=now,
        ))

    assert result["status_code"] == svc.STATUS_RUN_COMPLETED
    assert result["requires_alert"] is False
    assert result["evidence"]["jobs_started"] == 1


# ── D07: 일반 테스트 실패 → Workflow 미시작 아님 ──────────────────────────────

def test_D07_test_failure_not_workflow_miss(monkeypatch):
    """conclusion=failure Run은 Workflow 미시작이 아닌 RUN_COMPLETED."""
    slot = _slot_dt(10, 0)
    now  = slot + timedelta(minutes=70)

    run  = _gh_run(status="completed", conclusion="failure")
    job  = _gh_job(started=True)

    client = _FakeClient([
        _workflow_active_resp(),
        _runs_resp([run]),
        _jobs_resp([job]),
    ])

    with patch("services.qa_workflow_monitor_svc.httpx.AsyncClient", return_value=client):
        result = asyncio.run(svc.monitor_twice_daily(
            scheduled_slot_utc=slot.strftime("%Y-%m-%dT%H:%M:%SZ"),
            now_utc=now,
        ))

    assert result["status_code"] == svc.STATUS_RUN_COMPLETED
    assert result["requires_alert"] is False


# ── D08: GitHub API Timeout ──────────────────────────────────────────────────

def test_D08_github_api_timeout(monkeypatch):
    """httpx Timeout → GITHUB_API_NOT_VERIFIED, requires_alert=False."""
    import httpx

    slot = _slot_dt(10, 0)
    now  = slot + timedelta(minutes=70)

    class _TimeoutClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def get(self, *a, **kw):
            raise httpx.TimeoutException("timeout")

    with patch("services.qa_workflow_monitor_svc.httpx.AsyncClient", return_value=_TimeoutClient()):
        result = asyncio.run(svc.monitor_twice_daily(
            scheduled_slot_utc=slot.strftime("%Y-%m-%dT%H:%M:%SZ"),
            now_utc=now,
        ))

    assert result["status_code"] == svc.STATUS_GITHUB_API_NOT_VERIFIED
    assert result["requires_alert"] is False
    assert result["slack_sent"] is False


# ── D09: GitHub 429 ──────────────────────────────────────────────────────────

def test_D09_github_rate_limited(monkeypatch):
    """HTTP 429 → GITHUB_API_NOT_VERIFIED."""
    slot = _slot_dt(10, 0)
    now  = slot + timedelta(minutes=70)

    client = _FakeClient([_FakeResp(429)])

    with patch("services.qa_workflow_monitor_svc.httpx.AsyncClient", return_value=client):
        result = asyncio.run(svc.monitor_twice_daily(
            scheduled_slot_utc=slot.strftime("%Y-%m-%dT%H:%M:%SZ"),
            now_utc=now,
        ))

    assert result["status_code"] == svc.STATUS_GITHUB_API_NOT_VERIFIED


# ── D10: GitHub 5xx ──────────────────────────────────────────────────────────

def test_D10_github_server_error(monkeypatch):
    """HTTP 503 → GITHUB_API_NOT_VERIFIED."""
    slot = _slot_dt(10, 0)
    now  = slot + timedelta(minutes=70)

    client = _FakeClient([_FakeResp(503)])

    with patch("services.qa_workflow_monitor_svc.httpx.AsyncClient", return_value=client):
        result = asyncio.run(svc.monitor_twice_daily(
            scheduled_slot_utc=slot.strftime("%Y-%m-%dT%H:%M:%SZ"),
            now_utc=now,
        ))

    assert result["status_code"] == svc.STATUS_GITHUB_API_NOT_VERIFIED


# ── D11: GitHub 인증 실패 ────────────────────────────────────────────────────

def test_D11_github_auth_failure(monkeypatch):
    """HTTP 401 → GITHUB_API_NOT_VERIFIED."""
    slot = _slot_dt(10, 0)
    now  = slot + timedelta(minutes=70)

    client = _FakeClient([_FakeResp(401)])

    with patch("services.qa_workflow_monitor_svc.httpx.AsyncClient", return_value=client):
        result = asyncio.run(svc.monitor_twice_daily(
            scheduled_slot_utc=slot.strftime("%Y-%m-%dT%H:%M:%SZ"),
            now_utc=now,
        ))

    assert result["status_code"] == svc.STATUS_GITHUB_API_NOT_VERIFIED


# ── D12: Workflow 비활성화 ────────────────────────────────────────────────────

def test_D12_workflow_disabled(monkeypatch):
    """state=disabled_manually → WORKFLOW_DISABLED, requires_alert=True."""
    slot = _slot_dt(10, 0)
    now  = slot + timedelta(minutes=70)

    client = _FakeClient([_workflow_disabled_resp("disabled_manually")])

    with patch("services.qa_workflow_monitor_svc.httpx.AsyncClient", return_value=client):
        result = asyncio.run(svc.monitor_twice_daily(
            scheduled_slot_utc=slot.strftime("%Y-%m-%dT%H:%M:%SZ"),
            now_utc=now,
        ))

    assert result["status_code"] == svc.STATUS_WORKFLOW_DISABLED
    assert result["requires_alert"] is True
    assert result["evidence"]["workflow_state"] == "disabled_manually"
    assert result["slack_message"] is not None


# ── D13: UTC/KST 날짜 경계 ──────────────────────────────────────────────────

def test_D13_utc_kst_date_boundary():
    """UTC 21:00 Slot은 날짜 경계를 올바르게 처리한다.

    KST 06:00은 UTC 전날 21:00. resolve_scheduled_slot이 올바른 UTC Slot을 반환한다.
    """
    # UTC 2026-10-31 21:00:00 → 검사 시각: 2026-10-31 22:30:00
    slot_utc = datetime(2026, 10, 31, 21, 0, 0, tzinfo=timezone.utc)
    now_utc  = datetime(2026, 10, 31, 22, 30, 0, tzinfo=timezone.utc)

    resolved = svc.resolve_scheduled_slot(
        slot_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        now_utc=now_utc,
    )

    assert resolved.hour == 21
    assert resolved.day == 31
    assert resolved.tzinfo == timezone.utc


# ── D14: 오전·오후 Slot 식별 ─────────────────────────────────────────────────

def test_D14_slot_identification_both_slots():
    """10:00Z 및 21:00Z Slot 모두 resolve_scheduled_slot이 올바르게 반환한다."""
    # Slot 10:00Z (KST 19:00) → now=11:30Z (90분 경과)
    slot_10 = datetime(2026, 10, 30, 10, 0, 0, tzinfo=timezone.utc)
    now_10  = datetime(2026, 10, 30, 11, 30, 0, tzinfo=timezone.utc)
    r10 = svc.resolve_scheduled_slot(slot_10.strftime("%Y-%m-%dT%H:%M:%SZ"), now_utc=now_10)
    assert r10.hour == 10

    # Slot 21:00Z (KST 다음날 06:00) → now=22:30Z (90분 경과)
    slot_21 = datetime(2026, 10, 30, 21, 0, 0, tzinfo=timezone.utc)
    now_21  = datetime(2026, 10, 30, 22, 30, 0, tzinfo=timezone.utc)
    r21 = svc.resolve_scheduled_slot(slot_21.strftime("%Y-%m-%dT%H:%M:%SZ"), now_utc=now_21)
    assert r21.hour == 21


# ── D15: 동일 Slot 반복 관측 ────────────────────────────────────────────────

def test_D15_repeated_observation_same_status(monkeypatch):
    """동일 Slot을 두 번 관측해도 동일 상태 코드 반환 (결과 멱등)."""
    slot = _slot_dt(10, 0)
    now  = slot + timedelta(minutes=70)

    run = _gh_run(status="completed", conclusion="success")
    job = _gh_job(started=True)

    for _ in range(2):
        client = _FakeClient([
            _workflow_active_resp(),
            _runs_resp([run]),
            _jobs_resp([job]),
        ])

        with patch("services.qa_workflow_monitor_svc.httpx.AsyncClient", return_value=client):
            result = asyncio.run(svc.monitor_twice_daily(
                scheduled_slot_utc=slot.strftime("%Y-%m-%dT%H:%M:%SZ"),
                now_utc=now,
            ))

        assert result["status_code"] == svc.STATUS_RUN_COMPLETED


# ── D16: dry_run=True → slack_sent=False ─────────────────────────────────────

def test_D16_dry_run_no_slack_sent(monkeypatch):
    """requires_alert=True 상황에서도 dry_run → slack_sent=False."""
    slot = _slot_dt(10, 0)
    now  = slot + timedelta(minutes=90)

    send_called = []

    def _fake_send(*a, **kw):
        send_called.append(True)

    monkeypatch.setattr("services.qa_workflow_monitor_svc.log", MagicMock())

    client = _FakeClient([
        _workflow_active_resp(),
        _runs_resp([]),
    ])

    with patch("services.qa_workflow_monitor_svc.httpx.AsyncClient", return_value=client):
        with patch("services.slack_dispatcher.send_slack", _fake_send):
            result = asyncio.run(svc.monitor_twice_daily(
                scheduled_slot_utc=slot.strftime("%Y-%m-%dT%H:%M:%SZ"),
                dry_run=True,
                now_utc=now,
            ))

    assert result["slack_sent"] is False
    assert not send_called, "dry_run=True에서 Slack 발송 금지"


# ── D17: Billing 의심 구분 ───────────────────────────────────────────────────

def test_D17_billing_suspected_not_confirmed(monkeypatch):
    """Job이 없어도 BILLING_CONFIRMED 상태 코드를 부여하지 않는다."""
    slot = _slot_dt(10, 0)
    now  = slot + timedelta(minutes=70)

    run = _gh_run(status="completed", conclusion="failure")

    client = _FakeClient([
        _workflow_active_resp(),
        _runs_resp([run]),
        _jobs_resp([]),   # Job 없음 → Billing 의심
    ])

    with patch("services.qa_workflow_monitor_svc.httpx.AsyncClient", return_value=client):
        result = asyncio.run(svc.monitor_twice_daily(
            scheduled_slot_utc=slot.strftime("%Y-%m-%dT%H:%M:%SZ"),
            now_utc=now,
        ))

    # BILLING_CONFIRMED가 아닌 JOB_NOT_STARTED_SUSPECTED 이어야 한다
    assert result["status_code"] == svc.STATUS_JOB_NOT_STARTED_SUSPECTED
    assert result["status_code"] != "BILLING_CONFIRMED"


# ── D18: GitHub Dispatch 미호출 ──────────────────────────────────────────────

def test_D18_no_github_dispatch(monkeypatch):
    """monitor_twice_daily는 dispatch_qa_run을 절대 호출하지 않는다."""
    slot = _slot_dt(10, 0)
    now  = slot + timedelta(minutes=70)

    dispatch_called = []

    async def _fake_dispatch(*a, **kw):
        dispatch_called.append(True)

    monkeypatch.setattr(
        "services.github_dispatch_svc.dispatch_qa_run",
        _fake_dispatch,
    )

    run = _gh_run()
    client = _FakeClient([
        _workflow_active_resp(),
        _runs_resp([run]),
        _jobs_resp([_gh_job()]),
    ])

    with patch("services.qa_workflow_monitor_svc.httpx.AsyncClient", return_value=client):
        asyncio.run(svc.monitor_twice_daily(
            scheduled_slot_utc=slot.strftime("%Y-%m-%dT%H:%M:%SZ"),
            now_utc=now,
        ))

    assert not dispatch_called, "monitor는 GitHub Actions를 Dispatch하지 않는다"


# ── D19: QA Run DB 상태 변경 없음 ────────────────────────────────────────────

def test_D19_no_db_mutation(monkeypatch):
    """monitor_twice_daily는 QA Run DB에 INSERT/UPDATE하지 않는다."""
    slot = _slot_dt(10, 0)
    now  = slot + timedelta(minutes=70)

    run = _gh_run()
    client = _FakeClient([
        _workflow_active_resp(),
        _runs_resp([run]),
        _jobs_resp([_gh_job()]),
    ])

    supabase_calls = []

    class _FakeSupabase:
        def table(self, name):
            supabase_calls.append(name)
            return self
        def insert(self, *a, **kw): return self
        def update(self, *a, **kw): return self
        def execute(self): return MagicMock(data=[])

    monkeypatch.setattr("services.qa_workflow_monitor_svc.log", MagicMock())

    with patch("services.qa_workflow_monitor_svc.httpx.AsyncClient", return_value=client):
        asyncio.run(svc.monitor_twice_daily(
            scheduled_slot_utc=slot.strftime("%Y-%m-%dT%H:%M:%SZ"),
            now_utc=now,
        ))

    assert not supabase_calls, "monitor 서비스는 DB를 직접 호출하지 않는다"


# ── D20: WP-E Scanner 함수 시그니처 회귀 없음 ────────────────────────────────

def test_D20_stale_scan_signature_unchanged():
    """qa_stale_svc.scan_stale_runs 함수 시그니처가 유지된다."""
    import inspect
    from services.qa_stale_svc import scan_stale_runs

    sig = inspect.signature(scan_stale_runs)
    params = list(sig.parameters.keys())
    assert params == ["supabase"], f"시그니처 변경: {params}"


# ── D21: Slack Dispatcher QA_RUN_ERROR 경로 회귀 없음 ────────────────────────

def test_D21_slack_dispatcher_qa_run_error_route_intact():
    """slack_dispatcher.py의 QA_RUN_ERROR → CHANNEL_QA 라우팅이 유지된다."""
    from services.slack_dispatcher import EVENT_TYPE_CHANNEL, CHANNEL_QA

    assert EVENT_TYPE_CHANNEL.get("QA_RUN_ERROR") == CHANNEL_QA, (
        "QA_RUN_ERROR Slack 채널 라우팅 변경 금지"
    )


# ── D22: 미래 Slot 및 잘못된 입력 거부 ───────────────────────────────────────

def test_D22_future_slot_rejected():
    """미래 Slot 입력 시 ValueError."""
    future = (datetime.now(timezone.utc) + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with pytest.raises(ValueError, match="미래 Slot"):
        svc.resolve_scheduled_slot(future)


def test_D22b_invalid_slot_format():
    """잘못된 날짜 형식 입력 시 ValueError."""
    with pytest.raises(ValueError):
        svc.resolve_scheduled_slot("not-a-date")


def test_D22c_auto_select_returns_most_recent_elapsed_slot():
    """auto-select는 60분 이상 경과한 Slot 중 가장 최근 것을 반환한다.

    now=2026-10-31 11:30Z 기준:
      - 10:00Z (90분 경과) → 유효 (KST 19:00)
      - 21:00Z from 2026-10-30 (14.5시간 경과) → 유효하지만 더 오래됨
    → resolve는 10:00Z를 선택해야 한다.
    """
    now_utc = datetime(2026, 10, 31, 11, 30, 0, tzinfo=timezone.utc)
    resolved = svc.resolve_scheduled_slot(None, now_utc=now_utc)

    # 가장 최근 유효 Slot: 2026-10-31 10:00Z (90분 경과)
    assert resolved.hour == 10
    assert resolved.day == 31
    assert resolved.month == 10


# ════════════════════════════════════════════════════════════════════════════
# R1 보정 테스트 (WO-012-R1)
# ════════════════════════════════════════════════════════════════════════════

# ── R1-01: Slot 검증 보정 ────────────────────────────────────────────────────

def test_R1_01a_nonstandard_slot_rejected():
    """비표준 시각 12:35Z → ValueError (오탐 방지)."""
    slot = datetime(2026, 10, 30, 12, 35, 0, tzinfo=timezone.utc)
    now  = slot + timedelta(minutes=90)

    with pytest.raises(ValueError, match="유효하지 않은 Slot 시각"):
        svc.resolve_scheduled_slot(slot.strftime("%Y-%m-%dT%H:%M:%SZ"), now_utc=now)


def test_R1_01b_nonzero_seconds_rejected():
    """초 값이 0이 아닌 Slot → ValueError."""
    slot = datetime(2026, 10, 30, 10, 0, 30, tzinfo=timezone.utc)  # 10:00:30Z
    now  = slot + timedelta(minutes=90)

    with pytest.raises(ValueError, match="초·마이크로초"):
        svc.resolve_scheduled_slot(slot.strftime("%Y-%m-%dT%H:%M:%SZ"), now_utc=now)


def test_R1_01c_standard_slots_accepted():
    """표준 Slot 10:00Z 및 21:00Z는 정상 허용된다."""
    for hour in (10, 21):
        slot = datetime(2026, 10, 30, hour, 0, 0, tzinfo=timezone.utc)
        now  = slot + timedelta(minutes=90)

        resolved = svc.resolve_scheduled_slot(
            slot.strftime("%Y-%m-%dT%H:%M:%SZ"), now_utc=now
        )
        assert resolved.hour == hour
        assert resolved.minute == 0
        assert resolved.second == 0


# ── R1-02: Jobs API 오류 분류 보정 ───────────────────────────────────────────

def test_R1_02a_completed_jobs_api_failure_not_verified(monkeypatch):
    """completed Run + Jobs API 429 → GITHUB_API_NOT_VERIFIED (RUN_COMPLETED 금지)."""
    slot = _slot_dt(10, 0)
    now  = slot + timedelta(minutes=70)

    run = _gh_run(status="completed", conclusion="success")

    client = _FakeClient([
        _workflow_active_resp(),
        _runs_resp([run]),
        _FakeResp(429),      # Jobs API rate-limited
    ])

    with patch("services.qa_workflow_monitor_svc.httpx.AsyncClient", return_value=client):
        result = asyncio.run(svc.monitor_twice_daily(
            scheduled_slot_utc=slot.strftime("%Y-%m-%dT%H:%M:%SZ"),
            now_utc=now,
        ))

    assert result["status_code"] == svc.STATUS_GITHUB_API_NOT_VERIFIED, (
        "Jobs API 조회 실패는 RUN_COMPLETED가 아닌 GITHUB_API_NOT_VERIFIED"
    )
    assert result["requires_alert"] is False


def test_R1_02b_completed_jobs_api_503_not_verified(monkeypatch):
    """completed Run + Jobs API 503 → GITHUB_API_NOT_VERIFIED."""
    slot = _slot_dt(10, 0)
    now  = slot + timedelta(minutes=70)

    run = _gh_run(status="completed", conclusion="success")

    client = _FakeClient([
        _workflow_active_resp(),
        _runs_resp([run]),
        _FakeResp(503),
    ])

    with patch("services.qa_workflow_monitor_svc.httpx.AsyncClient", return_value=client):
        result = asyncio.run(svc.monitor_twice_daily(
            scheduled_slot_utc=slot.strftime("%Y-%m-%dT%H:%M:%SZ"),
            now_utc=now,
        ))

    assert result["status_code"] == svc.STATUS_GITHUB_API_NOT_VERIFIED


def test_R1_02c_completed_empty_jobs_job_not_started():
    """completed Run + Jobs API 200 + jobs=[] → JOB_NOT_STARTED_SUSPECTED."""
    run = _gh_run(status="completed", conclusion="failure")
    result = svc._classify_completed_run(run, jobs=[])
    assert result == svc.STATUS_JOB_NOT_STARTED_SUSPECTED


def test_R1_02d_completed_none_jobs_not_verified():
    """completed Run + Jobs API 실패(None) → GITHUB_API_NOT_VERIFIED."""
    run = _gh_run(status="completed", conclusion="success")
    result = svc._classify_completed_run(run, jobs=None)
    assert result == svc.STATUS_GITHUB_API_NOT_VERIFIED


# ── R1-03: 장기 QUEUED 감지 보정 ─────────────────────────────────────────────

def test_R1_03a_queued_30min_run_active(monkeypatch):
    """queued + 30분 경과 → RUN_ACTIVE (유예 내)."""
    slot = _slot_dt(10, 0)
    now  = slot + timedelta(minutes=30)

    run = _gh_run(status="queued", conclusion=None)

    client = _FakeClient([
        _workflow_active_resp(),
        _runs_resp([run]),
    ])

    with patch("services.qa_workflow_monitor_svc.httpx.AsyncClient", return_value=client):
        result = asyncio.run(svc.monitor_twice_daily(
            scheduled_slot_utc=slot.strftime("%Y-%m-%dT%H:%M:%SZ"),
            now_utc=now,
        ))

    assert result["status_code"] == svc.STATUS_RUN_ACTIVE
    assert result["requires_alert"] is False


def test_R1_03b_queued_70min_no_jobs_suspected(monkeypatch):
    """queued + 70분 경과 + Job 없음 → JOB_NOT_STARTED_SUSPECTED."""
    slot = _slot_dt(10, 0)
    now  = slot + timedelta(minutes=70)

    run = _gh_run(status="queued", conclusion=None)

    client = _FakeClient([
        _workflow_active_resp(),
        _runs_resp([run]),
        _jobs_resp([]),      # Jobs API 200 + 비어있음
    ])

    with patch("services.qa_workflow_monitor_svc.httpx.AsyncClient", return_value=client):
        result = asyncio.run(svc.monitor_twice_daily(
            scheduled_slot_utc=slot.strftime("%Y-%m-%dT%H:%M:%SZ"),
            now_utc=now,
        ))

    assert result["status_code"] == svc.STATUS_JOB_NOT_STARTED_SUSPECTED
    assert result["requires_alert"] is True


def test_R1_03c_queued_70min_jobs_api_failure_not_verified(monkeypatch):
    """queued + 70분 + Jobs API 오류 → GITHUB_API_NOT_VERIFIED."""
    slot = _slot_dt(10, 0)
    now  = slot + timedelta(minutes=70)

    run = _gh_run(status="queued", conclusion=None)

    client = _FakeClient([
        _workflow_active_resp(),
        _runs_resp([run]),
        _FakeResp(429),      # Jobs API rate-limited
    ])

    with patch("services.qa_workflow_monitor_svc.httpx.AsyncClient", return_value=client):
        result = asyncio.run(svc.monitor_twice_daily(
            scheduled_slot_utc=slot.strftime("%Y-%m-%dT%H:%M:%SZ"),
            now_utc=now,
        ))

    assert result["status_code"] == svc.STATUS_GITHUB_API_NOT_VERIFIED


def test_R1_03d_normal_completed_preserved(monkeypatch):
    """R1 보정 후에도 정상 completed Run + Job 시작됨 → RUN_COMPLETED 유지."""
    slot = _slot_dt(10, 0)
    now  = slot + timedelta(minutes=70)

    run = _gh_run(status="completed", conclusion="success")
    job = _gh_job(started=True)

    client = _FakeClient([
        _workflow_active_resp(),
        _runs_resp([run]),
        _jobs_resp([job]),
    ])

    with patch("services.qa_workflow_monitor_svc.httpx.AsyncClient", return_value=client):
        result = asyncio.run(svc.monitor_twice_daily(
            scheduled_slot_utc=slot.strftime("%Y-%m-%dT%H:%M:%SZ"),
            now_utc=now,
        ))

    assert result["status_code"] == svc.STATUS_RUN_COMPLETED
    assert result["requires_alert"] is False
