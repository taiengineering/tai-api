"""TAI Notification Runtime Bridge v1.0.0
Phase 4: Runtime Lifecycle Event → Notification Governance.

금지: hidden trigger, duplicate notification, semantic routing,
      guessed recipient, silent escalation, auto approval notification
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import logging

router = APIRouter(prefix="/bridge", tags=["알림 브릿지"])
logger = logging.getLogger("notification_bridge")


def _audit(action: str, entity: str, entity_id: str, user_id: str = "system"):
    logger.info(f"NOTIFICATION_BRIDGE_AUDIT | action={action} entity={entity} id={entity_id} by={user_id}")


def _sb():
    from db.supabase_client import get_supabase
    return get_supabase()


# ═══ Notification Events ═══

@router.get("/notification-events")
def bridge_list_events(
    event_type: Optional[str] = Query(None),
    event_status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """런타임 알림 이벤트 목록"""
    sb = _sb()
    q = sb.table("runtime_notification_event").select("*")
    if event_type:
        q = q.eq("event_type", event_type)
    if event_status:
        q = q.eq("event_status", event_status)
    offset = (page - 1) * page_size
    q = q.order("created_at", desc=True).range(offset, offset + page_size - 1)
    r = q.execute()
    return {"status": "success", "source": "runtime", "data": r.data or [], "page": page}


@router.post("/notification-events")
def bridge_create_event(
    event_type: str = Query(...),
    source_domain: str = Query(...),
    source_entity_id: str = Query(...),
    triggered_by: str = Query(...),
    escalation_required: bool = Query(False),
):
    """런타임 알림 이벤트 생성. semantic/guessed/inferred 금지."""
    valid_types = [
        'WORK_ASSIGNED', 'WORK_DUE_SOON', 'WORK_OVERDUE',
        'REVIEW_PENDING', 'REVIEW_REJECTED', 'REVIEW_APPROVED',
        'DOCUMENT_RENDERED', 'EVIDENCE_MISSING',
        'ESCALATION_REQUIRED', 'SCHEDULE_CREATED',
    ]
    if event_type not in valid_types:
        raise HTTPException(400, f"Invalid event_type. Must be one of: {valid_types}")

    sb = _sb()
    row = {
        "event_type": event_type,
        "source_domain": source_domain,
        "source_entity_id": source_entity_id,
        "triggered_by": triggered_by,
        "escalation_required": escalation_required,
        "source_trace": "RUNTIME_EVENT",
    }
    r = sb.table("runtime_notification_event").insert(row).execute()
    _audit("CREATE_EVENT", "notification_event", r.data[0]["id"], triggered_by)
    return {"status": "success", "source": "runtime", "data": r.data[0]}


# ═══ Notifications ═══

@router.get("/notifications")
def bridge_list_notifications(
    delivery_status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """알림 큐 조회"""
    sb = _sb()
    q = sb.table("runtime_notification_queue").select("*")
    if delivery_status:
        q = q.eq("delivery_status", delivery_status)
    offset = (page - 1) * page_size
    q = q.order("created_at", desc=True).range(offset, offset + page_size - 1)
    r = q.execute()
    return {"status": "success", "source": "runtime", "data": r.data or [], "page": page}


@router.get("/my-notifications")
def bridge_my_notifications(
    user_id: str = Query(...),
    delivery_status: Optional[str] = Query(None),
):
    """작업자/관리자 본인 알림 조회"""
    sb = _sb()
    q = sb.table("runtime_notification_queue").select(
        "*, runtime_notification_event(event_type, source_domain)"
    ).eq("recipient_user_id", user_id)
    if delivery_status:
        q = q.eq("delivery_status", delivery_status)
    q = q.order("created_at", desc=True).limit(50)
    r = q.execute()
    return {"status": "success", "source": "runtime", "data": r.data or []}


@router.post("/acknowledge-notification")
def bridge_acknowledge(
    notification_id: str = Query(...),
    user_id: str = Query(...),
):
    """알림 확인 (acknowledge)"""
    sb = _sb()

    # validation
    notif = sb.table("runtime_notification_queue").select("recipient_user_id, delivery_status").eq("id", notification_id).execute()
    if not notif.data:
        raise HTTPException(404, "Notification not found")
    if notif.data[0]["recipient_user_id"] != user_id:
        raise HTTPException(403, "Not the recipient")
    if notif.data[0]["delivery_status"] == "ACKNOWLEDGED":
        raise HTTPException(400, "Already acknowledged")

    sb.table("runtime_notification_queue").update({
        "delivery_status": "ACKNOWLEDGED",
        "acknowledged_at": "now()",
    }).eq("id", notification_id).execute()

    # audit
    sb.table("runtime_notification_audit").insert({
        "notification_id": notification_id,
        "action": "ACKNOWLEDGED",
        "action_by": user_id,
        "source_trace": "WORKER_ACTION",
    }).execute()

    _audit("ACKNOWLEDGE", "notification", notification_id, user_id)
    return {"status": "success", "acknowledged": True}


# ═══ Escalations ═══

@router.get("/escalations")
def bridge_list_escalations(
    escalation_status: Optional[str] = Query(None),
):
    """에스컬레이션 목록 조회"""
    sb = _sb()
    q = sb.table("runtime_escalation_queue").select("*")
    if escalation_status:
        q = q.eq("escalation_status", escalation_status)
    q = q.order("created_at", desc=True).limit(50)
    r = q.execute()
    return {"status": "success", "source": "runtime", "data": r.data or []}


# ═══ Status ═══

@router.get("/notification-status")
def bridge_notification_status():
    return {
        "status": "active",
        "phase": "Phase 4 — Runtime Notification Governance",
        "bridge_routes": [
            "/bridge/notification-events",
            "/bridge/notifications",
            "/bridge/my-notifications",
            "/bridge/acknowledge-notification",
            "/bridge/escalations",
        ],
        "forbidden_patterns": [
            "hidden_trigger", "duplicate_notification", "semantic_routing",
            "guessed_recipient", "silent_escalation", "auto_approval",
        ],
    }
