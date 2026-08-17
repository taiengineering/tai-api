"""점검세트 항목 조회 — inspect.html (Goal G-mswtdmi1-420f8c)."""
from __future__ import annotations

from db.supabase_client import get_supabase
from .errors import InspectionSetsSvcError

_ITEM_COLS = "id, item_seq, item_name, description, risk_type, is_required, check_type"


def get_set_items(inspection_set_id: str) -> dict:
    """세트 항목 목록. 없는 세트=404(ERROR), 있는 빈 세트=200+[](EMPTY). is_active=false 제외."""
    supabase = get_supabase()
    exists = supabase.table("inspection_sets").select("id").eq("id", inspection_set_id).limit(1).execute()
    if not exists.data:
        raise InspectionSetsSvcError(404, "점검세트를 찾을 수 없습니다")
    res = (
        supabase.table("inspection_set_items").select(_ITEM_COLS)
        .eq("inspection_set_id", inspection_set_id).neq("is_active", False)
        .order("item_seq").execute()
    )
    return {"status": "success", "data": {"items": res.data or []}}


def resolve_set_id_for_assignment(assignment_id: str):
    """work_assignments -> work_schedules -> inspection_set_id (없으면 None). worker_check 검증용."""
    supabase = get_supabase()
    wa = supabase.table("work_assignments").select("schedule_id").eq("id", assignment_id).limit(1).execute()
    if not wa.data or not wa.data[0].get("schedule_id"):
        return None
    ws = supabase.table("work_schedules").select("inspection_set_id").eq("id", wa.data[0]["schedule_id"]).limit(1).execute()
    if not ws.data:
        return None
    return ws.data[0].get("inspection_set_id")


def get_items_for_assignment(assignment_id: str) -> dict:
    """배정->세트->항목. 배정/일정 없음=404(ERROR), 세트 미연결=200+[](EMPTY, 검토 ⓑ)."""
    supabase = get_supabase()
    wa = supabase.table("work_assignments").select("schedule_id").eq("id", assignment_id).limit(1).execute()
    if not wa.data or not wa.data[0].get("schedule_id"):
        raise InspectionSetsSvcError(404, "배정된 점검을 찾을 수 없습니다")
    ws = supabase.table("work_schedules").select("inspection_set_id").eq("id", wa.data[0]["schedule_id"]).limit(1).execute()
    if not ws.data:
        raise InspectionSetsSvcError(404, "배정된 점검을 찾을 수 없습니다")
    set_id = ws.data[0].get("inspection_set_id")
    if not set_id:
        return {"status": "success", "data": {"items": []}}
    res = (
        supabase.table("inspection_set_items").select(_ITEM_COLS)
        .eq("inspection_set_id", set_id).neq("is_active", False)
        .order("item_seq").execute()
    )
    return {"status": "success", "data": {"items": res.data or []}}
