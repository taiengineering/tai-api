"""WO-TAI-QA-G5-SOURCE-IV-R1-001 — workflow_dispatch 이벤트 필터 공백 검증.

PLAN_ID: TAI-QA-PROACTIVE-DETECTION-PLAN-20261104-v1.0
GATE: G5_SOURCE_IV_R1

기존 자산 재사용:
  test_qa_workflow_monitor_svc.py D01~D22 (D04 포함) — 모든 미시작 감지 계약 커버
  — 기존 테스트가 커버하지 않는 공백만 추가

확인된 공백 (GAP-G5-001):
  서비스: qa_workflow_monitor_svc._list_workflow_runs()
    → GitHub Runs 조회 시 params["event"] = "schedule" 고정
  실제 tai-qa 정기검사: TAI Scheduler → workflow_dispatch 이벤트
    → GitHub server-side 필터링: event=schedule 쿼리에 workflow_dispatch Run 미포함
    → 모니터가 정상 실행을 WORKFLOW_NOT_OBSERVED 로 오판

신규 테스트 2건:
  D-WD-01  올바른 계약 정의: 모니터가 workflow_dispatch를 인식해야 함 (XFAIL — 현재 미충족)
  D-WD-02  workflow_dispatch Run 존재 + event=schedule 서버 필터 → WORKFLOW_NOT_OBSERVED 거짓 경보 재현

판정 구분:
  XFAIL = 올바른 계약이 현재 구현에서 충족되지 않음 (결함 존재 증거)
  PASS  = 결함 재현 성공 (오판 경로 확인)

운영 안전:
  PRODUCTION_API_HITS=0 / DB_CHANGE=NONE / SCHEDULE_CHANGE=NONE / DEPLOY=NONE
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

import services.qa_workflow_monitor_svc as svc


# ── 환경변수 픽스처 (전역 setenv 대신 테스트별 monkeypatch) ──────────────────────

@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("QA_GITHUB_TOKEN", "gh-test-token")


# ── 공통 헬퍼 ─────────────────────────────────────────────────────────────────────

class _FakeResp:
    def __init__(self, status_code: int, json_data: Any = None):
        self.status_code = status_code
        self._json = json_data or {}

    def json(self):
        return self._json


class _ParamCapturingClient:
    """httpx.AsyncClient 대체 — 순서대로 응답 반환 + 호출 params 기록."""

    def __init__(self, responses: list):
        self._responses = list(responses)
        self._call_count = 0
        self.calls: List[Dict[str, Any]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass

    async def get(self, url: str, **kwargs) -> Any:
        self.calls.append({"url": url, "params": kwargs.get("params", {})})
        resp = self._responses[min(self._call_count, len(self._responses) - 1)]
        self._call_count += 1
        return resp


class _EventFilteringClient:
    """httpx.AsyncClient 대체 — event 파라미터에 따른 GitHub server-side 필터링 모의.

    workflow_dispatch Run이 GitHub에 존재하지만,
    event=schedule 쿼리에는 반환하지 않는 GitHub 동작을 재현한다.
    """

    def __init__(self, dispatch_run: Dict[str, Any]):
        self._dispatch_run = dispatch_run  # GitHub에 실제 존재하는 workflow_dispatch Run
        self.calls: List[Dict[str, Any]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass

    async def get(self, url: str, **kwargs) -> _FakeResp:
        params = kwargs.get("params", {})
        self.calls.append({"url": url, "params": params})

        # Workflow 활성 상태 조회
        if "/actions/workflows/" in url and "/runs" not in url:
            return _FakeResp(200, {"state": "active"})

        # Runs 조회 — event 파라미터에 따른 GitHub server-side 필터링 재현
        if "/actions/workflows/" in url and "/runs" in url and "/jobs" not in url:
            event_filter = params.get("event")
            if event_filter == "schedule":
                # GitHub는 event=schedule 쿼리에 workflow_dispatch Run을 포함하지 않음
                return _FakeResp(200, {"workflow_runs": []})
            # event=workflow_dispatch 또는 필터 없음 → dispatch Run 반환
            return _FakeResp(200, {"workflow_runs": [self._dispatch_run]})

        return _FakeResp(200, {})


def _slot_dt(hour: int = 10, minute: int = 0) -> datetime:
    """오늘 UTC 기준 유효 slot datetime (10:00Z 또는 21:00Z만 허용)."""
    return datetime.now(timezone.utc).replace(
        hour=hour, minute=minute, second=0, microsecond=0,
    )


def _dispatch_run_obj(slot: datetime) -> Dict[str, Any]:
    """TAI Scheduler가 발생시킨 workflow_dispatch Run 모의 객체."""
    return {
        "id":          10001,
        "status":      "completed",
        "conclusion":  "success",
        "event":       "workflow_dispatch",
        "created_at":  slot.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "html_url":    "https://github.com/taiengineering/tai-qa/actions/runs/10001",
    }


# ── D-WD-01: 올바른 계약 정의 — 현재 미충족 (XFAIL) ────────────────────────────────

@pytest.mark.xfail(
    strict=True,
    reason=(
        "GAP-G5-001 KNOWN_DEFECT: Monitor가 event=schedule 필터를 사용해 "
        "workflow_dispatch 이벤트 Run을 인식하지 못한다. "
        "올바른 계약: event=workflow_dispatch 조회 추가 또는 event 필터 제거. "
        "이 테스트가 XPASS로 바뀌면 결함이 수정된 것이다."
    ),
)
def test_D_WD_01_correct_contract_uses_workflow_dispatch_filter():
    """올바른 계약: 모니터가 GitHub Runs 조회 시 workflow_dispatch를 인식하는 필터를 사용해야 한다.

    현재 구현은 event=schedule을 사용하므로 이 계약을 충족하지 못한다 → XFAIL.
    """
    slot = _slot_dt(10, 0)
    now  = slot + timedelta(minutes=90)

    gh_job = {"id": 99001, "name": "run-tests", "started_at": slot.strftime("%Y-%m-%dT%H:%M:%SZ")}

    client = _ParamCapturingClient([
        _FakeResp(200, {"state": "active"}),
        _FakeResp(200, {"workflow_runs": [_dispatch_run_obj(slot)]}),
        _FakeResp(200, {"jobs": [gh_job]}),
    ])

    with patch("services.qa_workflow_monitor_svc.httpx.AsyncClient", return_value=client):
        asyncio.run(svc.monitor_twice_daily(
            scheduled_slot_utc=slot.strftime("%Y-%m-%dT%H:%M:%SZ"),
            now_utc=now,
        ))

    runs_call = next(
        (c for c in client.calls if "/runs" in c["url"] and "/jobs" not in c["url"]),
        None,
    )
    assert runs_call is not None, "Workflow runs API 미호출"
    # 올바른 기대: workflow_dispatch 인식을 위한 필터 사용
    # 현재 구현은 "schedule"을 사용 → 이 단언이 실패 → XFAIL
    assert runs_call["params"].get("event") == "workflow_dispatch", (
        f"event 파라미터가 'workflow_dispatch' 아님: {runs_call['params'].get('event')!r} — "
        "event=schedule 고정 필터가 workflow_dispatch Run을 차단함 (GAP-G5-001)"
    )


# ── D-WD-02: workflow_dispatch Run → event=schedule 필터 → 거짓 경보 재현 ───────────

def test_D_WD_02_event_filter_excludes_dispatch_run_causes_false_alarm():
    """KNOWN_DEFECT_DEFERRED — GAP-G5-001 전체 경로 재현.

    재현 경로:
      1. TAI Scheduler가 workflow_dispatch로 tai-qa를 정상 실행
      2. GitHub에 workflow_dispatch Run (event=workflow_dispatch) 존재
      3. 모니터가 event=schedule 필터로 GitHub에 조회
      4. GitHub server-side 필터링: schedule 쿼리에 dispatch Run 미포함 → 빈 목록 반환
      5. 모니터: 60분 유예 경과 → WORKFLOW_NOT_OBSERVED + requires_alert=True

    결과: 정상 실행 중인 QA를 미실행으로 오판 → 거짓 경보 발생.

    수정 방향 (DEFERRED):
      _list_workflow_runs에서 event=workflow_dispatch 추가 조회 또는
      event 파라미터 제거 후 최근 Run을 시각 기준으로 직접 확인.
    """
    slot = _slot_dt(10, 0)
    now  = slot + timedelta(minutes=90)

    # GitHub에는 workflow_dispatch Run이 실제로 존재함
    # _EventFilteringClient가 event=schedule 쿼리에는 빈 목록을 반환해 GitHub 동작 재현
    client = _EventFilteringClient(dispatch_run=_dispatch_run_obj(slot))

    with patch("services.qa_workflow_monitor_svc.httpx.AsyncClient", return_value=client):
        result = asyncio.run(svc.monitor_twice_daily(
            scheduled_slot_utc=slot.strftime("%Y-%m-%dT%H:%M:%SZ"),
            now_utc=now,
        ))

    # 모니터가 event=schedule 필터를 사용했는지 검증
    runs_call = next(
        (c for c in client.calls if "/runs" in c["url"] and "/jobs" not in c["url"]),
        None,
    )
    assert runs_call is not None, "Runs API 미호출"
    assert runs_call["params"].get("event") == "schedule", (
        "서비스가 event=schedule 필터를 사용하지 않음 — 결함이 수정됐거나 경로가 변경됨"
    )

    # GitHub에 dispatch Run이 존재하는데 거짓 경보 발생 (결함 재현 성공)
    assert result["status_code"] == svc.STATUS_WORKFLOW_NOT_OBSERVED, (
        f"예상: WORKFLOW_NOT_OBSERVED, 실제: {result['status_code']!r}\n"
        "GAP-G5-001: event=schedule 필터가 workflow_dispatch Run을 차단해 거짓 경보 발생"
    )
    assert result["requires_alert"] is True, "거짓 경보 — requires_alert=True 기대"
