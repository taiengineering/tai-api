"""점검세트 항목 조회 — 작업자앱 inspect.html 대응 (2026-08-17, Goal G-mswtdmi1-420f8c)."""
from __future__ import annotations

from db.supabase_client import get_supabase


def get_set_items(inspection_set_id: str) -> dict:
    """점검세트의 항목 목록을 inspect.html 이 읽는 형태({data:{items:[...]}})로 반환.

    원소는 앱이 읽는 이름 그대로: id(필수)·item_name·description·risk_type.
    getDefaultItems() 가공 항목을 없애기 위한 조회 라우트의 백엔드.
    """
    supabase = get_supabase()
    res = (
        supabase.table("inspection_set_items")
        .select("id, item_seq, item_name, description, risk_type, is_required, check_type")
        .eq("inspection_set_id", inspection_set_id)
        .order("item_seq")
        .execute()
    )
    return {"status": "success", "data": {"items": res.data or []}}
