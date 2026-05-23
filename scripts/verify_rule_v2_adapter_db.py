#!/usr/bin/env python3
"""master_rule_v2 스키마 샘플 조회 + adapter 스모크 (로컬/Railway에서 실행).

Usage:
  cd tai-api && set -a && source .env && set +a
  python3 scripts/verify_rule_v2_adapter_db.py
"""

from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.rule_v2_adapter import adapt_v2_to_v1, adapt_v2_batch


def _check_keys() -> list[str]:
    issues: list[str] = []
    key = os.environ.get("SUPABASE_KEY") or ""
    svc = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""
    if len(key) < 100:
        issues.append(
            "SUPABASE_KEY가 너무 짧습니다 (~200자 JWT 필요). "
            ".env.example의 eyJxxx 플레이스홀더가 아닌 Supabase 대시보드/Railway 값을 넣으세요."
        )
    if len(svc) < 100:
        issues.append("SUPABASE_SERVICE_ROLE_KEY가 너무 짧습니다 (service_role JWT 필요).")
    if "xntdkrjhgcscmqctdzyo" in (os.environ.get("SUPABASE_URL") or ""):
        issues.append(
            "SUPABASE_URL이 구 프로젝트(xntdkrjhgcscmqctdzyo)입니다. "
            "vwlahtguyggrhvslabax 로 변경하세요."
        )
    return issues


def main() -> int:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
    if not url or not key:
        print("SUPABASE_URL / SUPABASE_KEY required")
        return 1

    for msg in _check_keys():
        print(f"WARN: {msg}")

    from supabase import create_client

    try:
        sb = create_client(url, key)
    except Exception as e:
        print(f"client error: {e}")
        return 1

    for table in (
        "master_rule_v2",
        "master_rule_v2_relation",
        "master_rule_scope",
        "master_building_legal_rules",
    ):
        try:
            res = sb.table(table).select("*").limit(1).execute()
        except Exception as e:
            err = str(e)
            if "Invalid API key" in err or "401" in err:
                print(
                    "\n401 Invalid API key — Railway에서 동기화:\n"
                    "  cd tai-api && railway variables --json | python3 -c \"...\"\n"
                    "  또는 Supabase 대시보드 → vwlahtguyggrhvslabax → Settings → API"
                )
            print(f"\n=== {table} ERROR ===\n{err[:300]}")
            continue
        if res.data:
            print(f"\n=== {table} ({len(res.data[0])} cols) ===")
            print(json.dumps(sorted(res.data[0].keys()), ensure_ascii=False))
        else:
            print(f"\n=== {table}: empty ===")

    kinds = [
        "OBLIGATION",
        "PROHIBITION",
        "PENALTY",
        "CONDITION",
        "EXCEPTION",
        "DELEGATION",
        "DEFINITION",
        "EXEMPTION",
    ]
    print("\n=== rule_kind counts ===")
    for kind in kinds:
        c = sb.table("master_rule_v2").select("id", count="exact").eq("rule_kind", kind).limit(0).execute()
        print(f"  {kind}: {c.count}")

    obl = (
        sb.table("master_rule_v2")
        .select("*")
        .eq("rule_kind", "OBLIGATION")
        .neq("status", "DEPRECATED")
        .limit(3)
        .execute()
        .data
        or []
    )
    print(f"\n=== adapt sample ({len(obl)} rows) ===")
    v1_list = adapt_v2_batch(obl, sector_hint="BUILDING")
    for v2, v1 in zip(obl, v1_list):
        print(
            f"  {v2.get('rule_code') or v2.get('id')}: "
            f"{v1.get('law_name')} {v1.get('law_article')} | {v1.get('obligation_type')} | active={v1.get('is_active')}"
        )

    draft = (
        sb.table("master_rule_v2")
        .select("*")
        .eq("rule_kind", "OBLIGATION")
        .eq("status", "DRAFT")
        .limit(1)
        .execute()
        .data
    )
    if draft:
        one = adapt_v2_to_v1(draft[0])
        print(f"\nDRAFT row is_active => {one.get('is_active') if one else None}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
