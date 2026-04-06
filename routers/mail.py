#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TAI 메일 관리 라우터 (Resend + Supabase)

[메일 발송]
POST   /mail/send                  메일 발송 (Resend)

[메일 조회]
GET    /mail/list                  메일 목록 (방향별 필터, 페이지네이션)
GET    /mail/unread-count          수신 미읽음 건수 (뱃지용)
GET    /mail/from-addresses        발신 허용 주소 목록
GET    /mail/{mail_id}             메일 상세 조회 (수신메일 자동 읽음)

[메일 상태 변경]
PATCH  /mail/read/{mail_id}        읽음 처리
PATCH  /mail/unread/{mail_id}      미읽음 처리
PATCH  /mail/read-all              수신 전체 읽음 처리
PATCH  /mail/delete/{mail_id}      소프트 삭제
PATCH  /mail/delete-bulk           일괄 소프트 삭제

[웹훅]
POST   /mail/webhook/inbound       Resend 수신 웹훅
"""

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from typing import Optional
import os
import resend as resend_client

from db.supabase_client import get_supabase

router = APIRouter(prefix="/mail", tags=["메일관리"])

# ============================================================
# Resend 설정
# ============================================================

resend_client.api_key = os.environ.get("RESEND_API_KEY", "")

ALLOWED_FROM = {
    "tai@taieng.co.kr": "TAI Engineering <tai@taieng.co.kr>",
    "taiwang@taieng.co.kr": "TAI Engineering <taiwang@taieng.co.kr>",
    "contact@taieng.co.kr": "TAI Engineering <contact@taieng.co.kr>",
}
DEFAULT_FROM = "tai@taieng.co.kr"


# ============================================================
# 스키마
# ============================================================

class MailSendRequest(BaseModel):
    """메일 발송 요청 스키마"""
    to: list[str]
    cc: Optional[list[str]] = None
    subject: str
    html: str
    from_email: Optional[str] = None
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
    """수신 미읽음 건수 응답 스키마"""
    unread_count: int


class FromAddressItem(BaseModel):
    """발신 주소 항목"""
    email: str
    display_name: str


class FromAddressesResponse(BaseModel):
    """발신 허용 주소 목록 응답 스키마"""
    addresses: list[FromAddressItem]


class BulkDeleteRequest(BaseModel):
    """일괄 삭제 요청 스키마"""
    ids: list[str]


# ============================================================
# POST /mail/send — 메일 발송
# ============================================================

@router.post("/send", response_model=MailSendResponse)
def send_mail(body: MailSendRequest):
    """Resend를 통해 메일을 발송하고 mail_logs 테이블에 기록한다."""
    supabase = get_supabase()

    # 발신 주소 검증
    from_key = body.from_email or DEFAULT_FROM
    if from_key not in ALLOWED_FROM:
        raise HTTPException(
            status_code=400,
            detail=f"허용되지 않은 발신 주소입니다: {from_key}",
        )
    from_address = ALLOWED_FROM[from_key]

    # Resend 발송 파라미터 구성
    send_params: dict = {
        "from": from_address,
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
        "direction": "outbound",
        "from_email": from_key,
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
# GET /mail/list — 메일 목록 조회 (방향별)
# ============================================================

@router.get("/list", response_model=MailListResponse)
def list_mails(
    direction: str = Query(..., description="메일 방향 (inbound / outbound)"),
    page: int = Query(default=1, ge=1, description="페이지 번호"),
    size: int = Query(default=20, ge=1, le=100, description="페이지 크기"),
    status: Optional[str] = Query(default=None, description="발송 상태 필터 (sent / failed / pending)"),
    read: Optional[bool] = Query(default=None, description="읽음 여부 필터"),
    search: Optional[str] = Query(default=None, description="제목·수신자 검색"),
    from_date: Optional[str] = Query(default=None, description="시작일 (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(default=None, description="종료일 (YYYY-MM-DD)"),
):
    """메일 목록을 방향(inbound/outbound)별로 페이지네이션 조회한다."""
    if direction not in ("inbound", "outbound"):
        raise HTTPException(status_code=400, detail="direction은 inbound 또는 outbound만 허용됩니다.")

    supabase = get_supabase()

    # 전체 건수 조회용 쿼리
    count_query = supabase.table("mail_logs").select("id", count="exact")
    # 데이터 조회용 쿼리
    data_query = supabase.table("mail_logs").select("*")

    # 공통 필터: direction + deleted=false
    count_query = count_query.eq("direction", direction).eq("deleted", False)
    data_query = data_query.eq("direction", direction).eq("deleted", False)

    if status:
        count_query = count_query.eq("status", status)
        data_query = data_query.eq("status", status)

    if read is not None:
        count_query = count_query.eq("read", read)
        data_query = data_query.eq("read", read)

    if search:
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
# GET /mail/unread-count — 수신 미읽음 건수
# ============================================================

@router.get("/unread-count", response_model=UnreadCountResponse)
def get_unread_count():
    """수신(inbound) 미읽음 메일 건수를 반환한다 (뱃지 표시용)."""
    supabase = get_supabase()

    res = (
        supabase.table("mail_logs")
        .select("id", count="exact")
        .eq("direction", "inbound")
        .eq("read", False)
        .eq("deleted", False)
        .execute()
    )

    return UnreadCountResponse(unread_count=res.count if res.count is not None else 0)


# ============================================================
# GET /mail/from-addresses — 발신 허용 주소 목록
# ============================================================

@router.get("/from-addresses", response_model=FromAddressesResponse)
def get_from_addresses():
    """발신 허용 주소 목록을 반환한다."""
    addresses = [
        FromAddressItem(email=email, display_name=display)
        for email, display in ALLOWED_FROM.items()
    ]
    return FromAddressesResponse(addresses=addresses)


# ============================================================
# PATCH /mail/read-all — 수신 전체 읽음 처리
# ============================================================

@router.patch("/read-all")
def mark_all_as_read():
    """수신(inbound) 미읽음 메일을 모두 읽음 처리한다."""
    supabase = get_supabase()

    supabase.table("mail_logs").update({"read": True}).eq(
        "direction", "inbound"
    ).eq("read", False).eq("deleted", False).execute()

    return {"success": True}


# ============================================================
# PATCH /mail/delete-bulk — 일괄 소프트 삭제
# ============================================================

@router.patch("/delete-bulk")
def delete_bulk(body: BulkDeleteRequest):
    """여러 메일을 일괄 소프트 삭제한다."""
    if not body.ids:
        raise HTTPException(status_code=400, detail="삭제할 메일 ID가 없습니다.")

    supabase = get_supabase()

    supabase.table("mail_logs").update({"deleted": True}).in_(
        "id", body.ids
    ).execute()

    return {"success": True, "deleted_count": len(body.ids)}


# ============================================================
# POST /mail/webhook/inbound — Resend 수신 웹훅
# ============================================================

@router.post("/webhook/inbound")
async def webhook_inbound(request: Request):
    """Resend 수신 웹훅을 처리하여 mail_logs에 저장한다."""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="잘못된 요청 본문입니다.")

    # Resend inbound webhook 페이로드에서 필드 추출
    from_email = payload.get("from", "")
    to_emails = payload.get("to", [])
    if isinstance(to_emails, str):
        to_emails = [to_emails]
    subject = payload.get("subject", "(제목 없음)")
    html_body = payload.get("html", payload.get("text", ""))

    log_row = {
        "from_email": from_email,
        "to_emails": to_emails,
        "cc_emails": [],
        "subject": subject,
        "html_body": html_body,
        "status": "sent",
        "direction": "inbound",
        "read": False,
        "deleted": False,
    }

    supabase = get_supabase()

    try:
        supabase.table("mail_logs").insert(log_row).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"수신 메일 저장 실패: {str(e)}")

    return {"success": True}


# ============================================================
# PATCH /mail/read/{mail_id} — 읽음 처리
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
        raise HTTPException(status_code=404, detail="메일을 찾을 수 없습니다.")

    return {"success": True}


# ============================================================
# PATCH /mail/unread/{mail_id} — 미읽음 처리
# ============================================================

@router.patch("/unread/{mail_id}")
def mark_as_unread(mail_id: str):
    """메일을 미읽음 처리한다."""
    supabase = get_supabase()

    res = (
        supabase.table("mail_logs")
        .update({"read": False})
        .eq("id", mail_id)
        .execute()
    )

    if not res.data:
        raise HTTPException(status_code=404, detail="메일을 찾을 수 없습니다.")

    return {"success": True}


# ============================================================
# PATCH /mail/delete/{mail_id} — 소프트 삭제
# ============================================================

@router.patch("/delete/{mail_id}")
def soft_delete(mail_id: str):
    """메일을 소프트 삭제한다 (deleted=true)."""
    supabase = get_supabase()

    res = (
        supabase.table("mail_logs")
        .update({"deleted": True})
        .eq("id", mail_id)
        .execute()
    )

    if not res.data:
        raise HTTPException(status_code=404, detail="메일을 찾을 수 없습니다.")

    return {"success": True}


# ============================================================
# GET /mail/{mail_id} — 메일 상세 조회
# ============================================================

@router.get("/{mail_id}")
def get_mail_detail(mail_id: str):
    """메일 단건 상세 조회 (수신메일은 자동 읽음 처리)."""
    supabase = get_supabase()

    res = (
        supabase.table("mail_logs")
        .select("*")
        .eq("id", mail_id)
        .eq("deleted", False)
        .single()
        .execute()
    )

    if not res.data:
        raise HTTPException(status_code=404, detail="메일을 찾을 수 없습니다.")

    # 수신 메일 상세 조회 시 자동으로 읽음 처리
    if res.data.get("direction") == "inbound" and not res.data.get("read"):
        supabase.table("mail_logs").update({"read": True}).eq("id", mail_id).execute()
        res.data["read"] = True

    return res.data
