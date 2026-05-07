"""
Canonical business/API sector codes (2026-05-07).

- API 및 저장 sector 필드: INDUSTRIAL (구 INDUSTRY), SPECIAL_FACILITY (구 SPECIAL)
- 플랜/가격 코드의 INDUSTRY_* , facility_type_code 등은 별도 도메인이므로 변경하지 않음.
"""
from __future__ import annotations

from typing import FrozenSet, Tuple

from services.legal_rules import normalize_sector_db

VALID_SECTORS: FrozenSet[str] = frozenset(
    {"BUILDING", "INDUSTRIAL", "CONSTRUCTION", "SPECIAL_FACILITY"}
)


def sector_codes_for_query(sector: str) -> Tuple[str, ...]:
    """조회 시 레거시 행까지 포함할 코드 목록 (DB 마이그레이션 전후 호환)."""
    u = normalize_sector_db(sector)
    if u == "INDUSTRIAL":
        return ("INDUSTRIAL", "INDUSTRY")
    if u == "SPECIAL_FACILITY":
        return ("SPECIAL_FACILITY", "SPECIAL")
    if not u:
        return tuple()
    return (u,)
