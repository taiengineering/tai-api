#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TAI Companies 라우터 - 사업장 등록/관리
전역변수: company_type / contract_status / industry_type

엔드포인트:
GET    /companies                    사업장 목록 조회
POST   /companies                    사업장 등록
GET    /companies/{id}               사업장 상세 조회
PATCH  /companies/{id}               사업장 수정
DELETE /companies/{id}               사업장 비활성화
GET    /companies/{id}/users         소속 회원 목록
GET    /companies/{id}/factories     소속 시설 목록
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from db.supabase_client import get_supabase

router = APIRouter(prefix="/companies", tags=["companies"])


# ============================================================
# 스키마
# ============================================================

class CompanyCreate(BaseModel):
    # 기본 정보 (필수)
    name:                str

    # 사업자 정보
    company_type_code:   Optional[str] = "002"   # company_type: 001=법인/002=개인/003=간이/004=공공/005=비영리
    business_number:     Optional[str] = None    # 사업자번호
    corporation_number:  Optional[str] = None    # 법인번호
    representative_name: Optional[str] = None    # 대표자명
    established_date:    Optional[str] = None    # 설립일

    # 업종 정보
    business_type:       Optional[str] = None    # 업태 (텍스트)
    business_category:   Optional[str] = None    # 업종 (텍스트)
    industry_type_code:  Optional[str] = None    # industry_type 전역변수

    # 연락처
    contact_phone:       Optional[str] = None
    contact_email:       Optional[str] = None
    phone:               Optional[str] = None
    fax:                 Optional[str] = None
    website_url:         Optional[str] = None

    # 주소
    zipcode:             Optional[str] = None
    address_road:        Optional[str] = None
    address_jibun:       Optional[str] = None
    address_detail:      Optional[str] = None
    address_sido:        Optional[str] = None
    address_sigungu:     Optional[str] = None
    address_dong:        Optional[str] = None

    # 기타
    employee_count:      Optional[int] = None
    logo_url:            Optional[str] = None


class CompanyUpdate(BaseModel):
    name:                Optional[str] = None
    company_type_code:   Optional[str] = None
    business_number:     Optional[str] = None
    corporation_number:  Optional[str] = None
    representative_name: Optional[str] = None
    established_date:    Optional[str] = None
    business_type:       Optional[str] = None
    business_category:   Optional[str] = None
    industry_type_code:  Optional[str] = None
    contact_phone:       Optional[str] = None
    contact_email:       Optional[str] = None
    phone:               Optional[str] = None
    fax:                 Optional[str] = None
    website_url:         Optional[str] = None
    zipcode:             Optional[str] = None
    address_road:        Optional[str] = None
    address_jibun:       Optional[str] = None
    address_detail:      Optional[str] = None
    address_sido:        Optional[str] = None
    address_sigungu:     Optional[str] = None
    address_dong:        Optional[str] = None
    employee_count:      Optional[int] = None
    logo_url:            Optional[str] = None
    status_code:         Optional[str] = None    # contract_status 전역변수


# ============================================================
# 1. 목록 조회
# ============================================================

@router.get("")
def get_companies(
    page:        int  = Query(default=1, ge=1),
    size:        int  = Query(default=20, ge=1, le=100),
    search:      Optional[str] = Query(default=None),
    status_code: Optional[str] = Query(default=None),
    sido:        Optional[str] = Query(default=None),
):
    supabase = get_supabase()
    query = supabase.table("companies").select("*", count="exact")

    if search:
        query = query.ilike("name", f"%{search}%")
    if status_code:
        query = query.eq("status_code", status_code)
    if sido:
        query = query.eq("address_sido", sido)

    offset = (page - 1) * size
    res = query.order("created_at", desc=True)\
               .range(offset, offset + size - 1)\
               .execute()

    return {
        "status": "success",
        "data": {
            "items":       res.data,
            "total":       res.count,
            "page":        page,
            "size":        size,
            "total_pages": -(-res.count // size) if res.count else 0,
        }
    }


# ============================================================
# 2. 사업장 등록
# ============================================================

@router.post("")
def create_company(req: CompanyCreate):
    supabase = get_supabase()

    # 사업자번호 중복 확인
    if req.business_number:
        dup = supabase.table("companies")\
            .select("id")\
            .eq("business_number", req.business_number)\
            .limit(1).execute()
        if dup.data:
            raise HTTPException(status_code=400, detail="이미 등록된 사업자번호입니다")

    # 법인번호 중복 확인
    if req.corporation_number:
        dup = supabase.table("companies")\
            .select("id")\
            .eq("corporation_number", req.corporation_number)\
            .limit(1).execute()
        if dup.data:
            raise HTTPException(status_code=400, detail="이미 등록된 법인번호입니다")

    now = datetime.now()
    company_code = f"COM-{now.strftime('%Y%m%d%H%M%S')}"

    data = {
        **req.dict(exclude_none=True),
        "company_code": company_code,
        "status_code":  "TRIAL",    # contract_status: 체험
        "is_active":    True,
        "created_at":   now.isoformat(),
        "updated_at":   now.isoformat(),
    }

    res = supabase.table("companies").insert(data).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="사업장 등록 실패")

    return {
        "status":  "success",
        "message": "사업장이 등록됐습니다",
        "data":    res.data[0],
    }


# ============================================================
# 3. 상세 조회
# ============================================================

@router.get("/{company_id}")
def get_company(company_id: str):
    supabase = get_supabase()
    res = supabase.table("companies")\
        .select("*")\
        .eq("id", company_id)\
        .single().execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="사업장을 찾을 수 없습니다")

    return {"status": "success", "data": res.data}


# ============================================================
# 4. 수정
# ============================================================

@router.patch("/{company_id}")
def update_company(company_id: str, req: CompanyUpdate):
    supabase = get_supabase()

    existing = supabase.table("companies")\
        .select("id").eq("id", company_id).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="사업장을 찾을 수 없습니다")

    update_data = {k: v for k, v in req.dict().items() if v is not None}
    update_data["updated_at"] = datetime.now().isoformat()

    res = supabase.table("companies")\
        .update(update_data).eq("id", company_id).execute()

    return {
        "status":  "success",
        "message": "사업장 정보가 수정됐습니다",
        "data":    res.data[0] if res.data else {},
    }


# ============================================================
# 5. 비활성화
# ============================================================

@router.delete("/{company_id}")
def delete_company(company_id: str):
    supabase = get_supabase()

    existing = supabase.table("companies")\
        .select("id").eq("id", company_id).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="사업장을 찾을 수 없습니다")

    supabase.table("companies").update({
        "is_active":   False,
        "status_code": "CANCELLED",   # contract_status: 해지
        "updated_at":  datetime.now().isoformat(),
    }).eq("id", company_id).execute()

    return {"status": "success", "message": "사업장이 비활성화됐습니다"}


# ============================================================
# 6. 소속 회원 목록
# ============================================================

@router.get("/{company_id}/users")
def get_company_users(company_id: str):
    supabase = get_supabase()
    res = supabase.table("users")\
        .select("id, name, email, phone, role_code, status_code, department, position, last_login_at")\
        .eq("company_id", company_id)\
        .order("created_at", desc=True).execute()

    return {"status": "success", "data": {"items": res.data, "total": len(res.data)}}


# ============================================================
# 7. 소속 시설 목록
# ============================================================

@router.get("/{company_id}/factories")
def get_company_factories(company_id: str):
    supabase = get_supabase()
    res = supabase.table("factories")\
        .select("id, name, site_type, address_road, employee_count, status_code, is_active")\
        .eq("company_id", company_id)\
        .order("created_at", desc=True).execute()

    return {"status": "success", "data": {"items": res.data, "total": len(res.data)}}
