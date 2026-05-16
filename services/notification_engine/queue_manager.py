"""Queue Manager v4.0 — Preference Enforcement + CRITICAL Bypass.

Mute/Disabled/Quiet Hour 적용. Policy Audit 기록.
"""

import logging
from datetime import datetime, timezone, timedelta, time as dtime
from typing import List, Optional

logger = logging.getLogger("notification_engine.queue")


def create_queue_items(
    event_row: dict,
    recipients: List[dict],
    message_title: str,
    message_body: str,
    dedupe_key: Optional[str] = None,
    cooldown_minutes: int = 15,
) -> List[dict]:
    created = []
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        now = datetime.now(timezone.utc)
        trace_id = event_row.get("trace_id", "")
        severity = event_row.get("severity", "INFO")
        event_type = event_row.get("event_type", "")
        source_type = event_row.get("source_type") or event_row.get("source_domain", "")

        for recipient in recipients:
            channel = recipient.get("delivery_channel", "TELEGRAM")
            actor_id = recipient.get("user_id") or event_row.get("triggered_by")
            item_dedupe = dedupe_key or _build_dedupe_key(event_row, recipient)

            # === Preference Enforcement ===
            policy_result = _check_preferences(
                actor_id=actor_id, source_type=source_type or event_type,
                channel_key=channel, severity=severity, now=now,
                event_id=event_row.get("id"), trace_id=trace_id,
            )

            if policy_result == "SUPPRESSED":
                logger.info("Suppressed (preference): %s ch=%s trace=%s", actor_id, channel, trace_id)
                continue

            # Cooldown/Dedupe
            if _is_in_cooldown(sb, item_dedupe, cooldown_minutes, now):
                logger.info("Suppressed (cooldown): %s trace=%s", item_dedupe, trace_id)
                continue

            # Queue 생성
            row = {
                "runtime_event_id": event_row["id"],
                "recipient_user_id": actor_id or "00000000-0000-0000-0000-000000000000",
                "notification_type": event_type or "ALERT",
                "delivery_channel": channel,
                "delivery_status": "QUEUED" if policy_result != "QUIET_HOUR_DELAYED" else "QUIET_HOUR_DELAYED",
                "message_title": message_title[:200] if message_title else "",
                "message_body": message_body[:2000] if message_body else "",
                "dedupe_key": item_dedupe,
                "cooldown_until": (now + timedelta(minutes=cooldown_minutes)).isoformat(),
                "escalation_level": recipient.get("escalation_level", 0),
                "trace_id": trace_id,
                "source_trace": "NOTIFICATION_ENGINE_QUEUE",
            }

            if policy_result == "QUIET_HOUR_DELAYED":
                row["next_retry_at"] = _calc_quiet_hour_end(now).isoformat()

            resp = sb.table("runtime_notification_queue").insert(row).execute()
            if resp.data:
                created.append(resp.data[0])

    except Exception as e:
        logger.error("Queue creation failed: %s", e)

    logger.info("Queue created: %d items for event %s", len(created), event_row.get("id"))
    return created


def _check_preferences(
    actor_id: Optional[str], source_type: str, channel_key: str,
    severity: str, now: datetime, event_id: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> str:
    """Preference 검사 → ALLOWED / SUPPRESSED / QUIET_HOUR_DELAYED / CRITICAL_BYPASS."""
    if not actor_id:
        return "ALLOWED"

    try:
        from services.notification_engine.preference_service import is_channel_muted

        # CRITICAL bypass
        if severity == "CRITICAL":
            _log_policy(event_id, actor_id, source_type, channel_key,
                        "CRITICAL_BYPASS", "ALLOWED", "CRITICAL severity bypasses preference",
                        severity, trace_id)
            return "ALLOWED"

        # Mute / Disabled check
        if is_channel_muted(actor_id, source_type, channel_key):
            _log_policy(event_id, actor_id, source_type, channel_key,
                        "MUTE", "SUPPRESSED", "Channel muted or disabled by preference",
                        severity, trace_id)
            return "SUPPRESSED"

        # Quiet Hour check (KST)
        if _is_quiet_hour(actor_id, now):
            _log_policy(event_id, actor_id, source_type, channel_key,
                        "QUIET_HOUR", "DELAYED", "Within quiet hour",
                        severity, trace_id)
            return "QUIET_HOUR_DELAYED"

        return "ALLOWED"
    except Exception as e:
        logger.debug("Preference check failed (fail-open): %s", e)
        return "ALLOWED"


def _is_quiet_hour(actor_id: str, now: datetime) -> bool:
    """KST 기준 quiet hour 확인."""
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        resp = sb.table("notification_preference_registry") \
            .select("quiet_hour_enabled,quiet_hour_start,quiet_hour_end") \
            .eq("actor_id", actor_id) \
            .eq("quiet_hour_enabled", True) \
            .limit(1).execute()
        if not resp.data:
            return False
        pref = resp.data[0]
        start_str = pref.get("quiet_hour_start")
        end_str = pref.get("quiet_hour_end")
        if not start_str or not end_str:
            return False

        kst = now + timedelta(hours=9)
        current = kst.time()
        start = dtime.fromisoformat(start_str)
        end = dtime.fromisoformat(end_str)

        if start <= end:
            return start <= current <= end
        else:
            return current >= start or current <= end
    except Exception:
        return False


def _calc_quiet_hour_end(now: datetime) -> datetime:
    """KST 07:00 기본 종료 시각."""
    kst = now + timedelta(hours=9)
    next_morning = kst.replace(hour=7, minute=0, second=0, microsecond=0)
    if kst.hour >= 7:
        next_morning += timedelta(days=1)
    return next_morning - timedelta(hours=9)  # UTC 변환


def _log_policy(
    event_id, actor_id, source_type, channel_key,
    policy_type, policy_result, reason, severity, trace_id,
):
    try:
        from db.supabase_client import get_supabase
        get_supabase().table("runtime_notification_policy_audit").insert({
            "notification_id": event_id,
            "event_id": event_id,
            "actor_id": actor_id,
            "source_type": source_type,
            "channel_key": channel_key,
            "policy_type": policy_type,
            "policy_result": policy_result,
            "reason": reason,
            "severity": severity,
            "trace_id": trace_id,
        }).execute()
    except Exception as e:
        logger.debug("Policy audit log failed: %s", e)


def _build_dedupe_key(event_row: dict, recipient: dict) -> str:
    return f"{event_row.get('event_type')}_{event_row.get('source_engine')}_{recipient.get('recipient_source', 'OP')}"


def _is_in_cooldown(sb, dedupe_key: str, cooldown_minutes: int, now: datetime) -> bool:
    try:
        since = (now - timedelta(minutes=cooldown_minutes)).isoformat()
        resp = sb.table("runtime_notification_queue") \
            .select("id", count="exact") \
            .eq("dedupe_key", dedupe_key) \
            .gte("created_at", since) \
            .in_("delivery_status", ["QUEUED", "PROCESSING", "DELIVERED", "RETRY_PENDING", "QUIET_HOUR_DELAYED"]) \
            .execute()
        return (resp.count or 0) > 0
    except Exception:
        return False
