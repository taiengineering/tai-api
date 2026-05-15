"""Alert Engine v2.0 — Notification Engine Phase 1 전환.

Integrity Event → Alert Rule 판정 → Cooldown/Dedupe → Notification Pipeline.

v2.0 변경사항:
  - Telegram 직접 발송 제거
  - Notification Engine Pipeline으로 전환
  - Worker 동기 실행 (이벤트 → Queue → 발송 즉시 처리)

Fail-safe: 절대 서비스 영향 없음.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger("watch_engine.alert.engine")


def evaluate_and_alert(now: Optional[datetime] = None) -> dict:
    """Alert Rule 기반 알림 평가 + Notification Pipeline 발송.

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

        # 2. Worker 동기 실행 — Queue에 쌓인 항목 즉시 발송
        try:
            from services.notification_engine.worker import process_queue
            worker_stats = process_queue(limit=50)
            logger.info("Worker sync run: %s", worker_stats)
        except Exception as e:
            logger.error("Worker sync run failed: %s", e)

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

    # Build message
    sample = resp.data[0] if resp.data else {}
    message_title, message_body = _build_message_parts(rule, count, sample)
    dedupe_key = f"{rule_key}_{event_type}"

    # === Notification Engine Pipeline ===
    try:
        from services.notification_engine.schemas import NotificationEventCreate
        from services.notification_engine.pipeline import run_pipeline

        event = NotificationEventCreate(
            event_type=event_type,
            source_engine="watch_engine",
            severity=severity or "WARNING",
            trace_id=f"WATCH-{rule_key}-{now.strftime('%Y%m%d%H%M')}",
            payload={
                "rule_key": rule_key,
                "count": count,
                "threshold_minutes": threshold_minutes,
                "sample_flow_key": sample.get("flow_key"),
                "sample_description": (sample.get("description") or "")[:200],
                "integrity_event_id": sample.get("id"),
            },
            source_domain="watch_engine.alert",
            source_entity_id=sample.get("id"),
        )

        result = run_pipeline(
            event=event,
            message_title=message_title,
            message_body=message_body,
            cooldown_minutes=cooldown_minutes,
            dedupe_key=dedupe_key,
        )

        if result.get("queued"):
            stats["alerts_sent"] += 1
        elif result.get("error"):
            stats["errors"] += 1
        else:
            stats["suppressed"] += 1

    except Exception as e:
        logger.error("Notification pipeline failed for %s: %s", rule_key, e)
        stats["errors"] += 1

    # alert_history 기록 (하위 호환)
    try:
        sb.table("alert_history").insert({
            "rule_key": rule_key,
            "event_type": event_type,
            "flow_key": sample.get("flow_key"),
            "severity": severity,
            "channel": "notification_engine",
            "message": (message_title + "\n" + message_body)[:500],
            "success": bool(result.get("queued")),
            "error_message": result.get("error"),
            "dedupe_key": dedupe_key,
            "integrity_event_id": sample.get("id"),
        }).execute()
    except Exception as e:
        logger.error("alert_history insert failed: %s", e)


def _build_message_parts(rule: dict, count: int, sample: dict) -> tuple[str, str]:
    """Title + Body 분리 (기존 _build_message 대체)."""
    severity = rule.get("severity", "")
    icon = "\U0001f6a8" if severity == "CRITICAL" else "\u26a0\ufe0f"

    title = f"{icon} [{severity}] {rule.get('rule_name', rule['rule_key'])}"
    body = (
        f"\uc720\ud615: {rule['event_type']}\n"
        f"\ubc1c\uc0dd: {count}\ud68c (\ucd5c\uadfc {rule.get('threshold_minutes', 5)}\ubd84)\n"
        f"\ud750\ub984: {sample.get('flow_key', '-')}\n"
        f"\uc124\uba85: {(sample.get('description') or '-')[:100]}\n"
        f"\u2500\u2500\u2500\n"
        f"Watch Engine v2.0 via Notification Engine"
    )
    return title, body


# === Legacy 호환 — _send_telegram 유지 (test endpoint용) ===
def _send_telegram(message: str) -> tuple[bool, str | None]:
    """Legacy 호환. test endpoint에서만 사용.
    Phase 2에서 제거 예정.
    """
    from services.notification_engine.adapters.telegram import send
    return send(message)
