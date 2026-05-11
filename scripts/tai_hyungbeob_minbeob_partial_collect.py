#!/usr/bin/env python3
"""
형법·민법 부분 적재 보강 — law_article_citation 의 cited_article_no 빈도 상위 N조만 UPSERT.

Track B PM (2026-05-10): 전체 459/1307조 대신 인용 분포 기준 형법 18 · 민법 31조 (합 49).
collect_v2.save_law_to_db(..., partial_merge=True) — 나머지 조문을 DELETED로 만들지 않음.

실행:
  cd tai-api && railway run python3 scripts/tai_hyungbeob_minbeob_partial_collect.py
  python3 scripts/tai_hyungbeob_minbeob_partial_collect.py --dry-run
  python3 scripts/tai_hyungbeob_minbeob_partial_collect.py --hyung-only
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from typing import Any

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
_SCRIPTS_DIR = os.path.join(_ROOT, "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from db.database import get_supabase
from routers.law_collector import (
    fetch_law_content,
    parse_law_content_xml,
    pick_match_law_from_list,
    fetch_law_list,
    parse_law_list_xml,
)
from collect_v2 import save_law_to_db

# Tier 1 검색명 → MST (법제처 목록과 동일하게 검색)
SPEC = (
    ("형법", "284025", "LAW", 18),
    ("민법", "284415", "LAW", 31),
)


def _parse_main_article_no(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _fetch_citation_article_nos(
    supabase: Any, law_id: str, law_name: str
) -> list[int]:
    """cited_law_id 우선, 없으면 cited_law_name 으로 인용 행에서 조번호 수집."""
    nums: list[int] = []
    chunk = 800
    offset = 0
    for use_name in (False, True):
        while True:
            q = supabase.table("law_article_citation").select("cited_article_no")
            if use_name:
                q = q.eq("cited_law_name", law_name)
            else:
                q = q.eq("cited_law_id", law_id)
            res = q.range(offset, offset + chunk - 1).execute()
            rows = res.data or []
            if not rows:
                break
            for row in rows:
                n = _parse_main_article_no(row.get("cited_article_no"))
                if n is not None:
                    nums.append(n)
            if len(rows) < chunk:
                break
            offset += chunk
        if nums or use_name:
            break
        offset = 0
    return nums


def top_n_article_numbers(nums: list[int], n: int) -> list[int]:
    ctr = Counter(nums)
    return [no for no, _ in ctr.most_common(n)]


def filter_parsed_articles(articles: list[dict], allowed: set[int]) -> list[dict]:
    out = []
    for a in articles:
        main = _parse_main_article_no(a.get("article_no"))
        if main is not None and main in allowed:
            out.append(a)
    return out


def minimal_target(law_name: str, law_type_code: str) -> dict:
    return {"law_name": law_name, "law_type_code": law_type_code}


def collect_one(
    supabase: Any,
    law_query: str,
    expected_mst: str,
    law_type_code: str,
    top_n: int,
    *,
    dry_run: bool,
) -> dict:
    mr = (
        supabase.table("law_master")
        .select("id, law_name, law_mst_no")
        .eq("law_mst_no", expected_mst)
        .execute()
    )
    if not mr.data:
        return {"law_query": law_query, "ok": False, "error": "law_master 없음 MST=" + expected_mst}
    row = mr.data[0]
    law_id = row["id"]
    law_name = row["law_name"] or law_query

    cited_nums = _fetch_citation_article_nos(supabase, law_id, law_name)
    top_articles = top_n_article_numbers(cited_nums, top_n)
    allowed = set(top_articles)

    content = fetch_law_content(expected_mst)
    if not content.get("ok"):
        return {
            "law_query": law_query,
            "ok": False,
            "error": f"lawService HTTP {content.get('status')}",
        }
    parsed = parse_law_content_xml(content["xml"])
    law_info = {
        **parsed["info"],
        "law_mst_no": expected_mst,
        "law_name_short": "",
        "revision_type": "",
    }
    filtered = filter_parsed_articles(parsed["articles"], allowed)

    list_result = fetch_law_list(query=law_query, display=15)
    laws = parse_law_list_xml(list_result["xml"]) if list_result.get("ok") else []
    matched = pick_match_law_from_list(laws, law_query) if laws else {
        "law_mst_no": expected_mst,
        "law_api_id": law_info.get("law_api_id", ""),
        "law_name": law_name,
        "law_name_short": "",
        "revision_type": "",
    }

    result_base = {
        "law_query": law_query,
        "ok": True,
        "law_id": law_id,
        "citation_rows_used": len(cited_nums),
        "distinct_cited_articles": len(set(cited_nums)),
        "target_top_n": top_n,
        "selected_article_nos": sorted(allowed),
        "parsed_total": len(parsed["articles"]),
        "filtered_count": len(filtered),
    }

    if dry_run:
        return result_base

    target = minimal_target(law_name, law_type_code)
    save_result = save_law_to_db(
        target,
        law_info,
        matched,
        content["xml"],
        filtered,
        supabase,
        partial_merge=True,
    )
    result_base.update(save_result)
    return result_base


def main() -> int:
    ap = argparse.ArgumentParser(description="형법·민법 인용 Top-N 부분 적재")
    ap.add_argument("--dry-run", action="store_true", help="DB 저장 없이 조번호·건수만 출력")
    ap.add_argument("--hyung-only", action="store_true", help="형법만")
    ap.add_argument("--min-only", action="store_true", help="민법만")
    args = ap.parse_args()

    spec = list(SPEC)
    if args.hyung_only:
        spec = [s for s in spec if s[0] == "형법"]
    if args.min_only:
        spec = [s for s in spec if s[0] == "민법"]
    if args.hyung_only and args.min_only:
        print("--hyung-only 와 --min-only 동시 사용 불가")
        return 2

    supabase = get_supabase()
    for law_query, mst, ltc, n in spec:
        print(f"\n=== {law_query} (MST {mst}, Top {n}) ===", flush=True)
        r = collect_one(supabase, law_query, mst, ltc, n, dry_run=args.dry_run)
        print(r, flush=True)
        if not r.get("ok"):
            return 1
    print("\n[DONE]", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
