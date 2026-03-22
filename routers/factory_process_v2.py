"""
시설 공정 관리 라우터 — v2.0.0
v_process_unified 기반 recommend-processes 수정
+ factory-process/overview 신규 추가
+ PATCH is_primary 신규 추가
"""
from fastapi import APIRouter, Query, HTTPException
from typing import Optional
import os
from supabase import create_client

router = APIRouter(prefix="/factory-process", tags=["factory-process"])

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

MATCH_BAND_ORDER = {"MUST": 1, "CORE": 2, "OPTIONAL": 3, "REFERENCE": 4}
SOURCE_BADGE = {"KOSHA_GUIDE": "KOSHA", "TAI_EXISTING": "TAI", "TEMPLATE": "TEMPLATE"}
SOURCE_PRIORITY = {"KOSHA_GUIDE": 1, "TAI_EXISTING": 2, "TEMPLATE": 3}


def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ──────────────────────────────────────────────
# GET /factory-process/overview
# 시설별 공정 현황 집계 (Admin 탭2)
# ⚠️ /overview 가 /{factory_id} 보다 먼저 선언되어야 함
# ──────────────────────────────────────────────
@router.get("/overview")
async def get_factory_process_overview(
    search: Optional[str] = Query(None, description="시설명/회사명 검색"),
    has_process: Optional[bool] = Query(None, description="공정 등록 여부 필터"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    supabase = get_supabase()
    offset = (page - 1) * page_size

    # factories 테이블에서 조회 + company join
    fac_query = supabase.table("factories").select(
        "id, factory_name, ksic_code, ksic_name, "
        "companies!inner(company_name)",
        count="exact"
    )

    if search:
        fac_query = fac_query.or_(f"factory_name.ilike.%{search}%")

    fac_query = fac_query.order("factory_name").range(offset, offset + page_size - 1)
    fac_res = fac_query.execute()
    factories = fac_res.data or []
    total = fac_res.count or 0

    if not factories:
        return {
            "status": "success",
            "data": {"items": [], "total": 0, "page": page, "page_size": page_size}
        }

    factory_ids = [f["id"] for f in factories]

    # 시설별 공정 수 집계
    proc_res = supabase.table("factory_process").select(
        "factory_id, process_id, is_primary"
    ).in_("factory_id", factory_ids).eq("is_active", True).execute()

    proc_map = {}
    for row in (proc_res.data or []):
        fid = row["factory_id"]
        if fid not in proc_map:
            proc_map[fid] = {"total": 0, "primary_count": 0, "last_added": None}
        proc_map[fid]["total"] += 1
        if row.get("is_primary"):
            proc_map[fid]["primary_count"] += 1

    items = []
    for f in factories:
        fid = f["id"]
        p = proc_map.get(fid, {"total": 0, "primary_count": 0})
        process_count = p["total"]

        # has_process 필터 적용
        if has_process is True and process_count == 0:
            continue
        if has_process is False and process_count > 0:
            continue

        items.append({
            "factory_id": fid,
            "factory_name": f.get("factory_name", ""),
            "company_name": (f.get("companies") or {}).get("company_name", ""),
            "ksic_code": f.get("ksic_code", ""),
            "ksic_name": f.get("ksic_name", ""),
            "process_count": process_count,
            "primary_count": p["primary_count"],
            "has_process": process_count > 0,
            "status_badge": "등록" if process_count > 0 else "미등록",
        })

    return {
        "status": "success",
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
        }
    }


# ──────────────────────────────────────────────
# GET /factory-process/{factory_id}/processes
# 시설에 등록된 공정 목록
# ──────────────────────────────────────────────
@router.get("/{factory_id}/processes")
async def get_factory_processes(factory_id: str):
    supabase = get_supabase()

    res = supabase.table("factory_process").select("*").eq(
        "factory_id", factory_id
    ).eq("is_active", True).execute()

    items = res.data or []

    # v_process_unified에서 소스 정보 보강
    process_ids = list(set(r["process_id"] for r in items))
    source_map = {}
    if process_ids:
        pres = supabase.table("v_process_unified").select(
            "process_id, process_source, source_priority"
        ).in_("process_id", process_ids).execute()
        for row in (pres.data or []):
            source_map[row["process_id"]] = {
                "process_source": row.get("process_source", ""),
                "source_priority": row.get("source_priority", 9),
            }

    result = []
    for row in items:
        s = source_map.get(row["process_id"], {})
        result.append({
            **row,
            "process_name": row.get("process_lv4") or row.get("process_lv3", ""),
            "process_source": s.get("process_source", ""),
            "source_badge": SOURCE_BADGE.get(s.get("process_source", ""), ""),
        })

    # MUST > CORE > OPTIONAL 정렬 없이 등록 순
    return {
        "status": "success",
        "data": {
            "factory_id": factory_id,
            "items": result,
            "total": len(result),
        }
    }


# ──────────────────────────────────────────────
# GET /factory-process/{factory_id}/recommend-processes
# KSIC 기반 추천 공정 목록 — v_process_unified 기반 v2
# ──────────────────────────────────────────────
@router.get("/{factory_id}/recommend-processes")
async def recommend_processes(
    factory_id: str,
    match_band: Optional[str] = Query(None, description="MUST/CORE/OPTIONAL"),
    source: Optional[str] = Query(None, description="소스 필터"),
    limit: int = Query(100, ge=1, le=500),
):
    supabase = get_supabase()

    # 1. 시설의 KSIC 코드 조회
    fac_res = supabase.table("factories").select(
        "id, factory_name, ksic_code, ksic_name"
    ).eq("id", factory_id).single().execute()

    if not fac_res.data:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다.")

    factory = fac_res.data
    ksic_code = factory.get("ksic_code")

    if not ksic_code:
        return {
            "status": "success",
            "message": "KSIC 업종 코드가 설정되지 않았습니다. 업종을 먼저 설정해주세요.",
            "data": {
                "factory_id": factory_id,
                "ksic_code": None,
                "items": [],
                "total": 0,
            }
        }

    # 2. v_process_unified에서 해당 KSIC 공정 조회 (우선순위 정렬)
    proc_query = supabase.table("v_process_unified").select(
        "id, process_id, industry_code_full, industry_name_full, "
        "process_lv1, process_lv2, process_lv3, process_lv4, process_path, "
        "process_source, source_priority, mapping_basis"
    ).eq("industry_code_full", ksic_code)

    if source:
        proc_query = proc_query.eq("process_source", source)

    proc_query = proc_query.order("source_priority").order("process_lv1").order("process_lv2")
    proc_query = proc_query.limit(limit)
    proc_res = proc_query.execute()
    all_processes = proc_res.data or []

    # 3. 이미 등록된 공정 ID 조회
    reg_res = supabase.table("factory_process").select("process_id").eq(
        "factory_id", factory_id
    ).eq("is_active", True).execute()
    registered_ids = set(r["process_id"] for r in (reg_res.data or []))

    # 4. 각 공정의 MUST 설비 수 조회 (v_equipment_unified 기반)
    process_ids = list(set(r["process_id"] for r in all_processes))
    must_equip_map = {}
    if process_ids:
        eq_res = supabase.table("v_equipment_unified").select(
            "process_id, facility_name_std, match_band"
        ).in_("process_id", process_ids).in_("match_band", ["MUST", "CORE"]).execute()

        for row in (eq_res.data or []):
            pid = row["process_id"]
            if pid not in must_equip_map:
                must_equip_map[pid] = {"MUST": [], "CORE": []}
            band = row["match_band"]
            if band in must_equip_map[pid]:
                if row["facility_name_std"] not in must_equip_map[pid][band]:
                    must_equip_map[pid][band].append(row["facility_name_std"])

    # 5. 결과 구성
    items = []
    for row in all_processes:
        pid = row["process_id"]
        equip_info = must_equip_map.get(pid, {"MUST": [], "CORE": []})

        # match_band 필터 (설비 기준)
        if match_band == "MUST" and not equip_info["MUST"]:
            continue

        is_registered = pid in registered_ids
        source_val = row.get("process_source", "")

        items.append({
            **row,
            "process_name": row.get("process_lv4") or row.get("process_lv3", ""),
            "source_badge": SOURCE_BADGE.get(source_val, ""),
            "is_kosha": source_val == "KOSHA_GUIDE",
            "is_registered": is_registered,
            "must_equipments": equip_info["MUST"][:5],
            "core_equipments": equip_info["CORE"][:5],
            "must_count": len(equip_info["MUST"]),
            "core_count": len(equip_info["CORE"]),
        })

    return {
        "status": "success",
        "data": {
            "factory_id": factory_id,
            "factory_name": factory.get("factory_name", ""),
            "ksic_code": ksic_code,
            "ksic_name": factory.get("ksic_name", ""),
            "items": items,
            "total": len(items),
            "registered_count": len(registered_ids),
            "recommended_count": len(items),
        }
    }


# ──────────────────────────────────────────────
# POST /factory-process/{factory_id}/processes
# 공정 추가 등록
# ──────────────────────────────────────────────
@router.post("/{factory_id}/processes")
async def add_factory_process(factory_id: str, body: dict):
    supabase = get_supabase()

    process_id = body.get("process_id")
    if not process_id:
        raise HTTPException(status_code=400, detail="process_id가 필요합니다.")

    # 중복 체크
    existing = supabase.table("factory_process").select("id").eq(
        "factory_id", factory_id
    ).eq("process_id", process_id).eq("is_active", True).execute()

    if existing.data:
        raise HTTPException(status_code=409, detail="이미 등록된 공정입니다.")

    # v_process_unified에서 공정 정보 조회
    proc_res = supabase.table("v_process_unified").select("*").eq(
        "process_id", process_id
    ).limit(1).execute()

    if not proc_res.data:
        raise HTTPException(status_code=404, detail="공정을 찾을 수 없습니다.")

    proc = proc_res.data[0]

    insert_data = {
        "factory_id": factory_id,
        "process_id": process_id,
        "process_lv1": proc.get("process_lv1", ""),
        "process_lv2": proc.get("process_lv2", ""),
        "process_lv3": proc.get("process_lv3", ""),
        "process_lv4": proc.get("process_lv4", ""),
        "process_path": proc.get("process_path", ""),
        "is_primary": body.get("is_primary", False),
        "is_active": True,
    }

    res = supabase.table("factory_process").insert(insert_data).execute()

    if not res.data:
        raise HTTPException(status_code=500, detail="공정 등록에 실패했습니다.")

    return {
        "status": "success",
        "message": "공정이 추가됐습니다. 법령 재진단을 실행하세요.",
        "data": res.data[0]
    }


# ──────────────────────────────────────────────
# POST /factory-process/{factory_id}/processes/bulk
# MUST+CORE 공정 전체 일괄 추가
# ──────────────────────────────────────────────
@router.post("/{factory_id}/processes/bulk")
async def bulk_add_factory_processes(
    factory_id: str,
    body: dict,
):
    supabase = get_supabase()

    process_ids = body.get("process_ids", [])
    if not process_ids:
        raise HTTPException(status_code=400, detail="process_ids가 필요합니다.")

    # 기존 등록 공정 조회
    existing_res = supabase.table("factory_process").select("process_id").eq(
        "factory_id", factory_id
    ).eq("is_active", True).execute()
    existing_ids = set(r["process_id"] for r in (existing_res.data or []))

    # v_process_unified에서 공정 정보 배치 조회
    proc_res = supabase.table("v_process_unified").select(
        "process_id, process_lv1, process_lv2, process_lv3, process_lv4, process_path"
    ).in_("process_id", process_ids).execute()

    proc_map = {r["process_id"]: r for r in (proc_res.data or [])}

    insert_rows = []
    skipped = []
    for pid in process_ids:
        if pid in existing_ids:
            skipped.append(pid)
            continue
        if pid not in proc_map:
            skipped.append(pid)
            continue
        p = proc_map[pid]
        insert_rows.append({
            "factory_id": factory_id,
            "process_id": pid,
            "process_lv1": p.get("process_lv1", ""),
            "process_lv2": p.get("process_lv2", ""),
            "process_lv3": p.get("process_lv3", ""),
            "process_lv4": p.get("process_lv4", ""),
            "process_path": p.get("process_path", ""),
            "is_primary": False,
            "is_active": True,
        })

    added_count = 0
    if insert_rows:
        res = supabase.table("factory_process").insert(insert_rows).execute()
        added_count = len(res.data or [])

    return {
        "status": "success",
        "message": f"{added_count}개 공정이 추가됐습니다. ({len(skipped)}개 건너뜀)",
        "data": {
            "added_count": added_count,
            "skipped_count": len(skipped),
            "skipped_ids": skipped,
        }
    }


# ──────────────────────────────────────────────
# DELETE /factory-process/{factory_id}/processes/{process_id}
# 공정 삭제 (비활성화)
# ──────────────────────────────────────────────
@router.delete("/{factory_id}/processes/{process_id}")
async def delete_factory_process(factory_id: str, process_id: str):
    supabase = get_supabase()

    res = supabase.table("factory_process").update({"is_active": False}).eq(
        "factory_id", factory_id
    ).eq("process_id", process_id).execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="등록된 공정을 찾을 수 없습니다.")

    return {
        "status": "success",
        "message": "공정이 삭제됐습니다.",
    }


# ──────────────────────────────────────────────
# PATCH /factory-process/{factory_id}/processes/{process_id}
# 주요 공정(is_primary) 토글
# ──────────────────────────────────────────────
@router.patch("/{factory_id}/processes/{process_id}")
async def update_factory_process(
    factory_id: str,
    process_id: str,
    body: dict,
):
    supabase = get_supabase()

    allowed = {"is_primary", "is_active"}
    update_data = {k: v for k, v in body.items() if k in allowed}

    if not update_data:
        raise HTTPException(status_code=400, detail="수정할 항목이 없습니다.")

    res = supabase.table("factory_process").update(update_data).eq(
        "factory_id", factory_id
    ).eq("process_id", process_id).execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="등록된 공정을 찾을 수 없습니다.")

    return {
        "status": "success",
        "message": "공정이 수정됐습니다.",
        "data": res.data[0]
    }


# ──────────────────────────────────────────────
# GET /factory-process/{factory_id}/recommend-equipment
# 등록된 공정 기반 설비 추천 (v_equipment_unified 기반)
# ──────────────────────────────────────────────
@router.get("/{factory_id}/recommend-equipment")
async def recommend_equipment(
    factory_id: str,
    band_filter: Optional[str] = Query(None, description="MUST/CORE/OPTIONAL"),
):
    supabase = get_supabase()

    # 등록된 공정 조회
    proc_res = supabase.table("factory_process").select("process_id").eq(
        "factory_id", factory_id
    ).eq("is_active", True).execute()

    if not proc_res.data:
        return {
            "status": "success",
            "message": "등록된 공정이 없습니다. 공정을 먼저 등록해주세요.",
            "data": {"factory_id": factory_id, "items": [], "total": 0}
        }

    process_ids = list(set(r["process_id"] for r in proc_res.data))

    # v_equipment_unified에서 설비 조회
    eq_query = supabase.table("v_equipment_unified").select(
        "process_id, facility_name_std, match_band, match_score, source_type, source_priority"
    ).in_("process_id", process_ids)

    if band_filter:
        eq_query = eq_query.eq("match_band", band_filter)
    else:
        eq_query = eq_query.in_("match_band", ["MUST", "CORE"])

    eq_query = eq_query.order("source_priority").order("match_band")
    eq_res = eq_query.execute()
    equip_items = eq_res.data or []

    # 설비명 기준 중복 제거 (여러 공정에 같은 설비 가능)
    seen = set()
    unique_items = []
    for row in equip_items:
        key = row["facility_name_std"]
        if key not in seen:
            seen.add(key)
            unique_items.append(row)

    return {
        "status": "success",
        "data": {
            "factory_id": factory_id,
            "items": unique_items,
            "total": len(unique_items),
            "source_process_count": len(process_ids),
        }
    }
