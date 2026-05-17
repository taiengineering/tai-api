"""Digest Runtime Service.

event → digest policy lookup → digest queue append.

Phase 1: Shadow mode — queue 저장만, 실제 묶음 발송 금지.

역할: 전달 밀도 조절. 이벤트 의미 변경 금지.
"""

import logging
from typing import Optional, Dict, Any, List
from db.supabase_client import get_supabase

logger = logging.getLogger("notification_engine.digest_runtime")


async def lookup_digest_policy(
    source_type: Optional[str] = None,
    event_type: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Digest 정책 조회. source_type 또는 event_type 매치."""
    try:
        sb = get_supabase()
        q = sb.table("notification_digest_policy_registry").select("*").eq("enabled", True)

        if event_type:
            resp = q.eq("event_type", event_type).execute()
            if resp.data:
                return resp.data[0]

        if source_type:
            resp2 = (
                sb.table("notification_digest_policy_registry")
                .select("*")
                .eq("enabled", True)
                .eq("source_type", source_type)
                .execute()
            )
            if resp2.data:
                return resp2.data[0]

        return None
    except Exception as e:
        logger.error("Digest policy lookup failed: %s", e)
        return None


async def append_digest_candidate(
    digest_policy_key: str,
    grouped_key: str,
    trace_id: Optional[str] = None,
    event_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Digest queue에 후보 저장."""
    try:
        sb = get_supabase()
        row = {
            "digest_policy_key": digest_policy_key,
            "grouped_key": grouped_key,
            "digest_status": "PENDING",
        }
        if trace_id:
            row["trace_id"] = trace_id
        if event_id:
            row["event_id"] = event_id

        resp = sb.table("runtime_notification_digest_queue").insert(row).execute()
        if resp.data:
            logger.info(
                "[DIGEST] candidate appended: policy=%s key=%s",
                digest_policy_key,
                grouped_key,
            )
            return resp.data[0]
        return None
    except Exception as e:
        logger.error("Digest candidate append failed: %s", e)
        return None


async def check_and_append(
    source_type: Optional[str] = None,
    event_type: Optional[str] = None,
    trace_id: Optional[str] = None,
    event_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Digest 정책 확인 후 queue append. Shadow mode."""
    policy = await lookup_digest_policy(source_type=source_type, event_type=event_type)

    if not policy:
        return {"digest": False, "reason": "no_matching_policy"}

    # grouping key 계산
    gk_field = policy.get("grouping_key", "source_type")
    grouped_key = (metadata or {}).get(gk_field) or source_type or event_type or "unknown"

    result = await append_digest_candidate(
        digest_policy_key=policy["digest_policy_key"],
        grouped_key=grouped_key,
        trace_id=trace_id,
        event_id=event_id,
    )

    return {
        "digest": True,
        "digest_policy_key": policy["digest_policy_key"],
        "grouped_key": grouped_key,
        "shadow_mode": True,
        "queued": result is not None,
    }


async def list_digest_policies(enabled_only: bool = True) -> List[Dict[str, Any]]:
    """Digest 정책 목록."""
    try:
        sb = get_supabase()
        q = sb.table("notification_digest_policy_registry").select("*")
        if enabled_only:
            q = q.eq("enabled", True)
        resp = q.order("digest_policy_key").execute()
        return resp.data or []
    except Exception as e:
        logger.error("List digest policies failed: %s", e)
        return []


async def list_digest_candidates(
    status: str = "PENDING",
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Digest queue 후보 목록."""
    try:
        sb = get_supabase()
        resp = (
            sb.table("runtime_notification_digest_queue")
            .select("*")
            .eq("digest_status", status)
            .order("queued_at", desc=True)
            .limit(limit)
            .execute()
        )
        return resp.data or []
    except Exception as e:
        logger.error("List digest candidates failed: %s", e)
        return []
