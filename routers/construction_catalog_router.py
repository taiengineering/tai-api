from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from db.supabase_client import get_supabase
from services.construction_catalog_svc import (
    list_kcsc_processes,
    list_kcsc_works_all,
    list_kcsc_works_by_process,
)

router = APIRouter(tags=["건설안전"])


@router.get("/kcsc/processes")
async def kcsc_processes(
    search: Optional[str] = Query(None, description="공정명 검색 (부분일치). 예) 굴착"),
    construction_type: Optional[str] = Query(None, description="BUILDING / CIVIL / COMMON"),
    work_type_code: Optional[str] = Query(None, description="작업 유형 코드. 예) EXCAVATION"),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
):
    supabase = get_supabase()
    try:
        return {"status": "success", "data": list_kcsc_processes(supabase, search, construction_type, work_type_code, page, size)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/kcsc/works")
async def kcsc_works_all(
    is_hazardous: Optional[bool] = Query(None),
    work_type_code: Optional[str] = Query(None),
    hazard_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(100, ge=1, le=300),
):
    supabase = get_supabase()
    try:
        return {"status": "success", "data": list_kcsc_works_all(supabase, is_hazardous, work_type_code, hazard_type, search, page, size)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/kcsc/works/{process_id}")
async def kcsc_works_by_process(process_id: str):
    supabase = get_supabase()
    try:
        return {"status": "success", "data": list_kcsc_works_by_process(supabase, process_id)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
