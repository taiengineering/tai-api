"""Response Feedback — 운영자 대응 기록 + 결과 평가."""
from __future__ import annotations
import uuid, logging
from datetime import datetime, timezone
from typing import Any
from db.supabase_client import get_supabase
from services.time import now_kst, serialize_external_utc

logger = logging.getLogger(__name__)
TABLE = "operational_response_feedback"

async def record_response_feedback(
    situation_id: str, operator_action: str, outcome: str = "unchanged",
    snapshot_id: str | None = None, environment: str = "production",
) -> dict[str, Any] | None:
    fb = {
        "id": str(uuid.uuid4()),
        "situation_id": situation_id,
        "snapshot_id": snapshot_id,
        "operator_action": operator_action,
        "outcome": outcome,
        "effectiveness": _outcome_to_effectiveness(outcome),
        "learning_notes": _build_learning_notes(outcome, operator_action),
        "recommended_future_response": [],
        "environment": environment,
        "created_at": serialize_external_utc(now_kst()),
    }
    try:
        sb = get_supabase()
        result = sb.table(TABLE).insert(fb).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"record_response_feedback: {e}")
        return None

async def get_feedback_for_situation(situation_id: str, limit: int = 20) -> list[dict]:
    try:
        sb = get_supabase()
        return (sb.table(TABLE).select("*").eq("situation_id", situation_id)
                .order("created_at", desc=True).limit(limit).execute()).data or []
    except Exception as e:
        logger.error(f"get_feedback: {e}"); return []

async def get_recent_feedback(limit: int = 50, environment: str | None = None) -> list[dict]:
    try:
        sb = get_supabase()
        q = sb.table(TABLE).select("*").order("created_at", desc=True).limit(limit)
        if environment: q = q.eq("environment", environment)
        return (q.execute()).data or []
    except Exception as e:
        logger.error(f"get_recent_feedback: {e}"); return []

def _outcome_to_effectiveness(outcome: str) -> float:
    return {"improved": 0.85, "unchanged": 0.40, "worsened": 0.15, "recurring": 0.25}.get(outcome, 0.40)

def _build_learning_notes(outcome: str, action: str) -> list[str]:
    notes = []
    if outcome == "improved": notes.append(f"대응 '{action}'이 효과적이었습니다")
    if outcome == "worsened": notes.append(f"대응 '{action}' 후 상황이 악화되었습니다")
    if outcome == "recurring": notes.append("대응 후 재발이 발생했습니다. 근본 원인 분석이 필요합니다")
    return notes
