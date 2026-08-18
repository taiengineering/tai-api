#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TAI 알림 시스템 라우터
전역변수: notification_priority / notification_group / notification_channel / notification_status

[알림 설정] - 총관리자 전용
GET    /notification-settings              트리거별 설정 목록
PATCH  /notification-settings/{trigger}   트리거 설정 수정

[알림 수신]
GET    /notifications                      알림 목록
GET    /notifications/unread-count         미읽은 알림 수
POST   /notifications/trigger-due-alerts  D-0/D-3/D-7 마감 알림 생성 (크론용)
PATCH  /notifications/{id}/read           단건 읽음 처리
PATCH  /notifications/read-all            전체 읽음 처리
DELETE /notifications/{id}                알림 삭제

[알림 발송] - 내부/시스템용
POST   /notifications/send                알림 발송
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, date, timedelta
from db.supabase_client import get_supabase

router = APIRouter(tags=["notifications"])


# ============================================================
# 스키마
# ============================================================

class NotificationSettingUpdate(BaseModel):
    channel_email:  Optional[bool] = None
    channel_kakao:  Optional[bool] = None
    channel_push:   Optional[bool] = None
    channel_site:   Optional[bool] = None
    email_subject:  Optional[str] = None
    email_body:     Optional[str] = None
    kakao_template: Optional[str] = None
    sms_template:   Optional[str] = None
    site_title:     Optional[str] = None
    site_body:      Optional[str] = None

class NotificationSend(BaseModel):
    trigger_code: str
    company_id:   Optional[str] = None
    user_id:      Optional[str] = None
    title:        str
    body:         Optional[str] = None
    link_url:     Optional[str] = None
    priority:     str = "INFO"        # notification_priority 전역변수
    channel:      str = "SITE"        # notification_channel 전역변수


# ============================================================
# 알림 설정 API (총관리자 전용)
# ============================================================

@router.get("/notification-settings")
def get_notification_settings(
    trigger_group: Optional[str] = Query(default=None)  # notification_group 전역변수
):
    """트리거별 알림 설정 목록"""
    supabase = get_supabase()
    query = supabase.table("notification_settings")\
        .select("*")\
        .eq("is_active", True)

    if trigger_group:
        query = query.eq("trigger_group", trigger_group)

    res = query.order("trigger_group").order("created_at").execute()

    # 그룹별 정리
    grouped = {}
    for item in (res.data or []):
        g = item["trigger_group"]
        if g not in grouped:
            grouped[g] = []
        grouped[g].append(item)

    return {"status": "success", "data": grouped}


@router.patch("/notification-settings/{trigger_code}")
def update_notification_setting(trigger_code: str, req: NotificationSettingUpdate):
    """트리거 알림 설정 수정 (총관리자 전용)"""
    supabase = get_supabase()

    existing = supabase.table("notification_settings")\
        .select("id").eq("trigger_code", trigger_code).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="트리거를 찾을 수 없습니다")

    update_data = {k: v for k, v in req.dict().items() if v is not None}
    update_data["updated_at"] = datetime.now().isoformat()

    res = supabase.table("notification_settings")\
        .update(update_data).eq("trigger_code", trigger_code).execute()

    return {"status": "success", "message": "알림 설정이 저장되었습니다", "data": res.data[0] if res.data else {}}


# ============================================================
# 알림 수신 API
# ============================================================

@router.get("/notifications")
def get_notifications(
    page:          int  = Query(default=1, ge=1),
    size:          int  = Query(default=20, ge=1, le=100),
    user_id:       Optional[str] = Query(default=None),
    worker_id:     Optional[str] = Query(default=None),
    phone:         Optional[str] = Query(default=None),
    company_id:    Optional[str] = Query(default=None),
    trigger_group: Optional[str] = Query(default=None),
    is_read:       Optional[bool] = Query(default=None),
    priority:      Optional[str] = Query(default=None),
    # [23] 화면(notification-list)이 보내는 별칭 파라미터 — 기존 파라미터와 하위호환.
    #   기존 trigger_group/is_read/size 는 그대로 두고, 화면이 쓰는 type/read/limit/from/to 를 수용한다.
    type_:         Optional[str]  = Query(default=None, alias="type"),   # → trigger_group
    read:          Optional[bool] = Query(default=None),                 # → is_read
    limit:         Optional[int]  = Query(default=None, ge=1, le=100),   # → size
    date_from:     Optional[str]  = Query(default=None, alias="from"),   # created_at >=
    date_to:       Optional[str]  = Query(default=None, alias="to"),     # created_at <=
    # ⚠ factory_id 는 notifications 테이블에 컬럼이 없어 서버가 필터할 수 없다(미지원, 무시).
    #   시설 축 필터가 필요하면 스키마/매핑 결정이 선행돼야 한다(별건).
):
    """알림 목록 조회 (worker_id, phone 파라미터 추가)"""
    supabase = get_supabase()

    # [23] 별칭 병합 — 별칭이 오면 채택하되 기존 파라미터를 우선 유지(하위호환).
    if not trigger_group and type_:
        trigger_group = type_
    if is_read is None and read is not None:
        is_read = read
    if limit is not None:
        size = limit

    # phone → user_id 변환
    resolved_user_id = user_id
    if not resolved_user_id and phone:
        clean = phone.replace("-", "").replace(" ", "")
        u = supabase.table("users").select("id").eq("phone", clean).limit(1).execute()
        if not u.data:
            fmt = f"{clean[:3]}-{clean[3:7]}-{clean[7:]}"
            u = supabase.table("users").select("id").eq("phone", fmt).limit(1).execute()
        if u.data:
            resolved_user_id = u.data[0]["id"]
    if not resolved_user_id and worker_id:
        resolved_user_id = worker_id

    query = supabase.table("notifications").select("*", count="exact")

    if resolved_user_id: query = query.eq("user_id", resolved_user_id)
    if company_id:       query = query.eq("company_id", company_id)
    if trigger_group:    query = query.eq("trigger_group", trigger_group)
    if is_read is not None: query = query.eq("is_read", is_read)
    if priority:         query = query.eq("priority", priority)
    # [23] 기간 필터 (created_at) — 화면 from/to
    if date_from:        query = query.gte("created_at", date_from)
    if date_to:          query = query.lte("created_at", date_to)

    offset = (page - 1) * size
    res = query.order("created_at", desc=True)\
               .range(offset, offset + size - 1).execute()

    return {
        "status": "success",
        "data": {
            "items":       res.data,
            "total":       res.count,
            "page":        page,
            "size":        size,
            "total_pages": -(-res.count // size) if res.count else 0,
        }
    }


@router.get("/notifications/unread-count")
def get_unread_count(
    user_id:    Optional[str] = Query(default=None),
    company_id: Optional[str] = Query(default=None),
):
    """미읽은 알림 수 조회 (탑바 댜지용)"""
    supabase = get_supabase()
    query = supabase.table("notifications")\
        .select("id", count="exact")\
        .eq("is_read", False)\
        .eq("channel", "SITE")

    if user_id:    query = query.eq("user_id", user_id)
    if company_id: query = query.eq("company_id", company_id)

    res = query.execute()
    count = res.count or 0

    return {
        "status": "success",
        "data": {
            "count":       count,
            "display":     "99+" if count > 99 else str(count),
            "has_unread":  count > 0,
        }
    }


# ============================================================
# POST /notifications/trigger-due-alerts
# 주의: /{notification_id}/read 엔드포인트보다 앞에 선언해야 라우트 충돌 없음
# ============================================================

@router.post("/notifications/trigger-due-alerts")
def trigger_due_alerts():
    """
    D-0 / D-3 / D-7 기준 work_schedules 마감 알림 생성.
    매일 오전 8시 크론(DUE_ALERT_DAILY)으로 호출.

    로직:
    1. 오늘+0/+3/+7 planned_date인 PENDING+active_yn=True 일정 조회
    2. 동일 link_url + label 중복이면 스킵
    3. notifications INSERT (trigger_code='DUE_ALERT', channel='SITE')
    4. 생성 건수 반환

    실제 콸럼: notifications에는 factory_id/schedule_id/due_days/is_sent 콘럼이 없음
    → link_url에 schedule_id 임베드, title에 label 포함하여 중복 판정
    """
    supabase = get_supabase()
    today = date.today()
    now   = datetime.now()

    DUE_TARGETS = [
        (0, "D-0",   "HIGH"),
        (3, "D-3",   "HIGH"),
        (7, "D-7",   "NORMAL"),
    ]
    total_created = 0
    total_skipped = 0

    for days, label, priority in DUE_TARGETS:
        target_date = today + timedelta(days=days)

        # 해당 마감일 PENDING 일정 조회
        sched_res = (
            supabase.table("work_schedules")
            .select("id, factory_id, company_id, assigned_user_id, description, obligation_type, law_name")
            .eq("planned_date", target_date.isoformat())
            .eq("status_code", "PENDING")
            .eq("active_yn", True)
            .execute()
        )

        for sched in (sched_res.data or []):
            sched_id = sched["id"]
            link_url = f"/work-schedules/{sched_id}"

            # 중복 체크: 동일 schedule link_url + label이 이미 있으면 스킵
            dup = (
                supabase.table("notifications")
                .select("id", count="exact")
                .eq("trigger_code", "DUE_ALERT")
                .eq("link_url", link_url)
                .ilike("title", f"%{label}%")
                .execute()
            )
            if dup.count and dup.count > 0:
                total_skipped += 1
                continue

            desc  = (sched.get("description") or "점검 일정").strip()
            law   = sched.get("law_name") or ""
            title = f"점검 마감 알림 ({label})"
            body  = desc
            if law:
                body += f"\n법령: {law}"
            body += f"\n마감: {target_date} ({label})"

            supabase.table("notifications").insert({
                "company_id":    sched.get("company_id"),
                "user_id":       sched.get("assigned_user_id"),
                "trigger_code":  "DUE_ALERT",
                "trigger_group": "SCHEDULE",
                "title":         title,
                "body":          body,
                "link_url":      link_url,
                "priority":      priority,
                "channel":       "SITE",
                "is_read":       False,
                "send_status":   "SUCCESS",
                "sent_at":       now.isoformat(),
                "created_at":    now.isoformat(),
            }).execute()
            total_created += 1

    return {
        "status": "success",
        "data": {
            "created": total_created,
            "skipped": total_skipped,
            "checked_dates": [
                (today + timedelta(days=d)).isoformat() for d in (0, 3, 7)
            ],
        },
    }


# ============================================================
# PATCH /notifications/{notification_id}/read
# 주의: trigger-due-alerts보다 나중에 선언해야 함
# ============================================================

@router.patch("/notifications/{notification_id}/read")
def mark_as_read(notification_id: str):
    """단건 읽음 처리"""
    supabase = get_supabase()

    existing = supabase.table("notifications")\
        .select("id").eq("id", notification_id).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="알림을 찾을 수 없습니다")

    supabase.table("notifications").update({
        "is_read": True,
        "read_at": datetime.now().isoformat(),
    }).eq("id", notification_id).execute()

    return {"status": "success", "message": "읽음 처리되었습니다"}


@router.patch("/notifications/read-all")
def mark_all_read(
    user_id:    Optional[str] = Query(default=None),
    company_id: Optional[str] = Query(default=None),
):
    """전체 읽음 처리"""
    supabase = get_supabase()
    query = supabase.table("notifications")\
        .update({"is_read": True, "read_at": datetime.now().isoformat()})\
        .eq("is_read", False)

    if user_id:    query = query.eq("user_id", user_id)
    if company_id: query = query.eq("company_id", company_id)

    query.execute()
    return {"status": "success", "message": "전체 읽음 처리되었습니다"}


@router.delete("/notifications/{notification_id}")
def delete_notification(notification_id: str):
    """알림 삭제"""
    supabase = get_supabase()

    existing = supabase.table("notifications")\
        .select("id").eq("id", notification_id).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="알림을 찾을 수 없습니다")

    supabase.table("notifications").delete().eq("id", notification_id).execute()
    return {"status": "success", "message": "알림이 삭제되었습니다"}


# ============================================================
# 알림 발송 API (내부/시스템용)
# ============================================================

@router.post("/notifications/send")
def send_notification(req: NotificationSend):
    """
    알림 발송
    - 트리거 설정 확인 → 체널별 발송 여부 결정
    - 현재: 사이트 알림만 저장 (이메일/카카오/Push는 추후 연동)
    """
    supabase = get_supabase()

    # 트리거 설정 조회
    setting = supabase.table("notification_settings")\
        .select("*")\
        .eq("trigger_code", req.trigger_code)\
        .eq("is_active", True)\
        .limit(1).execute()

    now = datetime.now()
    results = []

    # 사이트 알림 저장 (즉시 사용 가능)
    if not setting.data or setting.data[0].get("channel_site", True):
        res = supabase.table("notifications").insert({
            "company_id":   req.company_id,
            "user_id":      req.user_id,
            "trigger_code": req.trigger_code,
            "trigger_group": setting.data[0]["trigger_group"] if setting.data else "SYSTEM",
            "title":        req.title,
            "body":         req.body,
            "link_url":     req.link_url,
            "priority":     req.priority,
            "channel":      "SITE",
            "is_read":      False,
            "send_status":  "SUCCESS",
            "sent_at":      now.isoformat(),
            "created_at":   now.isoformat(),
        }).execute()
        results.append({"channel": "SITE", "status": "SUCCESS"})

    if setting.data and setting.data[0].get("channel_email"):
        results.append({"channel": "EMAIL", "status": "PENDING"})

    if setting.data and setting.data[0].get("channel_kakao"):
        results.append({"channel": "KAKAO", "status": "DISABLED"})

    if setting.data and setting.data[0].get("channel_push"):
        results.append({"channel": "PUSH", "status": "DISABLED"})

    return {
        "status":  "success",
        "message": "알림이 발송되었습니다",
        "data":    results,
    }


# ============================================================
# 알림 발송 헬퍼 함수 (다른 라우터에서 호출용)
# ============================================================

def create_notification(
    supabase,
    trigger_code: str,
    title: str,
    body: str = "",
    company_id: str = None,
    user_id: str = None,
    link_url: str = None,
    priority: str = "INFO",
):
    """
    다른 라우터에서 알림 생성 시 호출
    예) contracts.py에서 서비스 활성화 시 알림 발송
    """
    try:
        supabase.table("notifications").insert({
            "company_id":   company_id,
            "user_id":      user_id,
            "trigger_code": trigger_code,
            "title":        title,
            "body":         body,
            "link_url":     link_url,
            "priority":     priority,
            "channel":      "SITE",
            "is_read":      False,
            "send_status":  "SUCCESS",
            "sent_at":      datetime.now().isoformat(),
            "created_at":   datetime.now().isoformat(),
        }).execute()
    except Exception as e:
        print(f"알림 생성 실패: {e}")
