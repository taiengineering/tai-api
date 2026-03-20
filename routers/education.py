#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TAI 교육관리 라우터
전역변수: education_group / education_cycle / education_status / education_method / education_file_type

[교육 마스터]
GET    /education-master                    법정교육 마스터 목록
GET    /education-master/{code}             교육 마스터 상세

[교육 설정] - 총관리자
GET    /education-settings/{factory_id}     시설별 교육 설정 목록
PATCH  /education-settings/{factory_id}/{code}  교육 설정 수정

[교육 이력] - 안전관리자
GET    /education-history                   교육 이력 목록
POST   /education-history                   교육 이수 등록
GET    /education-history/{id}              이수 이력 상세
PATCH  /education-history/{id}              이수 이력 수정
GET    /education-history/summary           요약 통계 (카드)

[증빙서류]
GET    /education-history/{id}/files        증빙서류 목록
POST   /education-history/{id}/files        증빙서류 등록
DELETE /education-history/{id}/files/{fid}  증빙서류 삭제
"""

from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, date
from db.supabase_client import get_supabase

router = APIRouter(tags=["education"])


# ============================================================
# 스키마
# ============================================================

class EducationSettingUpdate(BaseModel):
    is_applied:   Optional[bool] = None
    target_types: Optional[list] = None
    alert_d30:    Optional[bool] = None
    alert_d7:     Optional[bool] = None
    alert_d1:     Optional[bool] = None
    memo:         Optional[str]  = None

class EducationHistoryCreate(BaseModel):
    factory_id:       str
    company_id:       Optional[str] = None
    user_id:          str
    education_code:   str
    due_date:         Optional[str] = None
    completed_at:     str                    # 이수일 (필수)
    completed_hours:  float                  # 이수시간 (필수)
    institution:      Optional[str] = None   # 교육기관명
    method:           str = "OFFLINE"        # education_method 전역변수
    location:         Optional[str] = None
    memo:             Optional[str] = None

class EducationHistoryUpdate(BaseModel):
    completed_at:    Optional[str]   = None
    completed_hours: Optional[float] = None
    institution:     Optional[str]   = None
    method:          Optional[str]   = None
    location:        Optional[str]   = None
    status_code:     Optional[str]   = None
    memo:            Optional[str]   = None

class EvidenceFileCreate(BaseModel):
    file_type:  str               # education_file_type 전역변수
    file_name:  str
    file_url:   Optional[str] = None
    file_size:  Optional[int] = None


# ============================================================
# 교육 마스터 API
# ============================================================

@router.get("/education-master")
def get_education_master(
    education_group: Optional[str] = Query(default=None),  # education_group 전역변수
    target_type:     Optional[str] = Query(default=None),
):
    """법정교육 마스터 목록"""
    supabase = get_supabase()
    query = supabase.table("education_master")\
        .select("*").eq("is_active", True)

    if education_group: query = query.eq("education_group", education_group)
    if target_type:     query = query.eq("target_type", target_type)

    res = query.order("education_code").execute()

    # 그룹별 정리
    grouped = {}
    for item in (res.data or []):
        g = item["education_group"]
        if g not in grouped:
            grouped[g] = []
        grouped[g].append(item)

    return {"status": "success", "data": grouped}


@router.get("/education-master/{education_code}")
def get_education_master_detail(education_code: str):
    """교육 마스터 상세"""
    supabase = get_supabase()
    res = supabase.table("education_master")\
        .select("*").eq("education_code", education_code).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="교육 마스터를 찾을 수 없습니다")
    return {"status": "success", "data": res.data}


# ============================================================
# 교육 설정 API (총관리자)
# ============================================================

@router.get("/education-settings/{factory_id}")
def get_education_settings(factory_id: str):
    """시설별 교육 설정 목록"""
    supabase = get_supabase()

    # 마스터 전체 조회
    master = supabase.table("education_master")\
        .select("*").eq("is_active", True).order("education_code").execute()

    # 시설 설정 조회
    settings = supabase.table("education_setting")\
        .select("*").eq("factory_id", factory_id).execute()

    setting_map = {s["education_code"]: s for s in (settings.data or [])}

    # 마스터 + 설정 병합
    result = []
    for m in (master.data or []):
        code    = m["education_code"]
        setting = setting_map.get(code, {})
        result.append({
            **m,
            "is_applied": setting.get("is_applied", True),
            "target_types": setting.get("target_types"),
            "alert_d30":  setting.get("alert_d30", True),
            "alert_d7":   setting.get("alert_d7",  True),
            "alert_d1":   setting.get("alert_d1",  True),
            "memo":       setting.get("memo"),
            "setting_id": setting.get("id"),
        })

    return {"status": "success", "data": result}


@router.patch("/education-settings/{factory_id}/{education_code}")
def update_education_setting(factory_id: str, education_code: str, req: EducationSettingUpdate):
    """시설별 교육 설정 수정"""
    supabase = get_supabase()

    now = datetime.now().isoformat()
    update_data = {k: v for k, v in req.dict().items() if v is not None}
    update_data["updated_at"] = now

    # upsert 처리
    existing = supabase.table("education_setting")\
        .select("id")\
        .eq("factory_id", factory_id)\
        .eq("education_code", education_code)\
        .limit(1).execute()

    if existing.data:
        res = supabase.table("education_setting")\
            .update(update_data)\
            .eq("factory_id", factory_id)\
            .eq("education_code", education_code).execute()
    else:
        res = supabase.table("education_setting").insert({
            "factory_id":     factory_id,
            "education_code": education_code,
            **update_data,
            "created_at": now,
        }).execute()

    return {"status": "success", "message": "교육 설정이 저장됐습니다", "data": res.data[0] if res.data else {}}


# ============================================================
# 교육 이력 API
# ============================================================

@router.get("/education-history")
def get_education_history(
    page:            int  = Query(default=1, ge=1),
    size:            int  = Query(default=20, ge=1, le=100),
    factory_id:      Optional[str] = Query(default=None),
    company_id:      Optional[str] = Query(default=None),
    user_id:         Optional[str] = Query(default=None),
    education_code:  Optional[str] = Query(default=None),
    status_code:     Optional[str] = Query(default=None),  # education_status 전역변수
    search:          Optional[str] = Query(default=None),
):
    """교육 이력 목록"""
    supabase = get_supabase()
    query = supabase.table("education_history").select("*", count="exact")

    if factory_id:     query = query.eq("factory_id", factory_id)
    if company_id:     query = query.eq("company_id", company_id)
    if user_id:        query = query.eq("user_id", user_id)
    if education_code: query = query.eq("education_code", education_code)
    if status_code:    query = query.eq("status_code", status_code)

    offset = (page - 1) * size
    res = query.order("due_date", desc=False)\
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


@router.get("/education-history/summary")
def get_education_summary(
    factory_id: Optional[str] = Query(default=None),
    company_id: Optional[str] = Query(default=None),
):
    """교육 이력 요약 통계 (카드용)"""
    supabase = get_supabase()
    query = supabase.table("education_history").select("status_code")

    if factory_id: query = query.eq("factory_id", factory_id)
    if company_id: query = query.eq("company_id", company_id)

    res = query.execute()
    items = res.data or []

    total     = len(items)
    completed = len([i for i in items if i["status_code"] == "COMPLETED"])
    pending   = len([i for i in items if i["status_code"] == "PENDING"])
    overdue   = len([i for i in items if i["status_code"] == "OVERDUE"])

    return {
        "status": "success",
        "data": {
            "total":     total,
            "completed": completed,
            "pending":   pending,
            "overdue":   overdue,
        }
    }


@router.post("/education-history")
def create_education_history(req: EducationHistoryCreate):
    """교육 이수 등록"""
    supabase = get_supabase()

    # 교육 마스터 확인
    master = supabase.table("education_master")\
        .select("required_hours, education_name")\
        .eq("education_code", req.education_code)\
        .single().execute()
    if not master.data:
        raise HTTPException(status_code=404, detail="교육 마스터를 찾을 수 없습니다")

    # 법정 기준시간 검증
    required = master.data["required_hours"]
    if req.completed_hours < required:
        raise HTTPException(
            status_code=400,
            detail=f"법정 기준시간을 충족하지 않습니다 (기준: {required}시간, 입력: {req.completed_hours}시간)"
        )

    now = datetime.now()
    res = supabase.table("education_history").insert({
        "factory_id":      req.factory_id,
        "company_id":      req.company_id,
        "user_id":         req.user_id,
        "education_code":  req.education_code,
        "due_date":        req.due_date,
        "completed_at":    req.completed_at,
        "completed_hours": req.completed_hours,
        "institution":     req.institution,
        "method":          req.method,
        "location":        req.location,
        "status_code":     "COMPLETED",
        "memo":            req.memo,
        "created_at":      now.isoformat(),
        "updated_at":      now.isoformat(),
    }).execute()

    return {
        "status":  "success",
        "message": f"{master.data['education_name']} 이수가 등록됐습니다",
        "data":    res.data[0],
    }


@router.get("/education-history/{history_id}")
def get_education_history_detail(history_id: str):
    """이수 이력 상세"""
    supabase = get_supabase()
    res = supabase.table("education_history")\
        .select("*").eq("id", history_id).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="이수 이력을 찾을 수 없습니다")
    return {"status": "success", "data": res.data}


@router.patch("/education-history/{history_id}")
def update_education_history(history_id: str, req: EducationHistoryUpdate):
    """이수 이력 수정"""
    supabase = get_supabase()

    existing = supabase.table("education_history")\
        .select("id, education_code").eq("id", history_id).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="이수 이력을 찾을 수 없습니다")

    # 이수시간 변경 시 기준시간 재검증
    if req.completed_hours:
        master = supabase.table("education_master")\
            .select("required_hours")\
            .eq("education_code", existing.data["education_code"])\
            .single().execute()
        if master.data and req.completed_hours < master.data["required_hours"]:
            raise HTTPException(
                status_code=400,
                detail=f"법정 기준시간을 충족하지 않습니다 (기준: {master.data['required_hours']}시간)"
            )

    update_data = {k: v for k, v in req.dict().items() if v is not None}
    update_data["updated_at"] = datetime.now().isoformat()

    res = supabase.table("education_history")\
        .update(update_data).eq("id", history_id).execute()

    return {"status": "success", "message": "이수 이력이 수정됐습니다", "data": res.data[0] if res.data else {}}


# ============================================================
# 증빙서류 API
# ============================================================

@router.get("/education-history/{history_id}/files")
def get_education_files(history_id: str):
    """증빙서류 목록"""
    supabase = get_supabase()
    res = supabase.table("education_files")\
        .select("*")\
        .eq("history_id", history_id)\
        .eq("is_active", True)\
        .order("uploaded_at", desc=True).execute()

    return {"status": "success", "data": {"items": res.data, "total": len(res.data or [])}}


@router.post("/education-history/{history_id}/files")
def add_education_file(history_id: str, req: EvidenceFileCreate):
    """증빙서류 등록 (URL 방식)"""
    supabase = get_supabase()

    existing = supabase.table("education_history")\
        .select("id").eq("id", history_id).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="이수 이력을 찾을 수 없습니다")

    now = datetime.now()
    res = supabase.table("education_files").insert({
        "history_id":  history_id,
        "file_type":   req.file_type,
        "file_name":   req.file_name,
        "file_url":    req.file_url,
        "file_size":   req.file_size,
        "uploaded_at": now.isoformat(),
        "is_active":   True,
        "created_at":  now.isoformat(),
    }).execute()

    return {"status": "success", "message": "증빙서류가 등록됐습니다", "data": res.data[0]}


@router.delete("/education-history/{history_id}/files/{file_id}")
def delete_education_file(history_id: str, file_id: str):
    """증빙서류 삭제"""
    supabase = get_supabase()

    existing = supabase.table("education_files")\
        .select("id")\
        .eq("id", file_id)\
        .eq("history_id", history_id)\
        .single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

    supabase.table("education_files").update({
        "is_active": False
    }).eq("id", file_id).execute()

    return {"status": "success", "message": "증빙서류가 삭제됐습니다"}
