"""QA Twice-Daily Timed Trigger — WO-TAI-QA-OPS-TIMED-TRIGGER-P0-005-R2.

GitHub Actions schedule 지연(최대 수 시간)을 우회하기 위해 TAI 스케줄러에서
qa-twice-daily.yml을 workflow_dispatch로 정시(KST 06:00 / 19:00) 발화한다.

cron_job_master: '0 6,19 * * *' KST (= 21:00Z + 10:00Z UTC)
dispatcher.py: claim_context(_scheduled_for, _attempt_no)를 payload에 전달한다.

contract:
  - 환경변수: QA_GITHUB_TOKEN (필수, 절대 log 출력 금지)
              QA_GITHUB_OWNER   (기본: taiengineering)
              QA_GITHUB_REPO    (기본: tai-qa)
              QA_GITHUB_WORKFLOW_TWICE_DAILY (기본: qa-twice-daily.yml)
              QA_GITHUB_REF     (기본: main)
  - 발화 대상: qa-twice-daily.yml — inputs 없음 (workflow가 자체 결정)
  - scheduled_for: dispatcher가 전달한 _scheduled_for 우선, 없으면 current_slot_utc(now) 폴백
  - 재처리 차단: _attempt_no > 1 이면 GitHub 미전송, DISPATCH_SKIPPED_RETRY 반환
  - 실패 시: RuntimeError 전파, no retry

4개 타임스탬프 (cron_job_log.detail에 기록):
  scheduled_for         — claim.scheduled_for 기준 UTC 시각 (dispatcher 전달값 우선)
  dispatch_attempted_at — GitHub API POST 직전
  dispatch_accepted_at  — GitHub HTTP 200/204 수신 시각
  github_job_started_at — None (비동기 확인 불가 — workflow monitor가 추후 갱신)

DB 변경 없음 — 스케줄러 claim/complete 경로가 cron_job_log 기록 담당.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

import httpx

log = logging.getLogger("qa_cron_trigger")

_GITHUB_API = "https://api.github.com"
_TWICE_DAILY_WORKFLOW_DEFAULT = "qa-twice-daily.yml"

# UTC 고정 슬롯: 10:00Z = KST 19:00 / 21:00Z = KST 06:00(익일)
_UTC_SLOTS = (10, 21)


def _cfg() -> dict:
    token = os.environ.get("QA_GITHUB_TOKEN", "")
    if not token:
        raise RuntimeError("QA_GITHUB_TOKEN 미설정 — GitHub dispatch 불가")
    return {
        "token":    token,
        "owner":    os.environ.get("QA_GITHUB_OWNER", "taiengineering"),
        "repo":     os.environ.get("QA_GITHUB_REPO", "tai-qa"),
        "workflow": os.environ.get(
            "QA_GITHUB_WORKFLOW_TWICE_DAILY", _TWICE_DAILY_WORKFLOW_DEFAULT
        ),
        "ref":      os.environ.get("QA_GITHUB_REF", "main"),
    }


def current_slot_utc(now: datetime) -> datetime:
    """now 기준 직전 UTC 슬롯(10:00Z 또는 21:00Z) 반환.

    예: now=10:05Z → 10:00Z / now=09:59Z → 전날 21:00Z
    """
    now_utc = now.astimezone(timezone.utc)
    candidates = []
    for hour in _UTC_SLOTS:
        candidates.append(now_utc.replace(hour=hour, minute=0, second=0, microsecond=0))
        candidates.append(
            (now_utc - timedelta(days=1)).replace(hour=hour, minute=0, second=0, microsecond=0)
        )
    past = [s for s in candidates if s <= now_utc]
    return max(past)


async def dispatch_qa_twice_daily(scheduled_for: datetime) -> dict:
    """qa-twice-daily.yml workflow_dispatch 호출 후 타임스탬프 dict 반환.

    실패 시 RuntimeError 전파. no retry.
    token은 절대 log에 출력하지 않는다.
    """
    cfg = _cfg()
    url = (
        f"{_GITHUB_API}/repos/{cfg['owner']}/{cfg['repo']}"
        f"/actions/workflows/{cfg['workflow']}/dispatches"
    )
    # qa-twice-daily.yml은 workflow_dispatch inputs 없음
    payload = {"ref": cfg["ref"]}
    headers = {
        "Authorization":        f"Bearer {cfg['token']}",
        "Accept":               "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    dispatch_attempted_at = datetime.now(timezone.utc).isoformat()

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, json=payload, headers=headers)

    if resp.status_code not in (200, 204):
        # status/body만 로그 — token 절대 미포함
        log.error(
            "[qa_cron_trigger] dispatch failed: status=%s slot=%s",
            resp.status_code,
            scheduled_for.isoformat(),
        )
        raise RuntimeError(
            f"GitHub dispatch failed: HTTP {resp.status_code}"
        )

    dispatch_accepted_at = datetime.now(timezone.utc).isoformat()
    log.info(
        "[qa_cron_trigger] dispatched: slot=%s workflow=%s",
        scheduled_for.isoformat(),
        cfg["workflow"],
    )

    return {
        "scheduled_for":         scheduled_for.isoformat(),
        "dispatch_attempted_at": dispatch_attempted_at,
        "dispatch_accepted_at":  dispatch_accepted_at,
        "github_job_started_at": None,  # 비동기 확인 불가 — workflow monitor가 추후 갱신
    }


async def trigger_qa_cron(payload: dict | None = None) -> dict:
    """TAI 스케줄러 핸들러 진입점.

    dispatcher.py가 claim_context(_scheduled_for, _attempt_no)를 payload에 주입한다.

    _scheduled_for: claim.scheduled_for — 스케줄러가 전달하는 정규 예약 시각 (UTC ISO)
                    없으면 current_slot_utc(now()) 폴백
    _attempt_no: > 1이면 재처리 — GitHub 미전송, DISPATCH_SKIPPED_RETRY 반환
    """
    p = payload or {}
    attempt_no = int(p.get("_attempt_no", 1))

    # R2-04: 재처리(attempt_no > 1) 시 GitHub 자동 재전송 금지
    if attempt_no > 1:
        log.warning(
            "[qa_cron_trigger] DISPATCH_SKIPPED_RETRY attempt_no=%s scheduled_for=%s",
            attempt_no,
            p.get("_scheduled_for"),
        )
        return {
            "status":                "DISPATCH_SKIPPED_RETRY",
            "reason":               f"attempt_no={attempt_no} — 재처리 시 자동 재전송 금지",
            "scheduled_for":         p.get("_scheduled_for"),
            "dispatch_attempted_at": None,
            "dispatch_accepted_at":  None,
            "github_job_started_at": None,
            "trigger_source":        "tai_scheduler",
        }

    # R2-03: dispatcher 전달값 우선, 없으면 now() 폴백
    scheduled_for_iso = p.get("_scheduled_for")
    if scheduled_for_iso:
        scheduled_for = datetime.fromisoformat(scheduled_for_iso)
    else:
        now = datetime.now(timezone.utc)
        scheduled_for = current_slot_utc(now)

    result = await dispatch_qa_twice_daily(scheduled_for)
    result["trigger_source"] = "tai_scheduler"
    return result
