import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from db.supabase_client import get_supabase
from schemas.construction import SiteCreate, SitePatch
from services.construction_sites_svc import (
    build_site_create_payload,
    build_site_stats,
    build_site_update_payload,
    list_sites as list_sites_svc,
    run_diagnose_site,
    run_generate_site_schedules,
)
from services.construction_svc import (
    auto_diagnose_and_schedule,
    create_factory_for_site,
    run_diagnosis,
    run_generate_schedules,
)
from utils.logger import get_logger

log = get_logger(__name__)
router = APIRouter(tags=["건설안전"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_uuid(value: str) -> str:
    try:
        uuid.UUID(value)
        return value
    except ValueError:
        raise HTTPException(status_code=400, detail="유효하지 않은 ID 형식입니다.")


@router.get("/sites")
async def list_sites(
    company_id: Optional[str] = Query(None),
    status_code: Optional[str] = Query(None),
    site_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    supabase = get_supabase()
    try:
        return {"status": "success", "data": list_sites_svc(supabase, company_id, status_code, site_type, search, page, size)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sites")
async def create_site(body: SiteCreate):
    supabase = get_supabase()
    try:
        data = build_site_create_payload(body, _now_iso)
        res = supabase.table("construction_sites").insert(data).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="등록 실패")
        site = res.data[0]

        factory_id = create_factory_for_site(supabase, site, _now_iso)
        auto_result = auto_diagnose_and_schedule(supabase, factory_id, site) if factory_id else {}
        updated = supabase.table("construction_sites").select("*").eq("id", site["id"]).single().execute()
        final_site = updated.data if updated.data else site
        return {"status": "success", "data": final_site, "auto": {"factory_id": factory_id, "diagnosis": auto_result.get("diagnosis"), "schedules": auto_result.get("schedules")}}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sites/{site_id}")
async def get_site(site_id: str):
    site_id = _validate_uuid(site_id)
    supabase = get_supabase()
    res = supabase.table("construction_sites").select("*").eq("id", site_id).eq("is_active", True).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="현장을 찾을 수 없습니다.")
    return {"status": "success", "data": res.data[0]}


@router.patch("/sites/{site_id}")
async def update_site(site_id: str, body: SitePatch):
    site_id = _validate_uuid(site_id)
    supabase = get_supabase()
    try:
        data = body.model_dump(exclude_none=True)
        if not data:
            raise HTTPException(status_code=400, detail="수정할 항목이 없습니다.")
        site_res = supabase.table("construction_sites").select("site_type,contract_amount,total_workers").eq("id", site_id).limit(1).execute()
        cur = site_res.data[0] if site_res.data else {}
        data = build_site_update_payload(body, cur, _now_iso)
        res = supabase.table("construction_sites").update(data).eq("id", site_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="현장을 찾을 수 없습니다.")
        return {"status": "success", "data": res.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/sites/{site_id}")
async def delete_site(site_id: str):
    site_id = _validate_uuid(site_id)
    supabase = get_supabase()
    res = supabase.table("construction_sites").update({"is_active": False, "updated_at": _now_iso()}).eq("id", site_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="현장을 찾을 수 없습니다.")
    return {"status": "success", "message": "삭제됐습니다."}


@router.get("/sites/{site_id}/stats")
async def get_site_stats(site_id: str):
    site_id = _validate_uuid(site_id)
    supabase = get_supabase()
    try:
        site_res = supabase.table("construction_sites").select("*").eq("id", site_id).limit(1).execute()
        if not site_res.data:
            raise HTTPException(status_code=404, detail="현장을 찾을 수 없습니다.")
        site = site_res.data[0]
        proc_res = supabase.table("construction_site_processes").select("id,status_code", count="exact").eq("site_id", site_id).eq("is_active", True).execute()
        work_res = supabase.table("construction_works").select("id,status_code,ptw_status", count="exact").eq("site_id", site_id).eq("is_active", True).execute()
        worker_res = supabase.table("construction_workers").select("id,worker_type,entry_status", count="exact").eq("site_id", site_id).eq("is_active", True).execute()
        insp_res = supabase.table("construction_inspections").select("id,overall_result", count="exact").eq("site_id", site_id).eq("is_active", True).execute()
        return {"status": "success", "data": build_site_stats(site_id, site, proc_res.data or [], work_res.data or [], worker_res.data or [], insp_res.data or [])}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sites/{site_id}/diagnose")
async def diagnose_site(site_id: str):
    site_id = _validate_uuid(site_id)
    supabase = get_supabase()
    try:
        _, factory_id, diag = run_diagnose_site(
            supabase,
            site_id,
            lambda sb, site: create_factory_for_site(sb, site, _now_iso),
            run_diagnosis,
        )
        try:
            from routers.inspection_set_auto import auto_create_inspection_sets_from_diagnosis

            company_res = supabase.table("factories").select("company_id").eq("id", factory_id).limit(1).execute()
            company_id = company_res.data[0].get("company_id") if company_res.data else None
            auto_create_inspection_sets_from_diagnosis(supabase, factory_id, company_id, diag.get("applicable_rules") or [])
        except Exception as e:
            log.error("[AUTO_INSPECT_SETS] diagnose_site 자동생성 실패 (무시): %s", e, exc_info=True)
        return {"status": "success", "data": {"site_id": site_id, "factory_id": factory_id, "applicable_rules": diag["applicable_count"], "diagnosis_id": diag["diagnosis_id"], "by_obligation_type": diag["by_obligation_type"]}}
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sites/{site_id}/generate-schedules")
async def generate_schedules(site_id: str):
    site_id = _validate_uuid(site_id)
    supabase = get_supabase()
    try:
        factory_id, sched = run_generate_site_schedules(supabase, site_id, run_generate_schedules)
        return {
            "status": "success",
            "data": {
                "site_id": site_id,
                "factory_id": factory_id,
                "created": sched["created"],
                "skipped": sched["skipped"],
                "total_rules": sched["total_rules"],
                "message": f"{sched['created']}건 일정 생성, {sched['skipped']}건 중복 스킵",
            },
        }
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
