#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TAI 메일 관리 라우터 (Resend 연동)

[메일 발송]
POST   /mail/send               메일 발송 (Resend)

[메일 조회]
GET    /mail/list                발송 목록 (페이지네이션)
GET    /mail/unread-count        최근 24시간 발송 건수
GET    /mail/{mail_id}           메일 상세 조회
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta, timezone
import os
import resend as resend_client

from db.supabase_client import get_supabase

router = APIRouter(prefix="/mail", tags=["메일관리"])

# ============================================================
# Resend 설정
# ============================================================

resend_client.api_key = os.environ.get("RESEND_API_KEY", "")

FROM_ADDRESS = "TAI Engineering <noreply@taieng.co.kr>"


# ============================================================
# 스키마
# ============================================================

class MailSendRequest(BaseModel):
    """메일 발송 요청 스키마"""
    to: list[str]
    cc: Optional[list[str]] = None
    subject: str
    html: str
    sent_by: Optional[str] = None


class MailSendResponse(BaseModel):
    """메일 발송 응답 스키마"""
    success: bool
    resend_id: Optional[str] = None


class MailListResponse(BaseModel):
    """메일 목록 응답 스키마"""
    items: list[dict]
    total: int
    page: int
    size: int


class UnreadCountResponse(BaseModel):
    """미확인 메일 건수 응답 스키마"""
    unread_count: int


# ============================================================
# POST /mail/send — 메일 발송
# ============================================================

@router.post("/send", response_model=MailSendResponse)
def send_mail(body: MailSendRequest):
    """Resend를 통해 메일을 발송하고 mail_logs 테이블에 기록한다."""
    supabase = get_supabase()

    # Resend 발송 파라미터 구성
    send_params: dict = {
        "from": FROM_ADDRESS,
        "to": body.to,
        "subject": body.subject,
        "html": body.html,
    }
    if body.cc:
        send_params["cc"] = body.cc

    # 발송 시도
    resend_id: Optional[str] = None
    status = "sent"
    error_message: Optional[str] = None

    try:
        result = resend_client.Emails.send(send_params)
        resend_id = result.get("id") if isinstance(result, dict) else getattr(result, "id", None)
    except Exception as e:
        status = "failed"
        error_message = str(e)

    # mail_logs 테이블에 로그 기록
    log_row = {
        "to_emails": body.to,
        "cc_emails": body.cc or [],
        "subject": body.subject,
        "html_body": body.html,
        "status": status,
        "resend_id": resend_id,
        "error_message": error_message,
        "sent_by": body.sent_by,
    }

    try:
        supabase.table("mail_logs").insert(log_row).execute()
    except Exception:
        # 로그 저장 실패는 발송 결과에 영향 없음
        pass

    if status == "failed":
        raise HTTPException(status_code=502, detail=f"메일 발송 실패: {error_message}")

    return MailSendResponse(success=True, resend_id=resend_id)


# ============================================================
# GET /mail/list — 발송 목록 조회
# ============================================================

@router.get("/list", response_model=MailListResponse)
def list_mails(
    page: int = Query(default=1, ge=1, description="페이지 번호"),
    size: int = Query(default=20, ge=1, le=100, description="페이지 크기"),
    status: Optional[str] = Query(default=None, description="발송 상태 필터 (sent / failed)"),
    search: Optional[str] = Query(default=None, description="제목·수신자 검색"),
    from_date: Optional[str] = Query(default=None, description="시작일 (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(default=None, description="종료일 (YYYY-MM-DD)"),
):
    """발송된 메일 목록을 페이지네이션으로 조회한다."""
    supabase = get_supabase()

    # 전체 건수 조회용 쿼리
    count_query = supabase.table("mail_logs").select("id", count="exact")
    # 데이터 조회용 쿼리
    data_query = supabase.table("mail_logs").select("*")

    # 필터 적용
    if status:
        count_query = count_query.eq("status", status)
        data_query = data_query.eq("status", status)

    if search:
        # subject ILIKE 검색
        filter_str = f"subject.ilike.%{search}%"
        count_query = count_query.or_(filter_str)
        data_query = data_query.or_(filter_str)

    if from_date:
        count_query = count_query.gte("created_at", f"{from_date}T00:00:00")
        data_query = data_query.gte("created_at", f"{from_date}T00:00:00")

    if to_date:
        count_query = count_query.lte("created_at", f"{to_date}T23:59:59")
        data_query = data_query.lte("created_at", f"{to_date}T23:59:59")

    # 전체 건수
    count_res = count_query.execute()
    total = count_res.count if count_res.count is not None else 0

    # 페이지네이션 + 정렬
    offset = (page - 1) * size
    data_res = (
        data_query
        .order("created_at", desc=True)
        .range(offset, offset + size - 1)
        .execute()
    )

    return MailListResponse(
        items=data_res.data or [],
        total=total,
        page=page,
        size=size,
    )


# ============================================================
# GET /mail/unread-count — 안 읽은 메일 건수
# ============================================================

@router.get("/unread-count", response_model=UnreadCountResponse)
def get_unread_count():
    """안 읽은 메일 건수를 반환한다 (뱃지 표시용)."""
    supabase = get_supabase()

    res = (
        supabase.table("mail_logs")
        .select("id", count="exact")
        .eq("read", False)
        .execute()
    )

    return UnreadCountResponse(unread_count=res.count if res.count is not None else 0)


# ============================================================
# PATCH /mail/read/{mail_id} — 메일 읽음 처리
# ============================================================

@router.patch("/read/{mail_id}")
def mark_as_read(mail_id: str):
    """메일을 읽음 처리한다."""
    supabase = get_supabase()

    res = (
        supabase.table("mail_logs")
        .update({"read": True})
        .eq("id", mail_id)
        .execute()
    )

    if not res.data:
        raise HTTPException(status_code=404, detail="메일 로그를 찾을 수 없습니다.")

    return {"success": True}


# ============================================================
# PATCH /mail/read-all — 전체 읽음 처리
# ============================================================

@router.patch("/read-all")
def mark_all_as_read():
    """안 읽은 메일을 모두 읽음 처리한다."""
    supabase = get_supabase()

    supabase.table("mail_logs").update({"read": True}).eq("read", False).execute()

    return {"success": True}


# ============================================================
# GET /mail/{mail_id} — 메일 상세 조회
# ============================================================

@router.get("/{mail_id}")
def get_mail_detail(mail_id: str):
    """메일 로그 단건 상세 조회 (자동 읽음 처리)."""
    supabase = get_supabase()

    res = (
        supabase.table("mail_logs")
        .select("*")
        .eq("id", mail_id)
        .single()
        .execute()
    )

    if not res.data:
        raise HTTPException(status_code=404, detail="메일 로그를 찾을 수 없습니다.")

    # 상세 조회 시 자동으로 읽음 처리
    if not res.data.get("read"):
        supabase.table("mail_logs").update({"read": True}).eq("id", mail_id).execute()

    return res.data
