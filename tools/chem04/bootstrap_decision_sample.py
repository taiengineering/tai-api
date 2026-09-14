"""Local Decision Gate sample + hole stats. No live OpenAPI. No production write."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.kosha_msds.bootstrap_decision import (
    extract_secondary_sections,
    flatten_msds_xml,
    load_coverage_map,
    sample_manifest_hash,
    select_sample,
    structural_holes_by_section,
)
from services.kosha_msds.content_audit import assert_secret_free, write_json
from services.kosha_msds.current_index import load_current_rows
from tools.chem04.paths import CONTENT_COVERAGE, CONTENT_MANIFESTS, CONTENT_SOURCE, OFFICIAL_CURRENT, ensure_layout

FIXTURE_DIR = Path("tests/fixtures/kosha_msds")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CHEM-04 bootstrap decision sample (local, no live API)")
    parser.add_argument("--official", default=str(OFFICIAL_CURRENT / "kosha_current_index.jsonl"))
    parser.add_argument("--coverage", default=str(CONTENT_COVERAGE / "current_content_coverage.jsonl"))
    parser.add_argument("--train-jsonl", default=str(CONTENT_SOURCE / "train.jsonl"))
    parser.add_argument("--out", default=str(CONTENT_MANIFESTS / "bootstrap_decision_sample.json"))
    parser.add_argument("--no-secondary-extract", action="store_true")
    return parser


def benzene_fixture_flatten() -> dict[int, str]:
    out: dict[int, str] = {}
    for n in range(1, 17):
        path = FIXTURE_DIR / f"benzene_detail_{n:02d}.xml"
        if path.exists():
            out[n] = flatten_msds_xml(path.read_text(encoding="utf-8"))
    return out


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ensure_layout()
    official = load_current_rows(Path(args.official))
    coverage = load_coverage_map(Path(args.coverage))
    sample = select_sample(official, coverage)
    holes = structural_holes_by_section(coverage.values())
    payload: dict[str, object] = {
        "WO": "WO-CHEM-04-BOOTSTRAP-DECISION-001",
        "live_api_calls": 0,
        "sample_chemicals": len(sample),
        "sample_sections_planned": len(sample) * 16,
        "sample_manifest_sha256": sample_manifest_hash(sample),
        "sample": sample,
        "structural_holes_by_section": {f"{n:02d}": holes[n] for n in sorted(holes)},
        "live_official_comparison": "NOT_RUN_SERVICE_KEY_MISSING",
        "production_ingest": "NO",
    }
    train = Path(args.train_jsonl)
    if train.exists() and not args.no_secondary_extract:
        bodies = extract_secondary_sections(train, {str(r["chemId"]) for r in sample})
        payload["secondary_section_counts"] = {cid: len(secs) for cid, secs in bodies.items()}
        fixture = benzene_fixture_flatten()
        if "001008" in bodies and fixture:
            payload["offline_fixture_compare_001008"] = {
                "note": "Historical test fixture, not live current OpenAPI.",
                "sections": {
                    f"{n:02d}": {
                        "fixture_flat_chars": len(fixture.get(n, "")),
                        "secondary_chars": len(bodies["001008"].get(n, "")),
                        "exact": fixture.get(n, "") == bodies["001008"].get(n, ""),
                        "normalized_equal": (fixture.get(n, "") or "").strip()
                        == (bodies["001008"].get(n, "") or "").strip(),
                    }
                    for n in range(1, 17)
                },
            }
    text = json.dumps(payload, ensure_ascii=False)
    assert_secret_free(text)
    write_json(Path(args.out), payload)
    print(json.dumps({k: payload[k] for k in payload if k != "sample"}, ensure_ascii=False, indent=2))
    print(json.dumps({"sample": sample}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
