"""
법정점검 세트 관리 라우터 — v1.4.0
v1.4.0: 기준일 입력 + 반복일정 생성 (1년치)
  - PATCH /{id}/anchor: anchor_date → 1년치 work_schedules 반복 생성 (기존 SCHEDULED 삭제 후 재생성)
    cycle=1month → 12개, cycle=1year → 2개
  - POST /anchor/bulk: factory_id의 PENDING_ANCHOR 전체 일괄 처리 (신규)
  - 두 필드 모두 지원: anchor_date (신규) / schedule_anchor_date (하위 호환)
v1.3.0: anchor 설정 시 work_schedules 1건 생성
v1.2.0: MANUAL 점검세트 등록 (POST /manual)
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

VERSION = "1.4.0"

# cycle_unit → relativedelta 매핑
DELTA_MAP = {
    "day":       lambda v: relativedelta(days=v),
    "week":      lambda v: relativedelta(weeks=v),
    "month":     lambda v: relativedelta(months=v),
    "quarter":   lambda v: relativedelta(months=3 * v),
    "half_year": lambda v: relativedelta(months=6 * v),
    "year":      lambda v: relativedelta(years=v),
}

# cycle_unit → repeat_type 텍스트
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
    """단일 next_date 계산 (하위 호환용)."""
    return anchor + _get_delta(cycle_unit, cycle_value)


def _build_schedules(iset: dict, anchor: date, end: date) -> List[dict]:
    """anchor ~ end 범위의 반복 일정 rows 목록 생성."""
    cycle_unit  = (iset.get("cycle_unit") or "year").lower()
    cycle_value = int(iset.get("cycle_value") or 1)
    delta       = _get_delta(cycle_unit, cycle_value)
    repeat_type = REPEAT_TYPE_MAP.get(cycle_unit, "yearly")
    source_type = "LEGAL" if iset.get("source") == "LEGAL_ENGINE" else "MANUAL"

    rows, cursor = [], anchor
    while cursor <= end:
        rows.append({
            "factory_id":        iset["factory_id"],
            "company_id":        iset.get("company_id"),
            "inspection_set_id": iset["id"],
            "planned_date":      cursor.isoformat(),
            "start_date":        cursor.isoformat(),
            "end_date":          cursor.isoformat(),
            "repeat_type":       repeat_type,
            "repeat_interval":   cycle_value,
            "status_code":       "SCHEDULED",
            "source_type":       source_type,
            "obligation_type":   iset.get("inspection_category") or "GENERAL",
            "summary":           iset.get("inspection_set_name") or "",
            "active_yn":         True,
        })
        cursor += delta
    return rows


# ── Pydantic 모델 ──────────────────────────────────

class AnchorBody(BaseModel):
    """단건 기준일 설정 (v1.4.0). anchor_date 또는 schedule_anchor_date 중 하나 필수."""
    anchor_date:          Optional[str] = None   # 신규 필드
    schedule_anchor_date: Optional[str] = None   # 하위 호환
    end_date:             Optional[str] = None   # 일정 종료일 (없으면 1년 후)
    last_inspection_date: Optional[str] = None   # 직전 점검일 (선택)


class BulkAnchorBody(BaseModel):
    """일괄 기준일 설정 — factory_id의 PENDING_ANCHOR 전체 처리."""
    factory_id:  str
    anchor_date: str            # 기준일 (전체 동일 적용)
    end_date:    Optional[str] = None


class AnchorBulkItem(BaseModel):
    """PATCH /anchor/bulk 하위 호환용 (items 배열)."""
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
# POST /inspection-sets/manual
# 고정 경로 — /{id} 앞에 반드시 먼저 선언
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
# POST /inspection-sets/anchor/bulk  (신규 v1.4.0)
# factory_id의 PENDING_ANCHOR 전체 일괄 처리
# 고정 경로 — /{id} 앞에 선언
# ══════════════════════════════════════════════

@router.post("/anchor/bulk")
def set_anchor_bulk(body: BulkAnchorBody):
    """
    factory_id의 PENDING_ANCHOR 상태 inspection_sets 전체에
    동일 anchor_date를 적용하고 반복일정을 생성합니다.
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
    end    = date.fromisoformat(body.end_date) if body.end_date else anchor + relativedelta(years=1)

    results = []
    total_created = 0

    for iset in sets:
        iset_id = iset["id"]
        try:
            # inspection_sets 업데이트
            next_date = _calc_next_date(anchor, iset.get("cycle_unit") or "year", int(iset.get("cycle_value") or 1))
            supabase.table("inspection_sets").update({
                "schedule_anchor_date": anchor.isoformat(),
                "schedule_end_date":    end.isoformat(),
                "next_planned_date":    next_date.isoformat(),
                "anchor_confirmed":     True,
                "status_code":          "ACTIVE",
                "updated_at":           datetime.now().isoformat(),
            }).eq("id", iset_id).execute()

            # 기존 SCHEDULED 삭제
            supabase.table("work_schedules").delete().eq(
                "inspection_set_id", iset_id
            ).eq("status_code", "SCHEDULED").execute()

            # 반복 일정 생성
            rows    = _build_schedules(iset, anchor, end)
            created = 0
            for i in range(0, len(rows), 20):
                r = supabase.table("work_schedules").insert(rows[i:i + 20]).execute()
                created += len(r.data or [])

            total_created += created
            results.append({"id": iset_id, "name": iset.get("inspection_set_name"), "created": created})

        except Exception as e:
            results.append({"id": iset_id, "name": iset.get("inspection_set_name"), "error": str(e)})

    return {
        "status":  "success",
        "message": f"{len(sets)}개 세트 처리, 총 {total_created}개 일정 생성",
        "data": {
            "factory_id":    body.factory_id,
            "anchor_date":   anchor.isoformat(),
            "end_date":      end.isoformat(),
            "total_sets":    len(sets),
            "total_created": total_created,
            "results":       results,
        },
    }


# ══════════════════════════════════════════════
# PATCH /inspection-sets/anchor/bulk (하위 호환 — items 배열)
# ══════════════════════════════════════════════

@router.patch("/anchor/bulk")
def bulk_update_anchor(body: AnchorBulkPatchBody):
    """일괄 기준일 저장 (하위 호환 — items 배열 방식)."""
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

            iset       = res.data[0]
            anchor     = date.fromisoformat(item.schedule_anchor_date)
            end        = anchor + relativedelta(years=1)
            next_date  = _calc_next_date(anchor, iset.get("cycle_unit") or "year", int(iset.get("cycle_value") or 1))

            update_data = {
                "schedule_anchor_date": item.schedule_anchor_date,
                "schedule_end_date":    end.isoformat(),
                "next_planned_date":    next_date.isoformat(),
                "anchor_confirmed":     True,
                "status_code":          "ACTIVE",
                "updated_at":           datetime.now().isoformat(),
            }
            if item.last_inspection_date:
                update_data["last_inspection_date"] = item.last_inspection_date

            supabase.table("inspection_sets").update(update_data).eq("id", item.id).execute()

            # 기존 SCHEDULED 삭제 후 재생성
            try:
                supabase.table("work_schedules").delete().eq(
                    "inspection_set_id", item.id
                ).eq("status_code", "SCHEDULED").execute()

                rows = _build_schedules(iset, anchor, end)
                for i in range(0, len(rows), 20):
                    supabase.table("work_schedules").insert(rows[i:i + 20]).execute()
            except Exception:
                pass

            updated_count += 1
        except Exception as e:
            errors.append({"id": item.id, "reason": str(e)})

    return {"status": "success", "data": {"updated": updated_count, "failed": len(errors), "errors": errors}}


# ══════════════════════════════════════════════
# PATCH /inspection-sets/{id}/anchor  v1.4.0
# ══════════════════════════════════════════════

@router.patch("/{inspection_set_id}/anchor")
def update_inspection_anchor(inspection_set_id: str, body: AnchorBody):
    """
    기준일 설정 + 1년치 반복일정 생성 (v1.4.0).

    - anchor_date 또는 schedule_anchor_date 중 하나 필수
    - end_date 없으면 anchor + 1년
    - 기존 SCHEDULED 일정 삭제 후 재생성 (COMPLETED는 유지)
    - cycle=1month → 12개, cycle=1year → 2개
    """
    supabase = get_supabase()

    # anchor_date 필드 결정 (신규: anchor_date, 하위 호환: schedule_anchor_date)
    anchor_str = body.anchor_date or body.schedule_anchor_date
    if not anchor_str:
        raise HTTPException(status_code=422, detail="anchor_date 또는 schedule_anchor_date는 필수입니다.")

    # inspection_set 전체 조회 (반복일정 생성에 필요)
    res = supabase.table("inspection_sets").select(
        "id, cycle_value, cycle_unit, factory_id, company_id, "
        "inspection_set_name, inspection_category, source"
    ).eq("id", inspection_set_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="점검 세트를 찾을 수 없습니다.")

    iset        = res.data[0]
    cycle_unit  = (iset.get("cycle_unit") or "year").lower()
    cycle_value = int(iset.get("cycle_value") or 1)
    anchor      = date.fromisoformat(anchor_str)
    end         = date.fromisoformat(body.end_date) if body.end_date else anchor + relativedelta(years=1)
    next_date   = _calc_next_date(anchor, cycle_unit, cycle_value)

    # inspection_sets 업데이트
    update_data = {
        "schedule_anchor_date": anchor.isoformat(),
        "schedule_end_date":    end.isoformat(),
        "next_planned_date":    next_date.isoformat(),
        "anchor_confirmed":     True,
        "status_code":          "ACTIVE",
        "updated_at":           datetime.now().isoformat(),
    }
    if body.last_inspection_date:
        update_data["last_inspection_date"] = body.last_inspection_date

    upd = supabase.table("inspection_sets").update(update_data).eq("id", inspection_set_id).execute()
    if not upd.data:
        raise HTTPException(status_code=500, detail="inspection_sets 업데이트 실패")

    # 기존 SCHEDULED 일정 삭제 (COMPLETED는 유지)
    created = 0
    try:
        supabase.table("work_schedules").delete().eq(
            "inspection_set_id", inspection_set_id
        ).eq("status_code", "SCHEDULED").execute()

        # 반복 일정 rows 생성
        rows = _build_schedules(iset, anchor, end)

        # 20건씩 배치 INSERT
        for i in range(0, len(rows), 20):
            r = supabase.table("work_schedules").insert(rows[i:i + 20]).execute()
            created += len(r.data or [])

    except Exception as e:
        print(f"[ANCHOR] work_schedules 생성 실패 (id={inspection_set_id}): {e}")
        # 생성 실패해도 anchor 저장 응답은 반환

    return {
        "status":  "success",
        "message": f"{created}개 반복일정이 생성됐습니다.",
        "data": {
            "inspection_set_id": inspection_set_id,
            "anchor_date":       anchor.isoformat(),
            "end_date":          end.isoformat(),
            "next_planned_date": next_date.isoformat(),
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
