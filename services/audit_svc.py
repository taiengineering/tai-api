"""관리자 운영 감사로그 (WO-2 AuditHook).

Goal: G-ms4je4z3-33eada
- admin_ops_audit_logs에 운영 위험조작(환불·수동활성화·회원조작·크레딧·삭제)을 불변 기록.
  · 주의: admin_audit_logs는 문서 리뷰 엔진 전용(action CHECK 제한)이므로 사용하지 않는다.
    운영 감사는 별도 테이블 admin_ops_audit_logs(action 자유 어휘)에 남긴다.
- best-effort: 감사 실패가 본 작업(환불 등)을 롤백시키면 안 되므로 예외를 삼키고 로그만 남긴다.
- service_role INSERT (RLS 무관). actor 미상이면 NULL 허용.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from db.supabase_client import get_supabase
from services.payment_helpers import now_iso

log = logging.getLogger(__name__)

_OPS_AUDIT_TABLE = "admin_ops_audit_logs"


def record(
    action: str,
    entity_type: str,
    entity_id: Optional[str] = None,
    actor_id: Optional[str] = None,
    before: Optional[Dict[str, Any]] = None,
    after: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """운영 감사 1건 기록. 실패해도 예외를 던지지 않는다(best-effort).

    Returns: 생성된 audit id 또는 None(실패 시).
    """
    try:
        row: Dict[str, Any] = {
            "action": action,
            "entity_type": entity_type,
            "created_at": now_iso(),
        }
        if entity_id:
            row["entity_id"] = entity_id
        if actor_id:
            row["actor_id"] = actor_id
        if before is not None:
            row["before_data"] = before
        if after is not None:
            row["after_data"] = after

        res = get_supabase().table(_OPS_AUDIT_TABLE).insert(row).execute()
        if res.data:
            return res.data[0]["id"]
        log.warning("[AUDIT] insert returned no data: action=%s entity=%s", action, entity_type)
        return None
    except Exception as e:  # noqa: BLE001
        log.warning("[AUDIT] record failed (best-effort): action=%s entity=%s err=%s", action, entity_type, e)
        return None
