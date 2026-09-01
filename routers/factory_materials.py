#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
routers/factory_materials.py — 사업장 취급물질 canonical 자산 CRUD (v1.0.1)
WO-SAFE-LEGAL-IND-CANONICAL-IMPLEMENT-001 / STEP6 (+ STEP6-PATCH-1: DELETE result contract).

STEP1 정본 테이블 factory_materials 를 그대로 결선한다(법령진단 전용 material profile 미생성).
  factory_materials: id PK, factory_id FK, material_name, material_category_code,
                     handling_mode_codes text[], is_active, created_at, updated_at
identity: material_name 또는 material_category_code 중 최소 하나가 non-blank(둘 다 blank/NULL 금지).
ownership: material -> factory -> company (_ensure_factory_own). 공유 get_supabase/auth 사용.
Marketing(material_profile/material_category/handling_modes) 저장 금지. diagnosis_input_fields 미조회.
STEP7 assembler 가 이 canonical 을 읽어 transport 로 변환한다.
"""
from typing import Optional, List, Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, StrictStr, AfterValidator

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services.company_scope import _ensure_factory_own
from services.time import now_kst, serialize_business_datetime

router = APIRouter(prefix="/factory-materials", tags=["factory-materials"])

TBL = "factory_materials"


# strict boundary (canonical shape/type + nonblank; Marketing SoT 아님)
def _nonblank_str_or_none(v):
    if v is None:
        return v
    if not isinstance(v, str):
        raise ValueError("문자열이어야 합니다")
    if v.strip() == "":
        raise ValueError("빈/공백 문자열은 허용되지 않습니다")
    return v


def _handling_mode_codes(v):
    if v is None:
        return v
    if not isinstance(v, list):
        raise ValueError("배열이어야 합니다")
    for x in v:
        if x.strip() == "":
            raise ValueError("빈/공백 문자열 항목은 허용되지 않습니다")
    return v


NonBlankStr = Annotated[StrictStr, AfterValidator(_nonblank_str_or_none)]
HandlingModeCodes = Annotated[List[StrictStr], AfterValidator(_handling_mode_codes)]

# PATCH 에서 explicit-null clear 를 허용하는 canonical field (정확히 3개).
MATERIAL_CANONICAL_NULL_CLEAR_FIELDS = {"material_name", "material_category_code", "handling_mode_codes"}


class FactoryMaterialCreate(BaseModel):
    factory_id:             str
    material_name:          Optional[NonBlankStr] = None
    material_category_code: Optional[NonBlankStr] = None
    handling_mode_codes:    Optional[HandlingModeCodes] = None

    class Config:
        extra = "forbid"   # id/is_active/created_at/updated_at/company_id 등 client 입력 차단(422)


class FactoryMaterialUpdate(BaseModel):
    material_name:          Optional[NonBlankStr] = None
    material_category_code: Optional[NonBlankStr] = None
    handling_mode_codes:    Optional[HandlingModeCodes] = None

    class Config:
        extra = "forbid"   # factory_id/id/is_active/timestamps/company_id 변경 차단(422)


def _identity_ok(name, category) -> bool:
    """material_name 또는 material_category_code 중 최소 하나가 non-blank."""
    return bool((name or "").strip()) or bool((category or "").strip())


def _now_iso() -> str:
    return serialize_business_datetime(now_kst())


def _ensure_material_own(supabase, material_id: str, current: dict) -> dict:
    """material(active) -> factory -> company 소유 확인. 검증된 row 반환(PATCH 중복조회 절감).
    missing/inactive/foreign 전부 404(존재 여부 미노출)."""
    r = (
        supabase.table(TBL)
        .select("*")
        .eq("id", material_id)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    rows = getattr(r, "data", None) or []
    if not rows:
        raise HTTPException(status_code=404, detail="물질 자산을 찾을 수 없습니다")
    _ensure_factory_own(supabase, rows[0]["factory_id"], current)
    return rows[0]


# LIST
@router.get("")
def list_materials(factory_id: str = Query(...), current: dict = Depends(get_current_user)):
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)   # foreign -> 404, material query 0
    res = (
        supabase.table(TBL)
        .select("id, factory_id, material_name, material_category_code, handling_mode_codes, is_active, created_at, updated_at")
        .eq("factory_id", factory_id)
        .eq("is_active", True)
        .order("created_at", desc=True)
        .execute()
    )
    items = getattr(res, "data", None) or []
    return {"status": "success", "data": {"factory_id": factory_id, "items": items, "total": len(items)}}


# GET SINGLE
@router.get("/{material_id}")
def get_material(material_id: str, current: dict = Depends(get_current_user)):
    supabase = get_supabase()
    row = _ensure_material_own(supabase, material_id, current)
    return {"status": "success", "data": row}


# CREATE
@router.post("")
def create_material(body: FactoryMaterialCreate, current: dict = Depends(get_current_user)):
    # identity gate (DB CHECK 를 정상흐름으로 쓰지 않음)
    if not _identity_ok(body.material_name, body.material_category_code):
        raise HTTPException(status_code=422, detail="material_name 또는 material_category_code 중 최소 하나가 필요합니다")
    supabase = get_supabase()
    _ensure_factory_own(supabase, body.factory_id, current)   # foreign -> 404, insert 0
    row = {
        "factory_id":             body.factory_id,
        "material_name":          body.material_name,
        "material_category_code": body.material_category_code,
        "handling_mode_codes":    body.handling_mode_codes,   # None/[]/string[] 그대로
        "is_active":              True,                        # server-fixed
        "updated_at":             _now_iso(),
    }
    res = supabase.table(TBL).insert(row).execute()
    data = getattr(res, "data", None) or []
    if not data:
        raise HTTPException(status_code=500, detail="물질 자산 등록 실패")
    return {"status": "success", "message": "물질 자산이 등록됐습니다", "data": data[0]}


# PATCH (sparse; post-merge identity gate)
@router.patch("/{material_id}")
def update_material(material_id: str, body: FactoryMaterialUpdate, current: dict = Depends(get_current_user)):
    supabase = get_supabase()
    existing = _ensure_material_own(supabase, material_id, current)   # active row 확보 + ownership

    provided = body.dict(exclude_unset=True)   # provided-only(explicit None 포함)
    update_data = {}
    for k, v in provided.items():
        if k in MATERIAL_CANONICAL_NULL_CLEAR_FIELDS:
            update_data[k] = v   # None(clear)/[]/string 그대로
    if not update_data:
        raise HTTPException(status_code=422, detail="수정할 내용이 없습니다")

    # post-merge identity gate: effective name/category 둘 다 blank 금지
    eff_name = update_data["material_name"] if "material_name" in update_data else existing.get("material_name")
    eff_cat = update_data["material_category_code"] if "material_category_code" in update_data else existing.get("material_category_code")
    if not _identity_ok(eff_name, eff_cat):
        raise HTTPException(status_code=422, detail="material_name 과 material_category_code 가 모두 비어 있을 수 없습니다")

    update_data["updated_at"] = _now_iso()
    res = supabase.table(TBL).update(update_data).eq("id", material_id).eq("is_active", True).execute()
    data = getattr(res, "data", None) or []
    if not data:
        raise HTTPException(status_code=404, detail="물질 자산을 찾을 수 없습니다")
    return {"status": "success", "message": "물질 자산이 수정됐습니다", "data": data[0]}


# DELETE (soft)
@router.delete("/{material_id}")
def delete_material(material_id: str, current: dict = Depends(get_current_user)):
    supabase = get_supabase()
    _ensure_material_own(supabase, material_id, current)   # active row + ownership (inactive -> 404)
    # STEP6-PATCH-1: UPDATE(id + is_active=true) 결과 행이 실제 존재할 때만 success. 0-row -> 404.
    res = (
        supabase.table(TBL)
        .update({"is_active": False, "updated_at": _now_iso()})
        .eq("id", material_id)
        .eq("is_active", True)
        .execute()
    )
    if not (getattr(res, "data", None) or []):
        raise HTTPException(status_code=404, detail="물질 자산을 찾을 수 없습니다")
    return {"status": "success", "message": "물질 자산이 비활성화됐습니다"}
