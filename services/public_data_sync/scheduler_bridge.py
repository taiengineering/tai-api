"""Public Data Scheduler Bridge — connects Central Scheduler to Public Data Control Plane.

Called by direct://public_data_sync_tick. Discovers due sources, executes each via
execute_due_source with a completion_state_resolver, and raises PublicDataSchedulerTickError
on any failure so the dispatcher can capture the structured summary.
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
_DEFAULT_CADENCE_SECONDS = 3600
_DEFAULT_RETRY_DELAY_SECONDS = 300
_DEFAULT_LEASE_SECONDS = 900
_DEFAULT_HB_INTERVAL_SECONDS = 60


class PublicDataSchedulerTickError(Exception):
    """Raised by tick_public_data_sources when one or more sources fail.

    The dispatcher reads `getattr(e, 'summary', None)` to capture structured detail.
    """

    def __init__(self, summary: dict[str, Any]) -> None:
        super().__init__(str(summary))
        self.summary = summary


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_completion_resolver(
    cadence_seconds: int,
    retry_delay_seconds: int,
) -> Callable[[RunResult], tuple[datetime | None, datetime | None]]:
    """Return a resolver that computes (next_due_at, retry_not_before) from a RunResult.

    SUCCESS / NO_CHANGE / SKIPPED → advance by cadence, no retry backoff.
    FAILED / PARTIAL              → next_due immediately, retry backoff applied.
    """
    _advance = frozenset({RunStatus.SUCCESS, RunStatus.NO_CHANGE, RunStatus.SKIPPED})

    def resolver(result: RunResult) -> tuple[datetime | None, datetime | None]:
        finished = result.finished_at or _now()
        if result.status in _advance:
            return finished + timedelta(seconds=cadence_seconds), None
        return finished, finished + timedelta(seconds=retry_delay_seconds)

    return resolver


def tick_public_data_sources(
    *,
    store=None,
    now: datetime | None = None,
    limit: int = _DEFAULT_LIMIT,
    cadence_seconds: int = _DEFAULT_CADENCE_SECONDS,
    retry_delay_seconds: int = _DEFAULT_RETRY_DELAY_SECONDS,
    lease_seconds: int = _DEFAULT_LEASE_SECONDS,
    heartbeat_interval_seconds: int = _DEFAULT_HB_INTERVAL_SECONDS,
    heartbeat_store_factory: Callable | None = None,
) -> list[dict[str, Any]]:
    """Discover due public data sources and execute each one.

    Args:
        store:                      PublicDataRuntimeStore instance (default: new instance)
        now:                        Current time (default: UTC now)
        limit:                      Maximum number of sources to execute per tick (capped at _MAX_LIMIT)
        cadence_seconds:            Advance next_due_at by this many seconds on success.
        retry_delay_seconds:        Retry backoff duration in seconds on failure.
        lease_seconds:              Execution lease duration in seconds.
        heartbeat_interval_seconds: Heartbeat renewal interval in seconds.
        heartbeat_store_factory:    Factory for the heartbeat thread's store (default: new instance).

    Returns:
        List of result dicts (one per successfully completed execution).

    Raises:
        PublicDataSchedulerTickError: when any source raises during execute_due_source.
    """
    effective_limit = min(max(1, limit), _MAX_LIMIT)
    now = now or _now()

    if store is None:
        store = PublicDataRuntimeStore()

    due_sources = store.list_due_sources(now=now)[:effective_limit]

    resolver = _make_completion_resolver(cadence_seconds, retry_delay_seconds)

    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for source_id in due_sources:
        try:
            result = execute_due_source(
                source_id,
                store=store,
                lease_seconds=lease_seconds,
                heartbeat_interval_seconds=heartbeat_interval_seconds,
                heartbeat_store_factory=heartbeat_store_factory,
                completion_state_resolver=resolver,
            )
        except Exception as exc:
            logger.error(
                "public_data_sync_tick source failed source_id=%s exception_type=%s",
                source_id, type(exc).__name__,
            )
            errors.append({
                "source_id": source_id,
                "error": type(exc).__name__,
                "detail": str(exc)[:500],
            })
            continue

        if result is not None:
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
