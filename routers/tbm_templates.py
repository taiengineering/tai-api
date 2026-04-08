"""
TBM 템플릿 업로더 — tbm_templates.py  v1.0.0

GET    /tbm-templates              템플릿 목록 (sort: popular|recent|name)
POST   /tbm-templates              템플릿 생성
GET    /tbm-templates/{id}         템플릿 상세
PATCH  /tbm-templates/{id}         템플릿 수정
DELETE /tbm-templates/{id}         템플릿 삭제 (soft delete)
POST   /tbm-templates/{id}/use     템플릿으로 TBM 실행 (tbm_meetings 생성)

DB: tbm_templates, tbm_meetings, tbm_attendees
"""

import uuid
from datetime import datetime, date
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
import os
from supabase import create_client

router = APIRouter(prefix="/tbm-templates", tags=["tbm-templates"])

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


def get_sb():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ── Pydantic 모델 ───────────────────────────────────────

class RiskItem(BaseModel):
    id: Optional[str] = None
    content: str
    category: str = "기타"  # 전도|협착|충돌|추락|낙하|폭발|화재|질식|감전|기타


class SafetyItem(BaseModel):
    id: Optional[str] = None
    content: str


class DefaultAttendee(BaseModel):
    name: str
    job_type: Optional[str] = None
    phone: Optional[str] = None


class TbmTemplateCreate(BaseModel):
    factory_id: Optional[str] = None
    company_id: Optional[str] = None
    template_name: str
    work_location: Optional[str] = None
    work_description: Optional[str] = None
    risk_items: List[RiskItem] = []
    safety_items: List[SafetyItem] = []
    default_attendees: List[DefaultAttendee] = []


class TbmTemplateUpdate(BaseModel):
    template_name: Optional[str] = None
    work_location: Optional[str] = None
    work_description: Optional[str] = None
    risk_items: Optional[List[RiskItem]] = None
    safety_items: Optional[List[SafetyItem]] = None
    default_attendees: Optional[List[DefaultAttendee]] = None


class TbmUseBody(BaseModel):
    work_date: Optional[str] = None        # YYYY-MM-DD, 없으면 today
    conductor_name: Optional[str] = None
    override_location: Optional[str] = None
    override_description: Optional[str] = None


# ── 헬퍼 ───────────────────────────────────────

def _ensure_ids(items: list) -> list:
    """아이템 id 없으면 uuid 자동 부여"""
    result = []
    for item in items:
        d = item.dict() if hasattr(item, 'dict') else dict(item)
        if not d.get('id'):
            d['id'] = str(uuid.uuid4())
        result.append(d)
    return result


def _summary(row: dict) -> dict:
    """risk_items/safety_items/default_attendees 수 대신 count로 리턴"""
    return {
        "id":               row["id"],
        "template_name":    row["template_name"],
        "factory_id":       row.get("factory_id"),
        "company_id":       row.get("company_id"),
        "work_location":    row.get("work_location"),
        "work_description": row.get("work_description"),
        "risk_count":       len(row.get("risk_items") or []),
        "safety_count":     len(row.get("safety_items") or []),
        "attendee_count":   len(row.get("default_attendees") or []),
        "use_count":        row.get("use_count", 0),
        "last_used_at":     row.get("last_used_at"),
        "created_at":       row.get("created_at"),
        "updated_at":       row.get("updated_at"),
    }


# ── GET /tbm-templates ─────────────────────────────

@router.get("")
async def list_templates(
    factory_id: Optional[str] = Query(None),
    company_id: Optional[str] = Query(None),
    q: Optional[str] = Query(None, description="template_name 검색"),
    library: Optional[bool] = Query(None, description="True면 라이브러리 전용 레코드만"),
    sort: str = Query("popular", description="popular|recent|name"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    sb = get_sb()
    query = sb.table("tbm_templates").select(
        "id, template_name, factory_id, company_id, work_location, work_description, "
        "risk_items, safety_items, default_attendees, use_count, last_used_at, created_at, updated_at",
        count="exact"
    ).eq("is_active", True)

    if library is True:
        query = query.eq("template_name", "__LIBRARY__")
    elif library is False:
        query = query.neq("template_name", "__LIBRARY__")
    else:
        query = query.neq("template_name", "__LIBRARY__")

    if factory_id:
        query = query.eq("factory_id", factory_id)
    if company_id:
        query = query.eq("company_id", company_id)
    if q:
        query = query.ilike("template_name", f"%{q}%")

    if sort == "popular":
        query = query.order("use_count", desc=True).order("updated_at", desc=True)
    elif sort == "recent":
        query = query.order("updated_at", desc=True)
    else:
        query = query.order("template_name")

    offset = (page - 1) * size
    res = query.range(offset, offset + size - 1).execute()

    items = [_summary(r) for r in (res.data or [])]
    total = res.count or 0

    return {
        "status": "success",
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "page_size": size,
            "total_pages": (total + size - 1) // size if total else 0,
        }
    }


# ── POST /tbm-templates ─────────────────────────────

@router.post("")
async def create_template(body: TbmTemplateCreate):
    if not body.template_name.strip():
        raise HTTPException(status_code=422, detail="template_name은 필수입니다.")

    sb = get_sb()
    data = {
        "template_name":    body.template_name.strip(),
        "factory_id":       body.factory_id,
        "company_id":       body.company_id,
        "work_location":    body.work_location,
        "work_description": body.work_description,
        "risk_items":       _ensure_ids(body.risk_items),
        "safety_items":     _ensure_ids(body.safety_items),
        "default_attendees": [a.dict() for a in body.default_attendees],
        "use_count":        0,
        "is_active":        True,
    }

    res = sb.table("tbm_templates").insert(data).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="템플릿 생성 실패")

    return {"status": "success", "message": "템플릿이 생성됐습니다.", "data": _summary(res.data[0])}


# ── GET /tbm-templates/{id} ────────────────────────

@router.get("/{template_id}")
async def get_template(template_id: str):
    sb = get_sb()
    res = sb.table("tbm_templates").select("*").eq("id", template_id).eq("is_active", True).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="템플릿을 찾을 수 없습니다.")
    return {"status": "success", "data": res.data[0]}


# ── PATCH /tbm-templates/{id} ───────────────────────

@router.patch("/{template_id}")
async def update_template(template_id: str, body: TbmTemplateUpdate):
    sb = get_sb()

    update: dict = {"updated_at": datetime.utcnow().isoformat()}
    if body.template_name is not None:
        update["template_name"] = body.template_name.strip()
    if body.work_location is not None:
        update["work_location"] = body.work_location
    if body.work_description is not None:
        update["work_description"] = body.work_description
    if body.risk_items is not None:
        update["risk_items"] = _ensure_ids(body.risk_items)
    if body.safety_items is not None:
        update["safety_items"] = _ensure_ids(body.safety_items)
    if body.default_attendees is not None:
        update["default_attendees"] = [a.dict() for a in body.default_attendees]

    if len(update) == 1:  # updated_at만
        raise HTTPException(status_code=422, detail="수정할 내용이 없습니다.")

    res = sb.table("tbm_templates").update(update).eq("id", template_id).eq("is_active", True).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="템플릿을 찾을 수 없습니다.")

    return {"status": "success", "message": "템플릿이 수정됐습니다.", "data": _summary(res.data[0])}


# ── DELETE /tbm-templates/{id} ──────────────────────

@router.delete("/{template_id}")
async def delete_template(template_id: str):
    sb = get_sb()
    res = sb.table("tbm_templates").update({"is_active": False}).eq("id", template_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="템플릿을 찾을 수 없습니다.")
    return {"status": "success", "message": "템플릿이 삭제됐습니다."}


# ── POST /tbm-templates/{id}/use ────────────────────

@router.post("/{template_id}/use")
async def use_template(template_id: str, body: TbmUseBody):
    """
    템플릿으로 TBM 실행:
    1. tbm_meetings 레코드 생성 (템플릿 내용 복사)
    2. tbm_attendees 레코드 생성 (default_attendees 기반)
    3. use_count += 1, last_used_at = now()
    """
    sb = get_sb()

    # 템플릿 조회
    t_res = sb.table("tbm_templates").select("*").eq("id", template_id).eq("is_active", True).limit(1).execute()
    if not t_res.data:
        raise HTTPException(status_code=404, detail="템플릿을 찾을 수 없습니다.")
    tmpl = t_res.data[0]

    # 날짜
    work_date_str = body.work_date or date.today().isoformat()

    # tbm_meetings 생성
    meeting_data = {
        "factory_id":       tmpl.get("factory_id"),
        "company_id":       tmpl.get("company_id"),
        "meeting_title":    tmpl["template_name"],
        "work_date":        work_date_str,
        "work_location":    body.override_location or tmpl.get("work_location"),
        "work_description": body.override_description or tmpl.get("work_description"),
        "risk_items":       tmpl.get("risk_items", []),
        "safety_items":     tmpl.get("safety_items", []),
        "conductor_name":   body.conductor_name,
        "status_code":      "DRAFT",
        "attendee_count":   len(tmpl.get("default_attendees") or []),
    }
    m_res = sb.table("tbm_meetings").insert(meeting_data).execute()
    if not m_res.data:
        raise HTTPException(status_code=500, detail="TBM 생성 실패")
    meeting = m_res.data[0]
    meeting_id = meeting["id"]

    # tbm_attendees 생성 (default_attendees 기반)
    attendees = tmpl.get("default_attendees") or []
    if attendees:
        attendee_rows = [
            {
                "meeting_id":  meeting_id,
                "name":        a.get("name", ""),
                "job_type":    a.get("job_type"),
                "phone":       a.get("phone"),
                "sign_status": "PENDING",
            }
            for a in attendees
        ]
        sb.table("tbm_attendees").insert(attendee_rows).execute()

    # use_count +1, last_used_at 업데이트
    sb.table("tbm_templates").update({
        "use_count":    (tmpl.get("use_count") or 0) + 1,
        "last_used_at": datetime.utcnow().isoformat(),
        "updated_at":   datetime.utcnow().isoformat(),
    }).eq("id", template_id).execute()

    return {
        "status":  "success",
        "message": "TBM이 생성됐습니다.",
        "data": {
            "meeting_id":    meeting_id,
            "template_name": tmpl["template_name"],
            "work_date":     work_date_str,
            "attendee_count": len(attendees),
        }
    }
