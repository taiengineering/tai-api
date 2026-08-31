# routers/watch_engine_alert_api.py — Alert 설정/이력 API
"""
Alert Rule CRUD + History + Mute/Snooze.
Founder Cockpit UI에서 제어 가능.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel
from services.time import now_kst, serialize_external_utc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/watch-engine/alert", tags=["알림설정"])


def _sb():
    from db.supabase_client import get_supabase
    return get_supabase()


# ═══ Alert Rule CRUD ═══

@router.get("/rules")
def list_alert_rules():
    try:
        resp = _sb().table("alert_rule_registry").select("*").order("rule_key").execute()
        return {"status": "success", "data": resp.data or []}
    except Exception as e:
        return {"status": "error", "message": str(e)}


class RuleUpdate(BaseModel):
    enabled: Optional[bool] = None
    threshold_count: Optional[int] = None
    threshold_minutes: Optional[int] = None
    cooldown_minutes: Optional[int] = None
    notify_channel: Optional[str] = None
    severity: Optional[str] = None
    description: Optional[str] = None


@router.patch("/rules/{rule_key}")
def update_alert_rule(rule_key: str, body: RuleUpdate):
    try:
        update = {k: v for k, v in body.dict().items() if v is not None}
        update["updated_at"] = serialize_external_utc(now_kst())
        _sb().table("alert_rule_registry").update(update).eq("rule_key", rule_key).execute()
        return {"status": "success", "message": f"{rule_key} 수정 완료"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Mute / Snooze ═══

class MuteBody(BaseModel):
    minutes: int = 60


@router.post("/rules/{rule_key}/mute")
def mute_rule(rule_key: str, body: MuteBody):
    try:
        muted_until = (now_kst() + timedelta(minutes=body.minutes)).isoformat()
        _sb().table("alert_rule_registry").update({
            "muted_until": muted_until,
            "updated_at": serialize_external_utc(now_kst()),
        }).eq("rule_key", rule_key).execute()
        return {"status": "success", "message": f"{rule_key} {body.minutes}분 무음 처리"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/rules/{rule_key}/unmute")
def unmute_rule(rule_key: str):
    try:
        _sb().table("alert_rule_registry").update({
            "muted_until": None,
            "updated_at": serialize_external_utc(now_kst()),
        }).eq("rule_key", rule_key).execute()
        return {"status": "success", "message": f"{rule_key} 무음 해제"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Alert History ═══

@router.get("/history")
def get_alert_history(limit: int = 20):
    try:
        resp = _sb().table("alert_history").select("*") \
            .order("sent_at", desc=True).limit(limit).execute()
        return {"status": "success", "data": resp.data or []}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Manual Send (test) ═══

@router.post("/test")
def test_alert():
    """Telegram 발송 테스트."""
    try:
        from watch_engine.alert.engine import _send_telegram
        ok, err = _send_telegram("\U0001f6a8 [TEST] Watch Engine Alert \ud14c\uc2a4\ud2b8\n\uc815\uc0c1 \uc218\uc2e0\ub418\uba74 Telegram \uc5f0\ub3d9 \uc644\ub8cc.")
        return {"status": "success" if ok else "error", "telegram_ok": ok, "error": err}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Manual Evaluate ═══

@router.post("/evaluate")
def run_alert_evaluation():
    try:
        from watch_engine.alert.engine import evaluate_and_alert
        result = evaluate_and_alert()
        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}
