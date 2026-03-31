"""
교육 발령·이수 관리 라우터 — v1.0.0

학습자/작업자 단위 교육 발령, 이수 완료, 이수증 업로드, 회사별 교육 링크 설정

DB:
  education_master            교육 종류 마스터 (20건)
  education_assignment        발령 관리 (1인 1행)
  company_education_setting   회사별 교육 링크 재정의

endpoints (prefix /education):
  GET    /education/master                           마스터 목록
  GET    /education/company-settings                 회사별 링크 목록 (effective_url 포함)
  PUT    /education/company-settings/{education_id}  링크 저장/수정 (UPSERT)
  DELETE /education/company-settings/{education_id}  기본값으로 초기화
  POST   /education/assign                           교육 발령 (다건)
  GET    /education/assignments/summary              요약 통계
  GET    /education/assignments                      목록 조회 (effective_url 포함)
  PATCH  /education/assignment/{id}/complete         이수 완료
  POST   /education/assignment/{id}/certificate      이수증 URL 저장
  POST   /education/assignments/expire               만료 처리 (크론용)
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone, date
from db.supabase_client import get_supabase

router = APIRouter(prefix="/education", tags=["education_assign"])

VERSION = "1.0.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _effective_url(master: dict, setting: dict) -> dict:
    """
    유효 URL 우선순위:
    1순위: company_education_setting.custom_url
    2순위: education_master.source_url
    3순위: None
    """
    custom_url = (setting or {}).get("custom_url", "") or ""
    source_url = (master or {}).get("source_url", "") or ""

    if custom_url.strip():
        return {
            "effective_url":       custom_url,
            "effective_url_label": (setting or {}).get("custom_url_label") or "회사 교육 포털",
            "custom_note":         (setting or {}).get("custom_note") or "",
            "has_custom":          True,
        }
    elif source_url.strip():
        return {
            "effective_url":       source_url,
            "effective_url_label": "KOSHA 기본 링크",
            "custom_note":         "",
            "has_custom":          False,
        }
    else:
        return {
            "effective_url":       None,
            "effective_url_label": "",
            "custom_note":         "이수증만 업로드하세요.",
            "has_custom":          False,
        }


# ============================================================
# Pydantic 모델
# ============================================================

class CompanyEduSettingBody(BaseModel):
    company_id:       str
    custom_url:       Optional[str] = None
    custom_url_label: Optional[str] = None
    custom_note:      Optional[str] = None
    is_active:        bool = True


class AssignBody(BaseModel):
    factory_id:   str
    education_id: str
    due_date:     str              # YYYY-MM-DD
    worker_ids:   List[str] = []   # worker_registry.id
    user_ids:     List[str] = []   # users.id
    note:         Optional[str] = None


class CompleteBody(BaseModel):
    completed_at:    Optional[str]   = None  # ISO datetime
    completed_hours: Optional[float] = None
    certificate_url: Optional[str]   = None
    note:            Optional[str]   = None


class CertBody(BaseModel):
    certificate_url: str


# ============================================================
# GET /education/master
# ============================================================

@router.get("/master")
def get_education_master(
    is_active: Optional[bool] = Query(None),
):
    """education_master 목록 조회."""
    supabase = get_supabase()
    q = supabase.table("education_master").select("*")
    if is_active is not None:
        q = q.eq("is_active", is_active)
    res = q.order("education_code").execute()
    return {"status": "success", "data": {"items": res.data or [], "total": len(res.data or [])}}


# ============================================================
# GET /education/company-settings  ← /{education_id} 앞에 선언
# ============================================================

@router.get("/company-settings")
def get_company_settings(
    company_id: str = Query(..., description="회사 ID"),
    education_id: Optional[str] = Query(None, description="특정 교육 ID (단건 필터)"),
):
    """
    education_master 전체 + 회사별 custom_url 합쳙 반환.
    effective_url / has_custom 포함.
    """
    supabase = get_supabase()

    # education_master
    mq = supabase.table("education_master").select("*").eq("is_active", True)
    if education_id:
        mq = mq.eq("id", education_id)
    master_res = mq.order("education_code").execute()
    masters    = master_res.data or []

    # company_education_setting
    sq = supabase.table("company_education_setting").select("*").eq(
        "company_id", company_id
    )
    if education_id:
        sq = sq.eq("education_id", education_id)
    setting_res = sq.execute()
    setting_map = {s["education_id"]: s for s in (setting_res.data or [])}

    result = []
    for m in masters:
        s   = setting_map.get(m["id"], {})
        eff = _effective_url(m, s)
        result.append({
            "id":               m["id"],
            "education_code":   m["education_code"],
            "education_name":   m["education_name"],
            "required_hours":   m.get("required_hours"),
            "cycle_type":       m.get("cycle_type"),
            "cycle_desc":       m.get("cycle_desc"),
            "source_url":       m.get("source_url"),
            "setting_id":       s.get("id"),
            "custom_url":       s.get("custom_url"),
            "custom_url_label": s.get("custom_url_label"),
            "custom_note":      s.get("custom_note"),
            **eff,
        })

    if education_id and result:
        return {"status": "success", "data": result[0]}
    return {"status": "success", "data": {"items": result, "total": len(result)}}


# ============================================================
# PUT /education/company-settings/{education_id}  UPSERT
# ============================================================

@router.put("/company-settings/{education_id}")
def upsert_company_setting(education_id: str, body: CompanyEduSettingBody):
    """
    회사별 교육 링크 저장/수정 (UPSERT).
    company_id + education_id 기준으로 존재 시 UPDATE, 없으면 INSERT.
    """
    supabase = get_supabase()
    now = _now_iso()

    exist = supabase.table("company_education_setting").select("id").eq(
        "company_id", body.company_id
    ).eq("education_id", education_id).limit(1).execute()

    payload = {
        "company_id":       body.company_id,
        "education_id":     education_id,
        "custom_url":       body.custom_url or "",
        "custom_url_label": body.custom_url_label or "",
        "custom_note":      body.custom_note or "",
        "is_active":        body.is_active,
        "updated_at":       now,
    }

    if exist.data:
        res = supabase.table("company_education_setting").update(payload).eq(
            "id", exist.data[0]["id"]
        ).execute()
    else:
        payload["created_at"] = now
        res = supabase.table("company_education_setting").insert(payload).execute()

    if not res.data:
        raise HTTPException(status_code=500, detail="저장 실패")
    return {"status": "success", "message": "교육 링크가 저장됐습니다.", "data": res.data[0]}


# ============================================================
# DELETE /education/company-settings/{education_id}  초기화
# ============================================================

@router.delete("/company-settings/{education_id}")
def reset_company_setting(
    education_id: str,
    company_id: str = Query(...),
):
    """
    회사별 교육 링크 삭제 → KOSHA 기본 URL 사용 복원.
    """
    supabase = get_supabase()
    exist = supabase.table("company_education_setting").select("id").eq(
        "company_id", company_id
    ).eq("education_id", education_id).limit(1).execute()

    if not exist.data:
        return {"status": "success", "message": "설정이 없습니다. (이미 기본값 사용 중)"}

    supabase.table("company_education_setting").delete().eq(
        "id", exist.data[0]["id"]
    ).execute()
    return {"status": "success", "message": "기본값(기본 URL)으로 복원됐습니다."}


# ============================================================
# POST /education/assign  교육 발령 (다건)
# ============================================================

@router.post("/assign")
def assign_education(body: AssignBody):
    """
    교육 발령 (1인 1행).
    worker_ids 또는 user_ids 배열에 있는 모든 대상에 education_assignment 생성.
    """
    supabase = get_supabase()

    if not body.worker_ids and not body.user_ids:
        raise HTTPException(status_code=422, detail="worker_ids 또는 user_ids 중 하나는 필수입니다.")

    # education_master 존재 확인
    edu = supabase.table("education_master").select(
        "id, education_name"
    ).eq("id", body.education_id).limit(1).execute()
    if not edu.data:
        raise HTTPException(status_code=404, detail="교육 링스터를 찾을 수 없습니다.")

    now    = _now_iso()
    rows   = []

    for wid in (body.worker_ids or []):
        rows.append({
            "factory_id":   body.factory_id,
            "education_id": body.education_id,
            "worker_id":    wid,
            "user_id":      None,
            "due_date":     body.due_date,
            "status_code":  "PENDING",
            "assigned_at":  now,
            "note":         body.note,
            "created_at":   now,
            "updated_at":   now,
        })

    for uid in (body.user_ids or []):
        rows.append({
            "factory_id":   body.factory_id,
            "education_id": body.education_id,
            "worker_id":    None,
            "user_id":      uid,
            "due_date":     body.due_date,
            "status_code":  "PENDING",
            "assigned_at":  now,
            "note":         body.note,
            "created_at":   now,
            "updated_at":   now,
        })

    created = 0
    errors  = []
    for i in range(0, len(rows), 20):
        try:
            res = supabase.table("education_assignment").insert(rows[i:i+20]).execute()
            created += len(res.data or [])
        except Exception as e:
            errors.append(str(e))

    return {
        "status":  "success",
        "message": f"{created}건 발령 완료",
        "data": {
            "factory_id":    body.factory_id,
            "education_id":  body.education_id,
            "education_name": edu.data[0]["education_name"],
            "due_date":      body.due_date,
            "created":       created,
            "errors":        errors,
        }
    }


# ============================================================
# GET /education/assignments/summary  ← /{id} 앞에 선언
# ============================================================

@router.get("/assignments/summary")
def get_assignments_summary(
    factory_id:  Optional[str] = Query(None),
    company_id:  Optional[str] = Query(None),
):
    """education_assignment 요약 통계 (전체/완료/대기/초과)."""
    supabase = get_supabase()
    q = supabase.table("education_assignment").select("id, status_code")
    if factory_id: q = q.eq("factory_id", factory_id)
    if company_id:
        # factory_id를 통한 company 필터 없으므로 스킵 or factories JOIN 생략
        pass
    res   = q.execute()
    rows  = res.data or []
    total     = len(rows)
    completed = sum(1 for r in rows if r["status_code"] == "COMPLETED")
    pending   = sum(1 for r in rows if r["status_code"] == "PENDING")
    overdue   = sum(1 for r in rows if r["status_code"] == "OVERDUE")

    return {
        "status": "success",
        "data": {
            "total":     total,
            "completed": completed,
            "pending":   pending,
            "overdue":   overdue,
            "rate":      round(completed / total * 100, 1) if total else 0,
        }
    }


# ============================================================
# GET /education/assignments  목록 조회 (effective_url 포함)
# ============================================================

@router.get("/assignments")
def get_assignments(
    factory_id:   Optional[str]  = Query(None),
    company_id:   Optional[str]  = Query(None),
    education_id: Optional[str]  = Query(None),
    status_code:  Optional[str]  = Query(None, description="PENDING | COMPLETED | OVERDUE"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    """
    education_assignment 목록.
    education_master + company_education_setting 머지하여 effective_url 포함 반환.
    """
    supabase = get_supabase()

    q = supabase.table("education_assignment").select(
        "*, education_master(id, education_code, education_name, required_hours, source_url)",
        count="exact"
    )
    if factory_id:   q = q.eq("factory_id",   factory_id)
    if education_id: q = q.eq("education_id",  education_id)
    if status_code:  q = q.eq("status_code",   status_code)

    offset = (page - 1) * size
    res    = q.order("due_date").range(offset, offset + size - 1).execute()
    total  = res.count or 0
    rows   = res.data or []

    # 회사별 설정 전체 조회 (포함된 factory_id로 company_id 유추 시도)
    # 간단한 방식: 에듀 ID 목록로 설정 조회
    edu_ids = list({r["education_id"] for r in rows if r.get("education_id")})
    setting_map: dict = {}

    if edu_ids and factory_id:
        # factory → company_id
        fac = supabase.table("factories").select("company_id").eq(
            "id", factory_id
        ).limit(1).execute()
        cid = (fac.data[0].get("company_id") if fac.data else None)
        if cid:
            sr = supabase.table("company_education_setting").select("*").eq(
                "company_id", cid
            ).in_("education_id", edu_ids).execute()
            for s in (sr.data or []):
                setting_map[s["education_id"]] = s

    items = []
    for row in rows:
        master  = row.pop("education_master", {}) or {}
        eff     = _effective_url(master, setting_map.get(row.get("education_id"), {}))
        items.append({
            **row,
            "education_code":   master.get("education_code"),
            "education_name":   master.get("education_name"),
            "required_hours":   master.get("required_hours"),
            **eff,
        })

    return {
        "status": "success",
        "data": {
            "items":       items,
            "total":       total,
            "page":        page,
            "size":        size,
            "total_pages": (total + size - 1) // size if total else 0,
        }
    }


# ============================================================
# PATCH /education/assignment/{id}/complete  이수 완료
# ============================================================

@router.patch("/assignment/{assignment_id}/complete")
def complete_assignment(assignment_id: str, body: CompleteBody):
    """education_assignment 이수 완료 처리."""
    supabase = get_supabase()
    chk = supabase.table("education_assignment").select("id, status_code").eq(
        "id", assignment_id
    ).limit(1).execute()
    if not chk.data:
        raise HTTPException(status_code=404, detail="발령 레코드를 찾을 수 없습니다.")

    now = _now_iso()
    update_data: dict = {
        "status_code": "COMPLETED",
        "completed_at": body.completed_at or now,
        "updated_at":   now,
    }
    if body.completed_hours is not None:
        update_data["completed_hours"] = body.completed_hours
    if body.certificate_url:
        update_data["certificate_url"] = body.certificate_url
    if body.note:
        update_data["note"] = body.note

    res = supabase.table("education_assignment").update(update_data).eq(
        "id", assignment_id
    ).execute()
    return {"status": "success", "message": "이수 완료 처리됐습니다.", "data": res.data[0] if res.data else {}}


# ============================================================
# POST /education/assignment/{id}/certificate  이수증 URL 저장
# ============================================================

@router.post("/assignment/{assignment_id}/certificate")
def save_certificate(assignment_id: str, body: CertBody):
    """
    이수증 URL 저장.
    파일 업로드는 프론트에서 Supabase Storage 직접 업로드 후
    URL을 이 API로 저장하는 방식을 사용.
    """
    supabase = get_supabase()
    chk = supabase.table("education_assignment").select("id").eq(
        "id", assignment_id
    ).limit(1).execute()
    if not chk.data:
        raise HTTPException(status_code=404, detail="발령 레코드를 찾을 수 없습니다.")

    res = supabase.table("education_assignment").update({
        "certificate_url": body.certificate_url,
        "updated_at":      _now_iso(),
    }).eq("id", assignment_id).execute()

    return {
        "status":  "success",
        "message": "이수증 URL이 저장됐습니다.",
        "data":    {"certificate_url": body.certificate_url}
    }


# ============================================================
# POST /education/assignments/expire  만료 처리 (크론용)
# ============================================================

@router.post("/assignments/expire")
def expire_assignments():
    """
    due_date < 오늘 AND status_code = 'PENDING' → 'OVERDUE'
    크론에서 daily 실행. (크론: cron_job_master에 POST /education/assignments/expire 등록)
    """
    supabase = get_supabase()
    today = date.today().isoformat()

    try:
        res = supabase.table("education_assignment").update({
            "status_code": "OVERDUE",
            "updated_at":  _now_iso(),
        }).eq("status_code", "PENDING").lt("due_date", today).execute()
        updated = len(res.data or [])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"만료 처리 실패: {e}")

    return {
        "status":  "success",
        "message": f"{updated}건 만료 처리됐습니다.",
        "data":    {"updated": updated, "date": today},
    }
