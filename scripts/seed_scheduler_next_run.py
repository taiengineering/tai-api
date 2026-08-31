#!/usr/bin/env python3
"""Seed cron_schedule_config.next_run_at from T0. Default dry-run.

Active authority = cron_job_master.is_active. is_enabled is ignored.
Only rows with next_run_at IS NULL are planned.

Do not --apply against production from this workstream.
  python scripts/seed_scheduler_next_run.py --t0 2026-09-01T09:00:00+09:00
  python scripts/seed_scheduler_next_run.py --t0 2026-09-01T09:00:00+09:00 --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.scheduler.seed import plan_next_run_seeds
from services.time import parse_business_datetime, serialize_business_datetime


def _rows(execute_result) -> list[dict]:
    data = getattr(execute_result, "data", None) or []
    return [r for r in data if isinstance(r, dict)]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="T0 next_run_at seed (NULL only)")
    p.add_argument("--t0", required=True, help="aware ISO datetime (e.g. 2026-09-01T09:00:00+09:00)")
    p.add_argument("--apply", action="store_true", help="write planned next_run_at (default: dry-run)")
    args = p.parse_args(argv)
    t0 = parse_business_datetime(args.t0)

    from db.database import get_supabase
    sb = get_supabase()
    masters = _rows(sb.table("cron_job_master").select("job_code,is_active,cron_expression").execute())
    configs = _rows(sb.table("cron_schedule_config").select("job_code,next_run_at,is_enabled").execute())
    planned = plan_next_run_seeds(masters, configs, t0)
    payload = {
        "t0": serialize_business_datetime(t0),
        "apply": bool(args.apply),
        "config_rows": len(configs),
        "planned": len(planned),
        "jobs": [
            {"job_code": r["job_code"], "next_run_at": r["next_run_at_iso"]}
            for r in planned
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not args.apply:
        return 0
    for row in planned:
        sb.table("cron_schedule_config").update(
            {"next_run_at": row["next_run_at_iso"]}
        ).eq("job_code", row["job_code"]).is_("next_run_at", "null").execute()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
