"""Recipient Resolver — 누가 받아야 하는가 결정.

Phase 1 범위: operator / owner / manager 수준만 지원.
복잡한 조직도 엔진 금지.

resolution 방식:
  runtime_notification_recipient_rule 테이블 기반.
  event_type → recipient_source → 실제 user_id resolve.
"""

import logging
from typing import List

logger = logging.getLogger("notification_engine.resolver")

# recipient_source → resolve 로직 매핑
# Phase 1: OPERATOR (= 시스템 운영자, 환경변수 기반)
DEFAULT_OPERATOR_SOURCE = "OPERATOR"


def resolve_recipients(event_type: str, event_row: dict) -> List[dict]:
    """event_type에 매칭되는 recipient rule 조회 → 수신자 목록 반환.

    Returns:
        [{"user_id": str|None, "delivery_channel": str, "escalation_level": int}, ...]
    """
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()

        # 1. rule 조회
        resp = sb.table("runtime_notification_recipient_rule") \
            .select("*") \
            .eq("event_type", event_type) \
            .eq("active", True) \
            .order("escalation_level") \
            .execute()

        rules = resp.data or []

        if not rules:
            # fallback: OPERATOR rule 없으면 기본 operator 반환
            logger.info("No recipient rules for %s, using default OPERATOR", event_type)
            return [{
                "user_id": None,  # Telegram은 chat_id 기반이므로 user_id 불필요
                "delivery_channel": "TELEGRAM",
                "escalation_level": 0,
                "recipient_source": DEFAULT_OPERATOR_SOURCE,
            }]

        # 2. rule → recipient 변환
        recipients = []
        for rule in rules:
            resolved = _resolve_single(rule, event_row)
            if resolved:
                recipients.append(resolved)

        return recipients if recipients else [{
            "user_id": None,
            "delivery_channel": "TELEGRAM",
            "escalation_level": 0,
            "recipient_source": DEFAULT_OPERATOR_SOURCE,
        }]

    except Exception as e:
        logger.error("Recipient resolution failed for %s: %s", event_type, e)
        return [{
            "user_id": None,
            "delivery_channel": "TELEGRAM",
            "escalation_level": 0,
            "recipient_source": DEFAULT_OPERATOR_SOURCE,
        }]


def _resolve_single(rule: dict, event_row: dict) -> dict | None:
    """단일 rule → recipient dict."""
    source = rule.get("recipient_source", "OPERATOR")
    channel = rule.get("delivery_channel", "TELEGRAM")
    level = rule.get("escalation_level", 0)

    # Phase 1: OPERATOR는 user_id 없이 Telegram chat_id로 전달
    # OWNER / MANAGER 등은 payload에서 user_id 추출
    user_id = None
    if source == "OWNER":
        user_id = (event_row.get("payload") or {}).get("owner_id")
    elif source == "MANAGER":
        user_id = (event_row.get("payload") or {}).get("manager_id")
    elif source == "TRIGGERED_BY":
        user_id = event_row.get("triggered_by")

    return {
        "user_id": user_id,
        "delivery_channel": channel,
        "escalation_level": level,
        "recipient_source": source,
    }
