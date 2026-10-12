"""Public chemical enrichment read router.

GET /public/chemical-enrichment/by-cas/{cas_no}

두 원천(EXT-037 화학물질 안전정보, EXT-132 위험물 정보)을 CAS 번호로 조회.
No auth. TAI DB read-only.
CAS 형식 오류 → 422.
DB 미설정 또는 쿼리 실패 → 각 원천별 UNAVAILABLE 상태 반환 (부분 실패 허용).
기존 KECO API, MSDS API 미변경.

503 응답 없음 — 한 원천 실패 시 나머지 결과는 정상 반환한다.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from services.ext037_chemical_safety.contract import (
    DISPLAY_NAME as EXT037_DISPLAY_NAME,
    SOURCE_ID as EXT037_SOURCE_ID,
)
from services.ext037_chemical_safety.read import (
    Ext037Unavailable,
    get_chemical_safety_by_cas,
)
from services.ext132_hazardous_material.contract import (
    DISPLAY_NAME as EXT132_DISPLAY_NAME,
    SOURCE_ID as EXT132_SOURCE_ID,
)
from services.ext132_hazardous_material.read import (
    Ext132Unavailable,
    get_hazardous_material_by_cas,
)
from services.keco_chemical.read import validate_cas

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/public/chemical-enrichment",
    tags=["Public chemical enrichment"],
)

_STATUS_AVAILABLE = "AVAILABLE"
_STATUS_UNAVAILABLE = "UNAVAILABLE"
_STATUS_NO_SNAPSHOT = "NO_CURRENT_SNAPSHOT"


@router.get("/by-cas/{cas_no}")
async def public_chemical_enrichment_by_cas(cas_no: str):
    """EXT-037·132 화학물질 부가정보 조회 (CAS 번호 기준).

    Returns:
      {
        "cas_no": "67-64-1",
        "chemical_safety": {"source_id": ..., "status": ..., "items": [...]},
        "hazardous_material": {"source_id": ..., "status": ..., "items": [...]},
      }
    items=[] 는 정상 응답 (CAS가 수집 DB에 없음).
    422: CAS 형식 오류.
    한 원천 실패 시 status=UNAVAILABLE 반환, 나머지 정상 반환.
    """
    try:
        cas = validate_cas(cas_no)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"INVALID_CAS_FORMAT: {exc}",
        ) from exc

    chemical_safety = _query_ext037(cas)
    hazardous_material = _query_ext132(cas)

    return {
        "cas_no": cas,
        "chemical_safety": chemical_safety,
        "hazardous_material": hazardous_material,
    }


def _query_ext037(cas: str) -> dict:
    try:
        items = get_chemical_safety_by_cas(cas)
        if items is None:
            return _source_block(EXT037_SOURCE_ID, EXT037_DISPLAY_NAME, _STATUS_NO_SNAPSHOT, [])
        return _source_block(EXT037_SOURCE_ID, EXT037_DISPLAY_NAME, _STATUS_AVAILABLE, items)
    except Ext037Unavailable as exc:
        logger.warning("EXT-037 unavailable for CAS %s: %s", cas, exc)
        return _source_block(EXT037_SOURCE_ID, EXT037_DISPLAY_NAME, _STATUS_UNAVAILABLE, [])


def _query_ext132(cas: str) -> dict:
    try:
        items = get_hazardous_material_by_cas(cas)
        if items is None:
            return _source_block(EXT132_SOURCE_ID, EXT132_DISPLAY_NAME, _STATUS_NO_SNAPSHOT, [])
        return _source_block(EXT132_SOURCE_ID, EXT132_DISPLAY_NAME, _STATUS_AVAILABLE, items)
    except Ext132Unavailable as exc:
        logger.warning("EXT-132 unavailable for CAS %s: %s", cas, exc)
        return _source_block(EXT132_SOURCE_ID, EXT132_DISPLAY_NAME, _STATUS_UNAVAILABLE, [])


def _source_block(source_id: str, display_name: str, status: str, items: list) -> dict:
    return {
        "source_id": source_id,
        "display_name": display_name,
        "status": status,
        "items": items,
    }
