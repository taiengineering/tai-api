#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
master_building_legal_rules 에 등장하는 law_name 중 law_master 에 없는 법령을
law.go.kr API로 수집하여 DB에 적재합니다.

실행:
  railway run python3 scripts/collect_missing_laws.py
  export $(cat .env | grep -v '#' | xargs) && python3 scripts/collect_missing_laws.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore

_ROOT = Path(__file__).resolve().parent.parent
if load_dotenv:
    load_dotenv(_ROOT / ".env")
    _admin = _ROOT.parent / "tai-admin" / "admin" / "full-version" / ".env"
    if _admin.is_file():
        load_dotenv(_admin)

if not os.environ.get("SUPABASE_KEY") and os.environ.get("SUPABASE_ANON_KEY"):
    os.environ["SUPABASE_KEY"] = os.environ["SUPABASE_ANON_KEY"]

sys.path.insert(0, str(_ROOT))

from db.database import get_supabase  # noqa: E402
from routers.law_collector import (  # noqa: E402
    fetch_law_content,
    fetch_law_list,
    parse_law_content_xml,
    parse_law_list_xml,
    save_law_to_db,
)


def _collect_one(law_name: str, supabase) -> dict:
    list_result = fetch_law_list(query=law_name, display=5)
    laws = parse_law_list_xml(list_result["xml"])
    if not laws:
        raise RuntimeError(f"법령을 찾을 수 없습니다: {law_name}")
    matched = next((l for l in laws if law_name in l["law_name"]), laws[0])
    content_result = fetch_law_content(matched["law_mst_no"])
    parsed = parse_law_content_xml(content_result["xml"])
    law_info = {
        **parsed["info"],
        "law_mst_no": matched["law_mst_no"],
        "law_name_short": matched.get("law_name_short", ""),
        "revision_type": matched.get("revision_type", ""),
    }
    return save_law_to_db(law_info, content_result["xml"], parsed["articles"], supabase)


def main() -> None:
    if not os.environ.get("LAW_API_OC"):
        print("[ERROR] LAW_API_OC 환경변수 필요 (국가법령정보 OC)")
        sys.exit(1)

    supabase = get_supabase()

    rules_res = (
        supabase.table("master_building_legal_rules")
        .select("law_name")
        .eq("is_active", True)
        .execute()
    )
    if not rules_res.data:
        print("활성 룰 없음")
        return

    law_names = sorted({r["law_name"] for r in rules_res.data if r.get("law_name")})
    if not law_names:
        print("law_name 없음")
        return

    masters_res = supabase.table("law_master").select("law_name").execute()
    master_set = {m["law_name"] for m in (masters_res.data or []) if m.get("law_name")}

    missing = [n for n in law_names if n not in master_set]
    print(f"전체 룰 법령명 고유: {len(law_names)}개, law_master 미존재: {len(missing)}개")

    if not missing:
        print("수집할 미매핑 없음")
        return

    ok, fail = 0, 0
    for name in missing:
        try:
            r = _collect_one(name, supabase)
            print(f"✅ 수집완료: {name} (조문 {r.get('article_count', 0)}개)")
            ok += 1
            time.sleep(0.5)
        except Exception as e:
            print(f"❌ 실패: {name} — {e}")
            fail += 1
            time.sleep(0.3)

    print(f"\n완료: 성공 {ok}, 실패 {fail}")


if __name__ == "__main__":
    main()
