#!/usr/bin/env python3
"""작업지시서 Step 7: rules_table 파이프라인 검증 (adapter → classify → builder).

paid-diagnosis-result.html 이 소비하는 full_result.rules_table 구조를 검사합니다.

Usage:
  cd ~/Desktop/tai-engineering/tai-api
  set -a && source .env && set +a
  python3 scripts/verify_work_order_step7_rules_table.py
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# format_rule_result_db 출력 + rules_table 행에 필요한 키 (diagnosis_result_web.py)
RULES_TABLE_REQUIRED_KEYS = frozenset(
    {
        "category",
        "rule_id",
        "law_name",
        "law_article",
        "obligation_type",
        "description",
        "obligation_summary",
        "penalty_amount",
        "penalty_summary",
        "appointment_target",
        "inspection_cycle",
        "schedule_type",
    }
)


def _facility_building():
    return {
        "employee_count": 55,
        "building_area": 6000,
        "floor_count": 5,
        "electric_capacity": 500,
        "worker_count": 55,
    }


def _distribution(rules_table: list) -> dict:
    return {
        "total": len(rules_table),
        "law_name_top5": Counter(r.get("law_name") for r in rules_table).most_common(5),
        "category": dict(Counter(r.get("category") for r in rules_table)),
        "obligation_type": dict(Counter(r.get("obligation_type") for r in rules_table)),
        "penalty_summary_present": sum(
            1 for r in rules_table if (r.get("penalty_summary") or r.get("penalty_amount") or "").strip()
        ),
    }


def main() -> int:
    from supabase import create_client

    from services.legal_context import _input_to_facility_context
    from services.legal_diagnosis_rules import fetch_diagnosis_rules
    from services.legal_format import _classify_rules_db, format_rule_result_db
    from services.legal_rules import evaluate_facility_conditions_db, normalize_sector_db, risk_level
    from services.legal_step1_builder import build_step1_result_data
    from services.legal_engine_svc import get_construction_summary

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
    if not url or not key:
        print("SUPABASE_URL / SUPABASE_KEY required")
        return 1

    sb = create_client(url, key)
    sector_raw = "BUILDING"
    sector_db = normalize_sector_db(sector_raw)

    all_rules = fetch_diagnosis_rules(sb, sector_db=sector_db, diagnosis_stage=1)
    facility_ctx = _input_to_facility_context(sector_raw, {"employee_count": 55, "floor_area": 6000})
    applicable, not_applicable = evaluate_facility_conditions_db(facility_ctx, all_rules, sector_raw)

    result_data = build_step1_result_data(
        sector_raw,
        [sector_db],
        "work-order-step7",
        datetime.now().isoformat(),
        facility_ctx,
        applicable,
        not_applicable,
        _classify_rules_db,
        format_rule_result_db,
        risk_level,
        get_construction_summary,
        supabase=sb,
    )

    rules_table = result_data.get("rules_table") or []
    issues: list[str] = []

    if not rules_table:
        issues.append("rules_table is empty")

    for i, row in enumerate(rules_table[:200]):
        missing = RULES_TABLE_REQUIRED_KEYS - set(row.keys())
        if missing:
            issues.append(f"row[{i}] missing keys: {sorted(missing)}")
            break

    # law accordion grouping smoke
    law_groups: dict = {}
    for r in rules_table:
        law_groups.setdefault(r.get("law_name") or "기타", []).append(r)
    if len(law_groups) < 1 and rules_table:
        issues.append("law grouping failed")

    report = {
        "engine_flags": {
            "TAI_USE_RUNTIME_ENGINE": os.environ.get("TAI_USE_RUNTIME_ENGINE"),
            "TAI_USE_V2_ENGINE": os.environ.get("TAI_USE_V2_ENGINE"),
        },
        "rule_pool": len(all_rules),
        "applicable": len(applicable),
        "not_applicable": len(not_applicable),
        "rules_table_distribution": _distribution(rules_table),
        "law_group_count": len(law_groups),
        "risk_level": result_data.get("risk_level"),
        "article_mapping_stats": result_data.get("article_mapping_stats"),
        "issues": issues,
        "sample_row": rules_table[0] if rules_table else None,
    }

    out_path = os.path.join(ROOT, "docs", "work-order-step7-rules-table-report.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nWrote {out_path}")

    if issues:
        print("\nFAIL:", "; ".join(issues))
        return 1
    print("\nOK: rules_table structure valid for paid UI")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
