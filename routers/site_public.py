"""
공개 웹용 — 문의 접수(POST /contacts), FAQ 목록(GET /faqs)
관리자 FAQ: prefix /admin/site-faqs
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Header, Query
from pydantic import BaseModel, Field

from db.supabase_client import get_supabase

router = APIRouter(tags=["공개 웹"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── POST /contacts (기존 프론트 사이트와 동일 URL·필드) ─────────────

class PublicContactBody(BaseModel):
    name: str = Field(..., min_length=1)
    company_name: Optional[str] = None
    email: str = Field(..., min_length=3)
    phone: Optional[str] = None
    inquiry_type: str = Field(..., min_length=1)
    content: str = Field(..., min_length=10)
    source: Optional[str] = "nexas.taieng.co.kr"


@router.post("/contacts")
def submit_public_contact(body: PublicContactBody):
    """공개 문의 접수 → site_contact_leads"""
    supabase = get_supabase()
    row = {
        "name": body.name.strip(),
        "company_name": (body.company_name or "").strip() or None,
        "email": body.email.strip(),
        "phone": (body.phone or "").strip() or None,
        "inquiry_type": body.inquiry_type.strip(),
        "content": body.content.strip(),
        "source": (body.source or "nexas.taieng.co.kr").strip(),
        "created_at": _now(),
    }
    try:
        res = supabase.table("site_contact_leads").insert(row).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"저장 실패: {e!s}")
    return {"status": "success", "data": res.data[0] if res.data else row}


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
