# routers/system_codes.py v2.0.0
# 전역변수 관리 API
#
# 기존:
#   GET /system-codes/multi?categories=   — 다중 카테고리 조회 (유지)
#   GET /system-codes                     — 단일 카테고리 조회 (유지)
#
# 신규 (전역변수 관리 페이지용):
#   GET  /system-codes/all                — 전체 카테고리+코드 그룹화
#   GET  /system-codes/categories         — 카테고리 목록만 (code_count 포함)
#   POST /system-codes                    — 코드 추가 (is_system 항상 false)
#   PATCH /system-codes/{id}             — 코드 수정 (is_system=true 403)
#   DELETE /system-codes/{id}            — 코드 삭제 (is_system=true 403)
#   POST /system-codes/category          — 카테고리 추가
#   PATCH /system-codes/category/{category} — 카테고리 수정

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
from datetime import datetime
import os
from supabase import create_client

router = APIRouter(prefix="/system-codes", tags=["system-codes"])

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ============================================================
# 기존 API — 하위 호환 유지
# ============================================================

@router.get("/multi")
def get_multi_codes(categories: str = Query(..., description="콤마 구분 카테고리 목록")):
    """다중 카테고리 코드 조회 (기존 API 유지)"""
    supabase = get_supabase()
    cat_list = [c.strip() for c in categories.split(",") if c.strip()]

    res = supabase.table("system_codes").select(
        "category, code, code_name, code_value, sort_order, description"
    ).in_("category", cat_list).eq("is_active", True).order("sort_order").execute()

    result = {}
    for row in (res.data or []):
        cat = row["category"]
        if cat not in result:
            result[cat] = []
        result[cat].append(row)

    return {"status": "success", "data": result}


@router.get("/search")
def search_codes(
    q:        Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    page:     int           = Query(1, ge=1),
    page_size: int          = Query(20, ge=1, le=200),
):
    """코드 검색"""
    supabase = get_supabase()
    offset = (page - 1) * page_size
    query = supabase.table("system_codes").select("*", count="exact").eq("is_active", True)
    if category:
        query = query.eq("category", category)
    if q:
        query = query.or_(f"code_name.ilike.%{q}%,code.ilike.%{q}%,category.ilike.%{q}%")
    query = query.order("category").order("sort_order").range(offset, offset + page_size - 1)
    res = query.execute()
    return {
        "status": "success",
        "data": {"items": res.data or [], "total": res.count or 0, "page": page, "page_size": page_size}
    }


# ============================================================
# 신규 — 전역변수 관리 페이지용
# ============================================================

@router.get("/all")
def get_all_codes(is_active: Optional[bool] = Query(None)):
    """
    전체 카테고리 + 코드 한 번에 반환 (카테고리별 그룹화)
    응답 구조:
    {
      "categories": [...],           ← 카테고리 목록 + code_count
      "codes_by_category": { category: [...] },  ← 카테고리별 코드
      "stats": { category_cnt, total_cnt, system_cnt, user_cnt }
    }
    """
    supabase = get_supabase()

    query = supabase.table("system_codes").select("*")
    if is_active is not None:
        query = query.eq("is_active", is_active)
    query = query.order("category").order("sort_order")
    res = query.execute()
    items = res.data or []

    # 카테고리별 그룹화
    categories_map = {}
    codes_by_category = {}

    for row in items:
        cat = row["category"]
        if cat not in categories_map:
            categories_map[cat] = {
                "category":      cat,
                "category_name": row.get("category_name", cat),
                "description":   row.get("description", ""),
                "is_system":     row.get("is_system", False),
                "is_active":     row.get("is_active", True),
                "code_count":    0,
                "system_count":  0,
            }
            codes_by_category[cat] = []

        categories_map[cat]["code_count"] += 1
        if row.get("is_system"):
            categories_map[cat]["system_count"] += 1
        codes_by_category[cat].append(row)

    categories = sorted(categories_map.values(), key=lambda x: x["category"])

    system_cnt = sum(1 for r in items if r.get("is_system"))
    return {
        "status": "success",
        "data": {
            "categories":        categories,
            "codes_by_category": codes_by_category,
            "stats": {
                "category_cnt": len(categories),
                "total_cnt":    len(items),
                "system_cnt":   system_cnt,
                "user_cnt":     len(items) - system_cnt,
            }
        }
    }


@router.get("/categories")
def get_categories(
    is_system: Optional[bool] = Query(None),
    is_active: Optional[bool] = Query(None),
):
    """카테고리 목록만 반환 (code_count 포함)"""
    supabase = get_supabase()

    query = supabase.table("system_codes").select(
        "category, category_name, description, is_system, is_active, sort_order"
    )
    if is_active is not None:
        query = query.eq("is_active", is_active)
    if is_system is not None:
        query = query.eq("is_system", is_system)

    res = query.order("category").execute()
    items = res.data or []

    # 카테고리별 집계
    seen = {}
    for row in items:
        cat = row["category"]
        if cat not in seen:
            seen[cat] = {
                "category":      cat,
                "category_name": row.get("category_name", cat),
                "description":   row.get("description", ""),
                "is_system":     row.get("is_system", False),
                "is_active":     row.get("is_active", True),
                "code_count":    0,
            }
        seen[cat]["code_count"] += 1

    categories = sorted(seen.values(), key=lambda x: x["category"])
    return {
        "status": "success",
        "data": {
            "items": categories,
            "total": len(categories),
        }
    }


@router.get("/{category}")
def get_codes_by_category(
    category:  str,
    is_active: Optional[bool] = Query(None),
):
    """특정 카테고리의 코드 목록"""
    supabase = get_supabase()
    query = supabase.table("system_codes").select("*").eq("category", category)
    if is_active is not None:
        query = query.eq("is_active", is_active)
    res = query.order("sort_order").execute()
    return {
        "status": "success",
        "data": {"items": res.data or [], "total": len(res.data or [])}
    }


# ============================================================
# 카테고리 추가
# ============================================================

@router.post("/category")
def create_category(body: dict):
    """
    카테고리 추가
    body: { category, category_name, description?, is_active? }
    """
    supabase = get_supabase()

    category = (body.get("category") or "").strip()
    category_name = (body.get("category_name") or "").strip()

    if not category:
        raise HTTPException(status_code=400, detail="category(카테고리 키)는 필수입니다")
    if not category_name:
        raise HTTPException(status_code=400, detail="category_name은 필수입니다")

    # 영문+언더바만 허용
    import re
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', category):
        raise HTTPException(status_code=400, detail="category 키는 영문자, 숫자, 언더바(_)만 허용됩니다")

    # 중복 확인
    existing = supabase.table("system_codes").select("id").eq("category", category).limit(1).execute()
    if existing.data:
        raise HTTPException(status_code=400, detail="이미 존재하는 카테고리 키입니다")

    # 카테고리 대표 코드 없이 카테고리만 추가 (더미 row 방식 대신, 실제 코드 추가 시 category_name 자동 부여)
    # 카테고리는 실제 코드 데이터로 존재하므로 초기 코드 1개 필요
    # → 빈 카테고리는 system_codes 구조상 불가 → 안내 코드 없이 category_name만 저장하는 메타 방식 사용
    # 실용적 해결: 카테고리 대표 행을 code='__meta__'로 저장 (프론트에서 필터)
    # → 더 깔끔한 방법: 카테고리 추가 시 placeholder code 없이 category_name만 반환, 실제 코드 추가 시 category_name 전달

    # 여기서는 첫 번째 코드 추가 시 카테고리가 생성되는 방식이므로
    # 카테고리 추가 API는 검증 후 클라이언트에 "준비됨" 반환
    # 실제 DB 저장은 첫 코드 추가 시 이루어짐
    return {
        "status": "success",
        "message": f"카테고리 '{category}'가 준비됐습니다. 코드를 추가해주세요.",
        "data": {
            "category":      category,
            "category_name": category_name,
            "description":   body.get("description", ""),
            "is_active":     body.get("is_active", True),
        }
    }


# ============================================================
# 코드 추가
# ============================================================

@router.post("")
def create_code(body: dict):
    """
    코드 추가 (is_system 항상 false)
    body: { category, category_name, code, code_name, code_value?, description?, sort_order? }
    """
    supabase = get_supabase()

    category = (body.get("category") or "").strip()
    code     = (body.get("code") or "").strip()
    code_name = (body.get("code_name") or "").strip()

    if not category:
        raise HTTPException(status_code=400, detail="category는 필수입니다")
    if not code:
        raise HTTPException(status_code=400, detail="code는 필수입니다")
    if not code_name:
        raise HTTPException(status_code=400, detail="code_name은 필수입니다")

    # 동일 카테고리 내 code 중복 확인
    existing = supabase.table("system_codes").select("id").eq(
        "category", category
    ).eq("code", code).limit(1).execute()
    if existing.data:
        raise HTTPException(status_code=400, detail="이미 존재하는 코드입니다")

    # sort_order 자동 계산 (미입력 시 현재 최대+10)
    sort_order = body.get("sort_order")
    if sort_order is None:
        max_res = supabase.table("system_codes").select("sort_order").eq(
            "category", category
        ).order("sort_order", desc=True).limit(1).execute()
        sort_order = ((max_res.data[0]["sort_order"] or 0) + 10) if max_res.data else 10

    insert_data = {
        "category":      category,
        "category_name": body.get("category_name", category),
        "code":          code,
        "code_name":     code_name,
        "code_value":    body.get("code_value"),
        "description":   body.get("description"),
        "sort_order":    sort_order,
        "is_active":     body.get("is_active", True),
        "is_system":     False,   # 항상 false
        "state":         "사용",
        "created_at":    datetime.now().isoformat(),
        "updated_at":    datetime.now().isoformat(),
    }

    res = supabase.table("system_codes").insert(insert_data).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="코드 추가 실패")

    return {
        "status":  "success",
        "message": "코드가 추가됐습니다.",
        "data":    res.data[0]
    }


# ============================================================
# 코드 수정
# ============================================================

@router.patch("/{code_id}")
def update_code(code_id: str, body: dict):
    """
    코드 수정
    - is_system=true 인 코드는 403 반환
    - code 필드는 수정 불가
    """
    supabase = get_supabase()

    # 대상 코드 조회
    res = supabase.table("system_codes").select("*").eq("id", code_id).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="코드를 찾을 수 없습니다")

    current = res.data
    if current.get("is_system"):
        raise HTTPException(status_code=403, detail="시스템 코드는 수정할 수 없습니다")

    # 수정 가능 필드만 허용 (code 필드 수정 불가)
    allowed = {"code_name", "code_value", "description", "sort_order", "is_active", "state", "category_name"}
    update_data = {k: v for k, v in body.items() if k in allowed}

    if not update_data:
        raise HTTPException(status_code=400, detail="수정할 항목이 없습니다")

    update_data["updated_at"] = datetime.now().isoformat()

    updated = supabase.table("system_codes").update(update_data).eq("id", code_id).execute()
    if not updated.data:
        raise HTTPException(status_code=500, detail="수정 실패")

    return {
        "status":  "success",
        "message": "수정됐습니다.",
        "data":    updated.data[0]
    }


# ============================================================
# 코드 삭제
# ============================================================

@router.delete("/{code_id}")
def delete_code(code_id: str):
    """
    코드 삭제
    - is_system=true 인 코드는 403 반환
    """
    supabase = get_supabase()

    res = supabase.table("system_codes").select("id, code, category, is_system").eq(
        "id", code_id
    ).single().execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="코드를 찾을 수 없습니다")

    if res.data.get("is_system"):
        raise HTTPException(status_code=403, detail="시스템 코드는 삭제할 수 없습니다")

    supabase.table("system_codes").delete().eq("id", code_id).execute()

    return {
        "status":  "success",
        "message": "코드가 삭제됐습니다.",
        "data":    {"id": code_id, "code": res.data.get("code"), "category": res.data.get("category")}
    }


# ============================================================
# 테스트
# ============================================================

@router.get("/")
def get_all_active(category: Optional[str] = Query(None)):
    """기본 조회 (하위 호환)"""
    supabase = get_supabase()
    query = supabase.table("system_codes").select("*").eq("is_active", True)
    if category:
        query = query.eq("category", category)
    res = query.order("category").order("sort_order").execute()
    return {"status": "success", "data": {"items": res.data or [], "total": len(res.data or [])}}
