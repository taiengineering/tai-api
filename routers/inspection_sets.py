"""
법정점검 세트 관리 라우터 — v1.3.0
v1.3.0: PATCH /{id}/anchor — anchor 설정 시 work_schedules 반복일정 자동 생성
  - inspection_sets 업데이트 (schedule_anchor_date, next_planned_date, anchor_confirmed)
  - 중복 체크 후 work_schedules INSERT (planned_date = next_planned_date)
  - 과거 날짜면 OVERDUE, 미래면 planned 상태
  - 응답에 schedule_created, scheduled_id 포함
v1.2.0: MANUAL 점검세트 등록 (POST /manual)
v1.1.0: 기준일 설정 API (PATCH anchor/bulk, PATCH {id}/anchor)
v1.0.0: 기본 CRUD
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import date
from dateutil.relativedelta import relativedelta
from db.supabase_client import get_supabase

router = APIRouter(prefix="/inspection-sets", tags=["inspection_sets"])

VERSION = "1.3.0"

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
    inspection_category:  str = "GENERAL"
    template_id:          Optional[str] = None
    cycle_value:          int = 1
    cycle_unit:           str = "month"
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
    """일괄 기준일 저장. 각 항목에 단건과 동일한 로직 적용 (work_schedules 생성 포함)."""
    supabase = get_supabase()
    updated_count, errors = 0, []

    for item in body.items:
        try:
            res = supabase.table("inspection_sets").select(
                "id, cycle_value, cycle_unit, factory_id, company_id, inspection_set_name"
            ).eq("id", item.id).limit(1).execute()
            if not res.data:
                errors.append({"id": item.id, "reason": "점검 세트를 찾을 수 없습니다."})
                continue

            iset       = res.data[0]
            cycle_unit = iset.get("cycle_unit") or "year"
            cycle_val  = int(iset.get("cycle_value") or 1)
            anchor     = date.fromisoformat(item.schedule_anchor_date)
            next_date  = _calc_next_date(anchor, cycle_unit, cycle_val)

            update_data = {
                "schedule_anchor_date": item.schedule_anchor_date,
                "next_planned_date":    next_date.isoformat(),
                "anchor_confirmed":     True,
                "status_code":          "ACTIVE",
            }
            if item.last_inspection_date:
                update_data["last_inspection_date"] = item.last_inspection_date

            supabase.table("inspection_sets").update(update_data).eq("id", item.id).execute()

            # work_schedules 중복 체크 후 생성
            try:
                exist = supabase.table("work_schedules").select("id").eq(
                    "inspection_set_id", item.id
                ).eq("planned_date", next_date.isoformat()).execute()
                if not exist.data:
                    status_code = "OVERDUE" if next_date < date.today() else "planned"
                    supabase.table("work_schedules").insert({
                        "inspection_set_id": item.id,
                        "company_id":        iset.get("company_id"),
                        "factory_id":        iset.get("factory_id"),
                        "planned_date":      next_date.isoformat(),
                        "start_date":        item.schedule_anchor_date,
                        "repeat_type":       cycle_unit,
                        "repeat_interval":   cycle_val,
                        "status_code":       status_code,
                        "active_yn":         True,
                        "description":       f"{iset.get('inspection_set_name', '법정점검')} — 자동생성",
                        "source_type":       "LEGAL",
                    }).execute()
            except Exception:
                pass  # work_schedules 생성 실패는 anchor 저장을 막지 않음

            updated_count += 1
        except Exception as e:
            errors.append({"id": item.id, "reason": str(e)})

    return {"status": "success", "data": {"updated": updated_count, "failed": len(errors), "errors": errors}}


# ══════════════════════════════════════════════
# PATCH /inspection-sets/{id}/anchor  v1.3.0
# ══════════════════════════════════════════════

@router.patch("/{inspection_set_id}/anchor")
def update_inspection_anchor(inspection_set_id: str, body: AnchorUpdateBody):
    """
    기준일 저장 + next_planned_date 자동 계산 + work_schedules 반복일정 생성.

    v1.3.0 추가:
    - anchor 확정 후 work_schedules에 1건 INSERT
    - 동일 inspection_set_id + planned_date 중복 시 skip
    - 과거 날짜면 OVERDUE, 미래면 planned 상태
    - 응답에 schedule_created, schedule_id 포함
    """
    supabase = get_supabase()

    # 1. inspection_set 조회
    res = supabase.table("inspection_sets").select(
        "id, cycle_value, cycle_unit, factory_id, company_id, inspection_set_name"
    ).eq("id", inspection_set_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="점검 세트를 찾을 수 없습니다.")

    iset       = res.data[0]
    cycle_unit = iset.get("cycle_unit") or "year"
    cycle_val  = int(iset.get("cycle_value") or 1)
    anchor     = date.fromisoformat(body.schedule_anchor_date)
    next_date  = _calc_next_date(anchor, cycle_unit, cycle_val)

    # 2. inspection_sets 업데이트
    update_data = {
        "schedule_anchor_date": body.schedule_anchor_date,
        "next_planned_date":    next_date.isoformat(),
        "anchor_confirmed":     True,
        "status_code":          "ACTIVE",
    }
    if body.last_inspection_date:
        update_data["last_inspection_date"] = body.last_inspection_date

    upd = supabase.table("inspection_sets").update(update_data).eq("id", inspection_set_id).execute()
    if not upd.data:
        raise HTTPException(status_code=500, detail="inspection_sets 업데이트 실패")

    # 3. work_schedules 반복일정 생성
    schedule_created = False
    schedule_id      = None
    schedule_status  = None

    try:
        # 중복 체크: 같은 inspection_set_id + planned_date 있으면 skip
        exist = supabase.table("work_schedules").select("id").eq(
            "inspection_set_id", inspection_set_id
        ).eq("planned_date", next_date.isoformat()).execute()

        if exist.data:
            schedule_id     = exist.data[0]["id"]
            schedule_created = False  # 이미 존재
        else:
            # 과거 날짜면 OVERDUE, 미래면 planned
            schedule_status = "OVERDUE" if next_date < date.today() else "planned"

            ws_res = supabase.table("work_schedules").insert({
                "inspection_set_id": inspection_set_id,
                "company_id":        iset.get("company_id"),
                "factory_id":        iset.get("factory_id"),
                "planned_date":      next_date.isoformat(),
                "start_date":        body.schedule_anchor_date,
                "repeat_type":       cycle_unit,
                "repeat_interval":   cycle_val,
                "status_code":       schedule_status,
                "active_yn":         True,
                "description":       f"{iset.get('inspection_set_name', '법정점검')} — 법정점검 자동생성",
                "source_type":       "LEGAL",
            }).execute()

            if ws_res.data:
                schedule_id      = ws_res.data[0]["id"]
                schedule_created = True

    except Exception as e:
        print(f"[ANCHOR] work_schedules 생성 실패 (inspection_set_id={inspection_set_id}): {e}")
        # work_schedules 생성 실패는 anchor 응답을 막지 않음

    return {
        "status": "success",
        "data": {
            "id":                   inspection_set_id,
            "schedule_anchor_date": body.schedule_anchor_date,
            "next_planned_date":    next_date.isoformat(),
            "anchor_confirmed":     True,
            "cycle_unit":           cycle_unit,
            "cycle_value":          cycle_val,
            # work_schedules 생성 결과
            "schedule_created":     schedule_created,
            "schedule_id":          schedule_id,
            "schedule_status":      schedule_status,
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
