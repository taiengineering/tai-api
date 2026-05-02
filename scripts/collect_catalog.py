#!/usr/bin/env python3
"""
법령 외부 카탈로그 수집 — SaaS 범위 누락 식별

목적:
  법제처 OPEN API를 키워드별로 listing → 우리가 모르는 법령 발견
  결과를 law_external_catalog에 적재 → 보유/타겟과 대조 → 진짜 누락 식별

배경:
  4/22 ATOMIC SWITCH 시 학교/의료/복지/선박 등 48개를 '서비스 범위 외'로 분리.
  SaaS 확장 후 다중 사업장 적용 (학교 안 공장, 공장 안 노인시설 등) 필요.
  사용자가 모르는 법령까지 발견하기 위해 외부 카탈로그 대조 필수.

설계:
  - 분야별 키워드로 광범위 검색 (law + admrul 양쪽)
  - 결과 distinct → 보유 182 + 통합 80 = 우리 시스템 인지 범위
  - 카탈로그 - 우리 인지 = 진짜 누락

사용법:
    cd ~/dev/tai-api
    set -a; source .env; set +a
    
    python3 scripts/collect_catalog.py collect    # 카탈로그 수집 (1회 약 30~60분)
    python3 scripts/collect_catalog.py classify   # 보유/타겟과 대조 분류
    python3 scripts/collect_catalog.py status     # 진행 통계
    python3 scripts/collect_catalog.py missing    # 진짜 누락 법령 출력
"""
from __future__ import annotations

import os
import sys
import time
from typing import Optional

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from db.database import get_supabase
from routers.law_collector import (
    fetch_law_list,
    parse_law_list_xml,
    law_type_name_to_code,
)
from routers.law_collector_admrul import (
    fetch_admrul_list,
    parse_admrul_list_xml,
)


# ═══════════════════════════════════════════════════════════
# 키워드 카테고리 — SaaS 범위 (건물/산업/건설 + 다중 부속시설)
# ═══════════════════════════════════════════════════════════

KEYWORDS_LAW = [
    # 건물 핵심
    "건축", "건축물", "다중이용", "시설물안전", "주차장", "승강기",
    "공동주택", "분양", "도시계획", "국토계획",
    "수도법", "하수도",
    # 산업안전·화학
    "산업안전", "산재", "공장", "공장설립", "화학물질", "위험물",
    "중대재해",
    # 건설
    "건설산업", "건설기술", "건설기계", "건설공사",
    # 환경
    "대기환경", "물환경", "폐기물", "소음", "진동", "악취", "토양환경",
    "환경기술",
    # 가스·전기
    "고압가스", "액화석유", "도시가스", "전기사업", "전기안전",
    "전기설비기술", "전기공사",
    # 소방·재난
    "소방시설", "화재예방", "위험물안전", "재난",
    # 노동·에너지
    "근로기준", "산업재해보상", "에너지이용", "탄소중립",
    # 부속시설 (사용자 통찰: 학교에 공장, 공장에 노인시설)
    "의료법", "의료기기", "공공보건의료",
    "노인복지", "사회복지", "장애인",
    "학교안전", "어린이놀이",
    # 통신
    "방송통신설비", "정보통신공사",
    # 석면·기타
    "석면",
]

KEYWORDS_ADMRUL = [
    # 안전·검사 기준
    "안전기준", "검사기준", "시험기준",
    "방호장치", "자율안전",
    # 산업안전 고시
    "안전보건교육", "작업환경측정", "안전보건관리비",
    "안전보건대장", "물질안전보건자료",
    "노출기준",
    # 가스 통합고시
    "가스안전관리기준",
    "안전관리기준통합고시",
    # 소방 NFPC/NFTC
    "NFPC", "NFTC",
    "화재안전성능기준", "화재안전기술기준",
    # 전기·승강기
    "전기설비기술기준", "한국전기설비",
    "승강기안전부품",
    # 건축·내진
    "내진설계", "에너지효율", "에너지절약",
    # 위험물·기계
    "위험물안전관리세부기준", "위험물안전관리",
    "기계식주차장",
    # 환경·기타
    "유해화학물질", "화학물질확인",
    # 부속시설 (어린이/학교/의료)
    "어린이놀이시설안전", "학교시설", "종합병원",
    "공중보건위기",
    # 통신
    "방송통신설비기술기준",
]


# ═══════════════════════════════════════════════════════════
# 수집
# ═══════════════════════════════════════════════════════════

def _upsert_catalog_entry(
    supabase, law_data: dict, api_target: str,
    keyword: str, page: int,
) -> bool:
    """단일 법령을 카탈로그에 UPSERT. 중복 시 skip."""
    law_api_id = (law_data.get("law_api_id") or "").strip()
    law_mst_no = (law_data.get("law_mst_no") or "").strip()
    
    if not law_api_id or not law_mst_no:
        return False
    
    payload = {
        "law_name": law_data.get("law_name", "") or "",
        "law_name_short": law_data.get("law_name_short", "") or None,
        "law_api_id": law_api_id,
        "law_mst_no": law_mst_no,
        "law_type_name": law_data.get("law_type_name", "") or None,
        "law_type_code": law_type_name_to_code(law_data.get("law_type_name", "") or ""),
        "ministry_code": law_data.get("ministry_code", "") or None,
        "ministry_name": law_data.get("ministry_name", "") or None,
        "law_number": str(law_data.get("law_number", "") or "") or None,
        "announcement_date": str(law_data["announcement_date"]) if law_data.get("announcement_date") else None,
        "enforcement_date": str(law_data["enforcement_date"]) if law_data.get("enforcement_date") else None,
        "revision_type": law_data.get("revision_type", "") or None,
        "api_target": api_target,
        "search_keyword": keyword,
        "search_page": page,
    }
    
    try:
        result = supabase.table("law_external_catalog").upsert(
            payload, on_conflict="law_api_id,law_mst_no,api_target"
        ).execute()
        return bool(result.data)
    except Exception as e:
        # UNIQUE 충돌은 정상 (이미 다른 키워드로 발견됨)
        if "duplicate" in str(e).lower() or "unique" in str(e).lower():
            return False
        print(f"  ⚠️ UPSERT 실패: {e}")
        return False


def cmd_collect(rate_limit_sec: float = 0.4) -> int:
    """키워드별로 법령 listing → law_external_catalog 적재."""
    supabase = get_supabase()
    
    print(f"\n{'=' * 70}")
    print(f"📚 외부 법령 카탈로그 수집 시작")
    print(f"{'=' * 70}")
    print(f"law 키워드: {len(KEYWORDS_LAW)}개")
    print(f"admrul 키워드: {len(KEYWORDS_ADMRUL)}개")
    print(f"Rate limit: {rate_limit_sec}초/요청\n")
    
    total_inserted = 0
    total_skipped = 0
    total_errors = 0
    
    # ──────────────────────────────────────────────────
    # Phase 1: target=law (법률/시행령/시행규칙)
    # ──────────────────────────────────────────────────
    print(f"\n{'─' * 70}\n🔍 Phase 1: target=law\n{'─' * 70}")
    
    for kw_idx, keyword in enumerate(KEYWORDS_LAW, 1):
        print(f"\n[{kw_idx}/{len(KEYWORDS_LAW)}] '{keyword}' (law)")
        
        for page in range(1, 11):  # 최대 10페이지 (1000건)
            try:
                result = fetch_law_list(query=keyword, display=100, page=page)
                if not result["ok"]:
                    print(f"  ❌ 페이지 {page}: HTTP {result['status']}")
                    total_errors += 1
                    break
                
                laws = parse_law_list_xml(result["xml"])
                if not laws:
                    print(f"  → 페이지 {page}: 결과 없음 (종료)")
                    break
                
                inserted_this_page = 0
                for law in laws:
                    if _upsert_catalog_entry(supabase, law, "law", keyword, page):
                        inserted_this_page += 1
                        total_inserted += 1
                    else:
                        total_skipped += 1
                
                print(f"  → 페이지 {page}: {len(laws)}건 (신규 {inserted_this_page})")
                
                if len(laws) < 100:
                    # 마지막 페이지
                    break
                
                time.sleep(rate_limit_sec)
            
            except Exception as e:
                print(f"  ❌ 페이지 {page} 오류: {type(e).__name__}: {str(e)[:100]}")
                total_errors += 1
                break
        
        time.sleep(rate_limit_sec)
    
    # ──────────────────────────────────────────────────
    # Phase 2: target=admrul (행정규칙/고시/기준)
    # ──────────────────────────────────────────────────
    print(f"\n{'─' * 70}\n🔍 Phase 2: target=admrul\n{'─' * 70}")
    
    for kw_idx, keyword in enumerate(KEYWORDS_ADMRUL, 1):
        print(f"\n[{kw_idx}/{len(KEYWORDS_ADMRUL)}] '{keyword}' (admrul)")
        
        for page in range(1, 11):
            try:
                result = fetch_admrul_list(query=keyword, display=100, page=page)
                if not result["ok"]:
                    print(f"  ❌ 페이지 {page}: HTTP {result['status']}")
                    total_errors += 1
                    break
                
                rules = parse_admrul_list_xml(result["xml"])
                if not rules:
                    print(f"  → 페이지 {page}: 결과 없음 (종료)")
                    break
                
                inserted_this_page = 0
                for rule in rules:
                    if _upsert_catalog_entry(supabase, rule, "admrul", keyword, page):
                        inserted_this_page += 1
                        total_inserted += 1
                    else:
                        total_skipped += 1
                
                print(f"  → 페이지 {page}: {len(rules)}건 (신규 {inserted_this_page})")
                
                if len(rules) < 100:
                    break
                
                time.sleep(rate_limit_sec)
            
            except Exception as e:
                print(f"  ❌ 페이지 {page} 오류: {type(e).__name__}: {str(e)[:100]}")
                total_errors += 1
                break
        
        time.sleep(rate_limit_sec)
    
    # ──────────────────────────────────────────────────
    # 최종 통계
    # ──────────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print(f"🎉 카탈로그 수집 완료")
    print(f"{'=' * 70}")
    
    total_count = supabase.table("law_external_catalog").select("id", count="exact").execute()
    print(f"📊 누적 법령 (distinct): {total_count.count}")
    print(f"📊 이번 세션 신규 적재: {total_inserted}")
    print(f"📊 이미 등록되어 skip: {total_skipped}")
    print(f"📊 오류: {total_errors}")
    print(f"\n다음 단계: python3 scripts/collect_catalog.py classify")
    
    return 0 if total_errors == 0 else 1


# ═══════════════════════════════════════════════════════════
# 분류 — 보유/타겟과 대조
# ═══════════════════════════════════════════════════════════

def cmd_classify() -> int:
    """카탈로그 항목을 보유/타겟과 대조하여 분류."""
    supabase = get_supabase()
    
    print(f"\n{'=' * 70}\n🔬 카탈로그 분류 시작\n{'=' * 70}\n")
    
    # 1. 보유 법령 (law_master)에 있는지
    print("Step 1: law_master 보유 여부 마킹...")
    sql_in_master = """
        UPDATE law_external_catalog ec
        SET is_in_law_master = (
            EXISTS(
                SELECT 1 FROM law_master lm 
                WHERE lm.law_name = ec.law_name
                   OR lm.law_api_id = ec.law_api_id
            )
        );
    """
    
    # 2. law_collection_target에 있는지
    print("Step 2: law_collection_target 등록 여부 마킹...")
    sql_in_target = """
        UPDATE law_external_catalog ec
        SET is_in_collection_target = (
            EXISTS(
                SELECT 1 FROM law_collection_target lct
                WHERE lct.law_name = ec.law_name
                   OR lct.law_api_id = ec.law_api_id
            )
        );
    """
    
    # 3. archive에 있는지
    print("Step 3: archive 보관 여부 마킹...")
    sql_in_archive = """
        UPDATE law_external_catalog ec
        SET is_in_archive = (
            EXISTS(
                SELECT 1 FROM law_master_archive_20260422 lma
                WHERE lma.law_name = ec.law_name
                   OR lma.law_api_id = ec.law_api_id
            )
        );
    """
    
    # 4. SaaS 관련성 분류 (키워드 + 부처 기반)
    print("Step 4: SaaS 관련성 분류...")
    sql_saas_relevance = """
        UPDATE law_external_catalog ec
        SET saas_relevance = CASE
            -- OUT_OF_SCOPE: 명확히 SaaS 범위 밖
            WHEN ec.law_name LIKE '%선박%' OR ec.law_name LIKE '%선원%'
              OR ec.law_name LIKE '%어선원%' OR ec.law_name LIKE '%선내%'
              OR ec.law_name LIKE '%항공%' OR ec.law_name LIKE '%항공기%'
              OR ec.law_name LIKE '%철도%' OR ec.law_name LIKE '%궤도%'
              OR ec.law_name LIKE '%국립%병원%' OR ec.law_name LIKE '%국립%연구원%'
              OR ec.law_name LIKE '%대검찰청%' OR ec.law_name LIKE '%법원안전%'
              OR ec.law_name LIKE '%재외동포%' OR ec.law_name LIKE '%외무%'
              OR ec.law_name LIKE '%국방%' OR ec.law_name LIKE '%군인%'
              OR ec.law_name LIKE '%캠핑용%' OR ec.law_name LIKE '%이동용%'
              OR ec.law_name LIKE '%어린이제품%' OR ec.law_name LIKE '%어린이보호포장%'
            THEN 'OUT_OF_SCOPE'
            
            -- CORE: 건물/산업/건설 핵심
            WHEN ec.law_name LIKE '%건축%' OR ec.law_name LIKE '%건설%'
              OR ec.law_name LIKE '%산업안전%' OR ec.law_name LIKE '%산안%'
              OR ec.law_name LIKE '%소방%' OR ec.law_name LIKE '%화재%'
              OR ec.law_name LIKE '%위험물%' OR ec.law_name LIKE '%가스%'
              OR ec.law_name LIKE '%전기%' OR ec.law_name LIKE '%승강기%'
              OR ec.law_name LIKE '%중대재해%' OR ec.law_name LIKE '%작업환경%'
              OR ec.law_name LIKE '%안전보건%'
              OR ec.law_name LIKE '%다중이용%' OR ec.law_name LIKE '%시설물%'
              OR ec.law_name LIKE '%주차장%' OR ec.law_name LIKE '%수도%'
              OR ec.law_name LIKE '%하수%' OR ec.law_name LIKE '%공장%'
              OR ec.law_name LIKE '%화학물질%' OR ec.law_name LIKE '%석면%'
              OR ec.law_name LIKE '%공동주택관리%' OR ec.law_name LIKE '%분양%'
              OR ec.law_name LIKE '%국토%' OR ec.law_name LIKE '%건축물%'
            THEN 'CORE'
            
            -- EXTENDED: 부속시설 (학교/의료/복지/장애인편의) — 사용자 통찰
            WHEN ec.law_name LIKE '%의료%' OR ec.law_name LIKE '%병원%'
              OR ec.law_name LIKE '%노인%' OR ec.law_name LIKE '%사회복지%'
              OR ec.law_name LIKE '%장애인%' OR ec.law_name LIKE '%학교%'
              OR ec.law_name LIKE '%어린이놀이%'
            THEN 'EXTENDED'
            
            -- ENVIRONMENT
            WHEN ec.law_name LIKE '%환경%' OR ec.law_name LIKE '%폐기물%'
              OR ec.law_name LIKE '%대기%' OR ec.law_name LIKE '%소음%'
              OR ec.law_name LIKE '%진동%' OR ec.law_name LIKE '%악취%'
              OR ec.law_name LIKE '%토양%'
            THEN 'CORE'
            
            ELSE 'PENDING'
        END;
    """
    
    print("\n⚠️  자동 분류 SQL은 Supabase 콘솔에서 직접 실행하세요:")
    print("   (Python 클라이언트는 raw UPDATE 미지원)")
    print("\n또는 다음 SQL을 Supabase MCP/콘솔에서 실행:\n")
    print(sql_in_master)
    print(sql_in_target)
    print(sql_in_archive)
    print(sql_saas_relevance)
    
    return 0


# ═══════════════════════════════════════════════════════════
# 통계 / 누락 추출
# ═══════════════════════════════════════════════════════════

def cmd_status() -> int:
    """카탈로그 수집 진행 상황."""
    supabase = get_supabase()
    
    print(f"\n{'=' * 70}\n📊 외부 카탈로그 통계\n{'=' * 70}\n")
    
    total = supabase.table("law_external_catalog").select("id", count="exact").execute()
    print(f"📚 총 distinct 법령: {total.count}\n")
    
    # api_target별
    for target in ["law", "admrul"]:
        count = supabase.table("law_external_catalog") \
            .select("id", count="exact") \
            .eq("api_target", target).execute()
        print(f"  - {target}: {count.count}")
    
    # 분류 통계 (분류 실행되어 있으면)
    classified = supabase.table("law_external_catalog") \
        .select("id", count="exact") \
        .not_.is_("saas_relevance", "null").execute()
    print(f"\n분류 완료: {classified.count}/{total.count}")
    
    if classified.count > 0:
        for relevance in ["CORE", "EXTENDED", "OUT_OF_SCOPE", "PENDING"]:
            cnt = supabase.table("law_external_catalog") \
                .select("id", count="exact") \
                .eq("saas_relevance", relevance).execute()
            print(f"  - {relevance}: {cnt.count}")
        
        print()
        in_master = supabase.table("law_external_catalog") \
            .select("id", count="exact") \
            .eq("is_in_law_master", True).execute()
        print(f"  ✅ law_master 보유: {in_master.count}")
        
        not_in_master = supabase.table("law_external_catalog") \
            .select("id", count="exact") \
            .eq("is_in_law_master", False).execute()
        print(f"  ❌ law_master 미보유: {not_in_master.count}")
    
    return 0


def cmd_missing() -> int:
    """진짜 누락 법령 추출 — CORE/EXTENDED 중 보유/타겟 둘 다 없는 것."""
    supabase = get_supabase()
    
    print(f"\n{'=' * 70}\n🎯 진짜 누락 법령 (수집 후보)\n{'=' * 70}\n")
    
    result = supabase.table("law_external_catalog") \
        .select("law_name,law_type_code,ministry_name,saas_relevance,api_target,search_keyword") \
        .eq("is_in_law_master", False) \
        .eq("is_in_collection_target", False) \
        .in_("saas_relevance", ["CORE", "EXTENDED"]) \
        .order("saas_relevance") \
        .order("ministry_name") \
        .order("law_name") \
        .execute()
    
    laws = result.data or []
    if not laws:
        print("✅ 누락 법령 없음! (모두 보유/타겟에 등록됨)")
        return 0
    
    print(f"발견된 누락: {len(laws)}건\n")
    
    by_relevance = {"CORE": [], "EXTENDED": []}
    for law in laws:
        by_relevance[law["saas_relevance"]].append(law)
    
    for rel in ["CORE", "EXTENDED"]:
        if not by_relevance[rel]:
            continue
        print(f"\n[{rel}] {len(by_relevance[rel])}건")
        print("-" * 70)
        for law in by_relevance[rel]:
            print(f"  - [{law['ministry_name'] or '미지정'}] "
                  f"({law['law_type_code']}) {law['law_name']}")
    
    print(f"\n다음 단계: 검토 후 law_collection_target에 INSERT")
    return 0


# ═══════════════════════════════════════════════════════════
# 메인
# ═══════════════════════════════════════════════════════════

def print_usage():
    print(__doc__)


def main() -> int:
    if len(sys.argv) < 2:
        print_usage()
        return 1
    
    command = sys.argv[1].lower()
    
    if command == "collect":
        return cmd_collect()
    elif command == "classify":
        return cmd_classify()
    elif command == "status":
        return cmd_status()
    elif command == "missing":
        return cmd_missing()
    elif command in ("help", "--help", "-h"):
        print_usage()
        return 0
    else:
        print(f"❌ 알 수 없는 명령: {command}")
        print_usage()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
