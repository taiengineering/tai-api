"""
Canonical business/API sector codes (2026-05-07).

- API 및 저장 sector 필드: INDUSTRIAL (구 INDUSTRY), SPECIAL_FACILITY (구 SPECIAL)
- 플랜/가격 코드의 INDUSTRY_* , facility_type_code 등은 별도 도메인이므로 변경하지 않음.

sector 표준의 단일 정의처(single source of truth).
sector 값을 다루는 모든 모듈(진단 입구 필터, 검증 하니스 등)은 여기의 함수를
인용해야 한다. 각 모듈이 자기만의 변환 상수를 두지 말 것 — 표준이 분산되면
한 곳을 고쳐도 다른 곳이 따라오지 않아 깨진다.
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


def to_mapping_sector(sector: str) -> str:
    """sector 값을 law_sector_mapping.sectors 표준 키로 환원(단일 표준).

    엔진 내부 표준(MANUFACTURING)·레거시(INDUSTRY, SPECIAL)를 모두
    표준값(INDUSTRIAL / SPECIAL_FACILITY / BUILDING / CONSTRUCTION)으로 정규화한다.
    내부적으로 normalize_sector_db(표준 변환 원천)를 사용한다.

    진단 입구 sector 필터와 검증 하니스는 둘 다 이 함수를 인용하여 동일 기준으로
    law_sector_mapping과 대조한다. 모듈별 별도 변환 상수를 두지 말 것.
    """
    return normalize_sector_db(sector or "")
