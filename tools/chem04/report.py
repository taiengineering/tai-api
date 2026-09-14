"""Local CLI: secret-free CHEM-04 artifact report. Does not call production."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from tools.chem04.paths import JOINS, MANIFESTS, OFFICIAL_CURRENT, ROOT, SECONDARY_SEED, ensure_layout

LEGACY_SEED = ROOT / "secondary_identity_seed.jsonl"
LEGACY_MANIFEST = ROOT / "secondary_manifest.json"


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def resolve_existing(*candidates: Path) -> Path:
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CHEM-04 local artifact summary (secret-free)")
    parser.add_argument("--seed")
    parser.add_argument("--official")
    parser.add_argument("--join")
    parser.add_argument("--manifest")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ensure_layout()
    seed = Path(args.seed) if args.seed else resolve_existing(SECONDARY_SEED / "secondary_identity_seed.jsonl", LEGACY_SEED)
    official = Path(args.official) if args.official else OFFICIAL_CURRENT / "kosha_current_index.jsonl"
    join = Path(args.join) if args.join else JOINS / "chem_current_identity_join.jsonl"
    manifest = Path(args.manifest) if args.manifest else resolve_existing(MANIFESTS / "secondary_manifest.json", LEGACY_MANIFEST)
    report = {
        "executor": "LOCAL",
        "production_ingest": "NO",
        "secondary_seed_path": str(seed),
        "secondary_seed_rows": _count_lines(seed),
        "secondary_seed_sha256": _sha256(seed),
        "official_current_rows": _count_lines(official),
        "official_current_sha256": _sha256(official),
        "join_rows": _count_lines(join),
        "join_sha256": _sha256(join),
        "manifest_present": manifest.exists(),
        "manifest_path": str(manifest) if manifest.exists() else None,
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    assert "serviceKey" not in text
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
