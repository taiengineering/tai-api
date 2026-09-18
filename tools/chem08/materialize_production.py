"""WO-CHEM-08 production materializer CLI (guarded).

--dry-run:   Load CHEM-05 plan artifacts, run preflight + classification
             + chunk planning against a supplied fixture store, and print
             a compact summary. No DB I/O.

--execute:   Fail-closed. Even with --owner-approved, this WO's writer
             refuses to open any DB connection. A separate future
             execution WO must set
                services.kosha_msds.materialize_writer.PRODUCTION_WRITE_ALLOWED = True
             (there is no CLI flag under this WO that flips it).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from services.kosha_msds import materialize_writer as w


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _print(obj: dict) -> None:
    print(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False))


def _dry_run(args, *, store: w.MemoryMaterializeStore) -> int:
    inputs = w.load_plan_inputs(
        plan_jsonl=Path(args.plan),
        manifest_json=Path(args.manifest),
        report_json=Path(args.report),
    )
    on_disk_plan_file_sha = _file_sha256(Path(args.plan))
    on_disk_responses_sha = None
    if args.responses:
        rp = Path(args.responses)
        if rp.exists():
            on_disk_responses_sha = _file_sha256(rp)

    summary = w.dry_run(
        inputs,
        store=store,
        on_disk_responses_sha256=on_disk_responses_sha,
        on_disk_plan_file_sha256=on_disk_plan_file_sha,
        resume_snapshot_id=args.resume_snapshot,
    )
    summary["mode"] = "DRY_RUN"
    summary["on_disk_plan_file_sha256"] = on_disk_plan_file_sha
    summary["on_disk_responses_sha256"] = on_disk_responses_sha
    _print(summary)
    return 0


def _execute_blocked(args, *, store: w.MemoryMaterializeStore) -> int:
    """This WO forbids production writes. We still run preflight so the
    caller can see the same report the future execution WO will see,
    but we NEVER open a DB connection.
    """
    inputs = w.load_plan_inputs(
        plan_jsonl=Path(args.plan),
        manifest_json=Path(args.manifest),
        report_json=Path(args.report),
    )
    on_disk_plan_file_sha = _file_sha256(Path(args.plan))
    on_disk_responses_sha = (
        _file_sha256(Path(args.responses)) if args.responses else None
    )
    report = w.preflight(
        inputs,
        store=store,
        on_disk_responses_sha256=on_disk_responses_sha,
        on_disk_plan_file_sha256=on_disk_plan_file_sha,
        resume_snapshot_id=args.resume_snapshot,
    )
    try:
        w.assert_can_execute_production_write(
            preflight_report=report,
            owner_approved=bool(args.owner_approved),
        )
        # If we ever reach here under WO-CHEM-08, something is wrong.
        _print({
            "mode": "EXECUTE_BLOCKED",
            "reason": "UNEXPECTED_WO_SCOPE_STATE",
            "detail": (
                f"{w.WO_SCOPE} must keep PRODUCTION_WRITE_ALLOWED=False. "
                "A future execution WO opens this path."
            ),
        })
        return 2
    except w.ProductionWriteForbidden as exc:
        _print({
            "mode": "EXECUTE_BLOCKED",
            "reason": str(exc),
            "wo_scope": w.WO_SCOPE,
            "production_write_allowed": w.PRODUCTION_WRITE_ALLOWED,
            "preflight_block_reasons": list(report.block_reasons),
        })
        return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="WO-CHEM-08 production materializer (dry-run + fail-closed execute)."
    )
    parser.add_argument("--plan", required=True,
                        help="Path to CHEM-05 materialize_plan.jsonl")
    parser.add_argument("--manifest", required=True,
                        help="Path to CHEM-05 materialize_manifest.json")
    parser.add_argument("--report", required=True,
                        help="Path to CHEM-05 materialize_report.json")
    parser.add_argument("--responses", default=None,
                        help="Optional path to hydration responses.jsonl for "
                             "SHA re-verification against the manifest.")
    parser.add_argument("--resume-snapshot", default=None,
                        help="Optional RUNNING snapshot id to resume.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true",
                      help="Blocked under this WO regardless of --owner-approved.")
    parser.add_argument("--owner-approved", action="store_true", default=False,
                        help="Signals owner-level approval. Insufficient by "
                             "itself under WO-CHEM-08; the WO scope also has "
                             "to allow production writes, which it does not.")
    args = parser.parse_args(argv)

    # WO-CHEM-08 never touches a live DB. The CLI is designed against
    # MemoryMaterializeStore only. Callers seed the fixture store as
    # needed. The future execution WO will supply a SupabaseMaterialize
    # store.
    store = w.MemoryMaterializeStore()

    if args.dry_run:
        return _dry_run(args, store=store)
    return _execute_blocked(args, store=store)


if __name__ == "__main__":
    sys.exit(main())
