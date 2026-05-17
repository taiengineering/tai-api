"""Audience Resolver Foundation.

audience_key → actor list resolve.

Phase 1: Mock + passthrough 기반.
Phase 2: Identity Core 연동.

역할: 누구에게 전달할지 결정. Permission 판단 금지.
"""

import logging
from typing import List, Dict, Any, Optional
from db.supabase_client import get_supabase

logger = logging.getLogger("notification_engine.audience_resolver")

# 표준 Audience 유형
AUDIENCE_TYPES = {
    "operator": "운영자 (안전관리자)",
    "tenant_admin": "테넌트 관리자 (회사 대표)",
    "safety_manager": "안전관리자",
    "company_admin": "회사 관리자",
    "worker": "작업자",
    "inspector": "점검자",
    "site_all": "현장 전체",
    "system_admin": "시스템 관리자",
    "platform_admin": "플랫폼 관리자",
}


async def resolve_audience(
    audience_key: str,
    tenant_id: Optional[str] = None,
    factory_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """audience_key로 대상 actor 목록 반환.

    Phase 1: 간단 DB 조회 + fallback.
    Phase 2: Identity Core 연동.

    Args:
        audience_key: operator / tenant_admin / worker 등
        tenant_id: 회사 ID (optional)
        factory_id: 시설 ID (optional)

    Returns:
        [{actor_id, name, phone, email, role_code, audience_key}]
    """
    try:
        # system_admin / platform_admin: 고정 대상
        if audience_key in ("system_admin", "platform_admin"):
            return _resolve_system_admin()

        # tenant 기반 조회
        if tenant_id:
            return await _resolve_by_tenant(audience_key, tenant_id, factory_id)

        # fallback: audience_key만 반환 (passthrough)
        logger.info("Audience passthrough: %s (no tenant_id)", audience_key)
        return [{
            "actor_id": None,
            "audience_key": audience_key,
            "name": AUDIENCE_TYPES.get(audience_key, audience_key),
            "resolved": False,
        }]

    except Exception as e:
        logger.error("Audience resolve failed: %s %s", audience_key, e)
        return []


def _resolve_system_admin() -> List[Dict[str, Any]]:
    """system_admin: role_code='001' 사용자."""
    try:
        sb = get_supabase()
        resp = (
            sb.table("users")
            .select("id, name, phone, email, role_code")
            .eq("role_code", "001")
            .execute()
        )
        return [
            {
                "actor_id": u["id"],
                "name": u.get("name"),
                "phone": u.get("phone"),
                "email": u.get("email"),
                "role_code": u.get("role_code"),
                "audience_key": "system_admin",
                "resolved": True,
            }
            for u in (resp.data or [])
        ]
    except Exception as e:
        logger.error("system_admin resolve failed: %s", e)
        return []


async def _resolve_by_tenant(
    audience_key: str, tenant_id: str, factory_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """tenant 기반 audience resolve."""
    try:
        sb = get_supabase()

        # role_code 매핑
        role_map = {
            "operator": ["002", "003"],       # 안전관리자, 관리책임자
            "tenant_admin": ["003"],           # 관리책임자
            "safety_manager": ["002"],         # 안전관리자
            "company_admin": ["003"],          # 관리책임자
            "worker": ["004", "005"],          # 작업자, 근로자
            "inspector": ["002", "006"],       # 안전관리자, 점검원
            "site_all": ["002", "003", "004", "005", "006"],
        }

        roles = role_map.get(audience_key, ["002"])

        q = (
            sb.table("users")
            .select("id, name, phone, email, role_code, company_id")
            .eq("company_id", tenant_id)
            .in_("role_code", roles)
        )

        resp = q.execute()
        return [
            {
                "actor_id": u["id"],
                "name": u.get("name"),
                "phone": u.get("phone"),
                "email": u.get("email"),
                "role_code": u.get("role_code"),
                "audience_key": audience_key,
                "resolved": True,
            }
            for u in (resp.data or [])
        ]
    except Exception as e:
        logger.error("tenant audience resolve failed: %s %s %s", audience_key, tenant_id, e)
        return []


async def list_audience_types() -> Dict[str, str]:
    """표준 Audience 유형 목록."""
    return AUDIENCE_TYPES
