"""Control Plane runner — orchestrates preflight → execute → result."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from services.public_data_sync.adapters import adapter_registry
from services.public_data_sync.contracts import RunContext, RunResult, RunStatus, TriggerKind
from services.public_data_sync.errors import PreflightError, SourceNotFoundError, AdapterNotRegisteredError
from services.public_data_sync.registry import registry

logger = logging.getLogger(__name__)


def run_source(
    source_id: str,
    *,
    trigger: TriggerKind = TriggerKind.MANUAL,
    params: dict | None = None,
) -> RunResult:
    """Run a single source through the control plane.

    Programming errors (unknown source_id, missing adapter): raise immediately.
    Runtime errors (preflight fail, adapter exception, source_id mismatch): return FAILED.
    """
    spec = registry.get(source_id)  # raises SourceNotFoundError if unknown

    adapter = adapter_registry.get(source_id)  # raises AdapterNotRegisteredError if missing

    ctx = RunContext(
        source_id=source_id,
        trigger=trigger,
        params=params or {},
        triggered_at=datetime.now(timezone.utc),
    )

    try:
        adapter.preflight(ctx)
    except PreflightError as exc:
        logger.warning("preflight failed source_id=%s error=%s", source_id, exc)
        return RunResult(
            source_id=source_id,
            status=RunStatus.FAILED,
            error=f"preflight: {exc}",
        )
    except Exception as exc:
        logger.error("preflight unexpected error source_id=%s", source_id, exc_info=True)
        return RunResult(
            source_id=source_id,
            status=RunStatus.FAILED,
            error=f"preflight unexpected: {type(exc).__name__}: {exc}",
        )

    try:
        result = adapter.execute(ctx)
    except Exception as exc:
        logger.error("adapter.execute raised source_id=%s", source_id, exc_info=True)
        return RunResult(
            source_id=source_id,
            status=RunStatus.FAILED,
            error=f"execute raised: {type(exc).__name__}: {exc}",
        )

    if result.source_id != source_id:
        logger.error(
            "source_id mismatch: expected=%s got=%s", source_id, result.source_id
        )
        return RunResult(
            source_id=source_id,
            status=RunStatus.FAILED,
            error=f"source_id mismatch: expected={source_id!r} got={result.source_id!r}",
        )

    return result
