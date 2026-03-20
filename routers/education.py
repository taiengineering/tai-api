"""
TAI 법정교육 관리 라우터
- education_master: 법정교육 마스터 20개 (읽기 전용)
- education_setting: 시설별 교육 ON/OFF 설정
- education_history: 개인별 교육 이수 이력
- education_files: 교육 증빙서류 (Supabase Storage)
"""

from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File, Form
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime, date
import os
import uuid
from supabase import create_client, Client

router = APIRouter()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

def get_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ─────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────

class EducationSettingUpdate(BaseModel):
    is_active: Optional[bool] = None
    target_types: Optional[list] = None
    notify_d30: Optional[bool] = None
    notify_d7: Optional[bool] = None
    notify_d1: Optional[bool] = None
    memo: Optional[str] = None

class EducationHistoryCreate(BaseModel):
    factory_id: str
    user_id: str
    education_code: str
    completed_date: date
    completed_hours: float
    institution_name: Optional[str] = None
    education_method: Optional[str] = None  # 집합교육 / 온라인교육 / 현장교육
    education_place: Optional[str] = None
    memo: Optional[str] = None
    due_date: Optional[date] = None

class EducationHistoryUpdate(BaseModel):
    completed_date: Optional[date] = None
    completed_hours: Optional[float] = None
    institution_name: Optional[str] = None
    education_method: Optional[str] = None
    education_place: Optional[str] = None
    memo: Optional[str] = None
    status: Optional[str] = None  # pending / completed / overdue


# ─────────────────────────────────────────────────────────────
# 1. 교육 마스터 (읽기 전용)
# ─────────────────────────────────────────────────────────────

@router.get("/education-master", tags=["교육관리"])
def get_education_master(
    category: Optional[str] = Query(None, description="worker_safety / duty / training"),
    supabase: Client = Depends(get_supabase)
):
    """법정교육 마스터 목록 조회 (20개)"""
    q = supabase.table("education_master").select("*").eq("is_active", True)
    if category:
        q = q.eq("category", category)
    res = q.order("sort_order").execute()
    return {"success": True, "data": res.data}


@router.get("/education-master/{education_code}", tags=["교육관리"])
def get_education_master_detail(education_code: str, supabase: Client = Depends(get_supabase)):
    """법정교육 마스터 상세 조회"""
    res = supabase.table("education_master").select("*").eq("education_code", education_code).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="교육 마스터를 찾을 수 없습니다.")
    return {"success": True, "data": res.data}


# ─────────────────────────────────────────────────────────────
# 2. 교육 설정 (시설별 ON/OFF)
# ─────────────────────────────────────────────────────────────

@router.get("/education-settings/{factory_id}", tags=["교육관리"])
def get_education_settings(factory_id: str, supabase: Client = Depends(get_supabase)):
    """시설별 전체 교육 설정 조회"""
    # 마스터와 LEFT JOIN 형식으로 설정값 반환
    master_res = supabase.table("education_master").select("*").eq("is_active", True).order("sort_order").execute()
    setting_res = supabase.table("education_setting").select("*").eq("factory_id", factory_id).execute()

    setting_map = {s["education_code"]: s for s in (setting_res.data or [])}

    result = []
    for m in (master_res.data or []):
        code = m["education_code"]
        setting = setting_map.get(code, {})
        result.append({
            **m,
            "is_active": setting.get("is_active", True),
            "target_types": setting.get("target_types", []),
            "notify_d30": setting.get("notify_d30", True),
            "notify_d7": setting.get("notify_d7", True),
            "notify_d1": setting.get("notify_d1", True),
            "memo": setting.get("memo"),
            "setting_id": setting.get("id"),
        })

    return {"success": True, "data": result}


@router.get("/education-settings/{factory_id}/{education_code}", tags=["교육관리"])
def get_education_setting_detail(
    factory_id: str,
    education_code: str,
    supabase: Client = Depends(get_supabase)
):
    """시설별 교육 설정 단건 조회"""
    res = supabase.table("education_setting") \
        .select("*, education_master(*)") \
        .eq("factory_id", factory_id) \
        .eq("education_code", education_code) \
        .maybe_single().execute()

    if not res.data:
        # 설정 없으면 마스터 기본값 반환
        master = supabase.table("education_master").select("*").eq("education_code", education_code).single().execute()
        if not master.data:
            raise HTTPException(status_code=404, detail="교육 마스터를 찾을 수 없습니다.")
        return {"success": True, "data": {**master.data, "is_active": True, "setting_id": None}}

    return {"success": True, "data": res.data}


@router.patch("/education-settings/{factory_id}/{education_code}", tags=["교육관리"])
def update_education_setting(
    factory_id: str,
    education_code: str,
    body: EducationSettingUpdate,
    supabase: Client = Depends(get_supabase)
):
    """시설별 교육 설정 저장 (upsert)"""
    existing = supabase.table("education_setting") \
        .select("id") \
        .eq("factory_id", factory_id) \
        .eq("education_code", education_code) \
        .maybe_single().execute()

    payload = {k: v for k, v in body.dict().items() if v is not None}
    payload["updated_at"] = datetime.utcnow().isoformat()

    if existing.data:
        res = supabase.table("education_setting") \
            .update(payload) \
            .eq("id", existing.data["id"]) \
            .execute()
    else:
        payload.update({"factory_id": factory_id, "education_code": education_code})
        res = supabase.table("education_setting").insert(payload).execute()

    return {"success": True, "data": res.data[0] if res.data else {}}


# ─────────────────────────────────────────────────────────────
# 3. 교육 이수 이력
# ─────────────────────────────────────────────────────────────

@router.get("/education-history", tags=["교육관리"])
def get_education_history(
    factory_id: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    education_code: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="pending / completed / overdue"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    supabase: Client = Depends(get_supabase)
):
    """교육 이수 이력 목록 조회"""
    offset = (page - 1) * size
    q = supabase.table("education_history") \
        .select("*, education_master(education_name, category, min_hours, due_rule), users(name, job_type), education_files(id)", count="exact")

    if factory_id:
        q = q.eq("factory_id", factory_id)
    if user_id:
        q = q.eq("user_id", user_id)
    if education_code:
        q = q.eq("education_code", education_code)
    if status:
        q = q.eq("status", status)

    res = q.order("due_date", desc=False).range(offset, offset + size - 1).execute()
    total = res.count or 0

    return {
        "success": True,
        "data": {
            "items": res.data,
            "total": total,
            "page": page,
            "size": size,
            "pages": (total + size - 1) // size
        }
    }


@router.get("/education-history/summary", tags=["교육관리"])
def get_education_history_summary(
    factory_id: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    supabase: Client = Depends(get_supabase)
):
    """교육 이수 현황 요약 카드 (전체/완료/미이수/기한초과)"""
    q = supabase.table("education_history").select("status")
    if factory_id:
        q = q.eq("factory_id", factory_id)
    if user_id:
        q = q.eq("user_id", user_id)

    res = q.execute()
    rows = res.data or []

    total = len(rows)
    completed = sum(1 for r in rows if r["status"] == "completed")
    pending = sum(1 for r in rows if r["status"] == "pending")
    overdue = sum(1 for r in rows if r["status"] == "overdue")

    return {
        "success": True,
        "data": {
            "total": total,
            "completed": completed,
            "pending": pending,
            "overdue": overdue
        }
    }


@router.post("/education-history", tags=["교육관리"])
def create_education_history(body: EducationHistoryCreate, supabase: Client = Depends(get_supabase)):
    """교육 이수 이력 등록"""
    # 법정 기준시간 검증
    master = supabase.table("education_master") \
        .select("min_hours, education_name") \
        .eq("education_code", body.education_code) \
        .single().execute()

    if not master.data:
        raise HTTPException(status_code=404, detail="교육 마스터를 찾을 수 없습니다.")

    min_hours = master.data.get("min_hours", 0)
    if body.completed_hours < min_hours:
        raise HTTPException(
            status_code=400,
            detail=f"법정 기준시간을 충족하지 않습니다. (기준: {min_hours}시간 이상)"
        )

    payload = {
        **body.dict(),
        "completed_date": str(body.completed_date) if body.completed_date else None,
        "due_date": str(body.due_date) if body.due_date else None,
        "status": "completed",
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }

    res = supabase.table("education_history").insert(payload).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="이수 이력 등록에 실패했습니다.")

    return {"success": True, "data": res.data[0]}


@router.get("/education-history/{history_id}", tags=["교육관리"])
def get_education_history_detail(history_id: str, supabase: Client = Depends(get_supabase)):
    """교육 이수 이력 상세 조회"""
    res = supabase.table("education_history") \
        .select("*, education_master(*), users(name, job_type, email), education_files(*)") \
        .eq("id", history_id) \
        .single().execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="이수 이력을 찾을 수 없습니다.")

    return {"success": True, "data": res.data}


@router.patch("/education-history/{history_id}", tags=["교육관리"])
def update_education_history(
    history_id: str,
    body: EducationHistoryUpdate,
    supabase: Client = Depends(get_supabase)
):
    """교육 이수 이력 수정"""
    existing = supabase.table("education_history").select("id, education_code").eq("id", history_id).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="이수 이력을 찾을 수 없습니다.")

    # 시간 변경 시 기준 재검증
    if body.completed_hours is not None:
        master = supabase.table("education_master") \
            .select("min_hours") \
            .eq("education_code", existing.data["education_code"]) \
            .single().execute()
        min_hours = master.data.get("min_hours", 0) if master.data else 0
        if body.completed_hours < min_hours:
            raise HTTPException(
                status_code=400,
                detail=f"법정 기준시간을 충족하지 않습니다. (기준: {min_hours}시간 이상)"
            )

    payload = {k: v for k, v in body.dict().items() if v is not None}
    if "completed_date" in payload and payload["completed_date"]:
        payload["completed_date"] = str(payload["completed_date"])
    payload["updated_at"] = datetime.utcnow().isoformat()

    res = supabase.table("education_history").update(payload).eq("id", history_id).execute()
    return {"success": True, "data": res.data[0] if res.data else {}}


# ─────────────────────────────────────────────────────────────
# 4. 증빙서류 (education_files + Supabase Storage)
# ─────────────────────────────────────────────────────────────

@router.get("/education-history/{history_id}/files", tags=["교육관리"])
def get_education_files(history_id: str, supabase: Client = Depends(get_supabase)):
    """교육 이수 증빙서류 목록"""
    res = supabase.table("education_files").select("*").eq("history_id", history_id).order("created_at").execute()
    return {"success": True, "data": res.data}


@router.post("/education-history/{history_id}/files", tags=["교육관리"])
async def upload_education_file(
    history_id: str,
    file: UploadFile = File(...),
    doc_type: str = Form("기타", description="수료증 / 출석부 / 이수확인서 / 교육일지 / 기타"),
    supabase: Client = Depends(get_supabase)
):
    """교육 증빙서류 업로드"""
    # 이력 존재 확인
    existing = supabase.table("education_history").select("id").eq("id", history_id).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="이수 이력을 찾을 수 없습니다.")

    # 파일 크기 제한 (10MB)
    MAX_SIZE = 10 * 1024 * 1024
    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="파일 크기가 초과되었습니다. (최대 10MB)")

    # 파일 형식 체크
    allowed_types = ["application/pdf", "image/jpeg", "image/png"]
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="PDF, JPG, PNG 파일만 업로드 가능합니다.")

    # Supabase Storage 업로드
    ext = file.filename.split(".")[-1] if "." in file.filename else "bin"
    storage_path = f"education/{history_id}/{uuid.uuid4()}.{ext}"

    try:
        upload_res = supabase.storage.from_("tai-files").upload(
            storage_path, content, {"content-type": file.content_type}
        )
        file_url = supabase.storage.from_("tai-files").get_public_url(storage_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"파일 업로드 실패: {str(e)}")

    # education_files 테이블에 메타데이터 저장
    meta = {
        "history_id": history_id,
        "file_name": file.filename,
        "file_url": file_url,
        "storage_path": storage_path,
        "doc_type": doc_type,
        "file_size": len(content),
        "mime_type": file.content_type,
        "created_at": datetime.utcnow().isoformat(),
    }
    res = supabase.table("education_files").insert(meta).execute()

    return {"success": True, "data": res.data[0] if res.data else meta}


@router.delete("/education-history/{history_id}/files/{file_id}", tags=["교육관리"])
def delete_education_file(
    history_id: str,
    file_id: str,
    supabase: Client = Depends(get_supabase)
):
    """교육 증빙서류 삭제"""
    file_row = supabase.table("education_files") \
        .select("*").eq("id", file_id).eq("history_id", history_id).single().execute()

    if not file_row.data:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")

    # Storage에서 삭제
    storage_path = file_row.data.get("storage_path")
    if storage_path:
        try:
            supabase.storage.from_("tai-files").remove([storage_path])
        except Exception:
            pass  # Storage 삭제 실패해도 DB는 삭제

    # DB에서 삭제
    supabase.table("education_files").delete().eq("id", file_id).execute()
    return {"success": True, "message": "파일이 삭제되었습니다."}
