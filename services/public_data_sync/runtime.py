"""Public Data Runtime Orchestrator — claim → run → complete."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from services.public_data_sync.contracts import RunResult, RunStatus, TriggerKind
from services.public_data_sync.errors import (
    RuntimeClaimError,
    RuntimeCompletionError,
    RuntimeFencedError,
    RuntimeHeartbeatError,
)
from services.public_data_sync.heartbeat import HeartbeatSupervisor
from services.public_data_sync.registry import registry
from services.public_data_sync.runtime_store import PublicDataRuntimeStore

logger = logging.getLogger(__name__)

# Claim rejection reasons that are expected business outcomes — return None, do not raise.
# Anything not in this set is a DB invariant violation or unexpected state — raise RuntimeClaimError.
_NORMAL_CLAIM_REJECTIONS = frozenset({
    "DISABLED",
    "NOT_DUE",
    "RETRY_NOT_BEFORE",
    "SOURCE_BUSY",
    "CREDENTIAL_BUSY",
    "RATE_LIMIT_BUSY",
    "SOURCE_LIMIT_UNSUPPORTED",
})


def _default_store() -> PublicDataRuntimeStore:
    return PublicDataRuntimeStore()


def execute_due_source(
    source_id: str,
    *,
    store: PublicDataRuntimeStore | None = None,
    trigger: TriggerKind = TriggerKind.SCHEDULED,
    lease_seconds: int = 900,
    scheduled_for: datetime | None = None,
    next_due_at: datetime | None = None,
    retry_not_before: datetime | None = None,
    metadata: dict[str, Any] | None = None,
) -> RunResult | None:
    """Orchestrate a single source execution through the runtime claim path.

    Returns None        → normal claim rejection (DISABLED, NOT_DUE, busy, etc.)
    Returns RunResult   → execution attempted (SUCCESS, FAILED, NO_CHANGE, …)

    Raises:
        SourceNotFoundError     — unknown source_id (programming error)
        RuntimeClaimError       — DB/RPC failure or invariant violation during claim_run
        RuntimeCompletionError  — DB/RPC failure during complete_run
        RuntimeFencedError      — complete_run rejected (source ownership lost)
    """
    from services.public_data_sync.runner import run_source

    if store is None:
        store = _default_store()

    spec = registry.get(source_id)  # raises SourceNotFoundError for unknown sources

    run_id = str(uuid4())
    now = datetime.now(timezone.utc)

    # claim_run: DB/RPC failures must propagate — callers must not treat as SKIP.
    # Raw exception chained with `from None` to prevent secret leakage via traceback.
    try:
        claim = store.claim_run(
            run_id=run_id,
            spec=spec,
            trigger=trigger,
            scheduled_for=scheduled_for,
            now=now,
            lease_seconds=lease_seconds,
        )
    except Exception as exc:
        logger.error(
            "claim_run failed source_id=%s exception_type=%s",
            source_id, type(exc).__name__,
        )
        raise RuntimeClaimError(source_id=source_id) from None

    if not claim.claimed:
        if claim.reason in _NORMAL_CLAIM_REJECTIONS:
            logger.info(
                "claim skipped source_id=%s reason=%s",
                source_id, claim.reason,
            )
            return None
        # Unexpected reason — DB invariant violation or new contract code not yet in allowlist.
        logger.error(
            "claim invariant violation source_id=%s reason=%s",
            source_id, claim.reason,
        )
        raise RuntimeClaimError(source_id=source_id, reason=claim.reason)

    supervisor = HeartbeatSupervisor(
        run_id=run_id,
        source_id=source_id,
        store_factory=_default_store,
        lease_seconds=lease_seconds,
    )
    supervisor.start()

    result: RunResult | None = None
    try:
        result = run_source(
            source_id,
            trigger=trigger,
            run_id=run_id,
            started_at=now,
            metadata=metadata,
        )
    except Exception as exc:
        logger.error(
            "run_source raised source_id=%s exception_type=%s",
            source_id, type(exc).__name__,
        )
        result = RunResult(
            run_id=run_id,
            source_id=source_id,
            status=RunStatus.FAILED,
            started_at=now,
            finished_at=datetime.now(timezone.utc),
            error_code="ORCHESTRATOR_EXCEPTION",
            error_message=type(exc).__name__,
        )
    finally:
        supervisor.stop()

    # Heartbeat failure is fail-closed: skip complete_run and raise the appropriate error.
    if supervisor.failed_reason == "LEASE_LOST":
        logger.warning(
            "heartbeat lost lease source_id=%s run_id=%s",
            source_id, run_id,
        )
        raise RuntimeFencedError(run_id=run_id, source_id=source_id)
    if supervisor.failed_reason == "HEARTBEAT_INFRA_ERROR":
        logger.error(
            "heartbeat infra error source_id=%s run_id=%s",
            source_id, run_id,
        )
        raise RuntimeHeartbeatError(
            run_id=run_id, source_id=source_id, reason="HEARTBEAT_INFRA_ERROR"
        )

    # complete_run: DB/RPC failures are infrastructure errors.
    # A FAILED adapter result with successful persistence is still returned normally.
    # Raw exception chained with `from None` to prevent secret leakage via traceback.
    try:
        completed = store.complete_run(
            run_id=run_id,
            result=result,
            next_due_at=next_due_at,
            retry_not_before=retry_not_before,
        )
    except Exception as exc:
        logger.error(
            "complete_run failed source_id=%s run_id=%s exception_type=%s",
            source_id, run_id, type(exc).__name__,
        )
        raise RuntimeCompletionError(run_id=run_id) from None

    if not completed:
        logger.warning(
            "complete_run fenced source_id=%s run_id=%s",
            source_id, run_id,
        )
        raise RuntimeFencedError(run_id=run_id, source_id=source_id)

    return result
