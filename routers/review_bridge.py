"""TAI Review Queue Runtime Bridge v1.0.0
Phase 5: Operational Authority → Runtime Governance.

금지: reviewer bypass, hidden approval, auto approval,
      silent rejection, duplicate review, legacy mutation
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import logging

router = APIRouter(prefix="/bridge", tags=["검토 브릿지"])
logger = logging.getLogger("review_bridge")


def _audit(action: str, entity: str, entity_id: str, user_id: str = "system"):
    logger.info(f"REVIEW_BRIDGE_AUDIT | action={action} entity={entity} id={entity_id} by={user_id}")


def _sb():
    from db.supabase_client import get_supabase
    return get_supabase()


# ═══ Review Queue ═══

@router.get("/review-queue")
def bridge_review_queue(
    review_domain: Optional[str] = Query(None),
    review_status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """검토 대기 목록"""
    sb = _sb()
    q = sb.table("runtime_review_decision").select("*")
    if review_domain:
        q = q.eq("review_domain", review_domain)
    if review_status:
        q = q.eq("review_status", review_status)
    offset = (page - 1) * page_size
    q = q.order("created_at", desc=True).range(offset, offset + page_size - 1)
    r = q.execute()
    return {"status": "success", "source": "runtime", "data": r.data or [], "page": page}


@router.get("/review-queue/{decision_id}")
def bridge_get_review(decision_id: str):
    """검토 단건 조회"""
    sb = _sb()
    r = sb.table("runtime_review_decision").select("*").eq("id", decision_id).execute()
    if not r.data:
        raise HTTPException(404, "Review decision not found")
    return {"status": "success", "source": "runtime", "data": r.data[0]}


# ═══ Review Decisions ═══

@router.post("/review-decisions")
def bridge_create_review(
    review_domain: str = Query(...),
    source_entity_id: str = Query(...),
    reviewer_id: str = Query(...),
    review_action: str = Query(...),
    review_reason: Optional[str] = Query(None),
):
    """검토 결정 생성. authority 검증 트리거 적용."""
    valid_actions = ['APPROVE', 'REJECT', 'RETURN_FOR_EDIT', 'ESCALATE', 'REOPEN']
    if review_action not in valid_actions:
        raise HTTPException(400, f"Invalid action. Must be: {valid_actions}")
    if review_action == 'REJECT' and not review_reason:
        raise HTTPException(400, "REJECT requires review_reason")

    sb = _sb()
    row = {
        "review_domain": review_domain,
        "source_entity_id": source_entity_id,
        "reviewer_id": reviewer_id,
        "review_action": review_action,
        "review_reason": review_reason,
        "review_started_at": "now()",
        "source_trace": "MANUAL_REVIEW",
    }
    try:
        r = sb.table("runtime_review_decision").insert(row).execute()
    except Exception as e:
        raise HTTPException(400, str(e))

    _audit(f"REVIEW_{review_action}", "review_decision", r.data[0]["id"], reviewer_id)
    return {"status": "success", "source": "runtime", "data": r.data[0]}


# ═══ Shortcuts: Approve / Reject / Reopen ═══

@router.post("/approve")
def bridge_approve(
    review_domain: str = Query(...),
    source_entity_id: str = Query(...),
    reviewer_id: str = Query(...),
    review_reason: Optional[str] = Query(None),
):
    """승인 실행"""
    return bridge_create_review(
        review_domain=review_domain,
        source_entity_id=source_entity_id,
        reviewer_id=reviewer_id,
        review_action='APPROVE',
        review_reason=review_reason,
    )


@router.post("/reject")
def bridge_reject(
    review_domain: str = Query(...),
    source_entity_id: str = Query(...),
    reviewer_id: str = Query(...),
    review_reason: str = Query(...),
):
    """반려 실행. reason 필수."""
    return bridge_create_review(
        review_domain=review_domain,
        source_entity_id=source_entity_id,
        reviewer_id=reviewer_id,
        review_action='REJECT',
        review_reason=review_reason,
    )


@router.post("/reopen")
def bridge_reopen(
    review_domain: str = Query(...),
    source_entity_id: str = Query(...),
    reviewer_id: str = Query(...),
    review_reason: str = Query(...),
):
    """재오픈"""
    return bridge_create_review(
        review_domain=review_domain,
        source_entity_id=source_entity_id,
        reviewer_id=reviewer_id,
        review_action='REOPEN',
        review_reason=review_reason,
    )


# ═══ Review Authority ═══

@router.get("/review-authority")
def bridge_list_authority(
    review_domain: Optional[str] = Query(None),
):
    """검토 권한 목록"""
    sb = _sb()
    q = sb.table("runtime_review_authority").select("*")
    if review_domain:
        q = q.eq("review_domain", review_domain)
    q = q.eq("authority_status", "ACTIVE").order("approval_level").limit(50)
    r = q.execute()
    return {"status": "success", "source": "runtime", "data": r.data or []}


# ═══ Review Escalations ═══

@router.get("/review-escalations")
def bridge_list_review_escalations(
    escalation_status: Optional[str] = Query(None),
):
    """검토 에스컬레이션 목록"""
    sb = _sb()
    q = sb.table("runtime_review_escalation").select(
        "*, runtime_review_decision(review_domain, review_action)"
    )
    if escalation_status:
        q = q.eq("escalation_status", escalation_status)
    q = q.order("created_at", desc=True).limit(50)
    r = q.execute()
    return {"status": "success", "source": "runtime", "data": r.data or []}


# ═══ Status ═══

@router.get("/review-status")
def bridge_review_status():
    return {
        "status": "active",
        "phase": "Phase 5 — Runtime Review Governance",
        "bridge_routes": [
            "/bridge/review-queue",
            "/bridge/review-queue/{id}",
            "/bridge/review-decisions",
            "/bridge/review-authority",
            "/bridge/review-escalations",
            "/bridge/approve",
            "/bridge/reject",
            "/bridge/reopen",
        ],
    }
