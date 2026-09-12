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
    network_preflight,
    production_consistency,
    release_lock,
    run_daily,
    try_acquire_lock,
    wrap_detail_batch,
)
from services.kosha_safety_materials.storage.runner import BATCH_SIZE as STORAGE_BATCH
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


async def _production_sync():
    from routers.kosha_collect import _fetch_safety_materials_page
    from services.kosha_safety_material_sync import SupabaseSnapshotStore, sync_safety_materials

    store = SupabaseSnapshotStore()

    async def sync_fn(*, dry_run: bool, start_page: int):
        return await sync_safety_materials(
            fetch_page=_fetch_safety_materials_page,
            store=store,
            dry_run=dry_run,
            start_page=start_page,
        )

    return store, sync_fn


def _production_storage():
    from services.kosha_safety_material_storage import _r2
    from services.kosha_safety_materials.storage.hold_store import SupabaseHoldStore
    from services.kosha_safety_materials.storage.runner import StorageQuery, apply_bulk
    from services.kosha_safety_materials.storage.version_service import (
        SupabaseVersionStore,
        assert_production_versions,
    )
    from services.kosha_safety_materials.writer import SupabaseStore

    store = SupabaseStore()
    query = StorageQuery(store.sb)
    holds = SupabaseHoldStore(store.sb)
    r2 = _r2()
    versions = SupabaseVersionStore()
    assert_production_versions(versions)

    def storage_fn(*, snapshot_id: str):
        del snapshot_id  # apply_bulk uses latest COMPLETED via snapshot_precondition
        out = apply_bulk(store, query, r2, versions, holds=holds, batch_size=STORAGE_BATCH)
        out["r2_overwrite"] = int(getattr(r2, "overwrites", 0) or 0)
        out["r2_delete"] = int(getattr(r2, "deletes", 0) or getattr(r2, "delete_count", 0) or 0)
        out["existing_open_holds"] = out.get("held")
        return out

    return store, storage_fn


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
        snapshot_store, sync_fn = await _production_sync()
        from services.kosha_safety_materials.display import SupabaseDisplayStore
        from services.kosha_safety_materials.writer import SupabaseStore

        enrich_store = SupabaseStore()
        display_store = SupabaseDisplayStore()
        _, storage_fn = _production_storage()

        report, code = await run_daily(
            preflight_fn=network_preflight,
            sync_fn=sync_fn,
            latest_completed_fn=snapshot_store.latest_completed,
            detail_batch_fn=wrap_detail_batch(enrich_store),
            storage_fn=storage_fn,
            consistency_fn=production_consistency(
                snapshot_store=enrich_store,
                display_store=display_store,
            ),
            host=socket.gethostname(),
        )
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
