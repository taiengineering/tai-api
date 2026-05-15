"""Alert Engine — 진짜 중요한 문제만 알림.

Integrity Event → Alert Rule 판정 → Cooldown/Dedupe → Telegram 발송.
Fail-safe: 절대 서비스 영향 없음.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger("watch_engine.alert.engine")


def evaluate_and_alert(now: Optional[datetime] = None) -> dict:
    """Alert Rule 기반 알림 평가 + 발송.

    Returns:
        {"rules_checked": int, "alerts_sent": int, "suppressed": int, "errors": int}
    """
    stats = {"rules_checked": 0, "alerts_sent": 0, "suppressed": 0, "errors": 0}
    if now is None:
        now = datetime.now(timezone.utc)

    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()

        # 1. Load active rules
        rules = sb.table("alert_rule_registry") \
            .select("*").eq("enabled", True).execute()

        for rule in (rules.data or []):
            stats["rules_checked"] += 1
            try:
                _process_rule(sb, rule, now, stats)
            except Exception as e:
                logger.error("Alert rule %s failed: %s", rule.get("rule_key"), e)
                stats["errors"] += 1

    except Exception as e:
        logger.error("Alert engine failed: %s", e)
        stats["errors"] += 1

    logger.info(
        "Alert: %d rules, %d sent, %d suppressed, %d errors",
        stats["rules_checked"], stats["alerts_sent"],
        stats["suppressed"], stats["errors"],
    )
    return stats


def _process_rule(sb, rule: dict, now: datetime, stats: dict):
    """Single alert rule processing."""
    rule_key = rule["rule_key"]
    event_type = rule["event_type"]
    severity = rule.get("severity")
    threshold_count = rule.get("threshold_count", 1)
    threshold_minutes = rule.get("threshold_minutes", 5)
    cooldown_minutes = rule.get("cooldown_minutes", 15)
    muted_until = rule.get("muted_until")

    # Mute check
    if muted_until:
        try:
            mute_dt = datetime.fromisoformat(str(muted_until).replace("Z", "+00:00"))
            if now < mute_dt:
                stats["suppressed"] += 1
                return
        except (ValueError, TypeError):
            pass

    # Count recent matching events
    since = (now - timedelta(minutes=threshold_minutes)).isoformat()
    q = sb.table("engine_integrity_event") \
        .select("id,flow_key,description,created_at", count="exact") \
        .eq("event_type", event_type) \
        .eq("resolved", False).eq("ignored", False) \
        .gte("created_at", since) \
        .not_.is_("trace_id", "null")
    if severity:
        q = q.eq("severity", severity)
    resp = q.execute()

    count = resp.count or 0
    if count < threshold_count:
        return  # Below threshold

    # Dedupe key
    dedupe_key = f"{rule_key}_{event_type}"

    # Cooldown check
    cooldown_since = (now - timedelta(minutes=cooldown_minutes)).isoformat()
    recent_alerts = sb.table("alert_history") \
        .select("id", count="exact") \
        .eq("dedupe_key", dedupe_key) \
        .gte("sent_at", cooldown_since) \
        .eq("success", True) \
        .execute()

    if (recent_alerts.count or 0) > 0:
        stats["suppressed"] += 1
        return  # Still in cooldown

    # Build message
    sample = resp.data[0] if resp.data else {}
    message = _build_message(rule, count, sample)

    # Send
    channel = rule.get("notify_channel", "telegram")
    success = False
    error_msg = None

    if channel == "telegram":
        success, error_msg = _send_telegram(message)
    else:
        logger.warning("Unknown channel: %s", channel)
        error_msg = f"Unknown channel: {channel}"

    # Record history
    sb.table("alert_history").insert({
        "rule_key": rule_key,
        "event_type": event_type,
        "flow_key": sample.get("flow_key"),
        "severity": severity,
        "channel": channel,
        "message": message[:500],
        "success": success,
        "error_message": error_msg,
        "dedupe_key": dedupe_key,
        "integrity_event_id": sample.get("id"),
    }).execute()

    if success:
        stats["alerts_sent"] += 1
    else:
        stats["errors"] += 1


def _build_message(rule: dict, count: int, sample: dict) -> str:
    severity = rule.get("severity", "")
    icon = "\U0001f6a8" if severity == "CRITICAL" else "\u26a0\ufe0f"
    return (
        f"{icon} [{severity}] {rule.get('rule_name', rule['rule_key'])}\n"
        f"\uc720\ud615: {rule['event_type']}\n"
        f"\ubc1c\uc0dd: {count}\ud68c (\ucd5c\uadfc {rule.get('threshold_minutes', 5)}\ubd84)\n"
        f"\ud750\ub984: {sample.get('flow_key', '-')}\n"
        f"\uc124\uba85: {(sample.get('description') or '-')[:100]}\n"
        f"\u2500\u2500\u2500\n"
        f"Watch Engine v1.2"
    )


def _send_telegram(message: str) -> tuple[bool, str | None]:
    """Telegram Bot API 발송. Fail-safe."""
    import os
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if not bot_token or not chat_id:
        logger.warning("Telegram not configured (TELEGRAM_BOT_TOKEN/CHAT_ID missing)")
        return False, "Telegram not configured"

    try:
        import requests
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        resp = requests.post(url, json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
        }, timeout=10)

        if resp.status_code == 200:
            return True, None
        else:
            return False, f"Telegram {resp.status_code}: {resp.text[:200]}"
    except Exception as e:
        logger.error("Telegram send failed: %s", e)
        return False, str(e)[:200]
