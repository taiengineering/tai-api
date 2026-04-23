#!/usr/bin/env python3
"""
NFPC/NFTC 재파싱 스크립트 (API 호출 없음)

목적:
  - 기존 law_content_raw.raw_xml 활용
  - 파서 v2.0으로 NFPC/NFTC 재파싱
  - 내부 키 체계 적용 (nfpc-art-*, nftc-sec-*)
  - article 테이블 재구성 (기존 UUID는 가능한 유지)

사용법:
    cd ~/dev/tai-api
    set -a; source .env; set +a
    
    # 단일 법령 테스트
    python3 scripts/reparse_admrul.py test "NFTC 102"
    
    # NFPC 전체 재파싱
    python3 scripts/reparse_admrul.py nfpc
    
    # NFTC 전체 재파싱  
    python3 scripts/reparse_admrul.py nftc
    
    # 둘 다
    python3 scripts/reparse_admrul.py all
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from db.database import get_supabase
from routers.law_collector_admrul import parse_admrul_content_xml


def get_admrul_targets(supabase, filter_type: str = "all", name_query: str = None):
    """
    admrul 대상 법령 조회 (NFPC, NFTC 등).
    law_type_code가 STANDARD 또는 NOTICE인 것.
    """
    query = supabase.table("law_master") \
        .select("id, law_name, law_type_code, current_version_id, law_api_id") \
        .in_("law_type_code", ["STANDARD", "NOTICE"]) \
        .eq("is_active", True)
    
    result = query.order("law_name").execute()
    targets = result.data or []
    
    # 필터링
    if filter_type == "nfpc":
        targets = [t for t in targets if "NFPC" in (t.get("law_name") or "")]
    elif filter_type == "nftc":
        targets = [t for t in targets if "NFTC" in (t.get("law_name") or "")]
    elif filter_type == "name" and name_query:
        targets = [t for t in targets if name_query in (t.get("law_name") or "")]
    
    return targets


def reparse_one_law(target: dict, supabase) -> dict:
    """1개 법령 재파싱."""
    law_id = target["id"]
    law_name = target["law_name"]
    version_id = target["current_version_id"]
    
    print(f"\n{'─' * 70}")
    print(f"🔄 {law_name}")
    print(f"   law_id: {law_id}")
    
    result = {
        "law_id": law_id,
        "law_name": law_name,
        "status": "FAILED",
        "error": None,
    }
    
    try:
        # 1) raw_xml 조회
        raw_result = supabase.table("law_content_raw") \
            .select("raw_xml") \
            .eq("law_version_id", version_id) \
            .limit(1) \
            .execute()
        
        if not raw_result.data:
            raise RuntimeError("law_content_raw 없음")
        
        raw_xml = raw_result.data[0]["raw_xml"]
        print(f"   ▶ XML: {len(raw_xml):,} bytes")
        
        # 2) 파서 v2.0으로 재파싱
        parsed = parse_admrul_content_xml(raw_xml)
        parse_mode = parsed.get("info", {}).get("_parse_mode", "UNKNOWN")
        articles = parsed["articles"]
        
        print(f"   ▶ 파서: {parse_mode} | 조문 {len(articles)}개 추출")
        
        if not articles:
            raise RuntimeError("파싱 결과 0개")
        
        # 3) 기존 article 조회 (UUID 유지 시도용)
        existing = supabase.table("law_article") \
            .select("id, article_internal_key") \
            .eq("law_id", law_id) \
            .execute()
        
        existing_by_key = {a["article_internal_key"]: a["id"] for a in (existing.data or [])}
        print(f"   ▶ 기존 article: {len(existing_by_key)}개")
        
        # 4) UPSERT 기반으로 재구성
        new_keys = set()
        preserved = 0
        inserted = 0
        
        for art in articles:
            ikey = art["article_internal_key"]
            new_keys.add(ikey)
            
            payload = {
                "law_id":                law_id,
                "law_version_id":        version_id,
                "article_internal_key":  ikey,
                "article_no":            art["article_no"],
                "article_sub_no":        art["article_sub_no"],
                "article_no_sort":       f"{str(art['article_no'] or 0).zfill(4)}-{str(art['article_sub_no'] or 0).zfill(3)}",
                "article_type":          art["article_type"],
                "article_title":         art["article_title"],
                "article_text":          art["article_text"],
                "is_changed":            art["is_changed"],
                "enforcement_date":      None,
                "article_status_code":   "ACTIVE",
                "updated_at":            datetime.now().isoformat(),
            }
            
            if ikey in existing_by_key:
                # UPDATE (UUID 유지)
                supabase.table("law_article") \
                    .update(payload) \
                    .eq("id", existing_by_key[ikey]) \
                    .execute()
                preserved += 1
            else:
                # INSERT (신규 조문)
                supabase.table("law_article").insert(payload).execute()
                inserted += 1
        
        # 5) 사라진 조문은 soft delete (내용 없었거나 키 체계 달라짐)
        deleted = 0
        for old_key, old_id in existing_by_key.items():
            if old_key not in new_keys:
                supabase.table("law_article").update({
                    "article_status_code": "DELETED",
                    "updated_at": datetime.now().isoformat(),
                }).eq("id", old_id).execute()
                deleted += 1
        
        print(f"   ✅ 완료: UUID유지 {preserved}, 신규 {inserted}, 삭제 {deleted}")
        
        result["status"] = "SUCCESS"
        result["parse_mode"] = parse_mode
        result["article_count"] = len(articles)
        result["preserved"] = preserved
        result["inserted"] = inserted
        result["deleted"] = deleted
    
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)[:200]}"
        result["error"] = error_msg
        print(f"   ❌ 실패: {error_msg}")
    
    return result


def cmd_test(name_query: str) -> int:
    """단일 법령 재파싱 테스트."""
    supabase = get_supabase()
    
    print(f"\n{'=' * 70}")
    print(f"🧪 재파싱 테스트: {name_query}")
    print(f"{'=' * 70}")
    
    targets = get_admrul_targets(supabase, filter_type="name", name_query=name_query)
    
    if not targets:
        print(f"❌ 대상 없음: {name_query}")
        return 1
    
    if len(targets) > 1:
        print(f"⚠️ {len(targets)}개 후보. 첫 번째만:")
        for t in targets[:5]:
            print(f"   - {t['law_name']}")
    
    result = reparse_one_law(targets[0], supabase)
    
    print(f"\n{'=' * 70}")
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result["status"] == "SUCCESS" else 1


def cmd_batch(filter_type: str) -> int:
    """대량 재파싱."""
    supabase = get_supabase()
    
    print(f"\n{'=' * 70}")
    print(f"🚀 {filter_type.upper()} 전체 재파싱")
    print(f"{'=' * 70}")
    
    targets = get_admrul_targets(supabase, filter_type=filter_type)
    total = len(targets)
    
    if total == 0:
        print(f"❌ {filter_type} 대상 없음")
        return 1
    
    print(f"총 {total}개 법령 재파싱 시작 (API 호출 0)\n")
    
    success = 0
    fail = 0
    total_articles = 0
    total_preserved = 0
    total_inserted = 0
    total_deleted = 0
    start = time.time()
    
    for idx, target in enumerate(targets, 1):
        print(f"\n[{idx}/{total}]", end="")
        result = reparse_one_law(target, supabase)
        
        if result["status"] == "SUCCESS":
            success += 1
            total_articles += result.get("article_count", 0)
            total_preserved += result.get("preserved", 0)
            total_inserted += result.get("inserted", 0)
            total_deleted += result.get("deleted", 0)
        else:
            fail += 1
    
    elapsed = time.time() - start
    
    print(f"\n{'=' * 70}")
    print(f"🎉 {filter_type.upper()} 재파싱 완료 ({elapsed:.1f}초)")
    print(f"{'=' * 70}")
    print(f"  법령: 성공 {success} / 실패 {fail} / 전체 {total}")
    print(f"  article: {total_articles}개 처리")
    print(f"  UUID 유지: {total_preserved}개")
    print(f"  신규 INSERT: {total_inserted}개")
    print(f"  soft DELETE: {total_deleted}개")
    
    return 0 if fail == 0 else 1


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    
    command = sys.argv[1].lower()
    
    if command == "test":
        if len(sys.argv) < 3:
            print("❌ 사용법: python3 scripts/reparse_admrul.py test \"법령명\"")
            return 1
        return cmd_test(sys.argv[2])
    elif command == "nfpc":
        return cmd_batch("nfpc")
    elif command == "nftc":
        return cmd_batch("nftc")
    elif command == "all":
        rc1 = cmd_batch("nfpc")
        rc2 = cmd_batch("nftc")
        return 0 if rc1 == 0 and rc2 == 0 else 1
    else:
        print(f"❌ 알 수 없는 명령: {command}")
        print(__doc__)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
