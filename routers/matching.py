"""
routers/matching.py — v1.2.0
전문가 매칭 신청 / 상태 관리 / 제안서 시스템 / 어드민 통계

v1.2.0: 대시보드 + 파이프라인 + price_commission CRUD 추가
  - GET  /matching/admin/dashboard       매칭 대시보드 통계
  - GET  /matching/admin/pipeline        진행 중 파이프라인 목록
  - commission_router: GET/POST/PATCH/DELETE/POST-calculate /price-commission

v1.1.0: 제안서 시스템 전체
v1.0.0: 기본 매칭 신청·상태·통계
  - POST /matching/results/match                   어드민 전문가 배정
  - POST /matching/results/{id}/notify             전문가 알림 발송
  - POST /matching/results/{id}/view               전문가 신청 열람
  - POST /matching/results/{id}/propose            전문가 제안서 발송
  - GET  /matching/requests/{id}/proposals         제안서 목록 조회
  - POST /matching/results/{id}/select             신청자 전문가 선택
  - GET  /matching/my-proposals                    전문가 내 제안서 목록

v1.0.0: 기본 매칭 신청·상태·통계

  RECEIVED → MATCHING → PROPOSED → SELECTED
  → CONTRACTING → CONTRACTED → IN_PROGRESS
  → CONFIRMING → SETTLED → CLOSED
  예외: CANCELLED / FAILED / DROPPED

prefix: /matching  (main.py에서 지정)
"""
from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from schemas.matching import (
    CalcBody,
    CommissionBody,
    MatchResultCreateBody,
    MatchingRequestBody,
    ProposalBody,
    StatusUpdateBody,
)

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


# ════════════════════════════════════════════════════════════════════════
# 제안서 시스템 (v1.1.0)
# 플로우: MATCHED → NOTIFIED → VIEWED → PROPOSED → SELECTED
# ════════════════════════════════════════════════════════════════════════

@router.post("/results/match")
def create_match_result(
    body: MatchResultCreateBody,
    current_user: dict = Depends(_require_admin),
):
    """
    어드민: 전문가 배정 (매칭 결과 등록)
    POST /matching/results/match

    매칭 엔진이 없는 현재는 어드민 수동 배정.
    최초 배정 시 matching_requests → MATCHING 자동 전이.
    """
    supabase = get_supabase()
    now      = _now_iso()

    # 중복 매칭 방지
    dup = (
        supabase.table("matching_results")
        .select("id")
        .eq("request_id", body.request_id)
        .eq("supplier_id", body.supplier_id)
        .execute()
    )
    if dup.data:
        raise HTTPException(status_code=409, detail="이미 매칭된 전문가입니다.")

    res = supabase.table("matching_results").insert({
        "request_id":     body.request_id,
        "expert_user_id": body.expert_user_id,
        "supplier_type":  body.supplier_type,
        "supplier_id":    body.supplier_id,
        "rank_no":        body.rank_no,
        "match_score":    body.match_score,
        "status":         "MATCHED",
        "created_at":     now,
    }).execute()

    if not res.data:
        raise HTTPException(status_code=500, detail="매칭 결과 저장 실패")

    result_id = res.data[0]["id"]

    # matching_requests 상태 RECEIVED → MATCHING (최초 배정 시만)
    req = (
        supabase.table("matching_requests")
        .select("status, status_history")
        .eq("id", body.request_id)
        .limit(1)
        .execute()
    )
    if req.data and req.data[0]["status"] == "RECEIVED":
        history = req.data[0].get("status_history") or []
        history.append({"status": "MATCHING", "at": now, "by": current_user["id"]})
        supabase.table("matching_requests").update({
            "status":         "MATCHING",
            "status_history": history,
            "matched_at":     now,
            "updated_at":     now,
        }).eq("id", body.request_id).execute()

    log.info(f"[MATCH] 전문가 배정 result_id={result_id} request={body.request_id}")
    return {
        "status": "success",
        "data":   {"result_id": result_id, "status": "MATCHED"},
    }


@router.post("/results/{result_id}/notify")
def notify_expert(
    result_id:    str,
    current_user: dict = Depends(_require_admin),
):
    """
    어드민: 매칭된 전문가에게 알림 발송
    POST /matching/results/{result_id}/notify

    MATCHED 상태인 건만 발송 가능.
    """
    supabase = get_supabase()
    res = (
        supabase.table("matching_results")
        .select("id, status, expert_user_id, request_id")
        .eq("id", result_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="매칭 결과를 찾을 수 없습니다.")

    result = res.data[0]
    if result["status"] not in ("MATCHED",):
        raise HTTPException(status_code=400, detail="MATCHED 상태인 건만 알림 발송 가능합니다.")

    now = _now_iso()

    supabase.table("notifications").insert({
        "user_id":    result["expert_user_id"],
        "title":      "새 매칭 신청이 도착했습니다",
        "body":       "고객의 서비스 신청이 접수되었습니다. 내용을 확인하고 제안서를 작성해 주세요.",
        "type":       "MATCHING",
        "ref_id":     result["request_id"],
        "is_read":    False,
        "created_at": now,
    }).execute()

    supabase.table("matching_results").update({
        "status":      "NOTIFIED",
        "notified_at": now,
    }).eq("id", result_id).execute()

    return {"status": "success", "message": "전문가에게 알림이 발송되었습니다."}


@router.post("/results/{result_id}/view")
def mark_viewed(
    result_id:    str,
    current_user: dict = Depends(get_current_user),
):
    """
    전문가: 신청 내용 열람 처리
    POST /matching/results/{result_id}/view

    viewed_at 기록, NOTIFIED → VIEWED 전이.
    이미 PROPOSED/SELECTED/REJECTED 상태면 viewed_at만 기록.
    """
    supabase = get_supabase()
    res = (
        supabase.table("matching_results")
        .select("id, status, expert_user_id, request_id")
        .eq("id", result_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="매칭 결과를 찾을 수 없습니다.")

    result = res.data[0]
    if result["expert_user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="권한이 없습니다.")

    now         = _now_iso()
    update_data: Dict[str, Any] = {"viewed_at": now}

    if result["status"] not in ("PROPOSED", "SELECTED", "REJECTED"):
        update_data["status"] = "VIEWED"

    supabase.table("matching_results").update(update_data).eq("id", result_id).execute()

    # 신청 상세 함께 반환
    request_res = (
        supabase.table("matching_requests")
        .select("*")
        .eq("id", result.get("request_id", ""))
        .limit(1)
        .execute()
    )

    return {
        "status": "success",
        "data": {
            "result":  {**result, **update_data},
            "request": request_res.data[0] if request_res.data else None,
        },
    }


@router.post("/results/{result_id}/propose")
def submit_proposal(
    result_id:    str,
    body:         ProposalBody,
    current_user: dict = Depends(get_current_user),
):
    """
    전문가: 제안서 작성 및 발송
    POST /matching/results/{result_id}/propose

    처리:
      1. matching_results 제안서 필드 저장, PROPOSED
      2. matching_requests → PROPOSED (첫 번째 제안이면)
      3. 신청자 알림 발송
    """
    supabase = get_supabase()
    res = (
        supabase.table("matching_results")
        .select("id, status, expert_user_id, request_id")
        .eq("id", result_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="매칭 결과를 찾을 수 없습니다.")

    result = res.data[0]
    if result["expert_user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="권한이 없습니다.")
    if result["status"] not in ("MATCHED", "NOTIFIED", "VIEWED"):
        raise HTTPException(status_code=400, detail=f"제안서를 발송할 수 없는 상태입니다: {result['status']}")

    now        = _now_iso()
    request_id = result["request_id"]

    # 1. 제안서 저장
    supabase.table("matching_results").update({
        "proposal_title":   body.proposal_title,
        "proposal_content": body.proposal_content,
        "proposal_amount":  body.proposal_amount,
        "proposal_period":  body.proposal_period,
        "proposal_note":    body.proposal_note,
        "status":           "PROPOSED",
        "proposed_at":      now,
        "sent_at":          now,
    }).eq("id", result_id).execute()

    # 2. matching_requests → PROPOSED (첫 번째 제안이면)
    req = (
        supabase.table("matching_requests")
        .select("id, status, status_history, user_id")
        .eq("id", request_id)
        .limit(1)
        .execute()
    )
    if req.data:
        req_data = req.data[0]
        if req_data["status"] in ("MATCHING", "RECEIVED"):
            history = req_data.get("status_history") or []
            history.append({
                "status": "PROPOSED",
                "at":     now,
                "by":     "expert",
                "memo":   f"제안서 발송 — result_id={result_id}",
            })
            supabase.table("matching_requests").update({
                "status":         "PROPOSED",
                "status_history": history,
                "updated_at":     now,
            }).eq("id", request_id).execute()

        # 3. 신청자 알림
        client_user_id = req_data.get("user_id")
        if client_user_id:
            supabase.table("notifications").insert({
                "user_id":    client_user_id,
                "title":      "전문가 제안서가 도착했습니다",
                "body":       f"제안금액 {body.proposal_amount:,}원 / {body.proposal_period}개월 제안이 왔습니다.",
                "type":       "PROPOSAL",
                "ref_id":     request_id,
                "is_read":    False,
                "created_at": now,
            }).execute()

    log.info(f"[PROPOSAL] 제안서 발송 result_id={result_id}")
    return {
        "status": "success",
        "data": {
            "result_id":       result_id,
            "status":          "PROPOSED",
            "proposal_amount": body.proposal_amount,
            "proposal_period": body.proposal_period,
        },
    }


@router.get("/requests/{request_id}/proposals")
def list_proposals(
    request_id:   str,
    current_user: dict = Depends(get_current_user),
):
    """
    신청자/어드민: 특정 신청의 제안서 목록
    GET /matching/requests/{request_id}/proposals

    PROPOSED 이상 상태 제안서만 반환.
    신청자는 본인 신청만 조회 가능.
    """
    supabase = get_supabase()

    # 신청자 본인 확인
    if current_user.get("role_code") != "001":
        req = (
            supabase.table("matching_requests")
            .select("user_id")
            .eq("id", request_id)
            .limit(1)
            .execute()
        )
        if not req.data:
            raise HTTPException(status_code=404, detail="신청을 찾을 수 없습니다.")
        if req.data[0].get("user_id") != current_user["id"]:
            raise HTTPException(status_code=403, detail="권한이 없습니다.")

    res = (
        supabase.table("matching_results")
        .select(
            "id, supplier_type, supplier_id, expert_user_id, "
            "rank_no, match_score, status, "
            "proposal_title, proposal_content, proposal_amount, "
            "proposal_period, proposal_note, "
            "proposed_at, selected_at, viewed_at"
        )
        .eq("request_id", request_id)
        .in_("status", ["PROPOSED", "SELECTED", "REJECTED"])
        .order("rank_no")
        .execute()
    )

    return {
        "status": "success",
        "data":   {"items": res.data or [], "total": len(res.data or [])},
    }


@router.post("/results/{result_id}/select")
def select_expert(
    result_id:    str,
    current_user: dict = Depends(get_current_user),
):
    """
    신청자: 제안서 선택 (1명 확정)
    POST /matching/results/{result_id}/select

    처리:
      1. 선택 result → SELECTED, is_selected=true
      2. 나머지 PROPOSED → REJECTED
      3. matching_requests → SELECTED
      4. 선택된 전문가에게 알림
    """
    supabase = get_supabase()

    res = (
        supabase.table("matching_results")
        .select("id, status, request_id, expert_user_id")
        .eq("id", result_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="제안서를 찾을 수 없습니다.")

    result     = res.data[0]
    request_id = result["request_id"]

    if result["status"] != "PROPOSED":
        raise HTTPException(status_code=400, detail="PROPOSED 상태인 제안서만 선택할 수 있습니다.")

    # 신청자 본인 확인
    req = (
        supabase.table("matching_requests")
        .select("id, status, status_history, user_id")
        .eq("id", request_id)
        .limit(1)
        .execute()
    )
    if not req.data:
        raise HTTPException(status_code=404, detail="신청을 찾을 수 없습니다.")

    req_data = req.data[0]
    if current_user.get("role_code") != "001" and req_data.get("user_id") != current_user["id"]:
        raise HTTPException(status_code=403, detail="권한이 없습니다.")

    now = _now_iso()

    # 1. 선택 result → SELECTED
    supabase.table("matching_results").update({
        "status":      "SELECTED",
        "is_selected": True,
        "selected_at": now,
    }).eq("id", result_id).execute()

    # 2. 나머지 PROPOSED → REJECTED
    supabase.table("matching_results").update({
        "status":        "REJECTED",
        "rejected_at":   now,
        "reject_reason": "다른 전문가가 선택되었습니다.",
    }).eq("request_id", request_id).eq("status", "PROPOSED").neq("id", result_id).execute()

    # 3. matching_requests → SELECTED
    history = req_data.get("status_history") or []
    history.append({
        "status": "SELECTED",
        "at":     now,
        "by":     current_user["id"],
        "memo":   f"전문가 선택 — result_id={result_id}",
    })
    supabase.table("matching_requests").update({
        "status":         "SELECTED",
        "status_history": history,
        "selected_at":    now,
        "updated_at":     now,
    }).eq("id", request_id).execute()

    # 4. 선택된 전문가 알림
    if result.get("expert_user_id"):
        supabase.table("notifications").insert({
            "user_id":    result["expert_user_id"],
            "title":      "고객이 제안서를 선택했습니다! 🎉",
            "body":       "계약 진행을 위해 확인해 주세요.",
            "type":       "SELECTED",
            "ref_id":     request_id,
            "is_read":    False,
            "created_at": now,
        }).execute()

    log.info(f"[PROPOSAL SELECT] result_id={result_id} request={request_id}")
    return {
        "status": "success",
        "data": {
            "result_id":  result_id,
            "request_id": request_id,
            "status":     "SELECTED",
            "message":    "전문가가 선택되었습니다. 계약 진행 단계로 넘어갑니다.",
        },
    }


@router.get("/my-proposals")
def my_proposals(
    status: Optional[str] = Query(None),
    page: int = Query(1,  ge=1),
    size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    """
    전문가: 내가 받은/제출한 제안서 목록
    GET /matching/my-proposals
    """
    supabase = get_supabase()
    q = supabase.table("matching_results").select(
        "id, request_id, supplier_type, status, "
        "proposal_title, proposal_amount, proposal_period, "
        "match_score, rank_no, "
        "notified_at, viewed_at, proposed_at, selected_at",
        count="exact",
    ).eq("expert_user_id", current_user["id"])

    if status:
        q = q.eq("status", status)

    offset = (page - 1) * size
    res    = q.order("created_at", desc=True).range(offset, offset + size - 1).execute()
    total  = res.count or 0

    return {
        "status": "success",
        "data": {
            "items": res.data or [],
            "total": total,
            "page":  page,
            "size":  size,
            "total_pages": (total + size - 1) // size if total else 0,
        },
    }


# ════════════════════════════════════════════════════════════════════════
# 어드민 대시보드 + 파이프라인 (v1.2.0)
# ════════════════════════════════════════════════════════════════════════

@router.get("/admin/dashboard")
def admin_dashboard(current_user: dict = Depends(_require_admin)):
    """
    어드민 매칭 대시보드 통계
    GET /matching/admin/dashboard

    - 상태별 건수 / 서비스유형별 건수
    - 이번달 신규 신청 / 계약 성사 수
    - 이번달 정산 완료 합계
    - 정산 대기 건수 + 금액
    - 어드민 처리 필요 항목별 건수
    """
    supabase   = get_supabase()
    now        = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()

    # 1. matching_requests 전체
    req_res      = supabase.table("matching_requests").select("status, expert_type, created_at").execute()
    all_requests = req_res.data or []
    status_count = dict(Counter(r["status"]      for r in all_requests))
    type_count   = dict(Counter(r["expert_type"] for r in all_requests))

    this_month_new = sum(
        1 for r in all_requests
        if r.get("created_at", "") >= month_start
    )
    contracted_statuses = {"CONTRACTED", "IN_PROGRESS", "CONFIRMING", "SETTLED", "CLOSED"}
    this_month_contracted = sum(
        1 for r in all_requests
        if r.get("status") in contracted_statuses and r.get("created_at", "") >= month_start
    )

    # 2. settlements
    settle_res  = supabase.table("settlements").select("status, net_pay_amount, created_at").execute()
    settlements = settle_res.data or []

    pending     = [s for s in settlements if s.get("status") == "PENDING"]
    pending_cnt = len(pending)
    pending_amt = sum(s.get("net_pay_amount", 0) or 0 for s in pending)
    this_month_paid = sum(
        s.get("net_pay_amount", 0) or 0
        for s in settlements
        if s.get("status") == "PAID" and s.get("created_at", "") >= month_start
    )

    # 3. 어드민 처리 필요 항목
    action_needed = {
        "matching":    status_count.get("RECEIVED",   0),
        "proposing":   status_count.get("MATCHING",   0),
        "contracting": status_count.get("SELECTED",   0),
        "paying":      status_count.get("CONTRACTED", 0),
        "settling":    pending_cnt,
    }

    return {
        "status": "success",
        "data": {
            "total_requests":  len(all_requests),
            "by_status":       status_count,
            "by_expert_type":  type_count,
            "this_month": {
                "new_requests":   this_month_new,
                "contracted":     this_month_contracted,
                "settled_amount": this_month_paid,
            },
            "action_needed": action_needed,
            "settlement": {
                "pending_count":  pending_cnt,
                "pending_amount": pending_amt,
            },
        },
    }


@router.get("/admin/pipeline")
def admin_pipeline(
    expert_type: Optional[str] = Query(None),
    page: int = Query(1,  ge=1),
    size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(_require_admin),
):
    """
    어드민: 진행 중 매칭 파이프라인 목록
    GET /matching/admin/pipeline

    CLOSED / CANCELLED / FAILED / DROPPED 제외한 전체.
    updated_at 최신 순 정렬.
    """
    supabase        = get_supabase()
    exclude_statuses = ["CLOSED", "CANCELLED", "FAILED", "DROPPED"]

    q = supabase.table("matching_requests").select(
        "id, expert_type, title, status, source, "
        "budget_min, budget_max, service_regions, "
        "created_at, updated_at, matched_at, selected_at",
        count="exact",
    ).not_.in_("status", exclude_statuses)

    if expert_type:
        q = q.eq("expert_type", expert_type)

    offset = (page - 1) * size
    res    = q.order("updated_at", desc=True).range(offset, offset + size - 1).execute()
    total  = res.count or 0

    return {
        "status": "success",
        "data": {
            "items": res.data or [],
            "total": total,
            "page":  page,
            "size":  size,
            "total_pages": (total + size - 1) // size if total else 0,
        },
    }


# ════════════════════════════════════════════════════════════════════════
# price_commission CRUD — 별도 라우터로 분리
# main.py에서: app.include_router(commission_router, prefix="/price-commission")
# ════════════════════════════════════════════════════════════════════════

commission_router = APIRouter()   # prefix: /price-commission (main.py 지정)


@commission_router.get("")
def list_commissions(
    service_type: Optional[str]  = Query(None),
    is_active:    Optional[bool] = Query(None),
    current_user: dict = Depends(_require_admin),
):
    """어드민: 수수료율 목록 — GET /price-commission"""
    supabase = get_supabase()
    q        = supabase.table("price_commission").select("*")
    if service_type:          q = q.eq("service_type", service_type)
    if is_active is not None: q = q.eq("is_active",    is_active)
    res = q.order("service_type").order("period_min").order("amount_min").execute()
    return {"status": "success", "data": {"items": res.data or []}}


@commission_router.post("")
def create_commission(
    body:         CommissionBody,
    current_user: dict = Depends(_require_admin),
):
    """수수료율 신규 등록 — POST /price-commission"""
    supabase = get_supabase()
    now      = _now_iso()
    res      = supabase.table("price_commission").insert({
        "service_type": body.service_type,
        "fee_rate":     body.fee_rate,
        "period_min":   body.period_min,
        "period_max":   body.period_max,
        "amount_min":   body.amount_min,
        "amount_max":   body.amount_max,
        "description":  body.description,
        "is_active":    body.is_active,
        "created_at":   now,
        "updated_at":   now,
    }).execute()
    return {"status": "success", "data": res.data[0] if res.data else {}}


@commission_router.post("/calculate")
def calculate_commission(body: CalcBody):
    """
    수수료 미리 계산 (로그인 불필요 — 견적 확인용)
    POST /price-commission/calculate
    """
    supabase    = get_supabase()
    period_days = (body.period_months or 1) * 30

    res = (
        supabase.table("price_commission")
        .select("fee_rate, period_min, period_max, amount_min, amount_max, description")
        .eq("service_type", body.service_type)
        .eq("is_active", True)
        .execute()
    )

    fee_rate = 10.0
    if res.data:
        # 기간·금액 조건이 맞는 첫 번째 행 선택
        matched = False
        for row in res.data:
            p_min = row.get("period_min") or 0
            p_max = row.get("period_max") or 999_999
            a_min = row.get("amount_min") or 0
            a_max = row.get("amount_max") or 9_999_999_999
            if p_min <= period_days <= p_max and a_min <= body.contract_amount <= a_max:
                fee_rate = float(row["fee_rate"])
                matched  = True
                break
        if not matched:
            fee_rate = float(res.data[0]["fee_rate"])   # 기본율

    tai_fee    = round(body.contract_amount * fee_rate / 100)
    expert_amt = body.contract_amount - tai_fee

    return {
        "status": "success",
        "data": {
            "contract_amount": body.contract_amount,
            "fee_rate":        fee_rate,
            "tai_fee_amount":  tai_fee,
            "expert_amount":   expert_amt,
        },
    }


@commission_router.patch("/{commission_id}")
def update_commission(
    commission_id: str,
    body:          CommissionBody,
    current_user:  dict = Depends(_require_admin),
):
    """수수료율 수정 — PATCH /price-commission/{id}"""
    supabase = get_supabase()
    supabase.table("price_commission").update({
        "service_type": body.service_type,
        "fee_rate":     body.fee_rate,
        "period_min":   body.period_min,
        "period_max":   body.period_max,
        "amount_min":   body.amount_min,
        "amount_max":   body.amount_max,
        "description":  body.description,
        "is_active":    body.is_active,
        "updated_at":   _now_iso(),
    }).eq("id", commission_id).execute()
    return {"status": "success", "message": "수수료율이 수정되었습니다."}


@commission_router.delete("/{commission_id}")
def deactivate_commission(
    commission_id: str,
    current_user:  dict = Depends(_require_admin),
):
    """수수료율 비활성화 (소프트 삭제) — DELETE /price-commission/{id}"""
    supabase = get_supabase()
    supabase.table("price_commission").update({
        "is_active":  False,
        "updated_at": _now_iso(),
    }).eq("id", commission_id).execute()
    return {"status": "success", "message": "비활성화 처리되었습니다."}
