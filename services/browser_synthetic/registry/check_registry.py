"""Synthetic Check Registry - 시나리오 조회 서비스.

역할: browser_synthetic_check_registry 테이블 읽기 전용.
"""
from __future__ import annotations

import logging

from db.supabase_client import get_supabase

logger = logging.getLogger(__name__)


async def get_enabled_checks(workflow_type: str | None = None) -> list[dict]:
    """활성화된 체크 목록 조회."""
    sb = get_supabase()
    q = (
        sb.table("browser_synthetic_check_registry")
        .select("*")
        .eq("enabled", True)
    )
    if workflow_type:
        q = q.eq("workflow_type", workflow_type)
    resp = q.execute()
    return resp.data or []


async def get_check_by_code(check_code: str) -> dict | None:
    """check_code로 단건 조회."""
    sb = get_supabase()
    resp = (
        sb.table("browser_synthetic_check_registry")
        .select("*")
        .eq("check_code", check_code)
        .maybe_single()
        .execute()
    )
    return resp.data


async def get_all_checks() -> list[dict]:
    """전체 체크 조회 (관리용)."""
    sb = get_supabase()
    resp = (
        sb.table("browser_synthetic_check_registry")
        .select("*")
        .order("workflow_type")
        .order("check_type")
        .execute()
    )
    return resp.data or []
