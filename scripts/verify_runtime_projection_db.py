#!/usr/bin/env python3
"""Runtime Engine projection 스모크 (Seoul Supabase).

Usage:
  cd /path/to/tai-engineering/tai-api
  set -a && source .env && set +a
  python3 scripts/verify_runtime_projection_db.py

  (Desktop 기준)
  cd ~/Desktop/tai-engineering/tai-api && set -a && source .env && set +a && python3 scripts/verify_runtime_projection_db.py
"""

from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.legal_runtime_fetch import fetch_runtime_rules_as_v1
from services.rule_candidate_projection import project_metadata_to_v1


def main() -> int:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
    if not url or not key:
        print("SUPABASE_URL / SUPABASE_KEY required")
        return 1

    from supabase import create_client

    sb = create_client(url, key)

    for table in (
        "runtime_metadata_resolution",
        "rule_candidate",
        "task_candidate",
        "executable_draft",
        "facility_applicability",
        "master_building_legal_rules",
        "master_rule_v2",
    ):
        try:
            res = sb.table(table).select("id", count="exact").limit(0).execute()
            print(f"{table}: {res.count} rows")
        except Exception as e:
            print(f"{table}: ERROR {str(e)[:120]}")

    sample = (
        sb.table("runtime_metadata_resolution")
        .select("*")
        .limit(1)
        .execute()
        .data
        or []
    )
    if sample:
        v1 = project_metadata_to_v1(sample[0], sector_hint="BUILDING")
        print("\n=== sample projection ===")
        print(json.dumps({k: v1[k] for k in ("rule_id", "law_name", "law_article", "obligation_type", "obligation_summary", "sector")}, ensure_ascii=False, indent=2))

    for sector in ("BUILDING", "MANUFACTURING", "CONSTRUCTION"):
        rules = fetch_runtime_rules_as_v1(sb, sector_db=sector, diagnosis_stage=1)
        print(f"\n{sector} projected rules (stage=1): {len(rules)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
