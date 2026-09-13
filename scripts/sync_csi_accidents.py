"""CSI official CSV sync CLI. Default is dry-run. No Graph/R2 writes."""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.csi_accidents.contract import APPLY_ENABLE_ENV, OFFICIAL_FILENAME
from services.csi_accidents.sync import download_official_csv, sync_csi_accidents


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="CSI accident CSV sync (dry-run default)")
    p.add_argument("--csv", help="Local official CSV bytes path")
    p.add_argument("--download", action="store_true", help="Download official 15108262 file")
    p.add_argument("--filename", default=OFFICIAL_FILENAME)
    p.add_argument(
        "--apply",
        action="store_true",
        help=f"Write catalog/snapshots. Requires {APPLY_ENABLE_ENV}=1",
    )
    args = p.parse_args(argv)

    if args.csv:
        with open(args.csv, "rb") as f:
            data = f.read()
    elif args.download:
        data = download_official_csv()
    else:
        print("pass --csv PATH or --download", file=sys.stderr)
        return 2

    dry_run = not args.apply
    store = None
    if args.apply:
        from db.supabase_client import get_supabase
        from services.csi_accidents.store import SupabaseCsiStore

        store = SupabaseCsiStore(get_supabase())

    result = sync_csi_accidents(
        data=data,
        filename=args.filename,
        dry_run=dry_run,
        store=store,
    )
    payload = dict(result.__dict__)
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    if result.status in {"REJECT", "FAILED"}:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
