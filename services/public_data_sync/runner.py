"""Control Plane runner — orchestrates preflight → run → result validation."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from services.public_data_sync.adapters import adapter_registry, register_builtin_adapters
from services.public_data_sync.contracts import (
    RunContext,
    RunResult,
    RunStatus,
    TriggerKind,
)
from services.public_data_sync.errors import (
    AdapterNotRegisteredError,
    PreflightError,
    SourceNotFoundError,
)
from services.public_data_sync.registry import registry

logger = logging.getLogger(__name__)


def run_source(
    source_id: str,
    *,
    trigger: TriggerKind = TriggerKind.MANUAL,
    dry_run: bool = False,
    request_budget: int | None = None,
    deadline: datetime | None = None,
    metadata: dict[str, Any] | None = None,
    run_id: str | None = None,
    started_at: datetime | None = None,
) -> RunResult:
    """Run a single source through the control plane.

    Programming errors (unknown source_id, missing adapter): raise immediately.
    Runtime errors (preflight fail, adapter exception, result mismatch): return FAILED.

    run_id / started_at may be supplied by the runtime orchestrator (claim path).
    When omitted, both are generated here (backward-compatible).
    """
    spec = registry.get(source_id)       # raises SourceNotFoundError
    register_builtin_adapters()           # idempotent — builtins always available
    adapter = adapter_registry.get(spec.adapter_key)  # raises AdapterNotRegisteredError

    run_id = run_id or str(uuid4())
    started_at = started_at or datetime.now(timezone.utc)

    ctx = RunContext(
        run_id=run_id,
        source_id=source_id,
        trigger=trigger,
        dry_run=dry_run,
        started_at=started_at,
        request_budget=request_budget,
        deadline=deadline,
        metadata=metadata or {},
    )

    def _fail(error_code: str, error_message: str) -> RunResult:
        return RunResult(
            run_id=run_id,
            source_id=source_id,
            status=RunStatus.FAILED,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            error_code=error_code,
            error_message=error_message,
        )

    try:
        adapter.preflight(ctx)
    except PreflightError as exc:
        logger.warning(
            "preflight failed source_id=%s error_code=PREFLIGHT_ERROR exception_type=%s",
            source_id, type(exc).__name__,
        )
        return _fail("PREFLIGHT_ERROR", f"preflight: {exc}")
    except Exception as exc:
        logger.error(
            "preflight unexpected error source_id=%s exception_type=%s",
            source_id, type(exc).__name__,
        )
        return _fail("PREFLIGHT_UNEXPECTED", f"{type(exc).__name__}: {exc}")

    try:
        result = adapter.run(ctx)
    except Exception as exc:
        logger.error(
            "adapter.run raised source_id=%s exception_type=%s",
            source_id, type(exc).__name__,
        )
        return _fail("EXECUTE_EXCEPTION", f"{type(exc).__name__}: {exc}")

    if result.started_at is None:
        result.started_at = started_at
    if result.finished_at is None:
        result.finished_at = datetime.now(timezone.utc)

    if result.source_id != source_id:
        logger.error("source_id mismatch expected=%s got=%s", source_id, result.source_id)
        return _fail("SOURCE_ID_MISMATCH", f"expected={source_id!r} got={result.source_id!r}")

    if result.run_id != run_id:
        logger.error("run_id mismatch expected=%s got=%s", run_id, result.run_id)
        return _fail("RUN_ID_MISMATCH", f"expected={run_id!r} got={result.run_id!r}")

    if result.finished_at < result.started_at:
        return _fail("TIMESTAMP_INVALID", "finished_at < started_at")

    return result
