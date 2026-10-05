"""Public KECO chemical read router.

GET /public/keco/chemicals/by-cas/{cas_no}

No auth. LEG DB read-only. raw_payload never exposed.
CAS 형식 오류 → 422. LEG_SUPABASE 미설정 또는 DB 오류 → 503.
Results: {cas_no, source_id, provider, source_dataset_url, chemicals: [...]}
빈 목록은 204 없이 200 반환.

503 public response는 고정 메시지만 반환한다.
내부 환경변수명/Supabase 오류 세부사항은 공개 응답에 포함하지 않는다.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from services.keco_chemical.contract import DATASET_URL, PROVIDER, SOURCE_ID
from services.keco_chemical.read import (
    KecoLegUnavailable,
    get_chemicals_by_cas,
    validate_cas,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/public/keco", tags=["Public KECO chemical"])

_503_DETAIL = {
    "code": "KECO_LEG_UNAVAILABLE",
    "message": "KECO reference data is temporarily unavailable",
}


@router.get("/chemicals/by-cas/{cas_no}")
async def public_keco_chemicals_by_cas(cas_no: str):
    """공개 KECO 화학물질 규제정보 조회 (CAS 번호 기준).

    Returns: {cas_no, source_id, provider, source_dataset_url, chemicals: [...]}
    chemicals=[] 는 정상 응답 (CAS가 수집 DB에 없음).
    422: CAS 형식 오류 (N-NN-N 패턴 아님).
    503: LEG DB 미설정 또는 쿼리 실패.
    """
    try:
        cas = validate_cas(cas_no)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"INVALID_CAS_FORMAT: {exc}",
        ) from exc

    try:
        chemicals = get_chemicals_by_cas(cas)
    except KecoLegUnavailable as exc:
        logger.warning("KECO LEG unavailable: %s", exc)
        raise HTTPException(status_code=503, detail=_503_DETAIL) from exc

    return {
        "cas_no": cas,
        "source_id": SOURCE_ID,
        "provider": PROVIDER,
        "source_dataset_url": DATASET_URL,
        "chemicals": chemicals,
    }
