"""
routers/matching.py — v1.0.0
전문가 매칭 신청 / 상태 관리 / 어드민 통계

파이프라인:
  RECEIVED → MATCHING → PROPOSED → SELECTED
  → CONTRACTING → CONTRACTED → IN_PROGRESS
  → CONFIRMING → SETTLED → CLOSED
  예외: CANCELLED / FAILED / DROPPED

prefix: /matching  (main.py에서 지정)
"""
from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator

from db.supabase_client import get_supabase
from routers.auth import get_current_user

log    = logging.getLogger(__name__)
router = APIRouter()   # prefix는 main.py에서 지정


# ── 상태 전이 규칙 ──────────────────────────────────────────────────────
STATUS_TRANSITIONS: Dict[str, set] = {
    "RECEIVED":    {"MATCHING", "CANCELLED"},
    "MATCHING":    {"PROPOSED", "FAILED", "CANCELLED"},
    "PROPOSED":    {"SELECTED", "CANCELLED"},
    "SELECTED":    {"CONTRACTING", "DROPPED"},
    "CONTRACTING": {"CONTRACTED", "DROPPED"},
    "CONTRACTED":  {"IN_PROGRESS"},
    "IN_PROGRESS": {"CONFIRMING"},
    "CONFIRMING":  {"SETTLED"},
    "SETTLED":     {"CLOSED"},
}

# 상태 전이 시 자동 기록할 타임스탬프 컬럼
STATUS_TIMESTAMP_MAP: Dict[str, str] = {
    "MATCHING":  "matched_at",
    "SELECTED":  "selected_at",
    "CANCELLED": "cancelled_at",
}


# ── 유틸 ──────────────────────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("role_code") != "001":
        raise HTTPException(status_code=403, detail="어드민만 접근 가능합니다.")
    return current_user


# ── 수수료 계산 유틸 ──────────────────────────────────────────────────
def calc_commission(
    supabase: Any,
    expert_type: str,
    amount: int,
    period_months: int,
) -> dict:
    """
    price_commission 테이블 기반 수수료 계산.
    서비스종류 × 기간 × 금액 → 수수료율 조회.
    조건에 맞는 레코드가 없으면 기본 10% 적용.
    """
    fee_rate = 10.0
    try:
        res = (
            supabase.table("price_commission")
            .select("fee_rate")
            .eq("service_type", expert_type)
            .eq("is_active", True)
            .limit(1)
            .execute()
        )
        if res.data:
            fee_rate = float(res.data[0].get("fee_rate", 10.0))
    except Exception as e:
        log.warning(f"[MATCHING] calc_commission 조회 실패, 기본 10% 적용: {e}")

    tai_fee_amount = round(amount * fee_rate / 100)
    expert_amount  = amount - tai_fee_amount
    return {
        "fee_rate":       fee_rate,
        "tai_fee_amount": tai_fee_amount,
        "expert_amount":  expert_amount,
    }


# ── Pydantic 모델 ──────────────────────────────────────────────────────
class MatchingRequestBody(BaseModel):
    # 필수
    user_id:     str
    expert_type: str
    title:       str

    # 선택
    company_id:      Optional[str]       = None
    factory_id:      Optional[str]       = None
    service_regions: Optional[List[str]] = None
    budget_min:      Optional[int]       = None
    budget_max:      Optional[int]       = None
    start_date:      Optional[str]       = None   # YYYY-MM-DD
    duration_months: Optional[int]       = None
    description:     Optional[str]       = None
    requirements:    Optional[dict]      = None
    source:          Optional[str]       = "SITE"  # SITE / SAAS / DIAGNOSIS_REPORT

    @field_validator("expert_type")
    @classmethod
    def check_expert_type(cls, v: str) -> str:
        if v not in {"EXPERT", "CONSULTING", "REPAIR"}:
            raise ValueError("expert_type은 EXPERT/CONSULTING/REPAIR 중 하나여야 합니다.")
        return v


class StatusUpdateBody(BaseModel):
    status: str
    memo:   Optional[str] = None


# ════════════════════════════════════════════════════════════════════════
# 엔드포인트
# ════════════════════════════════════════════════════════════════════════

@router.post("/requests")
def create_request(
    body: MatchingRequestBody,
    current_user: dict = Depends(get_current_user),
):
    """
    매칭 신청 접수
    POST /matching/requests

    1. 본인인증 확인 (identity_verified)
    2. matching_requests INSERT (status=RECEIVED)
    3. status_history 초기화
    """
    # 1. 본인인증 확인
    if not current_user.get("identity_verified"):
        raise HTTPException(status_code=403, detail="본인인증이 필요합니다.")

    supabase = get_supabase()
    now      = _now_iso()

    status_history = [{"status": "RECEIVED", "at": now, "by": current_user["id"]}]

    res = supabase.table("matching_requests").insert({
        "user_id":          current_user["id"],
        "expert_type":      body.expert_type,
        "title":            body.title,
        "company_id":       body.company_id,
        "factory_id":       body.factory_id,
        "service_regions":  body.service_regions,
        "budget_min":       body.budget_min,
        "budget_max":       body.budget_max,
        "start_date":       body.start_date,
        "duration_months":  body.duration_months,
        "description":      body.description,
        "requirements":     body.requirements,
        "source":           body.source,
        "status":           "RECEIVED",
        "status_history":   status_history,
        "created_at":       now,
        "updated_at":       now,
    }).execute()

    if not res.data:
        raise HTTPException(status_code=500, detail="저장 실패")

    log.info(f"[MATCHING] 신청 접수 — id={res.data[0]['id']} type={body.expert_type}")
    return {
        "status": "success",
        "data": {
            "request_id": res.data[0]["id"],
            "status":     "RECEIVED",
            "message":    "매칭 신청이 접수되었습니다. 담당자가 확인 후 연락드립니다.",
        },
    }


@router.get("/requests/my")
def my_requests(
    user_id: str          = Query(..., description="회원 UUID"),
    status:  Optional[str] = Query(None),
    page: int = Query(1,  ge=1),
    size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    """
    회원: 내 매칭 신청 목록
    GET /matching/requests/my?user_id={uuid}
    """
    if current_user["id"] != user_id:
        raise HTTPException(status_code=403, detail="권한이 없습니다.")

    supabase = get_supabase()
    q = supabase.table("matching_requests").select(
        "id, expert_type, title, status, source, "
        "service_regions, budget_min, budget_max, start_date, duration_months, "
        "created_at, updated_at",
        count="exact",
    ).eq("user_id", user_id)

    if status:
        q = q.eq("status", status)

    offset = (page - 1) * size
    res    = q.order("created_at", desc=True).range(offset, offset + size - 1).execute()
    total  = res.count or 0

    return {
        "status": "success",
        "data": {
            "items":       res.data or [],
            "total":       total,
            "page":        page,
            "size":        size,
            "total_pages": (total + size - 1) // size if total else 0,
        },
    }


@router.get("/requests")
def list_requests(
    expert_type: Optional[str] = Query(None),
    status:      Optional[str] = Query(None),
    source:      Optional[str] = Query(None),
    company_id:  Optional[str] = Query(None),
    keyword:     Optional[str] = Query(None, description="제목 검색"),
    date_from:   Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to:     Optional[str] = Query(None, description="YYYY-MM-DD"),
    page: int = Query(1,  ge=1),
    size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(_require_admin),
):
    """
    어드민: 매칭 신청 목록
    GET /matching/requests
    """
    supabase = get_supabase()
    q = supabase.table("matching_requests").select(
        "id, user_id, expert_type, title, status, source, company_id, factory_id, "
        "service_regions, budget_min, budget_max, start_date, duration_months, "
        "description, matched_at, selected_at, cancelled_at, "
        "created_at, updated_at",
        count="exact",
    )

    if expert_type: q = q.eq("expert_type", expert_type)
    if status:      q = q.eq("status",      status)
    if source:      q = q.eq("source",      source)
    if company_id:  q = q.eq("company_id",  company_id)
    if keyword:     q = q.ilike("title",    f"%{keyword}%")
    if date_from:   q = q.gte("created_at", date_from)
    if date_to:     q = q.lte("created_at", f"{date_to}T23:59:59")

    offset = (page - 1) * size
    res    = q.order("created_at", desc=True).range(offset, offset + size - 1).execute()
    total  = res.count or 0

    return {
        "status": "success",
        "data": {
            "items":       res.data or [],
            "total":       total,
            "page":        page,
            "size":        size,
            "total_pages": (total + size - 1) // size if total else 0,
        },
    }


@router.get("/requests/{request_id}")
def get_request(
    request_id:   str,
    current_user: dict = Depends(get_current_user),
):
    """
    매칭 신청 상세
    GET /matching/requests/{request_id}

    - 어드민: 전체 정보 + matching_results + matching_contracts
    - 일반 회원: 본인 신청만
    """
    supabase = get_supabase()
    req_res  = (
        supabase.table("matching_requests")
        .select("*")
        .eq("id", request_id)
        .limit(1)
        .execute()
    )
    if not req_res.data:
        raise HTTPException(status_code=404, detail="신청을 찾을 수 없습니다.")

    req = req_res.data[0]

    # 본인 또는 어드민 접근 허용
    is_admin = current_user.get("role_code") == "001"
    if not is_admin and req.get("user_id") != current_user["id"]:
        raise HTTPException(status_code=403, detail="권한이 없습니다.")

    # 매칭 결과 (제안서 목록)
    results_res = (
        supabase.table("matching_results")
        .select("*")
        .eq("request_id", request_id)
        .order("created_at", desc=False)
        .execute()
    )

    # 계약서
    contract_res = (
        supabase.table("matching_contracts")
        .select("*")
        .eq("request_id", request_id)
        .limit(1)
        .execute()
    )

    return {
        "status": "success",
        "data": {
            "request":  req,
            "results":  results_res.data or [],
            "contract": contract_res.data[0] if contract_res.data else None,
        },
    }


@router.patch("/requests/{request_id}/status")
def update_status(
    request_id:   str,
    body:         StatusUpdateBody,
    current_user: dict = Depends(_require_admin),
):
    """
    어드민: 매칭 상태 변경 (전이 규칙 검증)
    PATCH /matching/requests/{request_id}/status
    """
    supabase = get_supabase()
    req_res  = (
        supabase.table("matching_requests")
        .select("id, status, status_history")
        .eq("id", request_id)
        .limit(1)
        .execute()
    )
    if not req_res.data:
        raise HTTPException(status_code=404, detail="신청을 찾을 수 없습니다.")

    current_status = req_res.data[0]["status"]
    allowed        = STATUS_TRANSITIONS.get(current_status, set())

    if body.status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"'{current_status}' 상태에서 '{body.status}'로 변경할 수 없습니다. "
                   f"허용 전이: {allowed}",
        )

    now     = _now_iso()
    history = req_res.data[0].get("status_history") or []
    history.append({
        "status": body.status,
        "at":     now,
        "by":     current_user["id"],
        "memo":   body.memo or "",
    })

    update_row: Dict[str, Any] = {
        "status":         body.status,
        "status_history": history,
        "updated_at":     now,
    }
    # 상태별 타임스탬프 자동 기록
    ts_col = STATUS_TIMESTAMP_MAP.get(body.status)
    if ts_col:
        update_row[ts_col] = now

    supabase.table("matching_requests").update(update_row).eq("id", request_id).execute()

    log.info(f"[MATCHING STATUS] {request_id}: {current_status} → {body.status}")
    return {
        "status": "success",
        "data":   {"request_id": request_id, "status": body.status},
    }


@router.get("/admin/stats")
def admin_stats(current_user: dict = Depends(_require_admin)):
    """
    어드민 대시보드 통계
    GET /matching/admin/stats
    - 상태별 건수
    - 서비스유형별 건수
    - 전체 건수
    """
    supabase = get_supabase()

    # 한 번에 status + expert_type 조회
    res = supabase.table("matching_requests").select("status, expert_type").execute()
    rows = res.data or []

    status_count = dict(Counter(r["status"]      for r in rows))
    type_count   = dict(Counter(r["expert_type"] for r in rows))

    return {
        "status": "success",
        "data": {
            "by_status":      status_count,
            "by_expert_type": type_count,
            "total":          len(rows),
        },
    }
