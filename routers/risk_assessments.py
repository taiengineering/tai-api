"""
위험성평가 관리 라우터 — v1.4.0

v1.4.0 (2026-07-29, Goal G-ms5zwv4v-b88c4a) — 완료 가드와 보존만료일
  [C1] 완료 시 ra_item 판정 결과를 점검한다. 허용 가능한 수준에 이르지 못한 요인이
       남아 있으면 완료를 막는다. 근거: 고시 제12조제3항 — 위험성 감소대책 실행 후
       해당 공정의 위험성이 허용 가능한 수준인지 확인하고, 미달이면 허용 가능한
       수준이 될 때까지 추가 대책을 수립·실행해야 한다.
       예외: 제12조제4항 — 즉시 개선이 곤란하면 暫定(잠정) 조치를 실행한 뒤
       개선계획을 수립·실행할 수 있다. 이 경우 is_interim 대책이 있으면 통과시키되
       warnings 로 표시한다.
  [C2] 완료 시 retention_until(보존만료일)을 산출해 저장한다.
       근거: 시행규칙 제37조제2항(3년 보존) + 고시 제14조제2항(기산점 = 완료한 날).
       보존연수는 ra_policy_param.RETENTION 에서 읽으므로 법 개정 시 코드 수정이 없다.
  [C3] 상시평가(CONTINUOUS)를 assessment_type 에 정식 반영(고시 제15조제4항).
  [C4] 요인 판정 결과가 있으면 risk_level 을 ra_item 기준으로 산출(items_json 대체).

v1.3.0 (2026-07-29) — 법정 기한의 상수 하드코딩 제거
  법정 주기·기한을 코드 상수가 아니라 ra_policy_param(services/ra_policy_svc)에서 읽는다.
  근거: 산업안전보건법 제36조제4항이 "평가의 방법, 절차 및 시기"를 고시에 전부 위임하고,
        「사업장 위험성평가에 관한 지침」(고시 제2024-76호) 제28조가 3년마다 재검토를 예고한다.
  배경: v1.1.0 까지 최초평가 기한이 "1년"으로 박혀 있었다(2014년 구 고시 부칙의 잔재).
        현행 고시 제15조제1항은 "1개월이 되는 날까지 착수" 이며 v1.2.0 에서 정정했으나,
        상수로 두는 한 같은 사고가 재발한다. 이번 버전에서 값의 출처를 데이터로 옮긴다.

v1.2.0 (2026-07-29) — 법령 원문 대조 후 긴급 정정
  [F1] 최초평가 기한 "1년 이내" → "1개월이 되는 날까지 착수" (고시 제15조제1항)
  [F2] GET /risk-assessments: date_from / date_to 쿼리 지원
  [F3] 목록·상세 응답에 risk_level(대표 등급) 파생 필드 추가
  [F4] assessment_type 기본값 통일 (DB default 와 동일한 REGULAR)

설계: docs/ops/tai-risk-assessment/PLAN_risk-assessment-design_v2.md
검증: docs/ops/tai-risk-assessment/RESEARCH_legal-verification_v1.md

API:
  POST   /risk-assessments                     등록
  GET    /risk-assessments                     목록 조회
  GET    /risk-assessments/dashboard           현황 요약 (고정경로)
  GET    /risk-assessments/{id}                상세 조회
  PATCH  /risk-assessments/{id}                수정
  POST   /risk-assessments/{id}/files          파일 첨부
  POST   /risk-assessments/{id}/complete       완료 처리 (가드 + 보존만료일 산출)

  ※ 요인·대책·재판정은 routers/ra_items.py (/ra/*)

assessment_type (고시 제15조):
  INITIAL     최초평가 — 사업 성립일(건설업은 실착공일)부터 정해진 기한 내 착수
  REGULAR     정기평가 — 정해진 주기마다 적정성 재검토 (제15조제3항)
  SPECIAL     수시평가 — 제15조제2항 각 호 사유 발생 시, 계획 실행 착수 전
                         (제5호 중대산업사고·휴업 이상 산업재해는 작업 재개 전)
  CONTINUOUS  상시평가 — 제15조제4항. 월1회 이상 발굴, 주1회 이상 논의·점검,
                         매 작업일 TBM 의 3요건을 갖추면 수시·정기평가를 실시한 것으로 본다.
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone, date
from db.supabase_client import get_supabase
from services.health_registry import register_probe
from services.ra_policy_svc import get_param_value, list_params
from services.ra_decision_svc import assessment_readiness

router = APIRouter(prefix="/risk-assessments", tags=["risk_assessments"])

VERSION = "1.4.0"

# 아래 값들은 '정본'이 아니라 조회 실패 시의 안전망이다.
# 정본은 ra_policy_param (미적용 시 services/ra_policy_svc._FALLBACK).
_SAFETY_INITIAL_DUE_MONTHS = 1     # 고시 제15조제1항
_SAFETY_PERIODIC_CYCLE_YEARS = 1   # 고시 제15조제3항
_SAFETY_RETENTION_YEARS = 3        # 시행규칙 제37조제2항

# 등급 표기 정규화용(프론트 배지). 등급 체계는 사업장 자율(고시 제9조제2항)이라
# 한글·영문 표기가 혼재할 수 있어 알려진 표기만 정규화하고 미지의 값은 그대로 통과시킨다.
_LEVEL_ORDER = {
    "HIGH": 3, "상": 3, "높음": 3, "위험": 3,
    "MEDIUM": 2, "중": 2, "보통": 2, "주의": 2,
    "LOW": 1, "하": 1, "낮음": 1, "양호": 1,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_leap(y: int) -> bool:
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _last_day(y: int, m: int) -> int:
    return [31, 29 if _is_leap(y) else 28, 31, 30, 31, 30,
            31, 31, 30, 31, 30, 31][m - 1]


def _add_months(d: date, months: int) -> date:
    """월 단위 가산. 말일 보정 포함."""
    y, m = divmod((d.year * 12 + (d.month - 1)) + months, 12)
    m += 1
    return date(y, m, min(d.day, _last_day(y, m)))


def _add_years(d: date, years: int) -> date:
    """연 단위 가산. 2/29 → 평년 2/28 보정."""
    y = d.year + years
    return date(y, d.month, min(d.day, _last_day(y, d.month)))


def _periodic_cycle_years() -> int:
    return int(get_param_value("PERIODIC_CYCLE", default=_SAFETY_PERIODIC_CYCLE_YEARS) or
               _SAFETY_PERIODIC_CYCLE_YEARS)


def _initial_due_months() -> int:
    return int(get_param_value("INITIAL_DUE", default=_SAFETY_INITIAL_DUE_MONTHS) or
               _SAFETY_INITIAL_DUE_MONTHS)


def _retention_years() -> int:
    return int(get_param_value("RETENTION", default=_SAFETY_RETENTION_YEARS) or
               _SAFETY_RETENTION_YEARS)


def _next_review(assessment_date_str: str, assessment_type: str) -> Optional[str]:
    """정기평가: assessment_date + 정기평가 주기(고시 제15조제3항). 기타: None."""
    if assessment_type != "REGULAR":
        return None
    try:
        d = date.fromisoformat(assessment_date_str)
        return _add_years(d, _periodic_cycle_years()).isoformat()
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


def _top_level(items_json) -> Optional[str]:
    """items_json 에서 가장 높은 위험 등급을 대표 등급으로 산출(프론트 배지용)."""
    if not items_json:
        return None
    best, best_rank = None, -1
    for it in items_json:
        if not isinstance(it, dict):
            continue
        lv = it.get("level") or it.get("risk_level") or it.get("grade")
        if not lv:
            continue
        rank = _LEVEL_ORDER.get(str(lv).strip().upper(), _LEVEL_ORDER.get(str(lv).strip(), 0))
        if rank > best_rank:
            best, best_rank = lv, rank
    return best


# ── Pydantic 모델 ─────────────────────────────────────────────

class RiskCreateBody(BaseModel):
    company_id:           Optional[str] = None
    factory_id:           Optional[str] = None
    construction_site_id: Optional[str] = None
    assessment_type:      str = "REGULAR"    # INITIAL | REGULAR | SPECIAL | CONTINUOUS

    title:            Optional[str]  = None
    work_name:        Optional[str]  = None        # work_name 입력 시 title로 저장

    assessment_date:  Optional[str]  = None        # YYYY-MM-DD
    evaluated_at:     Optional[str]  = None        # 평가일 별칭

    department:       Optional[str]  = None
    process_name:     Optional[str]  = None
    assessor_name:    Optional[str]  = None
    summary_text:     Optional[str]  = None

    items_json:       Optional[list] = None
    risk_factor:      Optional[str]  = None
    risk_level:       Optional[str]  = None
    countermeasure:   Optional[str]  = None

    evaluator_id:     Optional[str]  = None        # created_by 별칭
    created_by:       Optional[str]  = None
    next_review_date: Optional[str]  = None

    # 설계 v2 추가 필드
    scale_id:         Optional[str]  = None        # 척도(고시 제9조제2항) — 판정에 필수
    trigger_reason:   Optional[str]  = None        # 수시평가 사유(제15조제2항 각 호)
    prep_json:        Optional[dict] = None        # 사전조사 안전보건정보(제9조제1항)
    participants_json: Optional[list] = None       # 근로자 참여(제6조)

    # 최초평가 착수기한 판정용(선택). 건설업은 실착공일.
    business_start_date: Optional[str] = None


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
    scale_id:         Optional[str]  = None
    trigger_reason:   Optional[str]  = None
    prep_json:        Optional[dict] = None
    participants_json: Optional[list] = None


class FileAttachBody(BaseModel):
    file_url:  str
    file_name: str
    file_type: Optional[str] = None


# ── 고정경로 먼저 선언 ──────────────────────────────────────────

@router.get("/dashboard")
def get_dashboard(
    factory_id:           Optional[str] = Query(None),
    company_id:           Optional[str] = Query(None),
    construction_site_id: Optional[str] = Query(None),
    business_start_date:  Optional[str] = Query(None, description="사업 성립일(건설=실착공일) YYYY-MM-DD"),
):
    """
    위험성평가 현황 요약.
    - 최초평가 완료 여부 및 착수기한 초과 여부(고시 제15조제1항)
    - 정기평가 D-day
    - 수시평가 미완료 건수
    - 적용된 법정 기한 값과 그 출처(policy_source)
    """
    supabase = get_supabase()
    q = supabase.table("risk_assessments").select(
        "id, assessment_type, title, assessment_date, next_review_date, status_code, completed_at"
    )
    if factory_id:           q = q.eq("factory_id",           factory_id)
    if company_id:           q = q.eq("company_id",           company_id)
    if construction_site_id: q = q.eq("construction_site_id", construction_site_id)
    res = q.execute()
    rows = res.data or []

    initial_done    = any(r["assessment_type"] == "INITIAL" and r["status_code"] == "COMPLETED" for r in rows)
    initial_started = any(r["assessment_type"] == "INITIAL" for r in rows)
    pending_special = sum(1 for r in rows if r["assessment_type"] == "SPECIAL" and r["status_code"] != "COMPLETED")

    next_regular = None
    next_regular_dday = None
    for r in rows:
        if r["assessment_type"] == "REGULAR" and r.get("next_review_date"):
            dd = _dday(r["next_review_date"])
            if dd is not None and (next_regular_dday is None or dd < next_regular_dday):
                next_regular_dday = dd
                next_regular = r["next_review_date"]

    # 최초평가 착수기한 — 사업 성립일 + INITIAL_DUE(개월)
    due_months = _initial_due_months()
    initial_due_date = None
    initial_due_dday = None
    initial_overdue = None
    if business_start_date:
        try:
            initial_due_date = _add_months(date.fromisoformat(business_start_date), due_months).isoformat()
            initial_due_dday = _dday(initial_due_date)
            initial_overdue = (not initial_started) and initial_due_dday is not None and initial_due_dday < 0
        except Exception:
            initial_due_date = None

    total     = len(rows)
    completed = sum(1 for r in rows if r["status_code"] == "COMPLETED")
    draft     = sum(1 for r in rows if r["status_code"] == "DRAFT")

    policy = list_params()

    return {
        "status": "success",
        "data": {
            "total":             total,
            "completed":         completed,
            "draft":             draft,
            "initial_done":      initial_done,
            "initial_started":   initial_started,
            "initial_due_months": due_months,          # 법정 착수기한(개월) — 데이터에서 조회
            "initial_due_date":  initial_due_date,
            "initial_due_dday":  initial_due_dday,
            "initial_overdue":   initial_overdue,
            "pending_special":   pending_special,
            "next_regular_date": next_regular,
            "next_regular_dday": next_regular_dday,
            "periodic_cycle_years": _periodic_cycle_years(),
            "retention_years":      _retention_years(),
            "policy_source":     policy.get("source"),  # db | fallback
            "alert": (
                "최초평가 착수기한 경과" if initial_overdue else
                "최초평가 미완료" if not initial_done and total == 0 else
                f"정기평가 {abs(next_regular_dday)}일 경과" if next_regular_dday is not None and next_regular_dday < 0 else
                f"정기평가 D-{next_regular_dday}" if next_regular_dday is not None else
                None
            )
        }
    }


# ── CRUD ─────────────────────────────────────────────────

@router.post("")
def create_assessment(body: RiskCreateBody):
    """위험성평가 등록."""
    supabase = get_supabase()
    now = _now()

    title = body.title or body.work_name or ""
    if not title:
        raise HTTPException(status_code=422, detail="title 또는 work_name은 필수입니다.")

    assessment_date = body.assessment_date or body.evaluated_at or date.today().isoformat()
    created_by = body.created_by or body.evaluator_id

    items_json = body.items_json or []
    if not items_json and body.risk_factor:
        items_json = [{
            "hazard":  body.risk_factor,
            "level":   body.risk_level or "MEDIUM",
            "measure": body.countermeasure or "",
            "freq":    None,
            "sev":     None,
            "score":   None,
        }]

    next_review = body.next_review_date or _next_review(assessment_date, body.assessment_type)
    row = {
        "company_id":           body.company_id,
        "factory_id":           body.factory_id,
        "construction_site_id": body.construction_site_id,
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
        "retention_years":      _retention_years(),   # 데이터에서 조회
        "next_review_date":     next_review,
        "ai_generated":         False,
        "created_by":           created_by,
        "created_at":           now,
        "updated_at":           now,
    }
    # 설계 v2 컬럼은 존재할 때만 실어 보낸다(미적용 환경 호환).
    for k, v in (("scale_id", body.scale_id), ("trigger_reason", body.trigger_reason),
                 ("prep_json", body.prep_json), ("participants_json", body.participants_json)):
        if v is not None:
            row[k] = v

    res = supabase.table("risk_assessments").insert(row).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="위험성평가 등록에 실패했습니다.")

    record = res.data[0]
    record["next_review_dday"] = _dday(next_review)
    record["risk_level"] = _top_level(items_json)
    return {"status": "success", "message": "위험성평가가 등록되었습니다.", "data": record}


@router.get("")
def list_assessments(
    factory_id:           Optional[str] = Query(None),
    company_id:           Optional[str] = Query(None),
    construction_site_id: Optional[str] = Query(None),
    assessment_type:      Optional[str] = Query(None),
    status_code:          Optional[str] = Query(None),
    year:                 Optional[int] = Query(None),
    date_from:            Optional[str] = Query(None, description="YYYY-MM-DD (assessment_date >=)"),
    date_to:              Optional[str] = Query(None, description="YYYY-MM-DD (assessment_date <=)"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    """위험성평가 목록 조회. date_from/date_to 가 지정되면 year 보다 우선한다."""
    supabase = get_supabase()
    q = supabase.table("risk_assessments").select(
        "id, company_id, factory_id, construction_site_id, "
        "assessment_type, title, assessment_date, "
        "process_name, assessor_name, status_code, next_review_date, "
        "retention_years, files_json, items_json, completed_at, created_at",
        count="exact"
    )
    if factory_id:           q = q.eq("factory_id",           factory_id)
    if company_id:           q = q.eq("company_id",           company_id)
    if construction_site_id: q = q.eq("construction_site_id", construction_site_id)
    if assessment_type:      q = q.eq("assessment_type",      assessment_type)
    if status_code:          q = q.eq("status_code",          status_code)

    if date_from or date_to:
        if date_from:
            q = q.gte("assessment_date", date_from)
        if date_to:
            q = q.lte("assessment_date", date_to)
    elif year:
        q = q.gte("assessment_date", f"{year}-01-01").lte("assessment_date", f"{year}-12-31")

    offset = (page - 1) * size
    res = q.order("assessment_date", desc=True).range(offset, offset + size - 1).execute()
    total = res.count or 0

    items = []
    for row in (res.data or []):
        row["next_review_dday"] = _dday(row.get("next_review_date"))
        row["file_count"]       = len(row.get("files_json") or [])
        row["item_count"]       = len(row.get("items_json") or [])
        row["risk_level"]       = _top_level(row.get("items_json"))
        row.pop("items_json", None)   # 목록 경량화 — 상세에서 제공
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
    record["risk_level"] = _top_level(record.get("items_json"))
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
    supabase.table("risk_assessments").update({
        "files_json": files,
        "updated_at": _now(),
    }).eq("id", assessment_id).execute()
    return {"status": "success", "message": "파일이 첨부되었습니다.", "data": {"files": files}}


def _readiness_of(assessment_id: str) -> Optional[dict]:
    """ra_item / ra_control 기반 완료 가능 여부. 테이블 미적용이면 None."""
    sb = get_supabase()
    try:
        items = (sb.table("ra_item").select("*")
                 .eq("assessment_id", assessment_id).execute().data) or []
    except Exception:
        return None   # 스키마 미적용 환경 — 가드를 건너뛰되 완료는 막지 않는다.

    controls: dict = {}
    ids = [str(i["id"]) for i in items]
    if ids:
        try:
            rows = sb.table("ra_control").select("*").in_("item_id", ids).execute().data or []
            for c in rows:
                controls.setdefault(str(c["item_id"]), []).append(c)
        except Exception:
            controls = {}
    return assessment_readiness(items, controls)


@router.post("/{assessment_id}/complete")
def complete_assessment(assessment_id: str):
    """위험성평가 완료 처리.

    가드 — 고시 제12조제3항: 감소대책 실행 후에도 허용 가능한 수준에 이르지 못한
    유해·위험요인이 남아 있으면 완료할 수 없다. 다만 제12조제4항에 따라 잠정조치를
    실행한 요인은 통과시키고 경고로 표시한다.

    보존만료일 — 시행규칙 제37조제2항(보존연수) + 고시 제14조제2항(기산점 = 완료한 날).
    """
    supabase = get_supabase()

    cur = supabase.table("risk_assessments").select("id, status_code").eq(
        "id", assessment_id).limit(1).execute()
    if not cur.data:
        raise HTTPException(status_code=404, detail="위험성평가를 찾을 수 없습니다.")

    ready = _readiness_of(assessment_id)
    if ready and not ready.get("can_complete"):
        raise HTTPException(status_code=409, detail={
            "code": "RA_NOT_ACCEPTABLE",
            "message": ("허용 가능한 수준에 이르지 못한 유해·위험요인이 남아 있습니다. "
                        "고시 제12조제3항에 따라 추가 감소대책을 수립·실행하거나, "
                        "제12조제4항에 따른 잠정조치를 등록한 뒤 완료하십시오."),
            "open_items": ready.get("open_items"),
            "warnings": ready.get("warnings"),
        })

    years = _retention_years()
    today = date.today()
    retention_until = _add_years(today, years).isoformat()

    now = _now()
    payload = {
        "status_code":     "COMPLETED",
        "completed_at":    now,
        "retention_years": years,          # 완료 시점 기준값으로 갱신
        "updated_at":      now,
    }
    try:
        res = supabase.table("risk_assessments").update(
            {**payload, "retention_until": retention_until}
        ).eq("id", assessment_id).execute()
    except Exception:
        # retention_until 컬럼 미적용 환경 — 완료 자체는 진행한다.
        res = supabase.table("risk_assessments").update(payload).eq(
            "id", assessment_id).execute()
        retention_until = None

    if not res.data:
        raise HTTPException(status_code=404, detail="위험성평가를 찾을 수 없습니다.")

    return {
        "status": "success",
        "message": "완료 처리되었습니다.",
        "data": {
            **res.data[0],
            "retention_until": retention_until,
            "retention_basis": "고시 제14조제2항 — 완료한 날부터 기산",
        },
        "warnings": (ready or {}).get("warnings") or [],
    }


async def _probe_risk():
    sb = get_supabase()
    r = sb.table("risk_assessments").select("id", count="exact").limit(1).execute()
    return {"assessments_count": r.count or 0, "policy_source": list_params().get("source")}


register_probe(
    "risk",
    _probe_risk,
    critical=False,
    desc_ko="위험성평가",
    meta={
        "impacts": [{"name": "위험성평가", "page": "safe > 위험관리 > 위험성평가"}],
        "fix_links": [{"name": "Supabase DB", "url": "https://supabase.com/dashboard/project/vwlahtguyggrhvslabax"}],
        "api": "GET /risk-assessments",
        "code": "routers/risk_assessments.py",
    },
)
