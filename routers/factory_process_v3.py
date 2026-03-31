"""
시설 공정 관리 라우터 — v3.2.0
v3.2.0: KCSC 공정 검색 및 등록 지원
  - GET  /factory-process/kcsc/search?q=&limit=  kcsc_process_master ILIKE 검색
  - POST /{factory_id}/processes: source='KCSC' + kcs_code 처리 추가
v3.1.0: 공정수동등록 보완
  - GET /processes: display_name, is_manual 필드 명시적 추가
  - DELETE /{factory_id}/processes/{process_record_id}: UUID(id) 기준 soft delete
  - PATCH  /{factory_id}/processes/{process_record_id}: UUID(id) 기준 + process_name_manual/lv1/lv2/lv3 수정 지원
v3.0.0: MANUAL 공정 등록, search, overview
"""
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from typing import Optional
import os
from supabase import create_client

router = APIRouter(prefix="/factory-process", tags=["factory-process"])

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

SOURCE_BADGE = {
    "KOSHA_GUIDE":    "KOSHA",
    "KOSHA_GUIDE_V2": "KOSHA",
    "TAI_EXISTING":  "TAI",
    "TEMPLATE":      "TEMPLATE",
    "MANUAL":        "수동입력",
    "KCSC":          "KCSC",
}


def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ── Pydantic 모델 ─────────────────────────────────────────

class ProcessCreateBody(BaseModel):
    process_id:          Optional[str] = None   # v_process_unified process_id (DB source)
    kcs_code:            Optional[str] = None   # KCSC 공정 코드 (source='KCSC' 시 사용)
    process_name_manual: Optional[str] = None   # 수동 공정명 (MANUAL 필수)
    source:              str = "DB"             # DB | MANUAL | KCSC
    process_lv1:         Optional[str] = None
    process_lv2:         Optional[str] = None
    process_lv3:         Optional[str] = None
    process_lv4:         Optional[str] = None
    is_primary:          bool = False


class ProcessUpdateBody(BaseModel):
    process_name_manual: Optional[str] = None
    process_lv1:         Optional[str] = None
    process_lv2:         Optional[str] = None
    process_lv3:         Optional[str] = None
    is_primary:          Optional[bool] = None


# ──────────────────────────────────────────────
# GET /factory-process/search
# ──────────────────────────────────────────────
@router.get("/search")
async def search_processes(
    ksic:   Optional[str] = Query(None),
    lv1:    Optional[str] = Query(None),
    lv2:    Optional[str] = Query(None),
    lv3:    Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    limit:  int = Query(300, ge=1, le=1000),
):
    supabase = get_supabase()
    query = supabase.table("v_process_unified").select(
        "id, process_id, industry_code_full, industry_name_full, "
        "process_lv1, process_lv2, process_lv3, process_lv4, "
        "process_path, process_source, source_priority"
    )
    if ksic:   query = query.eq("industry_code_full", ksic)
    if lv1:    query = query.eq("process_lv1", lv1)
    if lv2:    query = query.eq("process_lv2", lv2)
    if lv3:    query = query.eq("process_lv3", lv3)
    if source: query = query.eq("process_source", source)
    query = query.order("source_priority").order("process_lv1").order("process_lv2").order("process_lv3").order("process_lv4")
    res = query.limit(limit).execute()
    items = res.data or []

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
# ──────────────────────────────────────────────
@router.get("/overview")
async def get_factory_process_overview(
    search:      Optional[str]  = Query(None),
    has_process: Optional[bool] = Query(None),
    page:        int = Query(1, ge=1),
    page_size:   int = Query(20, ge=1, le=100),
):
    supabase = get_supabase()
    offset = (page - 1) * page_size

    fac_query = supabase.table("factories").select(
        "id, factory_name, ksic_code, ksic_name, companies!inner(company_name)",
        count="exact"
    )
    if search:
        fac_query = fac_query.or_(f"factory_name.ilike.%{search}%")
    fac_query = fac_query.order("factory_name").range(offset, offset + page_size - 1)
    fac_res = fac_query.execute()
    factories = fac_res.data or []
    total = fac_res.count or 0

    if not factories:
        return {"status": "success", "data": {"items": [], "total": 0, "page": page, "page_size": page_size}}

    factory_ids = [f["id"] for f in factories]
    proc_res = supabase.table("factory_process").select(
        "factory_id, process_id, is_primary, source"
    ).in_("factory_id", factory_ids).eq("is_active", True).execute()

    proc_map = {}
    for row in (proc_res.data or []):
        fid = row["factory_id"]
        if fid not in proc_map:
            proc_map[fid] = {"total": 0, "manual": 0, "primary": 0}
        proc_map[fid]["total"] += 1
        if row.get("source") in ("MANUAL",):  proc_map[fid]["manual"]  += 1
        if row.get("is_primary"):              proc_map[fid]["primary"] += 1

    items = []
    for f in factories:
        fid = f["id"]
        p = proc_map.get(fid, {"total": 0, "manual": 0, "primary": 0})
        process_count = p["total"]
        if has_process is True  and process_count == 0: continue
        if has_process is False and process_count  > 0: continue
        items.append({
            "factory_id":    fid,
            "factory_name":  f.get("factory_name", ""),
            "company_name":  (f.get("companies") or {}).get("company_name", ""),
            "ksic_code":     f.get("ksic_code", ""),
            "ksic_name":     f.get("ksic_name", ""),
            "process_count": process_count,
            "manual_count":  p["manual"],
            "primary_count": p["primary"],
            "has_process":   process_count > 0,
            "status_badge":  "등록" if process_count > 0 else "미등록",
        })

    return {
        "status": "success",
        "data": {
            "items": items, "total": total, "page": page, "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
        }
    }


# ──────────────────────────────────────────────
# GET /factory-process/kcsc/search  (v3.2.0 신규)
# 고정 경로 — /{factory_id} 앞에 선언
# ──────────────────────────────────────────────
@router.get("/kcsc/search")
async def search_kcsc_processes(
    q:     str = Query(..., description="공정명 검색어"),
    limit: int = Query(20, ge=1, le=100),
):
    """
    kcsc_process_master에서 process_name ILIKE 검색.
    반환: items: [{kcs_code, process_name, level1_name, level2_name, construction_type}]
    """
    supabase = get_supabase()
    res = supabase.table("kcsc_process_master").select(
        "kcs_code, process_name, level1_name, level2_name, construction_type"
    ).ilike("process_name", f"%{q}%").eq("is_active", True).limit(limit).execute()

    items = res.data or []
    return {
        "status": "success",
        "data": {
            "q":     q,
            "items": items,
            "total": len(items),
        }
    }


# ──────────────────────────────────────────────
# GET /factory-process/{factory_id}/processes
# v3.1.0: display_name, is_manual 명시적 추가
# ──────────────────────────────────────────────
@router.get("/{factory_id}/processes")
async def get_factory_processes(factory_id: str):
    supabase = get_supabase()

    res = supabase.table("factory_process").select(
        "id, factory_id, process_id, process_lv1, process_lv2, process_lv3, process_lv4, "
        "process_path, process_name_manual, source, is_primary, is_active, created_at"
    ).eq("factory_id", factory_id).eq("is_active", True).execute()

    items = res.data or []

    db_process_ids = [r["process_id"] for r in items if r.get("source") not in ("MANUAL", "KCSC") and r.get("process_id")]
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
        is_manual = (src_code == "MANUAL")

        if is_manual:
            process_source = "MANUAL"
            display_name   = row.get("process_name_manual") or "수동입력 공정"
        elif src_code == "KCSC":
            process_source = "KCSC"
            display_name   = (
                row.get("process_name_manual")
                or row.get("process_lv3")
                or row.get("process_lv2")
                or row.get("process_id", "")
            )
        else:
            process_source = source_map.get(row.get("process_id", ""), "")
            display_name   = (
                row.get("process_name_manual")
                or row.get("process_lv4")
                or row.get("process_lv3")
                or row.get("process_lv2")
                or row.get("process_lv1")
                or row.get("process_id", "")
            )

        result.append({
            **row,
            "display_name":   display_name,
            "process_name":   display_name,
            "process_source": process_source,
            "source_badge":   SOURCE_BADGE.get(process_source, ""),
            "is_manual":      is_manual,
        })

    return {
        "status": "success",
        "data": {"factory_id": factory_id, "items": result, "total": len(result)},
    }


# ──────────────────────────────────────────────
# POST /factory-process/{factory_id}/processes
# v3.2.0: source='KCSC' + kcs_code 처리 추가
# ──────────────────────────────────────────────
@router.post("/{factory_id}/processes")
async def add_factory_process(factory_id: str, body: ProcessCreateBody):
    supabase = get_supabase()
    import time

    source = (body.source or "DB").upper()

    if source == "MANUAL":
        process_name = (body.process_name_manual or "").strip()
        if not process_name:
            raise HTTPException(status_code=422, detail="수동 공정 등록 시 process_name_manual은 필수입니다.")

        process_id = f"MANUAL-{factory_id[:8]}-{int(time.time())}"
        lv1 = body.process_lv1 or "기타"
        insert_data = {
            "factory_id":          factory_id,
            "process_id":          process_id,
            "process_name_manual": process_name,
            "process_lv1":         lv1,
            "process_lv2":         body.process_lv2,
            "process_lv3":         body.process_lv3,
            "process_lv4":         body.process_lv4 or process_name,
            "process_path":        " > ".join(filter(None, [
                                       lv1, body.process_lv2, body.process_lv3, process_name
                                   ])),
            "source":              "MANUAL",
            "is_primary":          body.is_primary,
            "is_active":           True,
        }

    elif source == "KCSC":
        # v3.2.0: kcsc_process_master에서 kcs_code로 조회
        if not body.kcs_code:
            raise HTTPException(status_code=422, detail="KCSC 공정 등록 시 kcs_code는 필수입니다.")

        kcsc_res = supabase.table("kcsc_process_master").select(
            "kcs_code, process_name, level1_name, level2_name, construction_type, full_code"
        ).eq("kcs_code", body.kcs_code).eq("is_active", True).limit(1).execute()

        if not kcsc_res.data:
            raise HTTPException(status_code=404, detail="KCSC 공정을 찾을 수 없습니다.")

        kcsc = kcsc_res.data[0]

        # 중복 체크 (같은 factory에 동일 kcs_code 이미 등록 여부)
        dup = supabase.table("factory_process").select("id").eq(
            "factory_id", factory_id
        ).eq("process_id", body.kcs_code).eq("is_active", True).execute()
        if dup.data:
            raise HTTPException(status_code=409, detail="이미 등록된 KCSC 공정입니다.")

        lv1 = kcsc.get("level1_name") or kcsc.get("construction_type") or "기타"
        lv2 = kcsc.get("level2_name") or ""
        process_name = kcsc.get("process_name", "")
        insert_data = {
            "factory_id":          factory_id,
            "process_id":          body.kcs_code,          # kcs_code를 process_id로 저장
            "process_name_manual": process_name,            # 공정명을 manual 필드에 저장
            "process_lv1":         lv1,
            "process_lv2":         lv2,
            "process_lv3":         process_name,
            "process_lv4":         None,
            "process_path":        " > ".join(filter(None, [lv1, lv2, process_name])),
            "source":              "KCSC",
            "is_primary":          body.is_primary,
            "is_active":           True,
        }

    else:
        # source == "DB"
        if not body.process_id:
            raise HTTPException(status_code=422, detail="KCSC 공정 등록 시 process_id는 필수입니다.")

        existing = supabase.table("factory_process").select("id").eq(
            "factory_id", factory_id
        ).eq("process_id", body.process_id).eq("is_active", True).execute()
        if existing.data:
            raise HTTPException(status_code=409, detail="이미 등록된 공정입니다.")

        proc_res = supabase.table("v_process_unified").select("*").eq(
            "process_id", body.process_id
        ).limit(1).execute()
        if not proc_res.data:
            raise HTTPException(status_code=404, detail="공정을 찾을 수 없습니다.")

        proc = proc_res.data[0]
        insert_data = {
            "factory_id":  factory_id,
            "process_id":  body.process_id,
            "process_lv1": proc.get("process_lv1", ""),
            "process_lv2": proc.get("process_lv2", ""),
            "process_lv3": proc.get("process_lv3", ""),
            "process_lv4": proc.get("process_lv4", ""),
            "process_path": proc.get("process_path", ""),
            "source":      "DB",
            "is_primary":  body.is_primary,
            "is_active":   True,
        }

    res = supabase.table("factory_process").insert(insert_data).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="공정 등록에 실패했습니다.")

    record = res.data[0]
    is_manual = (source == "MANUAL")
    display_name = (
        record.get("process_name_manual")
        or record.get("process_lv4")
        or record.get("process_lv3")
        or record.get("process_id", "")
    )
    return {
        "status":  "success",
        "message": "공정이 추가됐습니다.",
        "data":    {**record, "display_name": display_name, "is_manual": is_manual, "source_badge": SOURCE_BADGE.get(source, source)},
    }


# ──────────────────────────────────────────────
# POST /factory-process/{factory_id}/processes/bulk
# ──────────────────────────────────────────────
@router.post("/{factory_id}/processes/bulk")
async def bulk_add_factory_processes(factory_id: str, body: dict):
    supabase = get_supabase()
    process_ids = body.get("process_ids", [])
    if not process_ids:
        raise HTTPException(status_code=400, detail="process_ids가 필요합니다.")

    existing_res = supabase.table("factory_process").select("process_id").eq(
        "factory_id", factory_id
    ).eq("is_active", True).execute()
    existing_ids = set(r["process_id"] for r in (existing_res.data or []))

    proc_res = supabase.table("v_process_unified").select(
        "process_id, process_lv1, process_lv2, process_lv3, process_lv4, process_path"
    ).in_("process_id", process_ids).execute()
    proc_map = {r["process_id"]: r for r in (proc_res.data or [])}

    insert_rows, skipped = [], []
    for pid in process_ids:
        if pid in existing_ids or pid not in proc_map:
            skipped.append(pid)
            continue
        p = proc_map[pid]
        insert_rows.append({
            "factory_id": factory_id, "process_id": pid,
            "process_lv1": p.get("process_lv1", ""), "process_lv2": p.get("process_lv2", ""),
            "process_lv3": p.get("process_lv3", ""), "process_lv4": p.get("process_lv4", ""),
            "process_path": p.get("process_path", ""), "source": "DB",
            "is_primary": False, "is_active": True,
        })

    added_count = 0
    if insert_rows:
        res = supabase.table("factory_process").insert(insert_rows).execute()
        added_count = len(res.data or [])

    return {
        "status":  "success",
        "message": f"{added_count}개 공정이 추가됐습니다. ({len(skipped)}개 건너뜀)",
        "data":    {"added_count": added_count, "skipped_count": len(skipped)},
    }


# ──────────────────────────────────────────────
# DELETE /factory-process/{factory_id}/processes/{process_record_id}
# v3.1.0: UUID(id) 기준 soft delete
# ──────────────────────────────────────────────
@router.delete("/{factory_id}/processes/{process_record_id}")
async def delete_factory_process(factory_id: str, process_record_id: str):
    """
    process_record_id = factory_process.id (UUID)
    MANUAL / KCSC 공정 포함 모든 공정 soft delete 가능.
    """
    supabase = get_supabase()
    res = supabase.table("factory_process").update({"is_active": False}).eq(
        "id", process_record_id
    ).eq("factory_id", factory_id).execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="등록된 공정을 찾을 수 없습니다.")

    return {"status": "success", "message": "공정이 삭제되었습니다."}


# ──────────────────────────────────────────────
# PATCH /factory-process/{factory_id}/processes/{process_record_id}
# v3.1.0: UUID(id) 기준 + process_name_manual/lv1/lv2/lv3 수정 지원
# ──────────────────────────────────────────────
@router.patch("/{factory_id}/processes/{process_record_id}")
async def update_factory_process(factory_id: str, process_record_id: str, body: ProcessUpdateBody):
    """
    process_record_id = factory_process.id (UUID)
    수정 가능 필드: process_name_manual, process_lv1, process_lv2, process_lv3, is_primary
    """
    supabase = get_supabase()

    update_data = {k: v for k, v in body.dict().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=422, detail="수정할 내용이 없습니다.")

    # process_name_manual 수정 시 process_lv4도 동기화
    if "process_name_manual" in update_data:
        update_data["process_lv4"] = update_data["process_name_manual"]

    res = supabase.table("factory_process").update(update_data).eq(
        "id", process_record_id
    ).eq("factory_id", factory_id).execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="등록된 공정을 찾을 수 없습니다.")

    return {"status": "success", "message": "공정이 수정됐습니다.", "data": res.data[0]}


# ──────────────────────────────────────────────
# GET /factory-process/{factory_id}/recommend-equipment
# ──────────────────────────────────────────────
@router.get("/{factory_id}/recommend-equipment")
async def recommend_equipment(
    factory_id:  str,
    band_filter: Optional[str] = Query(None),
):
    supabase = get_supabase()
    proc_res = supabase.table("factory_process").select("process_id, source").eq(
        "factory_id", factory_id
    ).eq("is_active", True).execute()

    if not proc_res.data:
        return {"status": "success", "message": "등록된 공정이 없습니다.",
                "data": {"factory_id": factory_id, "items": [], "total": 0}}

    process_ids = list(set(
        r["process_id"] for r in proc_res.data
        if r.get("source") not in ("MANUAL", "KCSC") and r.get("process_id")
    ))
    if not process_ids:
        return {"status": "success", "data": {"factory_id": factory_id, "items": [], "total": 0}}

    eq_query = supabase.table("v_equipment_unified").select(
        "process_id, facility_name_std, match_band, match_score, source_type, source_priority"
    ).in_("process_id", process_ids)
    if band_filter:
        eq_query = eq_query.eq("match_band", band_filter)
    else:
        eq_query = eq_query.in_("match_band", ["MUST", "CORE"])
    eq_query = eq_query.order("source_priority").order("match_band")
    eq_res = eq_query.execute()

    seen, unique_items = set(), []
    for row in (eq_res.data or []):
        key = row["facility_name_std"]
        if key not in seen:
            seen.add(key)
            unique_items.append(row)

    return {
        "status": "success",
        "data": {
            "factory_id": factory_id, "items": unique_items,
            "total": len(unique_items), "source_process_count": len(process_ids),
        }
    }
