"""Workflow Event Emitter — 상태 변화 → Platform Event 생성.

Workflow Engine은 직접 Notification 호출 금지.
반드시: Workflow Event → Notification Runtime 경유.
"""

import logging
from typing import Optional
from workflow_engine.contracts.event_contract import WorkflowEventContract
from workflow_engine.registry.transition_registry import (
    is_valid_transition, get_transition_detail,
)

logger = logging.getLogger("workflow_engine.events.emitter")


def emit_workflow_event(event: WorkflowEventContract) -> dict:
    """Workflow 상태 변화 이벤트 발행.

    1. Transition 검증
    2. workflow_event_log INSERT
    3. Notification Runtime으로 Event 전달

    Returns:
        {"event_log": dict|None, "notification": dict|None, "error": str|None}
    """
    result = {"event_log": None, "notification": None, "error": None}

    try:
        # 1. Transition 검증 (선택적: from_state가 있을 때만)
        if event.from_state:
            if not is_valid_transition(
                event.from_state, event.workflow_state, event.workflow_type
            ):
                result["error"] = (
                    f"Invalid transition: {event.from_state} → {event.workflow_state} "
                    f"(type={event.workflow_type})"
                )
                logger.warning(result["error"])
                # Integrity hook: invalid transition
                _on_invalid_transition(event)
                return result

            # emit_event_type override from registry
            detail = get_transition_detail(
                event.from_state, event.workflow_state, event.workflow_type
            )
            if detail and detail.get("emit_event_type") and not event.event_type:
                event.event_type = detail["emit_event_type"]

        # 2. Event Log INSERT
        from db.supabase_client import get_supabase
        sb = get_supabase()

        log_row = event.to_event_log_row()
        resp = sb.table("workflow_event_log").insert(log_row).execute()
        result["event_log"] = resp.data[0] if resp.data else None

        logger.info(
            "Workflow event: %s %s→%s trace=%s",
            event.workflow_type, event.from_state, event.workflow_state,
            log_row.get("trace_id"),
        )

        # 3. Notification Runtime으로 전달 (간접 경유)
        notif_result = _emit_to_notification_runtime(event)
        result["notification"] = notif_result

        # 4. Integrity hook: on_transition
        _on_transition(event)

    except Exception as e:
        logger.error("Workflow event emission failed: %s", e)
        result["error"] = str(e)

    return result


def _emit_to_notification_runtime(event: WorkflowEventContract) -> Optional[dict]:
    """Workflow Event → Notification Runtime Pipeline."""
    try:
        from services.notification_engine.schemas import NotificationEventCreate
        from services.notification_engine.pipeline import run_pipeline

        notif_dict = event.to_notification_event_dict()
        notif_event = NotificationEventCreate(**notif_dict)

        title = f"\u2699\ufe0f [{event.workflow_type}] {event.event_type}"
        body = (
            f"\uc0c1\ud0dc: {event.from_state or '-'} \u2192 {event.workflow_state}\n"
            f"\uc804\uc774: {event.transition or '-'}\n"
            f"Workflow: {event.workflow_id}"
        )

        return run_pipeline(
            event=notif_event,
            message_title=title,
            message_body=body,
            cooldown_minutes=5,
        )
    except Exception as e:
        logger.error("Notification relay failed: %s", e)
        return None


# ===== Integrity Hooks (interface only) =====

def _on_transition(event: WorkflowEventContract):
    """Hook: 정상 전이 발생 시. 현재 단계: logging only."""
    logger.debug("integrity_hook.on_transition: %s %s→%s",
                 event.workflow_type, event.from_state, event.workflow_state)


def _on_invalid_transition(event: WorkflowEventContract):
    """Hook: 부적합 전이 시도. 현재 단계: logging only."""
    logger.warning("integrity_hook.on_invalid_transition: %s %s→%s",
                   event.workflow_type, event.from_state, event.workflow_state)


def _on_timeout(event: WorkflowEventContract):
    """Hook: 타임아웃 발생. 현재 단계: interface 정의만."""
    logger.warning("integrity_hook.on_timeout: %s workflow=%s",
                   event.workflow_type, event.workflow_id)
