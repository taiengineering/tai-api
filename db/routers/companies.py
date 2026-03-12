from fastapi import APIRouter
from db.supabase_client import get_supabase

router = APIRouter(prefix="/companies", tags=["companies"])

@router.get("")
def get_companies():

    supabase = get_supabase()

    result = (
        supabase.table("companies")
        .select("*")
        .execute()
    )

    return result.data
