#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TAI Factories 라우터 - 시설 등록/관리 v2.5.0

v2.5.0 (2026-08-18, P13): 인증·회사 스코프 가드.
  비-ALL 은 토큰 company_id 강제. /{id} 및 중첩 자원은 시설 소유권 404.
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

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, StrictBool, StrictInt, StrictFloat, StrictStr, AfterValidator
from typing import Optional, List, Union, Annotated
from datetime import datetime, date
from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services.company_scope import _ensure_factory_own, _forced_company_id, _is_admin, _scope
from services.time import business_today, now_kst, serialize_business_datetime

# ============================================================
# WO-SAFE-LEGAL-IND-CANONICAL-IMPLEMENT-001 STEP3A
#   신규 canonical field 전용 strict 경계 (기존 필드 coercion 정책 불변).
#   None=미확인 / false=명시적 아니오 / 0=실제 zero / []=명시적 없음.
# ============================================================

def _canon_nonneg(v):
    if v is not None and v < 0:
        raise ValueError("0 이상이어야 합니다")
    return v


def _canon_str_list(v):
    if v is None:
        return v
    if not isinstance(v, list):
        raise ValueError("배열이어야 합니다")
    for x in v:
        if x.strip() == "":
            raise ValueError("빈/공백 문자열 항목은 허용되지 않습니다")
    return v


# int/float 허용, bool·문자열·coercion 거부(Strict). 음수 거부.
CanonNum = Annotated[Union[StrictInt, StrictFloat], AfterValidator(_canon_nonneg)]
# 항목 string only(StrictStr), 빈/공백 금지. NULL/[]/비어있지 않은 문자열 배열 허용.
CanonStrList = Annotated[List[StrictStr], AfterValidator(_canon_str_list)]

# PATCH 에서 explicit-null clear 를 허용하는 canonical nullable field (정확히 7개).
CANONICAL_NULL_CLEAR_FIELDS = {
    "work_height_m",
    "has_truck_loading_unloading",
    "truck_loading_height_m",
    "has_manual_heavy_handling",
    "manual_handling_weight_kg",
    "business_activity_types",
    "hazardous_work_environments",
}


def _build_factory_update(provided: dict) -> dict:
    """sparse partial-merge (STEP3A).

    canonical nullable field = provided 에 있으면 그대로(None/false/0/[] 포함) 반영(explicit-null clear).
    기존 legacy field = 기존 semantics 유지(None 은 skip, 즉 clear 불가).
    """
    update_data: dict = {}
    for k, v in provided.items():
        if k in CANONICAL_NULL_CLEAR_FIELDS:
            update_data[k] = v
        elif v is not None:
            update_data[k] = v
    return update_data


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
    # WO-CANONICAL STEP3A: 작업형태/작업환경 canonical (strict; default None)
    work_height_m:               Optional[CanonNum] = None
    has_truck_loading_unloading: Optional[StrictBool] = None
    truck_loading_height_m:      Optional[CanonNum] = None
    has_manual_heavy_handling:   Optional[StrictBool] = None
    manual_handling_weight_kg:   Optional[CanonNum] = None
    business_activity_types:     Optional[CanonStrList] = None
    hazardous_work_environments: Optional[CanonStrList] = None
    # WO-CANONICAL STEP3A: 건물구조 원천값(기존 DB 컬럼) API 결선
    building_structure_code:     Optional[str] = None
    building_structure_name:     Optional[str] = None


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
    # WO-CANONICAL STEP3A: 작업형태/작업환경 canonical (strict; default None; explicit-null clear)
    work_height_m:               Optional[CanonNum] = None
    has_truck_loading_unloading: Optional[StrictBool] = None
    truck_loading_height_m:      Optional[CanonNum] = None
    has_manual_heavy_handling:   Optional[StrictBool] = None
    manual_handling_weight_kg:   Optional[CanonNum] = None
    business_activity_types:     Optional[CanonStrList] = None
    hazardous_work_environments: Optional[CanonStrList] = None
    # WO-CANONICAL STEP3A: 기존 canonical gap 결선(built_year←completion_year, main_structure←구조원천)
    completion_year:             Optional[int] = None
    building_structure_code:     Optional[str] = None
    building_structure_name:     Optional[str] = None


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
    current:     dict = Depends(get_current_user),
):
    supabase = get_supabase()
    company_id = _forced_company_id(current, supabase, company_id)
    if not _is_admin(_scope(supabase, current.get("role_code"))) and not company_id:
        return {
            "status": "success",
            "data": {
                "items": [], "total": 0, "page": page, "size": size,
                "total_pages": 0,
            }
        }
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
def create_factory(req: FactoryCreate, current: dict = Depends(get_current_user)):
    supabase = get_supabase()
    if not _is_admin(_scope(supabase, current.get("role_code"))):
        cid = current.get("company_id")
        if not cid:
            raise HTTPException(status_code=403, detail="권한이 없습니다")
        req.company_id = cid
    company = supabase.table("companies").select("id").eq(
        "id", req.company_id
    ).single().execute()
    if not company.data:
        raise HTTPException(status_code=404, detail="사업장(회사)을 찾을 수 없습니다")
    now = now_kst()
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
    return {"status": "success", "message": "시설이 등록됐습니다", "data": res.data[0]}


# ============================================================
# 3. 상세 조회
# ============================================================

@router.get("/{factory_id}")
def get_factory(factory_id: str, current: dict = Depends(get_current_user)):
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)
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
async def update_factory(factory_id: str, req: FactoryUpdate, current: dict = Depends(get_current_user)):
    """
    v2.2.0: construction_type, subcontractor_worker_count 필드 저장·수정 가능
    v2.1.0: 실제 변경이 있으면 CHANGE 이벤트 트리거
            status_code='INACTIVE' 로 변경 시 CLOSURE 이벤트 트리거
    STEP3A: canonical nullable field 는 sparse partial-merge(explicit-null clear). 기존 필드 semantics 불변.
    """
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)
    existing = supabase.table("factories").select("id, status_code").eq(
        "id", factory_id
    ).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다")

    provided = req.dict(exclude_unset=True)
    update_data = _build_factory_update(provided)
    if not update_data:
        return {"status": "success", "message": "변경된 내용이 없습니다.", "data": {}}

    update_data["updated_at"] = serialize_business_datetime(now_kst())
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
                event_date = business_today(),
            )
        else:
            await trigger_event_schedules(
                factory_id = factory_id,
                event_type = "CHANGE",
                event_date = business_today(),
            )
    except Exception as e:
        print(f"[FACTORIES] 이벤트 트리거 실패 (factory={factory_id}): {e}")

    return {
        "status":  "success",
        "message": "시설 정보가 수정됐습니다",
        "data":    res.data[0] if res.data else {},
    }


# ============================================================
# 5. 비활성화
# ============================================================

@router.delete("/{factory_id}")
def delete_factory(factory_id: str, current: dict = Depends(get_current_user)):
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)
    existing = supabase.table("factories").select("id").eq(
        "id", factory_id
    ).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다")
    supabase.table("factories").update({
        "is_active":   False,
        "status_code": "INACTIVE",
        "updated_at":  serialize_business_datetime(now_kst()),
    }).eq("id", factory_id).execute()
    return {"status": "success", "message": "시설이 비활성화됐습니다"}


# ============================================================
# 6. 소속 회원 목록
# ============================================================

@router.get("/{factory_id}/users")
def get_factory_users(factory_id: str, current: dict = Depends(get_current_user)):
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)
    res = supabase.table("users").select(
        "id, name, email, phone, role_code, status_code, department, position"
    ).eq("factory_id", factory_id).order("created_at", desc=True).execute()
    return {"status": "success", "data": {"items": res.data, "total": len(res.data)}}


# ============================================================
# 7. 소속 건물 목록
# ============================================================

@router.get("/{factory_id}/buildings")
def get_factory_buildings(factory_id: str, current: dict = Depends(get_current_user)):
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)
    res = supabase.table("buildings").select(
        "id, name, building_use_code, floor_count, building_area, is_active"
    ).eq("factory_id", factory_id).order("created_at", desc=True).execute()
    return {"status": "success", "data": {"items": res.data, "total": len(res.data)}}


# ============================================================
# 8. 시설 담당자 목록
# ============================================================

@router.get("/{factory_id}/contacts")
def get_factory_contacts(factory_id: str, current: dict = Depends(get_current_user)):
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)
    res = supabase.table("factory_contacts").select("*").eq(
        "factory_id", factory_id
    ).eq("is_active", True).order("is_primary", desc=True).order("sort_order").execute()
    return {"status": "success", "data": {"items": res.data or [], "total": len(res.data or [])}}


# ============================================================
# 9. 시설 담당자 추가
# ============================================================

@router.post("/{factory_id}/contacts")
def add_factory_contact(factory_id: str, body: FactoryContactBody, current: dict = Depends(get_current_user)):
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)
    if body.is_primary:
        supabase.table("factory_contacts").update({"is_primary": False}).eq(
            "factory_id", factory_id
        ).eq("is_primary", True).execute()
    now = serialize_business_datetime(now_kst())
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
    return {"status": "success", "message": "담당자가 추가됐습니다.", "data": res.data[0]}


# ============================================================
# 10. 시설 담당자 수정
# ============================================================

@router.patch("/{factory_id}/contacts/{contact_id}")
def update_factory_contact(factory_id: str, contact_id: str, body: FactoryContactUpdate, current: dict = Depends(get_current_user)):
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)
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
    update_data["updated_at"] = serialize_business_datetime(now_kst())
    res = supabase.table("factory_contacts").update(update_data).eq(
        "id", contact_id
    ).execute()
    return {"status": "success", "message": "담당자가 수정됐습니다.", "data": res.data[0] if res.data else {}}


# ============================================================
# 11. 시설 담당자 삭제
# ============================================================

@router.delete("/{factory_id}/contacts/{contact_id}")
def delete_factory_contact(factory_id: str, contact_id: str, current: dict = Depends(get_current_user)):
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)
    chk = supabase.table("factory_contacts").select("id, is_primary").eq(
        "id", contact_id
    ).eq("factory_id", factory_id).limit(1).execute()
    if not chk.data:
        raise HTTPException(status_code=404, detail="담당자를 찾을 수 없습니다.")
    if chk.data[0].get("is_primary"):
        raise HTTPException(status_code=400, detail="대표담당자는 삭제할 수 없습니다.")
    supabase.table("factory_contacts").update({
        "is_active":  False,
        "updated_at": serialize_business_datetime(now_kst()),
    }).eq("id", contact_id).execute()
    return {"status": "success", "message": "담당자가 삭제됐습니다."}


# ============================================================
# 12. 법령 판정 실행 (기존 유지)
# ============================================================

@router.post("/{factory_id}/legal")
def run_legal_engine(factory_id: str, current: dict = Depends(get_current_user)):
    from routers.legal_engine import apply_legal_rules
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)
    try:
        result = apply_legal_rules(factory_id, supabase)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
