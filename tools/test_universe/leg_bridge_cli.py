#!/usr/bin/env python3
"""WO-SM-CORE22-E2E-112-BRIDGE-CONTRACT-001 — Official LEG dry-run CLI.

Does not call HTTP. Does not modify e2e_runner_all.py or BEFORE_BASELINE_V1.

  python3 tools/test_universe/leg_bridge_cli.py --dry-run \\
    --universe ~/45cm-test/profile_universe_v1.json \\
    --out ~/45cm-test/leg_e2e_bridge_v1/dry_run
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from services.time import now_kst, serialize_external_utc  # noqa: E402
from leg_bridge import (  # noqa: E402
    EXPECTED_PROFILE_COUNT,
    MAPPING_VERSION,
    WO,
    BridgeContractError,
    load_profile_universe,
    profile_to_leg_request,
    project_universe,
)

FORBIDDEN_OUT_NAMES = {
    "baseline_snapshot_set_v1.json",
    "snapshots_all",
    "before_clean",
    "profile_universe_v1.json",
    "BEFORE_BASELINE_V1",
}


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _assert_out_namespace(out: Path) -> None:
    resolved = out.resolve()
    parts = {p.lower() for p in resolved.parts}
    if "snapshots_all" in parts or "before_clean" in parts:
        raise SystemExit("REFUSE: dry-run out collides with Before namespace")
    if resolved.name in FORBIDDEN_OUT_NAMES:
        raise SystemExit(f"REFUSE: dry-run out name {resolved.name} is a Before artifact")


def _unique_matrix(built: list[dict]) -> list[dict]:
    seen: dict[tuple, dict] = {}
    for item in built:
        for r in item["records"]:
            key = (r["layer"], r["source_field"], r["mapping_type"], r["official_request_field"])
            if key not in seen:
                row = {k: r[k] for k in (
                    "layer", "source_field", "source_unit", "official_request_field",
                    "request_unit", "mapping_type", "production_normalizer", "loss", "evidence",
                )}
                row["example_profile_id"] = item["profile_id"]
                seen[key] = row
    return list(seen.values())


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=WO)
    p.add_argument("--dry-run", action="store_true", required=True,
                   help="Build 112 Official LEG requests. No HTTP.")
    p.add_argument("--universe", default=str(Path.home() / "45cm-test" / "profile_universe_v1.json"))
    p.add_argument("--out", default=str(Path.home() / "45cm-test" / "leg_e2e_bridge_v1" / "dry_run"))
    p.add_argument("--live", action="store_true", help=argparse.SUPPRESS)
    args = p.parse_args(argv)
    if args.live:
        print("PRODUCTION HTTP EXECUTION = FORBIDDEN in this WO", file=sys.stderr)
        return 2

    universe_path = Path(args.universe).expanduser()
    out = Path(args.out).expanduser()
    _assert_out_namespace(out)

    data = load_profile_universe(universe_path)
    profiles = data["profiles"]
    try:
        built, summary = project_universe(profiles)
    except BridgeContractError as e:
        print(f"PROFILE COUNT = {len(profiles)}")
        print("REQUEST BUILD = FAIL")
        print(f"FAIL = {e}")
        return 1

    out.mkdir(parents=True, exist_ok=True)
    req_dir = out / "requests"
    req_dir.mkdir(exist_ok=True)

    amount_map = {}
    for item in built:
        pid = item["profile_id"]
        req = item["request"]
        layers = next(p["layers"] for p in profiles if p["profile_id"] == pid)
        record = {
            "profile_id": pid,
            "sector": item["sector"],
            "profile_source_reference": {
                "universe": str(universe_path),
                "universe_sha256": _sha256_file(universe_path),
            },
            "raw_relevant_layers": {
                "company": layers.get("company"),
                "building": layers.get("building"),
                "process": layers.get("process"),
                "facility": layers.get("facility"),
                "work": layers.get("work"),
                "construction": layers.get("construction"),
            },
            "generated_request_payload": req,
            "mapping_version": item["mapping_version"],
            "request_field_list": item["request_field_list"],
            "omitted_source_fields": item["omitted_source_fields"],
            "unsupported_fields": item["unsupported_fields"],
            "mapping_gaps": item["mapping_gaps"],
            "factory_id": None,
            "company_id": None,
            "project_amount": None,
            "http_executed": 0,
        }
        (req_dir / f"{pid}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        if pid in {f"PF-{i:04d}" for i in range(52, 58)}:
            amount_map[pid] = {
                "profile_eok": (layers.get("construction") or {}).get("contract_amount_eok"),
                "request_eok": req.get("contract_amount_eok"),
            }

    type_counts = summary["type_counts"]
    summary.update({
        "generated_at_utc": serialize_external_utc(now_kst()),
        "universe_path": str(universe_path),
        "universe_sha256": _sha256_file(universe_path),
        "out": str(out.resolve()),
        "mapping_version": MAPPING_VERSION,
        "pf_0052_0057_amount": amount_map,
        "double_normalization": 0,
        "synthetic_default": 0,
        "production_http_execution": 0,
        "baseline_promotion": 0,
        "core22_expected_delta_policy": "NOT DEFINED",
        "cross_pipeline_semantic_diff": "NOT DEFINED",
        "leg_determinism_projection": "GAP",
        "sector_counts": dict(Counter(x["sector"] for x in built)),
    })
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out / "field_mapping_matrix.json").write_text(
        json.dumps(_unique_matrix(built), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"WO = {WO}")
    print(f"PROFILE COUNT = {EXPECTED_PROFILE_COUNT}")
    print(f"REQUEST BUILD = {len(built)} / {EXPECTED_PROFILE_COUNT}")
    print("FAIL = 0")
    print(f"DIRECT = {type_counts.get('DIRECT', 0)}")
    print(f"PRODUCTION_ADAPTER = {type_counts.get('PRODUCTION_ADAPTER', 0)}")
    print(f"UNSUPPORTED = {type_counts.get('UNSUPPORTED', 0)}")
    print(f"NOT_APPLICABLE = {type_counts.get('NOT_APPLICABLE', 0)}")
    print(f"GAP = {type_counts.get('GAP', 0)}")
    print(f"OUT = {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
