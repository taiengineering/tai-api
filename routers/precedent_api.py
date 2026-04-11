"""
routers/precedent_api.py — v1.2.0

【근본 원인 해결】
  Railway 서버 IP가 law.go.kr / data.go.kr 모두에서 차단됨
  (Connection reset by peer — law_collector.py 와 동일 증상)

【변경】
  GET  /precedents/search   → posts 테이블 DB 조회 (law.go.kr 직접 호출 제거)
  GET  /precedents/{id}     → posts 테이블 source_id 조회
  POST /precedents/collect  → 외부 API 호출 유지 (로컬/크론 전용, 실패 시 503 반환)
"""
from __future__ import annotations
import os, logging, httpx, asyncio
from datetime import datetime, timezone
from fastapi import APIRouter, Query, HTTPException
from typing import Optional
from db.supabase_client import get_supabase

log    = logging.getLogger(__name__)
router = APIRouter(prefix="/precedents", tags=["산재판례"])

# law.go.kr (collect 전용 — 로컬/외부에서만 작동)
LAW_BASE       = "https://www.law.go.kr/DRF/lawSearch.do"
LAW_DETAIL     = "https://www.law.go.kr/DRF/lawService.do"
DAT_SRC_SANJAE = "근로복지공단산재판례"

SAFETY_KEYWORDS = [
    "추락", "협착", "전도", "화재", "폭발",
    "질식", "감전", "충돌", "절단", "유해화학물질",
    "안전관리자", "산업재해", "중대재해", "사망",
]

DEFAULT_DISPLAY = 20
COLLECT_DISPLAY = 5


def _oc() -> str:
    return os.environ.get("LAW_API_OC", "taieng")


# ── GET /precedents/search  (DB 조회) ─────────────────────────────────────
@router.get("/search")
def search_precedents(
    query:   str           = Query(..., description="검색 키워드"),
    source:  Optional[str] = Query(None, description="sanjae = 산재판례만, 없으면 전체"),
    page:    int           = Query(1, ge=1),
    display: int           = Query(DEFAULT_DISPLAY, ge=1, le=100),
    size:    Optional[int] = Query(None),
):
    """
    posts 테이블(산재판례)에서 키워드 검색.
    Railway IP 차단 대응 — law.go.kr 직접 호출 없음.
    """
    if size is not None:
        display = min(size, 100)

    sb = get_supabase()

    q = (sb.table("posts")
           .select("id, title, summary, source_id, external_url, tags, published_at, subcategory")
           .ilike("title", f"%{query}%")
           .eq("status", "published"))

    # source 필터
    if source and source.lower() in ("sanjae", "comwel", "산재"):
        q = q.eq("category", "산재판례")
    else:
        q = q.eq("category", "산재판례")   # 현재 collect 는 산재판례만

    # 페이지네이션
    offset = (page - 1) * display
    q = q.order("published_at", desc=True).range(offset, offset + display - 1)

    res = q.execute()
    items = res.data or []

    # 전체 건수
    cnt_q = (sb.table("posts")
               .select("id", count="exact")
               .ilike("title", f"%{query}%")
               .eq("status", "published")
               .eq("category", "산재판례"))
    cnt_res = cnt_q.execute()
    total = cnt_res.count or 0

    return {
        "status":  "success",
        "query":   query,
        "source":  source or "all",
        "total":   total,
        "page":    page,
        "display": display,
        "items":   items,
    }


# ── GET /precedents/{prec_id}  (DB 조회) ─────────────────────────────────
@router.get("/{prec_id}")
def get_precedent(prec_id: str):
    """
    source_id=PREC_{prec_id} 로 posts 테이블에서 단건 조회.
    Railway IP 차단 대응 — law.go.kr 직접 호출 없음.
    """
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


# ── POST /precedents/collect  (law.go.kr 직접 호출 — 크론/로컬 전용) ────
@router.post("/collect")
async def collect_precedents(body: dict = None):
    """
    산재 키워드로 law.go.kr 산재판례를 수집해 posts 테이블에 저장.
    Railway IP 차단으로 Railway 환경에서는 실패할 수 있음.
    로컬 또는 외부 IP에서 수동 실행 권장.
    """
    sb      = get_supabase()
    saved   = 0
    skipped = 0
    errors  = 0
    blocked = False

    oc = _oc()

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            for keyword in SAFETY_KEYWORDS:
                try:
                    params = {
                        "OC":       oc,
                        "target":   "prec",
                        "type":     "JSON",
                        "datSrcNm": DAT_SRC_SANJAE,
                        "query":    keyword,
                        "display":  COLLECT_DISPLAY,
                        "page":     1,
                    }
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

                except (httpx.ConnectError, httpx.RemoteProtocolError,
                        httpx.TimeoutException) as e:
                    log.error(f"[PRECEDENT] 외부 API 연결 실패 (IP 차단 추정): {e}")
                    blocked = True
                    break
                except Exception as e:
                    log.error(f"[PRECEDENT] 키워드={keyword} 오류: {e}")
                    errors += 1

    except Exception as e:
        log.error(f"[PRECEDENT] collect 치명적 오류: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"법제처 API 연결 실패 (서버 IP 차단 추정). 로컬에서 실행하세요. 원인: {type(e).__name__}"
        )

    if blocked:
        raise HTTPException(
            status_code=503,
            detail="law.go.kr 연결 실패 (Railway IP 차단). 로컬 또는 외부 IP에서 실행하세요."
        )

    log.info(f"[PRECEDENT] collect 완료 saved={saved} skipped={skipped} errors={errors}")
    return {
        "status":   "success",
        "saved":    saved,
        "skipped":  skipped,
        "errors":   errors,
        "keywords": len(SAFETY_KEYWORDS),
    }
