# routers/juso.py — v1.0.0
# 주소 검색 + 좌표 변환 (카카오 로컬 API)
#
# 환경변수:
#   KAKAO_REST_API_KEY — 카카오 개발자센터 REST API 키
#
# 엔드포인트:
#   GET /juso/coord?query=주소   → { success, data: { query, road_address, address, lat, lng } }
#   GET /juso/search?query=주소  → 동일 (alias)

from __future__ import annotations
import os
import logging
import httpx
from fastapi import APIRouter, Query, HTTPException

log    = logging.getLogger(__name__)
router = APIRouter(prefix="/juso", tags=["주소·좌표"])

KAKAO_KEY = os.environ.get("KAKAO_REST_API_KEY", "")
KAKAO_URL = "https://dapi.kakao.com/v2/local/search/address.json"


async def _search_kakao(query: str) -> dict:
    """
    카카오 로컬 API 호출 → 첫 번째 결과 반환.
    응답 구조:
      road_address.address_name  → 도로명 주소
      address.address_name       → 지번 주소
      x                          → 경도(lng)
      y                          → 위도(lat)
    """
    if not KAKAO_KEY:
        raise HTTPException(
            status_code=503,
            detail="KAKAO_REST_API_KEY 환경변수가 설정되지 않았습니다."
        )

    headers = {"Authorization": f"KakaoAK {KAKAO_KEY}"}
    params  = {"query": query, "size": 1}

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(KAKAO_URL, headers=headers, params=params)

    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"카카오 API 오류: HTTP {resp.status_code}"
        )

    body = resp.json()
    docs = body.get("documents", [])
    if not docs:
        raise HTTPException(
            status_code=404,
            detail=f"주소를 찾을 수 없습니다: {query}"
        )

    doc = docs[0]

    # 도로명 주소
    road_addr = doc.get("road_address")
    road_address_name = (
        road_addr.get("address_name", "") if road_addr else ""
    )

    # 지번 주소
    jibun_addr = doc.get("address")
    address_name = (
        jibun_addr.get("address_name", "") if jibun_addr else ""
    )

    # 좌표
    lng = float(doc.get("x", 0))
    lat = float(doc.get("y", 0))

    return {
        "query":        query,
        "road_address": road_address_name or address_name,
        "address":      address_name or road_address_name,
        "lat":          lat,
        "lng":          lng,
        "raw":          doc,   # 원본 필드 전체 (프론트 디버깅용)
    }


@router.get("/coord")
async def get_coord(
    query: str = Query(..., description="검색할 주소 (예: 서울시 강남구 테헤란로)"),
):
    """
    주소 → 좌표 + 정규화 주소 반환.

    응답:
    ```json
    {
      "success": true,
      "data": {
        "query": "서울시 강남구 테헤란로",
        "road_address": "서울 강남구 테헤란로",
        "address": "서울 강남구 역삼동 735",
        "lat": 37.5013,
        "lng": 127.0397
      }
    }
    ```
    """
    data = await _search_kakao(query)
    return {"success": True, "data": data}


@router.get("/search")
async def search_address(
    query: str = Query(..., description="검색할 주소"),
):
    """GET /juso/coord 와 동일한 응답 — alias."""
    data = await _search_kakao(query)
    return {"success": True, "data": data}
