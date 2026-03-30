# routers/internal_api_registry.py — 내부 API 레지스트리
from fastapi import APIRouter
from db.supabase_client import get_supabase

router = APIRouter(prefix="/internal-api-registry", tags=["내부-API-레지스트리"])


@router.get("")
def list_endpoints():
    sb = get_supabase()
    rows = sb.table("internal_api_registry") \
        .select("*").eq("is_active", True) \
        .order("sort_order").execute().data or []
    return {"status": "success", "data": rows}


@router.post("")
def add_endpoint(body: dict):
    sb = get_supabase()
    allowed = [
        "group_name", "api_name", "method", "endpoint", "auth_required",
        "expect_status", "description", "is_active", "sort_order",
    ]
    data = {k: v for k, v in body.items() if k in allowed}
    res = sb.table("internal_api_registry").insert(data).execute()
    return {"status": "success", "data": res.data[0] if res.data else {}}


@router.delete("/{ep_id}")
def delete_endpoint(ep_id: str):
    sb = get_supabase()
    sb.table("internal_api_registry").update({"is_active": False}) \
        .eq("id", ep_id).execute()
    return {"status": "success"}
