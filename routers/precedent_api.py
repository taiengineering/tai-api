"""
routers/precedent_api.py — v1.7.3

v1.7.3 (2026-04-29):
  [FIX] EDGE_COLLECT_URL 기본값을 서울 프로젝트로 변경 (구 프로젝트 삭제 대비)

v1.7.2: GET /master-keys 시행령/시행규칙 포함
v1.7.1: save-matched upsert 오류 수정
v1.7.0: GET /master-keys + POST /save-matched
"""
from __future__ import annotations
import os, logging, re, httpx
import xml.etree.ElementTree as ET
from fastapi import APIRouter, Query, HTTPException
from typing import Optional
from datetime import datetime, timezone
from db.supabase_client import get_supabase

log = logging.getLogger(__name__)
router = APIRouter(prefix="/precedents", tags=["산재판례"])

# 서울 프로젝트 기반 기본값, 환경변수로 오버라이드 가능
_sb_url = os.environ.get("SUPABASE_URL", "https://vwlahtguyggrhvslabax.supabase.co")
EDGE_COLLECT_URL = os.environ.get(
    "SUPABASE_EDGE_COLLECT_URL",
    f"{_sb_url}/functions/v1/collect-precedents"
)
INTERNAL_SECRET = os.environ.get("INTERNAL_API_SECRET", "")
DEFAULT_DISPLAY = 20
VALID_SECTORS = {"BUILDING", "INDUSTRY", "CONSTRUCTION", "ALL"}

_EXCLUDE_PATTERNS = ["NFTC", "NFPC", "고시", "통합고시", "세칙", "규정",
                     "기술기준", "성능기준", "안전기준", "세부기준", "기준통합"]


@router.get("/master-keys")
async def get_master_search_keys(secret: str = Query("")):
    if secret != INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="내부 전용")
    sb = get_supabase()
    rows = sb.table("master_building_legal_rules").select(
        "rule_id, law_name, law_article"
    ).eq("is_active", True).not_.is_("law_article", "null").execute()
    groups = {}
    for row in (rows.data or []):
        law_name = row.get("law_name", "")
        law_article = row.get("law_article", "")
        if any(p in law_name for p in _EXCLUDE_PATTERNS):
            continue
        m = re.match(r"제(\d+)조", law_article)
        if not m:
            continue
        article_no = m.group(1)
        key = f"{law_name}|{article_no}"
        if key not in groups:
            groups[key] = {
                "law_name": law_name, "article_no": article_no,
                "search_query": f"{law_name} 제{article_no}조", "rule_ids": [],
            }
        groups[key]["rule_ids"].append(row["rule_id"])
    result = []
    for g in groups.values():
        g["rule_ids"] = list(set(g["rule_ids"]))
        g["rule_count"] = len(g["rule_ids"])
        result.append(g)
    result.sort(key=lambda x: x["rule_count"], reverse=True)
    return {"status": "success", "total_keys": len(result), "keys": result}


@router.post("/save-matched")
async def save_matched_precedent(body: dict):
    secret = body.get("secret", "")
    if secret != INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="내부 전용")
    prec = body.get("precedent", {})
    rule_ids = body.get("rule_ids", [])
    if not prec.get("prec_seq"):
        raise HTTPException(status_code=400, detail="prec_seq 필수")
    if not rule_ids:
        raise HTTPException(status_code=400, detail="rule_ids 필수")
    sb = get_supabase()
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        existing = sb.table("industrial_accident_precedents").select(
            "id"
        ).eq("prec_seq", str(prec["prec_seq"])).execute()
        prec_id = None
        if existing.data:
            prec_id = existing.data[0]["id"]
            update_data = {k: v for k, v in prec.items()
                          if v is not None and k not in ("prec_seq", "id")}
            update_data["updated_at"] = now_iso
            sb.table("industrial_accident_precedents").update(
                update_data
            ).eq("id", prec_id).execute()
            action = "updated"
        else:
            prec["created_at"] = now_iso
            prec["updated_at"] = now_iso
            ins = sb.table("industrial_accident_precedents").insert(prec).execute()
            if ins.data:
                prec_id = ins.data[0]["id"]
            action = "inserted"
        links_created = 0
        if prec_id:
            for rule_id in rule_ids:
                try:
                    ex = sb.table("precedent_rule_links").select("id").eq(
                        "precedent_id", prec_id
                    ).eq("rule_id", rule_id).execute()
                    if ex.data:
                        continue
                    sb.table("precedent_rule_links").insert({
                        "precedent_id": prec_id, "rule_id": rule_id,
                        "relevance_score": 90, "link_type": "violation",
                    }).execute()
                    links_created += 1
                except Exception as e:
                    log.warning(f"[PREC] link 실패 ({rule_id}): {e}")
        return {"status": "success", "action": action,
                "prec_seq": prec["prec_seq"], "links_created": links_created}
    except Exception as e:
        log.error(f"[PREC] save-matched 에러: {e}")
        raise HTTPException(status_code=500, detail=str(e)[:200])


@router.get("/search")
def search_precedents(
    query: str = Query(...), sector: Optional[str] = Query(None),
    year: Optional[int] = Query(None), page: int = Query(1, ge=1),
    display: int = Query(DEFAULT_DISPLAY, ge=1, le=100),
    size: Optional[int] = Query(None),
):
    if size is not None:
        display = min(size, 100)
    sb = get_supabase()
    offset = (page - 1) * display
    q = (sb.table("posts")
           .select("id, title, summary, source_id, external_url, tags, published_at, subcategory")
           .ilike("title", f"%{query}%").eq("status", "published").eq("category", "산재판례"))
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


@router.get("/iap/search")
def search_iap(
    query: str = Query(...), sector: Optional[str] = Query(None),
    hazard_type: Optional[str] = Query(None), year: Optional[int] = Query(None),
    page: int = Query(1, ge=1), size: int = Query(DEFAULT_DISPLAY, ge=1, le=100),
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
    res = (sb.table("posts").select("*")
             .eq("source", "law_go_kr_prec").eq("source_id", f"PREC_{prec_id}").execute())
    if not res.data:
        raise HTTPException(status_code=404, detail="판례를 찾을 수 없습니다.")
    return {"status": "success", "data": res.data[0]}


@router.post("/collect")
async def collect_precedents(body: dict = None):
    return await _call_collect_edge()

@router.post("/sync")
async def sync_precedents():
    return await _call_collect_edge()

async def _call_collect_edge() -> dict:
    secret = os.environ.get("TAI_COLLECT_SECRET", "")
    headers = {"Content-Type": "application/json"}
    if secret: headers["x-tai-secret"] = secret
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(EDGE_COLLECT_URL, headers=headers, json={})
        if resp.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"Edge Function 오류: {resp.status_code}")
        return resp.json()
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        raise HTTPException(status_code=503, detail=f"Edge Function 연결 실패: {type(e).__name__}")
