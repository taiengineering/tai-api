"""Alert Evaluator — Integrity Event → Alert 승격 여부 판단.

흐름:
  1. Integrity event 수신
  2. alert_rule_registry_v2 매칭
  3. Cooldown 확인
  4. Dedupe 확인
  5. workflow_alert_event 생성
  6. Notification hook (interface only)

Notification direct send 금지.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from services.time import now_kst

logger = logging.getLogger("workflow_alert.evaluator")


def evaluate_integrity_event(
    integrity_type: str,
    workflow_id: Optional[str] = None,
    integrity_event_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    payload: Optional[dict] = None,
    workflow_type: str = "COMMON",
) -> dict:
    """Integrity Event → Alert 승격 평가.

    Returns:
        {"alerts_created": int, "suppressed": int, "errors": int, "alerts": list}
    """
    stats = {"alerts_created": 0, "suppressed": 0, "errors": 0, "alerts": []}

    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()

        # 1. 매칭되는 rule 조회
        rules = _find_matching_rules(sb, integrity_type, workflow_type)

        if not rules:
            logger.debug("No alert rules for integrity_type=%s", integrity_type)
            return stats

        for rule in rules:
            try:
                _process_rule(sb, rule, workflow_id, integrity_event_id,
                              trace_id, tenant_id, payload or {}, stats)
            except Exception as e:
                logger.error("Rule %s failed: %s", rule.get("rule_code"), e)
                stats["errors"] += 1

    except Exception as e:
        logger.error("Alert evaluation failed: %s", e)
        stats["errors"] += 1

    return stats


def _find_matching_rules(sb, integrity_type: str, workflow_type: str) -> List[dict]:
    resp = sb.table("alert_rule_registry_v2") \
        .select("*") \
        .eq("integrity_type", integrity_type) \
        .eq("enabled", True) \
        .execute()
    rules = resp.data or []
    return [r for r in rules
            if r.get("workflow_type") in (workflow_type, "COMMON", "ALL")]


def _process_rule(sb, rule, workflow_id, integrity_event_id,
                  trace_id, tenant_id, payload, stats):
    rule_code = rule["rule_code"]
    severity = rule.get("severity_threshold", "WARNING")
    cooldown_sec = rule.get("cooldown_sec", 300)
    dedupe_enabled = rule.get("dedupe_enabled", True)
    escalation = rule.get("escalation_enabled", False)

    dedupe_key = f"{rule_code}_{workflow_id or 'global'}"

    # Cooldown
    if _is_in_cooldown(sb, dedupe_key, cooldown_sec):
        stats["suppressed"] += 1
        logger.debug("Alert suppressed (cooldown): %s", dedupe_key)
        return

    # Dedupe
    if dedupe_enabled and _is_duplicate(sb, dedupe_key):
        stats["suppressed"] += 1
        logger.debug("Alert suppressed (dedupe): %s", dedupe_key)
        return

    # Alert Event 생성
    alert_row = {
        "workflow_id": workflow_id,
        "integrity_event_id": integrity_event_id,
        "rule_code": rule_code,
        "alert_type": rule.get("integrity_type"),
        "severity": severity,
        "escalation_level": 1 if escalation else 0,
        "trace_id": trace_id,
        "tenant_id": tenant_id,
        "dedupe_key": dedupe_key,
        "payload": payload,
    }

    resp = sb.table("workflow_alert_event").insert(alert_row).execute()
    if resp.data:
        stats["alerts_created"] += 1
        stats["alerts"].append(resp.data[0])
        logger.info("Alert created: %s severity=%s trace=%s",
                    rule_code, severity, trace_id)

        # Notification hook (interface)
        _emit_notification_alert(resp.data[0])


def _is_in_cooldown(sb, dedupe_key: str, cooldown_sec: int) -> bool:
    try:
        since = (now_kst() - timedelta(seconds=cooldown_sec)).isoformat()
        resp = sb.table("workflow_alert_event") \
            .select("id", count="exact") \
            .eq("dedupe_key", dedupe_key) \
            .gte("created_at", since).execute()
        return (resp.count or 0) > 0
    except Exception:
        return False


def _is_duplicate(sb, dedupe_key: str) -> bool:
    try:
        resp = sb.table("workflow_alert_event") \
            .select("id", count="exact") \
            .eq("dedupe_key", dedupe_key) \
            .eq("resolved", False).execute()
        return (resp.count or 0) > 0
    except Exception:
        return False


def _emit_notification_alert(alert: dict):
    """Alert → Notification Runtime Hook.
    현재: pipeline.run_pipeline 호출.
    """
    try:
        from services.notification_engine.schemas import NotificationEventCreate
        from services.notification_engine.pipeline import run_pipeline
        from services.notification_engine.worker import process_queue

        severity = alert.get("severity", "WARNING")
        icon = "\U0001f6a8" if severity == "CRITICAL" else "\u26a0\ufe0f"

        event = NotificationEventCreate(
            event_type=alert.get("alert_type", "ALERT"),
            source_engine="alert_layer",
            severity=severity,
            trace_id=alert.get("trace_id"),
            tenant_id=alert.get("tenant_id"),
            payload={
                "alert_id": str(alert.get("id")),
                "rule_code": alert.get("rule_code"),
                "workflow_id": str(alert.get("workflow_id")) if alert.get("workflow_id") else None,
                **(alert.get("payload") or {}),
            },
            source_domain="alert_layer",
            source_entity_id=str(alert.get("id")),
        )

        run_pipeline(
            event=event,
            message_title=f"{icon} [{severity}] {alert.get('rule_code', 'ALERT')}",
            message_body=(
                f"\uc720\ud615: {alert.get('alert_type')}\n"
                f"Workflow: {alert.get('workflow_id') or '-'}\n"
                f"Rule: {alert.get('rule_code')}\n"
                f"Escalation: L{alert.get('escalation_level', 0)}"
            ),
            cooldown_minutes=int(alert.get("cooldown_sec", 300) / 60) or 5,
        )

        process_queue(limit=10)

    except Exception as e:
        logger.error("Notification hook failed for alert %s: %s",
                     alert.get("id"), e)
