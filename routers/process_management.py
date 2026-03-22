"""
공정 마스터 관리 라우터 — v1.0.0
v_process_unified / v_equipment_unified 뷰 기반
Admin 전용 공정 마스터 CRUD + 시설별 공정 현황 집계
"""
from fastapi import APIRouter, Query, HTTPException
from typing import Optional
from datetime import datetime
import os
from supabase import create_client

router = APIRouter(prefix="/process-management", tags=["process-management"])

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ──────────────────────────────────────────────
# GET /process-management
# 공정 마스터 목록 (v_process_unified 기반, 필터/페이지네이션)
# ──────────────────────────────────────────────
@router.get("")
async def get_process_list(
    search: Optional[str] = Query(None, description="공정명/경로 검색"),
    industry_code: Optional[str] = Query(None, description="KSIC 업종코드 (4자리)"),
    lv1: Optional[str] = Query(None, description="산업 대분류 lv1"),
    source: Optional[str] = Query(None, description="소스: KOSHA_GUIDE/TAI_EXISTING/TEMPLATE"),
    priority: Optional[str] = Query(None, description="우선순위: MUST/CORE/OPTIONAL/REFERENCE"),
    is_active: Optional[bool] = Query(None, description="활성 여부"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: Optional[str] = Query("process_path", description="정렬 기준"),
    sort_order: Optional[str] = Query("asc", description="asc/desc"),
):
    supabase = get_supabase()
    offset = (page - 1) * page_size

    # v_process_unified에서 조회 (equipment 수는 서브쿼리로)
    query = supabase.table("v_process_unified").select(
        "id, industry_code_full, industry_name_full, process_id, "
        "process_lv1, process_lv2, process_lv3, process_lv4, process_path, "
        "process_source, source_priority, mapping_basis, created_at",
        count="exact"
    )

    if search:
        query = query.or_(
            f"process_path.ilike.%{search}%,"
            f"process_lv4.ilike.%{search}%,"
            f"process_lv3.ilike.%{search}%"
        )
    if industry_code:
        query = query.eq("industry_code_full", industry_code)
    if lv1:
        query = query.eq("process_lv1", lv1)
    if source:
        query = query.eq("process_source", source)

    # 정렬
    asc_flag = sort_order.lower() != "desc"
    valid_sorts = ["process_path", "process_lv1", "industry_code_full", "created_at", "source_priority"]
    sort_col = sort_by if sort_by in valid_sorts else "process_path"
    query = query.order(sort_col, desc=not asc_flag)

    query = query.range(offset, offset + page_size - 1)
    res = query.execute()

    items = res.data or []
    total = res.count or 0

    # 소스별 배지 텍스트
    source_badge = {"KOSHA_GUIDE": "KOSHA", "TAI_EXISTING": "TAI", "TEMPLATE": "TEMPLATE"}

    # 각 공정의 연결 설비 수 조회 (배치)
    process_ids = list(set(row["process_id"] for row in items))
    equip_counts = {}
    if process_ids:
        # v_equipment_unified에서 process_id 기준 count
        eq_res = supabase.rpc(
            "get_equip_count_by_process",
            {"p_process_ids": process_ids}
        ).execute()
        if eq_res.data:
            for row in eq_res.data:
                equip_counts[row["process_id"]] = row["equip_count"]

    result = []
    for row in items:
        result.append({
            **row,
            "process_name": row.get("process_lv4") or row.get("process_lv3", ""),
            "source_badge": source_badge.get(row.get("process_source", ""), ""),
            "equip_count": equip_counts.get(row["process_id"], 0),
        })

    return {
        "status": "success",
        "data": {
            "items": result,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
        }
    }


# ──────────────────────────────────────────────
# GET /process-management/lv1-list
# 산업 대분류(lv1) 목록 (필터 드롭다운용)
# ──────────────────────────────────────────────
@router.get("/lv1-list")
async def get_process_lv1_list():
    supabase = get_supabase()
    res = supabase.table("v_process_unified").select(
        "process_lv1"
    ).execute()

    lv1_set = sorted(set(row["process_lv1"] for row in (res.data or []) if row.get("process_lv1")))
    return {"status": "success", "data": lv1_set}


# ──────────────────────────────────────────────
# GET /process-management/{process_id}
# 공정 마스터 상세
# ──────────────────────────────────────────────
@router.get("/{process_id}")
async def get_process_detail(process_id: str):
    supabase = get_supabase()

    # v_process_unified에서 조회
    res = supabase.table("v_process_unified").select("*").eq("process_id", process_id).execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="공정을 찾을 수 없습니다.")

    # 여러 업종에 같은 process_id 있을 수 있으므로 첫번째 + 업종 목록
    row = res.data[0]
    industry_codes = list(set(r["industry_code_full"] for r in res.data))

    # 원본 ksic_process_map에서 설명/활성 여부 조회
    orig = supabase.table("ksic_process_map").select(
        "review_flag, mapping_basis"
    ).eq("process_id", process_id).limit(1).execute()

    orig_data = orig.data[0] if orig.data else {}

    return {
        "status": "success",
        "data": {
            **row,
            "process_name": row.get("process_lv4") or row.get("process_lv3", ""),
            "industry_codes": industry_codes,
            "review_flag": orig_data.get("review_flag", False),
            "mapping_basis": orig_data.get("mapping_basis", ""),
        }
    }


# ──────────────────────────────────────────────
# GET /process-management/{process_id}/equipments
# 공정 연결 설비 목록 (v_equipment_unified 기반)
# ──────────────────────────────────────────────
@router.get("/{process_id}/equipments")
async def get_process_equipments(
    process_id: str,
    industry_code: Optional[str] = Query(None),
    match_band: Optional[str] = Query(None, description="MUST/CORE/OPTIONAL"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    supabase = get_supabase()
    offset = (page - 1) * page_size

    query = supabase.table("v_equipment_unified").select(
        "id, industry_code_full, industry_name_full, process_id, "
        "facility_name_std, match_band, match_score, match_basis, "
        "source_type, source_priority",
        count="exact"
    ).eq("process_id", process_id)

    if industry_code:
        query = query.eq("industry_code_full", industry_code)
    if match_band:
        query = query.eq("match_band", match_band)

    query = query.order("source_priority").order("match_band")
    query = query.range(offset, offset + page_size - 1)

    res = query.execute()
    items = res.data or []
    total = res.count or 0

    return {
        "status": "success",
        "data": {
            "process_id": process_id,
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    }


# ──────────────────────────────────────────────
# GET /process-management/{process_id}/factories
# 이 공정을 등록한 시설 목록
# ──────────────────────────────────────────────
@router.get("/{process_id}/factories")
async def get_process_factories(process_id: str):
    supabase = get_supabase()

    res = supabase.table("factory_process").select(
        "id, factory_id, is_primary, is_active, created_at, "
        "factories!inner(id, factory_name, company_id, ksic_code, ksic_name, "
        "companies!inner(id, company_name))"
    ).eq("process_id", process_id).eq("is_active", True).execute()

    items = []
    for row in (res.data or []):
        f = row.get("factories", {})
        c = f.get("companies", {})
        items.append({
            "factory_process_id": row["id"],
            "factory_id": row["factory_id"],
            "factory_name": f.get("factory_name", ""),
            "company_name": c.get("company_name", ""),
            "ksic_code": f.get("ksic_code", ""),
            "ksic_name": f.get("ksic_name", ""),
            "is_primary": row.get("is_primary", False),
            "registered_at": row.get("created_at", ""),
        })

    return {
        "status": "success",
        "data": {
            "process_id": process_id,
            "items": items,
            "total": len(items),
        }
    }


# ──────────────────────────────────────────────
# PATCH /process-management/{process_id}
# 공정 마스터 수정 (설명, 활성/비활성)
# ──────────────────────────────────────────────
@router.patch("/{process_id}")
async def update_process(process_id: str, body: dict):
    supabase = get_supabase()

    allowed = {"review_flag", "mapping_basis"}
    update_data = {k: v for k, v in body.items() if k in allowed}

    if not update_data:
        raise HTTPException(status_code=400, detail="수정할 항목이 없습니다.")

    res = supabase.table("ksic_process_map").update(update_data).eq(
        "process_id", process_id
    ).execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="공정을 찾을 수 없습니다.")

    return {"status": "success", "message": "공정이 수정됐습니다.", "updated_count": len(res.data)}
