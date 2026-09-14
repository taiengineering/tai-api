"""Local CLI: deterministic join of official current index to secondary chemId seed."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.kosha_msds.bootstrap import load_identity_rows
from services.kosha_msds.contract import SECONDARY_HF_REVISION
from services.kosha_msds.current_index import load_current_rows
from services.kosha_msds.identity_join import join_counts, join_official_to_secondary
from tools.chem04.paths import JOINS, OFFICIAL_CURRENT, SECONDARY_SEED, ensure_layout


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CHEM-04 local official×secondary identity join")
    parser.add_argument("--official", default=str(OFFICIAL_CURRENT / "kosha_current_index.jsonl"))
    parser.add_argument("--seed", default=str(SECONDARY_SEED / "secondary_identity_seed.jsonl"))
    parser.add_argument("--out", default=str(JOINS / "chem_current_identity_join.jsonl"))
    parser.add_argument("--revision", default=SECONDARY_HF_REVISION)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ensure_layout()
    official = load_current_rows(Path(args.official))
    secondary = load_identity_rows(Path(args.seed), revision=args.revision)
    joined = join_official_to_secondary(official, secondary)
    dest = Path(args.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8") as fh:
        for row in joined:
            fh.write(json.dumps(row.as_row(), ensure_ascii=False) + "\n")
    counts = join_counts(joined)
    print(json.dumps({"artifact": str(dest), "counts": counts}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
