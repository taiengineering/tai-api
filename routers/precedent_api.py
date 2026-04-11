"""
routers/precedent_api.py — v1.0.3

source 파라미터:
  None / '' → datSrcNm 미포함 (전체 판례)
  'sanjae'  → datSrcNm=근로복지공단산재판례

v1.0.3 변경:
  - sort=ddes 제거 (law.go.kr 리질 에러 원인)
  - safety-keywords 라우트를 /{prec_id} 앞으로 이동 (FastAPI 썸도움 방지)
"""
from __future__ import annotations
import os, logging, httpx, asyncio
from datetime import datetime, timezone
from fastapi import APIRouter, Query, HTTPException
from typing import Optional
from db.supabase_client import get_supabase

log    = logging.getLogger(__name__)
router = APIRouter(prefix="/precedents", tags=["산재판례"])

LAW_BASE       = "https://www.law.go.kr/DRF/lawSearch.do"
LAW_DETAIL     = "https://www.law.go.kr/DRF/lawService.do"
DAT_SRC_SANJAE = "근로복지공단산재판례"

SOURCE_MAP = {
    "sanjae":          DAT_SRC_SANJAE,
    "comwel":          DAT_SRC_SANJAE,
    "근로복지공단산재판례": DAT_SRC_SANJAE,
}

SAFETY_KEYWORDS = [
    "추락", "협착", "전도", "화재", "폭발",
    "질식", "감전", "충돌", "절단", "유해화학물질",
    "안전관리자", "산업재해", "중대재해", "사망",
]

DEFAULT_DISPLAY = 20
COLLECT_DISPLAY = 5


def _oc() -> str:
    oc = os.environ.get("LAW_API_OC", "")
    if not oc:
        raise HTTPException(status_code=503, detail="LAW_API_OC 환경변수 미설정")
    return oc


def _base_params() -> dict:
    return {"OC": _oc(), "target": "prec", "type": "JSON"}


# ── 콘크리트 라우트는 파라미터 라우트보다 먼저 선언 ────────────────
@router.get("/safety-keywords")
async def get_safety_keywords():
    return {"status": "success", "keywords": SAFETY_KEYWORDS}


@router.get("/search")
async def search_precedents(
    query:   str           = Query(...),
    source:  Optional[str] = Query(None),
    page:    int           = Query(1, ge=1),
    display: int           = Query(DEFAULT_DISPLAY, ge=1, le=100),
    size:    Optional[int] = Query(None),
):
    if size is not None:
        display = min(size, 100)

    params = _base_params()
    params.update({"query": query, "display": display, "page": page})
    # sort 제거 — law.go.kr에서 지원하지 않으면 500 발생

    if source:
        dat_src = SOURCE_MAP.get(source.lower().strip())
        if dat_src:
            params["datSrcNm"] = dat_src

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(LAW_BASE, params=params)

    if resp.status_code != 200:
        raise HTTPException(status_code=502,
                            detail=f"law.go.kr 응답 오류: {resp.status_code}")

    raw   = resp.json()
    body  = raw.get("PrecSearch", {})
    items = body.get("prec", [])
    if isinstance(items, dict):
        items = [items]

    return {
        "status":  "success",
        "query":   query,
        "source":  source or "all",
        "total":   int(body.get("totalCnt", 0)),
        "page":    page,
        "display": display,
        "items":   items,
    }


@router.get("/{prec_id}")
async def get_precedent(prec_id: str):
    params = _base_params()
    params["ID"] = prec_id

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


@router.post("/collect")
async def collect_precedents(body: dict = None):
    sb      = get_supabase()
    saved   = 0
    skipped = 0
    errors  = 0

    async with httpx.AsyncClient(timeout=30) as client:
        for keyword in SAFETY_KEYWORDS:
            try:
                params = _base_params()
                params.update({
                    "query":    keyword,
                    "display":  COLLECT_DISPLAY,
                    "page":     1,
                    "datSrcNm": DAT_SRC_SANJAE,
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

                    dup = (sb.table("posts")
                             .select("id")
                             .eq("source", "law_go_kr_prec")
                             .eq("source_id", source_id)
                             .execute())
                    if dup.data:
                        skipped += 1
                        continue

                    pub_date = item.get("선고일자", "") or item.get("공포일자", "")
                    try:
                        pub_dt = (datetime.strptime(pub_date, "%Y. %m. %d.")
                                          .replace(tzinfo=timezone.utc)
                                          .isoformat() if pub_date else None)
                    except ValueError:
                        pub_dt = None

                    post = {
                        "category":     "산재판례",
                        "subcategory":  keyword,
                        "title":        title,
                        "summary":      (item.get("판시사항", "") or "")[:500],
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

                await asyncio.sleep(0.3)

            except Exception as e:
                log.error(f"[PRECEDENT] 키워드={keyword} 오류: {e}")
                errors += 1

    log.info(f"[PRECEDENT] collect 완료 saved={saved} skipped={skipped} errors={errors}")
    return {
        "status":   "success",
        "saved":    saved,
        "skipped":  skipped,
        "errors":   errors,
        "keywords": len(SAFETY_KEYWORDS),
    }
