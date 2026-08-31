#!/usr/bin/env python3
"""Standalone KST scheduler worker. Asia/Seoul dispatcher tick. EXECUTE against live DB only when run as a process.

python scheduler_worker.py
"""
from __future__ import annotations

import logging
import threading
import time

from services.scheduler.dispatcher import tick
from services.scheduler.store import InMemoryStore

logger = logging.getLogger(__name__)
_thread_lock = threading.Lock()
_thread: threading.Thread | None = None


def start_dispatcher_thread(interval_seconds: float = 5.0) -> None:
    global _thread
    with _thread_lock:
        if _thread is not None and _thread.is_alive():
            return

        def _loop():
            from services.scheduler.db_store import DbStore
            store = DbStore()
            while True:
                try:
                    tick(store)
                except Exception as e:
                    logger.error("[SCHED] tick failed: %s", e)
                time.sleep(interval_seconds)

        _thread = threading.Thread(target=_loop, name="tai-kst-dispatcher", daemon=True)
        _thread.start()


def run_forever(store: InMemoryStore | None = None, interval_seconds: float = 5.0) -> None:
    logging.basicConfig(level=logging.INFO)
    logger.info("[SCHED] worker loop Asia/Seoul interval=%s", interval_seconds)
    mem = store or InMemoryStore()
    while True:
        try:
            tick(mem)
        except Exception as e:
            logger.error("[SCHED] tick failed: %s", e)
        time.sleep(interval_seconds)


if __name__ == "__main__":
    from services.scheduler.db_store import DbStore
    run_forever(DbStore())
