"""GitHub Actions Workflow 미시작 감시 — WO-TAI-QA-OPS-WORKFLOW-MONITOR-012 (WP-D).

tai-qa 정기 Workflow(qa-twice-daily.yml)가 예정 시각에 실행되지 않은 상황을 감지한다.
감지·보고 전용: QA Run DB 상태 변경 없음.

정기 QA 예정 시각 (UTC):
  - 21:00 UTC → KST 다음날 06:00
  - 10:00 UTC → KST 19:00

감시 검사 시각: 예정 시각 + 60분
  - 21:00 UTC Run → 22:00 UTC 검사 (KST 07:00)
  - 10:00 UTC Run → 11:00 UTC 검사 (KST 20:00)

상태 코드:
  RUN_OBSERVED             — 정상 schedule Run 기록 확인
  RUN_ACTIVE               — queued / in_progress 상태 실행 중
  RUN_COMPLETED            — Job 실행 완료
  WORKFLOW_NOT_OBSERVED    — 60분 유예 후에도 Run 기록 없음 → 운영 경보 후보
  JOB_NOT_STARTED_SUSPECTED— Run은 생성됐으나 Job 시작 증거 없음 → 운영 경보 후보
  WORKFLOW_DISABLED        — API에서 Workflow 비활성 확인 → 운영 경보 후보
  GITHUB_API_NOT_VERIFIED  — API 장애·인증 실패·429/5xx → 조회 오류 기록

안전 원칙:
  - GitHub API 오류는 QA 실패가 아님 → 기존 Run 상태 유지
  - Run 없음을 즉시 실패로 해석하지 않음 (GitHub 지연 공식 인정)
  - Billing 제한 의심은 JOB_NOT_STARTED_SUSPECTED, 확인되기 전 BILLING_CONFIRMED 금지
  - 일반 테스트 실패 ≠ Workflow 미시작
  - QA Run DB INSERT/UPDATE 없음
  - GitHub Actions Dispatch 없음
  - 이번 Draft PR에서는 실제 Slack 발송 비활성 (dry_run=True 고정)

중복 억제:
  workflow_alert_event.dedupe_key 는 일반 인덱스만 존재 — UNIQUE 보장 불가.
  cron_job_log.(job_code, scheduled_for) UNIQUE는 Cron 실행 로그 전용 의미를 유지.
  운영 활성화 전 UNIQUE 인덱스 추가 또는 별도 dedup 테이블이 필요하다.
  현재 Draft PR 범위: 감지·분류·Slack 메시지 생성까지. 실제 발송은 별도 Gate.

환경변수:
  QA_GITHUB_TOKEN       — PAT (workflow read scope) — 절대 log 출력 금지
  QA_GITHUB_OWNER       — repo 소유자 (default: taiengineering)
  QA_MONITOR_REPO       — 감시 대상 repo (default: tai-qa)
  QA_MONITOR_WORKFLOW   — 감시 대상 workflow 파일 (default: qa-twice-daily.yml)
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx
from httpx import NetworkError as _HttpxNetworkError, TimeoutException as _HttpxTimeout

log = logging.getLogger("qa_workflow_monitor")

_GITHUB_API = "https://api.github.com"

# 예정 시각 이후 감시 검사 가능 시각 (분)
_GRACE_MINUTES = 60

# 정기 QA Slot UTC 시각 (hour, minute)
_SCHEDULE_SLOTS_UTC: List[Tuple[int, int]] = [
    (21, 0),   # KST 다음날 06:00
    (10, 0),   # KST 19:00
]

# ── 상태 코드 ─────────────────────────────────────────────────────────────────

STATUS_RUN_OBSERVED             = "RUN_OBSERVED"
STATUS_RUN_ACTIVE               = "RUN_ACTIVE"
STATUS_RUN_COMPLETED            = "RUN_COMPLETED"
STATUS_WORKFLOW_NOT_OBSERVED    = "WORKFLOW_NOT_OBSERVED"
STATUS_JOB_NOT_STARTED_SUSPECTED = "JOB_NOT_STARTED_SUSPECTED"
STATUS_WORKFLOW_DISABLED        = "WORKFLOW_DISABLED"
STATUS_GITHUB_API_NOT_VERIFIED  = "GITHUB_API_NOT_VERIFIED"

# 운영 경보 트리거 대상 상태
_ALERT_STATUSES = frozenset({
    STATUS_WORKFLOW_NOT_OBSERVED,
    STATUS_JOB_NOT_STARTED_SUSPECTED,
    STATUS_WORKFLOW_DISABLED,
})


# ── 환경 설정 ────────────────────────────────────────────────────────────────

def _cfg() -> Dict[str, str]:
    token = os.environ.get("QA_GITHUB_TOKEN", "")
    if not token:
        raise RuntimeError("QA_GITHUB_TOKEN 미설정 — GitHub Workflow 감시 불가")
    return {
        "token":    token,
        "owner":    os.environ.get("QA_GITHUB_OWNER",     "taiengineering"),
        "repo":     os.environ.get("QA_MONITOR_REPO",     "tai-qa"),
        "workflow": os.environ.get("QA_MONITOR_WORKFLOW", "qa-twice-daily.yml"),
    }


def _headers(token: str) -> Dict[str, str]:
    return {
        "Authorization":        f"Bearer {token}",
        "Accept":               "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


# ── Slot 계산 ────────────────────────────────────────────────────────────────

def resolve_scheduled_slot(
    scheduled_slot_utc: Optional[str],
    now_utc: Optional[datetime] = None,
) -> datetime:
    """scheduled_slot_utc 문자열을 datetime으로 변환하거나, 가장 최근 Slot을 자동 선택.

    규칙:
      1. 명시된 경우: 파싱 후 검증 (미래 Slot 거부, 유효 Slot 형식 확인).
      2. 미지정 시: 지금 기준으로 60분 이상 경과한 가장 최근 Slot.

    반환: UTC aware datetime (timezone=UTC).
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)

    if scheduled_slot_utc is not None:
        try:
            dt = datetime.fromisoformat(scheduled_slot_utc.replace("Z", "+00:00"))
        except (ValueError, AttributeError) as exc:
            raise ValueError(f"scheduled_slot_utc 파싱 실패: {scheduled_slot_utc!r}") from exc

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)

        if dt > now_utc:
            raise ValueError(f"미래 Slot 조기 검사 금지: {scheduled_slot_utc!r}")

        _validate_slot_format(dt)
        return dt

    # 자동: 가장 최근 유효 Slot (60분 이상 경과)
    threshold = now_utc - timedelta(minutes=_GRACE_MINUTES)
    candidates: List[datetime] = []
    for days_back in range(2):
        base = now_utc - timedelta(days=days_back)
        for h, m in _SCHEDULE_SLOTS_UTC:
            slot = base.replace(hour=h, minute=m, second=0, microsecond=0)
            if slot <= threshold:
                candidates.append(slot)

    if not candidates:
        raise ValueError("검사 가능한 Slot이 없습니다. 아직 60분이 경과하지 않았습니다.")

    return max(candidates)


def _validate_slot_format(dt: datetime) -> None:
    """dt가 유효한 Schedule Slot 시각인지 검증. 유효하지 않으면 ValueError.

    조건:
      - (hour, minute) ∈ _SCHEDULE_SLOTS_UTC
      - second == 0
      - microsecond == 0

    비표준 시각(예: 12:35Z)은 실제 정기 QA가 없는 윈도우를 감시하게 되어
    오탐(WORKFLOW_NOT_OBSERVED)을 생성할 수 있으므로 허용하지 않는다.
    """
    h, m = dt.hour, dt.minute
    if (h, m) not in _SCHEDULE_SLOTS_UTC:
        valid = [f"{h:02d}:{m:02d}Z" for h, m in _SCHEDULE_SLOTS_UTC]
        raise ValueError(
            f"유효하지 않은 Slot 시각: {h:02d}:{m:02d}Z — 허용 시각: {valid}"
        )
    if dt.second != 0 or dt.microsecond != 0:
        raise ValueError(
            f"Slot 시각의 초·마이크로초는 0이어야 합니다: {dt.isoformat()}"
        )


def slot_window(slot: datetime) -> Tuple[datetime, datetime]:
    """Slot 감시 윈도우: [slot - 5분, slot + 60분].

    GitHub 예약 실행 지연 최대 60분을 수용한다.
    """
    return slot - timedelta(minutes=5), slot + timedelta(minutes=_GRACE_MINUTES)


# ── GitHub API 호출 ──────────────────────────────────────────────────────────

async def _get_workflow_state(cfg: Dict[str, str]) -> Optional[str]:
    """Workflow 활성 상태 조회.

    반환:
      "active"    — 활성
      "disabled_manually" / "disabled_inactivity" / 기타 — 비활성 상태 문자열
      None        — API 오류
    """
    url = (
        f"{_GITHUB_API}/repos/{cfg['owner']}/{cfg['repo']}"
        f"/actions/workflows/{cfg['workflow']}"
    )
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=_headers(cfg["token"]))
    except _HttpxTimeout:
        log.warning("[qa_wf_monitor] Workflow 상태 조회 timeout")
        return None
    except _HttpxNetworkError:
        log.warning("[qa_wf_monitor] Workflow 상태 조회 network error")
        return None
    except Exception:
        log.exception("[qa_wf_monitor] Workflow 상태 조회 오류")
        return None

    if resp.status_code in (401, 403):
        log.warning("[qa_wf_monitor] Workflow 상태 조회 인증 실패: %d", resp.status_code)
        return None
    if resp.status_code == 429:
        log.warning("[qa_wf_monitor] Workflow 상태 조회 rate limited")
        return None
    if resp.status_code >= 500:
        log.warning("[qa_wf_monitor] Workflow 상태 조회 서버 오류: %d", resp.status_code)
        return None
    if resp.status_code != 200:
        log.warning("[qa_wf_monitor] Workflow 상태 조회 예상 외 응답: %d", resp.status_code)
        return None

    try:
        data = resp.json()
    except Exception:
        log.warning("[qa_wf_monitor] Workflow 상태 응답 파싱 실패")
        return None

    return data.get("state", "unknown")


async def _list_workflow_runs(
    cfg: Dict[str, str],
    window_start: datetime,
    window_end: datetime,
) -> Optional[List[Dict[str, Any]]]:
    """schedule 이벤트 Run 목록 조회 (window 내 생성).

    반환:
      List[dict] — 해당 window 내 schedule Run 목록 (비어있을 수 있음)
      None       — API 오류
    """
    url = (
        f"{_GITHUB_API}/repos/{cfg['owner']}/{cfg['repo']}"
        f"/actions/workflows/{cfg['workflow']}/runs"
    )
    params = {
        "event":        "schedule",
        "created":      f"{window_start.strftime('%Y-%m-%dT%H:%M:%SZ')}.."
                        f"{window_end.strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "per_page":     10,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=_headers(cfg["token"]), params=params)
    except _HttpxTimeout:
        log.warning("[qa_wf_monitor] Workflow runs 조회 timeout")
        return None
    except _HttpxNetworkError:
        log.warning("[qa_wf_monitor] Workflow runs 조회 network error")
        return None
    except Exception:
        log.exception("[qa_wf_monitor] Workflow runs 조회 오류")
        return None

    if resp.status_code in (401, 403):
        log.warning("[qa_wf_monitor] Workflow runs 조회 인증 실패: %d", resp.status_code)
        return None
    if resp.status_code == 429:
        log.warning("[qa_wf_monitor] Workflow runs 조회 rate limited")
        return None
    if resp.status_code >= 500:
        log.warning("[qa_wf_monitor] Workflow runs 조회 서버 오류: %d", resp.status_code)
        return None
    if resp.status_code != 200:
        log.warning("[qa_wf_monitor] Workflow runs 조회 예상 외 응답: %d", resp.status_code)
        return None

    try:
        data = resp.json()
    except Exception:
        log.warning("[qa_wf_monitor] Workflow runs 응답 파싱 실패")
        return None

    return data.get("workflow_runs", [])


async def _get_run_jobs(
    cfg: Dict[str, str],
    run_id: int,
) -> Optional[List[Dict[str, Any]]]:
    """Run의 Jobs 목록 조회 (Job 시작 여부 확인용).

    반환:
      List[dict] — jobs 목록 (비어있을 수 있음)
      None       — API 오류
    """
    url = (
        f"{_GITHUB_API}/repos/{cfg['owner']}/{cfg['repo']}"
        f"/actions/runs/{run_id}/jobs"
    )
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=_headers(cfg["token"]))
    except (_HttpxTimeout, _HttpxNetworkError, Exception):
        log.warning("[qa_wf_monitor] jobs 조회 실패: run_id=%d", run_id)
        return None

    if resp.status_code != 200:
        return None

    try:
        data = resp.json()
    except Exception:
        return None

    return data.get("jobs", [])


# ── 상태 분류 ────────────────────────────────────────────────────────────────

def _classify_completed_run(
    run: Dict[str, Any],
    jobs: Optional[List[Dict[str, Any]]],
) -> str:
    """completed Run의 상태 코드 결정.

    jobs=None : Jobs API 조회 실패 → GITHUB_API_NOT_VERIFIED
                (None과 빈 목록의 의미를 혼용하지 않는다)
    jobs=[]   : Jobs API 200 + Job 없음 → JOB_NOT_STARTED_SUSPECTED
    jobs=[..] : started_at 있는 Job 존재 → RUN_COMPLETED
                started_at 없는 Job만 존재 → JOB_NOT_STARTED_SUSPECTED
    """
    if jobs is None:
        log.warning(
            "[qa_wf_monitor] completed run=%s Jobs API 조회 실패 → GITHUB_API_NOT_VERIFIED",
            run.get("id"),
        )
        return STATUS_GITHUB_API_NOT_VERIFIED

    started_jobs = [j for j in jobs if j.get("started_at")]
    if not started_jobs:
        return STATUS_JOB_NOT_STARTED_SUSPECTED
    return STATUS_RUN_COMPLETED


def _classify_queued_run(
    run: Dict[str, Any],
    jobs: Optional[List[Dict[str, Any]]],
    elapsed_minutes: float,
) -> str:
    """queued Run의 상태 코드 결정.

    60분 미경과 : RUN_ACTIVE (GitHub 대기열 지연 허용)
    60분 이상 + jobs=None  : Jobs API 조회 실패 → GITHUB_API_NOT_VERIFIED
    60분 이상 + jobs=[]    : Job 시작 증거 없음 → JOB_NOT_STARTED_SUSPECTED
    60분 이상 + jobs=[..] : Job 시작됨 → RUN_ACTIVE
    """
    if elapsed_minutes < _GRACE_MINUTES:
        return STATUS_RUN_ACTIVE

    if jobs is None:
        return STATUS_GITHUB_API_NOT_VERIFIED

    started_jobs = [j for j in jobs if j.get("started_at")]
    if not started_jobs:
        return STATUS_JOB_NOT_STARTED_SUSPECTED
    return STATUS_RUN_ACTIVE


# ── Slack 관제 메시지 생성 ───────────────────────────────────────────────────

def _build_slack_message(
    status_code: str,
    slot: datetime,
    cfg: Dict[str, str],
    run: Optional[Dict[str, Any]],
    detected_at: str,
) -> Dict[str, Any]:
    """운영 경보 Slack 메시지 구조 생성 (실제 발송 미포함).

    WP-D05 계약 준수:
      - Workflow 이름 포함
      - 예정 실행 시각 KST 포함
      - GitHub Run ID (있는 경우)
      - 상태 코드
      - 감지 시각
      - 관측된 증거
      - GitHub Actions URL
      - QA 실패 결과가 아님을 명시
    """
    kst_offset = timedelta(hours=9)
    slot_kst = (slot + kst_offset).strftime("%Y-%m-%d %H:%M KST")
    workflow_url = (
        f"https://github.com/{cfg['owner']}/{cfg['repo']}"
        f"/actions/workflows/{cfg['workflow']}"
    )
    run_id_str = str(run["id"]) if run else "없음"
    run_url = (
        f"https://github.com/{cfg['owner']}/{cfg['repo']}/actions/runs/{run['id']}"
        if run else workflow_url
    )

    status_labels = {
        STATUS_WORKFLOW_NOT_OBSERVED:     "⚠️ Workflow 미시작 감지",
        STATUS_JOB_NOT_STARTED_SUSPECTED: "⚠️ Job 미시작 의심",
        STATUS_WORKFLOW_DISABLED:         "🔴 Workflow 비활성",
    }
    label = status_labels.get(status_code, f"[{status_code}]")

    return {
        "text": f"{label} — {cfg['workflow']} / {slot_kst}",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*{label}*\n"
                        f"이 메시지는 QA 테스트 결과 실패가 아닙니다.\n"
                        f"GitHub Actions Workflow 시작 여부 감시 알림입니다."
                    ),
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Workflow*\n`{cfg['workflow']}`"},
                    {"type": "mrkdwn", "text": f"*예정 시각*\n{slot_kst}"},
                    {"type": "mrkdwn", "text": f"*상태 코드*\n`{status_code}`"},
                    {"type": "mrkdwn", "text": f"*GitHub Run ID*\n{run_id_str}"},
                    {"type": "mrkdwn", "text": f"*감지 시각*\n{detected_at}"},
                ],
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "GitHub Actions 확인"},
                        "url": run_url,
                    }
                ],
            },
        ],
    }


# ── 감시 진입점 ──────────────────────────────────────────────────────────────

async def monitor_twice_daily(
    scheduled_slot_utc: Optional[str] = None,
    dry_run: bool = True,
    now_utc: Optional[datetime] = None,
) -> Dict[str, Any]:
    """정기 Workflow 미시작 감시 실행.

    Args:
        scheduled_slot_utc: 검사할 Slot (ISO 8601 UTC). 미지정 시 자동 선택.
        dry_run:            True(기본) = 감지·분류만. False = Slack 발송 활성화.
                            이번 Draft PR 범위에서는 항상 True로 고정된다.
        now_utc:            현재 시각 오버라이드 (테스트용).

    Returns:
        {
            "slot_utc":          ISO 8601 UTC Slot 시각,
            "status_code":       상태 코드,
            "requires_alert":    bool — 운영 경보 트리거 여부,
            "run_id":            GitHub Run ID (있는 경우),
            "evidence":          관측된 증거 dict,
            "slack_message":     생성된 Slack 메시지 (requires_alert인 경우),
            "slack_sent":        bool — 항상 False (발송은 qa_monitor_cron_svc Outbox 경유),
            "detected_at":       ISO 8601 UTC 감지 시각,
        }
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)

    slot = resolve_scheduled_slot(scheduled_slot_utc, now_utc=now_utc)
    slot_str = slot.strftime("%Y-%m-%dT%H:%M:%SZ")
    detected_at = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        cfg = _cfg()
    except RuntimeError as exc:
        log.warning("[qa_wf_monitor] 설정 오류: %s", exc)
        return {
            "slot_utc":       slot_str,
            "status_code":    STATUS_GITHUB_API_NOT_VERIFIED,
            "requires_alert": False,
            "run_id":         None,
            "evidence":       {"error": str(exc)},
            "slack_message":  None,
            "slack_sent":     False,
            "detected_at":    detected_at,
        }

    w_start, w_end = slot_window(slot)

    # 1. Workflow 활성 상태 먼저 확인
    wf_state = await _get_workflow_state(cfg)

    if wf_state is None:
        log.warning("[qa_wf_monitor] Workflow 상태 조회 실패 — GITHUB_API_NOT_VERIFIED")
        return {
            "slot_utc":       slot_str,
            "status_code":    STATUS_GITHUB_API_NOT_VERIFIED,
            "requires_alert": False,
            "run_id":         None,
            "evidence":       {"api_error": "workflow_state_not_verified"},
            "slack_message":  None,
            "slack_sent":     False,
            "detected_at":    detected_at,
        }

    if wf_state != "active":
        log.warning(
            "[qa_wf_monitor] Workflow 비활성: state=%r workflow=%s",
            wf_state, cfg["workflow"],
        )
        msg = _build_slack_message(STATUS_WORKFLOW_DISABLED, slot, cfg, None, detected_at)
        return {
            "slot_utc":       slot_str,
            "status_code":    STATUS_WORKFLOW_DISABLED,
            "requires_alert": True,
            "run_id":         None,
            "evidence":       {"workflow_state": wf_state},
            "slack_message":  msg,
            "slack_sent":     False,
            "detected_at":    detected_at,
        }

    # 2. Run 목록 조회
    runs = await _list_workflow_runs(cfg, w_start, w_end)

    if runs is None:
        log.warning("[qa_wf_monitor] Run 목록 조회 실패 — GITHUB_API_NOT_VERIFIED")
        return {
            "slot_utc":       slot_str,
            "status_code":    STATUS_GITHUB_API_NOT_VERIFIED,
            "requires_alert": False,
            "run_id":         None,
            "evidence":       {"api_error": "workflow_runs_not_verified"},
            "slack_message":  None,
            "slack_sent":     False,
            "detected_at":    detected_at,
        }

    # 3. 감시 윈도우 내 Run 없음
    if not runs:
        grace_elapsed = (now_utc - slot).total_seconds() / 60
        if grace_elapsed < _GRACE_MINUTES:
            log.info(
                "[qa_wf_monitor] 아직 유예 중: slot=%s elapsed=%.1fmin",
                slot_str, grace_elapsed,
            )
            return {
                "slot_utc":       slot_str,
                "status_code":    STATUS_WORKFLOW_NOT_OBSERVED,
                "requires_alert": False,
                "run_id":         None,
                "evidence":       {
                    "grace_elapsed_min": round(grace_elapsed, 1),
                    "grace_remaining_min": round(_GRACE_MINUTES - grace_elapsed, 1),
                    "note": "60분 유예 미경과 — 아직 정상 범위",
                },
                "slack_message":  None,
                "slack_sent":     False,
                "detected_at":    detected_at,
            }

        # 60분 이상 경과 + Run 없음 → 운영 경보
        log.warning(
            "[qa_wf_monitor] WORKFLOW_NOT_OBSERVED: slot=%s elapsed=%.1fmin",
            slot_str, grace_elapsed,
        )
        msg = _build_slack_message(STATUS_WORKFLOW_NOT_OBSERVED, slot, cfg, None, detected_at)
        return {
            "slot_utc":       slot_str,
            "status_code":    STATUS_WORKFLOW_NOT_OBSERVED,
            "requires_alert": True,
            "run_id":         None,
            "evidence":       {
                "grace_elapsed_min": round(grace_elapsed, 1),
                "window_start_utc":  w_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "window_end_utc":    w_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
            "slack_message":  msg,
            "slack_sent":     False,
            "detected_at":    detected_at,
        }

    # 4. Run 발견 — 가장 최근 Run 분석
    run = sorted(runs, key=lambda r: r.get("created_at", ""), reverse=True)[0]
    run_id = run.get("id")
    gh_status = run.get("status", "")
    elapsed_minutes = (now_utc - slot).total_seconds() / 60

    # Job 조회 조건:
    #   - completed: 항상 조회 (시작 증거 확인)
    #   - queued + 60분 이상 경과: Billing 제한·대기열 장기 정체 감지
    #   - in_progress: 조회 불필요 (Run 자체가 실행 중임을 GitHub이 확인)
    jobs: Optional[List[Dict[str, Any]]] = None
    if gh_status == "completed":
        jobs = await _get_run_jobs(cfg, run_id)
    elif gh_status == "queued" and elapsed_minutes >= _GRACE_MINUTES:
        jobs = await _get_run_jobs(cfg, run_id)

    # 상태 분류 (None과 [] 의미 구분)
    if gh_status == "completed":
        status_code = _classify_completed_run(run, jobs)
    elif gh_status == "queued":
        status_code = _classify_queued_run(run, jobs, elapsed_minutes)
    elif gh_status == "in_progress":
        status_code = STATUS_RUN_ACTIVE
    else:
        log.warning("[qa_wf_monitor] 알 수 없는 Run status: %r run_id=%s", gh_status, run_id)
        status_code = STATUS_RUN_OBSERVED

    evidence: Dict[str, Any] = {
        "run_id":              run_id,
        "run_status":          gh_status,
        "run_conclusion":      run.get("conclusion"),
        "run_created_at":      run.get("created_at"),
        "run_html_url":        run.get("html_url"),
        "elapsed_minutes":     round(elapsed_minutes, 1),
    }
    if jobs is not None:
        evidence["job_count"]    = len(jobs)
        evidence["jobs_started"] = sum(1 for j in jobs if j.get("started_at"))

    requires_alert = status_code in _ALERT_STATUSES
    slack_msg: Optional[Dict[str, Any]] = None
    if requires_alert:
        slack_msg = _build_slack_message(status_code, slot, cfg, run, detected_at)
        log.warning(
            "[qa_wf_monitor] %s: slot=%s run_id=%s",
            status_code, slot_str, run_id,
        )
    else:
        log.info(
            "[qa_wf_monitor] %s: slot=%s run_id=%s",
            status_code, slot_str, run_id,
        )

    return {
        "slot_utc":       slot_str,
        "status_code":    status_code,
        "requires_alert": requires_alert,
        "run_id":         run_id,
        "evidence":       evidence,
        "slack_message":  slack_msg,
        "slack_sent":     False,
        "detected_at":    detected_at,
    }
