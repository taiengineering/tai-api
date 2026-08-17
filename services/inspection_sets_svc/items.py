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
