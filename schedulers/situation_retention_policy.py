"""Situation Retention Policy — Scheduler DIRECT handler.

매일 03:00 실행. 오래된 snapshot/feedback/closure 정리 상태 보고.
"""
from __future__ import annotations
import logging
from typing import Any

logger = logging.getLogger(__name__)

async def handler() -> dict[str, Any]:
    try:
        from watch_engine.trans_engine.retention.snapshot_retention import cleanup_old_snapshots
        from watch_engine.trans_engine.retention.feedback_retention import cleanup_old_feedback
        from watch_engine.trans_engine.retention.closure_retention import cleanup_old_closures

        results = [
            await cleanup_old_snapshots(),
            await cleanup_old_feedback(),
            await cleanup_old_closures(),
        ]
        return {"status": "success", "retention_report": results}
    except Exception as e:
        logger.error(f"retention handler: {e}")
        return {"status": "error", "message": str(e)}
