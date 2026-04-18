"""
routers/precedent_api.py — v1.4.0

v1.4.0 (2026-04-16 SB-04/SB-06):
  [ADD] GET /precedents/search 파라미터 확장: sector, year 추가
  [ADD] POST /precedents/sync  — /collect 별칭 (SB-06 cron HTTP trigger용)
  [ADD] GET /precedents/iap/search — industrial_accident_precedents 테이블 직접 검색
  DB: industrial_accident_precedents 테이블 신규 생성 (migration 별도 적용)

v1.3.0 (기존):
  GET  /precedents/search   → posts 테이블 DB 조회
  GET  /precedents/{id}     → posts 테이블 source_id 조회
  POST /precedents/collect  → Supabase Edge Function 프록시

【구조】
  posts 테이블 (category='산재판례') — 기존 운용 중
  industrial_accident_precedents     — 신규 전용 테이블 (향후 posts 대체)

【환경변수】
  SUPABASE_EDGE_COLLECT_URL  Edge Function URL
  TAI_COLLECT_SECRET         Edge Function 호출 인증키
"""
from __future__ import annotations
import os, logging, httpx, re
from fastapi import APIRouter, Query, HTTPException
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from db.supabase_client import get_supabase

log    = logging.getLogger(__name__)
router = APIRouter(prefix="/precedents", tags=["산재판례"])

LAW_API_OC = os.environ.get("LAW_API_OC", "")
LAW_API_BASE = "https://www.law.go.kr/DRF/lawSearch.do"

DEFAULT_DISPLAY = 20
VALID_SECTORS = {"BUILDING", "INDUSTRY", "CONSTRUCTION", "ALL"}


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
    """
    posts 테이블(산재판례)에서 키워드 검색.
    sector, year 파라미터로 추가 필터링 가능.
    """
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
    """
    v1.4.0: industrial_accident_precedents 테이블 직접 검색.
    (posts 기반 /search와 병행 운용)
    """
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
    sb = get_supabase()
    res = sb.table("posts").select("*").eq("source", "law_go_kr_prec").eq("source_id", f"PREC_{prec_id}").execute()
    if not res.data:
        raise HTTPException(status_code=404, detail=f"판례를 찾을 수 없습니다.")
    return {"status": "success", "data": res.data[0]}


# ── POST /precedents/collect  (Edge Function 프록시) ─────────────────────

@router.post("/collect")
async def collect_precedents(body: dict = None):
    """
    Supabase Edge Function을 통해 산재판례 수집.
    Railway IP 차단 우회: Railway → Edge Fn (다른 IP) → law.go.kr
    """
    return await _call_collect_edge()


# ── POST /precedents/sync  (SB-06: /collect 별칭, cron HTTP trigger용) ───

@router.post("/sync")
async def sync_precedents():
    """
    SB-06: /collect의 별칭 엔드포인트.
    cron-job.org 또는 GitHub Actions에서 매일 04:00 KST 호출.
    결과를 cron_execution_log에 기록 (Edge Function 내부에서 처리).
    """
    log.info("[PRECEDENT] /sync 호출 (cron trigger)")
    return await _call_collect_edge()


async def _call_collect_edge() -> dict:
    """Edge Function collect-precedents 호출 공통 함수."""
    secret = os.environ.get("TAI_COLLECT_SECRET", "")
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["x-tai-secret"] = secret

    keywords = (body or {}).get("keywords") or SAFETY_KEYWORDS
    total_saved = 0
    total_skipped = 0
    errors = []
    debug_info = []

    for kw in keywords:
        try:
            items, note = await _fetch_precedents_from_law(kw, display=20)
            if not items:
                debug_info.append({"keyword": kw, "fetched": 0, "note": note or "결과 없음"})
                continue
            result = await _save_precedents_to_db(items, kw)
            total_saved += result["saved"]
            total_skipped += result["skipped"]
            debug_info.append({"keyword": kw, "fetched": len(items),
                               "saved": result["saved"], "skipped": result["skipped"]})
        except Exception as e:
            errors.append({"keyword": kw, "error": str(e)})

        result = resp.json()
        log.info("[PRECEDENT] Edge collect 완료: %s", result)
        return result

    except (httpx.ConnectError, httpx.TimeoutException) as e:
        log.error("[PRECEDENT] Edge Function 연결 실패: %s", e)
        raise HTTPException(status_code=503,
                            detail=f"Edge Function 연결 실패: {type(e).__name__}")
