"""OBJ-01 INSPECTION RECORD — command request schemas (STEP-1A).

공통 metadata: expected_revision(>=0), command_id(UUID), reason(optional).
actor_type / actor_id / source 는 클라이언트 입력을 받지 않는다(서버 파생).

exclude_unset 의미 보존: 필드 미제공 ≠ 명시적 null.
라우터는 changes 를 model_dump(exclude_unset=True, mode='json') 로 직렬화해야 한다.
"""
from __future__ import annotations

from typing import Any, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class CommandMeta(BaseModel):
    """모든 command 공통 입력. actor/source 는 받지 않는다."""

    expected_revision: int = Field(..., ge=0)
    command_id: UUID
    reason: Optional[str] = None


class HeaderCorrectionChanges(BaseModel):
    inspection_date: Optional[str] = None
    inspector_id: Optional[UUID] = None


class HeaderCorrectionRequest(CommandMeta):
    changes: HeaderCorrectionChanges

    @model_validator(mode="after")
    def _require_one(self) -> "HeaderCorrectionRequest":
        if not self.changes.model_dump(exclude_unset=True):
            raise ValueError("changes must provide at least one field")
        return self


class ResultCorrectionChanges(BaseModel):
    result_code: Optional[str] = None
    value_text: Optional[str] = None
    value_number: Optional[float] = None
    note: Optional[str] = None
    checked_at: Optional[str] = None
    photo_url: Optional[str] = None
    photo_urls: Optional[List[Any]] = None
    item_name: Optional[str] = None  # server enforces: only for set_item-less rows


class ResultCorrectionRequest(CommandMeta):
    changes: ResultCorrectionChanges

    @model_validator(mode="after")
    def _require_one(self) -> "ResultCorrectionRequest":
        if not self.changes.model_dump(exclude_unset=True):
            raise ValueError("changes must provide at least one field")
        return self


class StatusChangeRequest(CommandMeta):
    # STEP-1A: only IN_PROGRESS -> COMPLETED is permitted (enforced in DB RPC).
    to_status: str


class DeactivationRequest(CommandMeta):
    """inspection / result 비활성 — 공통 metadata만."""

    pass
