# routers/juso.py — v2.1.0
# v2.1.0 (2026-04-14): 환경변수명 JUSO_CONFIRM_KEY → JUSO_API_KEY (Fly.io 기존 secret 재사용)
# v2.0.0 (2026-04-14): 카카오 로컬 API 제거 → 행정안전부 도로명주소 API (juso.go.kr) 교체
# v1.0.0: 카카오 로컬 API 사용 (제거됨)
#
# 환경변수:
#   JUSO_API_KEY — 행정안전부 도로명주소 개발자센터 승인키 (Fly.io에 이미 등록됨)
#
# 엔드포인트 (응답 구조 동일 유지):
#   GET /juso/coord?query=주소   → { success, data: { query, road_address, address, lat, lng } }
#   GET /juso/search?query=주소  → 동일 (alias)
#
# 행안부 API 문서: https://www.juso.go.kr/addrlink/devAddrLinkRequestGuide.do

from __future__ import annotations
import os
import logging
import httpx
from fastapi import APIRouter, Query, HTTPException

log    = logging.getLogger(__name__)
router = APIRouter(prefix="/juso", tags=["주소·좌표"])

JUSO_KEY = os.environ.get("JUSO_API_KEY", "")
JUSO_URL = "https://www.juso.go.kr/addrlink/addrLinkApi.do"


async def _search_juso(query: str) -> dict:
    """
    행정안전부 도로명주소 API 호출 → 첫 번째 결과 반환.

    응답 구조:
      juso[0].roadAddr    → 도로명 주소 (전체)
      juso[0].jibunAddr   → 지번 주소
      juso[0].entX        → 경도(lng) WGS84 — 출입구 좌표
      juso[0].entY        → 위도(lat) WGS84
      juso[0].zipNo       → 우편번호
      juso[0].siNm        → 시도명
      juso[0].sggNm       → 시군구명

    JUSO_API_KEY 미설정 시 503 반환.
    """
    if not JUSO_KEY:
        raise HTTPException(
            status_code=503,
            detail="JUSO_API_KEY 환경변수가 설정되지 않았습니다."
        )

    params = {
        "confmKey":     JUSO_KEY,
        "keyword":      query,
        "resultType":   "json",
        "currentPage":  1,
        "countPerPage": 5,
    }

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(JUSO_URL, params=params)

    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"행안부 주소 API 오류: HTTP {resp.status_code}"
        )

    body    = resp.json()
    results = body.get("results", {})
    common  = results.get("common", {})
    error_code = common.get("errorCode", "0")

    if error_code != "0":
        raise HTTPException(
            status_code=502,
            detail=f"행안부 API 오류코드 {error_code}: {common.get('errorMessage', '')}"
        )

    juso_list = results.get("juso", [])
    if not juso_list:
        raise HTTPException(
            status_code=404,
            detail=f"주소를 찾을 수 없습니다: {query}"
        )

    item = juso_list[0]

    road_address = item.get("roadAddr", "") or item.get("roadAddrPart1", "")
    address      = item.get("jibunAddr", "") or road_address

    def _coord(val) -> float:
        try:
            f = float(val)
            return f if f != 0.0 else 0.0
        except (TypeError, ValueError):
            return 0.0

    lng = _coord(item.get("entX"))
    lat = _coord(item.get("entY"))

    return {
        "query":        query,
        "road_address": road_address,
        "address":      address,
        "lat":          lat,
        "lng":          lng,
        "zip_code":     item.get("zipNo", ""),
        "sido":         item.get("siNm", ""),
        "sigungu":      item.get("sggNm", ""),
        "raw":          item,
    }


@router.get("/coord")
async def get_coord(
    query: str = Query(..., description="검색할 주소 (예: 서울시 강남구 테헤란로)"),
):
    """주소 → 좌표 + 정규화 주소 반환 (행안부 도로명주소 API)."""
    data = await _search_juso(query)
    return {"success": True, "data": data}


@router.get("/search")
async def search_address(
    query: str = Query(..., description="검색할 주소"),
):
    """GET /juso/coord 와 동일한 응답 — alias."""
    data = await _search_juso(query)
    return {"success": True, "data": data}
