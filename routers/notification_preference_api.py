"""Notification Preference API Router — v1.0.0
prefix: /notification-preference

Preference 저장/조회만. Permission 계산 금지.
"""

import logging
from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/notification-preference", tags=["알림선호"])


@router.get("/me")
def get_my_preferences(
    actor_id: str = Query(..., description="user_id"),
    tenant_id: Optional[str] = Query(None),
):
    try:
        from services.notification_engine.preference_service import get_preferences
        data = get_preferences(actor_id=actor_id, tenant_id=tenant_id)
        return {"status": "success", "data": data}
    except Exception as e:
        return {"status": "error", "message": str(e)}


class PreferenceUpdateBody(BaseModel):
    actor_id: str
    source_type: str = "*"
    channel_key: str = "*"
    enabled: Optional[bool] = None
    mute_enabled: Optional[bool] = None
    quiet_hour_enabled: Optional[bool] = None
    quiet_hour_start: Optional[str] = None
    quiet_hour_end: Optional[str] = None
    tenant_id: Optional[str] = None


@router.post("/update")
def update_preference(body: PreferenceUpdateBody):
    try:
        from services.notification_engine.preference_service import upsert_preference
        result = upsert_preference(
            actor_id=body.actor_id,
            source_type=body.source_type,
            channel_key=body.channel_key,
            enabled=body.enabled,
            mute_enabled=body.mute_enabled,
            quiet_hour_enabled=body.quiet_hour_enabled,
            quiet_hour_start=body.quiet_hour_start,
            quiet_hour_end=body.quiet_hour_end,
            tenant_id=body.tenant_id,
        )
        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/reset")
def reset_preferences(actor_id: str = Query(...)):
    try:
        from services.notification_engine.preference_service import reset_preferences as _reset
        _reset(actor_id=actor_id)
        return {"status": "success", "message": f"{actor_id} preferences reset"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
