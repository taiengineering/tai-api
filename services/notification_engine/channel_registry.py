"""Channel Registry Loader — channel_key → adapter mapping.

notification_channel_registry 테이블 기반.
"""

import logging
from typing import Optional, Callable

logger = logging.getLogger("notification_engine.channel_registry")

_cache: dict = {}

# Adapter module mapping (static)
ADAPTER_MAP = {
    "telegram": "services.notification_engine.adapters.telegram",
    "sms": "services.notification_engine.adapters.sms",
    "in_app": "services.notification_engine.adapters.in_app",
}


def get_channel_info(channel_key: str) -> Optional[dict]:
    """channel_key → registry row (캐시)."""
    if channel_key in _cache:
        return _cache[channel_key]
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        resp = sb.table("notification_channel_registry") \
            .select("*").eq("channel_key", channel_key).limit(1).execute()
        if resp.data:
            _cache[channel_key] = resp.data[0]
            return resp.data[0]
        return None
    except Exception as e:
        logger.error("Channel registry lookup failed: %s — %s", channel_key, e)
        return None


def is_channel_enabled(channel_key: str) -> bool:
    info = get_channel_info(channel_key)
    return info.get("enabled", False) if info else False


def resolve_adapter(channel_key: str) -> Optional[Callable]:
    """channel_key → send() 함수 반환."""
    info = get_channel_info(channel_key)
    if not info or not info.get("enabled"):
        return None

    adapter_name = info.get("adapter_name", "")
    module_path = ADAPTER_MAP.get(adapter_name)
    if not module_path:
        logger.error("No adapter module for: %s", adapter_name)
        return None

    try:
        import importlib
        mod = importlib.import_module(module_path)
        return getattr(mod, "send", None)
    except Exception as e:
        logger.error("Adapter import failed: %s — %s", module_path, e)
        return None


def list_enabled_channels() -> list:
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        resp = sb.table("notification_channel_registry") \
            .select("*").eq("enabled", True).execute()
        return resp.data or []
    except Exception:
        return []


def clear_cache():
    _cache.clear()
