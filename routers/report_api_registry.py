# routers/report_api_registry.py — 외부 API 레지스트리
from fastapi import APIRouter
from db.supabase_client import get_supabase

router = APIRouter(prefix="/report-api-registry", tags=["외부-API-레지스트리"])


@router.get("")
def list_external():
    sb = get_supabase()
    rows = sb.table("report_api_registry") \
        .select("*").order("created_at").execute().data or []
    return {"status": "success", "data": rows}


@router.post("")
def add_external(body: dict):
    sb = get_supabase()
    allowed = [
        "system_name", "operator", "system_type", "official_api",
        "api_apply_url", "login_required", "approval_type",
        "can_use_for_auto_filing", "recommendation", "apply_status",
        "apply_date", "approved_date", "api_key_issued", "notes",
    ]
    data = {k: v for k, v in body.items() if k in allowed}
    res = sb.table("report_api_registry").insert(data).execute()
    return {"status": "success", "data": res.data[0] if res.data else {}}


@router.patch("/{reg_id}")
def update_external(reg_id: str, body: dict):
    sb = get_supabase()
    allowed = ["apply_status", "apply_date", "approved_date", "api_key_issued", "notes"]
    data = {k: v for k, v in body.items() if k in allowed}
    res = sb.table("report_api_registry").update(data).eq("id", reg_id).execute()
    return {"status": "success", "data": res.data[0] if res.data else {}}


@router.delete("/{reg_id}")
def delete_external(reg_id: str):
    sb = get_supabase()
    sb.table("report_api_registry").delete().eq("id", reg_id).execute()
    return {"status": "success"}
