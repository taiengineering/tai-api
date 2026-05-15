"""Recovery Recommendation Engine — 운영자 대응 보조.

자동 복구 금지. 추천만 제공.
"""

import logging
from typing import Optional

logger = logging.getLogger("watch_engine.recovery")


def get_recovery_recommendation(
    sb,
    flow_key: str,
    event_type: str,
) -> Optional[dict]:
    """Get recovery recommendation from registry.

    Returns:
        {"recovery_type": str, "recovery_title": str,
         "recovery_description": str, "classification": str,
         "requires_human": bool}
        or None if no match.
    """
    try:
        resp = sb.table("workflow_recovery_registry") \
            .select("*") \
            .eq("flow_key", flow_key) \
            .eq("issue_type", event_type) \
            .eq("enabled", True) \
            .limit(1).execute()

        if not resp.data:
            return _get_generic_recommendation(event_type)

        r = resp.data[0]
        return {
            "recovery_type": r["recovery_type"],
            "recovery_title": r["recovery_title"],
            "recovery_description": r.get("recovery_description", ""),
            "classification": r.get("recovery_classification", "HUMAN_REQUIRED"),
            "requires_human": r.get("requires_human_confirmation", True),
        }
    except Exception as e:
        logger.error("Recovery recommendation failed: %s", e)
        return _get_generic_recommendation(event_type)


def _get_generic_recommendation(event_type: str) -> dict:
    """Generic fallback recommendations."""
    generics = {
        "field_mismatch": {
            "recovery_type": "CHECK_DATA_MAPPING",
            "recovery_title": "\ub370\uc774\ud130 \ub9e4\ud551 \ud655\uc778",
            "recovery_description": "submit\uacfc read \uac12 \ubd88\uc77c\uce58 \u2014 \ub370\uc774\ud130 \ubcc0\ud658 \ub85c\uc9c1 \uc810\uac80",
            "classification": "INVESTIGATION_REQUIRED",
            "requires_human": True,
        },
        "stuck_detected": {
            "recovery_type": "CHECK_WORKFLOW_STATE",
            "recovery_title": "\uc6cc\ud06c\ud50c\ub85c\uc6b0 \uc0c1\ud0dc \ud655\uc778",
            "recovery_description": "\ud750\ub984 \uc911\ub2e8 \u2014 API/DB \uc0c1\ud0dc \uc810\uac80",
            "classification": "HUMAN_REQUIRED",
            "requires_human": True,
        },
        "timeout_exceeded": {
            "recovery_type": "CHECK_PERFORMANCE",
            "recovery_title": "\uc131\ub2a5 \uc810\uac80",
            "recovery_description": "\uc751\ub2f5 \uc9c0\uc5f0 \u2014 \uc11c\ubc84 \ubd80\ud558 \ub610\ub294 DB \uc131\ub2a5 \ud655\uc778",
            "classification": "HUMAN_REQUIRED",
            "requires_human": True,
        },
        "sla_critical": {
            "recovery_type": "CHECK_SLA_ROOT_CAUSE",
            "recovery_title": "SLA \uc6d0\uc778 \ud655\uc778",
            "recovery_description": "SLA \uc704\ubc18 \u2014 \ubcd1\ubaa9 \ubd84\uc11d \ud544\uc694",
            "classification": "HUMAN_REQUIRED",
            "requires_human": True,
        },
        "selector_not_found": {
            "recovery_type": "VERIFY_SELECTOR",
            "recovery_title": "Selector \ud655\uc778",
            "recovery_description": "data-testid \ubcc0\uacbd \uc5ec\ubd80 \ud655\uc778",
            "classification": "HUMAN_REQUIRED",
            "requires_human": True,
        },
        "repeated_failure": {
            "recovery_type": "INVESTIGATE_ROOT_CAUSE",
            "recovery_title": "\uadfc\ubcf8 \uc6d0\uc778 \uc870\uc0ac",
            "recovery_description": "\ubc18\ubcf5 \uc7a5\uc560 \u2014 \uadfc\ubcf8 \uc6d0\uc778 \ubd84\uc11d \ud544\uc694",
            "classification": "INVESTIGATION_REQUIRED",
            "requires_human": True,
        },
        "workflow_instability": {
            "recovery_type": "STABILIZE_WORKFLOW",
            "recovery_title": "\uc6cc\ud06c\ud50c\ub85c\uc6b0 \uc548\uc815\ud654",
            "recovery_description": "\ubcf5\ud569 \uc7a5\uc560 \u2014 \uc804\uccb4 \ud750\ub984 \uc810\uac80 \ud544\uc694",
            "classification": "INVESTIGATION_REQUIRED",
            "requires_human": True,
        },
    }
    return generics.get(event_type, {
        "recovery_type": "GENERAL_CHECK",
        "recovery_title": "\uc77c\ubc18 \uc810\uac80",
        "recovery_description": "\uc774\uc288 \ud655\uc778 \ud544\uc694",
        "classification": "HUMAN_REQUIRED",
        "requires_human": True,
    })
