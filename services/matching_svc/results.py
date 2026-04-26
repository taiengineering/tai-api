from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from db.supabase_client import get_supabase
from schemas.matching import MatchResultCreateBody, ProposalBody
from services.matching_helpers import now_iso
from .errors import MatchingSvcError

log = logging.getLogger(__name__)


def create_match_result_record(body: MatchResultCreateBody, admin_user_id: str) -> dict:
    supabase = get_supabase()
    n = now_iso()
    dup = (
        supabase.table("matching_results")
        .select("id")
        .eq("request_id", body.request_id)
        .eq("supplier_id", body.supplier_id)
        .execute()
    )
    if dup.data:
        raise MatchingSvcError(409, "이미 매칭된 전문가입니다.")
    res = supabase.table("matching_results").insert({
        "request_id": body.request_id,
        "expert_user_id": body.expert_user_id,
        "supplier_type": body.supplier_type,
        "supplier_id": body.supplier_id,
        "rank_no": body.rank_no,
        "match_score": body.match_score,
        "status": "MATCHED",
        "created_at": n,
    }).execute()
    if not res.data:
        raise MatchingSvcError(500, "매칭 결과 저장 실패")
    result_id = res.data[0]["id"]
    req = (
        supabase.table("matching_requests")
        .select("status, status_history")
        .eq("id", body.request_id)
        .limit(1)
        .execute()
    )
    if req.data and req.data[0]["status"] == "RECEIVED":
        history = req.data[0].get("status_history") or []
        history.append({"status": "MATCHING", "at": n, "by": admin_user_id})
        supabase.table("matching_requests").update({
            "status": "MATCHING",
            "status_history": history,
            "matched_at": n,
            "updated_at": n,
        }).eq("id", body.request_id).execute()
    log.info("[MATCH] 전문가 배정 result_id=%s request=%s", result_id, body.request_id)
    return {"status": "success", "data": {"result_id": result_id, "status": "MATCHED"}}


def notify_expert_for_result(result_id: str) -> dict:
    supabase = get_supabase()
    res = (
        supabase.table("matching_results")
        .select("id, status, expert_user_id, request_id")
        .eq("id", result_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise MatchingSvcError(404, "매칭 결과를 찾을 수 없습니다.")
    result = res.data[0]
    if result["status"] not in ("MATCHED",):
        raise MatchingSvcError(400, "MATCHED 상태인 건만 알림 발송 가능합니다.")
    n = now_iso()
    supabase.table("notifications").insert({
        "user_id": result["expert_user_id"],
        "title": "새 매칭 신청이 도착했습니다",
        "body": "고객의 서비스 신청이 접수되었습니다. 내용을 확인하고 제안서를 작성해 주세요.",
        "type": "MATCHING",
        "ref_id": result["request_id"],
        "is_read": False,
        "created_at": n,
    }).execute()
    supabase.table("matching_results").update({
        "status": "NOTIFIED",
        "notified_at": n,
    }).eq("id", result_id).execute()
    return {"status": "success", "message": "전문가에게 알림이 발송되었습니다."}


def mark_result_viewed(result_id: str, expert_user_id: str) -> dict:
    supabase = get_supabase()
    res = (
        supabase.table("matching_results")
        .select("id, status, expert_user_id, request_id")
        .eq("id", result_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise MatchingSvcError(404, "매칭 결과를 찾을 수 없습니다.")
    result = res.data[0]
    if result["expert_user_id"] != expert_user_id:
        raise MatchingSvcError(403, "권한이 없습니다.")
    n = now_iso()
    update_data: Dict[str, Any] = {"viewed_at": n}
    if result["status"] not in ("PROPOSED", "SELECTED", "REJECTED"):
        update_data["status"] = "VIEWED"
    supabase.table("matching_results").update(update_data).eq("id", result_id).execute()
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
            "result": {**result, **update_data},
            "request": request_res.data[0] if request_res.data else None,
        },
    }


def submit_proposal_for_result(
    result_id: str,
    body: ProposalBody,
    expert_user_id: str,
) -> dict:
    supabase = get_supabase()
    res = (
        supabase.table("matching_results")
        .select("id, status, expert_user_id, request_id")
        .eq("id", result_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise MatchingSvcError(404, "매칭 결과를 찾을 수 없습니다.")
    result = res.data[0]
    if result["expert_user_id"] != expert_user_id:
        raise MatchingSvcError(403, "권한이 없습니다.")
    if result["status"] not in ("MATCHED", "NOTIFIED", "VIEWED"):
        raise MatchingSvcError(
            400,
            f"제안서를 발송할 수 없는 상태입니다: {result['status']}",
        )
    n = now_iso()
    request_id = result["request_id"]
    supabase.table("matching_results").update({
        "proposal_title": body.proposal_title,
        "proposal_content": body.proposal_content,
        "proposal_amount": body.proposal_amount,
        "proposal_period": body.proposal_period,
        "proposal_note": body.proposal_note,
        "status": "PROPOSED",
        "proposed_at": n,
        "sent_at": n,
    }).eq("id", result_id).execute()
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
                "at": n,
                "by": "expert",
                "memo": f"제안서 발송 — result_id={result_id}",
            })
            supabase.table("matching_requests").update({
                "status": "PROPOSED",
                "status_history": history,
                "updated_at": n,
            }).eq("id", request_id).execute()
        client_user_id = req_data.get("user_id")
        if client_user_id:
            supabase.table("notifications").insert({
                "user_id": client_user_id,
                "title": "전문가 제안서가 도착했습니다",
                "body": f"제안금액 {body.proposal_amount:,}원 / {body.proposal_period}개월 제안이 왔습니다.",
                "type": "PROPOSAL",
                "ref_id": request_id,
                "is_read": False,
                "created_at": n,
            }).execute()
    log.info("[PROPOSAL] 제안서 발송 result_id=%s", result_id)
    return {
        "status": "success",
        "data": {
            "result_id": result_id,
            "status": "PROPOSED",
            "proposal_amount": body.proposal_amount,
            "proposal_period": body.proposal_period,
        },
    }


def list_proposals_data(
    request_id: str,
    viewer_role_code: Optional[str],
    viewer_user_id: str,
) -> dict:
    supabase = get_supabase()
    if viewer_role_code != "001":
        req = (
            supabase.table("matching_requests")
            .select("user_id")
            .eq("id", request_id)
            .limit(1)
            .execute()
        )
        if not req.data:
            raise MatchingSvcError(404, "신청을 찾을 수 없습니다.")
        if req.data[0].get("user_id") != viewer_user_id:
            raise MatchingSvcError(403, "권한이 없습니다.")
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
    items = res.data or []
    return {"status": "success", "data": {"items": items, "total": len(items)}}


def select_expert_result(
    result_id: str,
    actor_user_id: str,
    actor_role_code: Optional[str],
) -> dict:
    supabase = get_supabase()
    res = (
        supabase.table("matching_results")
        .select("id, status, request_id, expert_user_id")
        .eq("id", result_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise MatchingSvcError(404, "제안서를 찾을 수 없습니다.")
    result = res.data[0]
    request_id = result["request_id"]
    if result["status"] != "PROPOSED":
        raise MatchingSvcError(400, "PROPOSED 상태인 제안서만 선택할 수 있습니다.")
    req = (
        supabase.table("matching_requests")
        .select("id, status, status_history, user_id")
        .eq("id", request_id)
        .limit(1)
        .execute()
    )
    if not req.data:
        raise MatchingSvcError(404, "신청을 찾을 수 없습니다.")
    req_data = req.data[0]
    if actor_role_code != "001" and req_data.get("user_id") != actor_user_id:
        raise MatchingSvcError(403, "권한이 없습니다.")
    n = now_iso()
    supabase.table("matching_results").update({
        "status": "SELECTED",
        "is_selected": True,
        "selected_at": n,
    }).eq("id", result_id).execute()
    supabase.table("matching_results").update({
        "status": "REJECTED",
        "rejected_at": n,
        "reject_reason": "다른 전문가가 선택되었습니다.",
    }).eq("request_id", request_id).eq("status", "PROPOSED").neq("id", result_id).execute()
    history = req_data.get("status_history") or []
    history.append({
        "status": "SELECTED",
        "at": n,
        "by": actor_user_id,
        "memo": f"전문가 선택 — result_id={result_id}",
    })
    supabase.table("matching_requests").update({
        "status": "SELECTED",
        "status_history": history,
        "selected_at": n,
        "updated_at": n,
    }).eq("id", request_id).execute()
    if result.get("expert_user_id"):
        supabase.table("notifications").insert({
            "user_id": result["expert_user_id"],
            "title": "고객이 제안서를 선택했습니다! 🎉",
            "body": "계약 진행을 위해 확인해 주세요.",
            "type": "SELECTED",
            "ref_id": request_id,
            "is_read": False,
            "created_at": n,
        }).execute()
    log.info("[PROPOSAL SELECT] result_id=%s request=%s", result_id, request_id)
    return {
        "status": "success",
        "data": {
            "result_id": result_id,
            "request_id": request_id,
            "status": "SELECTED",
            "message": "전문가가 선택되었습니다. 계약 진행 단계로 넘어갑니다.",
        },
    }


def my_proposals_list(
    expert_user_id: str,
    status: Optional[str],
    page: int,
    size: int,
) -> dict:
    supabase = get_supabase()
    q = supabase.table("matching_results").select(
        "id, request_id, supplier_type, status, "
        "proposal_title, proposal_amount, proposal_period, "
        "match_score, rank_no, "
        "notified_at, viewed_at, proposed_at, selected_at",
        count="exact",
    ).eq("expert_user_id", expert_user_id)
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
