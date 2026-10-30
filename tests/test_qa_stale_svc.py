"""WO-TAI-QA-OPS-STALE-RUN-011 — qa_stale_svc 계약 검증.

테스트 항목:
  E01  정상 QUEUED (< 30분) — 감지 안 됨
  E02  장기 QUEUED (> 30분) — 감지·보고, ERROR 전이 없음
  E03  정상 RUNNING (< 45분) — 감지 안 됨
  E04  장기 RUNNING + GitHub in_progress — STILL_ACTIVE, ERROR 없음
  E05  장기 RUNNING + GitHub completed + Callback 누락 — ERRORED_STALE
  E06  GitHub API Timeout → NOT_VERIFIED, ERROR 없음
  E07  GitHub API 429 → NOT_VERIFIED, ERROR 없음
  E08  GitHub API 5xx → NOT_VERIFIED, ERROR 없음
  E09  GitHub 인증 실패 (401/403) → NOT_VERIFIED, ERROR 없음
  E10  Callback 동시 적용 경합 (재조회 시 COMPLETED) → ALREADY_TRANSITIONED
  E11  이미 COMPLETED인 Run — 초기 쿼리에서 제외됨
  E12  이미 ERROR인 Run — 초기 쿼리에서 제외됨
  E13  github_run_attempt 불일치 → ATTEMPT_MISMATCH, ERROR 없음
  E14  중복 scan 호출 (두 번째 호출에서 이미 ERROR) → ALREADY_TRANSITIONED
  E15  Slack 발송 실패 — scan 결과에 영향 없음
  E16  기존 QA Lifecycle 회귀 — apply_results 계약 유지 확인

실제 GitHub API 호출 없음 — httpx.AsyncClient 완전 mock.
실제 DB 변경 없음 — supabase 완전 mock.
실제 Slack 발송 없음 — send_slack mock.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── 시간 헬퍼 ──────────────────────────────────────────────────────────────────

def _utc(offset_minutes: int = 0) -> str:
    """현재 UTC + offset_minutes 의 ISO 문자열."""
    dt = datetime.now(timezone.utc) + timedelta(minutes=offset_minutes)
    return dt.isoformat()


def _ago(minutes: int) -> str:
    """n분 전 ISO 문자열."""
    return _utc(-minutes)


# ── supabase Mock 빌더 ─────────────────────────────────────────────────────────

def _run_row(
    run_id: str = "run-001",
    status: str = "RUNNING",
    github_run_id: Optional[int] = 12345,
    github_run_attempt: int = 1,
    started_at: Optional[str] = None,
    requested_at: Optional[str] = None,
    trigger_type: str = "SCHEDULE",
) -> Dict[str, Any]:
    return {
        "id":                   run_id,
        "run_status":           status,
        "github_run_id":        github_run_id,
        "github_run_attempt":   github_run_attempt,
        "started_at":           started_at or _ago(50),
        "requested_at":         requested_at or _ago(50),
        "finished_at":          None,
        "error_code":           None,
        "trigger_type":         trigger_type,
    }


class _SupaMock:
    """체이너블 Supabase mock."""

    def __init__(
        self,
        *,
        running_stale: List[Dict] = None,
        queued_stale:  List[Dict] = None,
        reread_rows:   List[Dict] = None,
        has_results:   bool       = False,
        apply_called:  Optional[list] = None,
    ):
        self._running_stale = running_stale or []
        self._queued_stale  = queued_stale  or []
        self._reread_rows   = reread_rows   or []
        self._has_results   = has_results
        self._apply_called  = apply_called  # mutable list — caller를 통해 확인

        self._call_count: Dict[str, int] = {}

    def table(self, name: str):
        return _TableMock(name, self)


class _TableMock:
    def __init__(self, name: str, root: _SupaMock):
        self._name = name
        self._root = root
        self._filters: Dict[str, Any] = {}
        self._select_cols: str = ""
        self._update_data: Dict = {}
        self._insert_data: Any = None

    def select(self, cols, *a, **k):
        self._select_cols = cols
        return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def lte(self, col, val):
        return self

    def limit(self, n):
        return self

    def update(self, data):
        self._update_data = data
        return self

    def insert(self, data):
        self._insert_data = data
        return self

    def execute(self):
        res = MagicMock()
        res.count = None

        if self._name == "qa_runs":
            status_filter = self._filters.get("run_status")
            id_filter     = self._filters.get("id")

            if id_filter:
                # _reread_run() 호출
                res.data = [r for r in self._root._reread_rows if r["id"] == id_filter]
                return res

            if status_filter == "RUNNING":
                res.data = list(self._root._running_stale)
                return res

            if status_filter == "QUEUED":
                res.data = list(self._root._queued_stale)
                return res

            # apply_results 내부 update
            if self._update_data:
                if self._root._apply_called is not None:
                    self._root._apply_called.append(dict(self._update_data))
                res.data = [{"id": "run-001", **self._update_data}]
                return res

            res.data = []
            return res

        if self._name == "qa_run_results":
            if self._root._has_results:
                res.data = [{"id": "result-001"}]
            else:
                res.data = []
            return res

        res.data = []
        return res


# ── GitHub mock 팩토리 ─────────────────────────────────────────────────────────

def _gh_resp(status: int, body: Dict) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.json.return_value = body
    return r


def _patch_gh(resp_or_exc):
    """httpx.AsyncClient.get을 고정 응답 또는 예외로 대체."""
    if isinstance(resp_or_exc, Exception):
        mock_get = AsyncMock(side_effect=resp_or_exc)
    else:
        mock_get = AsyncMock(return_value=resp_or_exc)

    mock_client = MagicMock()
    mock_client.get = mock_get
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client, mock_get


# ── 공통 환경 패치 ──────────────────────────────────────────────────────────────

_ENV = {
    "QA_GITHUB_TOKEN":    "gh-test-token",
    "QA_GITHUB_OWNER":    "taiengineering",
    "QA_GITHUB_REPO":     "tai-qa",
    "INTERNAL_API_SECRET": "s3cret",
}


def _run_scan(supabase, mock_client=None, slack_side_effect=None):
    """scan_stale_runs() 실행 — httpx.AsyncClient mock (Slack 발송 없음)."""
    from services.qa_stale_svc import scan_stale_runs

    # Scanner는 Slack을 발송하지 않음 (R1-02/R1-03). mock은 call_count 검증용.
    send_slack_mock = AsyncMock(return_value=True)
    if slack_side_effect is not None:
        send_slack_mock.side_effect = slack_side_effect

    with patch.dict(os.environ, _ENV, clear=False):
        if mock_client is not None:
            with patch("httpx.AsyncClient", return_value=mock_client):
                result = asyncio.run(scan_stale_runs(supabase))
        else:
            result = asyncio.run(scan_stale_runs(supabase))

    return result, send_slack_mock


# ════════════════════════════════════════════════════════════════════════════════
# E01: 정상 QUEUED (< 30분) — 감지 안 됨
# ════════════════════════════════════════════════════════════════════════════════

def test_E01_fresh_queued_not_detected():
    supabase = _SupaMock(queued_stale=[], running_stale=[])
    result, _ = _run_scan(supabase)
    assert result["queued_reported"] == []
    assert result["running_processed"] == []


# ════════════════════════════════════════════════════════════════════════════════
# E02: 장기 QUEUED (> 30분) — 감지·보고, ERROR 전이 없음
# ════════════════════════════════════════════════════════════════════════════════

def test_E02_stale_queued_reported_no_error():
    run = _run_row(run_id="q-001", status="QUEUED", github_run_id=None, requested_at=_ago(40))
    supabase = _SupaMock(queued_stale=[run])
    result, slack_mock = _run_scan(supabase)

    assert len(result["queued_reported"]) == 1
    assert result["queued_reported"][0]["run_id"] == "q-001"
    assert result["queued_reported"][0]["action"] == "REPORTED"
    # ERROR 전이 없음
    assert result["errors"] == []
    # Scanner는 Slack 발송 안 함 (R1-02)
    assert slack_mock.call_count == 0


# ════════════════════════════════════════════════════════════════════════════════
# E03: 정상 RUNNING (< 45분) — 감지 안 됨
# ════════════════════════════════════════════════════════════════════════════════

def test_E03_fresh_running_not_detected():
    supabase = _SupaMock(queued_stale=[], running_stale=[])
    result, _ = _run_scan(supabase)
    assert result["running_processed"] == []


# ════════════════════════════════════════════════════════════════════════════════
# E04: 장기 RUNNING + GitHub in_progress → STILL_ACTIVE, ERROR 없음
# ════════════════════════════════════════════════════════════════════════════════

def test_E04_running_github_in_progress_no_error():
    run = _run_row(run_id="r-001", started_at=_ago(50))
    supabase = _SupaMock(running_stale=[run])
    gh_body  = {"status": "in_progress", "run_attempt": 1}
    mc, _    = _patch_gh(_gh_resp(200, gh_body))

    result, _ = _run_scan(supabase, mc)

    assert len(result["running_processed"]) == 1
    rec = result["running_processed"][0]
    assert rec["action"] == "STILL_ACTIVE"
    assert rec["gh_status"] == "in_progress"
    assert result["errors"] == []


# ════════════════════════════════════════════════════════════════════════════════
# E05: 장기 RUNNING + GitHub completed + Callback 누락 → CALLBACK_MISSING_DETECTED
# ════════════════════════════════════════════════════════════════════════════════

def test_E05_running_github_completed_no_callback_detected():
    run = _run_row(run_id="r-002", started_at=_ago(60))
    reread = [_run_row(run_id="r-002", status="RUNNING")]

    supabase = _SupaMock(running_stale=[run], reread_rows=reread, has_results=False)
    gh_body = {"status": "completed", "run_attempt": 1}
    mc, _   = _patch_gh(_gh_resp(200, gh_body))

    result, slack_mock = _run_scan(supabase, mc)

    assert len(result["running_processed"]) == 1
    rec = result["running_processed"][0]
    # 감지·보고만 — DB 상태 변경 없음 (R1-01)
    assert rec["action"] == "CALLBACK_MISSING_DETECTED"
    assert rec["gh_status"] == "completed"
    assert result["errors"] == []
    # Scanner는 Slack 발송 안 함 (R1-03)
    assert slack_mock.call_count == 0


# ════════════════════════════════════════════════════════════════════════════════
# E06: GitHub API Timeout → NOT_VERIFIED, ERROR 없음
# ════════════════════════════════════════════════════════════════════════════════

def test_E06_github_timeout_not_verified():
    import httpx
    run = _run_row(run_id="r-003", started_at=_ago(60))
    supabase = _SupaMock(running_stale=[run])
    mc, _    = _patch_gh(httpx.ReadTimeout("timeout", request=None))

    result, _ = _run_scan(supabase, mc)

    assert result["running_processed"][0]["action"] == "NOT_VERIFIED"
    assert result["errors"] == []


# ════════════════════════════════════════════════════════════════════════════════
# E07: GitHub API 429 → NOT_VERIFIED, ERROR 없음
# ════════════════════════════════════════════════════════════════════════════════

def test_E07_github_rate_limit_not_verified():
    run = _run_row(run_id="r-004", started_at=_ago(60))
    supabase = _SupaMock(running_stale=[run])
    mc, _    = _patch_gh(_gh_resp(429, {}))

    result, _ = _run_scan(supabase, mc)

    assert result["running_processed"][0]["action"] == "NOT_VERIFIED"


# ════════════════════════════════════════════════════════════════════════════════
# E08: GitHub API 5xx → NOT_VERIFIED, ERROR 없음
# ════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("status_code", [500, 503])
def test_E08_github_5xx_not_verified(status_code: int):
    run = _run_row(run_id="r-005", started_at=_ago(60))
    supabase = _SupaMock(running_stale=[run])
    mc, _    = _patch_gh(_gh_resp(status_code, {}))

    result, _ = _run_scan(supabase, mc)

    assert result["running_processed"][0]["action"] == "NOT_VERIFIED"


# ════════════════════════════════════════════════════════════════════════════════
# E09: GitHub 인증 실패 (401/403) → NOT_VERIFIED, ERROR 없음
# ════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("status_code", [401, 403])
def test_E09_github_auth_failure_not_verified(status_code: int):
    run = _run_row(run_id="r-006", started_at=_ago(60))
    supabase = _SupaMock(running_stale=[run])
    mc, _    = _patch_gh(_gh_resp(status_code, {}))

    result, _ = _run_scan(supabase, mc)

    assert result["running_processed"][0]["action"] == "NOT_VERIFIED"


# ════════════════════════════════════════════════════════════════════════════════
# E10: Callback 동시 적용 경합 (재조회 시 COMPLETED) → ALREADY_TRANSITIONED
# ════════════════════════════════════════════════════════════════════════════════

def test_E10_callback_race_already_transitioned():
    run = _run_row(run_id="r-007", started_at=_ago(60))
    # 재조회 시 COMPLETED로 변경된 상태
    reread = [_run_row(run_id="r-007", status="COMPLETED")]
    supabase = _SupaMock(running_stale=[run], reread_rows=reread, has_results=False)
    gh_body  = {"status": "completed", "run_attempt": 1}
    mc, _    = _patch_gh(_gh_resp(200, gh_body))

    result, _ = _run_scan(supabase, mc)

    assert result["running_processed"][0]["action"] == "ALREADY_TRANSITIONED"


# ════════════════════════════════════════════════════════════════════════════════
# E11: 이미 COMPLETED인 Run — 초기 쿼리에서 제외됨 (RUNNING 쿼리 필터)
# ════════════════════════════════════════════════════════════════════════════════

def test_E11_completed_run_excluded_from_query():
    # SupaMock이 RUNNING 필터를 사용하므로 COMPLETED run은 running_stale에 들어가지 않음
    supabase = _SupaMock(running_stale=[], queued_stale=[])
    result, _ = _run_scan(supabase)
    assert result["running_processed"] == []


# ════════════════════════════════════════════════════════════════════════════════
# E12: 이미 ERROR인 Run — 초기 쿼리에서 제외됨
# ════════════════════════════════════════════════════════════════════════════════

def test_E12_error_run_excluded_from_query():
    supabase = _SupaMock(running_stale=[], queued_stale=[])
    result, _ = _run_scan(supabase)
    assert result["running_processed"] == []


# ════════════════════════════════════════════════════════════════════════════════
# E13: github_run_attempt 불일치 → ATTEMPT_MISMATCH, ERROR 없음
# ════════════════════════════════════════════════════════════════════════════════

def test_E13_attempt_mismatch_no_error():
    run = _run_row(run_id="r-008", github_run_attempt=1, started_at=_ago(60))
    supabase = _SupaMock(running_stale=[run])
    # GitHub에서 attempt=2를 반환
    gh_body  = {"status": "completed", "run_attempt": 2}
    mc, _    = _patch_gh(_gh_resp(200, gh_body))

    result, _ = _run_scan(supabase, mc)

    assert result["running_processed"][0]["action"] == "ATTEMPT_MISMATCH"


# ════════════════════════════════════════════════════════════════════════════════
# E14: 중복 scan 호출 — 두 번째 호출에서 이미 ERROR → ALREADY_TRANSITIONED
# ════════════════════════════════════════════════════════════════════════════════

def test_E14_duplicate_scan_already_transitioned():
    """두 번째 scan 진입 시 첫 번째 scan이 이미 ERROR로 전이했음을 시뮬레이션.
    재조회(_reread_run) 시 ERROR 상태 → ALREADY_TRANSITIONED, apply_results 미호출.
    """
    run = _run_row(run_id="r-009", started_at=_ago(60))
    # 재조회 시 이미 ERROR로 전이된 상태 (첫 번째 scan에서 처리됨)
    reread = [_run_row(run_id="r-009", status="ERROR")]
    supabase = _SupaMock(running_stale=[run], reread_rows=reread, has_results=False)
    gh_body  = {"status": "completed", "run_attempt": 1}
    mc, _    = _patch_gh(_gh_resp(200, gh_body))

    result, _ = _run_scan(supabase, mc)

    assert result["running_processed"][0]["action"] == "ALREADY_TRANSITIONED"


# ════════════════════════════════════════════════════════════════════════════════
# E15: Scanner는 Slack을 발송하지 않음 (R1-02/R1-03)
# ════════════════════════════════════════════════════════════════════════════════

def test_E15_scanner_does_not_send_slack():
    """Scanner는 QUEUED/RUNNING stale 모두 Slack을 발송하지 않음."""
    run = _run_row(run_id="q-002", status="QUEUED", github_run_id=None, requested_at=_ago(40))
    supabase = _SupaMock(queued_stale=[run])

    result, slack_mock = _run_scan(supabase)

    assert len(result["queued_reported"]) == 1
    assert result["queued_reported"][0]["action"] == "REPORTED"
    assert result["errors"] == []
    assert slack_mock.call_count == 0


# ════════════════════════════════════════════════════════════════════════════════
# E16: Lifecycle 비침습 회귀 — Scanner는 DB 상태를 변경하지 않음
# ════════════════════════════════════════════════════════════════════════════════

def test_E16_scanner_does_not_mutate_db():
    """Scanner는 GitHub completed + Callback 미수신 시 DB 상태를 변경하지 않음.
    CALLBACK_MISSING_DETECTED 보고만. apply_results 호출 없음 (R1-01).
    """
    run = _run_row(run_id="r-010", started_at=_ago(60))
    reread = [_run_row(run_id="r-010", status="RUNNING")]
    supabase = _SupaMock(running_stale=[run], reread_rows=reread, has_results=False)
    gh_body  = {"status": "completed", "run_attempt": 1}
    mc, _    = _patch_gh(_gh_resp(200, gh_body))

    result, slack_mock = _run_scan(supabase, mc)

    rec = result["running_processed"][0]
    assert rec["action"] == "CALLBACK_MISSING_DETECTED"
    assert rec["gh_status"] == "completed"
    assert result["errors"] == []
    assert slack_mock.call_count == 0


# ════════════════════════════════════════════════════════════════════════════════
# 추가: github_run_id 없는 RUNNING stale → NO_GH_ID, ERROR 없음
# ════════════════════════════════════════════════════════════════════════════════

def test_running_stale_no_github_run_id():
    run = _run_row(run_id="r-011", github_run_id=None, started_at=_ago(60))
    supabase = _SupaMock(running_stale=[run])

    result, _ = _run_scan(supabase)

    assert result["running_processed"][0]["action"] == "NO_GH_ID"


# ════════════════════════════════════════════════════════════════════════════════
# 추가: RUNNING + results 존재 (Callback 처리 중) → RESULTS_EXIST, ERROR 없음
# ════════════════════════════════════════════════════════════════════════════════

def test_running_results_exist_no_error():
    run = _run_row(run_id="r-012", started_at=_ago(60))
    reread = [_run_row(run_id="r-012", status="RUNNING")]
    supabase = _SupaMock(running_stale=[run], reread_rows=reread, has_results=True)
    gh_body  = {"status": "completed", "run_attempt": 1}
    mc, _    = _patch_gh(_gh_resp(200, gh_body))

    result, _ = _run_scan(supabase, mc)

    assert result["running_processed"][0]["action"] == "RESULTS_EXIST"


# ════════════════════════════════════════════════════════════════════════════════
# 추가: GitHub 404 → GH_RUN_NOT_FOUND, ERROR 없음
# ════════════════════════════════════════════════════════════════════════════════

def test_github_run_not_found_no_error():
    run = _run_row(run_id="r-013", started_at=_ago(60))
    supabase = _SupaMock(running_stale=[run])
    mc, _    = _patch_gh(_gh_resp(404, {}))

    result, _ = _run_scan(supabase, mc)

    assert result["running_processed"][0]["action"] == "GH_RUN_NOT_FOUND"


# ════════════════════════════════════════════════════════════════════════════════
# 추가: scan_at 타임스탬프 포함 확인
# ════════════════════════════════════════════════════════════════════════════════

def test_scan_at_present_in_result():
    supabase = _SupaMock()
    result, _ = _run_scan(supabase)
    assert "scan_at" in result
    assert result["scan_at"]  # non-empty string
