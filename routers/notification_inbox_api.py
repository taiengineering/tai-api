"""Notification Inbox API Router — v1.0.0
prefix: /notification-inbox

Unified Feed Surface. Communication Surface만 담당.
Incident/Alert/Severity/Workflow mutation 금지.

API:
  GET   /notification-inbox/feed                   Unified Feed
  GET   /notification-inbox/unread-count            Unread 건수
  POST  /notification-inbox/{id}/read               Read 상태
  POST  /notification-inbox/{id}/unread             Unread 복구
  GET   /notification-inbox/timeline/{trace_id}     Feed Timeline
"""

import logging
from fastapi import APIRouter, Query
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/notification-inbox", tags=["알림인박스"])


@router.get("/feed")
def get_feed(
    user_id: Optional[str] = Query(None),
    source_type: Optional[str] = Query(None, description="trigger_group: OVERDUE, NOTIFICATION_ENGINE, etc"),
    unread_only: bool = Query(False),
    severity: Optional[str] = Query(None, description="priority: INFO, HIGH, CRITICAL"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    try:
        from services.notification_engine.feed_query import get_feed as _get_feed
        offset = (page - 1) * size
        result = _get_feed(
            user_id=user_id, source_type=source_type,
            unread_only=unread_only, severity=severity,
            limit=size, offset=offset,
        )
        return {"status": "success", "page": page, "size": size, "data": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/unread-count")
def unread_count(user_id: Optional[str] = Query(None)):
    try:
        from services.notification_engine.feed_query import get_unread_count
        count = get_unread_count(user_id=user_id)
        return {"status": "success", "data": {"unread_count": count}}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/{notification_id}/read")
def mark_as_read(notification_id: str):
    try:
        from services.notification_engine.feed_query import mark_read
        ok = mark_read(notification_id)
        return {"status": "success" if ok else "error", "notification_id": notification_id, "action": "READ"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/{notification_id}/unread")
def mark_as_unread(notification_id: str):
    try:
        from services.notification_engine.feed_query import mark_unread
        ok = mark_unread(notification_id)
        return {"status": "success" if ok else "error", "notification_id": notification_id, "action": "UNREAD"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/timeline/{trace_id}")
def feed_timeline(trace_id: str):
    try:
        from services.notification_engine.feed_query import get_feed_timeline
        result = get_feed_timeline(trace_id)
        if result is None:
            return {"status": "error", "message": "Timeline not found"}
        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}
