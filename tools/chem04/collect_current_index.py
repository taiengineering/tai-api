"""Local CLI: collect KOSHA official current chemList index.

Full ~2,000-page run belongs on the operator machine.
Cursor/agent may only dry-run with --max-pages 1..3.
Bare invocation without --max-pages or --full is refused.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.kosha_msds.current_index import collect_current_index
from tools.chem04.paths import CHECKPOINTS, OFFICIAL_CURRENT, ensure_layout


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CHEM-04 KOSHA current index collect")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--max-pages",
        type=int,
        help="small probe only (Cursor: 1..3). Do not use for the ~2057-page run.",
    )
    mode.add_argument(
        "--full",
        action="store_true",
        help="LOCAL FULL RUN only: collect every official current page",
    )
    parser.add_argument("--out", default=str(OFFICIAL_CURRENT / "kosha_current_index.jsonl"))
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--resume", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ensure_layout()
    summary = collect_current_index(
        dest=Path(args.out),
        delay_s=args.delay,
        max_pages=None if args.full else args.max_pages,
        log_progress=True,
        resume=args.resume,
    )
    summary["executor"] = "LOCAL" if args.full else "CURSOR_PROBE"
    (CHECKPOINTS / "current_index_last.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
