#!/usr/bin/env python3
"""
TAI 추가 수집 Tier 1 — §5.2 단건 적재 (본법 MST 검색·저장).

명세: Tier 1 본법 14건. 현재 구현은 검색 첫 매칭 법령 1건을 law_master 등에 UPSERT.
시행령·시행규칙 추가는 검색어(예: '○○법 시행령') 별도 배치가 필요할 수 있음.
"""
from __future__ import annotations

import os
import sys
import time

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from db.database import get_supabase
from routers.law_collector import (
    fetch_law_list,
    fetch_law_content,
    parse_law_list_xml,
    parse_law_content_xml,
    pick_match_law_from_list,
    save_law_to_db,
    delete_law_version_cascade_for_recollect,
)

# PM 명세 Tier 1 — citation Top 12 + ORPHAN 2
TIER1_LAWS = [
    "전자정부법",
    "형법",
    "고등교육법",
    "민법",
    "자동차관리법",
    "국민건강보험법",
    "개인정보 보호법",
    "산업표준화법",
    "국가표준기본법",
    "국민기초생활 보장법",
    "도로법",
    "초ㆍ중등교육법",
    "도로교통법",
    "방송통신발전 기본법",
]


def remove_empty_version_if_any(supabase, law_mst_no: str) -> bool:
    """이전 실패로 조문 0건인 law_version만 삭제해 재삽입 가능하게 함."""
    r = supabase.table("law_master").select("id").eq("law_mst_no", law_mst_no).execute()
    if not r.data:
        return False
    law_id = r.data[0]["id"]
    vr = (
        supabase.table("law_version")
        .select("id")
        .eq("law_id", law_id)
        .eq("law_mst_no", law_mst_no)
        .execute()
    )
    if not vr.data:
        return False
    vid = vr.data[0]["id"]
    cnt = (
        supabase.table("law_article")
        .select("id", count="exact", head=True)
        .eq("law_version_id", vid)
        .execute()
        .count
        or 0
    )
    if cnt == 0:
        delete_law_version_cascade_for_recollect(supabase, vid)
        return True
    return False


def collect_one(
    law_query: str, supabase, *, force_empty_fix: bool = False
) -> dict:
    list_result = fetch_law_list(query=law_query, display=15)
    if not list_result.get("ok"):
        return {
            "query": law_query,
            "ok": False,
            "error": f"lawSearch HTTP {list_result.get('status')} source={list_result.get('source')}",
        }
    laws = parse_law_list_xml(list_result["xml"])
    if not laws:
        return {"query": law_query, "ok": False, "error": "검색 결과 없음"}

    matched = pick_match_law_from_list(laws, law_query)
    if force_empty_fix:
        remove_empty_version_if_any(supabase, matched["law_mst_no"])
    content_result = fetch_law_content(matched["law_mst_no"])
    if not content_result.get("ok"):
        return {
            "query": law_query,
            "ok": False,
            "error": f"lawService HTTP {content_result.get('status')}",
        }

    parsed = parse_law_content_xml(content_result["xml"])
    law_info = {
        **parsed["info"],
        "law_mst_no": matched["law_mst_no"],
        "law_name_short": matched.get("law_name_short", ""),
        "revision_type": matched.get("revision_type", ""),
    }
    save_result = save_law_to_db(
        law_info, content_result["xml"], parsed["articles"], supabase
    )
    return {
        "query": law_query,
        "ok": True,
        "matched_name": matched["law_name"],
        "law_mst_no": matched["law_mst_no"],
        "article_count": save_result.get("article_count"),
        "api_source": list_result.get("source"),
    }


def main() -> int:
    supabase = get_supabase()
    force_empty_fix = "--force" in sys.argv
    ok_n = 0
    print(
        f"[Tier1] {len(TIER1_LAWS)}건 수집 시작 force_empty_fix={force_empty_fix}\n",
        flush=True,
    )
    for i, q in enumerate(TIER1_LAWS, 1):
        print(f"[{i}/{len(TIER1_LAWS)}] {q!r} ...", flush=True)
        try:
            r = collect_one(q, supabase, force_empty_fix=force_empty_fix)
        except Exception as e:
            r = {"query": q, "ok": False, "error": f"{type(e).__name__}: {e}"}
        print(f"    → {r}", flush=True)
        if r.get("ok"):
            ok_n += 1
        time.sleep(0.75)
    print(f"\n[DONE] 성공 {ok_n}/{len(TIER1_LAWS)}", flush=True)
    return 0 if ok_n == len(TIER1_LAWS) else 1


if __name__ == "__main__":
    sys.exit(main())
