#!/usr/bin/env python3
"""
Pilot 3: 가스·전기·소방 6법령 force 재수집 + FK 재연결.

사용법:
    cd ~/dev/tai-api
    git pull origin main
    set -a; source .env; set +a
    python3 scripts/pilot3_recollect.py 2>&1 | tee /tmp/pilot3_output.log
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from services.time import now_kst

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

# Pilot 3 대상 6법령 (우선순위: 작은 법령 → 큰 법령)
TARGETS = [
    "화재의 예방 및 안전관리에 관한 법률",
    "위험물안전관리법 시행규칙",
    "전기안전관리법 시행규칙",
    "소방시설 설치 및 관리에 관한 법률",
    "고압가스 안전관리법 시행규칙",
    "화학물질관리법 시행규칙",
]


def _match_law_name(laws: list[dict], law_name: str) -> dict | None:
    """정확 매칭 우선, 실패 시 부분 매칭."""
    exact = next((l for l in laws if (l.get("law_name") or "").strip() == law_name), None)
    if exact:
        return exact
    if "시행령" in law_name or "시행규칙" in law_name:
        return None
    partial = next((l for l in laws if law_name in (l.get("law_name") or "")), None)
    return partial or (laws[0] if laws else None)


def _check_emergency_stop(supabase) -> tuple[bool, str]:
    """긴급 중단: law_revision_board 최근 1시간만 체크."""
    try:
        since = (now_kst() - timedelta(hours=1)).isoformat()
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
        return {"law_name": law_name, "success": False, "error": f"긴급 중단: {reason}"}

    res = fetch_law_list(query=law_name, display=15)
    if not res["ok"]:
        return {"law_name": law_name, "success": False, "error": f"검색 API 실패: HTTP {res['status']}"}

    laws = parse_law_list_xml(res["xml"])
    matched = _match_law_name(laws, law_name)
    if not matched:
        return {
            "law_name": law_name,
            "success": False,
            "error": f"검색 결과에서 정확 매칭 실패. 후보: {[l['law_name'] for l in laws[:5]]}",
        }

    print(
        f"  ✅ 매칭: {matched['law_name']} | MST={matched['law_mst_no']} | 공포={matched['announcement_date']}"
    )

    law_check = (
        supabase.table("law_master")
        .select("id,law_name")
        .eq("law_name", matched["law_name"])
        .limit(1)
        .execute()
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
                supabase.table("law_article")
                .select("id", count="exact")
                .eq("law_version_id", old_vid)
                .execute()
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
        return {"law_name": law_name, "success": False, "error": f"본문 API 실패: HTTP {content['status']}"}

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
        print(f"  💾 저장 완료: article_count={result['article_count']}, new_version={result['is_new_version']}")
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
    """pilot2_recollect.py 의 reconnect_one 재사용 (article_no fallback 포함)."""
    from scripts.pilot2_recollect import reconnect_one as pilot2_reconnect

    return pilot2_reconnect(law_name, supabase)


def main() -> int:
    supabase = get_supabase()
    results: list[dict] = []

    print("\n" + "🚀" * 35)
    print("Pilot 3: 가스·전기·소방 6법령 재수집 시작")
    print("🚀" * 35)

    for law_name in TARGETS:
        result = recollect_one(law_name, supabase)
        if result.get("success"):
            try:
                rec = reconnect_one(result["matched_name"], supabase)
                result.update(rec)
            except Exception as e:
                result["reconnect_success"] = False
                result["reconnect_error"] = str(e)
        results.append(result)

    print("\n" + "=" * 70)
    print("📊 Pilot 3 완료 — 결과 요약")
    print("=" * 70)
    for r in results:
        if r.get("success"):
            print(
                f"✅ {r['law_name']}: article_count={r.get('article_count')}, "
                f"key_map={r.get('key_map_updated', '-')}, drafts={r.get('drafts_fixed', '-')}"
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
