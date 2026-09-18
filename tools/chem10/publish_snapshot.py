"""WO-CHEM-10 publish promoter CLI (guarded).

--dry-run:   Load a snapshot by id (from a MemoryPublishStore under
             this WO), run preflight, print the report. No DB I/O.

--execute:   Fail-closed. Even with --owner-approved, this WO's
             promoter refuses to open any DB connection or to call the
             fixture-side promote helper against a live store. A
             separate future execution WO must set
             `services.kosha_msds.publish.PRODUCTION_PUBLISH_ALLOWED = True`
             (there is no CLI flag under this WO that flips it).
"""
from __future__ import annotations

import argparse
import json
import sys

from services.kosha_msds import publish as p


def _print(obj: dict) -> None:
    print(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False))


def _dry_run(args, *, store: p.MemoryPublishStore) -> int:
    report = p.dry_run(
        args.snapshot_id,
        store=store,
        owner_approved=bool(args.owner_approved),
    )
    report["mode"] = "DRY_RUN"
    _print(report)
    return 0


def _execute_blocked(args, *, store: p.MemoryPublishStore) -> int:
    report = p.preflight_publish(args.snapshot_id, store=store)
    try:
        p.assert_can_execute_publish(
            report=report,
            owner_approved=bool(args.owner_approved),
        )
        _print({
            "mode": "EXECUTE_BLOCKED",
            "reason": "UNEXPECTED_WO_SCOPE_STATE",
            "detail": (
                f"{p.WO_SCOPE} must keep PRODUCTION_PUBLISH_ALLOWED=False. "
                "A future execution WO opens this path."
            ),
        })
        return 2
    except p.PublicationForbidden as exc:
        _print({
            "mode": "EXECUTE_BLOCKED",
            "reason": str(exc),
            "wo_scope": p.WO_SCOPE,
            "production_publish_allowed": p.PRODUCTION_PUBLISH_ALLOWED,
            "preflight_block_reasons": list(report.block_reasons),
        })
        return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="WO-CHEM-10 publish promoter (dry-run + fail-closed execute)."
    )
    parser.add_argument("--snapshot-id", required=True,
                        help="UUID of the kosha_msds_snapshots row to inspect.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true",
                      help="Blocked under this WO regardless of --owner-approved.")
    parser.add_argument("--owner-approved", action="store_true", default=False,
                        help="Signals owner-level approval. Insufficient by "
                             "itself under WO-CHEM-10; the WO scope also has "
                             "to allow production publication, which it does not.")
    args = parser.parse_args(argv)

    # WO-CHEM-10 never touches a live DB. The CLI is designed against
    # MemoryPublishStore. Callers seed the store in tests. The future
    # execution WO will supply a SupabasePublishStore.
    store = p.MemoryPublishStore()

    if args.dry_run:
        return _dry_run(args, store=store)
    return _execute_blocked(args, store=store)


if __name__ == "__main__":
    sys.exit(main())
