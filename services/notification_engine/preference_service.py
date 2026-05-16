"""Preference Service — Notification Preference CRUD.

Preference 저장/조회만 수행. 권한 계산 금지.
"""

import logging
from typing import Optional, List
from datetime import datetime, timezone

logger = logging.getLogger("notification_engine.preference")

DEFAULT_SOURCE = "*"
DEFAULT_CHANNEL = "*"


def get_preferences(actor_id: str, tenant_id: Optional[str] = None) -> List[dict]:
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        q = sb.table("notification_preference_registry") \
            .select("*").eq("actor_id", actor_id).order("source_type")
        if tenant_id:
            q = q.eq("tenant_id", tenant_id)
        return q.execute().data or []
    except Exception as e:
        logger.error("get_preferences failed: %s", e)
        return []


def upsert_preference(
    actor_id: str,
    source_type: str = DEFAULT_SOURCE,
    channel_key: str = DEFAULT_CHANNEL,
    enabled: Optional[bool] = None,
    mute_enabled: Optional[bool] = None,
    quiet_hour_enabled: Optional[bool] = None,
    quiet_hour_start: Optional[str] = None,
    quiet_hour_end: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> Optional[dict]:
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()

        row = {
            "actor_id": actor_id,
            "source_type": source_type,
            "channel_key": channel_key,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if tenant_id is not None:
            row["tenant_id"] = tenant_id
        if enabled is not None:
            row["enabled"] = enabled
        if mute_enabled is not None:
            row["mute_enabled"] = mute_enabled
        if quiet_hour_enabled is not None:
            row["quiet_hour_enabled"] = quiet_hour_enabled
        if quiet_hour_start is not None:
            row["quiet_hour_start"] = quiet_hour_start
        if quiet_hour_end is not None:
            row["quiet_hour_end"] = quiet_hour_end

        resp = sb.table("notification_preference_registry") \
            .upsert(row, on_conflict="actor_id,source_type,channel_key").execute()
        return resp.data[0] if resp.data else None
    except Exception as e:
        logger.error("upsert_preference failed: %s", e)
        return None


def reset_preferences(actor_id: str) -> int:
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        sb.table("notification_preference_registry") \
            .delete().eq("actor_id", actor_id).execute()
        return 0
    except Exception as e:
        logger.error("reset_preferences failed: %s", e)
        return -1


def is_channel_muted(actor_id: str, source_type: str, channel_key: str) -> bool:
    """Queue/Feed에서 사용. mute 또는 disabled 여부."""
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        # 정확한 매칭 우선, 없으면 와일드카드
        for st in [source_type, DEFAULT_SOURCE]:
            for ck in [channel_key, DEFAULT_CHANNEL]:
                resp = sb.table("notification_preference_registry") \
                    .select("enabled,mute_enabled") \
                    .eq("actor_id", actor_id) \
                    .eq("source_type", st) \
                    .eq("channel_key", ck) \
                    .limit(1).execute()
                if resp.data:
                    pref = resp.data[0]
                    if not pref.get("enabled", True):
                        return True
                    if pref.get("mute_enabled", False):
                        return True
        return False
    except Exception:
        return False  # fail-open


def get_muted_sources(actor_id: str) -> List[str]:
    """Feed에서 사용. muted source_type 목록."""
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        resp = sb.table("notification_preference_registry") \
            .select("source_type") \
            .eq("actor_id", actor_id) \
            .eq("mute_enabled", True).execute()
        return [r["source_type"] for r in (resp.data or []) if r["source_type"] != "*"]
    except Exception:
        return []
