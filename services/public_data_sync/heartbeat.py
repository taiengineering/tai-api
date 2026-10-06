"""HeartbeatSupervisor — daemon thread that renews the runtime lease during adapter execution."""
from __future__ import annotations

import logging
import threading
from typing import Callable

logger = logging.getLogger(__name__)

_DEFAULT_HEARTBEAT_INTERVAL = 300  # seconds


class HeartbeatSupervisor:
    """Renews the runtime lease while an adapter is executing.

    Uses a separate store instance (via store_factory) to avoid sharing a DB connection
    with the main thread.  The interval is bounded to at most lease_seconds // 3 so the
    lease is renewed before it can expire.

    Fail-closed contract:
      - heartbeat returns False  → failed_reason = "LEASE_LOST"   (→ RuntimeFencedError)
      - heartbeat raises         → failed_reason = "HEARTBEAT_INFRA_ERROR" (→ RuntimeHeartbeatError)
    Neither case calls complete_run; the caller must check failed_reason after stop().
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

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def _run(self) -> None:
        store = self._store_factory()
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
