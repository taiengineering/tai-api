#!/usr/bin/env python3
"""작업지시서 Step 4: DB 스키마·샘플·분포 확인 (Seoul Supabase).

Usage:
  cd ~/Desktop/tai-engineering/tai-api
  set -a && source .env && set +a
  python3 scripts/work_order_step4_db_schema.py
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _sample(sb, table: str, limit: int = 1):
    try:
        return sb.table(table).select("*").limit(limit).execute().data or []
    except Exception as e:
        return [{"_error": str(e)[:200]}]


def _count(sb, table: str) -> int | str:
    try:
        res = sb.table(table).select("id", count="exact").limit(0).execute()
        return res.count or 0
    except Exception as e:
        return f"ERROR: {str(e)[:120]}"


def main() -> int:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
    if not url or not key:
        print("SUPABASE_URL / SUPABASE_KEY required")
        return 1

    from supabase import create_client

    sb = create_client(url, key)
    report: dict = {"supabase_url": url, "tables": {}}

    for table in (
        "master_rule_v2",
        "master_rule_v2_relation",
        "master_rule_scope",
        "master_building_legal_rules",
        "runtime_metadata_resolution",
        "rule_candidate",
        "rule_article_mapping",
        "law_article",
    ):
        rows = _sample(sb, table, 1)
        cols = sorted(rows[0].keys()) if rows and "_error" not in rows[0] else []
        report["tables"][table] = {
            "row_count": _count(sb, table),
            "columns": cols,
            "sample_keys_only": cols[:20] if len(cols) > 20 else cols,
        }

    # rule_kind distribution (v2)
    try:
        kinds = sb.table("master_rule_v2").select("rule_kind").limit(5000).execute().data or []
        report["master_rule_v2_rule_kind_sample"] = dict(Counter(r.get("rule_kind") for r in kinds))
    except Exception as e:
        report["master_rule_v2_rule_kind_sample"] = str(e)[:200]

    out_path = os.path.join(ROOT, "docs", "work-order-step4-db-schema-report.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
