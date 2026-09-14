"""Local CLI: exact chemId join of official current index to secondary content index."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.kosha_msds.content_audit import (
    assert_secret_free,
    join_coverage,
    load_index_rows,
    write_jsonl,
)
from services.kosha_msds.current_index import load_current_rows
from tools.chem04.paths import CONTENT_COVERAGE, CONTENT_INDEXES, OFFICIAL_CURRENT, ensure_layout


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CHEM-04 local current×secondary content coverage")
    parser.add_argument("--official", default=str(OFFICIAL_CURRENT / "kosha_current_index.jsonl"))
    parser.add_argument("--index", default=str(CONTENT_INDEXES / "secondary_content_index.jsonl"))
    parser.add_argument("--out", default=str(CONTENT_COVERAGE / "current_content_coverage.jsonl"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ensure_layout()
    official = load_current_rows(Path(args.official))
    index = load_index_rows(Path(args.index))
    coverage = join_coverage(official, index)
    dest = Path(args.out)
    n = write_jsonl(dest, coverage)
    summary = {
        "artifact": str(dest),
        "rows": n,
        "match_method": "CHEMID_EXACT",
        "production_content": "NO",
        "live_bulk_api_calls": 0,
    }
    assert_secret_free(json.dumps(summary))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
