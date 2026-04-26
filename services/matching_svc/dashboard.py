from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Optional

from db.supabase_client import get_supabase


def get_dashboard_stats() -> dict:
    supabase = get_supabase()
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    req_res = supabase.table("matching_requests").select("status, expert_type, created_at").execute()
    all_requests = req_res.data or []
    status_count = dict(Counter(r["status"] for r in all_requests))
    type_count = dict(Counter(r["expert_type"] for r in all_requests))
    this_month_new = sum(
        1 for r in all_requests
        if r.get("created_at", "") >= month_start
    )
    contracted_statuses = {"CONTRACTED", "IN_PROGRESS", "CONFIRMING", "SETTLED", "CLOSED"}
    this_month_contracted = sum(
        1 for r in all_requests
        if r.get("status") in contracted_statuses and r.get("created_at", "") >= month_start
    )
    settle_res = supabase.table("settlements").select("status, net_pay_amount, created_at").execute()
    settlements = settle_res.data or []
    pending = [s for s in settlements if s.get("status") == "PENDING"]
    pending_cnt = len(pending)
    pending_amt = sum(s.get("net_pay_amount", 0) or 0 for s in pending)
    this_month_paid = sum(
        s.get("net_pay_amount", 0) or 0
        for s in settlements
        if s.get("status") == "PAID" and s.get("created_at", "") >= month_start
    )
    action_needed = {
        "matching": status_count.get("RECEIVED", 0),
        "proposing": status_count.get("MATCHING", 0),
        "contracting": status_count.get("SELECTED", 0),
        "paying": status_count.get("CONTRACTED", 0),
        "settling": pending_cnt,
    }
    return {
        "status": "success",
        "data": {
            "total_requests": len(all_requests),
            "by_status": status_count,
            "by_expert_type": type_count,
            "this_month": {
                "new_requests": this_month_new,
                "contracted": this_month_contracted,
                "settled_amount": this_month_paid,
            },
            "action_needed": action_needed,
            "settlement": {
                "pending_count": pending_cnt,
                "pending_amount": pending_amt,
            },
        },
    }


def get_pipeline(
    expert_type: Optional[str],
    page: int,
    size: int,
) -> dict:
    supabase = get_supabase()
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
    res = q.order("updated_at", desc=True).range(offset, offset + size - 1).execute()
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
