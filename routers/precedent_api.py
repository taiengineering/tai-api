"""
routers/precedent_api.py — v1.3.0

【구조】
  GET  /precedents/search   → posts 테이블 DB 조회
  GET  /precedents/{id}     → posts 테이블 source_id 조회
  POST /precedents/collect  → Supabase Edge Function 프록시
                              (Railway IP 차단 우회: Railway → Edge Fn → law.go.kr)

【환경변수】
  SUPABASE_EDGE_COLLECT_URL  Edge Function URL (기본값 하드코딩)
  TAI_COLLECT_SECRET         Edge Function 호출 인증키 (없으면 무인증)
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
SAFETY_KEYWORDS = [
    "추락", "협착", "전도", "화재", "폭발",
    "질식", "감전", "충돌", "절단", "유해화학물질",
    "안전관리자", "산업재해", "중대재해", "사망",
]


# ── GET /precedents/search  (DB 조회) ─────────────────────────────────────
@router.get("/search")
def search_precedents(
    query:   str           = Query(..., description="검색 키워드"),
    source:  Optional[str] = Query(None),
    page:    int           = Query(1, ge=1),
    display: int           = Query(DEFAULT_DISPLAY, ge=1, le=100),
    size:    Optional[int] = Query(None),
):
    """posts 테이블(산재판례)에서 키워드 검색. law.go.kr 직접 호출 없음."""
    if size is not None:
        display = min(size, 100)

    sb = get_supabase()
    offset = (page - 1) * display

    res = (sb.table("posts")
             .select("id, title, summary, source_id, external_url, tags, published_at, subcategory")
             .ilike("title", f"%{query}%")
             .eq("status", "published")
             .eq("category", "산재판례")
             .order("published_at", desc=True)
             .range(offset, offset + display - 1)
             .execute())

    cnt = (sb.table("posts")
             .select("id", count="exact")
             .ilike("title", f"%{query}%")
             .eq("status", "published")
             .eq("category", "산재판례")
             .execute())

    return {
        "status":  "success",
        "query":   query,
        "source":  source or "all",
        "total":   cnt.count or 0,
        "page":    page,
        "display": display,
        "items":   res.data or [],
    }


# ── GET /precedents/{prec_id}  (DB 조회) ─────────────────────────────────
@router.get("/{prec_id}")
def get_precedent(prec_id: str):
    """source_id=PREC_{prec_id} 로 posts 테이블 단건 조회."""
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
    """
    Supabase Edge Function을 통해 산재판례 수집.
    Railway IP 차단 우회: Railway → Edge Fn (다른 IP) → law.go.kr
    
    ※ Edge Function Secret 필요:
      Supabase 대시보드 > Functions > collect-precedents > Secrets
      LAW_API_OC = (Railway와 동일한 값)
    """
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
        log.info(f"[PRECEDENT] Edge collect 완료: {result}")
        return result

    except (httpx.ConnectError, httpx.TimeoutException) as e:
        log.error(f"[PRECEDENT] Edge Function 연결 실패: {e}")
        raise HTTPException(status_code=503,
                            detail=f"Edge Function 연결 실패: {type(e).__name__}")
