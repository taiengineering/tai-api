"""Integrity Rule Registry - 규칙 조회 서비스.

역할: workflow_integrity_rule_registry 테이블 읽기 전용.
상태 변경 금지.
"""
from __future__ import annotations

import logging
from uuid import UUID

from db.supabase_client import get_supabase

logger = logging.getLogger(__name__)


async def get_enabled_rules(workflow_type: str) -> list[dict]:
    """활성화된 규칙 목록 조회."""
    sb = get_supabase()
    resp = (
        sb.table("workflow_integrity_rule_registry")
        .select("*")
        .eq("workflow_type", workflow_type)
        .eq("enabled", True)
        .execute()
    )
    return resp.data or []


async def get_rules_by_type(
    workflow_type: str, rule_type: str
) -> list[dict]:
    """특정 rule_type의 활성 규칙 조회."""
    sb = get_supabase()
    resp = (
        sb.table("workflow_integrity_rule_registry")
        .select("*")
        .eq("workflow_type", workflow_type)
        .eq("rule_type", rule_type)
        .eq("enabled", True)
        .execute()
    )
    return resp.data or []


async def get_rule_by_code(rule_code: str) -> dict | None:
    """rule_code로 단건 조회."""
    sb = get_supabase()
    resp = (
        sb.table("workflow_integrity_rule_registry")
        .select("*")
        .eq("rule_code", rule_code)
        .maybe_single()
        .execute()
    )
    return resp.data


async def get_all_rules() -> list[dict]:
    """전체 규칙 조회 (관리용)."""
    sb = get_supabase()
    resp = (
        sb.table("workflow_integrity_rule_registry")
        .select("*")
        .order("workflow_type")
        .order("rule_type")
        .execute()
    )
    return resp.data or []
