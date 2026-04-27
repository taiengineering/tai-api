"""
위험성평가 관리 라우터 — v1.1.0

v1.1.0 (2026-04-07 Phase 3):
  - risk_assessments.construction_site_id 콓럼 추가 (migration)
  - GET /risk-assessments: construction_site_id 필터 지원
  - POST /risk-assessments body: construction_site_id 저장 지원
  - work_name, risk_factor, risk_level, countermeasure, evaluator_id, evaluated_at
    인수 지원 (내부적으로 title, items_json, created_by, assessment_date에 매핑)

risk_assessments 테이블 사용

API:
  POST   /risk-assessments                     등록
  GET    /risk-assessments                     목록 조회
  GET    /risk-assessments/dashboard           현황 요약 (고정경로)
  GET    /risk-assessments/{id}                상세 조회
  PATCH  /risk-assessments/{id}                수정
  POST   /risk-assessments/{id}/files          파일 쳊부
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
from services.health_registry import register_probe

router = APIRouter(prefix="/risk-assessments", tags=["risk_assessments"])

VERSION = "1.1.0"

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
    company_id:           Optional[str] = None
    factory_id:           Optional[str] = None
    construction_site_id: Optional[str] = None   # v1.1.0: 건설현장 연결
    assessment_type:      str = "SPECIAL"         # INITIAL | REGULAR | SPECIAL

    # 작업지시서의 work_name → title
    title:            Optional[str]  = None
    work_name:        Optional[str]  = None       # work_name 입력 시 title로 저장

    assessment_date:  Optional[str]  = None       # YYYY-MM-DD (evaluated_at과 중복 허용)
    evaluated_at:     Optional[str]  = None       # 평가일 별칭 지원

    department:       Optional[str]  = None
    process_name:     Optional[str]  = None
    assessor_name:    Optional[str]  = None
    summary_text:     Optional[str]  = None

    # items_json 벡크 OR risk_factor/risk_level/countermeasure 단일 입력
    items_json:       Optional[list] = None
    risk_factor:      Optional[str]  = None       # 단일 위험요인
    risk_level:       Optional[str]  = None       # HIGH | MEDIUM | LOW
    countermeasure:   Optional[str]  = None       # 조치사항

    evaluator_id:     Optional[str]  = None       # created_by 별칭
    created_by:       Optional[str]  = None
    next_review_date: Optional[str]  = None


class RiskUpdateBody(BaseModel):
    title:            Optional[str]  = None
    assessment_date:  Optional[str]  = None
    department:       Optional[str]  = None
    process_name:     Optional[str]  = None
    assessor_name:    Optional[str]  = None
    summary_text:     Optional[str]  = None
    items_json:       Optional[list] = None
    next_review_date: Optional[str]  = None
    construction_site_id: Optional[str] = None


class FileAttachBody(BaseModel):
    file_url:  str
    file_name: str
    file_type: Optional[str] = None


# ── 고정경로 먼저 선언 ──────────────────────────────────────────

@router.get("/dashboard")
def get_dashboard(
    factory_id:           Optional[str] = Query(None),
    company_id:           Optional[str] = Query(None),
    construction_site_id: Optional[str] = Query(None),  # v1.1.0
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
    if factory_id:           q = q.eq("factory_id",           factory_id)
    if company_id:           q = q.eq("company_id",           company_id)
    if construction_site_id: q = q.eq("construction_site_id", construction_site_id)  # v1.1.0
    res = q.execute()
    rows = res.data or []

    initial_done    = any(r["assessment_type"] == "INITIAL" and r["status_code"] == "COMPLETED" for r in rows)
    pending_special = sum(1 for r in rows if r["assessment_type"] == "SPECIAL" and r["status_code"] != "COMPLETED")

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
            "total":             total,
            "completed":         completed,
            "draft":             draft,
            "initial_done":      initial_done,
            "pending_special":   pending_special,
            "next_regular_date": next_regular,
            "next_regular_dday": next_regular_dday,
            "alert": (
                "최초평가 미완료" if not initial_done and total == 0 else
                f"정기평가 {abs(next_regular_dday)}일 초과" if next_regular_dday is not None and next_regular_dday < 0 else
                f"정기평가 D-{next_regular_dday}" if next_regular_dday is not None else
                None
            )
        }
    }


# ── CRUD ─────────────────────────────────────────────────

@router.post("")
def create_assessment(body: RiskCreateBody):
    """
    위험성평가 등록.

    v1.1.0: work_name/risk_factor/risk_level/countermeasure/evaluator_id/evaluated_at 지원
    - work_name 또는 title 중 하나 필수
    - risk_factor+risk_level+countermeasure → items_json 단일항목으로 자동변환
    - evaluator_id → created_by 매핑
    - evaluated_at → assessment_date 매핑
    """
    supabase = get_supabase()
    now = _now()

    # title 정리
    title = body.title or body.work_name or ""
    if not title:
        raise HTTPException(status_code=422, detail="title 또는 work_name은 필수입니다.")

    # assessment_date 정리
    assessment_date = body.assessment_date or body.evaluated_at or date.today().isoformat()

    # evaluator_id 정리
    created_by = body.created_by or body.evaluator_id

    # items_json 정리
    # risk_factor/risk_level/countermeasure 단일 입력 시 items_json으로 자동 변환
    items_json = body.items_json or []
    if not items_json and body.risk_factor:
        items_json = [{
            "hazard":       body.risk_factor,
            "level":        body.risk_level or "MEDIUM",
            "measure":      body.countermeasure or "",
            "freq":         None,
            "sev":          None,
            "score":        None,
        }]

    next_review = body.next_review_date or _next_review(assessment_date, body.assessment_type)
    row = {
        "company_id":           body.company_id,
        "factory_id":           body.factory_id,
        "construction_site_id": body.construction_site_id,   # v1.1.0
        "assessment_type":      body.assessment_type,
        "title":                title,
        "assessment_date":      assessment_date,
        "department":           body.department,
        "process_name":         body.process_name,
        "assessor_name":        body.assessor_name,
        "summary_text":         body.summary_text,
        "items_json":           items_json,
        "files_json":           [],
        "status_code":          "DRAFT",
        "retention_years":      RETENTION_YEARS,
        "next_review_date":     next_review,
        "ai_generated":         False,
        "created_by":           created_by,
        "created_at":           now,
        "updated_at":           now,
    }
    res = supabase.table("risk_assessments").insert(row).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="위험성평가 등록에 실패했습니다.")

    record = res.data[0]
    record["next_review_dday"] = _dday(next_review)
    return {"status": "success", "message": "위험성평가가 등록되었습니다.", "data": record}


@router.get("")
def list_assessments(
    factory_id:           Optional[str] = Query(None),
    company_id:           Optional[str] = Query(None),
    construction_site_id: Optional[str] = Query(None),   # v1.1.0
    assessment_type:      Optional[str] = Query(None),
    status_code:          Optional[str] = Query(None),
    year:                 Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    """위험성평가 목록 조회."""
    supabase = get_supabase()
    q = supabase.table("risk_assessments").select(
        "id, company_id, factory_id, construction_site_id, "
        "assessment_type, title, assessment_date, "
        "process_name, assessor_name, status_code, next_review_date, "
        "retention_years, files_json, completed_at, created_at",
        count="exact"
    )
    if factory_id:           q = q.eq("factory_id",           factory_id)
    if company_id:           q = q.eq("company_id",           company_id)
    if construction_site_id: q = q.eq("construction_site_id", construction_site_id)  # v1.1.0
    if assessment_type:      q = q.eq("assessment_type",      assessment_type)
    if status_code:          q = q.eq("status_code",          status_code)
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
    return {"status": "success", "message": "수정되었습니다.", "data": res.data[0]}


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
    return {"status": "success", "message": "파일이 첨부되었습니다.", "data": {"files": files}}


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
    return {"status": "success", "message": "완료 처리되었습니다.", "data": res.data[0]}


async def _probe_risk():
    sb = get_supabase()
    r = sb.table("risk_assessments").select("id", count="exact").limit(1).execute()
    return {"assessments_count": r.count or 0}


register_probe(
    "risk",
    _probe_risk,
    critical=False,
    desc_ko="위험성평가",
    meta={
        "impacts": [{"name": "위험성평가", "page": "safe > 위험관리 > 위험성평가"}],
        "fix_links": [{"name": "Supabase DB", "url": "https://supabase.com/dashboard/project/xntdkrjhgcscmqctdzyo"}],
        "api": "GET /risk-assessments",
        "code": "routers/risk_assessments.py",
    },
)
