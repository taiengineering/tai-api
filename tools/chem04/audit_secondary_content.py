"""Local CLI: stream secondary train.jsonl into a section-presence index.

Full 48,963-row execution belongs on the operator machine, not the Cursor agent.
Does not call KOSHA OpenAPI. Does not write production.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.kosha_msds.contract import SECONDARY_HF_REVISION, SECONDARY_HF_TRAIN_URL
from services.kosha_msds.content_audit import (
    assert_secret_free,
    stream_index_from_path,
    stream_secondary_index,
    write_json,
)
from tools.chem04.paths import CONTENT_CHECKPOINTS, CONTENT_INDEXES, CONTENT_MANIFESTS, ensure_layout


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="CHEM-04 secondary content index (LOCAL full run / Cursor fixture probe)"
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--local-jsonl", help="already-downloaded train.jsonl or a fixture")
    source.add_argument(
        "--download",
        action="store_true",
        help="LOCAL FULL RUN only: stream official HF train.jsonl (~883MB)",
    )
    parser.add_argument("--url", default=SECONDARY_HF_TRAIN_URL)
    parser.add_argument("--revision", default=SECONDARY_HF_REVISION)
    parser.add_argument("--max-rows", type=int, default=None, help="Cursor/fixture probe only")
    parser.add_argument("--resume", action="store_true", help="resume from checkpoint")
    parser.add_argument("--out", default=str(CONTENT_INDEXES / "secondary_content_index.jsonl"))
    parser.add_argument("--checkpoint", default=str(CONTENT_CHECKPOINTS / "secondary_index.json"))
    parser.add_argument("--manifest", default=str(CONTENT_MANIFESTS / "secondary_content_index.json"))
    return parser


def _iter_url_lines(url: str):
    from urllib.request import Request, urlopen

    req = Request(url, headers={"User-Agent": "TAI-CHEM04-content-audit/1.0"})
    with urlopen(req, timeout=120) as resp:
        buf = b""
        while True:
            chunk = resp.read(256 * 1024)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                yield line.decode("utf-8")
        if buf.strip():
            yield buf.decode("utf-8")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.download and args.max_rows is not None:
        raise SystemExit("--max-rows is a probe flag; do not combine with --download")
    ensure_layout()
    dest = Path(args.out)
    checkpoint = Path(args.checkpoint)
    if args.local_jsonl:
        result = stream_index_from_path(
            Path(args.local_jsonl),
            dest,
            source_revision=args.revision,
            max_rows=args.max_rows,
            checkpoint_path=checkpoint,
            resume=bool(args.resume),
            production_writer=None,
        )
        executor = "CURSOR_PROBE" if args.max_rows is not None else "LOCAL"
    else:
        result = stream_secondary_index(
            _iter_url_lines(args.url),
            dest,
            source_revision=args.revision,
            checkpoint_path=checkpoint,
            production_writer=None,
        )
        executor = "LOCAL"
    manifest = {
        "source_local_jsonl": args.local_jsonl,
        "source_url": args.url if args.download else None,
        "dataset_revision": args.revision,
        "identity_phase": "CLOSED",
        "rows": result["rows_total"] if args.resume else result["rows"],
        "invalid_chem_id": result["invalid_chem_id"],
        "observed_schema": result.get("observed_schema"),
        "artifact": str(dest),
        "production_content": "NO",
        "production_writer": None,
        "live_bulk_api_calls": 0,
        "executor": executor,
    }
    text = json.dumps(manifest, ensure_ascii=False)
    assert_secret_free(text)
    write_json(Path(args.manifest), manifest)
    print(json.dumps({"result": result, "executor": executor}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
