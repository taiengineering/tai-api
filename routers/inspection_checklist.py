"""
점검 체크리스트 라우터 — v1.0.0
- 점검 항목 자동 생성
- 점검 스케줄 생성/조회
- 점검 시작/결과기록/완료
- 점검 항목 조회 (inspection_set_id 기준)
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import datetime, date
from db.supabase_client import get_supabase

router = APIRouter(prefix="/inspection", tags=["inspection"])


# ──────────────────────────────────────────────
# GET /inspection/items?inspection_set_id=
# 점검세트별 점검 항목 조회
# ──────────────────────────────────────────────
@router.get("/items")
def get_inspection_items(
    inspection_set_id: Optional[str] = Query(None, description="점검세트 ID"),
    factory_id: Optional[str] = Query(None, description="시설 ID"),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
):
    supabase = get_supabase()
    query = supabase.table("inspection_items").select("*", count="exact")

    if inspection_set_id:
        query = query.eq("inspection_set_id", inspection_set_id)
    if factory_id:
        query = query.eq("factory_id", factory_id)

    offset = (page - 1) * size
    res = query.order("sort_order").range(offset, offset + size - 1).execute()

    return {
        "status": "success",
        "data": {
            "items": res.data,
            "total": res.count or 0,
            "page": page,
            "size": size,
        }
    }


# ──────────────────────────────────────────────
# POST /inspection/generate-items/{factory_id}
# 법령별 표준 점검 항목 자동 생성
# ──────────────────────────────────────────────
@router.post("/generate-items/{factory_id}")
def generate_inspection_items(factory_id: str):
    supabase = get_supabase()

    # 시설의 점검세트 조회
    sets_res = supabase.table("inspection_sets")\
        .select("id, set_name, legal_basis, inspection_cycle_code, inspection_cycle_unit")\
        .eq("factory_id", factory_id).eq("is_active", True).execute()

    if not sets_res.data:
        raise HTTPException(status_code=404, detail="점검세트가 없습니다. 법령 판정을 먼저 실행해주세요.")

    created_count = 0
    for s in sets_res.data:
        # 이미 항목이 있는지 확인
        existing = supabase.table("inspection_items")\
            .select("id", count="exact")\
            .eq("inspection_set_id", s["id"]).execute()

        if existing.count and existing.count > 0:
            continue

        # 표준 항목 생성 (기본 1개)
        supabase.table("inspection_items").insert({
            "inspection_set_id": s["id"],
            "factory_id": factory_id,
            "item_name": f"{s['set_name']} 점검",
            "item_description": s.get("legal_basis", ""),
            "check_type": "PASS_FAIL",
            "sort_order": 1,
            "is_active": True,
            "created_at": datetime.utcnow().isoformat(),
        }).execute()
        created_count += 1

    return {
        "status": "success",
        "message": f"점검 항목 {created_count}건 생성 완료",
        "data": {"factory_id": factory_id, "created_count": created_count}
    }


# ──────────────────────────────────────────────
# POST /inspection/generate-schedules/{factory_id}
# 점검 스케줄 일괄 생성
# ──────────────────────────────────────────────
@router.post("/generate-schedules/{factory_id}")
def generate_schedules(factory_id: str):
    supabase = get_supabase()

    sets_res = supabase.table("inspection_sets")\
        .select("id, set_name, inspection_cycle_code, inspection_cycle_unit")\
        .eq("factory_id", factory_id).eq("is_active", True).execute()

    if not sets_res.data:
        raise HTTPException(status_code=404, detail="점검세트가 없습니다.")

    created_count = 0
    now = datetime.utcnow()
    for s in sets_res.data:
        # 이미 스케줄이 있는지 확인
        existing = supabase.table("work_schedules")\
            .select("id", count="exact")\
            .eq("inspection_set_id", s["id"])\
            .eq("status", "SCHEDULED").execute()

        if existing.count and existing.count > 0:
            continue

        supabase.table("work_schedules").insert({
            "factory_id": factory_id,
            "inspection_set_id": s["id"],
            "schedule_name": s["set_name"],
            "scheduled_date": now.strftime("%Y-%m-%d"),
            "status": "SCHEDULED",
            "created_at": now.isoformat(),
        }).execute()
        created_count += 1

    return {
        "status": "success",
        "message": f"스케줄 {created_count}건 생성 완료",
        "data": {"factory_id": factory_id, "created_count": created_count}
    }


# ──────────────────────────────────────────────
# GET /inspection/status/{factory_id}
# 점검 현황 요약
# ──────────────────────────────────────────────
@router.get("/status/{factory_id}")
def get_inspection_status(factory_id: str):
    supabase = get_supabase()

    schedules = supabase.table("work_schedules")\
        .select("status").eq("factory_id", factory_id).execute()

    rows = schedules.data or []
    total = len(rows)
    scheduled = sum(1 for r in rows if r["status"] == "SCHEDULED")
    in_progress = sum(1 for r in rows if r["status"] == "IN_PROGRESS")
    completed = sum(1 for r in rows if r["status"] == "COMPLETED")
    overdue = sum(1 for r in rows if r["status"] == "OVERDUE")

    return {
        "status": "success",
        "data": {
            "factory_id": factory_id,
            "total": total,
            "scheduled": scheduled,
            "in_progress": in_progress,
            "completed": completed,
            "overdue": overdue,
        }
    }


# ──────────────────────────────────────────────
# GET /inspection/schedules/{factory_id}
# 점검 일정 목록
# ──────────────────────────────────────────────
@router.get("/schedules/{factory_id}")
def get_schedules(
    factory_id: str,
    month: Optional[str] = Query(None, description="YYYY-MM"),
    status: Optional[str] = Query(None, description="SCHEDULED/IN_PROGRESS/COMPLETED/OVERDUE"),
):
    supabase = get_supabase()
    query = supabase.table("work_schedules")\
        .select("*").eq("factory_id", factory_id)

    if month:
        query = query.gte("scheduled_date", f"{month}-01")\
                      .lte("scheduled_date", f"{month}-31")
    if status:
        query = query.eq("status", status)

    res = query.order("scheduled_date").execute()
    return {"status": "success", "data": res.data}


# ──────────────────────────────────────────────
# POST /inspection/start/{work_schedule_id}
# 점검 시작 → safety_inspections 생성
# ──────────────────────────────────────────────
@router.post("/start/{work_schedule_id}")
def start_inspection(work_schedule_id: str):
    supabase = get_supabase()

    schedule = supabase.table("work_schedules")\
        .select("*").eq("id", work_schedule_id).single().execute()
    if not schedule.data:
        raise HTTPException(status_code=404, detail="스케줄을 찾을 수 없습니다")

    if schedule.data["status"] != "SCHEDULED":
        raise HTTPException(status_code=400, detail="이미 시작된 점검입니다")

    now = datetime.utcnow()

    # safety_inspections 생성
    insp = supabase.table("safety_inspections").insert({
        "factory_id": schedule.data["factory_id"],
        "inspection_set_id": schedule.data.get("inspection_set_id"),
        "work_schedule_id": work_schedule_id,
        "inspection_date": now.strftime("%Y-%m-%d"),
        "status": "IN_PROGRESS",
        "created_at": now.isoformat(),
    }).execute()

    # 스케줄 상태 업데이트
    supabase.table("work_schedules").update({
        "status": "IN_PROGRESS",
        "updated_at": now.isoformat(),
    }).eq("id", work_schedule_id).execute()

    return {
        "status": "success",
        "message": "점검이 시작됐습니다",
        "data": insp.data[0] if insp.data else {}
    }


# ──────────────────────────────────────────────
# POST /inspection/result/{inspection_id}/items
# 항목별 결과 기록 (PASS/FAIL/NA)
# ──────────────────────────────────────────────
@router.post("/result/{inspection_id}/items")
def record_result(inspection_id: str, body: dict):
    supabase = get_supabase()

    items = body.get("items", [])
    if not items:
        raise HTTPException(status_code=400, detail="점검 항목이 없습니다")

    now = datetime.utcnow()
    for item in items:
        supabase.table("inspection_results").upsert({
            "inspection_id": inspection_id,
            "inspection_item_id": item["item_id"],
            "result": item["result"],  # PASS / FAIL / NA
            "memo": item.get("memo", ""),
            "checked_at": now.isoformat(),
        }).execute()

    return {
        "status": "success",
        "message": f"결과 {len(items)}건 기록 완료",
    }


# ──────────────────────────────────────────────
# POST /inspection/complete/{work_schedule_id}
# 완료 처리 + 다음 스케줄 자동 생성
# ──────────────────────────────────────────────
@router.post("/complete/{work_schedule_id}")
def complete_inspection(work_schedule_id: str):
    supabase = get_supabase()

    schedule = supabase.table("work_schedules")\
        .select("*").eq("id", work_schedule_id).single().execute()
    if not schedule.data:
        raise HTTPException(status_code=404, detail="스케줄을 찾을 수 없습니다")

    now = datetime.utcnow()

    # 스케줄 완료 처리
    supabase.table("work_schedules").update({
        "status": "COMPLETED",
        "completed_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }).eq("id", work_schedule_id).execute()

    # safety_inspections 완료 처리
    supabase.table("safety_inspections").update({
        "status": "COMPLETED",
        "completed_at": now.isoformat(),
    }).eq("work_schedule_id", work_schedule_id).execute()

    # equipment_assets.last_inspection_date 갱신
    inspection_set_id = schedule.data.get("inspection_set_id")
    if inspection_set_id:
        insp_set = supabase.table("inspection_sets")\
            .select("equipment_asset_id").eq("id", inspection_set_id).single().execute()
        if insp_set.data and insp_set.data.get("equipment_asset_id"):
            supabase.table("equipment_assets").update({
                "last_inspection_date": now.strftime("%Y-%m-%d"),
            }).eq("id", insp_set.data["equipment_asset_id"]).execute()

    return {
        "status": "success",
        "message": "점검이 완료됐습니다",
        "data": {"work_schedule_id": work_schedule_id}
    }
