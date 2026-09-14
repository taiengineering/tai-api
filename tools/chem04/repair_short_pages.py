"""Refetch only under-parsed official-index pages. Not a full crawl."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.kosha_msds.current_index import repair_short_pages
from tools.chem04.paths import CHECKPOINTS, OFFICIAL_CURRENT, ensure_layout


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="CHEM-04 repair under-parsed current-index pages (local, not a 2057-page recrawl)"
    )
    parser.add_argument("--out", default=str(OFFICIAL_CURRENT / "kosha_current_index.jsonl"))
    parser.add_argument("--delay", type=float, default=1.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ensure_layout()
    summary = repair_short_pages(dest=Path(args.out), delay_s=args.delay, log_progress=True)
    summary["executor"] = "LOCAL"
    (CHECKPOINTS / "current_index_repair.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
