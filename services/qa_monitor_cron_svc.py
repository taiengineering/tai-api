"""QA Monitor Cron Service — WO-016 WP-A.

WP-D Workflow 미시작 감시와 WP-E Stale Run 스캔을 Cron 형태로 실행한다.

Cron 스케줄 (미등록 — Draft PR 범위. DB 적용 없음):
  qa_workflow_monitor_twice_daily : 0 11,22 * * *  (UTC)
    → KST 20:00 / 07:00 (QA 예정 시각 + 60분 후)
    → 검사 대상 Slot: UTC 10:00 / 21:00 (60분 유예 후)
  qa_stale_run_scanner            : 10,25,40,55 * * * *  (UTC)
    → 15분마다

scheduled_for 기반 Slot 결정:
  cron_job_log 의 scheduled_for (UTC) 을 기반으로 감시 대상 Slot을 역산한다.
  scheduled_for = Slot + 60분 → Slot = scheduled_for - 60분.
  scheduled_for 가 없으면 now_utc 기준 자동 선택.

Fail-Closed 활성화 (WP-D):
  Slack 발송을 위해서는 두 조건을 모두 충족해야 한다:
    1. dry_run=False 로 명시적 호출
    2. 환경변수 QA_MONITOR_SLACK_ENABLED=true 설정
  어느 하나라도 없으면 Slack 발송 없이 감지·분류만 수행한다.

안전 원칙:
  - 실제 Slack 발송은 qa_monitor_outbox_svc 의 Outbox 경유
  - DB 마이그레이션 WO016_qa_monitor_notification_outbox.sql 적용 전까지
    dry_run=False 호출은 아웃박스 삽입을 시도하다 오류가 발생한다.
  - Cron 미등록 — 운영 활성화 전 별도 Owner 승인 필요
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

# 모듈 레벨 import — 테스트에서 patch("services.qa_monitor_cron_svc.X") 가능
from db.supabase_client import get_supabase
from services.qa_monitor_outbox_svc import accept_monitor_notification, send_monitor_notification
from services.qa_stale_svc import scan_stale_runs
from services.qa_workflow_monitor_svc import monitor_twice_daily

log = logging.getLogger("qa_monitor_cron")

# Slack 발송 활성화 환경변수
_ENV_SLACK_ENABLED = "QA_MONITOR_SLACK_ENABLED"

# 허용 예약 시각 UTC (hour, minute) → 대응 Slot (hour, minute)
# scheduled_for = Slot + 60분 (qa_workflow_monitor_svc._GRACE_MINUTES = 60)
_ALLOWED_SCHEDULED_FOR: Dict[tuple, tuple] = {
    (11, 0): (10, 0),   # UTC 11:00 → QA Slot 10:00
    (22, 0): (21, 0),   # UTC 22:00 → QA Slot 21:00
}


def _is_slack_enabled() -> bool:
    """QA_MONITOR_SLACK_ENABLED=true 인 경우만 True."""
    return os.environ.get(_ENV_SLACK_ENABLED, "").strip().lower() == "true"


def _slot_from_scheduled_for(scheduled_for_utc: str) -> str:
    """scheduled_for (ISO 8601) 에서 감시 대상 Slot UTC ISO 를 역산.

    Fail-Closed:
      - timezone-aware 입력만 허용 (naive 거부)
      - 입력을 UTC로 정규화
      - 분·초·마이크로초 = 0 검증
      - 허용 예약 시각 테이블(_ALLOWED_SCHEDULED_FOR)에 없으면 ValueError
      - 파싱 실패 시 자동 Slot 선택 없음

    Returns:
      Slot UTC ISO 8601 문자열 ("YYYY-MM-DDTHH:MM:SSZ")
    """
    if not isinstance(scheduled_for_utc, str) or not scheduled_for_utc.strip():
        raise ValueError(f"scheduled_for 빈 값: {scheduled_for_utc!r}")

    try:
        dt = datetime.fromisoformat(scheduled_for_utc.replace("Z", "+00:00"))
    except (ValueError, AttributeError) as exc:
        raise ValueError(
            f"scheduled_for ISO 8601 파싱 실패: {scheduled_for_utc!r}"
        ) from exc

    # timezone-aware 필수
    if dt.tzinfo is None:
        raise ValueError(
            f"scheduled_for timezone 없음 (UTC 명시 필요): {scheduled_for_utc!r}"
        )

    # UTC 정규화
    dt_utc = dt.astimezone(timezone.utc)

    # 분·초·마이크로초 검증
    if dt_utc.minute != 0 or dt_utc.second != 0 or dt_utc.microsecond != 0:
        raise ValueError(
            f"scheduled_for 분·초·마이크로초는 0이어야 함: {dt_utc.isoformat()}"
        )

    # 허용 예약 시각 검증 (Fail-Closed)
    key = (dt_utc.hour, dt_utc.minute)
    slot_hm = _ALLOWED_SCHEDULED_FOR.get(key)
    if slot_hm is None:
        allowed = [f"{h:02d}:{m:02d}Z" for h, m in sorted(_ALLOWED_SCHEDULED_FOR)]
        raise ValueError(
            f"비허용 예약 시각: {dt_utc.hour:02d}:{dt_utc.minute:02d}Z — "
            f"허용 시각: {allowed}"
        )

    slot_dt = dt_utc.replace(hour=slot_hm[0], minute=slot_hm[1], second=0, microsecond=0)
    return slot_dt.strftime("%Y-%m-%dT%H:%M:%SZ")


async def run_monitor_cron(
    supabase: Any = None,
    scheduled_for: Optional[str] = None,
    dry_run: bool = True,
    now_utc: Optional[datetime] = None,
) -> Dict[str, Any]:
    """WP-D Workflow 미시작 감시 Cron 실행.

    Args:
        supabase:       Supabase 클라이언트 (Slack 발송 활성화 시 필요).
        scheduled_for:  Cron 예약 시각 UTC ISO (cron_job_log.scheduled_for).
                        지정 시 Slot = scheduled_for - 60분.
                        미지정 시 monitor_twice_daily 자동 선택.
        dry_run:        False = Slack 발송 시도. True = 감지·분류만.
                        QA_MONITOR_SLACK_ENABLED=true 도 함께 필요.
        now_utc:        현재 시각 오버라이드 (테스트용).

    Returns:
        monitor_result + slack_enabled + outbox_status 포함 dict.
    """
    scheduled_slot_utc: Optional[str] = None
    if scheduled_for is not None:
        # Fail-Closed: 예약 시각 오류 시 자동 Slot 선택 금지 — 호출자에게 전파
        scheduled_slot_utc = _slot_from_scheduled_for(scheduled_for)

    monitor_result = await monitor_twice_daily(
        scheduled_slot_utc=scheduled_slot_utc,
        dry_run=True,
        now_utc=now_utc,
    )

    outbox_status: Optional[str] = None
    slack_enabled = _is_slack_enabled()

    if monitor_result.get("requires_alert") and not dry_run and slack_enabled:
        if supabase is None:
            log.error(
                "[qa_monitor_cron] Slack 활성화 시 supabase 클라이언트 필요 — 발송 건너뜀"
            )
        else:
            slot_utc    = monitor_result.get("slot_utc", "")
            status_code = monitor_result.get("status_code", "")
            event_type  = "QA_WORKFLOW_MONITOR_ALERT"

            # R1-03: repository|workflow|scheduled_slot_utc|event_type
            # 동일 Workflow의 동일 예정 실행에 대한 관측 상태 변화 시 중복 발송 억제
            from services.qa_workflow_monitor_svc import _cfg as _monitor_cfg
            try:
                _cfg_data = _monitor_cfg()
                repo      = _cfg_data.get("repo", "tai-qa")
                owner     = _cfg_data.get("owner", "taiengineering")
                workflow  = _cfg_data.get("workflow", "qa-twice-daily.yml")
            except RuntimeError:
                repo     = os.environ.get("QA_MONITOR_REPO",     "tai-qa")
                owner    = os.environ.get("QA_GITHUB_OWNER",    "taiengineering")
                workflow = os.environ.get("QA_MONITOR_WORKFLOW", "qa-twice-daily.yml")

            repository = f"{owner}/{repo}"
            dedupe_key = f"{repository}|{workflow}|{slot_utc}|{event_type}"
            slack_msg  = monitor_result.get("slack_message") or {}

            slack_payload: Dict[str, Any] = {
                "event_type":  event_type,
                "severity":    "WARNING",
                "title":       slack_msg.get("text", f"QA Workflow Monitor: {status_code}"),
                "detail":      f"slot={slot_utc} status={status_code}",
                "blocks":      slack_msg.get("blocks"),
                "repository":  repository,
                "workflow":    workflow,
            }

            inserted, row_id = accept_monitor_notification(
                supabase,
                dedupe_key=dedupe_key,
                slot_utc=slot_utc,
                status_code=status_code,
                slack_payload=slack_payload,
            )
            if inserted and row_id:
                outbox_status = await send_monitor_notification(
                    supabase, row_id, slack_payload
                )
            else:
                outbox_status = "DEDUPED"
                log.info(
                    "[qa_monitor_cron] 중복 경보 억제 dedupe_key=%s", dedupe_key
                )
    elif monitor_result.get("requires_alert"):
        reason = "dry_run=True" if dry_run else "QA_MONITOR_SLACK_ENABLED not true"
        log.info(
            "[qa_monitor_cron] 경보 감지됨 — Slack 비활성 (%s) status=%s",
            reason,
            monitor_result.get("status_code"),
        )

    # R2-01: outbox_status 기준으로 slack_sent / slack_accepted 계산.
    # monitor_twice_daily()의 slack_sent(항상 False, 감지 전용) 을 여기서 덮어씀.
    # slack_sent:    Slack 발송 수락 + DB 완료 기록까지 모두 성공
    # slack_accepted: Slack API가 발송을 수락 (DB 기록 실패 포함)
    slack_sent = outbox_status == "SENT"
    slack_accepted = outbox_status in ("SENT", "SENT_DB_FAILED")

    return {
        **monitor_result,
        "slack_enabled": slack_enabled,
        "outbox_status": outbox_status,
        "slack_sent": slack_sent,
        "slack_accepted": slack_accepted,
    }


async def run_stale_scan_cron() -> Dict[str, Any]:
    """WP-E Stale Run 스캔 Cron 실행.

    감지·보고 전용. Slack 발송 없음 (WP-E 계약 보존).
    """
    supabase = get_supabase()
    result = await scan_stale_runs(supabase)
    log.info(
        "[qa_monitor_cron] stale scan 완료: queued=%d running=%d",
        len(result.get("queued_stale", [])),
        len(result.get("running_stale", [])),
    )
    return result
