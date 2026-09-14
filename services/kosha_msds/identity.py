"""chemId is source identity. CAS/name are attributes. Search is not identity."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Callable, Optional

from services.kosha_msds.contract import (
    CHEM_ID_WIDTH,
    CONTENT_ID_PREFIX,
    IDENTITY_HOLD,
    IDENTITY_READY,
    SOURCE_ID,
)
from services.kosha_msds.parse import normalize_optional

UuidFn = Callable[[], uuid.UUID]


def new_content_id(uuid_fn: Optional[UuidFn] = None) -> str:
    fn = uuid_fn or uuid.uuid4
    return f"{CONTENT_ID_PREFIX}{fn()}"


def normalize_chem_id(value: Optional[str]) -> Optional[str]:
    return normalize_optional(value)


def format_numeric_chem_id(n: int) -> str:
    """Zero-padded 6-digit chemId. Leading zeros are identity, not decoration."""
    if type(n) is not int or n < 0 or n > (10**CHEM_ID_WIDTH) - 1:
        raise ValueError("chemId candidate must be int 0..999999")
    return f"{n:0{CHEM_ID_WIDTH}d}"


def identity_status_for_chem_id(chem_id: Optional[str]) -> str:
    if normalize_chem_id(chem_id):
        return IDENTITY_READY
    return IDENTITY_HOLD


@dataclass(frozen=True)
class ListCandidate:
    """A getChemList row. Never auto-selected as identity."""

    chem_id: Optional[str]
    chemical_name_ko: Optional[str]
    cas_no: Optional[str]
    ke_no: Optional[str]
    en_no: Optional[str]
    un_no: Optional[str]
    last_date: Optional[str]
    open_yn: Optional[str]
    kosha_confirm: Optional[str]
    identity_status: str
    identity_reason: Optional[str]
    raw: dict[str, Optional[str]]

    @property
    def source_key(self) -> Optional[str]:
        return self.chem_id


def candidate_from_list_item(item: dict[str, Optional[str]]) -> ListCandidate:
    chem_id = normalize_chem_id(item.get("chemId"))
    status = identity_status_for_chem_id(chem_id)
    reason = None if status == IDENTITY_READY else "missing chemId"
    return ListCandidate(
        chem_id=chem_id,
        chemical_name_ko=normalize_optional(item.get("chemNameKor")),
        cas_no=normalize_optional(item.get("casNo")),
        ke_no=normalize_optional(item.get("keNo")),
        en_no=normalize_optional(item.get("enNo")),
        un_no=normalize_optional(item.get("unNo")),
        last_date=normalize_optional(item.get("lastDate")),
        open_yn=normalize_optional(item.get("openYn")),
        kosha_confirm=normalize_optional(item.get("koshaConfirm")),
        identity_status=status,
        identity_reason=reason,
        raw=dict(item),
    )


def is_chem_content_id(content_id: str) -> bool:
    if not content_id.startswith(CONTENT_ID_PREFIX):
        return False
    try:
        uuid.UUID(content_id[len(CONTENT_ID_PREFIX) :])
    except ValueError:
        return False
    return True


# Import used by tests that check source_id constant wiring.
SOURCE_ID_FROZEN = SOURCE_ID
