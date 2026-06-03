"""Phase 9 — obligation_quality / admin_obligation_queue persistence (service layer).

Writes the evaluator output to Supabase and, on CORRECTION_REQUIRED, ensures an
admin queue entry exists. Supabase access is lazy (imported inside functions) so
importing this module never fails at router-load time.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from services.obligation_quality_evaluator import (
    CORRECTION_REQUIRED,
    evaluate_batch,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_evaluation(
    obligation_id: str,
    quality_status: str,
    quality_reason: Optional[str] = None,
    check_report_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Upsert one obligation_quality row (current status per obligation_id).
    On CORRECTION_REQUIRED, ensure an OPEN admin_obligation_queue entry.
    """
    from db.supabase_client import get_supabase
    sb = get_supabase()

    row = {
        "obligation_id": obligation_id,
        "quality_status": quality_status,
        "quality_reason": quality_reason,
        "check_report_id": check_report_id,
        "updated_at": _now(),
    }
    sb.table("obligation_quality").upsert(row, on_conflict="obligation_id").execute()

    queued = False
    if quality_status == CORRECTION_REQUIRED:
        queued = _ensure_queue_entry(sb, obligation_id, quality_reason)
    return {"obligation_id": obligation_id, "quality_status": quality_status, "queued": queued}


def record_batch(
    obligations: List[dict],
    reports_by_obligation: Optional[Dict[str, dict]] = None,
) -> List[Dict[str, Any]]:
    """Evaluate + persist a batch. Skips entries without a resolvable obligation_id."""
    results = evaluate_batch(obligations, reports_by_obligation)
    recorded: List[Dict[str, Any]] = []
    for r in results:
        oid = r.get("obligation_id")
        if not oid:
            continue
        recorded.append(
            record_evaluation(oid, r["quality_status"], r.get("quality_reason"), r.get("check_report_id"))
        )
    return recorded


def _ensure_queue_entry(sb, obligation_id: str, reason: Optional[str]) -> bool:
    """Insert an OPEN queue row only if no unresolved (OPEN/IN_PROGRESS) row exists."""
    existing = (
        sb.table("admin_obligation_queue")
        .select("id")
        .eq("obligation_id", obligation_id)
        .in_("status", ["OPEN", "IN_PROGRESS"])
        .limit(1)
        .execute()
    )
    if existing.data:
        return False
    sb.table("admin_obligation_queue").insert({
        "obligation_id": obligation_id,
        "reason": reason,
        "status": "OPEN",
        "created_at": _now(),
    }).execute()
    return True
