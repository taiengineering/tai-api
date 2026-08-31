"""In-memory occurrence store: claim, lease recovery, catch-up. No live DB."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4


TERMINAL = {"SUCCESS", "FAILED", "WARNING"}


@dataclass
class JobRow:
    job_code: str
    cron_expression: str
    is_active: bool
    handler: str
    next_run_at: datetime | None
    payload: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int = 300
    http_method: str = "POST"
    endpoint_url: str = ""


@dataclass
class Claim:
    job_code: str
    scheduled_for: datetime
    worker_id: str
    attempt_no: int
    lease_until: datetime
    log_id: str
    status: str = "RUNNING"


class InMemoryStore:
    def __init__(self) -> None:
        self.jobs: dict[str, JobRow] = {}
        self.logs: dict[tuple[str, datetime], dict[str, Any]] = {}

    def put_job(self, job: JobRow) -> None:
        self.jobs[job.job_code] = job

    def due(self, now: datetime) -> list[JobRow]:
        out = []
        for j in self.jobs.values():
            if not j.is_active or j.next_run_at is None:
                continue
            if j.next_run_at <= now:
                out.append(j)
        out.sort(key=lambda r: (r.next_run_at, r.job_code))
        return out

    def claim(
        self,
        job: JobRow,
        worker_id: str,
        now: datetime,
        lease: timedelta,
    ) -> Claim | None:
        scheduled_for = job.next_run_at
        if scheduled_for is None:
            return None
        key = (job.job_code, scheduled_for)
        existing = self.logs.get(key)
        if existing is not None:
            if existing["status"] in TERMINAL:
                return None
            if existing["status"] == "RUNNING" and existing["lease_until"] > now:
                return None
            if existing["status"] == "RUNNING" and existing["lease_until"] <= now:
                existing["attempt_no"] = int(existing["attempt_no"]) + 1
                existing["worker_id"] = worker_id
                existing["lease_until"] = now + lease
                existing["status"] = "RUNNING"
                return Claim(
                    job_code=job.job_code,
                    scheduled_for=scheduled_for,
                    worker_id=worker_id,
                    attempt_no=existing["attempt_no"],
                    lease_until=existing["lease_until"],
                    log_id=existing["id"],
                    status="RUNNING",
                )
            return None
        log_id = str(uuid4())
        self.logs[key] = {
            "id": log_id,
            "job_code": job.job_code,
            "scheduled_for": scheduled_for,
            "status": "RUNNING",
            "attempt_no": 1,
            "worker_id": worker_id,
            "lease_until": now + lease,
            "triggered_by": "SCHEDULE",
        }
        return Claim(
            job_code=job.job_code,
            scheduled_for=scheduled_for,
            worker_id=worker_id,
            attempt_no=1,
            lease_until=now + lease,
            log_id=log_id,
        )

    def complete(self, claim: Claim, status: str, detail: Any, now: datetime) -> None:
        key = (claim.job_code, claim.scheduled_for)
        row = self.logs[key]
        row["status"] = status
        row["finished_at"] = now
        row["result_detail"] = detail

    def advance_next_run(self, job: JobRow, scheduled_for: datetime, nxt: datetime) -> None:
        j = self.jobs[job.job_code]
        if j.next_run_at == scheduled_for:
            j.next_run_at = nxt
