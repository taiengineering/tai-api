"""Asia/Seoul dispatcher tick. Business jobs are DB rows, not APScheduler add_job.

Contract: at-least-once + at-most-one-live-claim + fenced completion + no silent miss.
Do not declare exactly-once. complete_and_advance is atomic; RPC failure does not advance.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from services.scheduler.cron_grammar import next_fire_after, next_fire_at_or_after
from services.scheduler.handlers import execute_direct
from services.scheduler.store import InMemoryStore, JobRow
from services.time import SYSTEM_CLOCK, Clock, now_kst, serialize_business_datetime

logger = logging.getLogger(__name__)
LEASE = timedelta(minutes=15)
DEFAULT_TICK_CAP = 20


def _http_execute(job: JobRow) -> Any:
    import os
    import requests
    base = os.environ.get("INTERNAL_API_URL", "https://api.taieng.co.kr")
    url = base.rstrip("/") + (job.endpoint_url or "")
    method = (job.http_method or "POST").upper()
    timeout = job.timeout_seconds or 300
    if method == "GET":
        resp = requests.get(url, timeout=timeout)
    else:
        resp = requests.post(url, json=job.payload or {}, timeout=timeout)
    try:
        body = resp.json()
    except Exception:
        body = {"text": resp.text[:300]}
    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code} {url}")
    return body


def execute_job(job: JobRow) -> Any:
    ep = job.handler or job.endpoint_url or ""
    if ep.startswith("direct://"):
        return execute_direct(ep, job.payload)
    return _http_execute(job)


def tick(
    store: InMemoryStore,
    clock: Clock = SYSTEM_CLOCK,
    worker_id: str = "dispatcher",
    tick_cap: int = DEFAULT_TICK_CAP,
) -> list[dict[str, Any]]:
    now = now_kst(clock)
    if hasattr(store, "refresh"):
        store.refresh(now)
    for j in store.jobs.values():
        if j.is_active and j.next_run_at is None and j.cron_expression:
            j.next_run_at = next_fire_at_or_after(j.cron_expression, now)
    results: list[dict[str, Any]] = []
    due = store.due(now)[:tick_cap]
    for job in due:
        claim = store.claim(job, worker_id=worker_id, now=now, lease=LEASE)
        if claim is None:
            continue
        status = "SUCCESS"
        detail: Any = None
        try:
            detail = execute_job(job)
        except Exception as e:
            status = "FAILED"
            detail = {"error": str(e)[:1000]}
            logger.error("[SCHED] %s FAILED scheduled_for=%s: %s", job.job_code, claim.scheduled_for, e)
        nxt = next_fire_after(job.cron_expression, claim.scheduled_for)
        try:
            fenced = store.complete_and_advance(claim, status, detail, now, nxt)
        except Exception as e:
            logger.error(
                "[SCHED] complete failed; leaving RUNNING for replay job=%s scheduled_for=%s: %s",
                job.job_code,
                claim.scheduled_for,
                e,
            )
            continue
        if fenced:
            logger.warning(
                "[SCHED] fenced complete rejected job=%s attempt=%s",
                job.job_code,
                claim.attempt_no,
            )
            continue
        results.append({
            "job_code": job.job_code,
            "scheduled_for": serialize_business_datetime(claim.scheduled_for),
            "status": status,
            "next_run_at": serialize_business_datetime(nxt),
            "attempt_no": claim.attempt_no,
            "worker_id": worker_id,
        })
    return results
