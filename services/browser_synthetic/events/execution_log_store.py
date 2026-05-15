"""Execution Log Store - Synthetic 실행 결과 저장.

역할: browser_synthetic_execution_log CRUD.
"""
from __future__ import annotations

import logging
from uuid import UUID

from db.supabase_client import get_supabase
from services.browser_synthetic.schemas import ExecutionLogCreate

logger = logging.getLogger(__name__)


async def create_execution_log(entry: ExecutionLogCreate) -> dict:
    """Synthetic 실행 로그 생성."""
    sb = get_supabase()
    row = {
        "check_code": entry.check_code,
        "execution_status": entry.execution_status,
        "started_at": entry.started_at.isoformat(),
        "payload": entry.payload,
    }
    if entry.workflow_id:
        row["workflow_id"] = str(entry.workflow_id)
    if entry.trace_id:
        row["trace_id"] = entry.trace_id
    if entry.completed_at:
        row["completed_at"] = entry.completed_at.isoformat()
    if entry.duration_ms is not None:
        row["duration_ms"] = entry.duration_ms
    if entry.error_message:
        row["error_message"] = entry.error_message
    if entry.screenshot_url:
        row["screenshot_url"] = entry.screenshot_url
    if entry.artifact_url:
        row["artifact_url"] = entry.artifact_url

    resp = sb.table("browser_synthetic_execution_log").insert(row).execute()
    logger.info(
        "Synthetic execution logged: check=%s status=%s dur=%sms",
        entry.check_code, entry.execution_status, entry.duration_ms,
    )
    return resp.data[0] if resp.data else {}


async def get_executions_by_trace(trace_id: str) -> list[dict]:
    """trace_id로 실행 로그 조회."""
    sb = get_supabase()
    resp = (
        sb.table("browser_synthetic_execution_log")
        .select("*")
        .eq("trace_id", trace_id)
        .order("started_at", desc=True)
        .execute()
    )
    return resp.data or []


async def get_executions_by_check(
    check_code: str, limit: int = 50
) -> list[dict]:
    """check_code별 최근 실행 로그 조회."""
    sb = get_supabase()
    resp = (
        sb.table("browser_synthetic_execution_log")
        .select("*")
        .eq("check_code", check_code)
        .order("started_at", desc=True)
        .limit(limit)
        .execute()
    )
    return resp.data or []


async def get_recent_executions(limit: int = 100) -> list[dict]:
    """최근 실행 로그 조회."""
    sb = get_supabase()
    resp = (
        sb.table("browser_synthetic_execution_log")
        .select("*")
        .order("started_at", desc=True)
        .limit(limit)
        .execute()
    )
    return resp.data or []
