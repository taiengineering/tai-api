"""
공개 웹용 — 문의 접수(POST /contacts), FAQ 목록(GET /faqs)
관리자 FAQ: prefix /admin/site-faqs
"""
import re
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Header, Query
from pydantic import BaseModel, Field

from db.supabase_client import get_supabase

logger = logging.getLogger("site_public")
router = APIRouter(tags=["공개 웹"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_CATEGORY_LABEL = {
    "introduction": "TAI Safe 도입",
    "diagnosis": "법령진단 문의",
    "tech": "기술지원",
    "partner": "제휴·파트너",
    "etc": "기타 문의",
}


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html or "").replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", text).strip()


# ── POST /contacts → inquiries 저장 + Slack(#tai-ops) 알림 ──────────

class PublicContactBody(BaseModel):
    name: str = Field(..., min_length=1)
    email: str = Field(..., min_length=3)
    content: str = Field(..., min_length=1)
    category: Optional[str] = None
    title: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    company_name: Optional[str] = None   # 구 필드 호환
    inquiry_type: Optional[str] = None   # 구 필드 호환
    source: Optional[str] = "marketing"
    page_url: Optional[str] = None


@router.post("/contacts")
def submit_public_contact(body: PublicContactBody):
    """공개 문의 접수 → inquiries 저장 + Slack 알림"""
    supabase = get_supabase()
    category = (body.category or body.inquiry_type or "").strip() or None
    company = (body.company or body.company_name or "").strip() or None
    row = {
        "name": body.name.strip(),
        "email": body.email.strip(),
        "phone": (body.phone or "").strip() or None,
        "company": company,
        "category": category,
        "title": (body.title or "").strip() or None,
        "content": body.content.strip(),
        "source": (body.source or "marketing").strip(),
        "page_url": (body.page_url or "").strip() or None,
        "inquiry_type": "INQUIRY",
        "is_member": False,
        "created_at": _now(),
        "updated_at": _now(),
    }
    try:
        res = supabase.table("inquiries").insert(row).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"저장 실패: {e!s}")

    saved = res.data[0] if res.data else row

    try:
        from services.slack_dispatcher import ops
        cat_label = _CATEGORY_LABEL.get(category, category or "문의")
        plain = _strip_html(body.content)
        detail = (
            f"분야: {cat_label}\n"
            f"성함: {row['name']} / 회사: {company or '-'}\n"
            f"연락처: {row['phone'] or '-'} / 이메일: {row['email']}\n"
            f"제목: {row['title'] or '-'}\n"
            f"내용: {plain[:800]}"
        )
        ops(f"새 문의 접수 · {cat_label} · {row['name']}", detail)
    except Exception:
        logger.exception("contact slack notify failed")

    return {"status": "success", "data": saved}


# ── GET /faqs ─────────────────────────────────────────────────────

@router.get("/faqs")
def list_public_faqs():
    """게시된 FAQ 목록 (공개, 인증 불필요)"""
    supabase = get_supabase()
    try:
        res = (
            supabase.table("site_faqs")
            .select("id, question, answer, sort_order")
            .eq("is_published", True)
            .order("sort_order", desc=False)
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "success", "data": {"items": res.data or []}}


# ── 관리자 FAQ CRUD /admin/site-faqs (Bearer 권장) ────────────────

admin_router = APIRouter(prefix="/admin/site-faqs", tags=["관리 - 공개 FAQ"])


class FaqCreate(BaseModel):
    question: str = Field(..., min_length=1)
    answer: str = Field(..., min_length=1)
    sort_order: int = 0
    is_published: bool = True


class FaqUpdate(BaseModel):
    question: Optional[str] = None
    answer: Optional[str] = None
    sort_order: Optional[int] = None
    is_published: Optional[bool] = None


def _require_bearer(authorization: Optional[str]):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")


@admin_router.get("")
def admin_list_faqs(
    authorization: Optional[str] = Header(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
):
    _require_bearer(authorization)
    supabase = get_supabase()
    offset = (page - 1) * size
    res = (
        supabase.table("site_faqs")
        .select("*", count="exact")
        .order("sort_order")
        .range(offset, offset + size - 1)
        .execute()
    )
    return {
        "status": "success",
        "data": {
            "items": res.data or [],
            "total": res.count or 0,
            "page": page,
            "size": size,
        },
    }


@admin_router.post("")
def admin_create_faq(body: FaqCreate, authorization: Optional[str] = Header(None)):
    _require_bearer(authorization)
    supabase = get_supabase()
    now = _now()
    row = {
        "question": body.question.strip(),
        "answer": body.answer.strip(),
        "sort_order": body.sort_order,
        "is_published": body.is_published,
        "created_at": now,
        "updated_at": now,
    }
    res = supabase.table("site_faqs").insert(row).execute()
    return {"status": "success", "data": res.data[0] if res.data else {}}


@admin_router.patch("/{faq_id}")
def admin_patch_faq(
    faq_id: str,
    body: FaqUpdate,
    authorization: Optional[str] = Header(None),
):
    _require_bearer(authorization)
    supabase = get_supabase()
    raw = body.model_dump(exclude_unset=True) if hasattr(body, "model_dump") else body.dict(exclude_unset=True)
    patch = {k: v for k, v in raw.items() if v is not None}
    if not patch:
        raise HTTPException(status_code=400, detail="변경할 필드가 없습니다.")
    patch["updated_at"] = _now()
    res = supabase.table("site_faqs").update(patch).eq("id", faq_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="FAQ를 찾을 수 없습니다.")
    return {"status": "success", "data": res.data[0]}


@admin_router.delete("/{faq_id}")
def admin_delete_faq(faq_id: str, authorization: Optional[str] = Header(None)):
    _require_bearer(authorization)
    supabase = get_supabase()
    res = supabase.table("site_faqs").delete().eq("id", faq_id).execute()
    return {"status": "success", "deleted": bool(res.data)}
