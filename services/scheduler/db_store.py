"""Supabase-backed store. Claim/complete are atomic RPCs. No split next_run write."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from services.scheduler.cron_grammar import next_fire_after, next_fire_at_or_after
from services.scheduler.store import Claim, InMemoryStore, JobRow, TERMINAL
from services.time import serialize_business_datetime
from watch_engine.trace import generate_trace_id

logger = logging.getLogger(__name__)


def _parse_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _first_row(data: Any) -> dict[str, Any] | None:
    if data is None or data is False:
        return None
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        if not data:
            return None
        row = data[0]
        return row if isinstance(row, dict) else None
    return None


def _as_fenced(data: Any) -> bool:
    if isinstance(data, bool):
        return data
    if isinstance(data, list) and data:
        v = data[0]
        if isinstance(v, bool):
            return v
        if isinstance(v, dict) and "tai_scheduler_complete_occurrence" in v:
            return bool(v["tai_scheduler_complete_occurrence"])
    if isinstance(data, dict) and "tai_scheduler_complete_occurrence" in data:
        return bool(data["tai_scheduler_complete_occurrence"])
    return bool(data)


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
        self.reconcile_terminal_wedges()

    def reconcile_terminal_wedges(self) -> None:
        """Self-heal leftover terminal(X) with config.next_run_at==X. Not used by the atomic complete path."""
        sb = self._client()
        for job in list(self.jobs.values()):
            if job.next_run_at is None or not job.cron_expression:
                continue
            try:
                existing = (
                    sb.table("cron_job_log")
                    .select("status,scheduled_for")
                    .eq("job_code", job.job_code)
                    .eq("scheduled_for", serialize_business_datetime(job.next_run_at))
                    .limit(1)
                    .execute()
                )
            except Exception:
                continue
            rows = existing.data or []
            if not rows:
                continue
            if rows[0].get("status") not in TERMINAL:
                continue
            nxt = next_fire_after(job.cron_expression, job.next_run_at)
            scheduled = serialize_business_datetime(job.next_run_at)
            try:
                sb.table("cron_schedule_config").update(
                    {"next_run_at": serialize_business_datetime(nxt)}
                ).eq("job_code", job.job_code).eq("next_run_at", scheduled).execute()
            except Exception:
                continue
            job.next_run_at = nxt

    def claim(self, job: JobRow, worker_id: str, now: datetime, lease: timedelta) -> Claim | None:
        scheduled_for = job.next_run_at
        if scheduled_for is None:
            return None
        candidate = generate_trace_id("cron_job")
        try:
            res = self._client().rpc("tai_scheduler_claim_occurrence", {
                "p_job_code": job.job_code,
                "p_scheduled_for": serialize_business_datetime(scheduled_for),
                "p_now": serialize_business_datetime(now),
                "p_lease": f"{int(lease.total_seconds())} seconds",
                "p_trace_id": candidate,
            }).execute()
        except Exception as e:
            logger.error("[SCHED] claim RPC failed job=%s: %s", job.job_code, e)
            return None
        row = _first_row(getattr(res, "data", None))
        if not row:
            return None
        log_id = row.get("log_id") or row.get("id")
        if log_id is None:
            return None
        persisted = row.get("trace_id")
        return Claim(
            job_code=job.job_code,
            scheduled_for=scheduled_for,
            worker_id=worker_id,
            attempt_no=int(row.get("attempt_no") or 1),
            lease_until=now + lease,
            log_id=str(log_id),
            trace_id=str(persisted) if persisted else "",
        )

    def complete(self, claim: Claim, status: str, detail: Any, now: datetime) -> None:
        raise RuntimeError("use complete_and_advance (atomic terminal+next_run)")

    def complete_and_advance(
        self,
        claim: Claim,
        status: str,
        detail: Any,
        now: datetime,
        nxt: datetime,
    ) -> bool:
        try:
            res = self._client().rpc("tai_scheduler_complete_occurrence", {
                "p_job_code": claim.job_code,
                "p_scheduled_for": serialize_business_datetime(claim.scheduled_for),
                "p_log_id": claim.log_id,
                "p_attempt_no": claim.attempt_no,
                "p_status": status,
                "p_detail": detail if isinstance(detail, dict) else {"raw": str(detail)},
                "p_finished_at": serialize_business_datetime(now),
                "p_next_run_at": serialize_business_datetime(nxt),
            }).execute()
        except Exception:
            logger.error(
                "[SCHED] complete RPC failed; no local advance job=%s scheduled_for=%s",
                claim.job_code,
                claim.scheduled_for,
            )
            raise
        fenced = _as_fenced(getattr(res, "data", None))
        if not fenced:
            job = self.jobs.get(claim.job_code)
            if job is not None and job.next_run_at == claim.scheduled_for:
                job.next_run_at = nxt
        return bool(fenced)

    def advance_next_run(self, job: JobRow, scheduled_for: datetime, nxt: datetime) -> None:
        raise RuntimeError("use complete_and_advance (atomic terminal+next_run)")
