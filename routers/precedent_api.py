"""
routers/precedent_api.py — v1.0.1
산재판례 검색 / 단건 조회 / 안전 키워드 일괄 수집

law.go.kr DRF API 활용:
  datSrcNm=근로복지공단산재판례  →  산재판례 전용 필터
  환경변수: LAW_API_OC  (기존 키 재사용)

Endpoints
  GET  /precedents/search          키워드 + source 필터 검색
  GET  /precedents/{prec_id}       본문 단건 조회
  POST /precedents/collect         안전 키워드 일괄 수집 → posts 저장

Cron (DB 등록): PRECEDENT_COLLECT_WEEKLY  매주 월 05:00
"""
from __future__ import annotations
import os, logging, httpx, asyncio
from datetime import datetime, timezone
from fastapi import APIRouter, Query, HTTPException
from typing import Optional
from db.supabase_client import get_supabase

log    = logging.getLogger(__name__)
router = APIRouter(prefix="/precedents", tags=["산재판례"])

# ── 상수 ───────────────────────────────────────────────────────────────────
LAW_BASE   = "https://www.law.go.kr/DRF/lawSearch.do"
LAW_DETAIL = "https://www.law.go.kr/DRF/lawService.do"
DAT_SRC    = "근로복지공단산재판례"

# 안전 관련 수집 키워드
SAFETY_KEYWORDS = [
    "추락", "협착", "전도", "화재", "폭발",
    "질식", "감전", "충돌", "절단", "유해화학물질",
    "안전관리자", "산업재해", "중대재해", "사망",
]

DEFAULT_DISPLAY = 20   # 검색 결과 기본 건수
COLLECT_DISPLAY = 5    # 수집 시 키워드당 최대 건수


def _oc() -> str:
    oc = os.environ.get("LAW_API_OC", "")
    if not oc:
        raise HTTPException(status_code=503, detail="LAW_API_OC 환경변수 미설정")
    return oc


def _law_params(extra: dict) -> dict:
    return {"OC": _oc(), "target": "prec", "type": "JSON",
            "datSrcNm": DAT_SRC, **extra}


# ── GET /precedents/search ─────────────────────────────────────────────────
@router.get("/search")
async def search_precedents(
    query:   str            = Query(..., description="검색 키워드"),
    source:  Optional[str]  = Query(None, description="출처 필터 (비워두면 산재판례 전체)"),
    page:    int            = Query(1, ge=1),
    display: int            = Query(DEFAULT_DISPLAY, ge=1, le=100),
):
    """산재판례 키워드 검색. source 파라미터로 출처 추가 필터링 가능."""
    params = _law_params({
        "query":   query,
        "display": display,
        "page":    page,
    })
    if source:
        params["datSrcNm"] = source  # 더 좁은 출처로 오버라이드

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(LAW_BASE, params=params)

    if resp.status_code != 200:
        raise HTTPException(status_code=502,
                            detail=f"law.go.kr 응답 오류: {resp.status_code}")

    raw  = resp.json()
    body = raw.get("PrecSearch", {})
    items = body.get("prec", [])
    if isinstance(items, dict):          # 단건이면 list로 감쌈
        items = [items]

    return {
        "status":  "success",
        "query":   query,
        "source":  source or DAT_SRC,
        "total":   int(body.get("totalCnt", 0)),
        "page":    page,
        "display": display,
        "items":   items,
    }


# ── GET /precedents/{prec_id} ─────────────────────────────────────────────
@router.get("/{prec_id}")
async def get_precedent(prec_id: str):
    """판례일련번호로 본문 단건 조회."""
    params = _law_params({"ID": prec_id})
    params["target"] = "prec"

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(LAW_DETAIL, params=params)

    if resp.status_code != 200:
        raise HTTPException(status_code=502,
                            detail=f"law.go.kr 응답 오류: {resp.status_code}")

    raw  = resp.json()
    data = raw.get("PrecService", raw)
    if not data:
        raise HTTPException(status_code=404, detail="판례를 찾을 수 없습니다.")

    return {"status": "success", "data": data}


# ── POST /precedents/collect ─────────────────────────────────────────────
@router.post("/collect")
async def collect_precedents(body: dict = None):
    """
    안전 키워드로 산재판례를 일괄 수집해 posts 테이블에 저장.
    source_id 중복 건은 skip (INSERT 시도 → 오류 무시).
    크론(PRECEDENT_COLLECT_WEEKLY) 또는 수동 실행 가능.
    """
    sb      = get_supabase()
    saved   = 0
    skipped = 0
    errors  = 0

    async with httpx.AsyncClient(timeout=30) as client:
        for keyword in SAFETY_KEYWORDS:
            try:
                params = _law_params({
                    "query":   keyword,
                    "display": COLLECT_DISPLAY,
                    "page":    1,
                })
                resp = await client.get(LAW_BASE, params=params)
                if resp.status_code != 200:
                    errors += 1
                    continue

                raw   = resp.json()
                items = raw.get("PrecSearch", {}).get("prec", [])
                if isinstance(items, dict):
                    items = [items]

                for item in items:
                    prec_id   = str(item.get("판례일련번호", ""))
                    title     = item.get("사건명", "") or item.get("제목", "")
                    source_id = f"PREC_{prec_id}"

                    if not prec_id or not title:
                        continue

                    # 중복 확인
                    dup = sb.table("posts") \
                            .select("id") \
                            .eq("source", "law_go_kr_prec") \
                            .eq("source_id", source_id) \
                            .execute()
                    if dup.data:
                        skipped += 1
                        continue

                    pub_date = item.get("선고일자", "") or item.get("공포일자", "")
                    try:
                        pub_dt = datetime.strptime(pub_date, "%Y. %m. %d.") \
                                         .replace(tzinfo=timezone.utc) \
                                         .isoformat() if pub_date else None
                    except ValueError:
                        pub_dt = None

                    post = {
                        "category":     "산재판례",
                        "subcategory":  keyword,
                        "title":        title,
                        "summary":      item.get("판시사항", "")[:500] if item.get("판시사항") else "",
                        "content":      item.get("판결요지", "") or item.get("전문", ""),
                        "source":       "law_go_kr_prec",
                        "source_id":    source_id,
                        "external_url": f"https://www.law.go.kr/precInfoP.do?precSeq={prec_id}",
                        "tags":         [keyword, "산재", "판례"],
                        "status":       "published",
                        "author_name":  "법령정보시스템",
                        "published_at": pub_dt,
                    }

                    try:
                        sb.table("posts").insert(post).execute()
                        saved += 1
                    except Exception as e:
                        log.warning(f"[PRECEDENT] INSERT 실패 {source_id}: {e}")
                        errors += 1

                await asyncio.sleep(0.3)   # rate-limit 방지

            except Exception as e:
                log.error(f"[PRECEDENT] 키워드={keyword} 오류: {e}")
                errors += 1

    log.info(f"[PRECEDENT] collect 완료 saved={saved} skipped={skipped} errors={errors}")
    return {
        "status":  "success",
        "saved":   saved,
        "skipped": skipped,
        "errors":  errors,
        "keywords": len(SAFETY_KEYWORDS),
    }
