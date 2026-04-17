"""
routers/precedent_api.py — v2.0.0

v2.0.0 (2026-04-17):
  [BREAKING] Edge Function 제거 → Fly.io에서 law.go.kr 직접 호출
  법제처 IP 등록: Fly.io outbound IP 등록 완료
  환경변수: LAW_API_OC (법제처 OPEN API 인증키)

v1.4.0:
  sector/year 파라미터, /sync 별칭, /iap/search
"""
from __future__ import annotations
import os, logging, httpx, re
from fastapi import APIRouter, Query, HTTPException
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from db.supabase_client import get_supabase

log    = logging.getLogger(__name__)
router = APIRouter(prefix="/precedents", tags=["산재판례"])

# 법제처 OPEN API
LAW_API_OC = os.environ.get("LAW_API_OC", "")
LAW_API_BASE = "https://www.law.go.kr/DRF/lawSearch.do"

DEFAULT_DISPLAY = 20
VALID_SECTORS = {"BUILDING", "INDUSTRY", "CONSTRUCTION", "ALL"}

SAFETY_KEYWORDS = [
    "추락", "협착", "전도", "화재", "폭발",
    "질식", "감전", "충돌", "절단", "유해화학물질",
    "안전관리자", "산업재해", "중대재해", "사망",
]


# ── 법제처 API 직접 호출 ──────────────────────────────────────

async def _fetch_precedents_from_law(keyword: str, display: int = 20) -> List[Dict[str, Any]]:
    """법제처 law.go.kr 판례 검색 API 직접 호출"""
    if not LAW_API_OC:
        log.warning("[PRECEDENT] LAW_API_OC 환경변수 미설정")
        return []

    params = {
        "OC": LAW_API_OC,
        "target": "prec",
        "type": "JSON",
        "query": keyword,
        "display": str(display),
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(LAW_API_BASE, params=params)

        if resp.status_code != 200:
            log.error("[PRECEDENT] law.go.kr HTTP %d: %s", resp.status_code, resp.text[:200])
            return []

        data = resp.json()

        # 응답 구조: {"PrecSearch":{"prec":[...], "totalCnt": N}} 또는 에러
        if isinstance(data, dict):
            # 에러 응답 처리
            if "result" in data and "실패" in str(data.get("result", "")):
                log.error("[PRECEDENT] law.go.kr API 오류: %s", data.get("msg", data.get("result")))
                return []

            prec_search = data.get("PrecSearch", {})
            if isinstance(prec_search, dict):
                items = prec_search.get("prec", [])
                if isinstance(items, dict):  # 단건일 때 dict로 온다
                    items = [items]
                return items if isinstance(items, list) else []

        return []

    except Exception as e:
        log.error("[PRECEDENT] law.go.kr 호출 실패 (keyword=%s): %s", keyword, e)
        return []


async def _save_precedents_to_db(items: List[Dict[str, Any]], keyword: str) -> Dict[str, int]:
    """검색된 판례를 posts 테이블에 저장 (중복 스킵)"""
    sb = get_supabase()
    saved = 0
    skipped = 0

    for item in items:
        prec_id = str(item.get("판례일련번호") or item.get("precId") or item.get("판례ID") or "").strip()
        if not prec_id:
            # 제목에서 ID 추출 시도
            title = item.get("사건명") or item.get("판례명") or item.get("precName") or ""
            prec_id = re.sub(r'[^0-9]', '', title)[:10] or f"AUTO_{hash(title) % 100000}"

        source_id = f"PREC_{prec_id}"

        # 중복 찾기
        try:
            existing = sb.table("posts").select("id").eq("source_id", source_id).limit(1).execute()
            if existing.data:
                skipped += 1
                continue
        except Exception:
            pass

        title = (
            item.get("사건명") or item.get("판례명") or
            item.get("precName") or item.get("caseNm") or "무제"
        )
        summary = (
            item.get("판시사항") or item.get("요지") or
            item.get("precSummary") or item.get("judgeNote") or ""
        )
        court = item.get("법원명") or item.get("courtName") or ""
        decision_date = item.get("선고일자") or item.get("precDate") or ""
        detail_link = item.get("판례상세링크") or item.get("detailLink") or ""

        if detail_link and not detail_link.startswith("http"):
            detail_link = f"https://www.law.go.kr{detail_link}"

        # published_at 파싱
        pub_at = None
        if decision_date:
            clean = re.sub(r'[^0-9]', '', decision_date)
            if len(clean) >= 8:
                try:
                    pub_at = f"{clean[:4]}-{clean[4:6]}-{clean[6:8]}"
                except Exception:
                    pass

        row = {
            "title": str(title)[:500],
            "summary": str(summary)[:5000] if summary else None,
            "source": "law_go_kr_prec",
            "source_id": source_id,
            "external_url": detail_link or None,
            "category": "산재판례",
            "subcategory": keyword,
            "tags": [keyword, court] if court else [keyword],
            "status": "published",
            "published_at": pub_at,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            sb.table("posts").insert(row).execute()
            saved += 1
        except Exception as e:
            log.error("[PRECEDENT] posts INSERT 실패 (source_id=%s): %s", source_id, e)

    return {"saved": saved, "skipped": skipped}


# ── GET /precedents/search ───────────────────────────────────────

@router.get("/search")
def search_precedents(
    query:   str           = Query(..., description="검색 키워드"),
    sector:  Optional[str] = Query(None),
    year:    Optional[int] = Query(None),
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


# ── GET /precedents/iap/search ──────────────────────────────────

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


# ── GET /precedents/{prec_id} ───────────────────────────────────

@router.get("/{prec_id}")
def get_precedent(prec_id: str):
    sb = get_supabase()
    res = sb.table("posts").select("*").eq("source", "law_go_kr_prec").eq("source_id", f"PREC_{prec_id}").execute()
    if not res.data:
        raise HTTPException(status_code=404, detail=f"판례를 찾을 수 없습니다. (ID: {prec_id})")
    return {"status": "success", "data": res.data[0]}


# ── POST /precedents/collect (v2.0.0: 직접 호출) ──────────────────

@router.post("/collect")
async def collect_precedents(body: dict = None):
    """
    v2.0.0: Fly.io에서 law.go.kr 직접 호출.
    Edge Function 우회 제거 — 법제처에 Fly.io IP 등록 완료.
    환경변수: LAW_API_OC
    """
    if not LAW_API_OC:
        raise HTTPException(status_code=500,
                            detail="LAW_API_OC 환경변수가 설정되지 않았습니다. Fly.io Secrets에 등록해주세요.")

    keywords = (body or {}).get("keywords") or SAFETY_KEYWORDS
    total_saved = 0
    total_skipped = 0
    errors = []
    debug_info = []

    for kw in keywords:
        try:
            items = await _fetch_precedents_from_law(kw, display=20)
            if not items:
                debug_info.append({"keyword": kw, "fetched": 0, "note": "결과 없음"})
                continue

            result = await _save_precedents_to_db(items, kw)
            total_saved += result["saved"]
            total_skipped += result["skipped"]
            debug_info.append({
                "keyword": kw,
                "fetched": len(items),
                "saved": result["saved"],
                "skipped": result["skipped"],
            })
        except Exception as e:
            errors.append({"keyword": kw, "error": str(e)})
            log.error("[PRECEDENT] collect 실패 (keyword=%s): %s", kw, e)

    log.info("[PRECEDENT] collect 완료: saved=%d skipped=%d errors=%d", total_saved, total_skipped, len(errors))

    return {
        "status": "ok",
        "version": "2.0.0",
        "method": "direct",
        "saved": total_saved,
        "skipped": total_skipped,
        "errors": len(errors),
        "keywords": len(keywords),
        "debugInfo": debug_info,
        "errorDetails": errors if errors else None,
    }


# ── POST /precedents/sync (별칭) ──────────────────────────────

@router.post("/sync")
async def sync_precedents():
    """SB-06: /collect의 별칭 (cron trigger용)"""
    log.info("[PRECEDENT] /sync 호출 (cron trigger)")
    return await collect_precedents()
