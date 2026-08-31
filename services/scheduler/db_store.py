"""Supabase-backed store. Not used in unit tests. Production dispatcher only."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from services.scheduler.cron_grammar import next_fire_at_or_after
from services.scheduler.store import Claim, InMemoryStore, JobRow, TERMINAL
from services.time import serialize_business_datetime


def _parse_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


class DbStore(InMemoryStore):
    def __init__(self, sb=None) -> None:
        super().__init__()
        self._sb = sb

    def _client(self):
        if self._sb is not None:
            return self._sb
        from db.supabase_client import get_supabase
        return get_supabase()

    def refresh(self, now: datetime) -> None:
        sb = self._client()
        masters = sb.table("cron_job_master").select("*").eq("is_active", True).execute()
        configs = sb.table("cron_schedule_config").select("*").execute()
        cfg = {c["job_code"]: c for c in (configs.data or [])}
        self.jobs = {}
        for m in masters.data or []:
            code = m["job_code"]
            c = cfg.get(code) or {}
            expr = m.get("cron_expression") or ""
            nxt = _parse_ts(c.get("next_run_at"))
            if nxt is None and expr:
                nxt = next_fire_at_or_after(expr, now)
                try:
                    sb.table("cron_schedule_config").update(
                        {"next_run_at": serialize_business_datetime(nxt)}
                    ).eq("job_code", code).execute()
                except Exception:
                    pass
            ep = m.get("endpoint_url") or ""
            self.put_job(JobRow(
                job_code=code,
                cron_expression=expr,
                is_active=bool(m.get("is_active")),
                handler=ep if str(ep).startswith("direct://") else ep,
                next_run_at=nxt,
                payload=m.get("request_payload") or {},
                timeout_seconds=m.get("timeout_seconds") or 300,
                http_method=m.get("http_method") or "POST",
                endpoint_url=ep,
            ))

    def claim(self, job: JobRow, worker_id: str, now: datetime, lease: timedelta) -> Claim | None:
        scheduled_for = job.next_run_at
        if scheduled_for is None:
            return None
        sb = self._client()
        key = (job.job_code, scheduled_for)
        existing = (
            sb.table("cron_job_log")
            .select("*")
            .eq("job_code", job.job_code)
            .eq("scheduled_for", serialize_business_datetime(scheduled_for))
            .limit(1)
            .execute()
        )
        rows = existing.data or []
        if rows:
            row = rows[0]
            if row.get("status") in TERMINAL:
                return None
            lease_until = _parse_ts(row.get("lease_until"))
            if row.get("status") == "RUNNING" and lease_until and lease_until > now:
                return None
            if row.get("status") == "RUNNING" and (lease_until is None or lease_until <= now):
                attempt = int(row.get("attempt_no") or 1) + 1
                sb.table("cron_job_log").update({
                    "attempt_no": attempt,
                    "lease_until": serialize_business_datetime(now + lease),
                    "status": "RUNNING",
                }).eq("id", row["id"]).execute()
                return Claim(
                    job_code=job.job_code,
                    scheduled_for=scheduled_for,
                    worker_id=worker_id,
                    attempt_no=attempt,
                    lease_until=now + lease,
                    log_id=str(row["id"]),
                )
            return None
        log_id = str(uuid4())
        try:
            ins = sb.table("cron_job_log").insert({
                "id": log_id,
                "job_code": job.job_code,
                "scheduled_for": serialize_business_datetime(scheduled_for),
                "triggered_by": "SCHEDULE",
                "status": "RUNNING",
                "attempt_no": 1,
                "lease_until": serialize_business_datetime(now + lease),
            }).execute()
            rid = (ins.data or [{}])[0].get("id", log_id)
        except Exception:
            return None
        self.logs[key] = {"id": rid, "status": "RUNNING"}
        return Claim(
            job_code=job.job_code,
            scheduled_for=scheduled_for,
            worker_id=worker_id,
            attempt_no=1,
            lease_until=now + lease,
            log_id=str(rid),
        )

    def complete(self, claim: Claim, status: str, detail: Any, now: datetime) -> None:
        sb = self._client()
        payload = {
            "status": status,
            "finished_at": serialize_business_datetime(now),
            "result_detail": detail if isinstance(detail, dict) else {"raw": str(detail)},
        }
        sb.table("cron_job_log").update(payload).eq("id", claim.log_id).execute()
        sb.table("cron_schedule_config").update({
            "last_run_at": serialize_business_datetime(now),
            "last_status": status,
        }).eq("job_code", claim.job_code).execute()

    def advance_next_run(self, job: JobRow, scheduled_for: datetime, nxt: datetime) -> None:
        super().advance_next_run(job, scheduled_for, nxt)
        sb = self._client()
        sb.table("cron_schedule_config").update({
            "next_run_at": serialize_business_datetime(nxt),
        }).eq("job_code", job.job_code).execute()
