"""T0 next_run_at seed plan. Active = cron_job_master.is_active only.

Policy:
  - seed only when config.next_run_at IS NULL
  - skip unless matching master.is_active is true
  - ignore cron_schedule_config.is_enabled (legacy rows exist)
  - next_run_at = first fire at-or-after T0 (Asia/Seoul cron grammar)
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from services.scheduler.cron_grammar import next_fire_at_or_after
from services.time import serialize_business_datetime


def plan_next_run_seeds(
    masters: list[dict[str, Any]],
    configs: list[dict[str, Any]],
    t0: datetime,
) -> list[dict[str, Any]]:
    if t0.tzinfo is None:
        raise ValueError("T0 must be timezone-aware")
    by_code = {m["job_code"]: m for m in masters}
    planned: list[dict[str, Any]] = []
    for cfg in configs:
        code = cfg["job_code"]
        master = by_code.get(code)
        if master is None:
            continue
        if not master.get("is_active"):
            continue
        if cfg.get("next_run_at") is not None:
            continue
        expr = master.get("cron_expression") or ""
        nxt = next_fire_at_or_after(expr, t0)
        planned.append({
            "job_code": code,
            "cron_expression": expr,
            "next_run_at": nxt,
            "next_run_at_iso": serialize_business_datetime(nxt),
        })
    return planned
