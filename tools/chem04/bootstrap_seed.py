"""Local CLI: download official HF train.jsonl and write identity-only seed.

Full 48,966-row execution belongs on the operator machine, not the Cursor agent.
Default refuses the Hugging Face download unless --download is passed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.kosha_msds.bootstrap import (
    extract_identity_from_path,
    extract_identity_from_url,
    load_identity_rows,
    seed_stats,
    write_manifest,
)
from services.kosha_msds.contract import (
    SECONDARY_GITHUB_HEAD,
    SECONDARY_HF_REVISION,
    SECONDARY_HF_TRAIN_BYTES,
    SECONDARY_HF_TRAIN_SHA256,
    SECONDARY_HF_TRAIN_URL,
)
from tools.chem04.paths import MANIFESTS, SECONDARY_SEED, ensure_layout


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="CHEM-04 secondary identity seed extract (LOCAL full run / Cursor fixture probe)"
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--local-jsonl",
        help="already-downloaded train.jsonl or a fixture; Cursor probe path",
    )
    source.add_argument(
        "--download",
        action="store_true",
        help="LOCAL FULL RUN only: fetch official HF train.jsonl (~883MB)",
    )
    parser.add_argument("--url", default=SECONDARY_HF_TRAIN_URL)
    parser.add_argument("--revision", default=SECONDARY_HF_REVISION)
    parser.add_argument("--expected-sha256", default=SECONDARY_HF_TRAIN_SHA256)
    parser.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="Cursor/fixture probe only; not valid with --download",
    )
    parser.add_argument(
        "--verify-sha256",
        action="store_true",
        help="LOCAL official train.jsonl only: compare to published HF sha256",
    )
    parser.add_argument("--out", default=str(SECONDARY_SEED / "secondary_identity_seed.jsonl"))
    parser.add_argument("--manifest", default=str(MANIFESTS / "secondary_manifest.json"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.download and args.max_rows is not None:
        raise SystemExit("--max-rows is a probe flag; do not combine with --download")
    ensure_layout()
    dest = Path(args.out)
    verify = bool(args.download or args.verify_sha256)
    expected = (args.expected_sha256 or None) if verify else None
    if args.local_jsonl:
        result = extract_identity_from_path(
            Path(args.local_jsonl),
            dest,
            revision=args.revision,
            expected_sha256=expected,
            max_rows=args.max_rows,
            production_writer=None,
        )
        executor = "CURSOR_PROBE" if args.max_rows is not None else "LOCAL"
    else:
        result = extract_identity_from_url(
            args.url,
            dest,
            revision=args.revision,
            expected_sha256=expected,
            production_writer=None,
        )
        executor = "LOCAL"
    rows = load_identity_rows(dest, revision=args.revision)
    stats = seed_stats(rows)
    stats["invalid_skipped"] = result.get("invalid", 0)
    manifest = {
        "source_url": args.url if args.download else None,
        "source_local_jsonl": args.local_jsonl,
        "source_reference": "https://huggingface.co/datasets/Yuyongkim/inconvenience-msds",
        "github_repo": "https://github.com/yuyongkim/inconvenience-msds",
        "github_head": SECONDARY_GITHUB_HEAD,
        "dataset_revision": args.revision,
        "file_list": ["train.jsonl"],
        "source_file_size": SECONDARY_HF_TRAIN_BYTES if args.download else None,
        "source_sha256": result.get("sha256"),
        "license": "CC BY 4.0 (dataset); MIT (encoder); KOSHA 공공누리 제1유형 (source MSDS)",
        "observed_fields": result["observed_fields"],
        "identity_rows": result["rows"],
        "invalid_chem_id_skipped": result.get("invalid", 0),
        "identity_artifact": str(dest),
        "stats": stats,
        "production_content": "BLOCKED",
        "executor": executor,
    }
    write_manifest(Path(args.manifest), manifest)
    print(json.dumps({"result": result, "stats": stats, "executor": executor}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
