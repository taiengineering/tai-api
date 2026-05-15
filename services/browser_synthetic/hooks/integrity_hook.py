"""Synthetic → Integrity Hook.

현재 범위: interface 정의만.
Integrity Evaluator 직접 호출 금지.
Workflow 수정 금지.

향후 Integrity Layer와 연결되면:
  Synthetic Event → Event Layer → Integrity Evaluation
"""
from __future__ import annotations

import logging

from services.browser_synthetic.schemas import SyntheticEvent

logger = logging.getLogger(__name__)


async def emit_synthetic_integrity_event(
    event: SyntheticEvent,
) -> None:
    """Synthetic 결과를 Integrity Layer 연결용 hook.

    현재: 로그만 기록.
    향후: Event Layer → Integrity Evaluation 경유.
    """
    if event.execution_status != "SUCCESS":
        logger.warning(
            "[SYNTHETIC_INTEGRITY] check=%s status=%s dur=%sms trace=%s",
            event.synthetic_check,
            event.execution_status,
            event.duration_ms,
            event.trace_id,
        )
    else:
        logger.info(
            "[SYNTHETIC_OK] check=%s dur=%sms trace=%s",
            event.synthetic_check,
            event.duration_ms,
            event.trace_id,
        )
    # TODO: Event Layer 구현 후 event_layer.emit(event) 호출
    # 절대 금지: integrity evaluator 직접 호출
    # 절대 금지: workflow 상태 수정
