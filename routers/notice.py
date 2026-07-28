"""통합 공지 배너 라우터 (WO-16 NoticeBanner).

Goal: G-ms4je4z3-33eada
- 어드민 CRUD + 채널별 공개 조회(marketing·safe가 호출).
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from services.notice_svc import (
    NoticeError, active_for_channel, create, delete, list_admin, toggle, update,
)

router = APIRouter(prefix="/notices", tags=["공지배너"])


class NoticeBody(BaseModel):
    title: str
    body: Optional[str] = None
    channels: Optional[List[str]] = None
    banner_type: Optional[str] = "INFO"
    link_url: Optional[str] = None
    link_label: Optional[str] = None
    starts_at: Optional[str] = None
    ends_at: Optional[str] = None
    priority: Optional[int] = 0
    enabled: Optional[bool] = True
    created_by: Optional[str] = None


class NoticePatch(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    channels: Optional[List[str]] = None
    banner_type: Optional[str] = None
    link_url: Optional[str] = None
    link_label: Optional[str] = None
    starts_at: Optional[str] = None
    ends_at: Optional[str] = None
    priority: Optional[int] = None
    enabled: Optional[bool] = None


# ── 공개(marketing·safe 호출) ──────────────────────────────
@router.get("/active")
def get_active(channel: str = Query(..., description="MARKETING | SAFE")):
    """채널 현재 노출 공지."""
    try:
        items = active_for_channel(channel)
    except NoticeError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    return {"status": "success", "data": items}


# ── 어드민 ────────────────────────────────────────────────
@router.get("")
def list_notices(channel: Optional[str] = Query(None), enabled: Optional[bool] = Query(None)):
    return {"status": "success", "data": list_admin(channel=channel, enabled=enabled)}


@router.post("")
def create_notice(body: NoticeBody):
    try:
        row = create(body.model_dump())
    except NoticeError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    return {"status": "success", "data": row}


@router.patch("/{notice_id}")
def update_notice(notice_id: str, body: NoticePatch):
    try:
        row = update(notice_id, body.model_dump())
    except NoticeError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    return {"status": "success", "data": row}


@router.patch("/{notice_id}/toggle")
def toggle_notice(notice_id: str, enabled: bool = Query(...)):
    try:
        row = toggle(notice_id, enabled)
    except NoticeError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    return {"status": "success", "data": row}


@router.delete("/{notice_id}")
def delete_notice(notice_id: str):
    delete(notice_id)
    return {"status": "success"}
