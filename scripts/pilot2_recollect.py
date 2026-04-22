#!/usr/bin/env python3
"""
Pilot 2: 건설업 3법령 force 재수집 + FK 재연결.

사용법:
    cd ~/dev/tai-api
    set -a; source .env; set +a
    python3 scripts/pilot2_recollect.py
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

# tai-api 루트를 path 에 추가
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from db.database import get_supabase
from routers.law_collector import (
    delete_law_version_cascade_for_recollect,
    fetch_law_content,
    fetch_law_list,
    parse_law_content_xml,
    parse_law_list_xml,
    save_law_to_db,
    snapshot_article_key_map_for_version,
)

TARGETS = [
    "건축법",
    "건축법 시행령",
    "건설기술 진흥법",
]


def _match_law_name(laws: list[dict], law_name: str) -> dict | None:
    exact = next((l for l in laws if (l.get("law_name") or "").strip() == law_name), None)
    if exact:
        return exact
    partial = next(
        (
            l for l in laws
            if (
                law_name in (l.get("law_name") or "")
                and "시행규칙" not in (l.get("law_name") or "")
                and "시행령" not in (l.get("law_name") or "")
            ) or (l.get("law_name") or "").strip() == law_name
        ),
        None,
    )
    if partial:
        return partial
    return laws[0] if laws else None


def _check_emergency_stop(supabase) -> tuple[bool, str]:
    """긴급 중단 기준: 최근 1시간 revision board 삽입만 체크."""
    try:
        since = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        recent = (
            supabase.table("law_revision_board")
            .select("id")
            .gte("created_at", since)
            .limit(1)
            .execute()
        )
        if recent.data:
            return True, "law_revision_board 최근 1시간 데이터 감지"
    except Exception as e:
        print(f"  ⚠️ 긴급중단 점검 스킵: {e}")

    return False, ""


def recollect_one(law_name: str, supabase) -> dict:
    print(f"\n{'=' * 70}")
    print(f"🎯 {law_name}")
    print(f"{'=' * 70}")

    should_stop, reason = _check_emergency_stop(supabase)
    if should_stop:
        return {
            "law_name": law_name,
            "success": False,
            "error": f"긴급 중단: {reason}",
        }

    res = fetch_law_list(query=law_name, display=10)
    if not res["ok"]:
        return {
            "law_name": law_name,
            "success": False,
            "error": f"검색 API 실패: HTTP {res['status']}",
        }

    laws = parse_law_list_xml(res["xml"])
    matched = _match_law_name(laws, law_name)
    if not matched:
        return {"law_name": law_name, "success": False, "error": "검색 결과 없음"}

    print(
        f"  ✅ 매칭: {matched['law_name']} | MST={matched['law_mst_no']} | 공포={matched['announcement_date']}"
    )

    law_check = (
        supabase.table("law_master").select("id,law_name").eq("law_name", matched["law_name"]).limit(1).execute()
    )
    if law_check.data:
        existing_law_id = law_check.data[0]["id"]
        ev = (
            supabase.table("law_version")
            .select("id")
            .eq("law_id", existing_law_id)
            .eq("law_mst_no", matched["law_mst_no"])
            .execute()
        )
        if ev.data:
            old_vid = ev.data[0]["id"]
            art_before = (
                supabase.table("law_article").select("id", count="exact").eq("law_version_id", old_vid).execute()
            )
            print(f"  🗑  기존 version={old_vid}, article {art_before.count}개 삭제 예정")
            snapshot_article_key_map_for_version(supabase, old_vid)
            try:
                delete_law_version_cascade_for_recollect(supabase, old_vid)
                print("  ✅ cascade 삭제 완료")
            except Exception as e:
                return {"law_name": law_name, "success": False, "error": f"cascade 삭제 실패: {e}"}
        else:
            print("  ℹ️  같은 MST version 없음 — 새로 삽입만")
    else:
        print("  ℹ️  law_master 없음 — 새로 생성")

    content = fetch_law_content(matched["law_mst_no"])
    if not content["ok"]:
        return {
            "law_name": law_name,
            "success": False,
            "error": f"본문 API 실패: HTTP {content['status']}",
        }

    parsed = parse_law_content_xml(content["xml"])
    print(f"  📄 XML {len(content['xml'])}자 → 조문 {len(parsed['articles'])}개")

    law_info = {
        **parsed["info"],
        "law_mst_no": matched["law_mst_no"],
        "law_name_short": matched.get("law_name_short", ""),
        "revision_type": matched.get("revision_type", ""),
    }
    try:
        result = save_law_to_db(law_info, content["xml"], parsed["articles"], supabase)
        print(
            f"  💾 저장 완료: article_count={result['article_count']}, new_version={result['is_new_version']}"
        )
        return {
            "law_name": law_name,
            "matched_name": matched["law_name"],
            "success": True,
            "mst_no": matched["law_mst_no"],
            "article_count": result["article_count"],
            "version_id": result["version_id"],
        }
    except Exception as e:
        return {"law_name": law_name, "success": False, "error": f"DB 저장 실패: {e}"}


def reconnect_one(law_name: str, supabase) -> dict:
    print(f"\n  🔗 FK 재연결: {law_name}")
    law_row = supabase.table("law_master").select("id").eq("law_name", law_name).limit(1).execute()
    if not law_row.data:
        return {"law_name": law_name, "reconnect_success": False, "error": "law_master 없음"}

    law_id = law_row.data[0]["id"]
    current_versions = (
        supabase.table("law_version").select("id").eq("law_id", law_id).eq("is_current", True).execute().data or []
    )
    current_version_ids = [r["id"] for r in current_versions]
    if not current_version_ids:
        return {"law_name": law_name, "reconnect_success": False, "error": "current version 없음"}

    new_articles = (
        supabase.table("law_article")
        .select("id,article_internal_key,article_no,article_sub_no,law_version_id")
        .in_("law_version_id", current_version_ids)
        .execute()
        .data
        or []
    )
    key_to_new_id = {a["article_internal_key"]: a["id"] for a in new_articles if a.get("article_internal_key")}
    by_no: dict[tuple[int, int | None], list[str]] = {}
    for a in new_articles:
        art_no = a.get("article_no")
        if art_no is None:
            continue
        sub_no = a.get("article_sub_no")
        k = (int(art_no), int(sub_no) if sub_no is not None else None)
        by_no.setdefault(k, []).append(a["id"])
    key_pattern = re.compile(r"^제(\d+)조(?:의(\d+))?$")

    updated = 0
    unmatched_keys: list[str] = []
    unmatched_rows: list[dict] = []
    map_rows = (
        supabase.table("law_article_key_map").select("id,article_internal_key").is_("new_article_id", "null").execute().data
        or []
    )
    for m in map_rows:
        key = (m.get("article_internal_key") or "").strip()
        if key in key_to_new_id:
            supabase.table("law_article_key_map").update({"new_article_id": key_to_new_id[key]}).eq(
                "id", m["id"]
            ).execute()
            updated += 1
        else:
            unmatched_rows.append(m)
            unmatched_keys.append(key)

    fallback_updated = 0
    for row in unmatched_rows:
        key = (row.get("article_internal_key") or "").strip()
        m = key_pattern.match(key)
        if not m:
            continue
        art_no = int(m.group(1))
        sub_no = int(m.group(2)) if m.group(2) else None
        candidates = by_no.get((art_no, sub_no)) or []
        if len(candidates) != 1:
            continue
        supabase.table("law_article_key_map").update({"new_article_id": candidates[0]}).eq("id", row["id"]).execute()
        updated += 1
        fallback_updated += 1
        if key in unmatched_keys:
            unmatched_keys.remove(key)

    print(f"    key_map 업데이트: {updated}건 matched")
    if fallback_updated:
        print(f"    fallback(article_no) 매칭: {fallback_updated}건")
    if unmatched_keys[:5]:
        print(f"    unmatched keys (샘플): {unmatched_keys[:5]}")

    drafts_fixed = 0
    try:
        mappings = (
            supabase.table("law_article_key_map")
            .select("old_article_id,new_article_id")
            .not_.is_("new_article_id", "null")
            .execute()
            .data
            or []
        )
        for m in mappings:
            r = (
                supabase.table("law_rule_drafts")
                .update({"article_id": m["new_article_id"]})
                .eq("article_id", m["old_article_id"])
                .execute()
            )
            drafts_fixed += len(r.data or [])
    except Exception as e:
        print(f"    drafts 재연결 에러: {e}")

    print(f"    drafts.article_id 재연결: {drafts_fixed}건")

    return {
        "law_name": law_name,
        "reconnect_success": True,
        "key_map_updated": updated,
        "drafts_fixed": drafts_fixed,
        "unmatched_count": len(unmatched_keys),
    }


def main() -> int:
    supabase = get_supabase()
    results: list[dict] = []

    print("\n" + "🚀" * 35)
    print("Pilot 2: 건설업 3법령 재수집 시작")
    print("🚀" * 35)

    for law_name in TARGETS:
        result = recollect_one(law_name, supabase)
        if result.get("success"):
            rec = reconnect_one(law_name, supabase)
            result.update(rec)
        results.append(result)

    print("\n" + "=" * 70)
    print("📊 Pilot 2 완료 — 결과 요약")
    print("=" * 70)
    for r in results:
        if r.get("success"):
            print(
                f"✅ {r['law_name']}: article_count={r.get('article_count')}, "
                f"key_map={r.get('key_map_updated')}, drafts={r.get('drafts_fixed')}"
            )
        else:
            print(f"❌ {r['law_name']}: {r.get('error')}")

    success_count = sum(1 for r in results if r.get("success"))
    print(f"\n총 {success_count}/{len(TARGETS)} 성공")

    print("\n[JSON]")
    print(json.dumps(results, ensure_ascii=False, indent=2, default=str))

    return 0 if success_count == len(TARGETS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
