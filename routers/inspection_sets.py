"""
법정점검 세트 관리 라우터 — v1.2.0
v1.2.0: MANUAL 점검세트 등록
  - POST /inspection-sets/manual  (고정 경로 — /{id} 앞에 선언)
v1.1.0: 기준일 설정 API 추가
  - PATCH /inspection-sets/anchor/bulk
  - PATCH /inspection-sets/{id}/anchor
  - GET에 anchor_confirmed 필터 추가
v1.0.0: 기본 CRUD
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import date
from dateutil.relativedelta import relativedelta
from db.supabase_client import get_supabase

router = APIRouter(prefix="/inspection-sets", tags=["inspection_sets"])

VERSION = "1.2.0"

UNIT_MAP = {
    "year":      lambda v: relativedelta(years=v),
    "month":     lambda v: relativedelta(months=v),
    "half_year": lambda v: relativedelta(months=6),
    "quarter":   lambda v: relativedelta(months=3),
}

UNIT_KO = {"year": "년", "month": "개월", "quarter": "분기", "half_year": "반기"}


def _calc_next_date(anchor: date, cycle_unit: str, cycle_value: int) -> date:
    fn = UNIT_MAP.get(cycle_unit)
    return anchor + (fn(cycle_value) if fn else relativedelta(years=1))


# ── Pydantic 모델 ──────────────────────────────

class AnchorUpdateBody(BaseModel):
    schedule_anchor_date: str
    last_inspection_date: Optional[str] = None


class AnchorBulkItem(BaseModel):
    id: str
    schedule_anchor_date: str
    last_inspection_date: Optional[str] = None


class AnchorBulkBody(BaseModel):
    items: List[AnchorBulkItem]


class ManualInspectionSetBody(BaseModel):
    factory_id:           str
    inspection_set_name:  str
    inspection_category:  str = "GENERAL"         # FIRE / ELEC / SAFETY / GENERAL ...
    template_id:          Optional[str] = None    # safety_templates.id
    cycle_value:          int = 1
    cycle_unit:           str = "month"           # year / month / quarter / half_year
    cycle_base_type:      str = "LAST_INSPECTION"
    description:          Optional[str] = None


# ══════════════════════════════════════════════
# GET /inspection-sets
# ══════════════════════════════════════════════

@router.get("")
def get_inspection_sets(
    factory_id:       Optional[str]  = Query(None),
    source:           Optional[str]  = Query(None),
    anchor_confirmed: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    supabase = get_supabase()
    query = supabase.table("inspection_sets").select(
        "id, company_id, factory_id, inspection_set_name, inspection_set_code, "
        "legal_rule_id, law_name, law_article, cycle_unit, cycle_value, "
        "cycle_base_type, cycle_base_guide, "
        "schedule_anchor_date, last_inspection_date, next_planned_date, anchor_confirmed, "
        "description, source, is_active, created_at, updated_at",
        count="exact"
    )
    if factory_id:              query = query.eq("factory_id", factory_id)
    if source:                  query = query.eq("source", source)
    if anchor_confirmed is not None: query = query.eq("anchor_confirmed", anchor_confirmed)

    offset = (page - 1) * size
    res = query.order("created_at", desc=True).range(offset, offset + size - 1).execute()
    return {
        "status": "success",
        "data": {
            "items": res.data or [], "total": res.count or 0,
            "page": page, "size": size,
            "total_pages": ((res.count or 0) + size - 1) // size if res.count else 0,
        }
    }


# ══════════════════════════════════════════════
# POST /inspection-sets/manual  ← 고정 경로: /{id} 앞에 반드시 먼저 선언
# ══════════════════════════════════════════════

@router.post("/manual")
def create_manual_inspection_set(body: ManualInspectionSetBody):
    """MANUAL 점검세트 등록 (법령엔진 외 자체 점검 세트)."""
    supabase = get_supabase()

    if not (body.inspection_set_name or "").strip():
        raise HTTPException(status_code=422, detail="점검 세트명은 필수입니다.")

    fac_res = supabase.table("factories").select("company_id").eq(
        "id", body.factory_id
    ).limit(1).execute()
    company_id = (fac_res.data[0].get("company_id") if fac_res.data else None)

    guide = f"마지막 점검일로부터 {body.cycle_value}{UNIT_KO.get(body.cycle_unit, body.cycle_unit)}마다"

    res = supabase.table("inspection_sets").insert({
        "factory_id":          body.factory_id,
        "company_id":          company_id,
        "inspection_set_name": body.inspection_set_name.strip(),
        "inspection_category": body.inspection_category,
        "template_id":         body.template_id,
        "cycle_value":         body.cycle_value,
        "cycle_unit":          body.cycle_unit,
        "cycle_base_type":     body.cycle_base_type,
        "cycle_base_guide":    guide,
        "custom_description":  body.description,
        "source":              "MANUAL",
        "status_code":         "PENDING_ANCHOR",
        "anchor_confirmed":    False,
        "is_active":           True,
    }).execute()

    if not res.data:
        raise HTTPException(status_code=500, detail="점검 세트 생성 실패")

    return {
        "status":  "success",
        "message": f'"{body.inspection_set_name}" 점검 세트 생성 완료',
        "data":    {"inspection_set_id": res.data[0]["id"]},
    }


# ══════════════════════════════════════════════
# PATCH /inspection-sets/anchor/bulk  ← /{id}/anchor 보다 먼저 선언
# ══════════════════════════════════════════════

@router.patch("/anchor/bulk")
def bulk_update_anchor(body: AnchorBulkBody):
    supabase = get_supabase()
    updated_count, errors = 0, []

    for item in body.items:
        try:
            res = supabase.table("inspection_sets").select(
                "id, cycle_value, cycle_unit"
            ).eq("id", item.id).limit(1).execute()
            if not res.data:
                errors.append({"id": item.id, "reason": "점검 세트를 찾을 수 없습니다."})
                continue

            iset = res.data[0]
            anchor    = date.fromisoformat(item.schedule_anchor_date)
            next_date = _calc_next_date(anchor, iset.get("cycle_unit") or "year", int(iset.get("cycle_value") or 1))

            update_data = {
                "schedule_anchor_date": item.schedule_anchor_date,
                "next_planned_date":    next_date.isoformat(),
                "anchor_confirmed":     True,
            }
            if item.last_inspection_date:
                update_data["last_inspection_date"] = item.last_inspection_date

            supabase.table("inspection_sets").update(update_data).eq("id", item.id).execute()
            updated_count += 1
        except Exception as e:
            errors.append({"id": item.id, "reason": str(e)})

    return {"status": "success", "data": {"updated": updated_count, "failed": len(errors), "errors": errors}}


# ══════════════════════════════════════════════
# PATCH /inspection-sets/{id}/anchor
# ══════════════════════════════════════════════

@router.patch("/{inspection_set_id}/anchor")
def update_inspection_anchor(inspection_set_id: str, body: AnchorUpdateBody):
    supabase = get_supabase()

    res = supabase.table("inspection_sets").select(
        "id, cycle_value, cycle_unit, factory_id"
    ).eq("id", inspection_set_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="점검 세트를 찾을 수 없습니다.")

    iset      = res.data[0]
    anchor    = date.fromisoformat(body.schedule_anchor_date)
    next_date = _calc_next_date(anchor, iset.get("cycle_unit") or "year", int(iset.get("cycle_value") or 1))

    update_data = {
        "schedule_anchor_date": body.schedule_anchor_date,
        "next_planned_date":    next_date.isoformat(),
        "anchor_confirmed":     True,
    }
    if body.last_inspection_date:
        update_data["last_inspection_date"] = body.last_inspection_date

    upd = supabase.table("inspection_sets").update(update_data).eq("id", inspection_set_id).execute()
    if not upd.data:
        raise HTTPException(status_code=500, detail="업데이트 실패")

    return {
        "status": "success",
        "data": {
            "id": inspection_set_id,
            "schedule_anchor_date": body.schedule_anchor_date,
            "next_planned_date":    next_date.isoformat(),
            "anchor_confirmed":     True,
            "cycle_unit":           iset.get("cycle_unit"),
            "cycle_value":          iset.get("cycle_value"),
        }
    }


# ══════════════════════════════════════════════
# 기존 엔드포인트 (하위 호환)
# ══════════════════════════════════════════════

@router.get("/company/{company_id}")
def get_company_inspection_sets(company_id: str):
    supabase = get_supabase()
    result = supabase.table("inspection_sets").select("*").eq(
        "company_id", company_id
    ).order("created_at", desc=True).execute()
    return {"status": "success", "data": result.data}


@router.get("/factory/{factory_id}")
def get_factory_inspection_sets(factory_id: str):
    supabase = get_supabase()
    result = supabase.table("inspection_sets").select("*").eq(
        "factory_id", factory_id
    ).order("created_at", desc=True).execute()
    return {"status": "success", "data": result.data}


@router.get("/{inspection_set_id}")
def get_inspection_set(inspection_set_id: str):
    supabase = get_supabase()
    result = supabase.table("inspection_sets").select("*").eq(
        "id", inspection_set_id
    ).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="점검세트를 찾을 수 없습니다")
    return {"status": "success", "data": result.data}
