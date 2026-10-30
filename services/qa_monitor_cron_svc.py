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

# Cron 검사 시각 = Slot + _MONITOR_OFFSET_MINUTES
# (qa_workflow_monitor_svc._GRACE_MINUTES = 60 과 동기화)
_MONITOR_OFFSET_MINUTES = 60


def _is_slack_enabled() -> bool:
    """QA_MONITOR_SLACK_ENABLED=true 인 경우만 True."""
    return os.environ.get(_ENV_SLACK_ENABLED, "").strip().lower() == "true"


def _slot_from_scheduled_for(scheduled_for_utc: str) -> str:
    """scheduled_for (ISO 8601) 에서 감시 대상 Slot UTC ISO 를 역산.

    scheduled_for = Slot + _MONITOR_OFFSET_MINUTES
    → Slot = scheduled_for - _MONITOR_OFFSET_MINUTES
    """
    try:
        dt = datetime.fromisoformat(scheduled_for_utc.replace("Z", "+00:00"))
    except (ValueError, AttributeError) as exc:
        raise ValueError(
            f"scheduled_for 파싱 실패: {scheduled_for_utc!r}"
        ) from exc
    slot_dt = dt - timedelta(minutes=_MONITOR_OFFSET_MINUTES)
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
        try:
            scheduled_slot_utc = _slot_from_scheduled_for(scheduled_for)
        except ValueError as exc:
            log.warning("[qa_monitor_cron] scheduled_for 변환 실패: %s", exc)
            scheduled_slot_utc = None

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
            slot_utc   = monitor_result.get("slot_utc", "")
            status_code = monitor_result.get("status_code", "")
            dedupe_key  = f"{slot_utc}|{status_code}"
            slack_msg   = monitor_result.get("slack_message") or {}

            slack_payload: Dict[str, Any] = {
                "event_type": "QA_WORKFLOW_MONITOR_ALERT",
                "severity":   "WARNING",
                "title":      slack_msg.get("text", f"QA Workflow Monitor: {status_code}"),
                "detail":     f"slot={slot_utc} status={status_code}",
                "blocks":     slack_msg.get("blocks"),
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

    return {
        **monitor_result,
        "slack_enabled": slack_enabled,
        "outbox_status": outbox_status,
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
