"""
routers/precedent_api.py — v1.7.0

v1.7.0 (2026-04-26):
  [ADD] GET /precedents/master-keys — master 룰에서 판례 검색 키 추출
  [ADD] POST /precedents/save-matched — 판례 저장 + rule_ids 즉시 연결
  [REMOVE] POST /precedents/save — 매칭 없는 단순 저장 제거

v1.6.0: POST /precedents/save
v1.5.0: GET /precedents/test-api
v1.4.0: sector/year 필터, /sync, /iap/search
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

EDGE_COLLECT_URL = os.environ.get(
    "SUPABASE_EDGE_COLLECT_URL",
    "https://xntdkrjhgcscmqctdzyo.supabase.co/functions/v1/collect-precedents"
)
INTERNAL_SECRET = os.environ.get("INTERNAL_API_SECRET", "")
DEFAULT_DISPLAY = 20
VALID_SECTORS = {"BUILDING", "INDUSTRY", "CONSTRUCTION", "ALL"}

# 시행령/시행규칙/NFTC 등 제외 패턴
_CHILD_LAW_PATTERNS = ["시행령", "시행규칙", "NFTC", "NFPC", "고시", "통합고시", "기준", "세칙", "규정"]


# ── GET /precedents/master-keys ────────────────────────────

@router.get("/master-keys")
async def get_master_search_keys(
    secret: str = Query(""),
):
    """master 룰에서 판례 검색 키 추출.
    모법 + 조문번호 조합 → 각 조합에 해당하는 rule_id 목록.
    """
    if secret != INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="내부 전용")

    sb = get_supabase()
    rows = sb.table("master_building_legal_rules").select(
        "rule_id, law_name, law_article"
    ).eq("is_active", True).not_.is_("law_article", "null").execute()

    # 모법만 필터 + 조문번호 추출 + 그룹핑
    groups = {}  # key: "법령명|조문번호" → {"law_name", "article_no", "rule_ids": []}
    for row in (rows.data or []):
        law_name = row.get("law_name", "")
        law_article = row.get("law_article", "")

        # 시행령/시행규칙/NFTC 등 제외
        if any(p in law_name for p in _CHILD_LAW_PATTERNS):
            continue

        # 조문번호 추출: "제38조" → "38", "제527조압력계" → "527"
        m = re.match(r"제(\d+)조", law_article)
        if not m:
            continue
        article_no = m.group(1)

        key = f"{law_name}|{article_no}"
        if key not in groups:
            groups[key] = {
                "law_name": law_name,
                "article_no": article_no,
                "search_query": f"{law_name} 제{article_no}조",
                "rule_ids": [],
            }
        groups[key]["rule_ids"].append(row["rule_id"])

    # rule_ids 중복 제거
    result = []
    for g in groups.values():
        g["rule_ids"] = list(set(g["rule_ids"]))
        g["rule_count"] = len(g["rule_ids"])
        result.append(g)

    # rule_count 많은 순 정렬
    result.sort(key=lambda x: x["rule_count"], reverse=True)

    return {
        "status": "success",
        "total_keys": len(result),
        "keys": result,
    }


# ── POST /precedents/save-matched ─────────────────────────

@router.post("/save-matched")
async def save_matched_precedent(body: dict):
    """판례 저장 + rule_ids 즉시 연결.
    수집 = 매칭. 매칭 안 되는 데이터는 저장 안 함.
    """
    secret = body.get("secret", "")
    if secret != INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="내부 전용")

    prec = body.get("precedent", {})
    rule_ids = body.get("rule_ids", [])

    if not prec.get("prec_seq"):
        raise HTTPException(status_code=400, detail="prec_seq 필수")
    if not rule_ids:
        raise HTTPException(status_code=400, detail="rule_ids 필수 (매칭 없는 판례는 저장 안 함)")

    sb = get_supabase()
    now_iso = datetime.now(timezone.utc).isoformat()

    # 1. 판례 upsert (prec_seq 기준)
    existing = sb.table("industrial_accident_precedents").select(
        "id"
    ).eq("prec_seq", prec["prec_seq"]).execute()

    prec_id = None
    if existing.data:
        prec_id = existing.data[0]["id"]
        update_data = {k: v for k, v in prec.items() if v is not None and k != "prec_seq"}
        update_data["updated_at"] = now_iso
        sb.table("industrial_accident_precedents").update(
            update_data
        ).eq("prec_seq", prec["prec_seq"]).execute()
        action = "updated"
    else:
        prec["created_at"] = now_iso
        prec["updated_at"] = now_iso
        ins = sb.table("industrial_accident_precedents").insert(prec).execute()
        if ins.data:
            prec_id = ins.data[0]["id"]
        action = "inserted"

    # 2. rule_ids 연결 (precedent_rule_links)
    links_created = 0
    if prec_id:
        for rule_id in rule_ids:
            try:
                # 중복 체크 (UNIQUE constraint)
                sb.table("precedent_rule_links").upsert({
                    "precedent_id": prec_id,
                    "rule_id": rule_id,
                    "relevance_score": 90,
                    "link_type": "violation",
                    "created_at": now_iso,
                }, on_conflict="precedent_id,rule_id").execute()
                links_created += 1
            except Exception as e:
                log.warning(f"[PREC] rule link 실패 ({rule_id}): {e}")

    return {
        "status": "success",
        "action": action,
        "prec_seq": prec["prec_seq"],
        "links_created": links_created,
    }


# ── GET /precedents/search ──────────────────────────────────

@router.get("/search")
def search_precedents(
    query: str = Query(...),
    sector: Optional[str] = Query(None),
    year: Optional[int] = Query(None),
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
        raise HTTPException(status_code=404, detail=f"판례를 찾을 수 없습니다.")
    return {"status": "success", "data": res.data[0]}


# ── POST /precedents/collect + /sync ────────────────────────

@router.post("/collect")
async def collect_precedents(body: dict = None):
    return await _call_collect_edge()

@router.post("/sync")
async def sync_precedents():
    return await _call_collect_edge()

async def _call_collect_edge() -> dict:
    secret = os.environ.get("TAI_COLLECT_SECRET", "")
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["x-tai-secret"] = secret
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(EDGE_COLLECT_URL, headers=headers, json={})
        if resp.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"Edge Function 오류: {resp.status_code}")
        return resp.json()
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        raise HTTPException(status_code=503, detail=f"Edge Function 연결 실패: {type(e).__name__}")
