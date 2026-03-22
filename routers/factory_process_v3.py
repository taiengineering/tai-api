"""
시설 공정 관리 라우터 — v3.0.0
v3 변경사항:
  - POST /processes: source 필드 추가 (DB / MANUAL)
  - POST /processes/manual: 수동 직접 입력 공정 등록
  - GET /search: KSIC 기반 4단계 셀렉트용 공정 조회
  - overview: MANUAL 공정 포함
"""
from fastapi import APIRouter, Query, HTTPException
from typing import Optional
import os
from supabase import create_client

router = APIRouter(prefix="/factory-process", tags=["factory-process"])

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

SOURCE_BADGE = {
    "KOSHA_GUIDE": "KOSHA",
    "KOSHA_GUIDE_V2": "KOSHA",
    "TAI_EXISTING": "TAI",
    "TEMPLATE": "TEMPLATE",
    "MANUAL": "수동입력",
}


def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ──────────────────────────────────────────────
# GET /factory-process/search
# KSIC + 계층 필터 기반 공정 목록 (v_process_unified)
# 4단계 셀렉트바 전용
# ──────────────────────────────────────────────
@router.get("/search")
async def search_processes(
    ksic: Optional[str] = Query(None, description="KSIC 4자리 업종코드"),
    lv1: Optional[str] = Query(None, description="공정 대분류"),
    lv2: Optional[str] = Query(None, description="공정 중분류"),
    lv3: Optional[str] = Query(None, description="공정 소분류"),
    source: Optional[str] = Query(None, description="소스 필터"),
    limit: int = Query(300, ge=1, le=1000),
):
    """
    4단계 셀렉트바를 위한 공정 목록 조회
    단계별 호출:
      1단계: ksic만 전달 → lv1 옵션 반환
      2단계: ksic + lv1 → lv2 옵션 반환
      3단계: ksic + lv1 + lv2 → lv3 옵션 반환
      4단계: ksic + lv1 + lv2 + lv3 → 공정명 목록 반환
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

    query = query.order("source_priority").order("process_lv1").order("process_lv2").order("process_lv3").order("process_lv4")
    query = query.limit(limit)

    res = query.execute()
    items = res.data or []

    # 단계별 unique 옵션 추출
    lv1_set = sorted(set(r["process_lv1"] for r in items if r.get("process_lv1")))
    lv2_set = sorted(set(r["process_lv2"] for r in items if r.get("process_lv2")))
    lv3_set = sorted(set(r["process_lv3"] for r in items if r.get("process_lv3")))

    result_items = []
    for row in items:
        src = row.get("process_source", "")
        result_items.append({
            **row,
            "process_name": row.get("process_lv4") or row.get("process_lv3", ""),
            "source_badge": SOURCE_BADGE.get(src, src),
            "is_kosha": src.startswith("KOSHA"),
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


# ──────────────────────────────────────────────
# GET /factory-process/overview
# 시설별 공정 현황 집계 (Admin 탭2) — MANUAL 포함
# ──────────────────────────────────────────────
@router.get("/overview")
async def get_factory_process_overview(
    search: Optional[str] = Query(None),
    has_process: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    supabase = get_supabase()
    offset = (page - 1) * page_size

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

    # 공정 수 집계 (source별 포함)
    proc_res = supabase.table("factory_process").select(
        "factory_id, process_id, is_primary, source"
    ).in_("factory_id", factory_ids).eq("is_active", True).execute()

    proc_map = {}
    for row in (proc_res.data or []):
        fid = row["factory_id"]
        if fid not in proc_map:
            proc_map[fid] = {"total": 0, "manual": 0, "primary": 0}
        proc_map[fid]["total"] += 1
        if row.get("source") == "MANUAL":
            proc_map[fid]["manual"] += 1
        if row.get("is_primary"):
            proc_map[fid]["primary"] += 1

    items = []
    for f in factories:
        fid = f["id"]
        p = proc_map.get(fid, {"total": 0, "manual": 0, "primary": 0})
        process_count = p["total"]

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
            "manual_count": p["manual"],
            "primary_count": p["primary"],
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
# 시설 등록 공정 목록 (source 포함)
# ──────────────────────────────────────────────
@router.get("/{factory_id}/processes")
async def get_factory_processes(factory_id: str):
    supabase = get_supabase()

    res = supabase.table("factory_process").select("*").eq(
        "factory_id", factory_id
    ).eq("is_active", True).execute()

    items = res.data or []

    # DB 소스 공정은 v_process_unified에서 소스 정보 보강
    db_process_ids = [r["process_id"] for r in items if r.get("source") != "MANUAL" and r.get("process_id")]
    source_map = {}
    if db_process_ids:
        pres = supabase.table("v_process_unified").select(
            "process_id, process_source, source_priority"
        ).in_("process_id", db_process_ids).execute()
        for row in (pres.data or []):
            source_map[row["process_id"]] = row.get("process_source", "")

    result = []
    for row in items:
        src_code = row.get("source", "DB")
        if src_code == "MANUAL":
            process_source = "MANUAL"
            process_name = row.get("process_name_manual", "수동입력 공정")
        else:
            process_source = source_map.get(row.get("process_id", ""), "")
            process_name = row.get("process_lv4") or row.get("process_lv3", "")

        result.append({
            **row,
            "process_name": process_name,
            "process_source": process_source,
            "source_badge": SOURCE_BADGE.get(process_source, ""),
            "is_manual": src_code == "MANUAL",
        })

    return {
        "status": "success",
        "data": {
            "factory_id": factory_id,
            "items": result,
            "total": len(result),
        }
    }


# ──────────────────────────────────────────────
# POST /factory-process/{factory_id}/processes
# 공정 추가 (DB 선택 또는 MANUAL)
# ──────────────────────────────────────────────
@router.post("/{factory_id}/processes")
async def add_factory_process(factory_id: str, body: dict):
    supabase = get_supabase()

    source = body.get("source", "DB")

    # ── MANUAL 직접 입력 ──
    if source == "MANUAL":
        process_name = body.get("process_name_manual", "").strip()
        if not process_name:
            raise HTTPException(status_code=400, detail="수동 입력 시 공정명(process_name_manual)이 필요합니다.")

        insert_data = {
            "factory_id": factory_id,
            "process_id": f"MANUAL-{factory_id[:8]}-{int(__import__('time').time())}",
            "process_lv1": body.get("process_lv1", ""),
            "process_lv2": body.get("process_lv2", ""),
            "process_lv3": body.get("process_lv3", ""),
            "process_lv4": process_name,
            "process_path": body.get("process_path", process_name),
            "process_name_manual": process_name,
            "source": "MANUAL",
            "is_primary": body.get("is_primary", False),
            "is_active": True,
        }
    else:
        # ── DB 선택 ──
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
            "source": "DB",
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
# MUST+CORE 공정 일괄 추가
# ──────────────────────────────────────────────
@router.post("/{factory_id}/processes/bulk")
async def bulk_add_factory_processes(factory_id: str, body: dict):
    supabase = get_supabase()

    process_ids = body.get("process_ids", [])
    if not process_ids:
        raise HTTPException(status_code=400, detail="process_ids가 필요합니다.")

    # 기존 등록 공정
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
            "source": "DB",
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
        "data": {"added_count": added_count, "skipped_count": len(skipped)}
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

    return {"status": "success", "message": "공정이 삭제됐습니다."}


# ──────────────────────────────────────────────
# PATCH /factory-process/{factory_id}/processes/{process_id}
# 주요 공정(is_primary) 토글
# ──────────────────────────────────────────────
@router.patch("/{factory_id}/processes/{process_id}")
async def update_factory_process(factory_id: str, process_id: str, body: dict):
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

    return {"status": "success", "message": "공정이 수정됐습니다.", "data": res.data[0]}


# ──────────────────────────────────────────────
# GET /factory-process/{factory_id}/recommend-equipment
# 등록 공정 기반 설비 추천
# ──────────────────────────────────────────────
@router.get("/{factory_id}/recommend-equipment")
async def recommend_equipment(
    factory_id: str,
    band_filter: Optional[str] = Query(None),
):
    supabase = get_supabase()

    proc_res = supabase.table("factory_process").select("process_id, source").eq(
        "factory_id", factory_id
    ).eq("is_active", True).execute()

    if not proc_res.data:
        return {
            "status": "success",
            "message": "등록된 공정이 없습니다.",
            "data": {"factory_id": factory_id, "items": [], "total": 0}
        }

    # MANUAL 공정은 설비 추천 제외
    process_ids = list(set(
        r["process_id"] for r in proc_res.data
        if r.get("source") != "MANUAL" and r.get("process_id")
    ))

    if not process_ids:
        return {
            "status": "success",
            "data": {"factory_id": factory_id, "items": [], "total": 0}
        }

    eq_query = supabase.table("v_equipment_unified").select(
        "process_id, facility_name_std, match_band, match_score, source_type, source_priority"
    ).in_("process_id", process_ids)

    if band_filter:
        eq_query = eq_query.eq("match_band", band_filter)
    else:
        eq_query = eq_query.in_("match_band", ["MUST", "CORE"])

    eq_query = eq_query.order("source_priority").order("match_band")
    eq_res = eq_query.execute()

    seen = set()
    unique_items = []
    for row in (eq_res.data or []):
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
