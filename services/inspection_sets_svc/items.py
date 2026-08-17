"""점검세트 항목 조회 — 작업자앱 inspect.html 대응 (2026-08-17, Goal G-mswtdmi1-420f8c)."""
from __future__ import annotations

from db.supabase_client import get_supabase
from .errors import InspectionSetsSvcError


def get_set_items(inspection_set_id: str) -> dict:
    """점검세트의 항목 목록을 inspect.html 이 읽는 형태({data:{items:[...]}})로 반환.

    - 세트가 없으면 404(검토 ③): 앱이 EMPTY 가 아니라 ERROR 로 구분하게 한다.
      (존재하는 빈 세트 = 200 + 빈 배열 = EMPTY, 없는 세트 = 404 = ERROR)
    - is_active=false 항목 제외(검토 ④): 폐지 항목이 현장 작업자에게 뜼지 않게.
    원소는 앱이 읽는 이름 그대로: id(필수)·item_name·description·risk_type.
    """
    supabase = get_supabase()
    exists = (
        supabase.table("inspection_sets").select("id").eq("id", inspection_set_id).limit(1).execute()
    )
    if not exists.data:
        raise InspectionSetsSvcError(404, "점검세트를 찾을 수 없습니다")
    res = (
        supabase.table("inspection_set_items")
        .select("id, item_seq, item_name, description, risk_type, is_required, check_type")
        .eq("inspection_set_id", inspection_set_id)
        .neq("is_active", False)  # 폐지 항목 제외(현재 전교 true, null 없음)
        .order("item_seq")
        .execute()
    )
    return {"status": "success", "data": {"items": res.data or []}}


def resolve_set_id_for_assignment(assignment_id: str) -> str | None:
    """work_assignments → work_schedules → inspection_set_id (없으면 None)."""
    supabase = get_supabase()
    wa = supabase.table("work_assignments").select("schedule_id").eq("id", assignment_id).limit(1).execute()
    if not wa.data or not wa.data[0].get("schedule_id"):
        return None
    ws = supabase.table("work_schedules").select("inspection_set_id").eq("id", wa.data[0]["schedule_id"]).limit(1).execute()
    if not ws.data:
        return None
    return ws.data[0].get("inspection_set_id")  # None 가능


def get_items_for_assignment(assignment_id: str) -> dict:
    """배정 → 세트 → 항목. inspect.html 이 읽는 {data:{items:[...]}} 형태. 없으면 404."""
    set_id = resolve_set_id_for_assignment(assignment_id)
    if not set_id:
        raise InspectionSetsSvcError(404, "배정된 점검을 찾을 수 없습니다")
    supabase = get_supabase()
    res = (
        supabase.table("inspection_set_items")
        .select("id, item_seq, item_name, description, risk_type, is_required, check_type")
        .eq("inspection_set_id", set_id)
        .neq("is_active", False)
        .order("item_seq")
        .execute()
    )
    return {"status": "success", "data": {"items": res.data or []}}
