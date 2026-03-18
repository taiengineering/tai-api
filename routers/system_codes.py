# routers/system_codes.py
from fastapi import APIRouter
from db.supabase_client import get_supabase

router = APIRouter(prefix="/system-codes", tags=["system_codes"])

@router.get("")
def get_all_codes():
    """전체 시스템 코드 조회"""
    supabase = get_supabase()
    return supabase.table("system_codes")\
        .select("*")\
        .eq("is_active", True)\
        .order("category")\
        .order("sort_order")\
        .execute().data

@router.get("/{category}")
def get_codes_by_category(category: str):
    """카테고리별 시스템 코드 조회"""
    supabase = get_supabase()
    return supabase.table("system_codes")\
        .select("code, code_name, code_value, description, sort_order")\
        .eq("category", category)\
        .eq("is_active", True)\
        .order("sort_order")\
        .execute().data

@router.get("/multi/{categories}")
def get_codes_by_categories(categories: str):
    """
    여러 카테고리 한번에 조회
    예: /system-codes/multi/building_use,site_type,industry_type
    """
    supabase = get_supabase()
    category_list = categories.split(",")
    result = supabase.table("system_codes")\
        .select("category, category_name, code, code_name, code_value, sort_order")\
        .in_("category", category_list)\
        .eq("is_active", True)\
        .order("category")\
        .order("sort_order")\
        .execute().data

    # 카테고리별로 그룹핑
    grouped = {}
    for item in result:
        cat = item["category"]
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append({
            "code":       item["code"],
            "code_name":  item["code_name"],
            "code_value": item["code_value"],
            "sort_order": item["sort_order"],
        })
    return grouped

