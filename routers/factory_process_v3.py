"""
시설 공정 관리 라우터 — v3.4.0
v3.4.0: (WO-SAFE-LEGAL-IND-CANONICAL-IMPLEMENT-001 STEP4) 공정 canonical 확장.
  - 공통 supabase client 사용(로컬 create_client 제거).
  - factory-scoped route 6개에 auth + factory ownership 결선(POST 는 trace 이전 소유권 확인).
  - hazard_codes / worker_count / activity_types 실제 공정 속성 3개 결선(strict; PATCH explicit-null clear).
  - factory_process_id / process 관계 / process_id / source 불변. legal_ namespace/route 미생성.
v3.3.0: (LEDGER §39) GET /search 의 분류 옵션(hierarchy) 을 목록 limit 과 분리.
  - 옵션(lv1/lv2/lv3_options)을 해당 업종(ksic) 전체 distinct 로 집계(캐스케이드).
  - 종전에는 limit 로 잘린 items 에서 옵션을 만들어(화면이 limit=1 로 옵션만 조회) 대분류가
    1개만 노출됐다. 화면이 이미 hierarchy 를 읽으므로 서버만 고치면 즉시 반영(무 vue3).
v3.2.0: KCSC 공정 검색 및 등록 지원
  - GET  /factory-process/kcsc/search?q=&limit=  kcsc_process_master ILIKE 검색
  - POST /{factory_id}/processes: source='KCSC' + kcs_code 처리 추가
v3.1.0: 공정수동등록 보완
  - GET /processes: display_name, is_manual 필드 명시적 추가
  - DELETE /{factory_id}/processes/{process_record_id}: UUID(id) 기준 soft delete
  - PATCH  /{factory_id}/processes/{process_record_id}: UUID(id) 기준 + process_name_manual/lv1/lv2/lv3 수정 지원
v3.0.0: MANUAL 공정 등록, search, overview
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, StrictInt, StrictStr, AfterValidator
from typing import Optional, List, Annotated
from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services.company_scope import _ensure_factory_own
from watch_engine import create_trace, emit_event
from watch_engine.trace import clear_trace

router = APIRouter(prefix="/factory-process", tags=["factory-process"])

SOURCE_BADGE = {
    "KOSHA_GUIDE":    "KOSHA",
    "KOSHA_GUIDE_V2": "KOSHA",
    "TAI_EXISTING":  "TAI",
    "TEMPLATE":      "TEMPLATE",
    "MANUAL":        "수동입력",
    "KCSC":          "KCSC",
}


# WO-CANONICAL STEP4: 공통 supabase client 사용(로컬 create_client 제거).
# 신규 canonical process field 전용 strict 경계 (기존 필드 coercion 정책 불변).


def _proc_nonneg_int(v):
    if v is None:
        return v
    if not isinstance(v, int):
        raise ValueError("정수여야 합니다")
    if v < 0:
        raise ValueError("0 이상이어야 합니다")
    return v


def _proc_str_list(v):
    if v is None:
        return v
    if not isinstance(v, list):
        raise ValueError("배열이어야 합니다")
    for x in v:
        if x.strip() == "":
            raise ValueError("빈/공백 문자열 항목은 허용되지 않습니다")
    return v


# StrictInt: bool/문자열/float 거부. 음수 거부.
ProcWorkerCount = Annotated[StrictInt, AfterValidator(_proc_nonneg_int)]
# 항목 string only(StrictStr), 빈/공백 금지. NULL/[]/문자열 배열 허용.
ProcStrList = Annotated[List[StrictStr], AfterValidator(_proc_str_list)]

# PATCH 에서 explicit-null clear 를 허용하는 canonical process field (정확히 3개).
PROCESS_CANONICAL_NULL_CLEAR_FIELDS = {"hazard_codes", "worker_count", "activity_types"}


def _proc_apply_canonical(insert_data: dict, body) -> None:
    """CREATE insert_data 에 canonical 3-field 를 provided(model_fields_set) 만 결선.
    omitted → 미포함(DB NULL) / 0·[] → 보존."""
    for f in ("hazard_codes", "worker_count", "activity_types"):
        if f in body.model_fields_set:
            insert_data[f] = getattr(body, f)


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
    # WO-CANONICAL STEP4: 공정 canonical 실제 속성 3개(strict; default None)
    hazard_codes:        Optional[ProcStrList] = None
    worker_count:        Optional[ProcWorkerCount] = None
    activity_types:      Optional[ProcStrList] = None


class ProcessUpdateBody(BaseModel):
    process_name_manual: Optional[str] = None
    process_lv1:         Optional[str] = None
    process_lv2:         Optional[str] = None
    process_lv3:         Optional[str] = None
    is_primary:          Optional[bool] = None
    # WO-CANONICAL STEP4: 공정 canonical 실제 속성 3개(strict; explicit-null clear)
    hazard_codes:        Optional[ProcStrList] = None
    worker_count:        Optional[ProcWorkerCount] = None
    activity_types:      Optional[ProcStrList] = None


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

    # §39: 분류 옵션(hierarchy)이 limit 에 잘리지 않도록, 옵션은 목록(items)과 분리해
    #      해당 업종(ksic) 전체를 distinct 로 집계한다(캐스케이드: lv1 → lv2 → lv3).
    #      화면 옵션 조회는 항상 ksic 를 보내므로, ksic 지정 시 이 경로를 탄다.
    #      (ksic 미지정 시에만 종전처럼 items 기반 — 회귀 방지.)
    if ksic:
        opt_rows = (
            supabase.table("v_process_unified")
            .select("process_lv1, process_lv2, process_lv3")
            .eq("industry_code_full", ksic)
            .limit(10000)
            .execute()
            .data
            or []
        )
        lv1_set = sorted(set(r["process_lv1"] for r in opt_rows if r.get("process_lv1")))
        lv2_src = [r for r in opt_rows if (not lv1 or r.get("process_lv1") == lv1)]
        lv2_set = sorted(set(r["process_lv2"] for r in lv2_src if r.get("process_lv2")))
        lv3_src = [r for r in lv2_src if (not lv2 or r.get("process_lv2") == lv2)]
        lv3_set = sorted(set(r["process_lv3"] for r in lv3_src if r.get("process_lv3")))
    else:
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
async def get_factory_processes(factory_id: str, current: dict = Depends(get_current_user)):
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)

    res = supabase.table("factory_process").select(
        "id, factory_id, process_id, process_lv1, process_lv2, process_lv3, process_lv4, "
        "process_path, process_name_manual, source, is_primary, is_active, created_at, "
        "hazard_codes, worker_count, activity_types"
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
async def add_factory_process(factory_id: str, body: ProcessCreateBody, current: dict = Depends(get_current_user)):
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)   # trace/event 이전에 소유권 확인(foreign/missing → 404, trace 미생성)
    create_trace(flow_key="process_registration", tenant_id="tai", actor_type="user")
    import time

    source = (body.source or "DB").upper()

    def _required_field_ok() -> bool:
        if source == "MANUAL":
            return bool((body.process_name_manual or "").strip())
        if source == "KCSC":
            return bool((body.kcs_code or "").strip())
        return bool((body.process_id or "").strip())

    emit_event(
        step_key="submit_payload",
        step_order=0,
        event_type="submit",
        result="success",
        connector_type="api",
        payload_summary={
            "has_process_type": bool((body.source or "").strip()),
            "process_type_key": source,
            "required_field_exists": _required_field_ok(),
        },
    )

    def _fail_validate_input():
        emit_event(
            step_key="validate_input",
            step_order=1,
            event_type="validate",
            result="failure",
            connector_type="api",
        )
        clear_trace()

    if source == "MANUAL":
        process_name = (body.process_name_manual or "").strip()
        if not process_name:
            _fail_validate_input()
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
        _proc_apply_canonical(insert_data, body)

    elif source == "KCSC":
        # v3.2.0: kcsc_process_master에서 kcs_code로 조회
        if not body.kcs_code:
            _fail_validate_input()
            raise HTTPException(status_code=422, detail="KCSC 공정 등록 시 kcs_code는 필수입니다.")

        kcsc_res = supabase.table("kcsc_process_master").select(
            "kcs_code, process_name, level1_name, level2_name, construction_type, full_code"
        ).eq("kcs_code", body.kcs_code).eq("is_active", True).limit(1).execute()

        if not kcsc_res.data:
            _fail_validate_input()
            raise HTTPException(status_code=404, detail="KCSC 공정을 찾을 수 없습니다.")

        kcsc = kcsc_res.data[0]

        # 중복 체크 (같은 factory에 동일 kcs_code 이미 등록 여부)
        dup = supabase.table("factory_process").select("id").eq(
            "factory_id", factory_id
        ).eq("process_id", body.kcs_code).eq("is_active", True).execute()
        if dup.data:
            _fail_validate_input()
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
        _proc_apply_canonical(insert_data, body)

    else:
        # source == "DB"
        if not body.process_id:
            _fail_validate_input()
            raise HTTPException(status_code=422, detail="KCSC 공정 등록 시 process_id는 필수입니다.")

        existing = supabase.table("factory_process").select("id").eq(
            "factory_id", factory_id
        ).eq("process_id", body.process_id).eq("is_active", True).execute()
        if existing.data:
            _fail_validate_input()
            raise HTTPException(status_code=409, detail="이미 등록된 공정입니다.")

        proc_res = supabase.table("v_process_unified").select("*").eq(
            "process_id", body.process_id
        ).limit(1).execute()
        if not proc_res.data:
            _fail_validate_input()
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
        _proc_apply_canonical(insert_data, body)

    emit_event(
        step_key="validate_input",
        step_order=1,
        event_type="validate",
        result="success",
        connector_type="api",
    )

    res = supabase.table("factory_process").insert(insert_data).execute()
    if not res.data:
        emit_event(
            step_key="save_db",
            step_order=2,
            event_type="save",
            result="failure",
            connector_type="database",
            payload_summary={
                "process_type_key": insert_data.get("source", source),
                "row_saved": False,
            },
        )
        clear_trace()
        raise HTTPException(status_code=500, detail="공정 등록에 실패했습니다.")

    emit_event(
        step_key="save_db",
        step_order=2,
        event_type="save",
        result="success",
        connector_type="database",
        payload_summary={
            "process_type_key": insert_data.get("source", source),
            "row_saved": True,
        },
    )

    record = res.data[0]
    is_manual = (source == "MANUAL")
    display_name = (
        record.get("process_name_manual")
        or record.get("process_lv4")
        or record.get("process_lv3")
        or record.get("process_id", "")
    )
    emit_event(
        step_key="read_result",
        step_order=3,
        event_type="read",
        result="success",
        connector_type="api",
        payload_summary={
            "process_type_key": record.get("source", source),
            "row_count": 1,
        },
    )

    # ═══ Document Auto Activation Hook (TASK 23) ═══
    try:
        from watch_engine.document import activate_documents_for_workflow
        from db.supabase_client import get_supabase as get_sb_client

        activate_documents_for_workflow(
            get_sb_client(),
            flow_key="process_registration",
            trace_id=f"procreg_{record.get('id', '')}",
            tenant_id=str(factory_id),
            factory_id=factory_id,
            actor_id="user",
            workflow_context={
                "process_name": display_name,
                "process_source": source,
                "process_id": record.get("process_id"),
            },
        )
    except Exception as _doc_err:
        import logging

        logging.getLogger("watch_engine.document.hook").warning(
            "Document activation hook failed (non-blocking): %s", _doc_err
        )
    # ═══ End Document Hook ═══

    clear_trace()
    return {
        "status":  "success",
        "message": "공정이 추가됐습니다.",
        "data":    {**record, "display_name": display_name, "is_manual": is_manual, "source_badge": SOURCE_BADGE.get(source, source)},
    }


# ──────────────────────────────────────────────
# POST /factory-process/{factory_id}/processes/bulk
# ──────────────────────────────────────────────
@router.post("/{factory_id}/processes/bulk")
async def bulk_add_factory_processes(factory_id: str, body: dict, current: dict = Depends(get_current_user)):
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)
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
async def delete_factory_process(factory_id: str, process_record_id: str, current: dict = Depends(get_current_user)):
    """
    process_record_id = factory_process.id (UUID)
    MANUAL / KCSC 공정 포함 모든 공정 soft delete 가능.
    """
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)
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
async def update_factory_process(factory_id: str, process_record_id: str, body: ProcessUpdateBody, current: dict = Depends(get_current_user)):
    """
    process_record_id = factory_process.id (UUID)
    수정 가능 필드(legacy): process_name_manual, process_lv1, process_lv2, process_lv3, is_primary
    STEP4: canonical 3-field(hazard_codes/worker_count/activity_types)는 sparse(explicit-null clear). 기존 필드 semantics 불변.
    """
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)
    # process row 존재확인(id+factory_id+is_active). foreign/missing/inactive → 404
    chk = supabase.table("factory_process").select("id").eq(
        "id", process_record_id
    ).eq("factory_id", factory_id).eq("is_active", True).limit(1).execute()
    if not chk.data:
        raise HTTPException(status_code=404, detail="등록된 공정을 찾을 수 없습니다.")

    provided = body.dict(exclude_unset=True)
    update_data = {}
    for k, v in provided.items():
        if k in PROCESS_CANONICAL_NULL_CLEAR_FIELDS:
            update_data[k] = v            # None/0/[] 그대로(explicit-null clear)
        elif v is not None:
            update_data[k] = v            # legacy: None skip
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
    current: dict = Depends(get_current_user),
):
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)
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
