"""RPC-semantics equivalent of tai_scheduler_* PLpgSQL. Tests only. No live DB."""
from __future__ import annotations

import threading
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from services.scheduler.store import TERMINAL
from services.time import serialize_business_datetime


def _ts(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _lease(value: Any) -> timedelta:
    if isinstance(value, timedelta):
        return value
    text = str(value).strip().lower()
    if text.endswith(" seconds"):
        return timedelta(seconds=int(float(text.split()[0])))
    if text.endswith("s") and text[:-1].replace(".", "", 1).isdigit():
        return timedelta(seconds=int(float(text[:-1])))
    raise ValueError(f"unsupported lease interval: {value!r}")


class _Resp:
    def __init__(self, data: Any):
        self.data = data


class SchedulerStateDB:
    """Single-lock transaction matching claim INSERT ON CONFLICT + CAS and fenced complete."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.masters: list[dict[str, Any]] = []
        self.config: dict[str, dict[str, Any]] = {}
        self.logs: dict[tuple[str, str], dict[str, Any]] = {}
        self.drop_complete_response = False
        self.complete_commits = 0
        self.split_states = 0

    def seed_job(
        self,
        job_code: str,
        cron_expression: str,
        next_run_at: datetime,
        *,
        handler: str = "direct://daily_health_check",
        is_active: bool = True,
    ) -> None:
        self.masters = [m for m in self.masters if m["job_code"] != job_code]
        self.masters.append({
            "job_code": job_code,
            "cron_expression": cron_expression,
            "is_active": is_active,
            "endpoint_url": handler,
            "http_method": "DIRECT",
            "request_payload": {},
            "timeout_seconds": 300,
        })
        self.config[job_code] = {
            "job_code": job_code,
            "cron_expression": cron_expression,
            "is_enabled": is_active,
            "next_run_at": next_run_at,
            "last_run_at": None,
            "last_status": None,
        }

    def _key(self, job_code: str, scheduled_for: datetime) -> tuple[str, str]:
        return (job_code, serialize_business_datetime(scheduled_for))

    def claim(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        job_code = params["p_job_code"]
        scheduled_for = _ts(params["p_scheduled_for"])
        now = _ts(params["p_now"])
        lease = _lease(params["p_lease"])
        key = self._key(job_code, scheduled_for)
        with self.lock:
            existing = self.logs.get(key)
            if existing is None:
                log_id = str(uuid4())
                self.logs[key] = {
                    "id": log_id,
                    "job_code": job_code,
                    "scheduled_for": scheduled_for,
                    "status": "RUNNING",
                    "attempt_no": 1,
                    "lease_until": now + lease,
                    "triggered_by": "SCHEDULE",
                }
                return [{"log_id": log_id, "attempt_no": 1}]
            if existing["status"] == "RUNNING" and existing["lease_until"] <= now:
                existing["attempt_no"] = int(existing["attempt_no"]) + 1
                existing["lease_until"] = now + lease
                existing["status"] = "RUNNING"
                return [{"log_id": existing["id"], "attempt_no": existing["attempt_no"]}]
            return []

    def complete(self, params: dict[str, Any]) -> bool:
        job_code = params["p_job_code"]
        log_id = str(params["p_log_id"])
        attempt_no = int(params["p_attempt_no"])
        status = params["p_status"]
        detail = params["p_detail"]
        finished_at = _ts(params["p_finished_at"])
        next_run_at = _ts(params["p_next_run_at"])
        with self.lock:
            row = None
            for item in self.logs.values():
                if str(item["id"]) == log_id:
                    row = item
                    break
            if row is None or row["status"] != "RUNNING" or int(row["attempt_no"]) != attempt_no:
                return True
            row["status"] = status
            row["finished_at"] = finished_at
            row["result_detail"] = detail
            cfg = self.config.setdefault(job_code, {"job_code": job_code})
            cfg["next_run_at"] = next_run_at
            cfg["last_run_at"] = finished_at
            cfg["last_status"] = status
            self.complete_commits += 1
            if row["status"] in TERMINAL and cfg.get("next_run_at") == row["scheduled_for"]:
                self.split_states += 1
            return False

    def observe_split(self) -> int:
        with self.lock:
            n = 0
            for row in self.logs.values():
                if row["status"] not in TERMINAL:
                    continue
                cfg = self.config.get(row["job_code"]) or {}
                nxt = cfg.get("next_run_at")
                if nxt is not None and nxt == row["scheduled_for"]:
                    n += 1
            return n


class _Rpc:
    def __init__(self, db: SchedulerStateDB, name: str, params: dict[str, Any]):
        self.db = db
        self.name = name
        self.params = params

    def execute(self):
        if self.name == "tai_scheduler_claim_occurrence":
            return _Resp(self.db.claim(self.params))
        if self.name == "tai_scheduler_complete_occurrence":
            fenced = self.db.complete(self.params)
            if self.db.drop_complete_response:
                raise TimeoutError("lost complete RPC response")
            return _Resp(fenced)
        raise ValueError(self.name)


class _Q:
    def __init__(self, db: SchedulerStateDB, name: str):
        self.db = db
        self.name = name
        self._eq: list[tuple[str, Any]] = []
        self._op = "select"
        self._row: dict[str, Any] | None = None
        self._limit: int | None = None

    def select(self, *a, **k):
        self._op = "select"
        return self

    def eq(self, col, val):
        self._eq.append((col, val))
        return self

    def limit(self, n):
        self._limit = n
        return self

    def update(self, payload):
        self._op = "update"
        self._row = payload
        return self

    def _match(self, row: dict[str, Any]) -> bool:
        for col, val in self._eq:
            left = row.get(col)
            if col in ("scheduled_for", "next_run_at", "last_run_at", "lease_until") and left is not None:
                if isinstance(left, datetime):
                    left = serialize_business_datetime(left)
            if left != val:
                return False
        return True

    def execute(self):
        with self.db.lock:
            if self.name == "cron_job_master":
                rows = [dict(r) for r in self.db.masters]
            elif self.name == "cron_schedule_config":
                rows = []
                for c in self.db.config.values():
                    item = dict(c)
                    for k in ("next_run_at", "last_run_at"):
                        if isinstance(item.get(k), datetime):
                            item[k] = serialize_business_datetime(item[k])
                    rows.append(item)
            elif self.name == "cron_job_log":
                rows = []
                for r in self.db.logs.values():
                    item = dict(r)
                    for k in ("scheduled_for", "lease_until", "finished_at"):
                        if isinstance(item.get(k), datetime):
                            item[k] = serialize_business_datetime(item[k])
                    rows.append(item)
            else:
                rows = []
            matched = [r for r in rows if self._match(r)]
            if self._op == "update":
                payload = self._row or {}
                updated = []
                if self.name == "cron_schedule_config":
                    for code, cfg in self.db.config.items():
                        view = dict(cfg)
                        for k in ("next_run_at", "last_run_at"):
                            if isinstance(view.get(k), datetime):
                                view[k] = serialize_business_datetime(view[k])
                        if self._match(view):
                            for k, v in payload.items():
                                if k in ("next_run_at", "last_run_at") and v is not None:
                                    cfg[k] = _ts(v)
                                else:
                                    cfg[k] = v
                            updated.append(dict(cfg))
                return _Resp(updated)
            if self._limit is not None:
                matched = matched[: self._limit]
            return _Resp(matched)


class FakeSchedulerSB:
    def __init__(self, db: SchedulerStateDB):
        self.db = db

    def rpc(self, name: str, params: dict[str, Any] | None = None):
        return _Rpc(self.db, name, params or {})

    def table(self, name: str):
        return _Q(self.db, name)
