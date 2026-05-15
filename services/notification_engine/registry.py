"""Event Registry — 플랫폼 공통 Notification Event Type 정의 조회.

notification_event_registry 테이블 기반.
이벤트 발행 시 유효성 검증 + severity_default 제공.
"""

import logging
from typing import Optional

logger = logging.getLogger("notification_engine.registry")

# 인메모리 캐시 (process lifetime)
_cache: dict = {}


def get_event_type_info(event_type: str) -> Optional[dict]:
    """이벤트 타입 정보 조회. 캐시 우선."""
    if event_type in _cache:
        return _cache[event_type]

    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        resp = sb.table("notification_event_registry") \
            .select("*") \
            .eq("event_type", event_type) \
            .limit(1).execute()

        if resp.data:
            _cache[event_type] = resp.data[0]
            return resp.data[0]
        return None
    except Exception as e:
        logger.error("Registry lookup failed: %s — %s", event_type, e)
        return None


def is_notification_enabled(event_type: str) -> bool:
    """이벤트 타입이 알림 활성화되어 있는지 확인."""
    info = get_event_type_info(event_type)
    if info is None:
        return True  # 레지스트리에 없으면 기본 허용 (fail-open)
    return info.get("notification_enabled", True)


def get_default_severity(event_type: str) -> str:
    """Registry에 정의된 severity_default 반환."""
    info = get_event_type_info(event_type)
    if info is None:
        return "INFO"
    return info.get("severity_default", "INFO")


def list_all_event_types() -> list:
    """전체 등록된 이벤트 타입 목록."""
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        resp = sb.table("notification_event_registry") \
            .select("event_type, event_name, severity_default, source_engine, notification_enabled") \
            .order("event_type").execute()
        return resp.data or []
    except Exception as e:
        logger.error("Registry list failed: %s", e)
        return []


def clear_cache():
    """Cache 초기화 (테스트용)."""
    _cache.clear()
