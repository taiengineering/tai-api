"""WO-TAI-QA-G5-COVERAGE-GAP-001 — workflow_dispatch 이벤트 필터 공백 검증.

PLAN_ID: TAI-QA-PROACTIVE-DETECTION-PLAN-20261104-v1.0
GATE: G5_SOURCE_COVERAGE

기존 자산 재사용:
  test_qa_workflow_monitor_svc.py D01~D22 (D04 포함) — 모든 미시작 감지 계약 커버
  — 기존 테스트가 커버하지 않는 공백만 추가

확인된 공백 (GAP-G5-001):
  서비스: qa_workflow_monitor_svc._list_workflow_runs()
    → GitHub Runs 조회 시 params["event"] = "schedule" 고정
  실제 tai-qa 정기검사: TAI Scheduler → workflow_dispatch 이벤트
    → GitHub는 event=schedule 필터로 실제 실행된 workflow_dispatch Run을 반환하지 않음
    → 모니터가 정상 실행을 WORKFLOW_NOT_OBSERVED 로 오판할 수 있음

신규 테스트 2건:
  D-WD-01  event=schedule 파라미터가 GitHub API에 전달됨을 계약으로 고정
  D-WD-02  workflow_dispatch 실행 후 event=schedule 필터로 빈 목록 반환
           → WORKFLOW_NOT_OBSERVED 오판 재현 (KNOWN_DEFECT_DEFERRED)

운영 안전:
  PRODUCTION_API_HITS=0 / DB_CHANGE=NONE / SCHEDULE_CHANGE=NONE / DEPLOY=NONE
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import patch

import pytest

os.environ.setdefault("QA_GITHUB_TOKEN", "gh-test-token")

import services.qa_workflow_monitor_svc as svc


# ── 헬퍼: 파라미터를 캡처하는 FakeClient ────────────────────────────────────────

class _ParamCapturingClient:
    """httpx.AsyncClient 대체 — get() 호출 파라미터를 기록한다."""

    def __init__(self, responses: list):
        self._responses = list(responses)
        self._call_count = 0
        self.calls: List[Dict[str, Any]] = []  # {"url": ..., "params": ...}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass

    async def get(self, url: str, **kwargs) -> Any:
        self.calls.append({"url": url, "params": kwargs.get("params", {})})
        resp = self._responses[min(self._call_count, len(self._responses) - 1)]
        self._call_count += 1
        return resp


class _FakeResp:
    def __init__(self, status_code: int, json_data: Any = None):
        self.status_code = status_code
        self._json = json_data or {}

    def json(self):
        return self._json


def _workflow_active_resp() -> _FakeResp:
    return _FakeResp(200, {"state": "active"})


def _runs_resp(runs: list = None) -> _FakeResp:
    return _FakeResp(200, {"workflow_runs": runs or []})


def _jobs_resp(jobs: list = None) -> _FakeResp:
    return _FakeResp(200, {"jobs": jobs or []})


def _slot_dt(hour: int = 10, minute: int = 0) -> datetime:
    """오늘 UTC 기준 유효 slot datetime (10:00Z 또는 21:00Z만 허용)."""
    return datetime.now(timezone.utc).replace(
        hour=hour, minute=minute, second=0, microsecond=0,
    )


# ── D-WD-01: event=schedule 파라미터 계약 ───────────────────────────────────────

def test_D_WD_01_schedule_event_filter_in_github_query():
    """_list_workflow_runs가 GitHub Runs API 호출 시 event='schedule'을 전달한다.

    계약 고정: 현재 구현이 event=schedule 필터를 사용함을 증거로 등록한다.
    이 테스트가 깨지면 필터 계약이 변경된 것이므로 반드시 GAP-G5-001 재검토가 필요하다.
    """
    slot = _slot_dt(10, 0)
    now  = slot + timedelta(minutes=90)

    gh_job = {"id": 99001, "name": "run-tests", "started_at": "2026-11-06T10:01:00Z"}
    gh_run = {"id": 10001, "status": "completed", "conclusion": "success",
              "created_at": slot.strftime("%Y-%m-%dT%H:%M:%SZ"),
              "html_url": "https://github.com/taiengineering/tai-qa/actions/runs/10001"}

    client = _ParamCapturingClient([
        _workflow_active_resp(),
        _runs_resp([gh_run]),
        _jobs_resp([gh_job]),
    ])

    with patch("services.qa_workflow_monitor_svc.httpx.AsyncClient", return_value=client):
        asyncio.run(svc.monitor_twice_daily(
            scheduled_slot_utc=slot.strftime("%Y-%m-%dT%H:%M:%SZ"),
            now_utc=now,
        ))

    # 두 번째 호출이 Runs API — params 확인
    runs_call = next(
        (c for c in client.calls if "runs" in c["url"] and "jobs" not in c["url"]),
        None,
    )
    assert runs_call is not None, "Workflow runs API 미호출"
    assert runs_call["params"].get("event") == "schedule", (
        f"event 파라미터가 'schedule' 아님: {runs_call['params'].get('event')!r}\n"
        "GAP-G5-001: event=schedule 계약 변경 감지 — GAP 영향 재검토 필요"
    )


# ── D-WD-02: workflow_dispatch Run 존재 → WORKFLOW_NOT_OBSERVED 오판 ────────────

def test_D_WD_02_workflow_dispatch_run_causes_false_not_observed():
    """KNOWN_DEFECT_DEFERRED — GAP-G5-001 재현.

    상황:
      TAI Scheduler가 workflow_dispatch로 tai-qa를 정상 실행했다.
      GitHub에는 workflow_dispatch Run이 존재한다.
      그러나 모니터는 event=schedule 필터로 GitHub에 조회하므로
      GitHub는 workflow_dispatch Run을 필터링해 빈 목록을 반환한다.
      모니터는 60분 유예 후 WORKFLOW_NOT_OBSERVED + requires_alert=True 로 보고한다.

    결과: 정상 실행 중인 QA를 미시작으로 오판 → 거짓 경보 발생.

    수정 방법 (DEFERRED):
      _list_workflow_runs에서 event='workflow_dispatch' 추가 조회 또는
      event 파라미터 제거 후 최근 Run을 직접 확인하는 방식으로 보완 필요.
    """
    slot = _slot_dt(10, 0)
    now  = slot + timedelta(minutes=90)

    # GitHub는 event=schedule 필터로 빈 목록 반환
    # (실제로 workflow_dispatch Run은 존재하지만 필터에 걸려 반환되지 않음)
    client = _ParamCapturingClient([
        _workflow_active_resp(),
        _runs_resp([]),   # event=schedule 필터 결과: 빈 목록
    ])

    with patch("services.qa_workflow_monitor_svc.httpx.AsyncClient", return_value=client):
        result = asyncio.run(svc.monitor_twice_daily(
            scheduled_slot_utc=slot.strftime("%Y-%m-%dT%H:%M:%SZ"),
            now_utc=now,
        ))

    # KNOWN_DEFECT_DEFERRED: 정상 실행이 존재하는데 오판으로 경보가 발생함
    assert result["status_code"] == svc.STATUS_WORKFLOW_NOT_OBSERVED, (
        "KNOWN_DEFECT_DEFERRED — GAP-G5-001: "
        "workflow_dispatch Run이 event=schedule 필터로 누락돼 WORKFLOW_NOT_OBSERVED 오판 "
        f"(실제 status_code={result['status_code']!r})"
    )
    assert result["requires_alert"] is True, (
        "KNOWN_DEFECT_DEFERRED: 거짓 경보(requires_alert=True)가 발생해야 함"
    )
