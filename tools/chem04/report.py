"""Local CLI: secret-free CHEM-04 artifact report. Does not call production."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from tools.chem04.paths import JOINS, MANIFESTS, OFFICIAL_CURRENT, SECONDARY_SEED, ensure_layout


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


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description="CHEM-04 local artifact summary (secret-free)")


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    ensure_layout()
    seed = SECONDARY_SEED / "secondary_identity_seed.jsonl"
    official = OFFICIAL_CURRENT / "kosha_current_index.jsonl"
    join = JOINS / "chem_current_identity_join.jsonl"
    manifest = MANIFESTS / "secondary_manifest.json"
    report = {
        "executor": "LOCAL",
        "production_ingest": "NO",
        "secondary_seed_rows": _count_lines(seed),
        "secondary_seed_sha256": _sha256(seed),
        "official_current_rows": _count_lines(official),
        "official_current_sha256": _sha256(official),
        "join_rows": _count_lines(join),
        "join_sha256": _sha256(join),
        "manifest_present": manifest.exists(),
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    assert "serviceKey" not in text
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
