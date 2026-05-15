"""Workflow Integrity API Router.

Endpoints:
- GET  /workflow/integrity/{workflow_id}  → Integrity Timeline
- POST /workflow/integrity/{workflow_id}/evaluate → 평가 실행
- GET  /workflow/integrity/rules → 전체 규칙 조회
- GET  /workflow/integrity/events/{workflow_id} → 이벤트 조회
- PATCH /workflow/integrity/events/{event_id}/resolve → 이벤트 해결
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from services.workflow_integrity.evaluator.integrity_evaluator import (
    evaluate_workflow,
)
from services.workflow_integrity.timeline.integrity_timeline import (
    get_integrity_timeline,
)
from services.workflow_integrity.registry.rule_registry import get_all_rules
from services.workflow_integrity.events.integrity_event_store import (
    get_events_by_workflow,
    get_unresolved_events,
    resolve_event,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/workflow/integrity", tags=["workflow-integrity"])


@router.get("/{workflow_id}")
async def api_integrity_timeline(workflow_id: UUID):
    """Integrity Timeline 조회.

    반환: integrity events + triggered rules + timeline correlation.
    """
    try:
        result = await get_integrity_timeline(workflow_id)
        return {"ok": True, "data": result}
    except Exception as e:
        logger.error("Integrity timeline error: %s", e)
        raise HTTPException(500, detail=str(e))


@router.post("/{workflow_id}/evaluate")
async def api_evaluate_workflow(
    workflow_id: UUID,
    workflow_type: str = Query("COMMON"),
    persist: bool = Query(True),
):
    """Workflow Integrity 평가 실행."""
    try:
        report = await evaluate_workflow(
            workflow_id=workflow_id,
            workflow_type=workflow_type,
            persist_events=persist,
        )
        return {
            "ok": True,
            "data": report.model_dump(mode="json"),
        }
    except Exception as e:
        logger.error("Integrity evaluation error: %s", e)
        raise HTTPException(500, detail=str(e))


@router.get("/rules/list")
async def api_list_rules():
    """전체 Integrity 규칙 조회."""
    try:
        rules = await get_all_rules()
        return {"ok": True, "data": rules}
    except Exception as e:
        logger.error("Rules list error: %s", e)
        raise HTTPException(500, detail=str(e))


@router.get("/events/{workflow_id}")
async def api_get_events(
    workflow_id: UUID,
    unresolved_only: bool = Query(False),
):
    """특정 workflow의 Integrity 이벤트 조회."""
    try:
        if unresolved_only:
            events = await get_unresolved_events(workflow_id)
        else:
            events = await get_events_by_workflow(workflow_id)
        return {"ok": True, "data": events}
    except Exception as e:
        logger.error("Events fetch error: %s", e)
        raise HTTPException(500, detail=str(e))


@router.patch("/events/{event_id}/resolve")
async def api_resolve_event(event_id: UUID):
    """Integrity 이벤트 해결 처리."""
    try:
        result = await resolve_event(event_id)
        if not result:
            raise HTTPException(404, detail="Event not found")
        return {"ok": True, "data": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Event resolve error: %s", e)
        raise HTTPException(500, detail=str(e))
