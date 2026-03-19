#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TAI Factories 라우터 - 시설 등록/관리
전역변수: user_status / site_type / condition_code

엔드포인트:
GET    /factories                시설 목록 조회
POST   /factories                시설 등록
GET    /factories/{id}           시설 상세 조회
PATCH  /factories/{id}           시설 수정
DELETE /factories/{id}           시설 비활성화
GET    /factories/{id}/users     소속 회원 목록
GET    /factories/{id}/buildings 소속 건물 목록
POST   /factories/{id}/legal     법령 판정 실행
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from db.supabase_client import get_supabase

router = APIRouter(prefix="/factories", tags=["factories"])


# ============================================================
# 스키마
# ============================================================

class FactoryCreate(BaseModel):
    # 필수
    company_id:  str
    name:        str

    # 기본 정보
    site_type:              Optional[str] = None    # site_type 전역변수
    ksic_code:              Optional[str] = None    # KSIC 산업분류 코드
    ksic_name:              Optional[str] = None    # KSIC 산업분류명
    industry_type_code:     Optional[str] = None    # industry_type 전역변수
    building_use_code:      Optional[str] = None    # 건물용도 코드

    # 담당자
    manager_name:           Optional[str] = None
    manager_phone:          Optional[str] = None
    manager_email:          Optional[str] = None

    # 주소
    zipcode:                Optional[str] = None
    address_road:           Optional[str] = None
    address_jibun:          Optional[str] = None
    address_detail:         Optional[str] = None
    address_sido:           Optional[str] = None
    address_sigungu:        Optional[str] = None
    address_dong:           Optional[str] = None
    latitude:               Optional[float] = None
    longitude:              Optional[float] = None

    # condition_code 기반 법령 판정 조건값
    employee_count:         Optional[int] = None    # 상시근로자수 (명)
    contractor_count:       Optional[int] = None    # 외주인원수 (명)
    building_area:          Optional[float] = None  # 연면적 (㎡)
    land_area:              Optional[float] = None  # 대지면적 (㎡)
    floor_count:            Optional[int] = None    # 지상 층수
    underground_floor_count: Optional[int] = None   # 지하 층수
    completion_year:        Optional[int] = None    # 준공연도
    electrical_capacity_kw: Optional[float] = None  # 전기용량 (kW)
    transformer_capacity_kva: Optional[float] = None # 변압기용량 (kVA)
    gas_capacity_m3:        Optional[float] = None  # 가스용량 (㎥)
    gas_capacity_kg:        Optional[float] = None  # 가스저장량 (kg)
    boiler_capacity_kw:     Optional[float] = None  # 보일러용량 (kW)
    boiler_capacity_th:     Optional[float] = None  # 보일러증발량 (t/h)
    elevator_count:         Optional[int] = None    # 승강기 대수
    annual_energy_toe:      Optional[float] = None  # 연간에너지사용량 (TOE)
    construction_amount:    Optional[float] = None  # 건설공사금액 (원)
    occupant_capacity:      Optional[int] = None    # 수용인원

    # 불리언 조건값
    is_factory_registered:  Optional[bool] = False
    is_hazardous_material:  Optional[bool] = False
    is_multi_use:           Optional[bool] = False
    hazardous_material:     Optional[bool] = False
    hazardous_material_type: Optional[str] = None
    fire_facility_required: Optional[bool] = False
    safety_manager_required: Optional[bool] = False
    special_use_flag:       Optional[bool] = False

    remarks:                Optional[str] = None


class FactoryUpdate(BaseModel):
    name:                   Optional[str] = None
    site_type:              Optional[str] = None
    ksic_code:              Optional[str] = None
    ksic_name:              Optional[str] = None
    industry_type_code:     Optional[str] = None
    building_use_code:      Optional[str] = None
    manager_name:           Optional[str] = None
    manager_phone:          Optional[str] = None
    manager_email:          Optional[str] = None
    zipcode:                Optional[str] = None
    address_road:           Optional[str] = None
    address_jibun:          Optional[str] = None
    address_detail:         Optional[str] = None
    address_sido:           Optional[str] = None
    address_sigungu:        Optional[str] = None
    address_dong:           Optional[str] = None
    latitude:               Optional[float] = None
    longitude:              Optional[float] = None
    employee_count:         Optional[int] = None
    contractor_count:       Optional[int] = None
    building_area:          Optional[float] = None
    floor_count:            Optional[int] = None
    underground_floor_count: Optional[int] = None
    electrical_capacity_kw: Optional[float] = None
    transformer_capacity_kva: Optional[float] = None
    gas_capacity_m3:        Optional[float] = None
    gas_capacity_kg:        Optional[float] = None
    boiler_capacity_kw:     Optional[float] = None
    boiler_capacity_th:     Optional[float] = None
    elevator_count:         Optional[int] = None
    annual_energy_toe:      Optional[float] = None
    construction_amount:    Optional[float] = None
    is_factory_registered:  Optional[bool] = None
    is_hazardous_material:  Optional[bool] = None
    is_multi_use:           Optional[bool] = None
    status_code:            Optional[str] = None
    remarks:                Optional[str] = None


# ============================================================
# 1. 목록 조회
# ============================================================

@router.get("")
def get_factories(
    page:        int  = Query(default=1, ge=1),
    size:        int  = Query(default=20, ge=1, le=100),
    company_id:  Optional[str] = Query(default=None),
    search:      Optional[str] = Query(default=None),
    site_type:   Optional[str] = Query(default=None),
    sido:        Optional[str] = Query(default=None),
    status_code: Optional[str] = Query(default=None),
):
    supabase = get_supabase()
    query = supabase.table("factories").select("*", count="exact")

    if company_id:  query = query.eq("company_id", company_id)
    if search:      query = query.ilike("name", f"%{search}%")
    if site_type:   query = query.eq("site_type", site_type)
    if sido:        query = query.eq("address_sido", sido)
    if status_code: query = query.eq("status_code", status_code)

    offset = (page - 1) * size
    res = query.order("created_at", desc=True)\
               .range(offset, offset + size - 1).execute()

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
# 2. 시설 등록
# ============================================================

@router.post("")
def create_factory(req: FactoryCreate):
    supabase = get_supabase()

    # 회사 존재 확인
    company = supabase.table("companies")\
        .select("id").eq("id", req.company_id).single().execute()
    if not company.data:
        raise HTTPException(status_code=404, detail="사업장(회사)을 찾을 수 없습니다")

    now = datetime.now()
    factories_code = f"FAC-{now.strftime('%Y%m%d%H%M%S')}"

    data = {
        **req.dict(exclude_none=True),
        "factories_code": factories_code,
        "status_code":    "ACTIVE",
        "is_active":      True,
        "created_at":     now.isoformat(),
        "updated_at":     now.isoformat(),
    }

    res = supabase.table("factories").insert(data).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="시설 등록 실패")

    return {
        "status":  "success",
        "message": "시설이 등록됐습니다",
        "data":    res.data[0],
    }


# ============================================================
# 3. 상세 조회
# ============================================================

@router.get("/{factory_id}")
def get_factory(factory_id: str):
    supabase = get_supabase()
    res = supabase.table("factories")\
        .select("*").eq("id", factory_id).single().execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다")

    return {"status": "success", "data": res.data}


# ============================================================
# 4. 수정
# ============================================================

@router.patch("/{factory_id}")
def update_factory(factory_id: str, req: FactoryUpdate):
    supabase = get_supabase()

    existing = supabase.table("factories")\
        .select("id").eq("id", factory_id).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다")

    update_data = {k: v for k, v in req.dict().items() if v is not None}
    update_data["updated_at"] = datetime.now().isoformat()

    res = supabase.table("factories")\
        .update(update_data).eq("id", factory_id).execute()

    return {
        "status":  "success",
        "message": "시설 정보가 수정됐습니다",
        "data":    res.data[0] if res.data else {},
    }


# ============================================================
# 5. 비활성화
# ============================================================

@router.delete("/{factory_id}")
def delete_factory(factory_id: str):
    supabase = get_supabase()

    existing = supabase.table("factories")\
        .select("id").eq("id", factory_id).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다")

    supabase.table("factories").update({
        "is_active":   False,
        "status_code": "INACTIVE",
        "updated_at":  datetime.now().isoformat(),
    }).eq("id", factory_id).execute()

    return {"status": "success", "message": "시설이 비활성화됐습니다"}


# ============================================================
# 6. 소속 회원 목록
# ============================================================

@router.get("/{factory_id}/users")
def get_factory_users(factory_id: str):
    supabase = get_supabase()
    res = supabase.table("users")\
        .select("id, name, email, phone, role_code, status_code, department, position")\
        .eq("factory_id", factory_id)\
        .order("created_at", desc=True).execute()

    return {"status": "success", "data": {"items": res.data, "total": len(res.data)}}


# ============================================================
# 7. 소속 건물 목록
# ============================================================

@router.get("/{factory_id}/buildings")
def get_factory_buildings(factory_id: str):
    supabase = get_supabase()
    res = supabase.table("buildings")\
        .select("id, name, building_use_code, floor_count, building_area, is_active")\
        .eq("factory_id", factory_id)\
        .order("created_at", desc=True).execute()

    return {"status": "success", "data": {"items": res.data, "total": len(res.data)}}


# ============================================================
# 8. 법령 판정 실행
# ============================================================

@router.post("/{factory_id}/legal")
def run_legal_engine(factory_id: str):
    from routers.legal_engine import apply_legal_rules
    supabase = get_supabase()
    try:
        result = apply_legal_rules(factory_id, supabase)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
