"""HeartbeatSupervisor — daemon thread that renews the runtime lease during adapter execution."""
from __future__ import annotations

import logging
import threading
from typing import Callable

logger = logging.getLogger(__name__)

_DEFAULT_HEARTBEAT_INTERVAL = 60  # seconds


class HeartbeatSupervisor:
    """Renews the runtime lease while an adapter is executing.

    Uses a separate store instance (via store_factory) to avoid sharing a DB connection
    with the main thread.  The interval is bounded to at most lease_seconds // 3 so the
    lease is renewed before it can expire.

    Fail-closed contract:
      - store_factory raises         → failed_reason = "HEARTBEAT_INFRA_ERROR"
      - heartbeat returns False      → failed_reason = "LEASE_LOST"   (→ RuntimeFencedError)
      - heartbeat raises             → failed_reason = "HEARTBEAT_INFRA_ERROR" (→ RuntimeHeartbeatError)
      - stop() join timeout          → failed_reason = "HEARTBEAT_STOP_TIMEOUT" (→ RuntimeHeartbeatError)
    None of these cases calls complete_run; the caller must check failed_reason after stop().
    """

    def __init__(
        self,
        run_id: str,
        source_id: str,
        *,
        store_factory: Callable,
        lease_seconds: int,
        heartbeat_interval_seconds: int = _DEFAULT_HEARTBEAT_INTERVAL,
    ) -> None:
        if lease_seconds <= 0:
            raise ValueError(f"lease_seconds must be positive, got {lease_seconds!r}")
        self._run_id = run_id
        self._source_id = source_id
        self._store_factory = store_factory
        self._lease_seconds = lease_seconds
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
            name=f"heartbeat-{self._run_id[:8]}",
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
        try:
            store = self._store_factory()
        except Exception as exc:
            logger.error(
                "heartbeat store_factory failed source_id=%s run_id=%s"
                " operation=store_factory exception_type=%s",
                self._source_id, self._run_id, type(exc).__name__,
            )
            self._failed_reason = "HEARTBEAT_INFRA_ERROR"
            return
        while not self._stop_event.wait(self._interval):
            try:
                alive = store.heartbeat(self._run_id, lease_seconds=self._lease_seconds)
            except Exception:
                logger.error(
                    "heartbeat exception source_id=%s run_id=%s",
                    self._source_id, self._run_id,
                )
                self._failed_reason = "HEARTBEAT_INFRA_ERROR"
                return
            if not alive:
                logger.warning(
                    "heartbeat returned false source_id=%s run_id=%s",
                    self._source_id, self._run_id,
                )
                self._failed_reason = "LEASE_LOST"
                return
