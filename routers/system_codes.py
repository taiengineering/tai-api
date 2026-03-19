# routers/system_codes.py
from fastapi import APIRouter, Query
from typing import List
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


@router.get("/multi")
def get_codes_by_categories(
    categories: str = Query(..., description="쉼표로 구분된 카테고리 목록. 예: user_role,user_status,company_type")
):
    """
    여러 카테고리 한번에 조회
    호출: GET /system-codes/multi?categories=user_role,user_status
    """
    supabase = get_supabase()
    category_list = [c.strip() for c in categories.split(",")]

    result = supabase.table("system_codes")\
        .select("category, category_name, code, code_name, description, sort_order")\
        .in_("category", category_list)\
        .eq("is_active", True)\
        .order("category")\
        .order("sort_order")\
        .execute().data

    # 카테고리별 그룹핑
    grouped = {}
    for item in result:
        cat = item["category"]
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append({
            "code":        item["code"],
            "code_name":   item["code_name"],
            "description": item.get("description"),
            "sort_order":  item["sort_order"],
        })
    return grouped


@router.get("/{category}")
def get_codes_by_category(category: str):
    """
    카테고리별 시스템 코드 단건 조회
    호출: GET /system-codes/user_role
    """
    supabase = get_supabase()
    return supabase.table("system_codes")\
        .select("code, code_name, description, sort_order")\
        .eq("category", category)\
        .eq("is_active", True)\
        .order("sort_order")\
        .execute().data
