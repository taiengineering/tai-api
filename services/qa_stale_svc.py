"""QA Stale Run Scanner — WO-TAI-QA-OPS-STALE-RUN-011.

DB와 GitHub Actions 상태를 대조하여 장기 정체 Run을 감지하고 보고한다.

안전 원칙:
  - GitHub API 오류(Timeout/네트워크/429/5xx/인증실패)는 QA 실패가 아님 → 상태 유지
  - None 반환(API 조회 실패)은 ERROR 전이 사유가 될 수 없음
  - 정상 실행 중인 Run을 임의로 ERROR 처리하지 않음
  - ERROR 전이 직전 DB 상태 재조회 (Callback 경합 보호)
  - apply_results()를 통한 lifecycle 준수 전이 (직접 DB UPDATE 금지)
  - github_run_id + github_run_attempt 양쪽 일치 확인 (잘못된 연결 방지)
  - Slack 발송 실패는 감지 결과에 영향 없음

QUEUED Stale (>30분):
  감지·보고만. 자동 ERROR 전이 없음.
  github_run_id가 없어 GitHub 확인 불가능한 경우 많음 (MANUAL run 등).

RUNNING Stale (>45분):
  GitHub 조회 가능한 경우에만 completed 확인.
  5가지 조건 모두 충족 시 STALE_RUN_NO_CALLBACK으로 ERROR 전이:
    1. DB Run이 여전히 RUNNING
    2. GitHub Run이 completed
    3. github_run_attempt 일치
    4. DB에 결과 기록 없음 (Callback 누락)
    5. 스캔 기준 유예시간 이미 경과 (calling > running_cutoff 시점 기준)
"""
from __future__ import annotations

import logging
import math
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx
from httpx import NetworkError as _HttpxNetworkError, TimeoutException as _HttpxTimeout

from services.qa_control_svc import apply_results
from services.qa_notify_svc import QA_RUN_ERROR, build_qa_slack_payload
from services.slack_dispatcher import send_slack
from services.time import now_kst

log = logging.getLogger("qa_stale")

# 정체 판단 기준 (분)
_QUEUED_STALE_MINUTES  = 30
_RUNNING_STALE_MINUTES = 45

# RUNNING stale → GitHub completed 확인 후 ERROR 전이할 최소 경과 시간 (분)
# 이 값은 _RUNNING_STALE_MINUTES에 포함됨 (추가 유예 없음 — 이미 45분 경과)
_CALLBACK_GRACE_MINUTES = 0  # 0 = 45분 기준 자체가 유예 역할

_GITHUB_API = "https://api.github.com"

# GitHub 응답 status 상수
_GH_IN_PROGRESS = "in_progress"
_GH_QUEUED      = "queued"
_GH_COMPLETED   = "completed"

# 내부 판정 코드 (GitHub API 오류 종류 구분)
_NOT_VERIFIED       = "NOT_VERIFIED"
_ATTEMPT_MISMATCH   = "ATTEMPT_MISMATCH"
_GH_RUN_NOT_FOUND   = "GH_RUN_NOT_FOUND"

_RUN_COLS = (
    "id, trigger_type, run_status, github_run_id, github_run_attempt, "
    "started_at, requested_at, finished_at, error_code"
)


# ── GitHub API ────────────────────────────────────────────────────────────────

async def _get_github_run_status(
    github_run_id: int,
    expected_attempt: int,
) -> Optional[str]:
    """GitHub Workflow run 상태 조회.

    반환값:
      "queued" / "in_progress" / "completed"  — GitHub 실제 상태
      "not_found"       — 404 (run 없음)
      "attempt_mismatch" — run_attempt 불일치 (잘못된 연결)
      None              — API 오류 (Timeout/네트워크/429/5xx/인증실패) → NOT_VERIFIED
    """
    token = os.environ.get("QA_GITHUB_TOKEN", "")
    if not token:
        log.warning("[qa_stale] QA_GITHUB_TOKEN 미설정 — GitHub 조회 불가")
        return None

    owner = os.environ.get("QA_GITHUB_OWNER", "taiengineering")
    repo  = os.environ.get("QA_GITHUB_REPO", "tai-qa")
    url   = f"{_GITHUB_API}/repos/{owner}/{repo}/actions/runs/{github_run_id}"
    headers = {
        "Authorization":        f"Bearer {token}",
        "Accept":               "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
    except _HttpxTimeout:
        log.warning("[qa_stale] GitHub API timeout: run_id=%d", github_run_id)
        return None
    except _HttpxNetworkError:
        log.warning("[qa_stale] GitHub API network error: run_id=%d", github_run_id)
        return None
    except Exception:
        log.exception("[qa_stale] GitHub API unexpected error: run_id=%d", github_run_id)
        return None

    if resp.status_code == 404:
        return _GH_RUN_NOT_FOUND

    if resp.status_code in (401, 403):
        log.warning("[qa_stale] GitHub auth error: %d run_id=%d", resp.status_code, github_run_id)
        return None

    if resp.status_code == 429:
        log.warning("[qa_stale] GitHub rate limited: run_id=%d", github_run_id)
        return None

    if resp.status_code >= 500:
        log.warning("[qa_stale] GitHub server error: %d run_id=%d", resp.status_code, github_run_id)
        return None

    if resp.status_code != 200:
        log.warning("[qa_stale] GitHub unexpected status: %d run_id=%d", resp.status_code, github_run_id)
        return None

    try:
        data = resp.json()
    except Exception:
        log.warning("[qa_stale] GitHub response parse error: run_id=%d", github_run_id)
        return None

    actual_attempt = data.get("run_attempt")
    if actual_attempt is not None and actual_attempt != expected_attempt:
        log.warning(
            "[qa_stale] attempt mismatch: run_id=%d expected=%d actual=%d",
            github_run_id, expected_attempt, actual_attempt,
        )
        return _ATTEMPT_MISMATCH

    return data.get("status")  # "queued" / "in_progress" / "completed"


# ── DB helpers ────────────────────────────────────────────────────────────────

def _reread_run(supabase, run_id: str) -> Optional[Dict[str, Any]]:
    """ERROR 전이 직전 DB 상태 재조회 (Callback 경합 보호)."""
    res = (
        supabase.table("qa_runs")
        .select(_RUN_COLS)
        .eq("id", run_id)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def _has_results(supabase, run_id: str) -> bool:
    """qa_run_results에 이 run의 결과가 한 건이라도 있으면 True."""
    res = (
        supabase.table("qa_run_results")
        .select("id")
        .eq("run_id", run_id)
        .limit(1)
        .execute()
    )
    return bool(res.data)


# ── Slack (fail-safe) ─────────────────────────────────────────────────────────

async def _notify_stale(run: Dict[str, Any], error_code: str, summary: str) -> None:
    """Stale run 감지 Slack 알림. 발송 실패는 조용히 흡수."""
    try:
        notif = {
            "event_type":    QA_RUN_ERROR,
            "trigger_type":  run.get("trigger_type"),
            "run_id":        run["id"],
            "error_summary": summary,
        }
        payload = build_qa_slack_payload(notif, is_run=True)
        await send_slack(**payload)
    except Exception as exc:
        log.warning("[qa_stale] Slack notify failed run=%s: %s", run["id"], exc)


# ── Stale scan entry point ────────────────────────────────────────────────────

async def scan_stale_runs(supabase) -> Dict[str, Any]:
    """QUEUED/RUNNING 정체 Run 스캔.

    반환 구조:
      {
        "queued_reported": [{"run_id": ..., "action": "REPORTED", ...}],
        "running_processed": [{"run_id": ..., "action": ..., "gh_status": ...}],
        "errors": [{"run_id": ..., "error": ...}],
        "scan_at": ISO timestamp,
      }

    action 종류:
      RUNNING stale:
        STILL_ACTIVE        — GitHub in_progress → 유지
        NOT_VERIFIED        — GitHub API 실패 → 유지
        ATTEMPT_MISMATCH    — attempt 불일치 → 유지
        GH_RUN_NOT_FOUND    — GitHub 404 → 보고만
        NO_GH_ID            — github_run_id 없음 → 보고만
        ALREADY_TRANSITIONED — 재조회 결과 더 이상 RUNNING 아님 → 무시
        RESULTS_EXIST       — 결과 기록 있음 (Callback 처리 중) → 무시
        ERRORED_STALE       — 5조건 충족 → apply_results(ERROR)
      QUEUED stale:
        REPORTED            — 감지·보고만 (자동 ERROR 없음)
    """
    now = now_kst()
    scan_at = now.isoformat()

    queued_cutoff  = (now - timedelta(minutes=_QUEUED_STALE_MINUTES)).isoformat()
    running_cutoff = (now - timedelta(minutes=_RUNNING_STALE_MINUTES)).isoformat()

    queued_res = (
        supabase.table("qa_runs")
        .select(_RUN_COLS)
        .eq("run_status", "QUEUED")
        .lte("requested_at", queued_cutoff)
        .execute()
    )
    running_res = (
        supabase.table("qa_runs")
        .select(_RUN_COLS)
        .eq("run_status", "RUNNING")
        .lte("started_at", running_cutoff)
        .execute()
    )

    queued_stale  = queued_res.data or []
    running_stale = running_res.data or []

    result: Dict[str, Any] = {
        "queued_reported":   [],
        "running_processed": [],
        "errors":            [],
        "scan_at":           scan_at,
    }

    # ── QUEUED stale: 감지·보고 전용 ─────────────────────────────────────────
    for run in queued_stale:
        run_id = run["id"]
        log.warning(
            "[qa_stale] QUEUED stale: run=%s trigger=%s age>%dmin",
            run_id, run.get("trigger_type"), _QUEUED_STALE_MINUTES,
        )
        result["queued_reported"].append({
            "run_id":       run_id,
            "trigger_type": run.get("trigger_type"),
            "action":       "REPORTED",
        })
        await _notify_stale(
            run,
            "STALE_QUEUED",
            f"QUEUED 상태 {_QUEUED_STALE_MINUTES}분 초과 — GitHub dispatch 미완료로 추정됨",
        )

    # ── RUNNING stale: GitHub 대조 후 조건부 ERROR ────────────────────────────
    for run in running_stale:
        run_id           = run["id"]
        github_run_id    = run.get("github_run_id")
        github_run_attempt = run.get("github_run_attempt") or 1

        # github_run_id 없음 → GitHub 조회 불가, 보고만
        if not github_run_id:
            log.warning(
                "[qa_stale] RUNNING stale no github_run_id: run=%s trigger=%s",
                run_id, run.get("trigger_type"),
            )
            result["running_processed"].append({
                "run_id":  run_id,
                "action":  "NO_GH_ID",
            })
            continue

        gh_status = await _get_github_run_status(github_run_id, github_run_attempt)

        # API 실패 → NOT_VERIFIED, 상태 유지
        if gh_status is None:
            log.warning("[qa_stale] NOT_VERIFIED: run=%s gh_run=%s", run_id, github_run_id)
            result["running_processed"].append({
                "run_id":    run_id,
                "gh_run_id": github_run_id,
                "action":    _NOT_VERIFIED,
            })
            continue

        # GitHub에서 여전히 실행 중 → 상태 유지
        if gh_status in (_GH_QUEUED, _GH_IN_PROGRESS):
            log.info(
                "[qa_stale] still active: run=%s gh_status=%s", run_id, gh_status,
            )
            result["running_processed"].append({
                "run_id":    run_id,
                "gh_run_id": github_run_id,
                "gh_status": gh_status,
                "action":    "STILL_ACTIVE",
            })
            continue

        # attempt 불일치 → 잘못된 연결, 상태 유지
        if gh_status == _ATTEMPT_MISMATCH:
            result["running_processed"].append({
                "run_id":    run_id,
                "gh_run_id": github_run_id,
                "action":    _ATTEMPT_MISMATCH,
            })
            continue

        # GitHub에 run 없음 → 보고만 (즉시 ERROR 불가)
        if gh_status == _GH_RUN_NOT_FOUND:
            log.warning("[qa_stale] GH run not found: run=%s gh_run=%s", run_id, github_run_id)
            result["running_processed"].append({
                "run_id":    run_id,
                "gh_run_id": github_run_id,
                "action":    _GH_RUN_NOT_FOUND,
            })
            continue

        # ── gh_status == "completed" 확인 ────────────────────────────────────
        if gh_status != _GH_COMPLETED:
            log.warning(
                "[qa_stale] unknown gh_status=%r run=%s", gh_status, run_id,
            )
            result["running_processed"].append({
                "run_id":    run_id,
                "gh_run_id": github_run_id,
                "gh_status": gh_status,
                "action":    _NOT_VERIFIED,
            })
            continue

        # 조건 1+2 충족: GitHub completed
        # 조건 3: DB 상태 재조회 (Callback 경합 보호)
        current = _reread_run(supabase, run_id)
        if current is None or current["run_status"] != "RUNNING":
            log.info(
                "[qa_stale] already transitioned: run=%s status=%s",
                run_id, current["run_status"] if current else "DELETED",
            )
            result["running_processed"].append({
                "run_id":    run_id,
                "gh_run_id": github_run_id,
                "gh_status": gh_status,
                "action":    "ALREADY_TRANSITIONED",
            })
            continue

        # 조건 4: DB에 결과 없음 (Callback 누락 확인)
        if _has_results(supabase, run_id):
            log.info(
                "[qa_stale] results exist (callback in progress): run=%s", run_id,
            )
            result["running_processed"].append({
                "run_id":    run_id,
                "gh_run_id": github_run_id,
                "gh_status": gh_status,
                "action":    "RESULTS_EXIST",
            })
            continue

        # 조건 5: 이미 running_cutoff 경과 (45분) — scan 진입 시점 기준으로 이미 충족

        # 5조건 모두 충족 → STALE_RUN_NO_CALLBACK
        log.warning(
            "[qa_stale] STALE_RUN_NO_CALLBACK: run=%s gh_run=%d completed, no callback",
            run_id, github_run_id,
        )
        try:
            apply_results(
                supabase,
                run_id=run_id,
                new_status="ERROR",
                github_run_id=None,
                github_run_attempt=None,
                head_sha=None,
                branch_name=None,
                run_started_at=None,
                run_finished_at=now.isoformat(),
                run_error_code="STALE_RUN_NO_CALLBACK",
                run_error_summary=(
                    f"GitHub run {github_run_id} (attempt {github_run_attempt}) "
                    "completed but callback was never received"
                ),
                results=[],
            )
            result["running_processed"].append({
                "run_id":    run_id,
                "gh_run_id": github_run_id,
                "gh_status": gh_status,
                "action":    "ERRORED_STALE",
            })
            await _notify_stale(
                current,
                "STALE_RUN_NO_CALLBACK",
                f"GitHub run {github_run_id} 완료 후 Callback 미수신 — STALE_RUN_NO_CALLBACK",
            )
        except Exception as exc:
            log.error(
                "[qa_stale] apply_results failed: run=%s: %s", run_id, exc,
            )
            result["errors"].append({
                "run_id": run_id,
                "error":  str(exc),
            })

    log.info(
        "[qa_stale] scan done: queued=%d running=%d errors=%d",
        len(result["queued_reported"]),
        len(result["running_processed"]),
        len(result["errors"]),
    )
    return result
