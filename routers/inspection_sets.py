"""
법정점검 세트 관리 라우터 — v1.5.0
v1.5.0: Rolling 생성 방식 전환
  - _build_schedules: 1년치 일괄 → 오늘 이후 첫 번째 planned_date 1건만 생성
  - end_date 파라미터 제거 (실제 INSERT 불필요)
  - GET /inspection-sets/preview-schedule: 캘린더 표시용 가상 렌더링 (DB INSERT 없음)
v1.4.0: 1년치 반복 생성
v1.3.0: anchor 설정 시 work_schedules 1건 생성
v1.2.0: MANUAL 점검세트 등록
v1.1.0: 기준일 설정 API
v1.0.0: 기본 CRUD
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from db.supabase_client import get_supabase

router = APIRouter(prefix="/inspection-sets", tags=["inspection_sets"])

VERSION = "1.5.0"

# cycle_unit → relativedelta 매핑
DELTA_MAP = {
    "day":       lambda v: relativedelta(days=v),
    "week":      lambda v: relativedelta(weeks=v),
    "month":     lambda v: relativedelta(months=v),
    "quarter":   lambda v: relativedelta(months=3 * v),
    "half_year": lambda v: relativedelta(months=6 * v),
    "year":      lambda v: relativedelta(years=v),
}

REPEAT_TYPE_MAP = {
    "day":       "daily",
    "week":      "weekly",
    "month":     "monthly",
    "quarter":   "quarterly",
    "half_year": "half_yearly",
    "year":      "yearly",
}

UNIT_KO = {"year": "년", "month": "개월", "quarter": "분기", "half_year": "반기"}


def _get_delta(cycle_unit: str, cycle_value: int):
    fn = DELTA_MAP.get(cycle_unit.lower())
    return fn(cycle_value) if fn else relativedelta(years=cycle_value)


def _calc_next_date(anchor: date, cycle_unit: str, cycle_value: int) -> date:
    """anchor + cycle → next_date."""
    return anchor + _get_delta(cycle_unit, cycle_value)


def _next_planned_from(base: date, cycle_unit: str, cycle_value: int) -> date:
    """
    base(완료일/anchor) 기준으로 오늘 이후 첫 번째 planned_date 1건 계산.
    base 자체가 오늘 이후면 base가 첫 번째.
    """
    delta    = _get_delta(cycle_unit, cycle_value)
    cursor   = base + delta           # base 다음 회차부터 시작
    today    = date.today()
    while cursor < today:             # 과거 스킵
        cursor += delta
    return cursor


def _build_next_schedule_row(iset: dict, base: date) -> dict:
    """
    v1.5.0 Rolling 방식:
    base(완료일 또는 anchor)에서 다음 1건만 생성.
    """
    cycle_unit  = (iset.get("cycle_unit") or "year").lower()
    cycle_value = int(iset.get("cycle_value") or 1)
    planned     = _next_planned_from(base, cycle_unit, cycle_value)
    repeat_type = REPEAT_TYPE_MAP.get(cycle_unit, "yearly")
    source_type = "LEGAL" if iset.get("source") == "LEGAL_ENGINE" else "MANUAL"
    return {
        "factory_id":        iset["factory_id"],
        "company_id":        iset.get("company_id"),
        "inspection_set_id": iset["id"],
        "planned_date":      planned.isoformat(),
        "start_date":        planned.isoformat(),
        "end_date":          planned.isoformat(),
        "repeat_type":       repeat_type,
        "repeat_interval":   cycle_value,
        "status_code":       "SCHEDULED",
        "source_type":       source_type,
        "obligation_type":   iset.get("inspection_category") or "GENERAL",
        "summary":           iset.get("inspection_set_name") or "",
        "active_yn":         True,
        "assigned_user_id":  None,   # 배정은 안전관리자가 시행
    }, planned


# ── Pydantic 모델 ─────────────────────────────────────

class AnchorBody(BaseModel):
    anchor_date:          Optional[str] = None
    schedule_anchor_date: Optional[str] = None   # 하위 호환
    last_inspection_date: Optional[str] = None


class BulkAnchorBody(BaseModel):
    factory_id:  str
    anchor_date: str


class AnchorBulkItem(BaseModel):
    id: str
    schedule_anchor_date: str
    last_inspection_date: Optional[str] = None


class AnchorBulkPatchBody(BaseModel):
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
        "description, source, is_active, status_code, created_at, updated_at",
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
# POST /inspection-sets/manual  ← /{id} 앞에 선언
# ══════════════════════════════════════════════

@router.post("/manual")
def create_manual_inspection_set(body: ManualInspectionSetBody):
    """MANUAL 점검세트 등록."""
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
# GET /inspection-sets/preview-schedule  v1.5.0 (DB INSERT 없음)
# ══════════════════════════════════════════════

@router.get("/preview-schedule")
def preview_schedule(
    factory_id: str = Query(..., description="시설 ID"),
    months:     int = Query(3, ge=1, le=12, description="향후 대상 개월수 (1~12)"),
):
    """
    캘린더 표시용 가상 렌더링 (v1.5.0).
    DB에 INSERT 없이 순수 계산만으로 향후 months개월치 예정일 반환.
    프론트 캘린더에서 점선/회색 스타일로 표시.
    """
    supabase = get_supabase()

    sets_res = supabase.table("inspection_sets").select(
        "id, inspection_set_name, cycle_unit, cycle_value, "
        "schedule_anchor_date, schedule_end_date, anchor_confirmed, next_planned_date"
    ).eq("factory_id", factory_id).eq("anchor_confirmed", True).eq("is_active", True).execute()
    sets = sets_res.data or []

    today    = date.today()
    end_date = today + relativedelta(months=months)
    preview  = []

    for iset in sets:
        cycle_unit  = (iset.get("cycle_unit") or "year").lower()
        cycle_value = int(iset.get("cycle_value") or 1)
        delta       = _get_delta(cycle_unit, cycle_value)
        name        = iset.get("inspection_set_name") or ""

        # 시작점: next_planned_date 있으면 그것부터, 없으면 anchor부터 계산
        anchor_str = iset.get("schedule_anchor_date")
        if not anchor_str:
            continue

        next_str = iset.get("next_planned_date")
        cursor   = date.fromisoformat(next_str) if next_str else date.fromisoformat(anchor_str) + delta

        # schedule_end_date 있으면 준수
        end_str  = iset.get("schedule_end_date")
        iset_end = date.fromisoformat(end_str) if end_str else end_date
        eff_end  = min(end_date, iset_end)

        while cursor <= eff_end:
            preview.append({
                "inspection_set_id":   iset["id"],
                "inspection_set_name": name,
                "planned_date":        cursor.isoformat(),
                "is_actual":           False,  # 실제 DB 레코드 아님
                "cycle":               f"{cycle_value} {cycle_unit}",
            })
            cursor += delta

    # planned_date 오름쉠 정렬
    preview.sort(key=lambda x: x["planned_date"])

    return {
        "status": "success",
        "data": {
            "factory_id": factory_id,
            "from":       today.isoformat(),
            "to":         end_date.isoformat(),
            "months":     months,
            "count":      len(preview),
            "preview":    preview,
        }
    }


# ══════════════════════════════════════════════
# POST /inspection-sets/anchor/bulk  ← /{id} 앞에 선언
# ══════════════════════════════════════════════

@router.post("/anchor/bulk")
def set_anchor_bulk(body: BulkAnchorBody):
    """
    factory_id의 PENDING_ANCHOR 상태 inspection_sets 전체에
    동일 anchor_date 적용 + Rolling 1건 일정 생성.
    """
    supabase = get_supabase()

    sets_res = supabase.table("inspection_sets").select(
        "id, factory_id, company_id, cycle_value, cycle_unit, "
        "inspection_set_name, inspection_category, source"
    ).eq("factory_id", body.factory_id).eq("status_code", "PENDING_ANCHOR").eq("is_active", True).execute()
    sets = sets_res.data or []

    if not sets:
        return {
            "status":  "success",
            "message": "처리할 PENDING_ANCHOR 상태 점검세트가 없습니다.",
            "data":    {"total_sets": 0, "total_created": 0, "results": []},
        }

    anchor = date.fromisoformat(body.anchor_date)
    results, total_created = [], 0

    for iset in sets:
        iset_id = iset["id"]
        try:
            cycle_unit  = (iset.get("cycle_unit") or "year").lower()
            cycle_value = int(iset.get("cycle_value") or 1)
            # Rolling: anchor 기준으로 오늘 이후 첫 번째 일정 1건
            row, planned = _build_next_schedule_row(iset, anchor)

            # inspection_sets 업데이트
            supabase.table("inspection_sets").update({
                "schedule_anchor_date": anchor.isoformat(),
                "next_planned_date":    planned.isoformat(),
                "anchor_confirmed":     True,
                "status_code":          "ACTIVE",
                "updated_at":           datetime.now().isoformat(),
            }).eq("id", iset_id).execute()

            # 기존 SCHEDULED 삭제 후 1건 INSERT
            supabase.table("work_schedules").delete().eq(
                "inspection_set_id", iset_id
            ).eq("status_code", "SCHEDULED").execute()

            r = supabase.table("work_schedules").insert(row).execute()
            created = len(r.data or [])
            total_created += created
            results.append({"id": iset_id, "name": iset.get("inspection_set_name"),
                            "next_planned_date": planned.isoformat(), "created": created})
        except Exception as e:
            results.append({"id": iset_id, "name": iset.get("inspection_set_name"), "error": str(e)})

    return {
        "status":  "success",
        "message": f"{len(sets)}개 세트 처리, 총 {total_created}개 일정 생성",
        "data": {
            "factory_id":    body.factory_id,
            "anchor_date":   anchor.isoformat(),
            "total_sets":    len(sets),
            "total_created": total_created,
            "results":       results,
        },
    }


# ══════════════════════════════════════════════
# PATCH /inspection-sets/anchor/bulk  (하위 호환)
# ══════════════════════════════════════════════

@router.patch("/anchor/bulk")
def bulk_update_anchor(body: AnchorBulkPatchBody):
    """items 배열 방식 Rolling 업데이트 (하위 호환)."""
    supabase = get_supabase()
    updated_count, errors = 0, []

    for item in body.items:
        try:
            res = supabase.table("inspection_sets").select(
                "id, cycle_value, cycle_unit, factory_id, company_id, "
                "inspection_set_name, inspection_category, source"
            ).eq("id", item.id).limit(1).execute()
            if not res.data:
                errors.append({"id": item.id, "reason": "점검 세트를 찾을 수 없습니다."})
                continue

            iset   = res.data[0]
            anchor = date.fromisoformat(item.schedule_anchor_date)
            row, planned = _build_next_schedule_row(iset, anchor)

            update_data = {
                "schedule_anchor_date": anchor.isoformat(),
                "next_planned_date":    planned.isoformat(),
                "anchor_confirmed":     True,
                "status_code":          "ACTIVE",
                "updated_at":           datetime.now().isoformat(),
            }
            if item.last_inspection_date:
                update_data["last_inspection_date"] = item.last_inspection_date
            supabase.table("inspection_sets").update(update_data).eq("id", item.id).execute()

            try:
                supabase.table("work_schedules").delete().eq(
                    "inspection_set_id", item.id
                ).eq("status_code", "SCHEDULED").execute()
                supabase.table("work_schedules").insert(row).execute()
            except Exception:
                pass

            updated_count += 1
        except Exception as e:
            errors.append({"id": item.id, "reason": str(e)})

    return {"status": "success", "data": {"updated": updated_count, "failed": len(errors), "errors": errors}}


# ══════════════════════════════════════════════
# PATCH /inspection-sets/{id}/anchor  v1.5.0
# ══════════════════════════════════════════════

@router.patch("/{inspection_set_id}/anchor")
def update_inspection_anchor(inspection_set_id: str, body: AnchorBody):
    """
    기준일 설정 + Rolling 1건 일정 생성 (v1.5.0).

    - anchor_date / schedule_anchor_date 중 하나 필수
    - 기존 SCHEDULED 삭제 후 오늘 이후 첫 번째 planned_date 1건 INSERT
    - COMPLETED 절대 건드리지 않음
    - 애용: { "created": 1, "next_planned_date": "2026-05-01" }
    """
    supabase = get_supabase()

    anchor_str = body.anchor_date or body.schedule_anchor_date
    if not anchor_str:
        raise HTTPException(status_code=422, detail="anchor_date 또는 schedule_anchor_date는 필수입니다.")

    res = supabase.table("inspection_sets").select(
        "id, cycle_value, cycle_unit, factory_id, company_id, "
        "inspection_set_name, inspection_category, source, schedule_end_date"
    ).eq("id", inspection_set_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="점검 세트를 찾을 수 없습니다.")

    iset        = res.data[0]
    cycle_unit  = (iset.get("cycle_unit") or "year").lower()
    cycle_value = int(iset.get("cycle_value") or 1)
    anchor      = date.fromisoformat(anchor_str)

    # Rolling: anchor 기준으로 오늘 이후 첫 번째 planned_date 1건
    row, planned = _build_next_schedule_row(iset, anchor)

    # schedule_end_date 있는데 planned가 그것을 넘으면 생성 안 함
    end_str = iset.get("schedule_end_date")
    if end_str and planned > date.fromisoformat(end_str):
        return {
            "status":  "success",
            "message": "일정 종료일이 지나 새로운 회차 생성 안 함.",
            "data": {
                "inspection_set_id": inspection_set_id,
                "anchor_date":       anchor.isoformat(),
                "next_planned_date": planned.isoformat(),
                "anchor_confirmed":  True,
                "created":           0,
            },
        }

    # inspection_sets 업데이트
    update_data = {
        "schedule_anchor_date": anchor.isoformat(),
        "next_planned_date":    planned.isoformat(),
        "anchor_confirmed":     True,
        "status_code":          "ACTIVE",
        "updated_at":           datetime.now().isoformat(),
    }
    if body.last_inspection_date:
        update_data["last_inspection_date"] = body.last_inspection_date

    upd = supabase.table("inspection_sets").update(update_data).eq("id", inspection_set_id).execute()
    if not upd.data:
        raise HTTPException(status_code=500, detail="inspection_sets 업데이트 실패")

    created = 0
    try:
        # 기존 SCHEDULED 삭제 (COMPLETED 유지)
        supabase.table("work_schedules").delete().eq(
            "inspection_set_id", inspection_set_id
        ).eq("status_code", "SCHEDULED").execute()

        # Rolling 1건 INSERT
        r = supabase.table("work_schedules").insert(row).execute()
        created = len(r.data or [])
    except Exception as e:
        print(f"[ANCHOR] work_schedules 생성 실패 (id={inspection_set_id}): {e}")

    return {
        "status":  "success",
        "message": f"{created}개 일정이 생성됐습니다.",
        "data": {
            "inspection_set_id": inspection_set_id,
            "anchor_date":       anchor.isoformat(),
            "next_planned_date": planned.isoformat(),
            "anchor_confirmed":  True,
            "cycle":             f"{cycle_value} {cycle_unit}",
            "created":           created,
        },
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
