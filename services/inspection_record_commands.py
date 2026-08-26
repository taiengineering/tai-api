"""OBJ-01 INSPECTION RECORD — Command service (STEP-1A).

typed semantic input → fn_apply_inspection_record_command RPC → known error mapping.

금지: MAX(revision) 계산, journal/receipt direct INSERT, base UPDATE.
모든 mutation 은 DB function 에서만 이뤄진다.

actor_type / source 는 서버가 고정한다 (클라이언트 입력 금지).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from services.inspection_record_resolver import (
    InspectionRecordError,
    _extract_data,
)

ACTOR_TYPE = "USER"
SOURCE = "SAFE_ADMIN"

# DB RPC 가 반환하는 known domain error 집합 (HTTP 매핑은 router).
KNOWN_DOMAIN_ERRORS = frozenset({
    "INSPECTION_NOT_FOUND",
    "RESULT_NOT_FOUND",
    "LEGACY_STATUS_UNRESOLVED",
    "RESULT_CODE_UNRESOLVED",
    "JOURNAL_REVISION_GAP",
    "REVISION_CONFLICT",
    "COMMAND_ID_REUSE_CONFLICT",
    "INVALID_CHANGE_FIELD",
    "INVALID_STATUS_TRANSITION",
    "INSPECTION_INACTIVE",
    "RESULT_INACTIVE",
})


def _apply(
    supabase: Any,
    *,
    inspection_id: str,
    expected_revision: int,
    command_id: str,
    event_type: str,
    target_result_id: Optional[str],
    changes: Optional[Dict[str, Any]],
    actor_id: Optional[str],
    reason: Optional[str],
) -> Dict[str, Any]:
    params = {
        "p_inspection_id": str(inspection_id),
        "p_expected_revision": int(expected_revision),
        "p_command_id": str(command_id),
        "p_event_type": event_type,
        "p_target_result_id": (str(target_result_id) if target_result_id else None),
        "p_changes": changes if changes is not None else {},
        "p_actor_type": ACTOR_TYPE,
        "p_actor_id": (str(actor_id) if actor_id else None),
        "p_reason": reason,
        "p_source": SOURCE,
    }
    resp = supabase.rpc("fn_apply_inspection_record_command", params).execute()
    data = _extract_data(resp)
    if not isinstance(data, dict):
        raise InspectionRecordError("COMMAND_MALFORMED_RESPONSE", str(type(data)))
    if data.get("ok") is True:
        return data.get("data") or {}
    raise InspectionRecordError(data.get("error") or "COMMAND_FAILED", data.get("detail") or "")


def correct_inspection(
    supabase: Any, inspection_id: str, *,
    expected_revision: int, command_id: str, changes: Dict[str, Any],
    actor_id: Optional[str], reason: Optional[str] = None,
) -> Dict[str, Any]:
    return _apply(
        supabase, inspection_id=inspection_id, expected_revision=expected_revision,
        command_id=command_id, event_type="INSPECTION_CORRECTION",
        target_result_id=None, changes=changes, actor_id=actor_id, reason=reason,
    )


def correct_result(
    supabase: Any, inspection_id: str, result_id: str, *,
    expected_revision: int, command_id: str, changes: Dict[str, Any],
    actor_id: Optional[str], reason: Optional[str] = None,
) -> Dict[str, Any]:
    return _apply(
        supabase, inspection_id=inspection_id, expected_revision=expected_revision,
        command_id=command_id, event_type="RESULT_CORRECTION",
        target_result_id=result_id, changes=changes, actor_id=actor_id, reason=reason,
    )


def change_status(
    supabase: Any, inspection_id: str, *,
    expected_revision: int, command_id: str, to_status: str,
    actor_id: Optional[str], reason: Optional[str] = None,
) -> Dict[str, Any]:
    return _apply(
        supabase, inspection_id=inspection_id, expected_revision=expected_revision,
        command_id=command_id, event_type="STATUS_CHANGE",
        target_result_id=None, changes={"to_status": to_status}, actor_id=actor_id, reason=reason,
    )


def deactivate_inspection(
    supabase: Any, inspection_id: str, *,
    expected_revision: int, command_id: str,
    actor_id: Optional[str], reason: Optional[str] = None,
) -> Dict[str, Any]:
    return _apply(
        supabase, inspection_id=inspection_id, expected_revision=expected_revision,
        command_id=command_id, event_type="INSPECTION_DEACTIVATION",
        target_result_id=None, changes={}, actor_id=actor_id, reason=reason,
    )


def deactivate_result(
    supabase: Any, inspection_id: str, result_id: str, *,
    expected_revision: int, command_id: str,
    actor_id: Optional[str], reason: Optional[str] = None,
) -> Dict[str, Any]:
    return _apply(
        supabase, inspection_id=inspection_id, expected_revision=expected_revision,
        command_id=command_id, event_type="RESULT_DEACTIVATION",
        target_result_id=result_id, changes={}, actor_id=actor_id, reason=reason,
    )
