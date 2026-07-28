"""소프트 삭제(휴지통) 서비스 (WO-5 SoftDelete).

Goal: G-ms4je4z3-33eada
- deleted_at 마킹으로 삭제/복구 (물리 DELETE 절대 없음).
- 화이트리스트 테이블만 허용 (임의 테이블 조작·오조작 차단).
- soft_delete/restore는 audit(DATA_SOFT_DELETE/DATA_RESTORE) 기록.
- is_active(정지/재개)와 별개: deleted_at IS NULL=정상, NOT NULL=휴지통.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from db.supabase_client import get_supabase
from services import audit_svc
from services.payment_helpers import now_iso

log = logging.getLogger(__name__)

# 소프트삭제 허용 테이블 (임의 테이블 조작 차단)
_ALLOWED = {"companies", "factories", "users", "company_contacts"}

# audit entity_type 매핑
_ENTITY = {
    "companies": "company",
    "factories": "factory",
    "users": "user",
    "company_contacts": "company_contact",
}


class SoftDeleteError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _check_table(table: str) -> None:
    if table not in _ALLOWED:
        raise SoftDeleteError(400, f"소프트삭제가 허용되지 않은 테이블입니다: {table}")


def _load_row(table: str, row_id: str) -> Dict[str, Any]:
    res = get_supabase().table(table).select("id, deleted_at").eq("id", row_id).limit(1).execute()
    if not res.data:
        raise SoftDeleteError(404, "대상을 찾을 수 없습니다.")
    return res.data[0]


def soft_delete(table: str, row_id: str, deleted_by: Optional[str] = None,
                reason: Optional[str] = None) -> Dict[str, Any]:
    """deleted_at=now() 마킹. 이미 삭제된 건은 409."""
    _check_table(table)
    row = _load_row(table, row_id)
    if row.get("deleted_at"):
        raise SoftDeleteError(409, "이미 삭제(휴지통)된 항목입니다.")

    ts = now_iso()
    get_supabase().table(table).update({"deleted_at": ts}).eq("id", row_id).execute()
    audit_svc.record(
        "DATA_SOFT_DELETE", _ENTITY.get(table, table), entity_id=row_id, actor_id=deleted_by,
        before={"deleted_at": None},
        after={"deleted_at": ts, "table": table, "reason": reason},
    )
    return {"ok": True, "deleted_at": ts}


def restore(table: str, row_id: str, restored_by: Optional[str] = None) -> Dict[str, Any]:
    """deleted_at=NULL 복구. 삭제되지 않은 건은 409."""
    _check_table(table)
    row = _load_row(table, row_id)
    if not row.get("deleted_at"):
        raise SoftDeleteError(409, "휴지통에 있지 않은 항목입니다.")

    get_supabase().table(table).update({"deleted_at": None}).eq("id", row_id).execute()
    audit_svc.record(
        "DATA_RESTORE", _ENTITY.get(table, table), entity_id=row_id, actor_id=restored_by,
        before={"deleted_at": row.get("deleted_at")},
        after={"deleted_at": None, "table": table},
    )
    return {"ok": True}


def list_trash(table: str, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    """휴지통(deleted_at NOT NULL) 목록."""
    _check_table(table)
    res = (
        get_supabase().table(table)
        .select("*")
        .not_.is_("deleted_at", "null")
        .order("deleted_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )
    return res.data or []
