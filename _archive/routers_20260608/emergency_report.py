"""
routers/emergency_report.py — v1.0.0
긴급 신고 엔드포인트

v1.0.0 (2026-04-24)
  POST /emergency/report — 긴급 신고 접수 + FCM 알림
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from db.supabase_client import get_supabase
from routers.auth import get_current_user

log = logging.getLogger(__name__)
router = APIRouter(prefix="/emergency", tags=["긴급신고"])

VALID_ACCIDENT_TYPES = {"fall", "fire", "pinch", "electric", "chem", "other"}


class EmergencyReportBody(BaseModel):
    phone: str
    worker_name: str
    accident_type: str
    accident_type_key: str  # fall|fire|pinch|electric|chem|other
    location: Optional[str] = None
    location_lat: Optional[float] = None
    location_lng: Optional[float] = None
    photo_urls: Optional[List[str]] = None


def _generate_report_number(supabase, prefix: str) -> str:
    """서버 발급 신고번호: {prefix}-{YYYYMMDD}-{SEQ}"""
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    pattern = f"{prefix}-{today}-%"

    res = supabase.table("emergency_reports") \
        .select("report_number") \
        .like("report_number", pattern) \
        .order("created_at", desc=True) \
        .limit(1).execute()

    seq = 1
    if res.data:
        last = res.data[0]["report_number"]
        try:
            seq = int(last.split("-")[-1]) + 1
        except ValueError:
            seq = 1

    return f"{prefix}-{today}-{seq:04d}"


@router.post("/report")
def create_emergency_report(
    body: EmergencyReportBody,
    current_user: dict = Depends(get_current_user),
):
    """긴급 신고 접수. 안전관리자에게 FCM 알림 발송."""
    supabase = get_supabase()
    now = datetime.now(timezone.utc).isoformat()

    if body.accident_type_key not in VALID_ACCIDENT_TYPES:
        raise HTTPException(status_code=400, detail=f"accident_type_key는 {VALID_ACCIDENT_TYPES} 중 하나여야 합니다")

    report_number = _generate_report_number(supabase, "EMG")

    row = {
        "report_number": report_number,
        "phone": body.phone.replace("-", "").replace(" ", ""),
        "worker_name": body.worker_name,
        "accident_type": body.accident_type,
        "accident_type_key": body.accident_type_key,
        "location": body.location,
        "location_lat": body.location_lat,
        "location_lng": body.location_lng,
        "photo_urls": body.photo_urls or [],
        "reporter_id": current_user.get("id"),
        "status": "RECEIVED",
        "created_at": now,
    }

    res = supabase.table("emergency_reports").insert(row).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="신고 저장 실패")

    report_id = res.data[0]["id"]

    # FCM 알림 — 안전관리자에게 발송
    notified_managers = []
    try:
        notified_managers = _notify_safety_managers(
            supabase, current_user, report_number, body.accident_type
        )
    except Exception as e:
        log.warning(f"[Emergency] FCM 발송 실패 (신고는 저장됨): {e}")

    return {
        "report_number": report_number,
        "id": report_id,
        "received_at": now,
        "notified_managers": notified_managers,
    }


def _notify_safety_managers(supabase, current_user: dict, report_number: str, accident_type: str) -> list:
    """현장/회사의 안전관리자에게 FCM 알림 발송."""
    company_id = current_user.get("company_id")
    if not company_id:
        return []

    # 안전관리자 조회 (role_code = SAFETY_MANAGER)
    mgrs = supabase.table("users") \
        .select("id, phone, push_token") \
        .eq("company_id", company_id) \
        .eq("role_code", "SAFETY_MANAGER") \
        .eq("is_active", True) \
        .execute()

    notified = []
    if not mgrs.data:
        return notified

    try:
        from utils.fcm_utils import send_push
    except Exception:
        return notified

    for mgr in mgrs.data:
        token = mgr.get("push_token")
        if not token:
            continue
        try:
            send_push(
                fcm_token=token,
                title="🚨 긴급신고 접수",
                body=f"[{report_number}] {accident_type}",
                data={"type": "emergency", "report_number": report_number, "accident_type": accident_type},
            )
            notified.append(mgr["id"])
        except Exception as e:
            log.warning(f"[Emergency] FCM 실패 manager={mgr['id']}: {e}")

    return notified
