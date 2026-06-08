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
# POST /process-management
# 공정 신규 등록
# ──────────────────────────────────────────────
@router.post("")
async def create_process(body: dict):
    supabase = get_supabase()
    try:
        process_lv1 = (body.get("process_lv1") or "").strip()
        process_lv4 = (body.get("process_lv4") or "").strip()

        if not process_lv1:
            raise HTTPException(status_code=400, detail="산업분류(process_lv1)는 필수입니다.")
        if not process_lv4:
            raise HTTPException(status_code=400, detail="공정명(process_lv4)는 필수입니다.")

        import time
        new_process_id = f"ADMIN-{int(time.time())}"

        lv2 = (body.get("process_lv2") or "").strip()
        lv3 = (body.get("process_lv3") or "").strip()
        parts = [p for p in [process_lv1, lv2, lv3, process_lv4] if p]
        process_path = ">".join(parts)
        industry_code = (body.get("industry_code_full") or "").strip()

        insert_data = {
            "process_id":         new_process_id,
            "process_lv1":        process_lv1,
            "process_lv2":        lv2,
            "process_lv3":        lv3,
            "process_lv4":        process_lv4,
            "process_path":       process_path,
            "process_source":     body.get("process_source", "MANUAL"),
            "industry_code_full": industry_code if industry_code else None,
            "review_flag":        False,
            "mapping_basis":      body.get("mapping_basis", "ADMIN_MANUAL"),
        }

        res = supabase.table("ksic_process_map").insert(insert_data).execute()

        if not res.data:
            raise HTTPException(status_code=500, detail="공정 등록에 실패했습니다.")

        return {
            "status": "success",
            "message": "공정이 등록됐습니다.",
            "data": {
                **res.data[0],
                "process_name": process_lv4
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
# 공정 연결 설비 목록 (process_equipment_map 테이블 직접 조회)
# ──────────────────────────────────────────────
@router.get("/{process_id}/equipments")
async def get_process_equipments(
    process_id: str,
    match_band: Optional[str] = None,
    page: int = 1,
    page_size: int = 50
):
    supabase = get_supabase()
    try:
        query = supabase.table("process_equipment_map").select(
            "facility_name_std, match_band, match_score, source_type, equipment_role, category_path"
        ).eq("process_id", process_id)

        if match_band:
            query = query.eq("match_band", match_band.upper())

        res = query.execute()
        rows = res.data or []

        # DISTINCT ON facility_name_std (Python에서 처리)
        seen = {}
        for row in rows:
            key = row.get("facility_name_std")
            if key not in seen:
                seen[key] = row
        items = list(seen.values())

        # match_band 정렬: MUST > CORE > OPTIONAL > REFERENCE
        band_order = {"MUST": 0, "CORE": 1, "OPTIONAL": 2, "REFERENCE": 3}
        items.sort(key=lambda x: band_order.get(x.get("match_band", ""), 99))

        total = len(items)
        start = (page - 1) * page_size
        paged = items[start:start + page_size]

        summary = {"MUST": 0, "CORE": 0, "OPTIONAL": 0, "REFERENCE": 0}
        for item in items:
            band = item.get("match_band", "")
            if band in summary:
                summary[band] += 1

        return {
            "status": "success",
            "data": {
                "process_id": process_id,
                "items": paged,
                "total": total,
                "summary": {k.lower(): v for k, v in summary.items()},
                "page": page,
                "page_size": page_size
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────
# GET /process-management/{process_id}/factories
# 이 공정을 등록한 시설 목록
# ──────────────────────────────────────────────
@router.get("/{process_id}/factories")
async def get_process_factories(process_id: str):
    supabase = get_supabase()
    try:
        res = supabase.table("factory_process").select(
            "id, factory_id, is_primary, is_active, created_at, "
            "factories!inner(id, name, site_code, ksic_code, ksic_name, address_road)"
        ).eq("process_id", process_id).eq("is_active", True).execute()

        rows = res.data or []
        items = []
        for row in rows:
            f = row.get("factories") or {}
            items.append({
                "factory_process_id": row.get("id"),
                "factory_id": row.get("factory_id"),
                "factory_name": f.get("name"),
                "site_code": f.get("site_code"),
                "ksic_code": f.get("ksic_code"),
                "ksic_name": f.get("ksic_name"),
                "address": f.get("address_road"),
                "is_primary": row.get("is_primary"),
                "registered_at": row.get("created_at")
            })

        return {
            "status": "success",
            "data": {
                "process_id": process_id,
                "items": items,
                "total": len(items)
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────
# PATCH /process-management/{process_id}
# 공정 마스터 수정 (설명, 활성/비활성)
# ──────────────────────────────────────────────
@router.patch("/{process_id}")
async def update_process(process_id: str, body: dict):
    supabase = get_supabase()

    allowed = {
        "process_lv1",
        "process_lv2",
        "process_lv3",
        "process_lv4",
        "process_source",
        "industry_code_full",
        "review_flag",
        "mapping_basis",
    }
    update_data = {k: v for k, v in body.items() if k in allowed}

    if not update_data:
        raise HTTPException(status_code=400, detail="수정할 필드가 없습니다.")

    res = supabase.table("ksic_process_map").update(update_data).eq(
        "process_id", process_id
    ).execute()

    return {
        "status": "success",
        "message": "공정이 수정됐습니다.",
        "updated_count": len(res.data or [])
    }


# ──────────────────────────────────────────────
# DELETE /process-management/{process_id}
# 공정 삭제 (factory_process 비활성화 + ksic_process_map 삭제)
# ──────────────────────────────────────────────
@router.delete("/{process_id}")
async def delete_process(process_id: str):
    supabase = get_supabase()
    try:
        supabase.table("factory_process").update({"is_active": False}).eq(
            "process_id", process_id
        ).execute()

        res = supabase.table("ksic_process_map").delete().eq(
            "process_id", process_id
        ).execute()

        return {
            "status": "success",
            "message": f"공정 {process_id} 삭제 완료",
            "deleted_count": len(res.data or [])
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
