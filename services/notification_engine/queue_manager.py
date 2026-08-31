"""Queue Manager v4.1 — Quiet Hour 종료 시각 preference 기반 계산."""

import logging
from datetime import datetime, timezone, timedelta, time as dtime
from typing import List, Optional
from services.time import now_kst

logger = logging.getLogger("notification_engine.queue")


def create_queue_items(
    event_row: dict,
    recipients: List[dict],
    message_title: str,
    message_body: str,
    dedupe_key: Optional[str] = None,
    cooldown_minutes: int = 15,
    force_quiet_hour: bool = False,
) -> List[dict]:
    created = []
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        now = now_kst()
        trace_id = event_row.get("trace_id", "")
        severity = event_row.get("severity", "INFO")
        event_type = event_row.get("event_type", "")
        source_type = event_row.get("source_type") or event_row.get("source_domain", "")

        for recipient in recipients:
            channel = recipient.get("delivery_channel", "TELEGRAM")
            actor_id = recipient.get("user_id") or event_row.get("triggered_by")
            item_dedupe = dedupe_key or _build_dedupe_key(event_row, recipient)

            # Preference Enforcement
            policy_result = _check_preferences(
                actor_id=actor_id, source_type=source_type or event_type,
                channel_key=channel, severity=severity, now=now,
                event_id=event_row.get("id"), trace_id=trace_id,
                force_quiet_hour=force_quiet_hour,
            )

            if policy_result == "SUPPRESSED":
                continue

            if _is_in_cooldown(sb, item_dedupe, cooldown_minutes, now):
                continue

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
                qh_end = _calc_quiet_hour_end_for_actor(actor_id, now)
                row["next_retry_at"] = qh_end.isoformat()
                _log_policy(event_row.get("id"), actor_id, source_type or event_type,
                            channel, "QUIET_HOUR", "DELAYED",
                            f"Delayed until {qh_end.isoformat()}",
                            severity, trace_id)

            resp = sb.table("runtime_notification_queue").insert(row).execute()
            if resp.data:
                created.append(resp.data[0])

    except Exception as e:
        logger.error("Queue creation failed: %s", e)

    logger.info("Queue created: %d items for event %s", len(created), event_row.get("id"))
    return created


def _check_preferences(
    actor_id, source_type, channel_key, severity, now,
    event_id=None, trace_id=None, force_quiet_hour=False,
) -> str:
    if not actor_id:
        return "ALLOWED"
    try:
        from services.notification_engine.preference_service import is_channel_muted

        if severity == "CRITICAL" and not force_quiet_hour:
            _log_policy(event_id, actor_id, source_type, channel_key,
                        "CRITICAL_BYPASS", "ALLOWED", "CRITICAL bypasses preference",
                        severity, trace_id)
            return "ALLOWED"

        if not force_quiet_hour and is_channel_muted(actor_id, source_type, channel_key):
            _log_policy(event_id, actor_id, source_type, channel_key,
                        "MUTE", "SUPPRESSED", "Muted or disabled",
                        severity, trace_id)
            return "SUPPRESSED"

        if force_quiet_hour or _is_quiet_hour(actor_id, now):
            return "QUIET_HOUR_DELAYED"

        return "ALLOWED"
    except Exception:
        return "ALLOWED"


def _is_quiet_hour(actor_id: str, now: datetime) -> bool:
    try:
        from db.supabase_client import get_supabase
        resp = get_supabase().table("notification_preference_registry") \
            .select("quiet_hour_enabled,quiet_hour_start,quiet_hour_end") \
            .eq("actor_id", actor_id).eq("quiet_hour_enabled", True) \
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


def _calc_quiet_hour_end_for_actor(actor_id: Optional[str], now: datetime) -> datetime:
    """Preference의 quiet_hour_end 기반 계산. KST."""
    end_time_str = None
    if actor_id:
        try:
            from db.supabase_client import get_supabase
            resp = get_supabase().table("notification_preference_registry") \
                .select("quiet_hour_end") \
                .eq("actor_id", actor_id).eq("quiet_hour_enabled", True) \
                .limit(1).execute()
            if resp.data:
                end_time_str = resp.data[0].get("quiet_hour_end")
        except Exception:
            pass

    kst = now + timedelta(hours=9)
    if end_time_str:
        try:
            end_t = dtime.fromisoformat(end_time_str)
        except Exception:
            end_t = dtime(7, 0)
    else:
        end_t = dtime(7, 0)

    target = kst.replace(hour=end_t.hour, minute=end_t.minute, second=0, microsecond=0)
    if kst.time() >= end_t:
        target += timedelta(days=1)
    return target - timedelta(hours=9)  # UTC


def _log_policy(event_id, actor_id, source_type, channel_key,
                policy_type, policy_result, reason, severity, trace_id):
    try:
        from db.supabase_client import get_supabase
        get_supabase().table("runtime_notification_policy_audit").insert({
            "notification_id": event_id, "event_id": event_id,
            "actor_id": actor_id, "source_type": source_type,
            "channel_key": channel_key, "policy_type": policy_type,
            "policy_result": policy_result, "reason": reason,
            "severity": severity, "trace_id": trace_id,
        }).execute()
    except Exception as e:
        logger.debug("Policy audit log failed: %s", e)


def _build_dedupe_key(event_row, recipient):
    return f"{event_row.get('event_type')}_{event_row.get('source_engine')}_{recipient.get('recipient_source', 'OP')}"


def _is_in_cooldown(sb, dedupe_key, cooldown_minutes, now):
    try:
        since = (now - timedelta(minutes=cooldown_minutes)).isoformat()
        resp = sb.table("runtime_notification_queue") \
            .select("id", count="exact").eq("dedupe_key", dedupe_key) \
            .gte("created_at", since) \
            .in_("delivery_status", ["QUEUED", "PROCESSING", "DELIVERED",
                                     "RETRY_PENDING", "QUIET_HOUR_DELAYED"]) \
            .execute()
        return (resp.count or 0) > 0
    except Exception:
        return False
