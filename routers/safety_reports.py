"""
routers/safety_reports.py — v1.0.0
이상신고 엔드포인트

v1.0.0 (2026-04-24)
  POST /safety-reports — 이상신고 접수 (photos→photo_urls)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from db.supabase_client import get_supabase
from routers.auth import get_current_user

log = logging.getLogger(__name__)
router = APIRouter(tags=["이상신고"])

VALID_REPORT_TYPES = {"설비이상", "환경위험", "신체이상", "작업방법이상"}
VALID_URGENCIES = {"normal", "urgent", "critical"}


class SafetyReportBody(BaseModel):
    phone: str
    worker_id: Optional[str] = None
    factory_id: Optional[str] = None
    site_id: Optional[str] = None
    report_type: str
    description: str
    urgency: str = "normal"
    location_lat: Optional[float] = None
    location_lng: Optional[float] = None
    location_text: Optional[str] = None
    photo_urls: Optional[List[str]] = None
    submitted_at: Optional[str] = None

    @field_validator("description")
    @classmethod
    def check_description_length(cls, v: str) -> str:
        if len(v.strip()) < 10:
            raise ValueError("description은 최소 10자 이상이어야 합니다")
        return v.strip()


def _generate_report_number(supabase, prefix: str, table: str) -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    pattern = f"{prefix}-{today}-%"

    res = supabase.table(table) \
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


@router.post("/safety-reports")
def create_safety_report(
    body: SafetyReportBody,
    current_user: dict = Depends(get_current_user),
):
    """이상신고 접수. urgency=critical이면 FCM 알림."""
    supabase = get_supabase()
    now = datetime.now(timezone.utc).isoformat()

    if body.report_type not in VALID_REPORT_TYPES:
        raise HTTPException(status_code=400, detail=f"report_type는 {VALID_REPORT_TYPES} 중 하나여야 합니다")
    if body.urgency not in VALID_URGENCIES:
        raise HTTPException(status_code=400, detail=f"urgency는 {VALID_URGENCIES} 중 하나여야 합니다")

    report_number = _generate_report_number(supabase, "RPT", "safety_reports")

    row = {
        "report_number": report_number,
        "phone": body.phone.replace("-", "").replace(" ", ""),
        "worker_id": body.worker_id or current_user.get("id"),
        "factory_id": body.factory_id,
        "site_id": body.site_id,
        "report_type": body.report_type,
        "description": body.description,
        "urgency": body.urgency,
        "location_lat": body.location_lat,
        "location_lng": body.location_lng,
        "location_text": body.location_text,
        "photo_urls": body.photo_urls or [],
        "reporter_id": current_user.get("id"),
        "status": "RECEIVED",
        "created_at": now,
    }

    res = supabase.table("safety_reports").insert(row).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="신고 저장 실패")

    report_id = res.data[0]["id"]

    # critical urgency → FCM 알림
    if body.urgency == "critical":
        try:
            _notify_critical(supabase, current_user, report_number, body.report_type)
        except Exception as e:
            log.warning(f"[SafetyReport] FCM 발송 실패 (신고는 저장됨): {e}")

    return {
        "report_number": report_number,
        "id": report_id,
        "received_at": now,
    }


def _notify_critical(supabase, current_user: dict, report_number: str, report_type: str):
    company_id = current_user.get("company_id")
    if not company_id:
        return

    mgrs = supabase.table("users") \
        .select("id, push_token") \
        .eq("company_id", company_id) \
        .eq("role_code", "SAFETY_MANAGER") \
        .eq("is_active", True) \
        .execute()

    if not mgrs.data:
        return

    try:
        from utils.fcm_utils import send_push
    except Exception:
        return

    for mgr in mgrs.data:
        token = mgr.get("push_token")
        if not token:
            continue
        try:
            send_push(
                fcm_token=token,
                title="⚠️ 긴급 이상신고",
                body=f"[{report_number}] {report_type}",
                data={"type": "safety_report", "report_number": report_number},
            )
        except Exception as e:
            log.warning(f"[SafetyReport] FCM 실패 manager={mgr['id']}: {e}")
