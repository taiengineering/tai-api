"""Live sample compare: frozen 16 chemId × Detail01~16. No production write.

Cursor: --probe (max 1 chemId) or --preflight (001008 × Detail01).
Local PC: --local-run (preflight then 16 × 16). 256 re-run is separately authorized.
Service key is read from the environment only and is never logged or serialized.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.kr_public_api import kr_get
from services.kosha_msds.bootstrap_decision import extract_secondary_sections, sample_manifest_hash
from services.kosha_msds.content_audit import (
    assert_secret_free,
    canonical_json_hash,
    sha256_file,
    write_json,
    write_jsonl,
)
from services.kosha_msds.contract import (
    CURSOR_LIVE_SAMPLE_MAX_CHEMS,
    EXPECTED_OPTIONC_SAMPLE_SHA256,
    LIVE_SAMPLE_MAX_CALLS,
)
from services.kosha_msds.live_sample import (
    LiveSampleError,
    assert_manifest_sha,
    live_sample_key,
    load_sample_rows,
    run_live_sample,
    run_preflight,
    scan_secret_free_dir,
)
from tools.chem04.paths import (
    CONTENT_SOURCE,
    DECISION,
    DECISION_CHECKPOINTS,
    DECISION_MANIFESTS,
    DECISION_NORMALIZED,
    DECISION_RAW,
    ensure_layout,
)

FIXTURE_MANIFEST = Path("tests/fixtures/kosha_msds/optionc_live_sample_manifest.json")
PREFLIGHT_REPORT = DECISION / "preflight_report.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CHEM-04 OPTION C live sample compare")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--probe", action="store_true", help="Cursor only: 1 chemId × 16 sections")
    mode.add_argument("--local-run", action="store_true", help="LOCAL PC only: preflight then frozen 16 × 16")
    mode.add_argument("--preflight", action="store_true", help="001008 × getChemDetail01 once; does not resume sample")
    parser.add_argument("--sample-manifest", default=str(FIXTURE_MANIFEST))
    parser.add_argument("--expected-sha", default=EXPECTED_OPTIONC_SAMPLE_SHA256)
    parser.add_argument("--train-jsonl", default=str(CONTENT_SOURCE / "train.jsonl"))
    parser.add_argument("--checkpoint", default=str(DECISION_CHECKPOINTS / "live_sample.json"))
    parser.add_argument("--out-report", default=str(DECISION / "live_sample_report.json"))
    parser.add_argument("--out-comparison", default=str(DECISION / "comparison.jsonl"))
    parser.add_argument("--out-preflight", default=str(PREFLIGHT_REPORT))
    return parser


def _get(url, params=None, timeout=30, **_):
    return kr_get(url, params=params, timeout=timeout)


def _print_report(report: dict, extra: dict | None = None) -> None:
    public = {k: v for k, v in report.items() if k != "chemical_status"}
    if extra:
        public.update(extra)
    printed = json.dumps(public, ensure_ascii=False, indent=2)
    assert_secret_free(printed)
    print(printed)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    key = live_sample_key()
    if not key:
        raise SystemExit("BLOCKED: service key unavailable")
    ensure_layout()
    sample_path = Path(args.sample_manifest)
    rows = load_sample_rows(sample_path)
    actual = assert_manifest_sha(rows, expected=args.expected_sha)

    if args.preflight:
        result = run_preflight(get_fn=_get, service_key=key)
        report = {
            "WO": "WO-CHEM-04-OPTIONC-FETCH-DIAG-001",
            "sample_manifest_sha256_actual": actual,
            "MANIFEST_MATCH": "PASS" if actual == args.expected_sha else "FAIL",
            "production_writer": None,
            "BOOTSTRAP_POLICY": "NOT DECIDED",
            "live_bulk_hydration": "NO",
            "production_ingest": "NO",
            "sample_checkpoint_written": False,
            **result,
        }
        if result.get("fetch_error"):
            report["error_token_counts"] = {str(result["fetch_error"]): 1}
        else:
            report["error_token_counts"] = {}
        report_path = Path(args.out_preflight)
        report["live_sample_report_sha256"] = canonical_json_hash(report)
        write_json(report_path, report)
        scan_secret_free_dir(report_path.parent, extra_tokens=(key,))
        _print_report(report, extra={"preflight_report_file_sha256": sha256_file(report_path)})
        return 0 if result.get("preflight") == "OK" else 2

    dest_manifest = DECISION / "sample_manifest.json"
    dest_manifest.parent.mkdir(parents=True, exist_ok=True)
    dest_manifest.write_text(
        json.dumps({"sample": rows, "sample_manifest_sha256": actual}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    copied = DECISION_MANIFESTS / "sample_manifest.json"
    copied.parent.mkdir(parents=True, exist_ok=True)
    copied.write_text(dest_manifest.read_text(encoding="utf-8"), encoding="utf-8")
    if sample_manifest_hash(rows) != actual:
        raise LiveSampleError("MANIFEST_MISMATCH", "hash changed after copy")
    train = Path(args.train_jsonl)
    if not train.exists():
        raise SystemExit(f"BLOCKED: secondary train.jsonl missing: {train}")
    secondary = extract_secondary_sections(train, {r["chemId"] for r in rows})
    max_chems = CURSOR_LIVE_SAMPLE_MAX_CHEMS if args.probe else 16
    max_calls = 16 if args.probe else LIVE_SAMPLE_MAX_CALLS
    result = run_live_sample(
        sample_rows=rows,
        secondary_by_chem=secondary,
        get_fn=_get,
        service_key=key,
        max_calls=max_calls,
        max_chems=max_chems,
        checkpoint_path=Path(args.checkpoint),
        raw_dir=DECISION_RAW,
        normalized_dir=DECISION_NORMALIZED,
        production_writer=None,
        require_preflight=bool(args.local_run),
    )
    report = dict(result["report"])
    comparison_path = Path(args.out_comparison)
    write_jsonl(comparison_path, result["rows"])
    report_path = Path(args.out_report)
    report["comparison_sha256"] = sha256_file(comparison_path)
    report["sample_manifest_sha256_actual"] = actual
    report["MANIFEST_MATCH"] = "PASS" if actual == args.expected_sha else "FAIL"
    report["live_sample_report_sha256"] = canonical_json_hash(report)
    write_json(report_path, report)
    scan_secret_free_dir(DECISION, extra_tokens=(key,))
    _print_report(report, extra={"live_sample_report_file_sha256": sha256_file(report_path)})
    if report.get("quota_stop") or (report.get("preflight") or {}).get("preflight") == "FAIL":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
