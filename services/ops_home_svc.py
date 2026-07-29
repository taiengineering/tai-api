"""관제홈 운영 대시보드 서비스 (WO-13 OpsHome).

Goal: G-ms4je4z3-33eada (운영 보강 G-ms5pdquz-9e76e5)
- 기존 집계 재사용(신규 집계 없음). 1인 운영자의 "오늘 처리할 일" 요약.
- action_queue(처리 대기) + alerts(이상 신호) + today(오늘의 숫자).
- 각 소스 오류 격리: 한 소스 실패해도 나머지 반환.
- 결제 상태 코드(system_codes payment_status): PENDING/SUCCESS/FAILED/CANCELLED.
  입금대기 = payment_method='VBANK' AND status_code='PENDING' AND vbank_confirmed_at IS NULL.

[2026-07-29] 메일 발송 실패 지표 보정:
  기존에는 전체 기간·삭제분 포함으로 누적 집계되어(과거 Resend 도메인 미인증 실패 245건 등)
  이미 해소된 문제가 '이상 신호'에 영구히 남았다. 미읽음 메일 집계처럼 deleted=false 를 적용하고,
  '지금 조치가 필요한 신호'라는 성격에 맞게 최근 MAIL_FAIL_WINDOW_DAYS 일로 한정한다.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from db.supabase_client import get_supabase

log = logging.getLogger(__name__)

# 이상 신호로 볼 메일 발송 실패의 관측 기간(일).
MAIL_FAIL_WINDOW_DAYS = 7


def _today_start_iso() -> str:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def _days_ago_iso(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _count(table: str, build) -> int:
    try:
        q = get_supabase().table(table).select("id", count="exact")
        q = build(q)
        return q.execute().count or 0
    except Exception as e:  # noqa: BLE001
        log.warning("[OPS-HOME] count 실패 %s: %s", table, e)
        return 0


def action_queue() -> Dict[str, Any]:
    """처리 대기 큐."""
    approval_pending = _count("automation_run_log",
                              lambda q: q.eq("status", "APPROVAL_PENDING"))
    unread_mail = _count("mail_logs",
                         lambda q: q.eq("direction", "inbound").eq("read", False).eq("deleted", False))
    # 입금 대기: 가상계좌 결제 중 미입금(PENDING + 미확인)
    vbank_waiting = _count("payments",
                           lambda q: q.eq("payment_method", "VBANK")
                                       .eq("status_code", "PENDING")
                                       .is_("vbank_confirmed_at", "null"))
    return {
        "approval_pending": approval_pending,
        "unread_inbound_mail": unread_mail,
        "vbank_waiting": vbank_waiting,
        "total": approval_pending + unread_mail + vbank_waiting,
    }


def alerts() -> Dict[str, Any]:
    """이상 신호."""
    # 필수 연동 미설정
    critical_missing = []
    try:
        from services.integration_health_svc import get_health
        critical_missing = get_health().get("core_critical_missing", [])
    except Exception as e:  # noqa: BLE001
        log.warning("[OPS-HOME] integration health 실패: %s", e)

    # 최근 N일 + 미삭제 발송 실패만 이상 신호로 본다(과거 누적분 제외).
    since = _days_ago_iso(MAIL_FAIL_WINDOW_DAYS)
    mail_failed = _count("mail_logs",
                         lambda q: q.eq("direction", "outbound")
                                     .eq("status", "failed")
                                     .eq("deleted", False)
                                     .gte("created_at", since))

    return {
        "core_critical_missing": critical_missing,
        "core_critical_missing_count": len(critical_missing),
        "mail_send_failed": mail_failed,
        "mail_send_failed_window_days": MAIL_FAIL_WINDOW_DAYS,
    }


def today() -> Dict[str, Any]:
    """오늘의 숫자 + 자산 통계(재사용)."""
    start = _today_start_iso()
    new_companies = _count("companies", lambda q: q.gte("created_at", start).is_("deleted_at", "null"))
    new_users = _count("users", lambda q: q.gte("created_at", start).is_("deleted_at", "null"))
    new_payments = _count("payments", lambda q: q.gte("created_at", start))

    # 자산 통계(dashboard_stats MV 재사용)
    assets: Dict[str, Any] = {}
    try:
        res = get_supabase().table("dashboard_stats").select("*").limit(1).execute()
        if res.data:
            d = res.data[0]
            assets = {
                "total_companies": d.get("total_companies", 0),
                "total_factories": d.get("total_factories", 0),
                "active_contracts": d.get("active_contracts", 0),
                "total_users": d.get("total_users", 0),
            }
    except Exception as e:  # noqa: BLE001
        log.warning("[OPS-HOME] dashboard_stats 실패: %s", e)

    return {
        "new_companies": new_companies,
        "new_users": new_users,
        "new_payments": new_payments,
        "assets": assets,
    }


def get_home() -> Dict[str, Any]:
    """관제홈 종합."""
    return {
        "action_queue": action_queue(),
        "alerts": alerts(),
        "today": today(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
