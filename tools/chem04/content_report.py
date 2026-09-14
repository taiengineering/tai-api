"""Local CLI: secret-free content audit report + artifact hashes. No production write."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.kosha_msds.content_audit import (
    assert_secret_free,
    canonical_json_hash,
    count_jsonl,
    coverage_metrics,
    delta_queue_rows,
    endpoint_counts,
    quota_scenarios,
    sha256_file,
    write_json,
)
from tools.chem04.paths import (
    CONTENT_COVERAGE,
    CONTENT_INDEXES,
    CONTENT_MANIFESTS,
    CONTENT_QUEUES,
    CONTENT_REPORTS,
    ensure_layout,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CHEM-04 local content audit report")
    parser.add_argument("--index", default=str(CONTENT_INDEXES / "secondary_content_index.jsonl"))
    parser.add_argument("--coverage", default=str(CONTENT_COVERAGE / "current_content_coverage.jsonl"))
    parser.add_argument("--queue", default=str(CONTENT_QUEUES / "hydration_queue.jsonl"))
    parser.add_argument("--out", default=str(CONTENT_REPORTS / "content_audit_report.json"))
    parser.add_argument("--manifest", default=str(CONTENT_MANIFESTS / "content_manifest.json"))
    return parser


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ensure_layout()
    coverage = _load_jsonl(Path(args.coverage))
    queue_path = Path(args.queue)
    queue = _load_jsonl(queue_path) if queue_path.exists() else delta_queue_rows(coverage)
    metrics = coverage_metrics(coverage, queue)
    quota = quota_scenarios(
        int(metrics["DELTA_API_CALLS"]),
        int(metrics["STRICT_API_CALLS"]),
        endpoint_counts(queue),
    )
    canonical = {
        "WO": "WO-CHEM-04-CONTENT-LOCAL-001",
        "metrics": metrics,
        "quota_scenarios": quota,
        "secondary_index_rows": count_jsonl(Path(args.index)),
        "coverage_rows": len(coverage),
        "queue_rows": len(queue),
        "production_ingest": "NO",
        "FULL_DETAIL_HYDRATION": "NOT STARTED",
        "live_bulk_api_calls": 0,
    }
    report = dict(canonical)
    report["canonical_sha256"] = canonical_json_hash(canonical)
    dest = Path(args.out)
    write_json(dest, report)
    hashes = {
        "secondary_content_index": {
            "path": args.index,
            "sha256": sha256_file(Path(args.index)),
            "row_count": count_jsonl(Path(args.index)),
        },
        "current_content_coverage": {
            "path": args.coverage,
            "sha256": sha256_file(Path(args.coverage)),
            "row_count": len(coverage),
        },
        "hydration_queue": {
            "path": args.queue,
            "sha256": sha256_file(queue_path),
            "row_count": len(queue),
        },
        "report": {
            "path": str(dest),
            "sha256": report["canonical_sha256"],
            "file_sha256": sha256_file(dest),
        },
        "source_revision": None,
        "production_ingest": "NO",
    }
    write_json(Path(args.manifest), hashes)
    text = json.dumps({"report": report, "manifest": hashes}, ensure_ascii=False, indent=2)
    assert_secret_free(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
