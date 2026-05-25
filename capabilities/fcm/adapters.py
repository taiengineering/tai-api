"""FCM Adapter — v1.0.0

DB operations for FCM token lookup/save.
Capability core에서 import하지 않음. Wrapper가 주입.

사용:
  from capabilities.fcm.adapters import find_token_by_phone, save_token_worker, save_token_by_phone
"""
import logging
from typing import Optional

log = logging.getLogger(__name__)


def find_token_by_phone(supabase, phone: str) -> Optional[str]:
    """전화번호로 FCM 토큰 조회. worker_registry → users 순서."""
    clean = phone.replace("-", "").replace(" ", "")
    wr = supabase.table("worker_registry").select("push_token").eq("phone", clean).limit(1).execute()
    if wr.data and wr.data[0].get("push_token"):
        return wr.data[0]["push_token"]
    u = supabase.table("users").select("push_token").eq("phone", clean).limit(1).execute()
    if not u.data:
        u = supabase.table("users").select("push_token").eq("phone", f"{clean[:3]}-{clean[3:7]}-{clean[7:]}").limit(1).execute()
    if u.data and u.data[0].get("push_token"):
        return u.data[0]["push_token"]
    return None


def save_token_worker(supabase, worker_id: str, fcm_token: str) -> bool:
    """worker_registry에 FCM 토큰 저장."""
    chk = supabase.table("worker_registry").select("id").eq("id", worker_id).limit(1).execute()
    if not chk.data:
        return False
    supabase.table("worker_registry").update({"push_token": fcm_token, "app_installed": True}).eq("id", worker_id).execute()
    return True


def save_token_by_phone(supabase, phone: str, fcm_token: str, platform: str = "web") -> Optional[str]:
    """전화번호로 FCM 토큰 저장. worker_registry → users fallback. 저장한 table명 반환."""
    clean = phone.replace("-", "").replace(" ", "")
    wr = supabase.table("worker_registry").select("id").eq("phone", clean).limit(1).execute()
    if wr.data:
        supabase.table("worker_registry").update({"push_token": fcm_token, "app_installed": True}).eq("id", wr.data[0]["id"]).execute()
        return "worker_registry"
    u = supabase.table("users").select("id").eq("phone", clean).limit(1).execute()
    if not u.data:
        u = supabase.table("users").select("id").eq("phone", f"{clean[:3]}-{clean[3:7]}-{clean[7:]}").limit(1).execute()
    if u.data:
        supabase.table("users").update({"push_token": fcm_token, "push_platform": platform}).eq("id", u.data[0]["id"]).execute()
        return "users"
    return None
