#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TAI Factories 라우터 - 시설 등록/관리 v2.4.0

v2.4.0 (LEGAL-CONSTRUCTION): 건설 법령 판정 입력 필드 6개 추가
  - subcontractor_count (int, 하도급 업체 수)
  - has_tower_crane / has_confined_space / has_asbestos_demo / has_blasting / has_diving (boolean, 위험시설)
v2.3.0 (LEGAL-FIELD): 법령 판정 입력 필드 5개 추가
  - has_safety_manager / has_high_pressure_gas / has_chemical_substance / has_boiler (boolean)
  - building_grade (int)
  (floor_count, gas_capacity_m3, transformer_capacity_kva 는 기존 스키마에 이미 존재)
v2.2.0 (B-CON-001): 건설 전용 필드 추가
  - construction_type (VARCHAR 20: 건축/토목/공통/기타)
  - subcontractor_worker_count (하도급 근로자 수)
v2.1.0: CHANGE / CLOSURE 이벤트 트리거 추가
v2.0.0: 담당자 관리 API 추가
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, date
from db.supabase_client import get_supabase

router = APIRouter(prefix="/factories", tags=["factories"])


# ============================================================
# 스키마
# ============================================================

class FactoryCreate(BaseModel):
    company_id:  str
    name:        str
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
    land_area:              Optional[float] = None
    floor_count:            Optional[int] = None
    underground_floor_count: Optional[int] = None
    completion_year:        Optional[int] = None
    electrical_capacity_kw: Optional[float] = None
    transformer_capacity_kva: Optional[float] = None
    gas_capacity_m3:        Optional[float] = None
    gas_capacity_kg:        Optional[float] = None
    boiler_capacity_kw:     Optional[float] = None
    boiler_capacity_th:     Optional[float] = None
    elevator_count:         Optional[int] = None
    annual_energy_toe:      Optional[float] = None
    construction_amount:    Optional[float] = None
    occupant_capacity:      Optional[int] = None
    is_factory_registered:  Optional[bool] = False
    is_hazardous_material:  Optional[bool] = False
    is_multi_use:           Optional[bool] = False
    hazardous_material:     Optional[bool] = False
    hazardous_material_type: Optional[str] = None
    fire_facility_required: Optional[bool] = False
    safety_manager_required: Optional[bool] = False
    special_use_flag:       Optional[bool] = False
    remarks:                Optional[str] = None
    # v2.2.0: 건설 전용 필드
    construction_type:            Optional[str] = None   # 건축/토목/공통/기타
    subcontractor_worker_count:   Optional[int] = 0      # 하도급 근로자 수
    # v2.3.0: 법령 판정 입력 필드 (산업/건축)
    has_safety_manager:      Optional[bool] = None
    has_high_pressure_gas:   Optional[bool] = None
    has_chemical_substance:  Optional[bool] = None
    has_boiler:              Optional[bool] = None
    building_grade:          Optional[int] = None
    # v2.4.0: 건설 법령 판정 입력 필드
    subcontractor_count:     Optional[int] = None
    has_tower_crane:         Optional[bool] = None
    has_confined_space:      Optional[bool] = None
    has_asbestos_demo:       Optional[bool] = None
    has_blasting:            Optional[bool] = None
    has_diving:              Optional[bool] = None


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
    # v2.2.0: 건설 전용 필드
    construction_type:            Optional[str] = None   # 건축/토목/공통/기타
    subcontractor_worker_count:   Optional[int] = None   # 하도급 근로자 수
    # v2.3.0: 법령 판정 입력 필드 (산업/건축)
    has_safety_manager:      Optional[bool] = None
    has_high_pressure_gas:   Optional[bool] = None
    has_chemical_substance:  Optional[bool] = None
    has_boiler:              Optional[bool] = None
    building_grade:          Optional[int] = None
    # v2.4.0: 건설 법령 판정 입력 필드
    subcontractor_count:     Optional[int] = None
    has_tower_crane:         Optional[bool] = None
    has_confined_space:      Optional[bool] = None
    has_asbestos_demo:       Optional[bool] = None
    has_blasting:            Optional[bool] = None
    has_diving:              Optional[bool] = None


class FactoryContactBody(BaseModel):
    contact_type: str
    name:         str
    phone:        str
    email:        Optional[str] = None
    position:     Optional[str] = None
    is_primary:   bool = False


class FactoryContactUpdate(BaseModel):
    contact_type: Optional[str] = None
    name:         Optional[str] = None
    phone:        Optional[str] = None
    email:        Optional[str] = None
    position:     Optional[str] = None
    is_primary:   Optional[bool] = None


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
    res = query.order("created_at", desc=True).range(offset, offset + size - 1).execute()
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
    company = supabase.table("companies").select("id").eq(
        "id", req.company_id
    ).single().execute()
    if not company.data:
        raise HTTPException(status_code=404, detail="사업장(회사)을 찾을 수 없습니다")
    now = datetime.now()
    data = {
        **req.dict(exclude_none=True),
        "factories_code": f"FAC-{now.strftime('%Y%m%d%H%M%S')}",
        "status_code":    "ACTIVE",
        "is_active":      True,
        "created_at":     now.isoformat(),
        "updated_at":     now.isoformat(),
    }
    res = supabase.table("factories").insert(data).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="시설 등록 실패")
    return {"status": "success", "message": "시설이 등록뙀습니다", "data": res.data[0]}


# ============================================================
# 3. 상세 조회
# ============================================================

@router.get("/{factory_id}")
def get_factory(factory_id: str):
    supabase = get_supabase()
    res = supabase.table("factories").select("*").eq(
        "id", factory_id
    ).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다")
    return {"status": "success", "data": res.data}


# ============================================================
# 4. 수정 (v2.2.0: 건설 필드 포함 + v2.1.0: CHANGE / CLOSURE 트리거)
# ============================================================

@router.patch("/{factory_id}")
async def update_factory(factory_id: str, req: FactoryUpdate):
    """
    v2.2.0: construction_type, subcontractor_worker_count 필드 저장·수정 가능
    v2.1.0: 실제 변경이 있으면 CHANGE 이벤트 트리거
            status_code='INACTIVE' 로 변경 시 CLOSURE 이벤트 트리거
    """
    supabase = get_supabase()
    existing = supabase.table("factories").select("id, status_code").eq(
        "id", factory_id
    ).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다")

    update_data = {k: v for k, v in req.dict().items() if v is not None}
    if not update_data:
        return {"status": "success", "message": "변경된 내용이 없습니다.", "data": {}}

    update_data["updated_at"] = datetime.now().isoformat()
    res = supabase.table("factories").update(update_data).eq(
        "id", factory_id
    ).execute()

    # 이벤트 트리거
    try:
        from routers.event_trigger import trigger_event_schedules
        new_status = update_data.get("status_code", "")
        if new_status == "INACTIVE":
            await trigger_event_schedules(
                factory_id = factory_id,
                event_type = "CLOSURE",
                event_date = date.today(),
            )
        else:
            await trigger_event_schedules(
                factory_id = factory_id,
                event_type = "CHANGE",
                event_date = date.today(),
            )
    except Exception as e:
        print(f"[FACTORIES] 이벤트 트리거 실패 (factory={factory_id}): {e}")

    return {
        "status":  "success",
        "message": "시설 정보가 수정똥습니다",
        "data":    res.data[0] if res.data else {},
    }


# ============================================================
# 5. 비활성화
# ============================================================

@router.delete("/{factory_id}")
def delete_factory(factory_id: str):
    supabase = get_supabase()
    existing = supabase.table("factories").select("id").eq(
        "id", factory_id
    ).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다")
    supabase.table("factories").update({
        "is_active":   False,
        "status_code": "INACTIVE",
        "updated_at":  datetime.now().isoformat(),
    }).eq("id", factory_id).execute()
    return {"status": "success", "message": "시설이 비활성화똥습니다"}


# ============================================================
# 6. 소속 회원 목록
# ============================================================

@router.get("/{factory_id}/users")
def get_factory_users(factory_id: str):
    supabase = get_supabase()
    res = supabase.table("users").select(
        "id, name, email, phone, role_code, status_code, department, position"
    ).eq("factory_id", factory_id).order("created_at", desc=True).execute()
    return {"status": "success", "data": {"items": res.data, "total": len(res.data)}}


# ============================================================
# 7. 소속 건물 목록
# ============================================================

@router.get("/{factory_id}/buildings")
def get_factory_buildings(factory_id: str):
    supabase = get_supabase()
    res = supabase.table("buildings").select(
        "id, name, building_use_code, floor_count, building_area, is_active"
    ).eq("factory_id", factory_id).order("created_at", desc=True).execute()
    return {"status": "success", "data": {"items": res.data, "total": len(res.data)}}


# ============================================================
# 8. 시설 담당자 목록
# ============================================================

@router.get("/{factory_id}/contacts")
def get_factory_contacts(factory_id: str):
    supabase = get_supabase()
    res = supabase.table("factory_contacts").select("*").eq(
        "factory_id", factory_id
    ).eq("is_active", True).order("is_primary", desc=True).order("sort_order").execute()
    return {"status": "success", "data": {"items": res.data or [], "total": len(res.data or [])}}


# ============================================================
# 9. 시설 담당자 추가
# ============================================================

@router.post("/{factory_id}/contacts")
def add_factory_contact(factory_id: str, body: FactoryContactBody):
    supabase = get_supabase()
    if body.is_primary:
        supabase.table("factory_contacts").update({"is_primary": False}).eq(
            "factory_id", factory_id
        ).eq("is_primary", True).execute()
    now = datetime.now().isoformat()
    res = supabase.table("factory_contacts").insert({
        "factory_id":   factory_id,
        "contact_type": body.contact_type,
        "name":         body.name,
        "phone":        body.phone,
        "email":        body.email,
        "position":     body.position,
        "is_primary":   body.is_primary,
        "is_active":    True,
        "created_at":   now,
        "updated_at":   now,
    }).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="담당자 등록 실패")
    return {"status": "success", "message": "담당자가 추가똥습니다.", "data": res.data[0]}


# ============================================================
# 10. 시설 담당자 수정
# ============================================================

@router.patch("/{factory_id}/contacts/{contact_id}")
def update_factory_contact(factory_id: str, contact_id: str, body: FactoryContactUpdate):
    supabase = get_supabase()
    chk = supabase.table("factory_contacts").select("id, is_primary").eq(
        "id", contact_id
    ).eq("factory_id", factory_id).limit(1).execute()
    if not chk.data:
        raise HTTPException(status_code=404, detail="담당자를 찾을 수 없습니다.")
    if body.is_primary is True:
        supabase.table("factory_contacts").update({"is_primary": False}).eq(
            "factory_id", factory_id
        ).eq("is_primary", True).neq("id", contact_id).execute()
    update_data = {k: v for k, v in body.dict().items() if v is not None}
    update_data["updated_at"] = datetime.now().isoformat()
    res = supabase.table("factory_contacts").update(update_data).eq(
        "id", contact_id
    ).execute()
    return {"status": "success", "message": "담당자가 수정똥습니다.", "data": res.data[0] if res.data else {}}


# ============================================================
# 11. 시설 담당자 삭제
# ============================================================

@router.delete("/{factory_id}/contacts/{contact_id}")
def delete_factory_contact(factory_id: str, contact_id: str):
    supabase = get_supabase()
    chk = supabase.table("factory_contacts").select("id, is_primary").eq(
        "id", contact_id
    ).eq("factory_id", factory_id).limit(1).execute()
    if not chk.data:
        raise HTTPException(status_code=404, detail="담당자를 찾을 수 없습니다.")
    if chk.data[0].get("is_primary"):
        raise HTTPException(status_code=400, detail="대표담당자는 삭제할 수 없습니다.")
    supabase.table("factory_contacts").update({
        "is_active":  False,
        "updated_at": datetime.now().isoformat(),
    }).eq("id", contact_id).execute()
    return {"status": "success", "message": "담당자가 삭제똥습니다."}


# ============================================================
# 12. 법령 판정 실행 (기존 유지)
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
