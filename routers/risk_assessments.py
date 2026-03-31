"""
위험성평가 관리 라우터 — v1.0.0

risk_assessments 테이블 사용

API:
  POST   /risk-assessments                     등록
  GET    /risk-assessments                     목록 조회
  GET    /risk-assessments/dashboard           현황 요약 (고정경로)
  GET    /risk-assessments/{id}                상세 조회
  PATCH  /risk-assessments/{id}                수정
  POST   /risk-assessments/{id}/files          파일 첨부
  POST   /risk-assessments/{id}/complete       완료 처리

assessment_type:
  INITIAL   최초평가 (사업 개시 후 1년 이내)
  REGULAR   정기평가 (매년)
  SPECIAL   수시평가 (설비도입·공정변경·중대재해)
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone, date, timedelta
from db.supabase_client import get_supabase

router = APIRouter(prefix="/risk-assessments", tags=["risk_assessments"])

VERSION = "1.0.0"

RETENTION_YEARS = 3


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _next_review(assessment_date_str: str, assessment_type: str) -> Optional[str]:
    """정기평가: assessment_date + 1년. 기타: None."""
    if assessment_type != "REGULAR":
        return None
    try:
        d = date.fromisoformat(assessment_date_str)
        return date(d.year + 1, d.month, d.day).isoformat()
    except Exception:
        return None


def _dday(target_date_str: Optional[str]) -> Optional[int]:
    if not target_date_str:
        return None
    try:
        target = date.fromisoformat(target_date_str)
        return (target - date.today()).days
    except Exception:
        return None


# ── Pydantic 모델 ─────────────────────────────────────────────

class RiskCreateBody(BaseModel):
    company_id:       str
    factory_id:       Optional[str] = None
    assessment_type:  str                     # INITIAL | REGULAR | SPECIAL
    title:            str
    assessment_date:  str                     # YYYY-MM-DD
    department:       Optional[str] = None
    process_name:     Optional[str] = None
    assessor_name:    Optional[str] = None
    summary_text:     Optional[str] = None
    items_json:       Optional[list] = []     # 위험요인 항목 [{hazard, freq, sev, score, level, measure}]
    next_review_date: Optional[str] = None    # 수동 지정 시
    created_by:       Optional[str] = None


class RiskUpdateBody(BaseModel):
    title:            Optional[str]  = None
    assessment_date:  Optional[str]  = None
    department:       Optional[str]  = None
    process_name:     Optional[str]  = None
    assessor_name:    Optional[str]  = None
    summary_text:     Optional[str]  = None
    items_json:       Optional[list] = None
    next_review_date: Optional[str]  = None


class FileAttachBody(BaseModel):
    file_url:  str
    file_name: str
    file_type: Optional[str] = None


# ── 고정경로 먼저 선언 ────────────────────────────────────────

@router.get("/dashboard")
def get_dashboard(
    factory_id:  Optional[str] = Query(None),
    company_id:  Optional[str] = Query(None),
):
    """
    위험성평가 현황 요약.
    - 최초평가 완료 여부
    - 정기평가 D-day (다음 평가일까지)
    - 수시평가 미완료 건수
    - 전체 통계
    """
    supabase = get_supabase()
    q = supabase.table("risk_assessments").select(
        "id, assessment_type, title, assessment_date, next_review_date, status_code, completed_at"
    )
    if factory_id: q = q.eq("factory_id", factory_id)
    if company_id: q = q.eq("company_id", company_id)
    res = q.execute()
    rows = res.data or []

    initial_done  = any(r["assessment_type"] == "INITIAL" and r["status_code"] == "COMPLETED" for r in rows)
    pending_special = sum(1 for r in rows if r["assessment_type"] == "SPECIAL" and r["status_code"] != "COMPLETED")

    # 가장 가까운 정기평가 D-day
    next_regular = None
    next_regular_dday = None
    for r in rows:
        if r["assessment_type"] == "REGULAR" and r.get("next_review_date"):
            dd = _dday(r["next_review_date"])
            if dd is not None and (next_regular_dday is None or dd < next_regular_dday):
                next_regular_dday = dd
                next_regular = r["next_review_date"]

    total     = len(rows)
    completed = sum(1 for r in rows if r["status_code"] == "COMPLETED")
    draft     = sum(1 for r in rows if r["status_code"] == "DRAFT")

    return {
        "status": "success",
        "data": {
            "total":              total,
            "completed":          completed,
            "draft":              draft,
            "initial_done":       initial_done,
            "pending_special":    pending_special,
            "next_regular_date":  next_regular,
            "next_regular_dday": next_regular_dday,
            "alert": (
                "최초평가 미완료" if not initial_done and total == 0 else
                f"정기평가 {abs(next_regular_dday)}일 초과" if next_regular_dday is not None and next_regular_dday < 0 else
                f"정기평가 D-{next_regular_dday}" if next_regular_dday is not None else
                None
            )
        }
    }


# ── CRUD ─────────────────────────────────────────────────────

@router.post("")
def create_assessment(body: RiskCreateBody):
    """위험성평가 등록."""
    supabase = get_supabase()
    now = _now()

    next_review = body.next_review_date or _next_review(body.assessment_date, body.assessment_type)
    row = {
        "company_id":       body.company_id,
        "factory_id":       body.factory_id,
        "assessment_type":  body.assessment_type,
        "title":            body.title,
        "assessment_date":  body.assessment_date,
        "department":       body.department,
        "process_name":     body.process_name,
        "assessor_name":    body.assessor_name,
        "summary_text":     body.summary_text,
        "items_json":       body.items_json or [],
        "files_json":       [],
        "status_code":      "DRAFT",
        "retention_years":  RETENTION_YEARS,
        "next_review_date": next_review,
        "ai_generated":     False,
        "created_by":       body.created_by,
        "created_at":       now,
        "updated_at":       now,
    }
    res = supabase.table("risk_assessments").insert(row).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="위험성평가 등록에 실패했습니다.")

    record = res.data[0]
    record["next_review_dday"] = _dday(next_review)
    return {"status": "success", "message": "위험성평가가 등록됐습니다.", "data": record}


@router.get("")
def list_assessments(
    factory_id:      Optional[str] = Query(None),
    company_id:      Optional[str] = Query(None),
    assessment_type: Optional[str] = Query(None),
    status_code:     Optional[str] = Query(None),
    year:            Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    """위험성평가 목록 조회."""
    supabase = get_supabase()
    q = supabase.table("risk_assessments").select(
        "id, company_id, factory_id, assessment_type, title, assessment_date, "
        "process_name, assessor_name, status_code, next_review_date, "
        "retention_years, files_json, completed_at, created_at",
        count="exact"
    )
    if factory_id:      q = q.eq("factory_id",      factory_id)
    if company_id:      q = q.eq("company_id",      company_id)
    if assessment_type: q = q.eq("assessment_type", assessment_type)
    if status_code:     q = q.eq("status_code",     status_code)
    if year:
        q = q.gte("assessment_date", f"{year}-01-01").lte("assessment_date", f"{year}-12-31")

    offset = (page - 1) * size
    res = q.order("assessment_date", desc=True).range(offset, offset + size - 1).execute()
    total = res.count or 0

    items = []
    for row in (res.data or []):
        row["next_review_dday"] = _dday(row.get("next_review_date"))
        row["file_count"]       = len(row.get("files_json") or [])
        items.append(row)

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


@router.get("/{assessment_id}")
def get_assessment(assessment_id: str):
    """위험성평가 상세 조회."""
    supabase = get_supabase()
    res = supabase.table("risk_assessments").select("*").eq(
        "id", assessment_id
    ).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="위험성평가를 찾을 수 없습니다.")
    record = res.data[0]
    record["next_review_dday"] = _dday(record.get("next_review_date"))
    return {"status": "success", "data": record}


@router.patch("/{assessment_id}")
def update_assessment(assessment_id: str, body: RiskUpdateBody):
    """위험성평가 수정."""
    supabase = get_supabase()
    payload = {k: v for k, v in body.dict().items() if v is not None}
    if not payload:
        raise HTTPException(status_code=422, detail="수정할 내용이 없습니다.")
    payload["updated_at"] = _now()
    res = supabase.table("risk_assessments").update(payload).eq(
        "id", assessment_id
    ).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="위험성평가를 찾을 수 없습니다.")
    return {"status": "success", "message": "수정됐습니다.", "data": res.data[0]}


@router.post("/{assessment_id}/files")
def attach_file(assessment_id: str, body: FileAttachBody):
    """파일 URL 첨부."""
    supabase = get_supabase()
    chk = supabase.table("risk_assessments").select(
        "id, files_json"
    ).eq("id", assessment_id).limit(1).execute()
    if not chk.data:
        raise HTTPException(status_code=404, detail="위험성평가를 찾을 수 없습니다.")

    files = list(chk.data[0].get("files_json") or [])
    files.append({
        "url":      body.file_url,
        "name":     body.file_name,
        "type":     body.file_type,
        "added_at": _now(),
    })
    res = supabase.table("risk_assessments").update({
        "files_json": files,
        "updated_at": _now(),
    }).eq("id", assessment_id).execute()
    return {"status": "success", "message": "파일이 첨부됐습니다.", "data": {"files": files}}


@router.post("/{assessment_id}/complete")
def complete_assessment(assessment_id: str):
    """위험성평가 완료 처리."""
    supabase = get_supabase()
    now = _now()
    res = supabase.table("risk_assessments").update({
        "status_code":  "COMPLETED",
        "completed_at": now,
        "updated_at":   now,
    }).eq("id", assessment_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="위험성평가를 찾을 수 없습니다.")
    return {"status": "success", "message": "완료 처리됐습니다.", "data": res.data[0]}
