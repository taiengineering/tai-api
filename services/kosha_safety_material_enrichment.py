"""WP-1C-4B production entry: current snapshot detail enrichment."""
from __future__ import annotations

import json
import os

from services.kosha_safety_materials.enrichment import (
    DEFAULT_BATCH,
    dry_run_plan,
    run_one_batch,
    run_until_done,
    snapshot_precondition,
)
from services.kosha_safety_materials.writer import SupabaseStore


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass
    if not os.getenv("SUPABASE_SERVICE_KEY") and os.getenv("SUPABASE_SERVICE_ROLE_KEY"):
        os.environ["SUPABASE_SERVICE_KEY"] = os.environ["SUPABASE_SERVICE_ROLE_KEY"]


if __name__ == "__main__":
    import argparse

    _load_env()
    p = argparse.ArgumentParser(description="KOSHA current-membership detail enrichment")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--batch-size", type=int, default=DEFAULT_BATCH)
    p.add_argument("--once", action="store_true", help="한 batch만")
    args = p.parse_args()
    store = SupabaseStore()
    if args.dry_run or not args.apply:
        out = dry_run_plan(store, batch_size=args.batch_size)
    elif args.once:
        pre = snapshot_precondition(store)
        out = run_one_batch(store, run_snapshot_id=pre["snapshot"]["id"], batch_size=args.batch_size, dry_run=False)
    else:
        out = run_until_done(store, batch_size=args.batch_size, dry_run=False)
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
