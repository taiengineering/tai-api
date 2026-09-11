"""WP-1C-5B storage CLI — dry-run default; apply requires production version store."""
from __future__ import annotations

import json
import os
from pathlib import Path

from services.kosha_safety_materials.detail_client import StopRun
from services.kosha_safety_materials.storage.hold_store import SupabaseHoldStore, oversize_report
from services.kosha_safety_materials.storage.r2_store import R2Error, R2Store, credentials_from_env, make_s3_client
from services.kosha_safety_materials.storage.runner import (
    apply_assets,
    apply_bulk,
    collect_eligible,
    dry_run_plan,
    lookup_eligible_item,
    stop_run_payload,
    verify_pilot_objects,
)
from services.kosha_safety_materials.storage.store import StorageError
from services.kosha_safety_materials.storage.version_service import (
    SupabaseVersionStore,
    assert_production_versions,
)
from services.kosha_safety_materials.writer import SupabaseStore


def _load_env() -> None:
    root = Path(__file__).resolve().parents[1]
    env_path = root / ".env"
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path)
        load_dotenv()
    except Exception:
        if env_path.is_file():
            for line in env_path.read_text().splitlines():
                s = line.strip()
                if not s or s.startswith("#") or "=" not in s:
                    continue
                k, v = s.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'").strip('"'))
    if not os.getenv("SUPABASE_SERVICE_KEY") and os.getenv("SUPABASE_SERVICE_ROLE_KEY"):
        os.environ["SUPABASE_SERVICE_KEY"] = os.environ["SUPABASE_SERVICE_ROLE_KEY"]


def _r2():
    creds = credentials_from_env()
    return R2Store(make_s3_client(creds), bucket=creds["bucket"])


def _print(obj: dict, code: int = 0) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))
    raise SystemExit(code)


if __name__ == "__main__":
    import argparse
    from services.kosha_safety_materials.storage.runner import StorageQuery

    _load_env()
    p = argparse.ArgumentParser(description="KOSHA Type1/3 original storage")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--limit", type=int, default=0, help="controlled N assets (Gate-3/4)")
    p.add_argument("--asset-id", type=int, default=0, help="controlled single asset_id")
    p.add_argument("--batch-size", type=int, default=20)
    p.add_argument("--verify-pilot", action="store_true")
    args = p.parse_args()
    store = SupabaseStore()
    query = StorageQuery(store.sb)
    holds = SupabaseHoldStore(store.sb)
    if args.dry_run or (not args.apply and not args.verify_pilot):
        out = dry_run_plan(store, query, holds=holds)
        try:
            credentials_from_env()
            out["r2_credentials"] = "PRESENT"
        except R2Error as e:
            out["r2_credentials"] = e.code
        _print(out, 0)
    try:
        r2 = _r2()
    except R2Error as e:
        _print({"status": "R2_INTEGRATION_BLOCKED", "code": e.code}, 2)
    versions = SupabaseVersionStore()
    assert_production_versions(versions)
    try:
        if args.verify_pilot:
            out = verify_pilot_objects(query, r2)
            out["status"] = "PILOT_OK"
            _print(out, 0)
        if args.apply and args.asset_id:
            plan = collect_eligible(store, query, holds=holds)
            items = [x for x in plan["pending"] if int(x.get("asset_id") or 0) == int(args.asset_id)]
            if not items:
                found = lookup_eligible_item(store, query, int(args.asset_id))
                items = [found] if found else []
            if not items:
                _print({"status": "ASSET_NOT_ELIGIBLE", "asset_id": args.asset_id}, 2)
            out = apply_assets(items, store=store, query=query, r2=r2, versions=versions, holds=holds)
            out["status"] = "CONTROLLED"
            _print(out, 0)
        if args.apply and args.limit:
            plan = collect_eligible(store, query, holds=holds)
            items = plan["pending"][: args.limit]
            out = apply_assets(items, store=store, query=query, r2=r2, versions=versions, holds=holds)
            out["status"] = "CONTROLLED"
            _print(out, 0)
        if args.apply:
            out = apply_bulk(store, query, r2, versions, holds=holds, batch_size=args.batch_size)
            _print(out, 0)
    except StopRun as e:
        extra = {}
        try:
            snap = store.latest_completed() or {}
            extra = oversize_report(holds, snap.get("id"))
        except Exception:
            extra = {}
        _print({**stop_run_payload(e), **extra}, 2)
    except StorageError as e:
        _print({"status": e.code}, 2)
    except R2Error as e:
        _print({"status": e.code}, 2)
    _print({"status": "NOOP"}, 0)
