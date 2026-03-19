#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TAI 담당자/파일 관리 라우터
전역변수: company_contact_type / factory_contact_type / company_file_type

[회사 담당자]
GET    /companies/{id}/contacts        담당자 목록
POST   /companies/{id}/contacts        담당자 추가
PATCH  /companies/{id}/contacts/{cid}  담당자 수정
DELETE /companies/{id}/contacts/{cid}  담당자 삭제

[시설 담당자]
GET    /factories/{id}/contacts        담당자 목록
POST   /factories/{id}/contacts        담당자 추가
PATCH  /factories/{id}/contacts/{cid}  담당자 수정
DELETE /factories/{id}/contacts/{cid}  담당자 삭제

[회사 파일]
GET    /companies/{id}/files           파일 목록
POST   /companies/{id}/files           파일 업로드
DELETE /companies/{id}/files/{fid}     파일 삭제

[회사 계약 현황]
GET    /companies/{id}/contracts       계약 현황
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from db.supabase_client import get_supabase

router = APIRouter(tags=["contacts"])


# ============================================================
# 스키마
# ============================================================

class ContactCreate(BaseModel):
    contact_type: str = "001"   # company_contact_type / factory_contact_type
    name:         str
    phone:        str
    email:        Optional[str] = None
    position:     Optional[str] = None
    is_primary:   bool = False
    sort_order:   int = 0

class ContactUpdate(BaseModel):
    contact_type: Optional[str] = None
    name:         Optional[str] = None
    phone:        Optional[str] = None
    email:        Optional[str] = None
    position:     Optional[str] = None
    sort_order:   Optional[int] = None

class FileUrlCreate(BaseModel):
    file_type:    str               # company_file_type 전역변수
    file_name:    str
    file_url:     Optional[str] = None
    contract_url: Optional[str] = None
    file_size:    Optional[int] = None


# ============================================================
# 회사 담당자 API
# ============================================================

@router.get("/companies/{company_id}/contacts")
def get_company_contacts(company_id: str):
    """회사 담당자 목록"""
    supabase = get_supabase()

    # 회사 존재 확인
    company = supabase.table("companies")\
        .select("id").eq("id", company_id).single().execute()
    if not company.data:
        raise HTTPException(status_code=404, detail="회사를 찾을 수 없습니다")

    res = supabase.table("company_contacts")\
        .select("*")\
        .eq("company_id", company_id)\
        .eq("is_active", True)\
        .order("is_primary", desc=True)\
        .order("sort_order")\
        .execute()

    return {"status": "success", "data": {"items": res.data, "total": len(res.data)}}


@router.post("/companies/{company_id}/contacts")
def add_company_contact(company_id: str, req: ContactCreate):
    """회사 담당자 추가"""
    supabase = get_supabase()

    company = supabase.table("companies")\
        .select("id").eq("id", company_id).single().execute()
    if not company.data:
        raise HTTPException(status_code=404, detail="회사를 찾을 수 없습니다")

    # 대표담당자 중복 확인
    if req.is_primary:
        existing_primary = supabase.table("company_contacts")\
            .select("id")\
            .eq("company_id", company_id)\
            .eq("is_primary", True)\
            .eq("is_active", True)\
            .limit(1).execute()
        if existing_primary.data:
            raise HTTPException(status_code=400, detail="대표담당자는 1명만 등록 가능합니다")

    now = datetime.now()
    res = supabase.table("company_contacts").insert({
        "company_id":   company_id,
        "contact_type": req.contact_type,
        "name":         req.name,
        "phone":        req.phone,
        "email":        req.email,
        "position":     req.position,
        "is_primary":   req.is_primary,
        "sort_order":   req.sort_order,
        "is_active":    True,
        "created_at":   now.isoformat(),
        "updated_at":   now.isoformat(),
    }).execute()

    return {"status": "success", "message": "담당자가 추가됐습니다", "data": res.data[0]}


@router.patch("/companies/{company_id}/contacts/{contact_id}")
def update_company_contact(company_id: str, contact_id: str, req: ContactUpdate):
    """회사 담당자 수정"""
    supabase = get_supabase()

    existing = supabase.table("company_contacts")\
        .select("id, is_primary")\
        .eq("id", contact_id)\
        .eq("company_id", company_id)\
        .single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="담당자를 찾을 수 없습니다")

    update_data = {k: v for k, v in req.dict().items() if v is not None}
    update_data["updated_at"] = datetime.now().isoformat()

    res = supabase.table("company_contacts")\
        .update(update_data).eq("id", contact_id).execute()

    return {"status": "success", "message": "담당자 정보가 수정됐습니다", "data": res.data[0] if res.data else {}}


@router.delete("/companies/{company_id}/contacts/{contact_id}")
def delete_company_contact(company_id: str, contact_id: str):
    """회사 담당자 삭제 (대표담당자 삭제 불가)"""
    supabase = get_supabase()

    existing = supabase.table("company_contacts")\
        .select("id, is_primary")\
        .eq("id", contact_id)\
        .eq("company_id", company_id)\
        .single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="담당자를 찾을 수 없습니다")

    if existing.data.get("is_primary"):
        raise HTTPException(status_code=400, detail="대표담당자는 삭제할 수 없습니다")

    supabase.table("company_contacts").update({
        "is_active":  False,
        "updated_at": datetime.now().isoformat(),
    }).eq("id", contact_id).execute()

    return {"status": "success", "message": "담당자가 삭제됐습니다"}


# ============================================================
# 시설 담당자 API
# ============================================================

@router.get("/factories/{factory_id}/contacts")
def get_factory_contacts(factory_id: str):
    """시설 담당자 목록"""
    supabase = get_supabase()

    factory = supabase.table("factories")\
        .select("id").eq("id", factory_id).single().execute()
    if not factory.data:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다")

    res = supabase.table("factory_contacts")\
        .select("*")\
        .eq("factory_id", factory_id)\
        .eq("is_active", True)\
        .order("is_primary", desc=True)\
        .order("sort_order")\
        .execute()

    return {"status": "success", "data": {"items": res.data, "total": len(res.data)}}


@router.post("/factories/{factory_id}/contacts")
def add_factory_contact(factory_id: str, req: ContactCreate):
    """시설 담당자 추가"""
    supabase = get_supabase()

    factory = supabase.table("factories")\
        .select("id").eq("id", factory_id).single().execute()
    if not factory.data:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다")

    if req.is_primary:
        existing_primary = supabase.table("factory_contacts")\
            .select("id")\
            .eq("factory_id", factory_id)\
            .eq("is_primary", True)\
            .eq("is_active", True)\
            .limit(1).execute()
        if existing_primary.data:
            raise HTTPException(status_code=400, detail="대표담당자는 1명만 등록 가능합니다")

    now = datetime.now()
    res = supabase.table("factory_contacts").insert({
        "factory_id":   factory_id,
        "contact_type": req.contact_type,
        "name":         req.name,
        "phone":        req.phone,
        "email":        req.email,
        "position":     req.position,
        "is_primary":   req.is_primary,
        "sort_order":   req.sort_order,
        "is_active":    True,
        "created_at":   now.isoformat(),
        "updated_at":   now.isoformat(),
    }).execute()

    return {"status": "success", "message": "담당자가 추가됐습니다", "data": res.data[0]}


@router.patch("/factories/{factory_id}/contacts/{contact_id}")
def update_factory_contact(factory_id: str, contact_id: str, req: ContactUpdate):
    """시설 담당자 수정"""
    supabase = get_supabase()

    existing = supabase.table("factory_contacts")\
        .select("id")\
        .eq("id", contact_id)\
        .eq("factory_id", factory_id)\
        .single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="담당자를 찾을 수 없습니다")

    update_data = {k: v for k, v in req.dict().items() if v is not None}
    update_data["updated_at"] = datetime.now().isoformat()

    res = supabase.table("factory_contacts")\
        .update(update_data).eq("id", contact_id).execute()

    return {"status": "success", "message": "담당자 정보가 수정됐습니다", "data": res.data[0] if res.data else {}}


@router.delete("/factories/{factory_id}/contacts/{contact_id}")
def delete_factory_contact(factory_id: str, contact_id: str):
    """시설 담당자 삭제 (대표담당자 삭제 불가)"""
    supabase = get_supabase()

    existing = supabase.table("factory_contacts")\
        .select("id, is_primary")\
        .eq("id", contact_id)\
        .eq("factory_id", factory_id)\
        .single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="담당자를 찾을 수 없습니다")

    if existing.data.get("is_primary"):
        raise HTTPException(status_code=400, detail="대표담당자는 삭제할 수 없습니다")

    supabase.table("factory_contacts").update({
        "is_active":  False,
        "updated_at": datetime.now().isoformat(),
    }).eq("id", contact_id).execute()

    return {"status": "success", "message": "담당자가 삭제됐습니다"}


# ============================================================
# 회사 파일 API (Supabase Storage 연동)
# ============================================================

@router.get("/companies/{company_id}/files")
def get_company_files(company_id: str):
    """회사 파일 목록"""
    supabase = get_supabase()

    res = supabase.table("company_files")\
        .select("*")\
        .eq("company_id", company_id)\
        .eq("is_active", True)\
        .order("uploaded_at", desc=True)\
        .execute()

    return {"status": "success", "data": {"items": res.data, "total": len(res.data)}}


@router.post("/companies/{company_id}/files/upload")
async def upload_company_file(
    company_id: str,
    file_type:  str = Form(...),   # company_file_type 전역변수
    file:       UploadFile = File(...),
):
    """파일 업로드 → Supabase Storage"""
    supabase = get_supabase()

    # 파일 크기 확인
    MAX_SIZE = 20 * 1024 * 1024  # 20MB
    contents = await file.read()
    if len(contents) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="파일 크기는 20MB 이하여야 합니다")

    # 허용 확장자
    allowed = [".pdf", ".jpg", ".jpeg", ".png"]
    import os
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed:
        raise HTTPException(status_code=400, detail="PDF, JPG, PNG 파일만 업로드 가능합니다")

    # Supabase Storage 업로드
    now      = datetime.now()
    path     = f"companies/{company_id}/{file_type}/{now.strftime('%Y%m%d%H%M%S')}_{file.filename}"
    bucket   = "tai-files"

    try:
        storage_res = supabase.storage.from_(bucket).upload(
            path, contents, {"content-type": file.content_type}
        )
        file_url = supabase.storage.from_(bucket).get_public_url(path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"파일 업로드 실패: {str(e)}")

    # DB 저장
    res = supabase.table("company_files").insert({
        "company_id":  company_id,
        "file_type":   file_type,
        "file_name":   file.filename,
        "file_url":    file_url,
        "file_size":   len(contents),
        "uploaded_at": now.isoformat(),
        "is_active":   True,
        "created_at":  now.isoformat(),
    }).execute()

    return {"status": "success", "message": "파일이 업로드됐습니다", "data": res.data[0]}


@router.post("/companies/{company_id}/files/url")
def save_contract_url(company_id: str, req: FileUrlCreate):
    """전자계약서 URL 저장"""
    supabase = get_supabase()

    now = datetime.now()
    res = supabase.table("company_files").insert({
        "company_id":   company_id,
        "file_type":    req.file_type,
        "file_name":    req.file_name,
        "file_url":     req.file_url,
        "contract_url": req.contract_url,
        "file_size":    req.file_size,
        "uploaded_at":  now.isoformat(),
        "is_active":    True,
        "created_at":   now.isoformat(),
    }).execute()

    return {"status": "success", "message": "파일 정보가 저장됐습니다", "data": res.data[0]}


@router.delete("/companies/{company_id}/files/{file_id}")
def delete_company_file(company_id: str, file_id: str):
    """파일 삭제 (비활성화)"""
    supabase = get_supabase()

    existing = supabase.table("company_files")\
        .select("id, file_url")\
        .eq("id", file_id)\
        .eq("company_id", company_id)\
        .single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

    supabase.table("company_files").update({
        "is_active": False,
    }).eq("id", file_id).execute()

    return {"status": "success", "message": "파일이 삭제됐습니다"}


# ============================================================
# 회사 계약 현황
# ============================================================

@router.get("/companies/{company_id}/contracts")
def get_company_contracts(company_id: str):
    """회사 계약 현황 (계약 목록 + ACTIVE 계약 강조)"""
    supabase = get_supabase()

    company = supabase.table("companies")\
        .select("id").eq("id", company_id).single().execute()
    if not company.data:
        raise HTTPException(status_code=404, detail="회사를 찾을 수 없습니다")

    res = supabase.table("contracts")\
        .select("*")\
        .eq("company_id", company_id)\
        .order("created_at", desc=True)\
        .execute()

    contracts   = res.data or []
    active      = [c for c in contracts if c.get("status_code") == "ACTIVE"]
    pending     = [c for c in contracts if c.get("status_code") == "PENDING_PAYMENT"]
    others      = [c for c in contracts if c.get("status_code") not in ["ACTIVE", "PENDING_PAYMENT"]]

    return {
        "status": "success",
        "data": {
            "active_contracts":  active,
            "pending_contracts": pending,
            "other_contracts":   others,
            "total":             len(contracts),
        }
    }

