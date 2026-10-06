"""KOSHA safety-library daily orchestrator CLI.

Phase 1: code only. Do not install production crontab from this script.

Intended production (Cafe24 fixed-IP, GPT-approved Phase 2):
  cd <tai-api-production-path> &&
  flock -n /var/lock/kosha_safety_material_daily_sync.lock \\
    <venv-python> scripts/kosha_safety_material_daily_sync.py \\
    >> /var/log/kosha_safety_material_daily_sync.log 2>&1

Schedule: 04:10 Asia/Seoul  →  crontab `10 4 * * *` when the host clock is KST.
Do not add GitHub Actions `schedule:` until KOSHA network from that runner is proven.

Secrets stay in protected env. Never pass API keys on the cron line.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.kosha_safety_materials.daily_sync import (
    EXIT_FAIL,
    EXIT_OK,
    release_lock,
    try_acquire_lock,
)
from services.time import now_kst

DEFAULT_LOCK = os.environ.get(
    "KOSHA_DAILY_LOCK",
    "/tmp/kosha_safety_material_daily_sync.lock",
)


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass
    if not os.getenv("SUPABASE_SERVICE_KEY") and os.getenv("SUPABASE_SERVICE_ROLE_KEY"):
        os.environ["SUPABASE_SERVICE_KEY"] = os.environ["SUPABASE_SERVICE_ROLE_KEY"]


def _print(report: dict, code: int) -> int:
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return code


async def main(argv: list[str] | None = None) -> int:
    _load_env()
    p = argparse.ArgumentParser(description="KOSHA daily snapshot + detail + R2 orchestration")
    p.add_argument("--lock-file", default=DEFAULT_LOCK)
    p.add_argument("--skip-lock", action="store_true", help="tests only; production cron must flock")
    args = p.parse_args(argv)

    lock_fh = None
    if not args.skip_lock:
        lock_fh = try_acquire_lock(args.lock_file)
        if lock_fh is None:
            report = {
                "final_status": "SKIPPED_LOCKED",
                "failure_code": None,
                "started_at_kst": now_kst().isoformat(),
                "ended_at_kst": now_kst().isoformat(),
                "execution_host": socket.gethostname(),
            }
            return _print(report, EXIT_OK)

    try:
        from services.kosha_safety_materials.production_daily import run_production_daily
        report, code = await run_production_daily()
        return _print(report, code)
    except Exception as e:
        report = {
            "final_status": "STORAGE_STOP" if "R2" in type(e).__name__ else "FAILED",
            "failure_code": getattr(e, "reason", None) or getattr(e, "code", None) or type(e).__name__,
            "started_at_kst": now_kst().isoformat(),
            "ended_at_kst": now_kst().isoformat(),
            "execution_host": socket.gethostname(),
        }
        return _print(report, EXIT_FAIL)
    finally:
        release_lock(lock_fh)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
