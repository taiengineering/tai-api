"""WO-CHEM-05 materialize CLI.

Two modes:
    --dry-run        Rebuild the plan from responses.jsonl and print the report.
                     No DB I/O.
    --execute        Refuses to run unless the plan is execute-eligible AND
                     the operator supplies an explicit --i-understand-full-corpus
                     flag. Even then, this WO does NOT perform any DB mutation:
                     WO-CHEM-05-AUTHORITATIVE-INGEST-ADAPTER-001 §17/§27/§45
                     forbid production writes. The runner exits non-zero with
                     an explicit block reason before opening any connection.

Actual production materialization requires a separate future WO with
owner approval; see WO §43-§44.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from services.kosha_msds import materialize as m
from tools.chem05 import build_materialize_plan as planner

BLOCK_ADAPTER_WO_FORBIDS_WRITE = "ADAPTER_WO_FORBIDS_PRODUCTION_WRITE"


def _print(obj: dict) -> None:
    print(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False))


def _do_dry_run(args) -> int:
    report = planner.run(
        responses_path=Path(args.responses),
        census_path=Path(args.census) if args.census else None,
        out_dir=Path(args.out_dir),
    )
    _print({
        "mode": "DRY_RUN",
        "counts": report["counts"],
        "execute_eligible": report["execute_eligible"],
        "execute_block_reasons": report["execute_block_reasons"],
        "plan_semantic_sha256": report["plan_sha256"],
        "plan_file_sha256": report["plan_file_sha256"],
        "manifest_sha256": report["manifest_sha256"],
        "responses_sha256": report["responses_sha256"],
        "artifact_paths": {
            "plan": str(Path(args.out_dir) / "materialize_plan.jsonl"),
            "manifest": str(Path(args.out_dir) / "materialize_manifest.json"),
            "report": str(Path(args.out_dir) / "materialize_report.json"),
        },
    })
    return 0


def _do_execute(args) -> int:
    """Execute path. Fail-closed. Never opens a DB connection under this WO."""
    # Always rebuild the plan from source first, no stale-report shortcuts.
    report = planner.run(
        responses_path=Path(args.responses),
        census_path=Path(args.census) if args.census else None,
        out_dir=Path(args.out_dir),
    )

    if not report["execute_eligible"]:
        _print({
            "mode": "EXECUTE_BLOCKED",
            "reason": "PLAN_NOT_ELIGIBLE",
            "execute_block_reasons": report["execute_block_reasons"],
            "counts": report["counts"],
            "plan_semantic_sha256": report["plan_sha256"],
        })
        return 2

    # Even when eligible, this WO forbids production DB writes (§17/§27/§45).
    # The gate below is intentional and separate from the eligibility check
    # above: execute-eligibility is a data-shape gate; this is a WO-scope gate.
    if not args.i_understand_full_corpus:
        _print({
            "mode": "EXECUTE_BLOCKED",
            "reason": BLOCK_ADAPTER_WO_FORBIDS_WRITE,
            "detail": (
                "This WO (WO-CHEM-05-AUTHORITATIVE-INGEST-ADAPTER-001) forbids "
                "production writes (§17, §27, §45). A future WO with explicit "
                "owner approval is required. --i-understand-full-corpus is not "
                "sufficient by itself under this WO."
            ),
            "counts": report["counts"],
        })
        return 2

    _print({
        "mode": "EXECUTE_BLOCKED",
        "reason": BLOCK_ADAPTER_WO_FORBIDS_WRITE,
        "detail": (
            "This WO forbids production DB mutation. Even with the operator "
            "acknowledging the full-corpus gate, this adapter refuses to open "
            "a DB connection under WO-CHEM-05-AUTHORITATIVE-INGEST-ADAPTER-001."
        ),
        "counts": report["counts"],
    })
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="WO-CHEM-05 materialize CLI (dry-run planner + fail-closed execute)."
    )
    parser.add_argument("--responses", default=str(planner.DEFAULT_RESPONSES))
    parser.add_argument("--census", default=None)
    parser.add_argument("--out-dir", default=str(planner.DEFAULT_OUT_DIR))
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true",
                      help="Build plan + report. No DB I/O.")
    mode.add_argument("--execute", action="store_true",
                      help="Refuses to write; blocked by WO scope.")
    parser.add_argument(
        "--i-understand-full-corpus",
        action="store_true",
        default=False,
        help="Operator acknowledgment for the eligibility gate. Even with "
             "this flag, --execute is blocked by WO scope in this WO.",
    )
    args = parser.parse_args(argv)

    if args.dry_run:
        return _do_dry_run(args)
    if args.execute:
        return _do_execute(args)
    # Argparse's required=True prevents reaching here.
    parser.error("must supply exactly one of --dry-run or --execute")
    return 2


if __name__ == "__main__":
    sys.exit(main())
