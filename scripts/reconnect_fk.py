#!/usr/bin/env python3
"""
재수집 후 law_article_key_map 을 이용해 article_id FK 복구.

사용법 (tai-api 루트, SUPABASE_URL / SUPABASE_KEY 설정):
  python3 scripts/reconnect_fk.py --law-name "산업안전보건법"

동작:
  1) law_master 에서 law_id 조회
  2) 현행 law_version id 조회
  3) map 행별로 new_article_id 가 비어 있으면, 동일 article_internal_key 의
     현행 버전 law_article id 를 찾아 채움
  4) law_rule_drafts.article_id, inspection_set_items.law_article_id 업데이트
"""
from __future__ import annotations

import argparse
import os
import sys

# tai-api 루트를 path 에 추가
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from db.database import get_supabase  # noqa: E402


def reconnect_for_law(law_name: str) -> dict:
    sb = get_supabase()
    lm = sb.table("law_master").select("id").eq("law_name", law_name).limit(1).execute().data
    if not lm:
        return {"error": f"law_master not found: {law_name}"}
    law_id = lm[0]["id"]
    lv = sb.table("law_version").select("id").eq("law_id", law_id).eq("is_current", True).limit(1).execute().data
    if not lv:
        return {"error": "no current law_version"}
    new_vid = lv[0]["id"]

    maps = sb.table("law_article_key_map").select("*").is_("new_article_id", "null").execute().data or []
    arts = sb.table("law_article").select("id,article_internal_key").eq("law_version_id", new_vid).execute().data or []
    by_key = {a["article_internal_key"]: a["id"] for a in arts if a.get("article_internal_key")}

    updated_drafts = 0
    updated_items = 0
    for row in maps:
        key = row.get("article_internal_key") or ""
        old_id = row.get("old_article_id")
        new_id = by_key.get(key)
        if not new_id or not old_id:
            continue
        sb.table("law_article_key_map").update({"new_article_id": new_id}).eq("id", row["id"]).execute()
        d = sb.table("law_rule_drafts").update({"article_id": new_id}).eq("article_id", old_id).execute()
        updated_drafts += len(d.data or [])
        i = sb.table("inspection_set_items").update({"law_article_id": new_id}).eq("law_article_id", old_id).execute()
        updated_items += len(i.data or [])

    return {
        "law_name": law_name,
        "new_version_id": new_vid,
        "map_rows": len(maps),
        "drafts_updated": updated_drafts,
        "inspection_items_updated": updated_items,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--law-name", required=True)
    args = ap.parse_args()
    r = reconnect_for_law(args.law_name)
    print(r)
    return 0 if "error" not in r else 1


if __name__ == "__main__":
    raise SystemExit(main())
