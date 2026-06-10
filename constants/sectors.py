"""
Canonical business/API sector codes.

sector 표준의 단일 정의처(single source of truth).
표준값의 '원천'은 DB 테이블 public.sector_standard 이며, 이 모듈은 그 값을
읽어 와 VALID_SECTORS 등으로 노출한다(=DB화). DB 조회 실패 시에는 아래
_FALLBACK_SECTORS(현재 표준 4종)로 폴백하여 서비스가 멈추지 않게 한다
(구멍 없는 동작 보장).

- API 및 저장 sector 필드: INDUSTRIAL (구 INDUSTRY), SPECIAL_FACILITY (구 SPECIAL)
- 플랜/가격 코드의 INDUSTRY_* , facility_type_code 등은 별도 도메인이므로 변경하지 않음.

sector 값을 다루는 모든 모듈(진단 입구 필터, 검증 하니스 등)은 여기의 함수를
인용해야 한다. 각 모듈이 자기만의 변환 상수를 두지 말 것 — 표준이 분산되면
한 곳을 고쳐도 다른 곳이 따라오지 않아 깨진다.

표준값을 바꿔야 하면 코드가 아니라 DB(sector_standard)를 수정한다.
"""
from __future__ import annotations

import logging
from typing import Dict, FrozenSet, List, Tuple

from services.legal_rules import normalize_sector_db

log = logging.getLogger(__name__)

# DB 조회 실패 시 폴백. DB(sector_standard)의 현재 내용과 동일하게 유지.
# 이름·타입(frozenset)은 기존 import 호환을 위해 그대로 둔다.
_FALLBACK_SECTORS: FrozenSet[str] = frozenset(
    {"BUILDING", "INDUSTRIAL", "CONSTRUCTION", "SPECIAL_FACILITY"}
)
# 폴백 legacy 별칭 (sector_standard.legacy_codes와 동일)
_FALLBACK_LEGACY: Dict[str, Tuple[str, ...]] = {
    "INDUSTRIAL": ("INDUSTRIAL", "INDUSTRY"),
    "SPECIAL_FACILITY": ("SPECIAL_FACILITY", "SPECIAL"),
}


def _load_sector_standard_from_db() -> Tuple[FrozenSet[str], Dict[str, Tuple[str, ...]]]:
    """sector_standard 테이블에서 표준 sector와 legacy 별칭을 읽는다.

    Returns: (active_sector_codes, {sector_code: (code, *legacy_codes)})
    실패 시 (_FALLBACK_SECTORS, _FALLBACK_LEGACY) 폴백.
    """
    try:
        from db.supabase_client import get_supabase

        supabase = get_supabase()
        res = (
            supabase.table("sector_standard")
            .select("sector_code, legacy_codes, is_active")
            .eq("is_active", True)
            .execute()
        )
        rows = res.data or []
        if not rows:
            log.warning("sector_standard 비어있음 → 폴백 사용")
            return _FALLBACK_SECTORS, _FALLBACK_LEGACY
        codes = set()
        legacy: Dict[str, Tuple[str, ...]] = {}
        for r in rows:
            code = (r.get("sector_code") or "").strip().upper()
            if not code:
                continue
            codes.add(code)
            legacy_list = [str(x).strip().upper() for x in (r.get("legacy_codes") or []) if x]
            if legacy_list:
                legacy[code] = tuple([code] + legacy_list)
        if not codes:
            return _FALLBACK_SECTORS, _FALLBACK_LEGACY
        return frozenset(codes), legacy
    except Exception as exc:  # DB 장애 등 → 폴백
        log.warning("sector_standard 조회 실패 → 폴백 사용: %s", exc)
        return _FALLBACK_SECTORS, _FALLBACK_LEGACY


# 모듈 로드 시 1회 적재(원천=DB, 실패 시 폴백).
VALID_SECTORS, _LEGACY_CODES = _load_sector_standard_from_db()


def reload_sector_standard() -> FrozenSet[str]:
    """런타임에 sector_standard를 다시 읽어 VALID_SECTORS를 갱신한다.

    DB에서 표준을 수정한 뒤 재배포 없이 반영하고 싶을 때 호출.
    """
    global VALID_SECTORS, _LEGACY_CODES
    VALID_SECTORS, _LEGACY_CODES = _load_sector_standard_from_db()
    return VALID_SECTORS


def sector_codes_for_query(sector: str) -> Tuple[str, ...]:
    """조회 시 레거시 행까지 포함할 코드 목록 (DB 마이그레이션 전후 호환).

    legacy 별칭의 원천도 DB(sector_standard.legacy_codes)이며, 적재 실패 시
    _FALLBACK_LEGACY를 사용한다.
    """
    u = normalize_sector_db(sector)
    if not u:
        return tuple()
    legacy = _LEGACY_CODES.get(u)
    if legacy:
        return legacy
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
