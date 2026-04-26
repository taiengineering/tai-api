"""
routers/precedent_api.py — v1.6.0

v1.6.0 (2026-04-26):
  [ADD] POST /precedents/save — Mac 수집 스크립트에서 판례 저장
        prec_seq 기준 upsert (중복 방지)

v1.5.0 (2026-04-25):
  [ADD] GET /precedents/test-api — 법제처 판례 API 실제 응답 테스트

v1.4.0 (2026-04-16 SB-04/SB-06):
  [ADD] GET /precedents/search 파라미터 확장: sector, year 추가
  [ADD] POST /precedents/sync  — /collect 별칭
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
from datetime import datetime, timezone
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


# ── POST /precedents/save ─────────────────────────────────

@router.post("/save")
async def save_precedent(body: dict):
    """Mac 수집 스크립트에서 호출. prec_seq 기준 upsert."""
    secret = body.get("secret", "")
    if secret != INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="내부 전용")

    prec = body.get("precedent", {})
    if not prec.get("prec_seq"):
        raise HTTPException(status_code=400, detail="prec_seq 필수")
    if not prec.get("case_number"):
        raise HTTPException(status_code=400, detail="case_number 필수")

    sb = get_supabase()

    # 중복 체크
    existing = sb.table("industrial_accident_precedents").select(
        "id"
    ).eq("prec_seq", prec["prec_seq"]).execute()

    if existing.data:
        # UPDATE (상세 보강)
        update_data = {
            k: v for k, v in prec.items()
            if v is not None and k != "prec_seq"
        }
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        sb.table("industrial_accident_precedents").update(
            update_data
        ).eq("prec_seq", prec["prec_seq"]).execute()
        return {"status": "success", "action": "updated", "prec_seq": prec["prec_seq"]}
    else:
        # INSERT
        prec["created_at"] = datetime.now(timezone.utc).isoformat()
        prec["updated_at"] = datetime.now(timezone.utc).isoformat()
        sb.table("industrial_accident_precedents").insert(prec).execute()
        return {"status": "success", "action": "inserted", "prec_seq": prec["prec_seq"]}


# ── 판례 API 헬퍼 ──────────────────────────────────────────

async def _fetch_law_api(url: str, params: dict) -> str:
    """법제처 API 호출. 직접 → proxy 폴백."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, params=params)
            if resp.status_code == 200 and len(resp.text) > 100:
                return resp.text
    except Exception as e:
        log.info(f"[PREC] 직접 호출 실패 (proxy 시도): {e}")

    try:
        async with httpx.AsyncClient(timeout=20, proxy=PROXY_URL) as client:
            resp = await client.get(url, params=params)
            if resp.status_code == 200:
                return resp.text
    except Exception as e:
        log.warning(f"[PREC] proxy 호출도 실패: {e}")

    return ""


def _parse_prec_list(xml_text: str) -> tuple:
    if not xml_text:
        return [], 0
    root = ET.fromstring(xml_text)
    total = 0
    total_el = root.find("totalCnt")
    if total_el is not None and total_el.text:
        total = int(total_el.text)
    items = []
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
    raw_date = item.get("선고일자", "") or ""
    if len(raw_date) == 8:
        mapped["decision_date"] = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
    seq = item.get("판례일련번호")
    if seq:
        mapped["source_url"] = f"https://www.law.go.kr/precInfoP.do?precSeq={seq}"
    if detail:
        mapped["summary"] = (detail.get("판결요지") or "")[:500]
        mapped["full_text_length"] = len(detail.get("판례내용") or "")
        mapped["judicial_summary"] = (detail.get("판시사항") or "")[:300]
        mapped["violation_laws_raw"] = detail.get("참조조문")
        mapped["related_precedents"] = detail.get("참조판례")
    mapped["_ai_tagging_needed"] = [
        "sector", "hazard_type", "accident_type", "equipment_type",
        "defendant_type", "sentence_type", "sentence_detail",
        "violation_types", "violation_summary", "keywords", "condition_codes"
    ]
    return mapped


# ── GET /precedents/test-api ────────────────────────────────

@router.get("/test-api")
async def test_precedent_api(
    law_name: str = Query("산업안전보건법"),
    display: int = Query(3, ge=1, le=10),
    detail: bool = Query(False),
    secret: str = Query(""),
):
    if secret != INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="내부 전용 엔드포인트")

    params = {
        "OC": LAW_OC, "target": "prec", "type": "XML",
        "query": law_name, "display": display, "search": 2,
    }
    xml_text = await _fetch_law_api(LAW_API_SEARCH, params)
    if not xml_text:
        return {"status": "error", "message": "법제처 API 호출 실패"}

    items, total = _parse_prec_list(xml_text)

    detail_data = None
    if detail and items and items[0].get("판례일련번호"):
        detail_xml = await _fetch_law_api(LAW_API_DETAIL, {
            "OC": LAW_OC, "target": "prec", "type": "XML",
            "ID": items[0]["판례일련번호"],
        })
        detail_data = _parse_prec_detail(detail_xml)

    tai_mappings = []
    for i, item in enumerate(items):
        d = detail_data if (i == 0 and detail_data) else None
        tai_mappings.append(_map_to_tai_table(item, d))

    sb = get_supabase()
    master_sample = sb.table("master_building_legal_rules").select(
        "rule_id, law_article, obligation_type, obligation_summary"
    ).ilike("law_name", f"%{law_name}%").eq("is_active", True).limit(5).execute()

    return {
        "status": "success",
        "test_summary": {"검색_법령": law_name, "검색_총건수": total, "반환_건수": len(items)},
        "raw_items": items,
        "detail": detail_data,
        "tai_table_mapping": tai_mappings,
        "master_rule_samples": master_sample.data or [],
    }


# ── GET /precedents/search ──────────────────────────────────

@router.get("/search")
def search_precedents(
    query: str = Query(...),
    sector: Optional[str] = Query(None),
    year: Optional[int] = Query(None),
    source: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    display: int = Query(DEFAULT_DISPLAY, ge=1, le=100),
    size: Optional[int] = Query(None),
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

    return {"status": "success", "query": query, "total": cnt.count or 0,
            "page": page, "display": display, "items": res.data or []}


# ── GET /precedents/iap/search ──────────────────────────────

@router.get("/iap/search")
def search_iap(
    query: str = Query(...),
    sector: Optional[str] = Query(None),
    hazard_type: Optional[str] = Query(None),
    year: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(DEFAULT_DISPLAY, ge=1, le=100),
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
    return {"status": "success", "query": query, "total": len(res.data or []),
            "page": page, "size": size, "items": res.data or []}


# ── GET /precedents/{prec_id} ───────────────────────────────

@router.get("/{prec_id}")
def get_precedent(prec_id: str):
    sb = get_supabase()
    res = (sb.table("posts").select("*")
             .eq("source", "law_go_kr_prec")
             .eq("source_id", f"PREC_{prec_id}").execute())
    if not res.data:
        raise HTTPException(status_code=404, detail=f"판례를 찾을 수 없습니다. (ID: {prec_id})")
    return {"status": "success", "data": res.data[0]}


# ── POST /precedents/collect ────────────────────────────────

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
            raise HTTPException(status_code=503, detail="Edge Function 인증 실패")
        if resp.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"Edge Function 오류: {resp.status_code}")
        result = resp.json()
        log.info("[PRECEDENT] Edge collect 완료: %s", result)
        return result
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        log.error("[PRECEDENT] Edge Function 연결 실패: %s", e)
        raise HTTPException(status_code=503, detail=f"Edge Function 연결 실패: {type(e).__name__}")
