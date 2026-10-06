"""SchedulerHeartbeatSupervisor — daemon thread that renews the scheduler occurrence lease."""
from __future__ import annotations

import logging
import threading
from datetime import timedelta
from typing import Callable

logger = logging.getLogger(__name__)

_DEFAULT_HEARTBEAT_INTERVAL = 60  # seconds


class SchedulerHeartbeatSupervisor:
    """Renews the scheduler occurrence lease while a job is executing.

    Uses a separate store instance (via store_factory) to avoid sharing a DB connection
    with the main thread.  The interval is bounded to at most lease_seconds // 3 so the
    lease is renewed before it can expire.

    Fail-closed contract:
      - store_factory raises              → failed_reason = "HEARTBEAT_INFRA_ERROR"
      - heartbeat_occurrence returns False → failed_reason = "LEASE_LOST"
      - heartbeat_occurrence raises       → failed_reason = "HEARTBEAT_INFRA_ERROR"
      - stop() join timeout              → failed_reason = "HEARTBEAT_STOP_TIMEOUT"
    None of these cases calls complete_and_advance; caller checks failed_reason after stop().
    """

    def __init__(
        self,
        claim,
        *,
        store_factory: Callable,
        lease: timedelta,
        heartbeat_interval_seconds: int = _DEFAULT_HEARTBEAT_INTERVAL,
    ) -> None:
        lease_seconds = int(lease.total_seconds())
        if lease_seconds <= 0:
            raise ValueError(f"lease must be positive, got {lease!r}")
        self._claim = claim
        self._store_factory = store_factory
        self._lease = lease
        self._interval = min(heartbeat_interval_seconds, max(1, lease_seconds // 3))
        self._stop_event = threading.Event()
        self._failed_reason: str | None = None
        self._thread: threading.Thread | None = None

    @property
    def failed_reason(self) -> str | None:
        return self._failed_reason

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name=f"sched-hb-{self._claim.log_id[:8]}",
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> bool:
        """Signal the heartbeat thread to stop and wait for it to exit.

        Returns True if the thread exited cleanly within the timeout.
        Returns False if the thread is still alive after the timeout;
        sets failed_reason to HEARTBEAT_STOP_TIMEOUT when no prior failure is recorded.
        """
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                if self._failed_reason is None:
                    self._failed_reason = "HEARTBEAT_STOP_TIMEOUT"
                return False
        return True

    def _run(self) -> None:
        from services.time import now_kst
        try:
            store = self._store_factory()
        except Exception as exc:
            logger.error(
                "scheduler heartbeat store_factory failed job=%s log_id=%s exception_type=%s",
                self._claim.job_code, self._claim.log_id, type(exc).__name__,
            )
            self._failed_reason = "HEARTBEAT_INFRA_ERROR"
            return
        while not self._stop_event.wait(self._interval):
            try:
                alive = store.heartbeat_occurrence(
                    self._claim,
                    now=now_kst(),
                    lease=self._lease,
                )
            except Exception:
                logger.error(
                    "scheduler heartbeat exception job=%s log_id=%s",
                    self._claim.job_code, self._claim.log_id,
                )
                self._failed_reason = "HEARTBEAT_INFRA_ERROR"
                return
            if not alive:
                logger.warning(
                    "scheduler heartbeat returned false job=%s log_id=%s",
                    self._claim.job_code, self._claim.log_id,
                )
                self._failed_reason = "LEASE_LOST"
                return
