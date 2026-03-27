from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from db.supabase_client import get_supabase

router = APIRouter(prefix="/inspection-sets", tags=["inspection_sets"])


@router.get("")
def get_inspection_sets(
    factory_id: Optional[str] = Query(None, description="시설 ID"),
    source: Optional[str] = Query(None, description="소스: MANUAL / LEGAL_ENGINE"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    supabase = get_supabase()
    query = supabase.table("inspection_sets").select("*", count="exact")

    if factory_id:
        query = query.eq("factory_id", factory_id)
    if source:
        query = query.eq("source", source)

    offset = (page - 1) * size
    res = query.order("created_at", desc=True)\
               .range(offset, offset + size - 1).execute()

    return {
        "status": "success",
        "data": {
            "items": res.data,
            "total": res.count or 0,
            "page": page,
            "size": size,
        }
    }


@router.get("/company/{company_id}")
def get_company_inspection_sets(company_id: str):
    supabase = get_supabase()
    result = supabase.table("inspection_sets")\
        .select("*").eq("company_id", company_id)\
        .order("created_at", desc=True).execute()
    return {"status": "success", "data": result.data}


@router.get("/factory/{factory_id}")
def get_factory_inspection_sets(factory_id: str):
    supabase = get_supabase()
    result = supabase.table("inspection_sets")\
        .select("*").eq("factory_id", factory_id)\
        .order("created_at", desc=True).execute()
    return {"status": "success", "data": result.data}


@router.get("/{inspection_set_id}")
def get_inspection_set(inspection_set_id: str):
    supabase = get_supabase()
    result = supabase.table("inspection_sets")\
        .select("*").eq("id", inspection_set_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="점검세트를 찾을 수 없습니다")
    return {"status": "success", "data": result.data}
