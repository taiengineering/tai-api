"""Public Data Runtime Orchestrator — claim → run → complete."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from services.public_data_sync.contracts import RunResult, RunStatus, TriggerKind
from services.public_data_sync.registry import registry
from services.public_data_sync.runtime_store import PublicDataRuntimeStore

logger = logging.getLogger(__name__)


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

    Returns None  → claim rejected (source disabled, not due, busy, etc.)
    Returns RunResult → execution attempted (success or failure).

    Programming errors (unknown source_id): raise immediately.
    All other errors: return FAILED RunResult + attempt complete.
    """
    from services.public_data_sync.runner import run_source

    if store is None:
        store = _default_store()

    spec = registry.get(source_id)  # raises SourceNotFoundError for unknown sources

    run_id = str(uuid4())
    now = datetime.now(timezone.utc)

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
        return None

    if not claim.claimed:
        logger.info(
            "claim skipped source_id=%s reason=%s",
            source_id, claim.reason,
        )
        return None

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
            error_message=f"{type(exc).__name__}: {exc}",
        )

    try:
        completed = store.complete_run(
            run_id=run_id,
            result=result,
            next_due_at=next_due_at,
            retry_not_before=retry_not_before,
        )
        if not completed:
            logger.warning(
                "complete_run fenced source_id=%s run_id=%s",
                source_id, run_id,
            )
    except Exception as exc:
        logger.error(
            "complete_run raised source_id=%s exception_type=%s",
            source_id, type(exc).__name__,
        )

    return result
