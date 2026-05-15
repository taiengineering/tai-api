"""Integrity Hooks — Workflow → Integrity Layer 연결 인터페이스.

현재 단계: interface 정의만. 실제 evaluator 구현 금지.
"""

import logging
from typing import Protocol, Optional

logger = logging.getLogger("workflow_engine.integrity_hooks")


class WorkflowIntegrityHook(Protocol):
    """Workflow Integrity Hook Interface.

    구현체는 Integrity Layer에서 제공.
    현재 단계에서는 이 interface만 존재.
    """

    def on_transition(
        self, workflow_id: str, workflow_type: str,
        from_state: str, to_state: str, trace_id: Optional[str] = None,
    ) -> None:
        """정상 전이 발생 시 호출."""
        ...

    def on_timeout(
        self, workflow_id: str, workflow_type: str,
        current_state: str, trace_id: Optional[str] = None,
    ) -> None:
        """타임아웃 발생 시 호출."""
        ...

    def on_invalid_transition(
        self, workflow_id: str, workflow_type: str,
        from_state: str, to_state: str, trace_id: Optional[str] = None,
    ) -> None:
        """부적합 전이 시도 시 호출."""
        ...


class NoOpIntegrityHook:
    """Default no-op 구현. 로깅만 수행."""

    def on_transition(self, workflow_id, workflow_type, from_state, to_state, trace_id=None):
        logger.debug("NoOp: transition %s %s→%s", workflow_type, from_state, to_state)

    def on_timeout(self, workflow_id, workflow_type, current_state, trace_id=None):
        logger.debug("NoOp: timeout %s state=%s", workflow_type, current_state)

    def on_invalid_transition(self, workflow_id, workflow_type, from_state, to_state, trace_id=None):
        logger.warning("NoOp: invalid %s %s→%s", workflow_type, from_state, to_state)
