"""OBJ-01 INSPECTION RECORD — Command API (STEP-1A, additive dormant).

canonical runtime:
    authenticated caller
    → ownership/scope guard (_ensure_inspection_own, 기존 재사용)
    → command service
    → fn_apply_inspection_record_command RPC (revision-guarded, idempotent)

invariant:
    - AUTH BEFORE COMMAND: get_current_user → ownership guard → service (순서 고정).
    - actor_type/actor_id/source 는 body 에서 받지 않고 서버가 고정한다.
    - result 소유(result_id belongs to inspection_id) 검증은 DB RPC 내부에서 한다.
    - 내부 detail(UUID/DB message)을 public response 로 노출하지 않는다.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from routers.inspection_checklist import _ensure_inspection_own
from schemas.inspection_record import (
    DeactivationRequest,
    HeaderCorrectionRequest,
    ResultCorrectionRequest,
    StatusChangeRequest,
)
from services import inspection_record_commands as cmd
from services.inspection_record_resolver import InspectionRecordError

router = APIRouter(prefix="/inspection", tags=["점검 레코드 Command"])

_STATUS_404 = frozenset({"INSPECTION_NOT_FOUND", "RESULT_NOT_FOUND"})
_STATUS_409 = frozenset({
    "REVISION_CONFLICT",
    "COMMAND_ID_REUSE_CONFLICT",
    "INVALID_STATUS_TRANSITION",
    "INSPECTION_INACTIVE",
    "RESULT_INACTIVE",
    "LEGACY_STATUS_UNRESOLVED",
    "RESULT_CODE_UNRESOLVED",
    "JOURNAL_REVISION_GAP",
})
_STATUS_400 = frozenset({"INVALID_CHANGE_FIELD"})


def _raise_http(exc: InspectionRecordError):
    code = exc.code
    if code in _STATUS_404:
        status = 404
    elif code in _STATUS_409:
        status = 409
    elif code in _STATUS_400:
        status = 400
    else:
        status = 500  # unexpected/malformed — code 만 전달, DB detail 비노출
    raise HTTPException(status_code=status, detail={"code": code})


@router.post("/{inspection_id}/corrections")
async def correct_inspection_ep(
    inspection_id: str,
    body: HeaderCorrectionRequest,
    current: dict = Depends(get_current_user),
):
    sb = get_supabase()
    _ensure_inspection_own(sb, inspection_id, current)
    try:
        data = cmd.correct_inspection(
            sb, inspection_id,
            expected_revision=body.expected_revision,
            command_id=str(body.command_id),
            changes=body.changes.model_dump(exclude_unset=True, mode="json"),
            actor_id=current.get("id"),
            reason=body.reason,
        )
        return {"ok": True, "data": data}
    except InspectionRecordError as exc:
        _raise_http(exc)


@router.post("/{inspection_id}/results/{result_id}/corrections")
async def correct_result_ep(
    inspection_id: str,
    result_id: str,
    body: ResultCorrectionRequest,
    current: dict = Depends(get_current_user),
):
    sb = get_supabase()
    _ensure_inspection_own(sb, inspection_id, current)
    try:
        data = cmd.correct_result(
            sb, inspection_id, result_id,
            expected_revision=body.expected_revision,
            command_id=str(body.command_id),
            changes=body.changes.model_dump(exclude_unset=True, mode="json"),
            actor_id=current.get("id"),
            reason=body.reason,
        )
        return {"ok": True, "data": data}
    except InspectionRecordError as exc:
        _raise_http(exc)


@router.post("/{inspection_id}/status-changes")
async def change_status_ep(
    inspection_id: str,
    body: StatusChangeRequest,
    current: dict = Depends(get_current_user),
):
    sb = get_supabase()
    _ensure_inspection_own(sb, inspection_id, current)
    try:
        data = cmd.change_status(
            sb, inspection_id,
            expected_revision=body.expected_revision,
            command_id=str(body.command_id),
            to_status=body.to_status,
            actor_id=current.get("id"),
            reason=body.reason,
        )
        return {"ok": True, "data": data}
    except InspectionRecordError as exc:
        _raise_http(exc)


@router.post("/{inspection_id}/deactivations")
async def deactivate_inspection_ep(
    inspection_id: str,
    body: DeactivationRequest,
    current: dict = Depends(get_current_user),
):
    sb = get_supabase()
    _ensure_inspection_own(sb, inspection_id, current)
    try:
        data = cmd.deactivate_inspection(
            sb, inspection_id,
            expected_revision=body.expected_revision,
            command_id=str(body.command_id),
            actor_id=current.get("id"),
            reason=body.reason,
        )
        return {"ok": True, "data": data}
    except InspectionRecordError as exc:
        _raise_http(exc)


@router.post("/{inspection_id}/results/{result_id}/deactivations")
async def deactivate_result_ep(
    inspection_id: str,
    result_id: str,
    body: DeactivationRequest,
    current: dict = Depends(get_current_user),
):
    sb = get_supabase()
    _ensure_inspection_own(sb, inspection_id, current)
    try:
        data = cmd.deactivate_result(
            sb, inspection_id, result_id,
            expected_revision=body.expected_revision,
            command_id=str(body.command_id),
            actor_id=current.get("id"),
            reason=body.reason,
        )
        return {"ok": True, "data": data}
    except InspectionRecordError as exc:
        _raise_http(exc)
