"""
점검 템플릿 CRUD 라우터 — v1.1.0
v1.1.0 (2026-08-20): 인증·회사 스코프 (Wave3, 직접MCP)
  - 전 엔드포인트 로그인 필수(get_current_user).
  - detail/{id}·{id}/items·DELETE → 템플릿 소유확인(_ensure_template_own).
  - GET /{factory_id}·POST → 시설 소유확인(_ensure_factory_own).
v1.0.0: 점검항목 수동 입력 신규
  - GET  /safety-templates/detail/{id}  (항목 포함 상세) — /{factory_id} 보다 먼저 선언
  - GET  /safety-templates/{factory_id} (목록 + item_count)
  - POST /safety-templates              (템플릿+항목 일괄 생성)
  - POST /safety-templates/{id}/items   (항목 추가)
  - DELETE /safety-templates/{id}/items/{item_id} (항목 soft delete)
  - DELETE /safety-templates/{id}       (템플릿 soft delete)
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services.company_scope import _ensure_own_company, _ensure_factory_own

router = APIRouter(prefix="/safety-templates", tags=["safety-templates"])

VERSION = "1.1.0"


def _ensure_template_own(sb, template_id, current):
    """safety_template 소유확인(행 company_id). 없으면/타사면 404."""
    r = sb.table("safety_templates").select("id, company_id").eq("id", template_id).limit(1).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail="템플릿을 찾을 수 없습니다.")
    _ensure_own_company(r.data[0].get("company_id"), current, sb, "템플릿을 찾을 수 없습니다.")


# ── Pydantic 모델 ────────────────────────────

class TemplateItemBody(BaseModel):
    item_name:      str
    item_type:      str = "text"   # text / boolean / numeric / photo / select
    sort_order:     int = 0
    is_required:    bool = False
    standard_value: Optional[str] = None  # 기준값 (예: '0.5MPa 이하')
    check_method:   Optional[str] = None  # 육안 / 계측 / 작동테스트
    cycle:          Optional[str] = None  # daily / weekly / monthly / quarterly / yearly
    risk_level:     Optional[str] = None  # HIGH / MEDIUM / LOW


class TemplateCreateBody(BaseModel):
    factory_id:    str
    template_name: str
    description:   Optional[str] = None
    items:         List[TemplateItemBody] = []


class TemplateUpdateBody(BaseModel):
    template_name: Optional[str] = None
    description:   Optional[str] = None


# ══════════════════════════════════════════════
# GET /safety-templates/detail/{template_id}
# 라우팅 충돌 방지: /{factory_id} 보다 반드시 먼저 선언
# ══════════════════════════════════════════════

@router.get("/detail/{template_id}")
async def get_template_detail(template_id: str, current: dict = Depends(get_current_user)):
    """템플릿 상세 + 항목 목록 포함."""
    supabase = get_supabase()

    t_res = supabase.table("safety_templates").select("*").eq(
        "id", template_id
    ).limit(1).execute()
    if not t_res.data:
        raise HTTPException(status_code=404, detail="템플릿을 찾을 수 없습니다.")

    t = t_res.data[0]
    # ── 회사 소유확인 (P13) ──
    _ensure_own_company(t.get("company_id"), current, supabase, "템플릿을 찾을 수 없습니다.")

    items_res = supabase.table("safety_template_items").select("*").eq(
        "template_id", template_id
    ).eq("is_active", True).order("sort_order").execute()
    t["items"] = items_res.data or []

    return {"status": "success", "data": t}


# ══════════════════════════════════════════════
# GET /safety-templates/{factory_id}
# ══════════════════════════════════════════════

@router.get("/{factory_id}")
async def list_templates(factory_id: str, current: dict = Depends(get_current_user)):
    """시설별 템플릿 목록 (item_count 포함)."""
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)

    res = supabase.table("safety_templates").select(
        "id, template_name, description, source, is_active, created_at"
    ).eq("factory_id", factory_id).eq("is_active", True).order(
        "created_at", desc=True
    ).execute()

    templates = res.data or []
    for t in templates:
        cnt_res = supabase.table("safety_template_items").select(
            "id", count="exact"
        ).eq("template_id", t["id"]).eq("is_active", True).limit(0).execute()
        t["item_count"] = cnt_res.count or 0

    return {"status": "success", "data": templates}


# ══════════════════════════════════════════════
# POST /safety-templates
# ══════════════════════════════════════════════

@router.post("")
async def create_template(body: TemplateCreateBody, current: dict = Depends(get_current_user)):
    """템플릿 + 항목 일괄 생성."""
    supabase = get_supabase()

    if not (body.template_name or "").strip():
        raise HTTPException(status_code=422, detail="템플릿명은 필수입니다.")

    # ── 시설 소유확인 (P13) ──
    _ensure_factory_own(supabase, body.factory_id, current)

    # 시설의 company_id 조회
    fac_res = supabase.table("factories").select("company_id").eq(
        "id", body.factory_id
    ).limit(1).execute()
    company_id = (fac_res.data[0].get("company_id") if fac_res.data else None)

    # 템플릿 INSERT
    tpl_res = supabase.table("safety_templates").insert({
        "factory_id":    body.factory_id,
        "company_id":    company_id,
        "template_name": body.template_name.strip(),
        "description":   body.description,
        "source":        "MANUAL",
        "is_active":     True,
    }).execute()
    if not tpl_res.data:
        raise HTTPException(status_code=500, detail="템플릿 생성 실패")

    template_id = tpl_res.data[0]["id"]

    # 항목 INSERT (배치)
    item_count = 0
    if body.items:
        item_rows = [
            {
                "template_id":    template_id,
                "item_name":      item.item_name,
                "item_type":      item.item_type,
                "sort_order":     item.sort_order if item.sort_order else idx,
                "is_required":    item.is_required,
                "standard_value": item.standard_value,
                "check_method":   item.check_method,
                "cycle":          item.cycle,
                "risk_level":     item.risk_level,
                "is_active":      True,
            }
            for idx, item in enumerate(body.items, start=1)
        ]
        for i in range(0, len(item_rows), 50):
            res = supabase.table("safety_template_items").insert(item_rows[i:i+50]).execute()
            item_count += len(res.data or [])

    return {
        "status":  "success",
        "message": f'템플릿 "{body.template_name}" 생성 완료',
        "data":    {"template_id": template_id, "item_count": item_count},
    }


# ══════════════════════════════════════════════
# POST /safety-templates/{template_id}/items
# ══════════════════════════════════════════════

@router.post("/{template_id}/items")
async def add_template_items(template_id: str, items: List[TemplateItemBody], current: dict = Depends(get_current_user)):
    """기존 템플릿에 항목 추가."""
    supabase = get_supabase()
    _ensure_template_own(supabase, template_id, current)

    if not items:
        raise HTTPException(status_code=422, detail="항목이 없습니다.")

    # 현재 max sort_order 조회
    last_res = supabase.table("safety_template_items").select(
        "sort_order"
    ).eq("template_id", template_id).order("sort_order", desc=True).limit(1).execute()
    base_order = (last_res.data[0]["sort_order"] if last_res.data else 0)

    rows = [
        {
            "template_id":    template_id,
            "item_name":      i.item_name,
            "item_type":      i.item_type,
            "sort_order":     i.sort_order if i.sort_order else base_order + idx,
            "is_required":    i.is_required,
            "standard_value": i.standard_value,
            "check_method":   i.check_method,
            "cycle":          i.cycle,
            "risk_level":     i.risk_level,
            "is_active":      True,
        }
        for idx, i in enumerate(items, start=1)
    ]
    res = supabase.table("safety_template_items").insert(rows).execute()
    return {"status": "success", "data": {"added": len(res.data or [])}}


# ══════════════════════════════════════════════
# DELETE /safety-templates/{template_id}/items/{item_id}
# 라우팅 순서: /{id}/items/{item_id} 를 /{id} 보다 먼저 선언
# ══════════════════════════════════════════════

@router.delete("/{template_id}/items/{item_id}")
async def delete_template_item(template_id: str, item_id: str, current: dict = Depends(get_current_user)):
    """항목 soft delete."""
    supabase = get_supabase()
    _ensure_template_own(supabase, template_id, current)
    supabase.table("safety_template_items").update({"is_active": False}).eq(
        "id", item_id
    ).eq("template_id", template_id).execute()
    return {"status": "success", "message": "항목이 삭제되었습니다."}


# ══════════════════════════════════════════════
# DELETE /safety-templates/{template_id}
# ══════════════════════════════════════════════

@router.delete("/{template_id}")
async def delete_template(template_id: str, current: dict = Depends(get_current_user)):
    """템플릿 soft delete (항목은 유지)."""
    supabase = get_supabase()
    _ensure_template_own(supabase, template_id, current)
    supabase.table("safety_templates").update({"is_active": False}).eq(
        "id", template_id
    ).execute()
    return {"status": "success", "message": "템플릿이 삭제되었습니다."}
