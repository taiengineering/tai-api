"""
routers/precedent_api.py — v1.5.0

v1.5.0 (2026-04-25):
  [ADD] GET /precedents/test-api — 법제처 판례 API 실제 응답 테스트
        master DB 법령명 기준 검색 + TAI 테이블 매핑 미리보기
        직접 호출 → 실패 시 iwinv proxy 폴백

v1.4.0 (2026-04-16 SB-04/SB-06):
  [ADD] GET /precedents/search 파라미터 확장: sector, year 추가
  [ADD] POST /precedents/sync  — /collect 별칭 (SB-06 cron HTTP trigger용)
  [ADD] GET /precedents/iap/search — industrial_accident_precedents 테이블 직접 검색

【환경변수】
  SUPABASE_EDGE_COLLECT_URL  Edge Function URL
  TAI_COLLECT_SECRET         Edge Function 호출 인증키
"""
from __future__ import annotations
import os, logging, httpx, re
import xml.etree.ElementTree as ET
from fastapi import APIRouter, Query, HTTPException
from typing import Optional, List, Dict, Any
from db.supabase_client import get_supabase

log    = logging.getLogger(__name__)
router = APIRouter(prefix="/precedents", tags=["산재판례"])

EDGE_COLLECT_URL = os.environ.get(
    "SUPABASE_EDGE_COLLECT_URL",
    "https://xntdkrjhgcscmqctdzyo.supabase.co/functions/v1/collect-precedents"
)
LAW_OC = "taieng"
PROXY_URL = os.environ.get("PROXY_URL", "http://115.68.227.222:3128")
INTERNAL_SECRET = os.environ.get("INTERNAL_API_SECRET", "")

DEFAULT_DISPLAY = 20
VALID_SECTORS = {"BUILDING", "INDUSTRY", "CONSTRUCTION", "ALL"}

LAW_API_SEARCH = "http://www.law.go.kr/DRF/lawSearch.do"
LAW_API_DETAIL = "http://www.law.go.kr/DRF/lawService.do"


# ── 판례 API 헬퍼 ──────────────────────────────────────────

async def _fetch_law_api(url: str, params: dict) -> str:
    """법제처 API 호출. 직접 → proxy 폴백."""
    # 1차: 직접 호출
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, params=params)
            if resp.status_code == 200 and len(resp.text) > 100:
                return resp.text
    except Exception as e:
        log.info(f"[PREC] 직접 호출 실패 (proxy 시도): {e}")

    # 2차: iwinv proxy
    try:
        async with httpx.AsyncClient(
            timeout=20,
            proxy=PROXY_URL,
        ) as client:
            resp = await client.get(url, params=params)
            if resp.status_code == 200:
                return resp.text
    except Exception as e:
        log.warning(f"[PREC] proxy 호출도 실패: {e}")

    return ""


def _parse_prec_list(xml_text: str) -> tuple:
    """판례 목록 XML 파싱 → (items, total_count)"""
    if not xml_text:
        return [], 0

    root = ET.fromstring(xml_text)
    total = 0
    total_el = root.find("totalCnt")
    if total_el is not None and total_el.text:
        total = int(total_el.text)

    items = []
    # 법제처 XML: <PrecSearch><prec>...</prec></PrecSearch> 또는 직접 하위
    for node in root.iter():
        if node.find("판례일련번호") is not None:
            item = {}
            for field in ["판례일련번호", "사건명", "사건번호", "선고일자",
                          "법원명", "사건종류명", "사건종류코드", "판결유형",
                          "선고", "판례상세링크"]:
                el = node.find(field)
                item[field] = el.text.strip() if el is not None and el.text else None
            items.append(item)

    return items, total


def _parse_prec_detail(xml_text: str) -> dict:
    """판례 상세 XML 파싱"""
    if not xml_text:
        return {}

    root = ET.fromstring(xml_text)
    detail = {}
    for field in ["판례정보일련번호", "사건명", "사건번호", "선고일자",
                   "법원명", "사건종류명", "판결유형", "선고",
                   "판시사항", "판결요지", "참조조문", "참조판례", "판례내용"]:
        el = root.find(f".//{field}")
        if el is not None and el.text:
            detail[field] = el.text.strip()

    return detail


def _map_to_tai_table(item: dict, detail: dict = None) -> dict:
    """API 응답 → industrial_accident_precedents 컬럼 매핑"""
    mapped = {
        "case_number": item.get("사건번호"),
        "case_name": item.get("사건명"),
        "court_name": item.get("법원명"),
        "decision_date": None,
        "case_type": item.get("사건종류명"),
        "source": "law_go_kr",
        "source_url": None,
        "prec_seq": item.get("판례일련번호"),
    }

    # 날짜 변환: "20240315" → "2024-03-15"
    raw_date = item.get("선고일자", "") or ""
    if len(raw_date) == 8:
        mapped["decision_date"] = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"

    # 소스 URL
    seq = item.get("판례일련번호")
    if seq:
        mapped["source_url"] = f"https://www.law.go.kr/precInfoP.do?precSeq={seq}"

    if detail:
        mapped["summary"] = (detail.get("판결요지") or "")[:500]
        mapped["full_text_length"] = len(detail.get("판례내용") or "")
        mapped["judicial_summary"] = (detail.get("판시사항") or "")[:300]
        mapped["violation_laws_raw"] = detail.get("참조조문")
        mapped["related_precedents"] = detail.get("참조판례")

    # AI 태깅 필요 필드 (빈칸으로 표시)
    mapped["_ai_tagging_needed"] = [
        "sector", "hazard_type", "accident_type", "equipment_type",
        "defendant_type", "sentence_type", "sentence_detail",
        "violation_types", "violation_summary", "keywords", "condition_codes"
    ]

    return mapped


# ── GET /precedents/test-api ────────────────────────────────

@router.get("/test-api")
async def test_precedent_api(
    law_name: str = Query("산업안전보건법", description="검색할 법령명 (master DB 기준)"),
    display: int = Query(3, ge=1, le=10, description="검색 건수"),
    detail: bool = Query(False, description="첫 건 상세 조회 여부"),
    secret: str = Query("", description="INTERNAL_API_SECRET"),
):
    """법제처 판례 API 실제 응답 테스트.
    master DB 법령명으로 검색 → 원시 응답 + TAI 테이블 매핑 미리보기.
    """
    if secret != INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="내부 전용 엔드포인트")

    # 1. 목록 검색
    params = {
        "OC": LAW_OC,
        "target": "prec",
        "type": "XML",
        "query": law_name,
        "display": display,
        "search": 2,  # 판시요지+판시내용 검색
    }
    xml_text = await _fetch_law_api(LAW_API_SEARCH, params)
    if not xml_text:
        return {
            "status": "error",
            "message": "법제처 API 호출 실패 (직접+proxy 모두)",
            "hint": "Railway/proxy IP가 차단됐을 수 있음"
        }

    items, total = _parse_prec_list(xml_text)

    # 2. 상세 조회 (옵션)
    detail_data = None
    if detail and items and items[0].get("판례일련번호"):
        detail_params = {
            "OC": LAW_OC,
            "target": "prec",
            "type": "XML",
            "ID": items[0]["판례일련번호"],
        }
        detail_xml = await _fetch_law_api(LAW_API_DETAIL, detail_params)
        detail_data = _parse_prec_detail(detail_xml)

    # 3. TAI 매핑 미리보기
    tai_mappings = []
    for i, item in enumerate(items):
        d = detail_data if (i == 0 and detail_data) else None
        tai_mappings.append(_map_to_tai_table(item, d))

    # 4. master 매칭 후보 (같은 법령명의 rule_id 샘플)
    sb = get_supabase()
    master_sample = sb.table("master_building_legal_rules").select(
        "rule_id, law_article, obligation_type, obligation_summary"
    ).ilike("law_name", f"%{law_name}%").eq(
        "is_active", True
    ).limit(5).execute()

    # 5. 통계
    all_laws = sb.table("master_building_legal_rules").select(
        "law_name", count="exact"
    ).eq("is_active", True).ilike("law_name", f"%{law_name}%").execute()

    return {
        "status": "success",
        "test_summary": {
            "검색_법령": law_name,
            "검색_총건수": total,
            "반환_건수": len(items),
            "상세_조회": detail is True,
            "API_호출_방식": "direct_or_proxy",
        },
        "raw_items": items,
        "detail": detail_data,
        "tai_table_mapping": tai_mappings,
        "master_rule_samples": master_sample.data or [],
        "master_rule_count": all_laws.count or 0,
        "storage_plan": {
            "step1_direct_save": ["case_number", "case_name", "court_name", "decision_date",
                                   "case_type", "source", "source_url"],
            "step2_detail_fetch": ["summary(판결요지)", "full_text(판례내용)",
                                    "violation_laws(참조조문→jsonb)"],
            "step3_ai_tagging": ["sector", "hazard_type", "accident_type", "equipment_type",
                                  "defendant_type", "sentence_type", "violation_types",
                                  "keywords", "condition_codes"],
            "step4_rule_matching": "참조조문 파싱 → master law_article 매칭 → precedent_rule_links INSERT",
        },
    }


# ── GET /precedents/search  (posts 테이블 조회) ──────────────────────────

@router.get("/search")
def search_precedents(
    query:   str           = Query(..., description="검색 키워드"),
    sector:  Optional[str] = Query(None, description="섹터 필터: BUILDING / INDUSTRY / CONSTRUCTION / ALL"),
    year:    Optional[int] = Query(None, description="결정연도 필터 (예: 2023)"),
    source:  Optional[str] = Query(None, description="소스 필터 (현재 미사용)"),
    page:    int           = Query(1, ge=1),
    display: int           = Query(DEFAULT_DISPLAY, ge=1, le=100),
    size:    Optional[int] = Query(None, description="display 별칭"),
):
    if size is not None:
        display = min(size, 100)

    sb = get_supabase()
    offset = (page - 1) * display

    q = (sb.table("posts")
           .select("id, title, summary, source_id, external_url, tags, published_at, subcategory")
           .ilike("title", f"%{query}%")
           .eq("status", "published")
           .eq("category", "산재판례"))

    if sector and sector.upper() in VALID_SECTORS and sector.upper() != "ALL":
        q = q.eq("subcategory", sector.upper())

    if year:
        q = q.gte("published_at", f"{year}-01-01").lte("published_at", f"{year}-12-31")

    res = q.order("published_at", desc=True).range(offset, offset + display - 1).execute()

    cnt_q = (sb.table("posts")
               .select("id", count="exact")
               .ilike("title", f"%{query}%")
               .eq("status", "published")
               .eq("category", "산재판례"))
    if sector and sector.upper() in VALID_SECTORS and sector.upper() != "ALL":
        cnt_q = cnt_q.eq("subcategory", sector.upper())
    if year:
        cnt_q = cnt_q.gte("published_at", f"{year}-01-01").lte("published_at", f"{year}-12-31")
    cnt = cnt_q.execute()

    return {
        "status":  "success",
        "query":   query,
        "sector":  sector or "all",
        "year":    year,
        "total":   cnt.count or 0,
        "page":    page,
        "display": display,
        "items":   res.data or [],
    }


# ── GET /precedents/iap/search  (industrial_accident_precedents 테이블) ──

@router.get("/iap/search")
def search_iap(
    query:      str           = Query(..., description="검색 키워드 (case_name, summary 검색)"),
    sector:     Optional[str] = Query(None, description="섹터 필터: BUILDING / INDUSTRY / CONSTRUCTION"),
    hazard_type:Optional[str] = Query(None, description="위험유형: 추락/충돌/화재 등"),
    year:       Optional[int] = Query(None, description="결정연도"),
    page:       int           = Query(1, ge=1),
    size:       int           = Query(DEFAULT_DISPLAY, ge=1, le=100),
):
    sb = get_supabase()
    offset = (page - 1) * size

    q = sb.table("industrial_accident_precedents") \
          .select("id, case_number, case_name, court_name, decision_date, sector, hazard_type, summary, source_url") \
          .ilike("case_name", f"%{query}%")

    if sector:
        q = q.eq("sector", sector.upper())
    if hazard_type:
        q = q.ilike("hazard_type", f"%{hazard_type}%")
    if year:
        q = q.gte("decision_date", f"{year}-01-01").lte("decision_date", f"{year}-12-31")

    res = q.order("decision_date", desc=True).range(offset, offset + size - 1).execute()

    return {
        "status": "success",
        "query":  query,
        "total":  len(res.data or []),
        "page":   page,
        "size":   size,
        "items":  res.data or [],
    }


# ── GET /precedents/{prec_id}  (posts 테이블 단건 조회) ──────────────────

@router.get("/{prec_id}")
def get_precedent(prec_id: str):
    sb  = get_supabase()
    res = (sb.table("posts")
             .select("*")
             .eq("source", "law_go_kr_prec")
             .eq("source_id", f"PREC_{prec_id}")
             .execute())

    if not res.data:
        raise HTTPException(status_code=404,
                            detail=f"판례를 찾을 수 없습니다. (ID: {prec_id})")
    return {"status": "success", "data": res.data[0]}


# ── POST /precedents/collect  (Edge Function 프록시) ─────────────────────

@router.post("/collect")
async def collect_precedents(body: dict = None):
    return await _call_collect_edge()


@router.post("/sync")
async def sync_precedents():
    log.info("[PRECEDENT] /sync 호출 (cron trigger)")
    return await _call_collect_edge()


async def _call_collect_edge() -> dict:
    secret = os.environ.get("TAI_COLLECT_SECRET", "")
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["x-tai-secret"] = secret

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(EDGE_COLLECT_URL, headers=headers, json={})

        if resp.status_code == 401:
            raise HTTPException(status_code=503,
                                detail="Edge Function 인증 실패. TAI_COLLECT_SECRET 확인 필요.")
        if resp.status_code >= 400:
            raise HTTPException(status_code=502,
                                detail=f"Edge Function 오류: {resp.status_code} — {resp.text[:200]}")

        result = resp.json()
        log.info("[PRECEDENT] Edge collect 완료: %s", result)
        return result

    except (httpx.ConnectError, httpx.TimeoutException) as e:
        log.error("[PRECEDENT] Edge Function 연결 실패: %s", e)
        raise HTTPException(status_code=503,
                            detail=f"Edge Function 연결 실패: {type(e).__name__}")
