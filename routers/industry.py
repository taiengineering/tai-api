"""
산업분류(KSIC) 검색 라우터 — v1.0.0
  GET /industry/search?q=&lv1=&size=   KSIC 검색 (자동완성용)
  GET /industry/lv1                    대분류 목록
  GET /industry/lv2?lv1_code=          중분류 목록
  GET /industry/lv3?lv2_code=          소분류 목록
"""
from fastapi import APIRouter, Query
from typing import Optional
import os
from supabase import create_client

router = APIRouter(prefix="/industry", tags=["industry"])

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ── GET /industry/search ─────────────────────────────────
@router.get("/search")
async def search_industry(
    q:    Optional[str] = Query(None, description="검색어 (업종명)"),
    lv1:  Optional[str] = Query(None, description="대분류 코드 필터"),
    size: int = Query(30, ge=1, le=100),
):
    """
    industry_name_full ILIKE 검색.
    q 없으면 전체 목록 (lv1 필터 적용).
    """
    supabase = get_supabase()
    query = supabase.table("industry_master").select(
        "industry_code_full, industry_name_full, "
        "lv1_code, lv1_name, lv2_code, lv2_name, "
        "lv3_code, lv3_name, lv4_code, lv4_name, "
        "industry_path_ko"
    ).eq("is_active", True)

    if q and q.strip():
        query = query.ilike("industry_name_full", f"%{q.strip()}%")
    if lv1:
        query = query.eq("lv1_code", lv1)

    query = query.order("lv1_code").order("lv2_code").order("industry_code_full")
    res = query.limit(size).execute()
    items = res.data or []

    return {
        "status": "success",
        "data": {
            "q": q,
            "items": [
                {
                    "code":  row["industry_code_full"],
                    "name":  row["industry_name_full"],
                    "path":  row.get("industry_path_ko") or " > ".join(filter(None, [
                                 row.get("lv1_name", "").split("(")[0].strip(),
                                 row.get("lv2_name", ""),
                                 row.get("lv3_name", ""),
                                 row.get("lv4_name", "") if row.get("lv4_name") != row.get("industry_name_full") else "",
                             ])),
                    "lv1_code": row.get("lv1_code"),
                    "lv1_name": row.get("lv1_name", "").split("(")[0].strip(),
                    "lv2_code": row.get("lv2_code"),
                    "lv2_name": row.get("lv2_name"),
                }
                for row in items
            ],
            "total": len(items),
        }
    }


# ── GET /industry/lv1 ────────────────────────────────────
@router.get("/lv1")
async def get_lv1():
    """대분류 목록"""
    supabase = get_supabase()
    res = supabase.table("industry_master").select(
        "lv1_code, lv1_name"
    ).eq("is_active", True).order("lv1_code").execute()

    seen, items = set(), []
    for row in (res.data or []):
        k = row["lv1_code"]
        if k not in seen:
            seen.add(k)
            items.append({
                "code": k,
                "name": row["lv1_name"].split("(")[0].strip(),
                "name_full": row["lv1_name"],
            })

    return {"status": "success", "data": {"items": items}}


# ── GET /industry/lv2 ────────────────────────────────────
@router.get("/lv2")
async def get_lv2(lv1_code: str = Query(...)):
    """중분류 목록 (대분류 코드 기준)"""
    supabase = get_supabase()
    res = supabase.table("industry_master").select(
        "lv2_code, lv2_name"
    ).eq("is_active", True).eq("lv1_code", lv1_code).order("lv2_code").execute()

    seen, items = set(), []
    for row in (res.data or []):
        k = row["lv2_code"]
        if k and k not in seen:
            seen.add(k)
            items.append({"code": k, "name": row["lv2_name"]})

    return {"status": "success", "data": {"items": items}}


# ── GET /industry/lv3 ────────────────────────────────────
@router.get("/lv3")
async def get_lv3(lv2_code: str = Query(...)):
    """소분류(최종) 목록 (중분류 코드 기준)"""
    supabase = get_supabase()
    res = supabase.table("industry_master").select(
        "industry_code_full, industry_name_full, lv3_code, lv3_name, lv4_code, lv4_name"
    ).eq("is_active", True).eq("lv2_code", lv2_code).order("industry_code_full").execute()

    items = [
        {
            "code": row["industry_code_full"],
            "name": row["industry_name_full"],
            "lv3_code": row.get("lv3_code"),
            "lv3_name": row.get("lv3_name"),
        }
        for row in (res.data or [])
    ]

    return {"status": "success", "data": {"items": items}}
