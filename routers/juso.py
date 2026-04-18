# routers/juso.py — v2.2.0
# v2.2.0 (2026-04-18): SSL verify=False 추가 (Fly.io Tokyo→juso.go.kr 타임아웃 해결)
#                       /search 엔드포인트 배열 반환으로 변경 (FE 복수 결과 드롭다운 대응)
# v2.1.0 (2026-04-14): 환경변수명 JUSO_CONFIRM_KEY → JUSO_API_KEY
# v2.0.0 (2026-04-14): 카카오 로컬 API 제거 → 행정안전부 도로명주소 API 교체
#
# 환경변수:
#   JUSO_API_KEY — 행정안전부 도로명주소 개발자센터 승인키
#
# 엔드포인트:
#   GET /juso/search?query=주소  → { success, data: [{...}, ...], count: N }  ← 배열 반환
#   GET /juso/coord?query=주소   → { success, data: {...} }                   ← 단일 반환

from __future__ import annotations
import os
import logging
import httpx
from fastapi import APIRouter, Query, HTTPException

log    = logging.getLogger(__name__)
router = APIRouter(prefix="/juso", tags=["주소·좌표"])

JUSO_KEY = os.environ.get("JUSO_API_KEY", "")
JUSO_URL = "https://www.juso.go.kr/addrlink/addrLinkApi.do"


def _parse_juso_item(item: dict, query: str = "") -> dict:
    """juso API 결과 1건을 정규화된 dict로 변환."""
    road_address = item.get("roadAddr", "") or item.get("roadAddrPart1", "")
    address      = item.get("jibunAddr", "") or road_address

    def _coord(val) -> float:
        try:
            f = float(val)
            return f if f != 0.0 else 0.0
        except (TypeError, ValueError):
            return 0.0

    return {
        "query":         query,
        "road_address":  road_address,
        "address":       address,
        "lat":           _coord(item.get("entY")),
        "lng":           _coord(item.get("entX")),
        "zip_code":      item.get("zipNo", ""),
        "building_name": item.get("bdNm", ""),
        "sido":          item.get("siNm", ""),
        "sigungu":       item.get("sggNm", ""),
        "raw":           item,
    }


async def _call_juso_api(query: str, count: int = 5) -> list[dict]:
    """
    행정안전부 도로명주소 API 호출 → 결과 목록 반환.
    verify=False: Fly.io Tokyo에서 juso.go.kr SSL 인증서 체인 검증 실패 방지.
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
        "countPerPage": count,
    }

    async with httpx.AsyncClient(timeout=10, verify=False) as client:
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
    return [_parse_juso_item(item, query) for item in juso_list]


@router.get("/search")
async def search_address(
    query: str = Query(..., description="검색할 주소"),
    count: int = Query(5, ge=1, le=20, description="결과 수"),
):
    """주소 검색 → 후보 목록 반환 (배열). FE 드롭다운 대응."""
    items = await _call_juso_api(query, count)
    return {"success": True, "data": items, "count": len(items)}


@router.get("/coord")
async def get_coord(
    query: str = Query(..., description="검색할 주소 (예: 서울시 강남구 테헤란로)"),
):
    """주소 → 좌표 + 정규화 주소 반환 (첫 번째 결과 단일 객체)."""
    items = await _call_juso_api(query, 1)
    if not items:
        raise HTTPException(status_code=404, detail=f"주소를 찾을 수 없습니다: {query}")
    return {"success": True, "data": items[0]}
