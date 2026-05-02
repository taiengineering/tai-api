# routers/law_catalog_collector.py — v1.0.0
# 외부 법령 카탈로그 수집 (Railway 백그라운드 실행)
#
# 목적: 법제처 OPEN API 키워드별 listing → law_external_catalog 적재
# 사용:
#   POST /law-collector/collect-catalog            # 시작 (백그라운드)
#   GET  /law-collector/catalog-status             # 진행 확인
#
# 배경: 사용자 로컬 .env DNS 문제 우회. Railway는 자체 환경변수 사용.
# 작성: 2026-05-02

import time
from datetime import datetime
from fastapi import APIRouter, BackgroundTasks
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

router = APIRouter(prefix="/law-collector", tags=["법령 외부 카탈로그"])

# ════════════════════════════════════════════════════════
# 키워드 카테고리—SaaS 범위 (건물/산업/건설 + 다중 부속시설)
# ════════════════════════════════════════════════════════

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


# ════════════════════════════════════════════════════════
# 적재 헬퍼
# ════════════════════════════════════════════════════════

def _upsert_catalog_entry(supabase, law_data, api_target, keyword, page):
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
        msg = str(e).lower()
        if "duplicate" in msg or "unique" in msg:
            return False
        print(f"[CATALOG] UPSERT 실패: {e}")
        return False


# ════════════════════════════════════════════════════════
# 백그라운드 수집
# ════════════════════════════════════════════════════════

def _run_collect_catalog(rate_limit_sec: float = 0.4):
    started_at = datetime.now()
    print(f"\n{'=' * 70}\n📚 외부 카탈로그 수집 시작 ({started_at.isoformat()})\n{'=' * 70}")
    print(f"law 키워드: {len(KEYWORDS_LAW)}개")
    print(f"admrul 키워드: {len(KEYWORDS_ADMRUL)}개")
    print(f"Rate limit: {rate_limit_sec}초/요청\n")

    supabase = get_supabase()
    total_inserted = 0
    total_skipped = 0
    total_errors = 0

    # Phase 1: target=law
    print(f"\n{'─' * 70}\n🔍 Phase 1: target=law\n{'─' * 70}")
    for kw_idx, keyword in enumerate(KEYWORDS_LAW, 1):
        print(f"[{kw_idx}/{len(KEYWORDS_LAW)}] '{keyword}' (law)")
        for page in range(1, 11):
            try:
                result = fetch_law_list(query=keyword, display=100, page=page)
                if not result["ok"]:
                    print(f"  ❌ 페이지 {page}: HTTP {result['status']}")
                    total_errors += 1
                    break
                laws = parse_law_list_xml(result["xml"])
                if not laws:
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
                    break
                time.sleep(rate_limit_sec)
            except Exception as e:
                print(f"  ❌ 오류: {type(e).__name__}: {str(e)[:100]}")
                total_errors += 1
                break
        time.sleep(rate_limit_sec)

    # Phase 2: target=admrul
    print(f"\n{'─' * 70}\n🔍 Phase 2: target=admrul\n{'─' * 70}")
    for kw_idx, keyword in enumerate(KEYWORDS_ADMRUL, 1):
        print(f"[{kw_idx}/{len(KEYWORDS_ADMRUL)}] '{keyword}' (admrul)")
        for page in range(1, 11):
            try:
                result = fetch_admrul_list(query=keyword, display=100, page=page)
                if not result["ok"]:
                    print(f"  ❌ 페이지 {page}: HTTP {result['status']}")
                    total_errors += 1
                    break
                rules = parse_admrul_list_xml(result["xml"])
                if not rules:
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
                print(f"  ❌ 오류: {type(e).__name__}: {str(e)[:100]}")
                total_errors += 1
                break
        time.sleep(rate_limit_sec)

    elapsed_min = (datetime.now() - started_at).total_seconds() / 60
    total_count = supabase.table("law_external_catalog").select("id", count="exact").execute()
    print(f"\n{'=' * 70}")
    print(f"🎉 카탈로그 수집 완료 (소요: {elapsed_min:.1f}분)")
    print(f"  누적 distinct: {total_count.count}")
    print(f"  신규 적재: {total_inserted}")
    print(f"  skip: {total_skipped}")
    print(f"  오류: {total_errors}")
    print(f"{'=' * 70}")


# ════════════════════════════════════════════════════════
# 엔드포인트
# ════════════════════════════════════════════════════════

@router.post("/collect-catalog")
async def trigger_collect_catalog(background_tasks: BackgroundTasks):
    background_tasks.add_task(_run_collect_catalog)
    return {
        "status": "started",
        "message": "외부 카탈로그 수집 시작. law_external_catalog 테이블에서 진행 확인.",
        "keywords_law": len(KEYWORDS_LAW),
        "keywords_admrul": len(KEYWORDS_ADMRUL),
        "estimated_duration_minutes": "30~60",
        "started_at": datetime.now().isoformat(),
    }


@router.get("/catalog-status")
async def get_catalog_status():
    supabase = get_supabase()
    total = supabase.table("law_external_catalog").select("id", count="exact").execute()
    by_law = supabase.table("law_external_catalog").select("id", count="exact").eq("api_target", "law").execute()
    by_admrul = supabase.table("law_external_catalog").select("id", count="exact").eq("api_target", "admrul").execute()

    # 최근 적재 시간 조회 (진행 중인지 판단용)
    recent = supabase.table("law_external_catalog") \
        .select("collected_at, search_keyword, api_target") \
        .order("collected_at", desc=True).limit(1).execute()
    last_collected = recent.data[0] if recent.data else None

    return {
        "total": total.count,
        "by_target": {
            "law": by_law.count,
            "admrul": by_admrul.count,
        },
        "last_collected": last_collected,
    }


@router.get("/catalog-keywords")
async def get_catalog_keywords():
    return {
        "keywords_law": KEYWORDS_LAW,
        "keywords_admrul": KEYWORDS_ADMRUL,
    }
