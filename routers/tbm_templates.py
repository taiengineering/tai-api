"""
TBM 템플릿 업로더 — tbm_templates.py  v1.4.0

GET    /tbm-templates              템플릿 목록 (sort: popular|recent|name)
POST   /tbm-templates              템플릿 생성
GET    /tbm-templates/{id}         템플릿 상세
PATCH  /tbm-templates/{id}         템플릿 수정
DELETE /tbm-templates/{id}         템플릿 삭제 (soft delete)
POST   /tbm-templates/{id}/use     템플릿으로 TBM 실행 (tbm_meetings 생성)

DB: tbm_templates, tbm_meetings, tbm_attendees, groups, worker_group, worker_registry

v1.1.0 (2026-08-11): risk_items/safety_items 시드 정본 shape — RiskItem {description, ppe, precaution}, SafetyItem {description}.
v1.1.1 (2026-08-11): 시설(factory) 단위 스코핑.
v1.2.0 (2026-08-11): TBM 그룹화(Phase 2) — /use 에 group_id 지정 시 그룹원 자동 소집.
v1.3.0 (2026-08-11): 팀 템플릿 스코핑 — team_id 수용(생성) + 목록 필터.
           스코프 = 전역(factory·team null) / 시설(factory, team null) / 팀(team_id).
           team_id 지정 시: 팀 템플릿 + (팀 미지정 && (전역|해당 시설)). 미지정 시: 팀 템플릿 제외.
v1.4.0 (2026-08-20): 인증·회사 스코프 (Wave3, 직접MCP)
           - 전 엔드포인트 로그인 필수(get_current_user).
           - 목록: 비-ALL 은 전역 프리셋(company_id null) + 자사만.
           - 생성: require_company_id 로 비-ALL 은 토큰 company_id 강제, factory 지정 시 소유확인.
           - 상세/사용: 전역 프리셋은 허용, 그 외 자사만(_ensure_own_company).
           - 수정/삭제: 전역 프리셋은 ALL 전용, 그 외 자사만.
           - (미결) /use 의 group_id·team_id 교차회사 검증은 후속(그룹 소유확인) — 통지.
"""

import uuid
from datetime import datetime, date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
import os
from supabase import create_client

from routers.auth import get_current_user
from services.company_scope import (
    _scope,
    _is_admin,
    _require_admin,
    require_company_id,
    _ensure_own_company,
    _ensure_factory_own,
)

router = APIRouter(prefix="/tbm-templates", tags=["tbm-templates"])

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


def get_sb():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def _ensure_tbm_own_or_global(sb, template_id, current, *, write=False):
    """tbm_template 소유확인. 전역 프리셋(company_id null)은 조회/사용 허용, 수정/삭제(write)는 ALL 전용.
    반환: 템플릿 row(없으면 404)."""
    r = sb.table("tbm_templates").select("*").eq("id", template_id).eq("is_active", True).limit(1).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail="템플릿을 찾을 수 없습니다.")
    row = r.data[0]
    cid = row.get("company_id")
    if cid is None:
        if write:
            _require_admin(current, sb)   # 전역 프리셋 수정/삭제는 ALL 전용
    else:
        _ensure_own_company(cid, current, sb, "템플릿을 찾을 수 없습니다.")
    return row


# ── Pydantic 모델 ────────────────────────────

class RiskItem(BaseModel):
    """시드 정본 shape: 위험 내용(description) + 개인보호구(ppe) + 주의사항(precaution)."""
    id: Optional[str] = None
    description: str
    ppe: Optional[str] = None
    precaution: Optional[str] = None


class SafetyItem(BaseModel):
    """시드 정본 shape: 안전수칙 내용(description)."""
    id: Optional[str] = None
    description: str


class DefaultAttendee(BaseModel):
    name: str
    job_type: Optional[str] = None
    phone: Optional[str] = None


class TbmTemplateCreate(BaseModel):
    factory_id: Optional[str] = None
    team_id: Optional[str] = None
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
    group_id: Optional[str] = None         # 그룹 선택 시 그룹원 자동 소집
    team_id: Optional[str] = None          # 미지정 시 group 에서 유도


# ── 헬퍼 ────────────────────────────

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
        "team_id":          row.get("team_id"),
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


# ── GET /tbm-templates ─────────────────

@router.get("")
async def list_templates(
    factory_id: Optional[str] = Query(None),
    team_id: Optional[str] = Query(None),
    company_id: Optional[str] = Query(None),
    q: Optional[str] = Query(None, description="template_name 검색"),
    library: Optional[bool] = Query(None, description="True면 라이브러리 전용 레코드만"),
    sort: str = Query("popular", description="popular|recent|name"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current: dict = Depends(get_current_user),
):
    sb = get_sb()
    query = sb.table("tbm_templates").select(
        "id, template_name, factory_id, team_id, company_id, work_location, work_description, "
        "risk_items, safety_items, default_attendees, use_count, last_used_at, created_at, updated_at",
        count="exact"
    ).eq("is_active", True)

    if library is True:
        query = query.eq("template_name", "__LIBRARY__")
    elif library is False:
        query = query.neq("template_name", "__LIBRARY__")
    else:
        query = query.neq("template_name", "__LIBRARY__")

    # 스코핑: 전역(factory·team null) / 시설(factory, team null) / 팀(team_id)
    #   team_id 지정 → 팀 템플릿 + (팀 미지정 && (전역 프리셋 | 해당 시설))
    #   미지정      → 팀 템플릿 제외(team_id IS NULL) 후 (전역 | 해당 시설)
    if team_id:
        if factory_id:
            query = query.or_(
                f"team_id.eq.{team_id},"
                f"and(team_id.is.null,or(factory_id.is.null,factory_id.eq.{factory_id}))"
            )
        else:
            query = query.or_(f"team_id.eq.{team_id},and(team_id.is.null,factory_id.is.null)")
    else:
        query = query.filter("team_id", "is", "null")
        if factory_id:
            query = query.or_(f"factory_id.is.null,factory_id.eq.{factory_id}")
        else:
            query = query.filter("factory_id", "is", "null")

    # ── 회사 스코프 (P13): 비-ALL 은 전역 프리셋(company_id null) + 자사만 ──
    if not _is_admin(_scope(sb, current.get("role_code"))):
        cid = current.get("company_id")
        if cid:
            query = query.or_(f"company_id.is.null,company_id.eq.{cid}")
        else:
            query = query.filter("company_id", "is", "null")

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


# ── POST /tbm-templates ─────────────────

@router.post("")
async def create_template(body: TbmTemplateCreate, current: dict = Depends(get_current_user)):
    if not body.template_name.strip():
        raise HTTPException(status_code=422, detail="template_name은 필수입니다.")

    sb = get_sb()

    # ── 회사 스코프 강제 (P13): 비-ALL 은 토큰 company_id ──
    _forced = require_company_id(current, sb)
    if _forced:
        body.company_id = _forced
    if body.factory_id:
        _ensure_factory_own(sb, body.factory_id, current)

    data = {
        "template_name":    body.template_name.strip(),
        "factory_id":       body.factory_id,
        "team_id":          body.team_id,
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


# ── GET /tbm-templates/{id} ──────────────

@router.get("/{template_id}")
async def get_template(template_id: str, current: dict = Depends(get_current_user)):
    sb = get_sb()
    row = _ensure_tbm_own_or_global(sb, template_id, current)
    return {"status": "success", "data": row}


# ── PATCH /tbm-templates/{id} ───────────────

@router.patch("/{template_id}")
async def update_template(template_id: str, body: TbmTemplateUpdate, current: dict = Depends(get_current_user)):
    sb = get_sb()
    _ensure_tbm_own_or_global(sb, template_id, current, write=True)

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


# ── DELETE /tbm-templates/{id} ────────────────

@router.delete("/{template_id}")
async def delete_template(template_id: str, current: dict = Depends(get_current_user)):
    sb = get_sb()
    _ensure_tbm_own_or_global(sb, template_id, current, write=True)
    res = sb.table("tbm_templates").update({"is_active": False}).eq("id", template_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="템플릿을 찾을 수 없습니다.")
    return {"status": "success", "message": "템플릿이 삭제됐습니다."}


# ── POST /tbm-templates/{id}/use ────────────────

@router.post("/{template_id}/use")
async def use_template(template_id: str, body: TbmUseBody, current: dict = Depends(get_current_user)):
    """
    템플릿으로 TBM 실행:
    1. tbm_meetings 레코드 생성 (템플릿 내용 복사, group_id/team_id 기록)
    2. tbm_attendees 레코드 생성
       - group_id 지정 → 그룹원(worker_group) 자동 소집 (worker_id 연결)
       - 미지정        → 템플릿 default_attendees
    3. use_count += 1, last_used_at = now()
    """
    sb = get_sb()

    # 템플릿 조회 + 소유확인(전역 프리셋 허용)
    tmpl = _ensure_tbm_own_or_global(sb, template_id, current)

    # 날짜
    work_date_str = body.work_date or date.today().isoformat()

    # 그룹 지정 시: team_id 유도 + 그룹원 자동 소집
    group_id = body.group_id
    team_id = body.team_id or tmpl.get("team_id")
    group_members = []
    if group_id:
        if not body.team_id:
            g_res = sb.table("groups").select("team_id").eq("id", group_id).limit(1).execute()
            if g_res.data:
                team_id = g_res.data[0].get("team_id")
        wg_res = sb.table("worker_group").select(
            "worker_id, worker_registry(name, phone, job_type_name)"
        ).eq("group_id", group_id).execute()
        for row in (wg_res.data or []):
            w = row.get("worker_registry") or {}
            if not isinstance(w, dict):
                w = {}
            group_members.append({
                "worker_id": row.get("worker_id"),
                "name":      w.get("name", ""),
                "job_type":  w.get("job_type_name"),
                "phone":     w.get("phone"),
            })

    # 참석자: 그룹 지정 시 그룹원, 아니면 템플릿 default_attendees
    if group_members:
        attendee_src = group_members
    else:
        attendee_src = [
            {"worker_id": None, "name": a.get("name", ""), "job_type": a.get("job_type"), "phone": a.get("phone")}
            for a in (tmpl.get("default_attendees") or [])
        ]

    # tbm_meetings 생성
    meeting_data = {
        "factory_id":       tmpl.get("factory_id"),
        "company_id":       tmpl.get("company_id"),
        "group_id":         group_id,
        "team_id":          team_id,
        "meeting_title":    tmpl["template_name"],
        "work_date":        work_date_str,
        "work_location":    body.override_location or tmpl.get("work_location"),
        "work_description": body.override_description or tmpl.get("work_description"),
        "risk_items":       tmpl.get("risk_items", []),
        "safety_items":     tmpl.get("safety_items", []),
        "conductor_name":   body.conductor_name,
        "status_code":      "DRAFT",
        "attendee_count":   len(attendee_src),
    }
    m_res = sb.table("tbm_meetings").insert(meeting_data).execute()
    if not m_res.data:
        raise HTTPException(status_code=500, detail="TBM 생성 실패")
    meeting = m_res.data[0]
    meeting_id = meeting["id"]

    # tbm_attendees 생성
    if attendee_src:
        attendee_rows = [
            {
                "meeting_id":  meeting_id,
                "worker_id":   a.get("worker_id"),
                "name":        a.get("name", ""),
                "job_type":    a.get("job_type"),
                "phone":       a.get("phone"),
                "sign_status": "PENDING",
            }
            for a in attendee_src
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
            "meeting_id":     meeting_id,
            "template_name":  tmpl["template_name"],
            "work_date":      work_date_str,
            "group_id":       group_id,
            "team_id":        team_id,
            "attendee_count": len(attendee_src),
        }
    }
