"""Event Wiring Service.

event_type → wiring registry lookup → policy resolve → runtime emit.

역할: 이벤트를 정책에 연결. 운영 판단 금지.
"""

import logging
from typing import Optional, Dict, Any, List
from db.supabase_client import get_supabase

logger = logging.getLogger("notification_engine.event_wiring")


async def lookup_wiring(event_type: str) -> Optional[Dict[str, Any]]:
    """event_type으로 wiring registry 조회."""
    try:
        sb = get_supabase()
        resp = (
            sb.table("notification_event_wiring_registry")
            .select("*")
            .eq("event_type", event_type)
            .eq("enabled", True)
            .execute()
        )
        if resp.data:
            return resp.data[0]
        return None
    except Exception as e:
        logger.error("Wiring lookup failed for %s: %s", event_type, e)
        return None


async def resolve_policy(policy_key: str) -> Optional[Dict[str, Any]]:
    """policy_key로 정책 조회."""
    try:
        sb = get_supabase()
        resp = (
            sb.table("notification_policy_registry")
            .select("*")
            .eq("policy_key", policy_key)
            .execute()
        )
        if resp.data:
            return resp.data[0]
        return None
    except Exception as e:
        logger.error("Policy resolve failed for %s: %s", policy_key, e)
        return None


async def wire_and_emit(
    event_type: str,
    payload: Optional[Dict[str, Any]] = None,
    override_channel: Optional[str] = None,
    override_severity: Optional[str] = None,
) -> Dict[str, Any]:
    """Event → Wiring → Policy → Runtime Emit.

    Args:
        event_type: 이벤트 유형 (e.g. 'workflow_stuck')
        payload: 이벤트 데이터
        override_channel: 채널 오버라이드
        override_severity: severity 오버라이드

    Returns:
        {status, wiring_key, policy_key, emitted}
    """
    # 1. Wiring lookup
    wiring = await lookup_wiring(event_type)
    if not wiring:
        logger.info("No active wiring for event_type=%s", event_type)
        return {"status": "skipped", "reason": "no_wiring", "event_type": event_type}

    # 2. Policy resolve
    policy = await resolve_policy(wiring["notification_policy_key"])
    if not policy:
        logger.warning("Policy not found: %s", wiring["notification_policy_key"])
        return {"status": "error", "reason": "policy_not_found", "policy_key": wiring["notification_policy_key"]}

    # 3. Cooldown check (wiring override > policy default)
    cooldown = wiring.get("cooldown_seconds") or policy.get("cooldown_seconds", 0)
    # TODO: cooldown 실제 검사 (last_sent 테이블 필요)

    # 4. Build emit params
    channel = override_channel or policy["default_channel"]
    severity = override_severity or policy["default_severity"]
    audience = wiring.get("audience_key", "operator")

    title = (payload or {}).get("title", f"[{severity}] {event_type}")
    body = (payload or {}).get("body", f"Event: {event_type}")

    # 5. Emit via pipeline
    try:
        from services.notification_engine.pipeline import emit_notification

        result = await emit_notification(
            source_type=event_type,
            title=title,
            body=body,
            severity=severity,
            channel_key=channel,
            target_type="role",
            target_id=audience,
            metadata={
                "wiring_key": wiring["wiring_key"],
                "policy_key": policy["policy_key"],
                "source_engine": wiring["source_engine"],
                "payload": payload,
            },
            force_quiet_hour=policy.get("quiet_hour_bypass", False),
        )

        return {
            "status": "emitted",
            "wiring_key": wiring["wiring_key"],
            "policy_key": policy["policy_key"],
            "channel": channel,
            "severity": severity,
            "audience": audience,
            "cooldown": cooldown,
            "emit_result": result,
        }
    except Exception as e:
        logger.error("Emit failed for wiring %s: %s", wiring["wiring_key"], e)
        return {"status": "error", "reason": str(e), "wiring_key": wiring["wiring_key"]}


async def list_wirings(enabled_only: bool = True) -> List[Dict[str, Any]]:
    """Wiring 목록 조회."""
    try:
        sb = get_supabase()
        q = sb.table("notification_event_wiring_registry").select("*")
        if enabled_only:
            q = q.eq("enabled", True)
        resp = q.order("source_engine").execute()
        return resp.data or []
    except Exception as e:
        logger.error("List wirings failed: %s", e)
        return []


async def list_policies() -> List[Dict[str, Any]]:
    """정책 목록 조회."""
    try:
        sb = get_supabase()
        resp = sb.table("notification_policy_registry").select("*").order("policy_key").execute()
        return resp.data or []
    except Exception as e:
        logger.error("List policies failed: %s", e)
        return []
