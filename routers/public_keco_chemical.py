"""Public KECO chemical read router.

GET /public/keco/chemicals/by-cas/{cas_no}

No auth. LEG DB read-only. raw_payload never exposed.
CAS 형식 오류 → 422. LEG_SUPABASE 미설정 → 503.
Results: {cas_no, chemicals: [...]}, 빈 목록은 204 없이 200 반환.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from services.keco_chemical.read import (
    KecoLegUnavailable,
    get_chemicals_by_cas,
    validate_cas,
)

router = APIRouter(prefix="/public/keco", tags=["Public KECO chemical"])


@router.get("/chemicals/by-cas/{cas_no}")
async def public_keco_chemicals_by_cas(cas_no: str):
    """공개 KECO 화학물질 규제정보 조회 (CAS 번호 기준).

    Returns: {cas_no, chemicals: [...]}
    chemicals=[] 는 정상 응답 (CAS가 수집 DB에 없음).
    422: CAS 형식 오류 (N-NN-N 패턴 아님).
    503: LEG DB 미설정.
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
        raise HTTPException(
            status_code=503,
            detail={"code": "KECO_LEG_UNAVAILABLE", "message": str(exc)},
        ) from exc

    return {"cas_no": cas, "chemicals": chemicals}
