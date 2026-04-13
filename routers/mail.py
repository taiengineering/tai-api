#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TAI 메일 관리 라우터 v2.0.0

v2.0.0:
  - POST /mail/send        첨부파일(multipart) 지원 (Supabase Storage 업로드 → Resend attachments)
  - POST /mail/reply/:id   답장
  - GET  /mail/:id         수신메일 html_body + attachments 완전 반환
  - GET  /mail/attachment/:mail_id/:filename  첨부파일 다운로드 (서명된 URL 리디렉트)
  - 인바운드 웹훅: html_body 저장 개선
"""

from fastapi import APIRouter, HTTPException, Query, Request, File, UploadFile, Form
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from typing import Optional, List
import os, json, uuid, base64
import resend as resend_client
import httpx

from db.supabase_client import get_supabase

router = APIRouter(prefix="/mail", tags=["메일관리"])

# ─── 설정 ────────────────────────────────────────────────────

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
resend_client.api_key = RESEND_API_KEY

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")  # service role key

ALLOWED_FROM = {
    "tai@taieng.co.kr":     "TAI Engineering <tai@taieng.co.kr>",
    "taiwang@taieng.co.kr": "TAI Engineering <taiwang@taieng.co.kr>",
    "contact@taieng.co.kr": "TAI Engineering <contact@taieng.co.kr>",
}
DEFAULT_FROM    = "tai@taieng.co.kr"
STORAGE_BUCKET  = "mail-attachments"
MAX_ATTACH_SIZE = 10 * 1024 * 1024  # 10MB


# ─── 첨부파일 헬퍼 ───────────────────────────────────────────

async def _upload_attachment(file: UploadFile, mail_id: str) -> dict:
    """Supabase Storage에 파일 업로드 후 메타정보 반환."""
    supabase = get_supabase()
    content = await file.read()
    if len(content) > MAX_ATTACH_SIZE:
        raise HTTPException(status_code=400, detail=f"{file.filename}: 파일 크기 초과 (최대 10MB)")

    safe_name = file.filename.replace(" ", "_") if file.filename else f"file_{uuid.uuid4().hex[:8]}"
    path = f"{mail_id}/{safe_name}"

    try:
        supabase.storage.from_(STORAGE_BUCKET).upload(
            path=path,
            file=content,
            file_options={"content-type": file.content_type or "application/octet-stream"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"첨부파일 업로드 실패: {e}")

    return {
        "name":         safe_name,
        "path":         path,
        "size":         len(content),
        "content_type": file.content_type or "application/octet-stream",
        "content_b64":  base64.b64encode(content).decode(),  # Resend 전송용
    }


def _build_resend_attachments(attach_metas: list) -> list:
    """Resend attachments 포맷 구성."""
    return [
        {"filename": a["name"], "content": a["content_b64"]}
        for a in attach_metas
    ]


def _strip_b64(attach_metas: list) -> list:
    """DB 저장 전 content_b64 제거 (용량 절약)."""
    return [
        {k: v for k, v in a.items() if k != "content_b64"}
        for a in attach_metas
    ]


# ─── 스키마 ──────────────────────────────────────────────────

class MailSendRequest(BaseModel):
    """JSON 방식 메일 발송 (첨부파일 없을 때)."""
    to:         List[str]
    cc:         Optional[List[str]] = None
    subject:    str
    html:       str
    from_email: Optional[str] = None
    sent_by:    Optional[str] = None


class BulkDeleteRequest(BaseModel):
    mail_ids: List[str]


# ─── POST /mail/send ─────────────────────────────────────────

@router.post("/send")
async def send_mail(
    to:         str         = Form(...,  description="수신자(콤마 구분 가능)"),
    cc:         Optional[str] = Form(None),
    subject:    str         = Form(...),
    html:       str         = Form(...),
    from_email: Optional[str] = Form(None),
    sent_by:    Optional[str] = Form(None),
    files:      List[UploadFile] = File(default=[]),
):
    """
    메일 발송 (첨부파일 지원, multipart/form-data).

    - to: 콤마로 구분된 수신자 목록
    - files: 첨부파일 (0~N개)
    """
    supabase = get_supabase()

    # 발신 주소 검증
    from_key = from_email or DEFAULT_FROM
    if from_key not in ALLOWED_FROM:
        raise HTTPException(status_code=400, detail=f"허용되지 않은 발신 주소: {from_key}")
    from_address = ALLOWED_FROM[from_key]

    # 수신자 파싱
    to_list = [e.strip() for e in to.split(",") if e.strip()]
    cc_list = [e.strip() for e in (cc or "").split(",") if e.strip()]

    # 임시 mail_id (저장 전 사용)
    mail_id = str(uuid.uuid4())

    # 첨부파일 업로드
    attach_metas = []
    for f in files:
        if f.filename:
            meta = await _upload_attachment(f, mail_id)
            attach_metas.append(meta)

    # Resend 파라미터
    send_params: dict = {
        "from":    from_address,
        "to":      to_list,
        "subject": subject,
        "html":    html,
    }
    if cc_list:
        send_params["cc"] = cc_list
    if attach_metas:
        send_params["attachments"] = _build_resend_attachments(attach_metas)

    # 발송
    resend_id: Optional[str] = None
    status = "sent"
    error_message: Optional[str] = None

    try:
        result = resend_client.Emails.send(send_params)
        resend_id = result.get("id") if isinstance(result, dict) else getattr(result, "id", None)
    except Exception as e:
        status = "failed"
        error_message = str(e)

    # DB 저장
    log_row = {
        "id":          mail_id,
        "to_emails":   to_list,
        "cc_emails":   cc_list,
        "subject":     subject,
        "html_body":   html,
        "status":      status,
        "resend_id":   resend_id,
        "error_message": error_message,
        "sent_by":     sent_by,
        "direction":   "outbound",
        "from_email":  from_key,
        "attachments": _strip_b64(attach_metas),
    }

    try:
        supabase.table("mail_logs").insert(log_row).execute()
    except Exception:
        pass

    if status == "failed":
        raise HTTPException(status_code=502, detail=f"메일 발송 실패: {error_message}")

    return {"success": True, "resend_id": resend_id, "mail_id": mail_id}


# ─── POST /mail/reply/:mail_id ───────────────────────────────

@router.post("/reply/{mail_id}")
async def reply_mail(
    mail_id:    str,
    to:         str            = Form(...),
    subject:    Optional[str]  = Form(None),
    html:       str            = Form(...),
    from_email: Optional[str]  = Form(None),
    sent_by:    Optional[str]  = Form(None),
    files:      List[UploadFile] = File(default=[]),
):
    """
    원본 메일에 답장.

    - subject: 없으면 원본 제목에 Re: 접두사 자동 추가
    - to: 답장 수신자 (보통 원본 발신자 이메일)
    """
    supabase = get_supabase()

    # 원본 메일 조회
    orig = supabase.table("mail_logs").select("*").eq("id", mail_id).single().execute()
    if not orig.data:
        raise HTTPException(status_code=404, detail="원본 메일을 찾을 수 없습니다.")
    original = orig.data

    # 제목 자동 설정
    orig_subject = original.get("subject", "")
    reply_subject = subject or (f"Re: {orig_subject}" if not orig_subject.startswith("Re:") else orig_subject)

    # 발신 주소
    from_key = from_email or DEFAULT_FROM
    if from_key not in ALLOWED_FROM:
        raise HTTPException(status_code=400, detail=f"허용되지 않은 발신 주소: {from_key}")
    from_address = ALLOWED_FROM[from_key]

    to_list = [e.strip() for e in to.split(",") if e.strip()]
    new_mail_id = str(uuid.uuid4())

    # 첨부파일
    attach_metas = []
    for f in files:
        if f.filename:
            meta = await _upload_attachment(f, new_mail_id)
            attach_metas.append(meta)

    # 원본 인용 HTML
    orig_html = original.get("html_body", "")
    reply_html = f"""
{html}
<br><br>
<div style="border-left:3px solid #ccc; padding-left:12px; color:#666; margin-top:16px;">
  <p><b>From:</b> {original.get('from_email','')}<br>
  <b>To:</b> {', '.join(original.get('to_emails',[]))}<br>
  <b>Subject:</b> {orig_subject}</p>
  <div>{orig_html}</div>
</div>
"""

    send_params: dict = {
        "from":    from_address,
        "to":      to_list,
        "subject": reply_subject,
        "html":    reply_html,
    }
    if attach_metas:
        send_params["attachments"] = _build_resend_attachments(attach_metas)

    # In-Reply-To 헤더 (있으면 추가)
    orig_resend_id = original.get("resend_id")
    if orig_resend_id:
        send_params["headers"] = {"In-Reply-To": f"<{orig_resend_id}>"}

    resend_id: Optional[str] = None
    status = "sent"
    error_message: Optional[str] = None

    try:
        result = resend_client.Emails.send(send_params)
        resend_id = result.get("id") if isinstance(result, dict) else getattr(result, "id", None)
    except Exception as e:
        status = "failed"
        error_message = str(e)

    log_row = {
        "id":          new_mail_id,
        "to_emails":   to_list,
        "cc_emails":   [],
        "subject":     reply_subject,
        "html_body":   reply_html,
        "status":      status,
        "resend_id":   resend_id,
        "error_message": error_message,
        "sent_by":     sent_by,
        "direction":   "outbound",
        "from_email":  from_key,
        "reply_to_id": mail_id,
        "in_reply_to": orig_resend_id,
        "attachments": _strip_b64(attach_metas),
    }

    try:
        supabase.table("mail_logs").insert(log_row).execute()
    except Exception:
        pass

    if status == "failed":
        raise HTTPException(status_code=502, detail=f"답장 발송 실패: {error_message}")

    return {"success": True, "resend_id": resend_id, "mail_id": new_mail_id}


# ─── GET /mail/attachment/:mail_id/:filename ─────────────────

@router.get("/attachment/{mail_id}/{filename}")
def download_attachment(mail_id: str, filename: str):
    """
    첨부파일 다운로드 (서명된 URL로 리디렉트).
    """
    supabase = get_supabase()
    path = f"{mail_id}/{filename}"

    try:
        res = supabase.storage.from_(STORAGE_BUCKET).create_signed_url(path, expires_in=3600)
        url = res.get("signedURL") or res.get("signed_url") or (res.get("data") or {}).get("signedUrl", "")
        if not url:
            raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
        return RedirectResponse(url=url)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"첨부파일 URL 생성 실패: {e}")


# ─── GET /mail/list ───────────────────────────────────────────

@router.get("/list")
def list_mails(
    direction: str           = Query(..., description="inbound / outbound"),
    page:      int           = Query(default=1, ge=1),
    size:      int           = Query(default=20, ge=1, le=100),
    status:    Optional[str] = Query(default=None),
    read:      Optional[bool]= Query(default=None),
    search:    Optional[str] = Query(default=None),
    from_date: Optional[str] = Query(default=None),
    to_date:   Optional[str] = Query(default=None),
):
    if direction not in ("inbound", "outbound"):
        raise HTTPException(status_code=400, detail="direction은 inbound 또는 outbound만 허용됩니다.")

    supabase = get_supabase()

    def _apply_filters(q):
        q = q.eq("direction", direction).eq("deleted", False)
        if status:   q = q.eq("status", status)
        if read is not None: q = q.eq("read", read)
        if search:   q = q.or_(f"subject.ilike.%{search}%")
        if from_date: q = q.gte("created_at", f"{from_date}T00:00:00")
        if to_date:   q = q.lte("created_at", f"{to_date}T23:59:59")
        return q

    total_res = _apply_filters(supabase.table("mail_logs").select("id", count="exact")).execute()
    total = total_res.count or 0

    offset = (page - 1) * size
    data_res = _apply_filters(
        supabase.table("mail_logs").select(
            "id, subject, from_email, to_emails, cc_emails, direction, status, "
            "read, deleted, attachments, reply_to_id, created_at"
        )
    ).order("created_at", desc=True).range(offset, offset + size - 1).execute()

    return {"items": data_res.data or [], "total": total, "page": page, "size": size}


# ─── GET /mail/unread-count ───────────────────────────────────

@router.get("/unread-count")
def get_unread_count():
    supabase = get_supabase()
    res = supabase.table("mail_logs").select("id", count="exact").eq(
        "direction", "inbound").eq("read", False).eq("deleted", False).execute()
    return {"unread_count": res.count or 0}


# ─── GET /mail/from-addresses ────────────────────────────────

@router.get("/from-addresses")
def get_from_addresses():
    return {"addresses": [
        {"email": e, "display_name": d} for e, d in ALLOWED_FROM.items()
    ]}


# ─── PATCH /mail/read-all ─────────────────────────────────────

@router.patch("/read-all")
def mark_all_as_read():
    supabase = get_supabase()
    supabase.table("mail_logs").update({"read": True}).eq(
        "direction", "inbound").eq("read", False).eq("deleted", False).execute()
    return {"success": True}


# ─── PATCH /mail/delete-bulk ──────────────────────────────────

@router.patch("/delete-bulk")
def delete_bulk(body: BulkDeleteRequest):
    if not body.mail_ids:
        raise HTTPException(status_code=400, detail="삭제할 메일 ID가 없습니다.")
    supabase = get_supabase()
    supabase.table("mail_logs").update({"deleted": True}).in_("id", body.mail_ids).execute()
    return {"success": True, "deleted_count": len(body.mail_ids)}


# ─── POST /mail/webhook/inbound ───────────────────────────────

@router.post("/webhook/inbound")
async def webhook_inbound(request: Request):
    """Resend 수신 웹훅 — html_body 완전 저장."""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="잘못된 요청 본문")

    event_type = payload.get("type", "")
    if event_type != "email.received":
        return {"ok": True, "skipped": True, "type": event_type}

    data       = payload.get("data", {})
    email_id   = data.get("email_id", "")
    from_email = data.get("from", "")
    to_emails  = data.get("to", [])
    if isinstance(to_emails, str): to_emails = [to_emails]
    cc_emails  = data.get("cc", [])
    if isinstance(cc_emails, str): cc_emails = [cc_emails]
    subject    = data.get("subject", "(제목 없음)")

    # Resend Received emails API로 본문 + 첨부파일 조회
    html_body   = ""
    attachments = []
    if email_id and RESEND_API_KEY:
        try:
            api_res = httpx.get(
                f"https://api.resend.com/emails/{email_id}",
                headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
                timeout=10,
            )
            if api_res.status_code == 200:
                detail = api_res.json()
                html_body = detail.get("html") or detail.get("text") or ""
                # 수신 첨부파일 메타 (Resend는 파일 URL 제공 안 함 - 메타만)
                for att in detail.get("attachments", []):
                    attachments.append({
                        "name":         att.get("filename", ""),
                        "content_type": att.get("content-type", ""),
                        "size":         att.get("size", 0),
                        "path":         "",  # 수신 첨부는 별도 저장 불가
                    })
        except Exception:
            html_body = "(본문 조회 실패)"

    supabase = get_supabase()
    log_row = {
        "from_email":  from_email,
        "to_emails":   to_emails,
        "cc_emails":   cc_emails,
        "subject":     subject,
        "html_body":   html_body,
        "resend_id":   email_id,
        "status":      "sent",
        "direction":   "inbound",
        "read":        False,
        "deleted":     False,
        "attachments": attachments,
    }

    try:
        supabase.table("mail_logs").insert(log_row).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"수신 메일 저장 실패: {e}")

    return {"success": True}


# ─── PATCH /mail/read/:id ─────────────────────────────────────

@router.patch("/read/{mail_id}")
def mark_as_read(mail_id: str):
    supabase = get_supabase()
    res = supabase.table("mail_logs").update({"read": True}).eq("id", mail_id).execute()
    if not res.data: raise HTTPException(status_code=404, detail="메일을 찾을 수 없습니다.")
    return {"success": True}


# ─── PATCH /mail/unread/:id ───────────────────────────────────

@router.patch("/unread/{mail_id}")
def mark_as_unread(mail_id: str):
    supabase = get_supabase()
    res = supabase.table("mail_logs").update({"read": False}).eq("id", mail_id).execute()
    if not res.data: raise HTTPException(status_code=404, detail="메일을 찾을 수 없습니다.")
    return {"success": True}


# ─── PATCH /mail/delete/:id ───────────────────────────────────

@router.patch("/delete/{mail_id}")
def soft_delete(mail_id: str):
    supabase = get_supabase()
    res = supabase.table("mail_logs").update({"deleted": True}).eq("id", mail_id).execute()
    if not res.data: raise HTTPException(status_code=404, detail="메일을 찾을 수 없습니다.")
    return {"success": True}


# ─── GET /mail/:id ────────────────────────────────────────────

@router.get("/{mail_id}")
def get_mail_detail(mail_id: str):
    """메일 상세 조회 — html_body + attachments 완전 반환, 수신 자동 읽음."""
    supabase = get_supabase()
    res = supabase.table("mail_logs").select("*").eq(
        "id", mail_id).eq("deleted", False).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="메일을 찾을 수 없습니다.")

    mail = res.data

    # 수신 메일 자동 읽음
    if mail.get("direction") == "inbound" and not mail.get("read"):
        supabase.table("mail_logs").update({"read": True}).eq("id", mail_id).execute()
        mail["read"] = True

    # html_body 없으면 Resend API 재조회
    if not mail.get("html_body") and mail.get("resend_id") and RESEND_API_KEY:
        try:
            api_res = httpx.get(
                f"https://api.resend.com/emails/{mail['resend_id']}",
                headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
                timeout=10,
            )
            if api_res.status_code == 200:
                detail = api_res.json()
                html_body = detail.get("html") or detail.get("text") or ""
                if html_body:
                    supabase.table("mail_logs").update({"html_body": html_body}).eq("id", mail_id).execute()
                    mail["html_body"] = html_body
        except Exception:
            pass

    return mail
