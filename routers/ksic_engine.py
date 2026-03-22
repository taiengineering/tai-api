"""
KSIC 엔진 v3 추가 엔드포인트
기존 ksic_engine.py 파일에 아래 라우터들을 추가하세요.
prefix="/ksic-engine" 이미 등록되어 있음.

신규:
  GET /ksic-engine/hierarchy          — lv1 전체 목록
  GET /ksic-engine/hierarchy/lv2      — lv1 선택 후 lv2 목록
  GET /ksic-engine/hierarchy/lv3      — lv2 선택 후 lv3 목록
  GET /ksic-engine/hierarchy/lv4      — lv3 선택 후 lv4(업종코드) 목록
"""
from fastapi import APIRouter, Query
from typing import Optional
import os
from supabase import create_client

router = APIRouter(prefix="/ksic-engine", tags=["KSIC엔진"])

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ──────────────────────────────────────────────
# GET /ksic-engine/hierarchy
# lv1 목록 전체 (셀렉트바 대분류용)
# ──────────────────────────────────────────────
@router.get("/hierarchy")
async def get_ksic_lv1():
    """KSIC 대분류(lv1) 전체 목록 - 4단계 셀렉트 첫 번째"""
    supabase = get_supabase()
    res = supabase.table("industry_master").select(
        "lv1_code, lv1_name"
    ).eq("is_active", True).execute()

    # 중복 제거 + 정렬
    seen = set()
    items = []
    for row in (res.data or []):
        key = row["lv1_code"]
        if key and key not in seen:
            seen.add(key)
            items.append({
                "code": key,
                "name": row["lv1_name"] or "",
            })

    items.sort(key=lambda x: x["code"])

    return {
        "status": "success",
        "data": {"level": 1, "items": items, "total": len(items)}
    }


# ──────────────────────────────────────────────
# GET /ksic-engine/hierarchy/lv2?lv1={code}
# lv2 목록 (lv1 선택 후 중분류용)
# ──────────────────────────────────────────────
@router.get("/hierarchy/lv2")
async def get_ksic_lv2(lv1: str = Query(..., description="lv1 코드")):
    """KSIC 중분류(lv2) 목록 - 대분류 선택 후"""
    supabase = get_supabase()
    res = supabase.table("industry_master").select(
        "lv2_code, lv2_name"
    ).eq("lv1_code", lv1).eq("is_active", True).execute()

    seen = set()
    items = []
    for row in (res.data or []):
        key = row["lv2_code"]
        if key and key not in seen:
            seen.add(key)
            items.append({
                "code": key,
                "name": row["lv2_name"] or "",
            })

    items.sort(key=lambda x: x["code"])

    return {
        "status": "success",
        "data": {"level": 2, "parent_code": lv1, "items": items, "total": len(items)}
    }


# ──────────────────────────────────────────────
# GET /ksic-engine/hierarchy/lv3?lv2={code}
# lv3 목록 (lv2 선택 후 소분류용)
# ──────────────────────────────────────────────
@router.get("/hierarchy/lv3")
async def get_ksic_lv3(lv2: str = Query(..., description="lv2 코드")):
    """KSIC 소분류(lv3) 목록 - 중분류 선택 후"""
    supabase = get_supabase()
    res = supabase.table("industry_master").select(
        "lv3_code, lv3_name"
    ).eq("lv2_code", lv2).eq("is_active", True).execute()

    seen = set()
    items = []
    for row in (res.data or []):
        key = row["lv3_code"]
        if key and key not in seen:
            seen.add(key)
            items.append({
                "code": key,
                "name": row["lv3_name"] or "",
            })

    items.sort(key=lambda x: x["code"])

    return {
        "status": "success",
        "data": {"level": 3, "parent_code": lv2, "items": items, "total": len(items)}
    }


# ──────────────────────────────────────────────
# GET /ksic-engine/hierarchy/lv4?lv3={code}
# lv4 목록 (lv3 선택 후 세세분류/업종코드용)
# ──────────────────────────────────────────────
@router.get("/hierarchy/lv4")
async def get_ksic_lv4(lv3: str = Query(..., description="lv3 코드")):
    """KSIC 세분류(lv4/업종코드) 목록 - 소분류 선택 후"""
    supabase = get_supabase()
    res = supabase.table("industry_master").select(
        "industry_code_full, industry_name_full, industry_path_ko"
    ).eq("lv3_code", lv3).eq("is_active", True).execute()

    items = []
    for row in (res.data or []):
        if row.get("industry_code_full"):
            items.append({
                "code": row["industry_code_full"],
                "name": row["industry_name_full"] or "",
                "path": row["industry_path_ko"] or "",
            })

    items.sort(key=lambda x: x["code"])

    return {
        "status": "success",
        "data": {"level": 4, "parent_code": lv3, "items": items, "total": len(items)}
    }


# ──────────────────────────────────────────────
# GET /ksic-engine/process-search?ksic={code}&lv1={lv1}&lv2={lv2}&lv3={lv3}
# KSIC 코드 기반 공정 목록 (v_process_unified)
# 셀렉트바 각 단계별 공정 필터링용
# ──────────────────────────────────────────────
@router.get("/process-search")
async def search_processes_by_ksic(
    ksic: Optional[str] = Query(None, description="KSIC 4자리 업종코드"),
    lv1: Optional[str] = Query(None, description="공정 대분류 (lv1)"),
    lv2: Optional[str] = Query(None, description="공정 중분류 (lv2)"),
    lv3: Optional[str] = Query(None, description="공정 소분류 (lv3)"),
    source: Optional[str] = Query(None, description="소스 필터: KOSHA_GUIDE/TAI_EXISTING/TEMPLATE"),
    limit: int = Query(200, ge=1, le=1000),
):
    """
    KSIC 코드 기반 공정 목록 조회 (v_process_unified)
    4단계 셀렉트바에서 각 단계별로 호출:
    - ksic만 → 해당 업종의 lv1 목록
    - ksic + lv1 → 해당 lv1의 lv2 목록
    - ksic + lv1 + lv2 → 해당 lv2의 lv3 목록
    - ksic + lv1 + lv2 + lv3 → 공정명 목록
    """
    supabase = get_supabase()

    query = supabase.table("v_process_unified").select(
        "id, process_id, industry_code_full, industry_name_full, "
        "process_lv1, process_lv2, process_lv3, process_lv4, "
        "process_path, process_source, source_priority"
    )

    if ksic:
        query = query.eq("industry_code_full", ksic)
    if lv1:
        query = query.eq("process_lv1", lv1)
    if lv2:
        query = query.eq("process_lv2", lv2)
    if lv3:
        query = query.eq("process_lv3", lv3)
    if source:
        query = query.eq("process_source", source)

    query = query.order("source_priority").order("process_lv1").order("process_lv2").order("process_lv3")
    query = query.limit(limit)

    res = query.execute()
    items = res.data or []

    # 단계별 unique 목록 추출
    lv1_set = sorted(set(r["process_lv1"] for r in items if r.get("process_lv1")))
    lv2_set = sorted(set(r["process_lv2"] for r in items if r.get("process_lv2")))
    lv3_set = sorted(set(r["process_lv3"] for r in items if r.get("process_lv3")))

    source_badge = {
        "KOSHA_GUIDE": "KOSHA", "KOSHA_GUIDE_V2": "KOSHA",
        "TAI_EXISTING": "TAI", "TEMPLATE": "TEMPLATE"
    }

    result_items = []
    for row in items:
        result_items.append({
            **row,
            "process_name": row.get("process_lv4") or row.get("process_lv3", ""),
            "source_badge": source_badge.get(row.get("process_source", ""), ""),
            "is_kosha": row.get("process_source", "").startswith("KOSHA"),
        })

    return {
        "status": "success",
        "data": {
            "ksic_code": ksic,
            "items": result_items,
            "total": len(result_items),
            "hierarchy": {
                "lv1_options": lv1_set,
                "lv2_options": lv2_set,
                "lv3_options": lv3_set,
            }
        }
    }
