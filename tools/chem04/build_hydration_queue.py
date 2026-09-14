"""Local CLI: section-level delta hydration queue. Does not emit 20,568×16 blindly."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.kosha_msds.content_audit import (
    assert_secret_free,
    coverage_metrics,
    delta_queue_rows,
    write_jsonl,
)
from tools.chem04.paths import CONTENT_COVERAGE, CONTENT_QUEUES, ensure_layout


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CHEM-04 local delta hydration queue")
    parser.add_argument("--coverage", default=str(CONTENT_COVERAGE / "current_content_coverage.jsonl"))
    parser.add_argument("--out", default=str(CONTENT_QUEUES / "hydration_queue.jsonl"))
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
    queue = delta_queue_rows(coverage)
    dest = Path(args.out)
    n = write_jsonl(dest, queue)
    metrics = coverage_metrics(coverage, queue)
    summary = {
        "artifact": str(dest),
        "DELTA_API_CALLS": n,
        "STRICT_API_CALLS": metrics["STRICT_API_CALLS"],
        "API_CALL_REDUCTION": metrics["API_CALL_REDUCTION"],
        "API_CALL_REDUCTION_PCT": metrics["API_CALL_REDUCTION_PCT"],
        "blind_full_matrix_rows": False,
        "production_content": "NO",
        "live_bulk_api_calls": 0,
    }
    assert_secret_free(json.dumps(summary))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
