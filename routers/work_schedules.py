from fastapi import APIRouter
from db.supabase_client import get_supabase

router = APIRouter(prefix="/work-schedules", tags=["work_schedules"])


# 작업일정 전체
@router.get("")
def get_work_schedules():
    supabase = get_supabase()

    result = (
        supabase.table("work_schedules")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )

    return result.data


# 특정 공장의 작업일정
@router.get("/factory/{factory_id}")
def get_factory_work_schedules(factory_id: str):
    supabase = get_supabase()

    result = (
        supabase.table("work_schedules")
        .select("*")
        .eq("factory_id", factory_id)
        .order("created_at", desc=True)
        .execute()
    )

    return result.data


# 특정 점검세트 기준 작업일정
@router.get("/inspection-set/{inspection_set_id}")
def get_inspection_set_work_schedules(inspection_set_id: str):
    supabase = get_supabase()

    result = (
        supabase.table("work_schedules")
        .select("*")
        .eq("inspection_set_id", inspection_set_id)
        .order("created_at", desc=True)
        .execute()
    )

    return result.data


# 특정 일정 1건
@router.get("/{schedule_id}")
def get_work_schedule(schedule_id: str):
    supabase = get_supabase()

    result = (
        supabase.table("work_schedules")
        .select("*")
        .eq("id", schedule_id)
        .limit(1)
        .execute()
    )

    return result.data
