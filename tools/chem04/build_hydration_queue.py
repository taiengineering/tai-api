"""Local CLI: section-level hydration queues. Does not emit 20,568×16 blindly.

Writes two queues:
- hydration_queue.jsonl = AUTHORITATIVE_VERIFY (holes + REVISION_UNKNOWN + REVISION_CHANGED)
- structural_delta_queue.jsonl = STRUCTURAL_DELTA (holes only; bootstrap-as-is)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.kosha_msds.content_audit import (
    assert_secret_free,
    authoritative_verify_queue_rows,
    coverage_metrics,
    structural_queue_rows,
    write_jsonl,
)
from tools.chem04.paths import CONTENT_COVERAGE, CONTENT_QUEUES, ensure_layout


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CHEM-04 local structural + authoritative hydration queues")
    parser.add_argument("--coverage", default=str(CONTENT_COVERAGE / "current_content_coverage.jsonl"))
    parser.add_argument("--out", default=str(CONTENT_QUEUES / "hydration_queue.jsonl"))
    parser.add_argument(
        "--structural-out",
        default=str(CONTENT_QUEUES / "structural_delta_queue.jsonl"),
    )
    return parser


def _load_coverage(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ensure_layout()
    coverage = _load_coverage(Path(args.coverage))
    structural = structural_queue_rows(coverage)
    verify = authoritative_verify_queue_rows(coverage)
    dest = Path(args.out)
    structural_dest = Path(args.structural_out)
    verify_n = write_jsonl(dest, verify)
    structural_n = write_jsonl(structural_dest, structural)
    metrics = coverage_metrics(coverage)
    summary = {
        "artifact": str(dest),
        "structural_artifact": str(structural_dest),
        "STRICT_API_CALLS": metrics["STRICT_API_CALLS"],
        "STRUCTURAL_DELTA_CALLS": structural_n,
        "AUTHORITATIVE_VERIFY_CALLS": verify_n,
        "DELTA_API_CALLS": verify_n,
        "DELTA_API_CALLS_MEANS": "AUTHORITATIVE_VERIFY_CALLS",
        "API_CALL_REDUCTION": metrics["API_CALL_REDUCTION"],
        "API_CALL_REDUCTION_PCT": metrics["API_CALL_REDUCTION_PCT"],
        "STRUCTURAL_API_CALL_REDUCTION": metrics["STRUCTURAL_API_CALL_REDUCTION"],
        "STRUCTURAL_API_CALL_REDUCTION_PCT": metrics["STRUCTURAL_API_CALL_REDUCTION_PCT"],
        "blind_full_matrix_rows": False,
        "production_content": "NO",
        "live_bulk_api_calls": 0,
    }
    assert_secret_free(json.dumps(summary))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
