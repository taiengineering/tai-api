"""OBJ-01 KNOT-3A — SAFE lifecycle status writer bridge.

SAFE 의 점검 lifecycle 완료를 base UPDATE 가 아니라 STATUS_CHANGE journal append 로
전환하기 위한 orchestration helper. 이 모듈은 오직 Resolver + 기존 change_status
command service 만 사용한다.

절대 금지 (이 모듈에서 직접 수행하지 않음):
    safety_inspections UPDATE
    journal INSERT / receipt INSERT
    MAX(revision) 계산

멱등성: 최종 유효 상태(effective state)로 보장한다. 이미 COMPLETED 면 command RPC 를
호출하지 않고 success no-op 이다. REVISION_CONFLICT 는 단 1회 re-resolve 로만 수렴을
시도하며(retry loop 금지), re-resolve 결과가 COMPLETED 면 concurrent completion 으로
인정해 성공 처리한다.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from services.inspection_record_commands import change_status
from services.inspection_record_resolver import (
    InspectionRecordError,
    resolve_inspection_record,
)


class InspectionStatusWriteError(Exception):
    """writer bridge domain 예외. code 보유. HTTP 매핑은 router 책임(409)."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def complete_inspection_status(
    supabase: Any,
    inspection_id: str,
    *,
    actor_id: Optional[str],
    reason: str,
) -> Dict[str, Any]:
    """inspection lifecycle 를 COMPLETED 로 전표화(STATUS_CHANGE)한다. 멱등.

    Returns:
        {"status": "COMPLETED", "changed": bool, "noop": bool,
         "revision": <int|None>, "command_id": <str|None>}
        - changed True  : STATUS_CHANGE 전표 1건 append 됨 (IN_PROGRESS -> COMPLETED)
        - changed False : 이미 COMPLETED (또는 concurrent completion) -> journal append 0

    Raises:
        InspectionStatusWriteError: 결정적 도메인 오류(code 보유).
    """
    # 1) 현재 유효 레코드
    try:
        record = resolve_inspection_record(inspection_id, supabase)
    except InspectionRecordError as e:
        raise InspectionStatusWriteError(e.code, e.detail)

    # 2) inactive -> INSPECTION_INACTIVE
    if record.get("is_active") is not True:
        raise InspectionStatusWriteError("INSPECTION_INACTIVE", str(inspection_id))

    status = record.get("inspection_status")

    # 3) already COMPLETED -> success no-op (journal append 0)
    if status == "COMPLETED":
        return {
            "status": "COMPLETED",
            "changed": False,
            "noop": True,
            "revision": record.get("revision"),
            "command_id": None,
        }

    # 4) not IN_PROGRESS -> INVALID_STATUS_TRANSITION
    if status != "IN_PROGRESS":
        raise InspectionStatusWriteError("INVALID_STATUS_TRANSITION", f"{status} -> COMPLETED")

    # 5) current revision (MAX(revision) 계산 금지 — resolver 가 준 값을 그대로 사용)
    current_revision = record.get("revision")
    if not isinstance(current_revision, int) or isinstance(current_revision, bool):
        raise InspectionStatusWriteError("SOURCE_INTEGRITY_ERROR", f"revision {current_revision!r}")

    # 6) server-generated command id (endpoint 멱등성의 근거는 effective state 이며,
    #    command_id 는 DB command 계층의 재사용 방지 키다)
    command_id = str(uuid.uuid4())

    # 7) STATUS_CHANGE command
    try:
        result = change_status(
            supabase,
            inspection_id,
            expected_revision=current_revision,
            command_id=command_id,
            to_status="COMPLETED",
            actor_id=actor_id,
            reason=reason,
        )
    except InspectionRecordError as e:
        # 8) REVISION_CONFLICT -> re-resolve 단 1회 (retry loop 금지)
        if e.code == "REVISION_CONFLICT":
            try:
                rec2 = resolve_inspection_record(inspection_id, supabase)
            except InspectionRecordError as e2:
                raise InspectionStatusWriteError(e2.code, e2.detail)
            if rec2.get("inspection_status") == "COMPLETED":
                # concurrent completion 으로 인정 -> success no-op
                return {
                    "status": "COMPLETED",
                    "changed": False,
                    "noop": True,
                    "revision": rec2.get("revision"),
                    "command_id": None,
                }
            # 그 외 -> 원래 REVISION_CONFLICT 전파
            raise InspectionStatusWriteError("REVISION_CONFLICT", e.detail)
        raise InspectionStatusWriteError(e.code, e.detail)

    return {
        "status": "COMPLETED",
        "changed": True,
        "noop": False,
        "revision": (result.get("revision") if isinstance(result, dict) else None),
        "command_id": command_id,
    }
