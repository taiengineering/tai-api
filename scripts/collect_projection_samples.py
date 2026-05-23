#!/usr/bin/env python3
"""Step 1: 실제 진단 파이프라인 4단계 샘플 수집.

Usage:
  cd ~/Desktop/tai-engineering/tai-api
  set -a && source .env && set +a
  python3 scripts/collect_projection_samples.py              # fast: 12 cases, paid only
  python3 scripts/collect_projection_samples.py --full       # 24 cases (free+paid)
  python3 scripts/collect_projection_samples.py --limit 4    # first 4 cases only
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SAMPLES_ROOT = ROOT / "docs" / "projection_samples"

CASE_MATRIX: List[Dict[str, Any]] = [
    {"slug": "building_small", "sector": "BUILDING", "employee_count": 5, "floor_area": 500},
    {"slug": "building_medium", "sector": "BUILDING", "employee_count": 50, "floor_area": 3000},
    {"slug": "building_large", "sector": "BUILDING", "employee_count": 300, "floor_area": 15000},
    {"slug": "manufacturing_small", "sector": "MANUFACTURING", "employee_count": 5, "floor_area": 500},
    {"slug": "manufacturing_medium", "sector": "MANUFACTURING", "employee_count": 50, "floor_area": 3000},
    {"slug": "manufacturing_large", "sector": "MANUFACTURING", "employee_count": 300, "floor_area": 10000},
    {
        "slug": "construction_small",
        "sector": "CONSTRUCTION",
        "worker_count": 20,
        "contract_amount_eok": 5,
        "construction_type": "BUILDING",
    },
    {
        "slug": "construction_large",
        "sector": "CONSTRUCTION",
        "worker_count": 120,
        "contract_amount_eok": 80,
        "construction_type": "BUILDING",
    },
    {"slug": "building_zero", "sector": "BUILDING", "employee_count": 0, "floor_area": 200},
    {"slug": "building_xlarge", "sector": "BUILDING", "employee_count": 1000, "floor_area": 50000},
    {"slug": "special_facility", "sector": "SPECIAL_FACILITY", "employee_count": 30, "floor_area": 2000},
    {"slug": "manufacturing_edge", "sector": "MANUFACTURING", "employee_count": 1, "floor_area": 50},
]

_RUNTIME_RAW_CAP = 200
_PROJECTION_CAP = 200


def _build_ui_json(full_result: Dict[str, Any], input_data: Dict[str, Any]) -> Dict[str, Any]:
    rules_table = [r for r in (full_result.get("rules_table") or []) if isinstance(r, dict)]
    law_groups: Dict[str, list] = {}
    for r in rules_table:
        law_groups.setdefault(r.get("law_name") or "기타", []).append(r)
    ob_counts: Dict[str, int] = {}
    for r in rules_table:
        ot = r.get("obligation_type") or "OTHER"
        ob_counts[ot] = ob_counts.get(ot, 0) + 1
    return {
        "sector": full_result.get("sector"),
        "applicable_count": full_result.get("applicable_count"),
        "risk_level": full_result.get("risk_level"),
        "rules_table_count": len(rules_table),
        "law_group_count": len(law_groups),
        "law_groups_top5": sorted(
            [{"law_name": k, "count": len(v)} for k, v in law_groups.items()],
            key=lambda x: x["count"],
            reverse=True,
        )[:5],
        "obligation_type_counts": ob_counts,
        "projection_cleanup_stats": full_result.get("projection_cleanup_stats"),
        "input_data": input_data,
    }


def _fetch_runtime_raw(sb, rule_ids: List[str], cap: int = _RUNTIME_RAW_CAP) -> List[Dict[str, Any]]:
    runtime_raw: List[Dict[str, Any]] = []
    ids = rule_ids[:cap]
    for i in range(0, len(ids), 80):
        chunk = ids[i : i + 80]
        res = sb.table("runtime_metadata_resolution").select("*").in_("id", chunk).execute()
        runtime_raw.extend(res.data or [])
    return runtime_raw


def run_case(
    sb,
    case: Dict[str, Any],
    variant: str,
    *,
    rules_cache: Dict[str, List[Dict[str, Any]]],
    skip_articles: bool,
) -> Dict[str, Any]:
    from services.legal_context import _input_to_facility_context
    from services.legal_format import _classify_rules_db
    from services.legal_rules import evaluate_facility_conditions_db, normalize_sector_db, risk_level
    from services.projection_cleanup import apply_rules_table_cleanup

    sector_raw = case["sector"]
    sector_db = normalize_sector_db(sector_raw)
    inp = {k: v for k, v in case.items() if k not in ("slug", "sector")}
    facility_ctx = _input_to_facility_context(sector_raw, inp)

    if sector_db not in rules_cache:
        from services.legal_diagnosis_rules import fetch_diagnosis_rules

        print(f"  loading rule pool for {sector_db}...")
        rules_cache[sector_db] = fetch_diagnosis_rules(sb, sector_db=sector_db, diagnosis_stage=1)

    all_rules = rules_cache[sector_db]
    applicable, not_applicable = evaluate_facility_conditions_db(facility_ctx, all_rules, sector_raw)

    rule_ids = [str(r.get("rule_id")) for r in applicable if r.get("rule_id")]
    runtime_raw = _fetch_runtime_raw(sb, rule_ids)

    triggered: Dict[str, List] = {
        "appointment": [],
        "inspection": [],
        "notify": [],
        "report": [],
        "action": [],
        "not_applicable": [],
    }
    article_ctx = None
    if not skip_articles and rule_ids:
        from services.legal_article_loader import fetch_article_contexts

        try:
            article_ctx = fetch_article_contexts(sb, rule_ids[:100], rules=applicable[:100])
        except Exception as e:
            print(f"  article lookup skipped: {e}")
    try:
        _classify_rules_db(applicable, triggered, article_ctx)
    except TypeError:
        _classify_rules_db(applicable, triggered)

    rules_table_raw: List[Dict[str, Any]] = []
    for key, label in [("appointment", "선임"), ("inspection", "점검"), ("action", "조치")]:
        for row in triggered[key]:
            rules_table_raw.append({"category": label, **row})
    for row in triggered["report"]:
        rules_table_raw.append({"category": "신고", **row})
    for row in triggered["notify"]:
        rules_table_raw.append({"category": "보고", **row})

    rules_before = copy.deepcopy(rules_table_raw)
    cleanup_stats = apply_rules_table_cleanup(rules_table_raw)
    visible = [r for r in rules_table_raw if not r.get("_overflow")]
    appointment_n = len([r for r in visible if r.get("category") == "선임"])

    result_data = {
        "sector": sector_raw,
        "rules_table": rules_table_raw,
        "applicable_count": len(visible),
        "risk_level": risk_level(len(visible), appointment_n),
        "projection_cleanup_stats": cleanup_stats,
        "not_applicable_total": len(not_applicable),
        "total_rules_checked": len(applicable) + len(not_applicable),
    }

    ui_json = _build_ui_json(result_data, inp)

    return {
        "name": f"{case['slug']}_{variant}",
        "case": case,
        "variant": variant,
        "runtime_raw_count": len(runtime_raw),
        "projection_count": len(applicable),
        "rules_table_after_count": len(rules_table_raw),
        "files": {
            "01_runtime_raw.json": runtime_raw,
            "02_projection.json": applicable[:_PROJECTION_CAP],
            "03_rules_table.json": rules_table_raw,
            "03_rules_table_before_cleanup.json": rules_before,
            "04_ui_json.json": ui_json,
        },
        "pre_cleanup_count": len(rules_before),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect projection pipeline samples")
    parser.add_argument("--full", action="store_true", help="Collect free+paid variants (24 samples)")
    parser.add_argument("--limit", type=int, default=0, help="Max case count from matrix")
    parser.add_argument("--with-articles", action="store_true", help="Fetch article text (slower)")
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove existing sample_* dirs before collecting",
    )
    args = parser.parse_args()

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
    if not url or not key:
        print("SUPABASE_URL / SUPABASE_KEY required")
        return 1

    from supabase import create_client

    sb = create_client(url, key)
    SAMPLES_ROOT.mkdir(parents=True, exist_ok=True)

    if args.clean:
        removed = 0
        for d in SAMPLES_ROOT.iterdir():
            if d.is_dir() and d.name.startswith("sample_"):
                import shutil

                shutil.rmtree(d)
                removed += 1
        print(f"Cleaned {removed} old sample dirs")

    cases = CASE_MATRIX[: args.limit] if args.limit else CASE_MATRIX
    variants = ("free", "paid") if args.full else ("paid",)
    rules_cache: Dict[str, List[Dict[str, Any]]] = {}

    manifest: List[Dict[str, Any]] = []
    idx = 0
    for case in cases:
        for variant in variants:
            idx += 1
            sample_name = f"sample_{idx:03d}_{case['slug']}_{variant}"
            print(f"Collecting {sample_name}...")
            try:
                payload = run_case(
                    sb,
                    case,
                    variant,
                    rules_cache=rules_cache,
                    skip_articles=not args.with_articles,
                )
            except KeyboardInterrupt:
                print("\nInterrupted — partial manifest saved")
                break
            except Exception as e:
                print(f"  FAIL: {e}")
                continue
            sample_dir = SAMPLES_ROOT / sample_name
            sample_dir.mkdir(parents=True, exist_ok=True)
            for fname, data in payload["files"].items():
                with open(sample_dir / fname, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            meta = {k: v for k, v in payload.items() if k != "files"}
            with open(sample_dir / "meta.json", "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
            manifest.append({"sample": sample_name, **meta})

    manifest_path = SAMPLES_ROOT / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({"collected_at": datetime.now().isoformat(), "samples": manifest}, f, ensure_ascii=False, indent=2)
    print(f"Collected {len(manifest)} samples → {SAMPLES_ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
