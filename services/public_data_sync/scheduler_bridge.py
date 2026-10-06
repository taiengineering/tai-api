"""Public Data Scheduler Bridge — connects Central Scheduler to Public Data Control Plane.

Called by direct://public_data_sync_tick. Discovers due sources, reads each source's
runtime cadence and next_due_at from the SoT (public_data_source_runtime), then executes
via execute_due_source with a per-source completion_state_resolver.

Raises PublicDataSchedulerTickError on any failure (missing cadence, execution error,
or FAILED/PARTIAL result) so the dispatcher marks the scheduler occurrence as FAILED.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from services.public_data_sync.contracts import RunResult, RunStatus
from services.public_data_sync.runtime import execute_due_source
from services.public_data_sync.runtime_store import PublicDataRuntimeStore

logger = logging.getLogger(__name__)

_DEFAULT_LIMIT = 2
_MAX_LIMIT = 10
_DEFAULT_RETRY_DELAY_SECONDS = 3600
_MIN_RETRY_DELAY_SECONDS = 300
_MAX_RETRY_DELAY_SECONDS = 86400
_DEFAULT_LEASE_SECONDS = 900
_DEFAULT_HB_INTERVAL_SECONDS = 60

_TERMINAL_SUCCESS = frozenset({RunStatus.SUCCESS, RunStatus.NO_CHANGE, RunStatus.SKIPPED})
_TERMINAL_FAILURE = frozenset({RunStatus.FAILED, RunStatus.PARTIAL})


class PublicDataSchedulerTickError(Exception):
    """Raised by tick_public_data_sources when one or more sources fail.

    The dispatcher reads `getattr(e, 'summary', None)` to capture structured detail.
    The message is a fixed safe string — raw exception text never appears here.
    """

    def __init__(self, summary: dict[str, Any]) -> None:
        super().__init__("public data scheduler tick failed")
        self.summary = summary


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    from dateutil.parser import parse as _parse
    return _parse(value)


def _effective_retry_delay(requested: int) -> int:
    return min(max(requested, _MIN_RETRY_DELAY_SECONDS), _MAX_RETRY_DELAY_SECONDS)


def _make_completion_resolver(
    cadence_seconds: int,
    retry_delay_seconds: int,
) -> Callable[[RunResult], tuple[datetime | None, datetime | None]]:
    """Return a per-source resolver for (next_due_at, retry_not_before).

    SUCCESS / NO_CHANGE / SKIPPED → advance by source cadence, no retry backoff.
    FAILED / PARTIAL              → next_due immediately, retry backoff applied.
    """

    def resolver(result: RunResult) -> tuple[datetime | None, datetime | None]:
        finished = result.finished_at or _now()
        if result.status in _TERMINAL_SUCCESS:
            return finished + timedelta(seconds=cadence_seconds), None
        return finished, finished + timedelta(seconds=retry_delay_seconds)

    return resolver


def tick_public_data_sources(
    *,
    store=None,
    now: datetime | None = None,
    limit: int = _DEFAULT_LIMIT,
    retry_delay_seconds: int = _DEFAULT_RETRY_DELAY_SECONDS,
    lease_seconds: int = _DEFAULT_LEASE_SECONDS,
    heartbeat_interval_seconds: int = _DEFAULT_HB_INTERVAL_SECONDS,
    heartbeat_store_factory: Callable | None = None,
) -> list[dict[str, Any]]:
    """Discover due public data sources and execute each one.

    Source cadence is read from public_data_source_runtime (SoT) — not passed by the caller.
    FAILED/PARTIAL results are treated as scheduler tick failures.

    Args:
        store:                      PublicDataRuntimeStore instance (default: new instance)
        now:                        Current time (default: UTC now)
        limit:                      Maximum sources per tick (capped at _MAX_LIMIT)
        retry_delay_seconds:        Retry backoff duration; clamped to [300, 86400].
        lease_seconds:              Execution lease duration in seconds.
        heartbeat_interval_seconds: Heartbeat renewal interval in seconds.
        heartbeat_store_factory:    Factory for the heartbeat thread's store.

    Returns:
        List of result dicts for sources that completed with SUCCESS/NO_CHANGE/SKIPPED.

    Raises:
        PublicDataSchedulerTickError: when any source has missing cadence, raises during
            execution, or completes with FAILED/PARTIAL status.
    """
    effective_retry = _effective_retry_delay(retry_delay_seconds)
    effective_limit = min(max(1, limit), _MAX_LIMIT)
    now = now or _now()

    if store is None:
        store = PublicDataRuntimeStore()

    due_sources = store.list_due_sources(now=now)[:effective_limit]

    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for source_id in due_sources:
        # Read source-specific operational state from the SoT.
        runtime = store.get_source_runtime(source_id)
        cadence = (runtime or {}).get("cadence_seconds")
        if not cadence or int(cadence) <= 0:
            logger.error(
                "public_data_sync_tick cadence missing source_id=%s cadence=%r",
                source_id, cadence,
            )
            errors.append({"source_id": source_id, "error": "CONFIG_CADENCE_MISSING"})
            continue

        cadence = int(cadence)
        original_next_due_raw = (runtime or {}).get("next_due_at")
        original_next_due = _parse_ts(
            original_next_due_raw.isoformat()
            if isinstance(original_next_due_raw, datetime)
            else original_next_due_raw
        )

        resolver = _make_completion_resolver(cadence, effective_retry)

        try:
            result = execute_due_source(
                source_id,
                store=store,
                scheduled_for=original_next_due,
                lease_seconds=lease_seconds,
                heartbeat_interval_seconds=heartbeat_interval_seconds,
                heartbeat_store_factory=heartbeat_store_factory,
                completion_state_resolver=resolver,
                metadata={"scheduler_bridge": "PUBLIC_DATA_SYNC_TICK"},
            )
        except Exception as exc:
            logger.error(
                "public_data_sync_tick source failed source_id=%s exception_type=%s",
                source_id, type(exc).__name__,
            )
            errors.append({
                "source_id": source_id,
                "error": type(exc).__name__,
            })
            continue

        if result is None:
            continue

        if result.status in _TERMINAL_FAILURE:
            logger.warning(
                "public_data_sync_tick source completed with failure source_id=%s status=%s",
                source_id, result.status.value,
            )
            errors.append({
                "source_id": result.source_id,
                "error": "SOURCE_EXECUTION_FAILED",
                "status": result.status.value,
                "error_code": result.error_code,
            })
            continue

        results.append({
            "source_id": result.source_id,
            "run_id": result.run_id,
            "status": result.status.value,
        })

    if errors:
        raise PublicDataSchedulerTickError({
            "tick_errors": errors,
            "succeeded": len(results),
            "failed": len(errors),
        })

    return results
