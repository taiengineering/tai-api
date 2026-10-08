"""routers/admin_law_updates.py — OBJ-LAU-05B 60% Admin API

GET  /admin/law-updates                    — case list
GET  /admin/law-updates/{case_id}          — case detail
POST /admin/law-updates/{case_id}/notify-slack — send LAW_REVISION_COLLECTED Slack

인증: get_current_user + _require_admin.
Source DB: LEG_SUPABASE_URL + LEG_SUPABASE_SERVICE_ROLE_KEY.
DB write = 0 (notify-slack updates Slack timestamps only).
"""
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services.company_scope import _require_admin

log = logging.getLogger("admin_law_updates")

router = APIRouter(prefix="/admin/law-updates", tags=["admin-law-updates"])

_leg_client = None


def _get_leg_client():
    global _leg_client
    if _leg_client is None:
        from supabase import create_client
        url = os.environ.get("LEG_SUPABASE_URL")
        key = os.environ.get("LEG_SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            raise RuntimeError(
                "LEG_SUPABASE_URL and LEG_SUPABASE_SERVICE_ROLE_KEY required "
                "for admin-law-updates endpoints"
            )
        _leg_client = create_client(url, key)
    return _leg_client


_LIST_SELECT = (
    "case_id,law_name,law_id,law_api_id,event_type,"
    "old_mst,new_mst,announcement_date,enforcement_date,"
    "application_status,development_alert_code,last_safe_stage,"
    "detected_at,created_at,updated_at"
)

_DETAIL_SELECT = (
    "case_id,law_name,law_id,law_api_id,event_type,"
    "old_mst,new_mst,old_version_id,new_version_id,"
    "detected_mst_no,detected_raw_hash,detected_at,"
    "announcement_date,enforcement_date,revision_type,"
    "application_status,development_alert_code,last_safe_stage,resume_stage,"
    "slack_collected_notified_at,slack_collected_message_ts,"
    "last_slack_alert_code,last_slack_alert_at,"
    "created_at,updated_at"
)


@router.get("")
def list_cases(
    application_status: Optional[str] = Query(None),
    law_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current: dict = Depends(get_current_user),
):
    """법령 갱신 케이스 목록.

    법령명·저장상태·검색일 등 요약 정보 반환.
    """
    supabase = get_supabase()
    _require_admin(current, supabase)
    leg = _get_leg_client()
    q = (
        leg.table("law_update_case")
        .select(_LIST_SELECT)
        .order("created_at", desc=True)
        .limit(limit)
        .offset(offset)
    )
    if application_status:
        q = q.eq("application_status", application_status)
    if law_id:
        q = q.eq("law_id", law_id)
    res = q.execute()
    return {"status": "success", "data": res.data or [], "count": len(res.data or [])}


@router.get("/{case_id}")
def get_case(
    case_id: str,
    current: dict = Depends(get_current_user),
):
    """법령 갱신 케이스 상세.

    상태·실패사유·version_id·Slack 전송 기록 포함.
    """
    supabase = get_supabase()
    _require_admin(current, supabase)
    leg = _get_leg_client()
    res = (
        leg.table("law_update_case")
        .select(_DETAIL_SELECT)
        .eq("case_id", case_id)
        .execute()
    )
    rows = res.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="case not found")
    return {"status": "success", "data": rows[0]}


@router.post("/{case_id}/notify-slack")
def notify_slack(
    case_id: str,
    current: dict = Depends(get_current_user),
):
    """COLLECTED 케이스에 LAW_REVISION_COLLECTED Slack 알림 전송.

    이미 전송됐으면 sent=false / detail=ALREADY_NOTIFIED.
    Slack 실패 시 저장 상태 영향 없음.
    채널 미설정(LAW_UPDATE_SLACK_TEST_CHANNEL) 시 sent=false.
    """
    supabase = get_supabase()
    _require_admin(current, supabase)
    leg = _get_leg_client()
    res = (
        leg.table("law_update_case")
        .select(_DETAIL_SELECT)
        .eq("case_id", case_id)
        .execute()
    )
    rows = res.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="case not found")

    from services.law_update_slack import notify_collected
    sent, detail = notify_collected(case_id, rows[0], leg)
    return {"status": "success", "sent": sent, "detail": detail}
