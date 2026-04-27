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
from services.health_registry import register_probe

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


class EducationPendingCreate(BaseModel):
    """교육 발령(미이수 배정) — pending 행 생성"""
    factory_id: str
    user_id: str
    education_code: str
    due_date: Optional[date] = None
    memo: Optional[str] = None


class CompanyEducationSettingUpsert(BaseModel):
    custom_url: Optional[str] = None
    custom_url_label: Optional[str] = None
    custom_note: Optional[str] = None
    is_active: Optional[bool] = True


def _merge_master_company_row(m: dict, srow: Optional[dict]) -> dict:
    source_url = (m.get("source_url") or "").strip() or None
    mid = m.get("id")
    has_custom = False
    custom_url = None
    custom_label = None
    custom_note = None
    if srow and srow.get("is_active", True):
        cu = (srow.get("custom_url") or "").strip()
        if cu:
            has_custom = True
            custom_url = cu
            custom_label = (srow.get("custom_url_label") or "").strip() or None
            custom_note = (srow.get("custom_note") or "").strip() or None
    effective_url = (custom_url or source_url or None)
    eff_label = None
    if has_custom and custom_url:
        eff_label = custom_label or "회사 교육 링크"
    elif source_url:
        eff_label = "KOSHA/기본 링크"
    return {
        "education_id": str(mid) if mid is not None else None,
        "education_code": m.get("education_code"),
        "education_name": m.get("education_name") or m.get("education_code"),
        "min_hours": m.get("min_hours"),
        "cycle_trigger_code": m.get("cycle_trigger_code"),
        "cycle_value": m.get("cycle_value"),
        "cycle_unit_code": m.get("cycle_unit_code"),
        "cycle_status_code": m.get("hours_status_code") or m.get("cycle_status_code"),
        "source_url": source_url,
        "effective_url": effective_url,
        "effective_url_label": eff_label,
        "has_custom": has_custom,
        "custom_url": custom_url,
        "custom_url_label": custom_label,
        "custom_note": custom_note or "",
        "is_active_setting": srow.get("is_active", True) if srow else True,
    }


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


@router.get("/education/company-effective-link", tags=["교육관리"])
def get_education_company_effective_link(
    company_id: str = Query(..., description="회사 ID"),
    education_code: str = Query(..., description="education_master.education_code"),
    supabase: Client = Depends(get_supabase),
):
    """
    교육 수강 링크 표시 우선순위:
    1) company_education_setting.custom_url (테이블이 있고 행이 있는 경우)
    2) education_master.source_url (KOSHA 등 기본값)
    3) 없음 → effective_url null (프론트에서 이수증만 안내)
    """
    mres = supabase.table("education_master").select("*").eq("education_code", education_code).limit(1).execute()
    if not mres.data:
        raise HTTPException(status_code=404, detail="교육 마스터를 찾을 수 없습니다.")
    m = mres.data[0]
    mid = m.get("id")
    source_url = (m.get("source_url") or "").strip() or None
    education_name = m.get("education_name") or education_code

    custom_url = None
    custom_label = None
    custom_note = None
    has_custom = False

    try:
        if mid:
            ces = (
                supabase.table("company_education_setting")
                .select("*")
                .eq("company_id", company_id)
                .eq("education_id", mid)
                .limit(1)
                .execute()
            )
            row = (ces.data or [None])[0]
            if row and row.get("is_active", True):
                cu = (row.get("custom_url") or "").strip()
                if cu:
                    custom_url = cu
                    custom_label = (row.get("custom_url_label") or "").strip() or None
                    custom_note = (row.get("custom_note") or "").strip() or None
                    has_custom = True
    except Exception:
        pass

    effective_url = (custom_url or source_url or None)
    eff_label = None
    if has_custom and custom_url:
        eff_label = custom_label or "회사 교육 링크"
    elif source_url:
        eff_label = "KOSHA/기본 링크"

    return {
        "success": True,
        "data": {
            "education_code": education_code,
            "education_name": education_name,
            "source_url": source_url,
            "effective_url": effective_url,
            "effective_url_label": eff_label,
            "has_custom": has_custom,
            "custom_note": custom_note or "",
        },
    }


@router.get("/education/company-settings", tags=["교육관리"])
def get_company_education_settings(
    company_id: str = Query(..., description="회사 ID"),
    supabase: Client = Depends(get_supabase),
):
    """education_master + company_education_setting 병합 목록 (회사별 수강 링크 설정 화면용)"""
    master_res = supabase.table("education_master").select("*").eq("is_active", True).order("sort_order").execute()
    setting_data = []
    try:
        setting_res = (
            supabase.table("company_education_setting")
            .select("*")
            .eq("company_id", company_id)
            .execute()
        )
        setting_data = setting_res.data or []
    except Exception:
        setting_data = []

    smap = {}
    for s in setting_data:
        eid = s.get("education_id")
        if eid is not None:
            smap[str(eid)] = s

    result = []
    for m in (master_res.data or []):
        mid = m.get("id")
        srow = smap.get(str(mid)) if mid is not None else None
        result.append(_merge_master_company_row(m, srow))

    return {"success": True, "data": result}


@router.put("/education/company-settings/{education_id}", tags=["교육관리"])
def upsert_company_education_setting(
    education_id: str,
    body: CompanyEducationSettingUpsert,
    company_id: str = Query(..., description="회사 ID"),
    supabase: Client = Depends(get_supabase),
):
    """회사별 교육 링크 저장·수정 (custom_url 비우면 행 삭제 → KOSHA 기본)"""
    mcheck = supabase.table("education_master").select("id").eq("id", education_id).limit(1).execute()
    if not mcheck.data:
        raise HTTPException(status_code=404, detail="교육 마스터를 찾을 수 없습니다.")

    cu = (body.custom_url or "").strip()
    if not cu:
        try:
            supabase.table("company_education_setting").delete().eq("company_id", company_id).eq(
                "education_id", education_id
            ).execute()
        except Exception:
            pass
        return {"success": True, "data": {"deleted": True}}

    row_label = (body.custom_url_label or "").strip() or None
    row_note = (body.custom_note or "").strip() or None
    row_active = body.is_active if body.is_active is not None else True

    existing = (
        supabase.table("company_education_setting")
        .select("id")
        .eq("company_id", company_id)
        .eq("education_id", education_id)
        .limit(1)
        .execute()
    )
    now = datetime.utcnow().isoformat()
    if existing.data:
        upd = {
            "custom_url": cu,
            "custom_url_label": row_label,
            "custom_note": row_note,
            "is_active": row_active,
            "updated_at": now,
        }
        res = (
            supabase.table("company_education_setting")
            .update(upd)
            .eq("company_id", company_id)
            .eq("education_id", education_id)
            .execute()
        )
    else:
        ins = {
            "company_id": company_id,
            "education_id": education_id,
            "custom_url": cu,
            "custom_url_label": row_label,
            "custom_note": row_note,
            "is_active": row_active,
            "created_at": now,
            "updated_at": now,
        }
        res = supabase.table("company_education_setting").insert(ins).execute()

    return {"success": True, "data": res.data[0] if res.data else {}}


@router.delete("/education/company-settings/{education_id}", tags=["교육관리"])
def delete_company_education_setting(
    education_id: str,
    company_id: str = Query(..., description="회사 ID"),
    supabase: Client = Depends(get_supabase),
):
    """회사별 교육 링크 초기화 (KOSHA 기본으로 복원)"""
    try:
        supabase.table("company_education_setting").delete().eq("company_id", company_id).eq(
            "education_id", education_id
        ).execute()
    except Exception:
        pass
    return {"success": True, "data": {"deleted": True}}


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

def _filter_education_rows_by_search(rows: list, search: Optional[str]) -> list:
    if not search or not str(search).strip():
        return rows
    s = str(search).strip().lower()
    out = []
    for r in rows or []:
        u = r.get("users") or {}
        m = r.get("education_master") or {}
        un = (u.get("name") or "").lower()
        en = (m.get("education_name") or "").lower()
        if s in un or s in en:
            out.append(r)
    return out


@router.get("/education-history", tags=["교육관리"])
def get_education_history(
    factory_id: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    education_code: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="pending / completed / overdue"),
    category: Optional[str] = Query(None, description="worker_safety / duty / training"),
    search: Optional[str] = Query(None, description="이름·교육명 부분 검색(전체 로드 후 필터)"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    supabase: Client = Depends(get_supabase)
):
    """교육 이수 이력 목록 조회"""
    offset = (page - 1) * size
    q = supabase.table("education_history") \
        .select(
            "*, education_master(education_name, category, min_hours, due_rule), users(name, job_type, department, position), education_files(id)",
            count="exact",
        )

    if factory_id:
        q = q.eq("factory_id", factory_id)
    if user_id:
        q = q.eq("user_id", user_id)
    if education_code:
        q = q.eq("education_code", education_code)
    if status:
        q = q.eq("status", status)
    if category:
        mres = supabase.table("education_master").select("education_code").eq("category", category).eq("is_active", True).execute()
        codes = [x["education_code"] for x in (mres.data or [])]
        if not codes:
            return {
                "success": True,
                "data": {"items": [], "total": 0, "page": page, "size": size, "pages": 0},
            }
        q = q.in_("education_code", codes)

    if search and str(search).strip():
        res = q.order("due_date", desc=False).execute()
        rows = _filter_education_rows_by_search(res.data or [], search)
        total = len(rows)
        pages = (total + size - 1) // size if size else 1
        sliced = rows[offset : offset + size]
        return {
            "success": True,
            "data": {
                "items": sliced,
                "total": total,
                "page": page,
                "size": size,
                "pages": pages,
            },
        }

    res = q.order("due_date", desc=False).range(offset, offset + size - 1).execute()
    total = res.count or 0

    return {
        "success": True,
        "data": {
            "items": res.data,
            "total": total,
            "page": page,
            "size": size,
            "pages": (total + size - 1) // size if size else 0,
        },
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


@router.post("/education-history/pending", tags=["교육관리"])
def create_pending_education_history(body: EducationPendingCreate, supabase: Client = Depends(get_supabase)):
    """교육 발령 — 미이수(pending) 배정 행 생성"""
    master = (
        supabase.table("education_master")
        .select("education_code, education_name")
        .eq("education_code", body.education_code)
        .single()
        .execute()
    )
    if not master.data:
        raise HTTPException(status_code=404, detail="교육 마스터를 찾을 수 없습니다.")

    dup = (
        supabase.table("education_history")
        .select("id")
        .eq("factory_id", body.factory_id)
        .eq("user_id", body.user_id)
        .eq("education_code", body.education_code)
        .in_("status", ["pending", "overdue"])
        .limit(1)
        .execute()
    )
    if dup.data:
        raise HTTPException(status_code=400, detail="동일 교육이 이미 미이수로 배정되어 있습니다.")

    now = datetime.utcnow().isoformat()
    payload = {
        "factory_id": body.factory_id,
        "user_id": body.user_id,
        "education_code": body.education_code,
        "status": "pending",
        "due_date": str(body.due_date) if body.due_date else None,
        "completed_date": None,
        "completed_hours": 0,
        "memo": body.memo,
        "created_at": now,
        "updated_at": now,
    }
    res = supabase.table("education_history").insert(payload).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="교육 배정에 실패했습니다.")
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


async def _probe_education():
    sb = get_supabase()
    r = sb.table("education_history").select("id", count="exact").limit(1).execute()
    return {"records_count": r.count or 0}


register_probe("education", _probe_education, critical=False, desc_ko="교육 관리")
