from __future__ import annotations

import logging
from collections import Counter
from typing import Any, Dict, Optional

from db.supabase_client import get_supabase
from schemas.matching import MatchingRequestBody, StatusUpdateBody
from services.matching_helpers import STATUS_TIMESTAMP_MAP, now_iso, validate_status_transition
from .errors import MatchingSvcError

log = logging.getLogger(__name__)


def calc_commission(
    supabase: Any,
    expert_type: str,
    amount: int,
    period_months: int,
) -> dict:
    del period_months
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
        log.warning("[MATCHING] calc_commission 조회 실패, 기본 10%% 적용: %s", e)
    tai_fee_amount = round(amount * fee_rate / 100)
    expert_amount = amount - tai_fee_amount
    return {"fee_rate": fee_rate, "tai_fee_amount": tai_fee_amount, "expert_amount": expert_amount}


def create_matching_request(body: MatchingRequestBody, user_id: str) -> dict:
    supabase = get_supabase()
    n = now_iso()
    status_history = [{"status": "RECEIVED", "at": n, "by": user_id}]
    res = supabase.table("matching_requests").insert({
        "user_id": user_id,
        "expert_type": body.expert_type,
        "title": body.title,
        "company_id": body.company_id,
        "factory_id": body.factory_id,
        "service_regions": body.service_regions,
        "budget_min": body.budget_min,
        "budget_max": body.budget_max,
        "start_date": body.start_date,
        "duration_months": body.duration_months,
        "description": body.description,
        "requirements": body.requirements,
        "source": body.source,
        "status": "RECEIVED",
        "status_history": status_history,
        "created_at": n,
        "updated_at": n,
    }).execute()
    if not res.data:
        raise MatchingSvcError(500, "저장 실패")
    log.info("[MATCHING] 신청 접수 — id=%s type=%s", res.data[0]["id"], body.expert_type)
    return {
        "status": "success",
        "data": {
            "request_id": res.data[0]["id"],
            "status": "RECEIVED",
            "message": "매칭 신청이 접수되었습니다. 담당자가 확인 후 연락드립니다.",
        },
    }


def list_my_requests(
    user_id: str,
    status: Optional[str],
    page: int,
    size: int,
) -> dict:
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
    res = q.order("created_at", desc=True).range(offset, offset + size - 1).execute()
    total = res.count or 0
    return {
        "status": "success",
        "data": {
            "items": res.data or [],
            "total": total,
            "page": page,
            "size": size,
            "total_pages": (total + size - 1) // size if total else 0,
        },
    }


def list_requests_admin(
    expert_type: Optional[str],
    status: Optional[str],
    source: Optional[str],
    company_id: Optional[str],
    keyword: Optional[str],
    date_from: Optional[str],
    date_to: Optional[str],
    page: int,
    size: int,
) -> dict:
    supabase = get_supabase()
    q = supabase.table("matching_requests").select(
        "id, user_id, expert_type, title, status, source, company_id, factory_id, "
        "service_regions, budget_min, budget_max, start_date, duration_months, "
        "description, matched_at, selected_at, cancelled_at, "
        "created_at, updated_at",
        count="exact",
    )
    if expert_type:
        q = q.eq("expert_type", expert_type)
    if status:
        q = q.eq("status", status)
    if source:
        q = q.eq("source", source)
    if company_id:
        q = q.eq("company_id", company_id)
    if keyword:
        q = q.ilike("title", f"%{keyword}%")
    if date_from:
        q = q.gte("created_at", date_from)
    if date_to:
        q = q.lte("created_at", f"{date_to}T23:59:59")
    offset = (page - 1) * size
    res = q.order("created_at", desc=True).range(offset, offset + size - 1).execute()
    total = res.count or 0
    return {
        "status": "success",
        "data": {
            "items": res.data or [],
            "total": total,
            "page": page,
            "size": size,
            "total_pages": (total + size - 1) // size if total else 0,
        },
    }


def get_request_detail(request_id: str, viewer_user_id: str, viewer_role_code: Optional[str]) -> dict:
    supabase = get_supabase()
    req_res = (
        supabase.table("matching_requests")
        .select("*")
        .eq("id", request_id)
        .limit(1)
        .execute()
    )
    if not req_res.data:
        raise MatchingSvcError(404, "신청을 찾을 수 없습니다.")
    req = req_res.data[0]
    is_admin = viewer_role_code == "001"
    if not is_admin and req.get("user_id") != viewer_user_id:
        raise MatchingSvcError(403, "권한이 없습니다.")
    results_res = (
        supabase.table("matching_results")
        .select("*")
        .eq("request_id", request_id)
        .order("created_at", desc=False)
        .execute()
    )
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
            "request": req,
            "results": results_res.data or [],
            "contract": contract_res.data[0] if contract_res.data else None,
        },
    }


def update_request_status(
    request_id: str,
    body: StatusUpdateBody,
    admin_user_id: str,
) -> dict:
    supabase = get_supabase()
    req_res = (
        supabase.table("matching_requests")
        .select("id, status, status_history")
        .eq("id", request_id)
        .limit(1)
        .execute()
    )
    if not req_res.data:
        raise MatchingSvcError(404, "신청을 찾을 수 없습니다.")
    current_status = req_res.data[0]["status"]
    try:
        validate_status_transition(current_status, body.status)
    except ValueError as e:
        raise MatchingSvcError(400, str(e)) from e
    n = now_iso()
    history = req_res.data[0].get("status_history") or []
    history.append({
        "status": body.status,
        "at": n,
        "by": admin_user_id,
        "memo": body.memo or "",
    })
    update_row: Dict[str, Any] = {
        "status": body.status,
        "status_history": history,
        "updated_at": n,
    }
    ts_col = STATUS_TIMESTAMP_MAP.get(body.status)
    if ts_col:
        update_row[ts_col] = n
    supabase.table("matching_requests").update(update_row).eq("id", request_id).execute()
    log.info("[MATCHING STATUS] %s: %s → %s", request_id, current_status, body.status)
    return {"status": "success", "data": {"request_id": request_id, "status": body.status}}


def admin_stats_simple() -> dict:
    supabase = get_supabase()
    res = supabase.table("matching_requests").select("status, expert_type").execute()
    rows = res.data or []
    status_count = dict(Counter(r["status"] for r in rows))
    type_count = dict(Counter(r["expert_type"] for r in rows))
    return {
        "status": "success",
        "data": {
            "by_status": status_count,
            "by_expert_type": type_count,
            "total": len(rows),
        },
    }
