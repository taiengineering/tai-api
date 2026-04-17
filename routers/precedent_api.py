"""
routers/precedent_api.py — v1.4.0

v1.4.0 (2026-04-16 SB-04/SB-06):
  [ADD] GET /precedents/search 파라미터 확장: sector, year 추가
  [ADD] POST /precedents/sync  — /collect 별칭 (SB-06 cron HTTP trigger용)
  [ADD] GET /precedents/iap/search — industrial_accident_precedents 테이블 직접 검색

v1.3.0 (기존):
  GET  /precedents/search   → posts 테이블 DB 조회
  GET  /precedents/{id}     → posts 테이블 source_id 조회
  POST /precedents/collect  → Supabase Edge Function 프록시
"""
from __future__ import annotations
import os, logging, httpx
from fastapi import APIRouter, Query, HTTPException
from typing import Optional
from db.supabase_client import get_supabase

log    = logging.getLogger(__name__)
router = APIRouter(prefix="/precedents", tags=["산재판례"])

EDGE_COLLECT_URL = os.environ.get(
    "SUPABASE_EDGE_COLLECT_URL",
    "https://xntdkrjhgcscmqctdzyo.supabase.co/functions/v1/collect-precedents"
)

DEFAULT_DISPLAY = 20
VALID_SECTORS = {"BUILDING", "INDUSTRY", "CONSTRUCTION", "ALL"}


@router.get("/search")
def search_precedents(
    query:   str           = Query(..., description="검색 키워드"),
    sector:  Optional[str] = Query(None, description="섹터 필터: BUILDING / INDUSTRY / CONSTRUCTION / ALL"),
    year:    Optional[int] = Query(None, description="결정연도 필터 (예: 2023)"),
    source:  Optional[str] = Query(None),
    page:    int           = Query(1, ge=1),
    display: int           = Query(DEFAULT_DISPLAY, ge=1, le=100),
    size:    Optional[int] = Query(None),
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
    cnt_q = (sb.table("posts").select("id", count="exact")
               .ilike("title", f"%{query}%").eq("status", "published").eq("category", "산재판례"))
    if sector and sector.upper() in VALID_SECTORS and sector.upper() != "ALL":
        cnt_q = cnt_q.eq("subcategory", sector.upper())
    if year:
        cnt_q = cnt_q.gte("published_at", f"{year}-01-01").lte("published_at", f"{year}-12-31")
    cnt = cnt_q.execute()
    return {"status": "success", "query": query, "sector": sector or "all", "year": year,
            "total": cnt.count or 0, "page": page, "display": display, "items": res.data or []}


@router.get("/iap/search")
def search_iap(
    query:      str           = Query(...),
    sector:     Optional[str] = Query(None),
    hazard_type:Optional[str] = Query(None),
    year:       Optional[int] = Query(None),
    page:       int           = Query(1, ge=1),
    size:       int           = Query(DEFAULT_DISPLAY, ge=1, le=100),
):
    sb = get_supabase()
    offset = (page - 1) * size
    q = sb.table("industrial_accident_precedents") \
          .select("id, case_number, case_name, court_name, decision_date, sector, hazard_type, summary, source_url") \
          .ilike("case_name", f"%{query}%")
    if sector: q = q.eq("sector", sector.upper())
    if hazard_type: q = q.ilike("hazard_type", f"%{hazard_type}%")
    if year: q = q.gte("decision_date", f"{year}-01-01").lte("decision_date", f"{year}-12-31")
    res = q.order("decision_date", desc=True).range(offset, offset + size - 1).execute()
    return {"status": "success", "query": query, "total": len(res.data or []),
            "page": page, "size": size, "items": res.data or []}


@router.get("/{prec_id}")
def get_precedent(prec_id: str):
    sb = get_supabase()
    res = sb.table("posts").select("*").eq("source", "law_go_kr_prec").eq("source_id", f"PREC_{prec_id}").execute()
    if not res.data:
        raise HTTPException(status_code=404, detail=f"판례를 찾을 수 없습니다. (ID: {prec_id})")
    return {"status": "success", "data": res.data[0]}


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
    if secret: headers["x-tai-secret"] = secret
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(EDGE_COLLECT_URL, headers=headers, json={})
        if resp.status_code == 401:
            raise HTTPException(status_code=503, detail="Edge Function 인증 실패.")
        if resp.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"Edge Function 오류: {resp.status_code} — {resp.text[:200]}")
        result = resp.json()
        log.info("[PRECEDENT] Edge collect 완료: %s", result)
        return result
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        log.error("[PRECEDENT] Edge Function 연결 실패: %s", e)
        raise HTTPException(status_code=503, detail=f"Edge Function 연결 실패: {type(e).__name__}")
