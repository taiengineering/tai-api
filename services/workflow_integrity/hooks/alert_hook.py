"""Integrity → Alert Hook.

현재 범위: interface 정의만.
Alert Runtime 직접 구현 금지.
Notification direct send 금지.

향후 Alert Layer가 구현되면 이 hook을 통해 연결한다:
  Integrity Event → Alert Layer → Notification Runtime
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


async def emit_integrity_alert(
    workflow_id: UUID,
    rule_code: str,
    severity: str,
    message: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Integrity 이상 탐지 시 Alert Layer로 전달하는 hook.

    현재: 로그만 기록.
    향후: Alert Layer → Notification Runtime 경유.
    """
    logger.warning(
        "[INTEGRITY_ALERT] workflow=%s rule=%s severity=%s msg=%s",
        workflow_id,
        rule_code,
        severity,
        message,
    )
    # TODO: Alert Layer 구현 후 여기서 alert_layer.create_alert() 호출
    # 절대 금지: notification 직접 호출
