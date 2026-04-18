# routers/juso.py — v2.0.1
# 주소 검색 + 좌표 변환 (행정안전부 도로명주소 API)
# 카카오 API 완전 제거 (2026-04-14)
#
# 환경변수:
#   JUSO_API_KEY — 행정안전부 도로명주소 API 승인키
#     신청: https://business.juso.go.kr/addrlink/openApi/apiReqst.do
#
# 엔드포인트:
#   GET /juso/search?query=주소           → 주소 목록 (최대 10건)
#   GET /juso/coord?query=주소            → 첫 번째 결과 + 좌표
#   GET /juso/coord?admCd=&rnMgtSn=&udrtYn=&buldMnnm=&buldSlno= → 좌표만

from __future__ import annotations
import os
import logging
import httpx
from fastapi import APIRouter, Query, HTTPException
from typing import Optional

log    = logging.getLogger(__name__)
router = APIRouter(prefix="/juso", tags=["주소·좌표"])

JUSO_KEY = os.environ.get("JUSO_API_KEY", "")
JUSO_SEARCH_URL = "https://business.juso.go.kr/addrlink/addrLinkApi.do"
JUSO_COORD_URL  = "https://business.juso.go.kr/addrlink/addrCoordApi.do"


async def _search_juso(query: str, count: int = 10) -> list[dict]:
    """
    행안부 도로명주소 API 호출 → 주소 목록 반환.
    """
    if not JUSO_KEY:
        raise HTTPException(
            status_code=503,
            detail="JUSO_API_KEY 환경변수가 설정되지 않았습니다."
        )

    params = {
        "confmKey":   JUSO_KEY,
        "keyword":    query,
        "resultType": "json",
        "countPerPage": str(count),
        "currentPage": "1",
    }

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(JUSO_SEARCH_URL, params=params)

    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"행안부 주소 API 오류: HTTP {resp.status_code}"
        )

    body = resp.json()
    results = body.get("results", {})
    common  = results.get("common", {})

    # 에러 체크
    err_cd = common.get("errorCode", "0")
    if err_cd != "0":
        err_msg = common.get("errorMessage", "알 수 없는 오류")
        raise HTTPException(
            status_code=400,
            detail=f"주소 검색 오류: [{err_cd}] {err_msg}"
        )

    juso_list = results.get("juso", [])
    if not juso_list:
        return []

    # 정규화된 결과 반환
    return [
        {
            "road_address":  j.get("roadAddr", ""),
            "jibun_address": j.get("jibunAddr", ""),
            "zip_code":      j.get("zipNo", ""),
            "building_name": j.get("bdNm", ""),
            "sido":          j.get("siNm", ""),
            "sigungu":       j.get("sggNm", ""),
            # 좌표 API 호출에 필요한 키값들
            "adm_cd":        j.get("admCd", ""),
            "rn_mgt_sn":     j.get("rnMgtSn", ""),
            "udrt_yn":       j.get("udrtYn", ""),
            "buld_mnnm":     j.get("buldMnnm", ""),
            "buld_slno":     j.get("buldSlno", ""),
        }
        for j in juso_list
    ]


async def _get_coord(adm_cd: str, rn_mgt_sn: str, udrt_yn: str,
                     buld_mnnm: str, buld_slno: str) -> dict:
    """
    행안부 좌표제공 API 호출 → 위경도 반환.
    """
    if not JUSO_KEY:
        raise HTTPException(
            status_code=503,
            detail="JUSO_API_KEY 환경변수가 설정되지 않았습니다."
        )

    params = {
        "confmKey":   JUSO_KEY,
        "admCd":      adm_cd,
        "rnMgtSn":    rn_mgt_sn,
        "udrtYn":     udrt_yn,
        "buldMnnm":   buld_mnnm,
        "buldSlno":   buld_slno,
        "resultType": "json",
    }

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(JUSO_COORD_URL, params=params)

    if resp.status_code != 200:
        return {"lat": None, "lng": None}

    body = resp.json()
    results = body.get("results", {})
    juso_list = results.get("juso", [])

    if not juso_list:
        return {"lat": None, "lng": None}

    j = juso_list[0]
    lat = j.get("entY") or j.get("y")
    lng = j.get("entX") or j.get("x")

    try:
        return {"lat": float(lat), "lng": float(lng)}
    except (TypeError, ValueError):
        return {"lat": None, "lng": None}


@router.get("/search")
async def search_address(
    query: str = Query(..., description="검색할 주소 (예: 서울시 강남구 테헤란로)"),
    count: int = Query(10, ge=1, le=20, description="결과 수"),
):
    """
    주소 검색 → 후보 목록 반환.
    프론트에서 사용자가 선택하면 해당 주소의 키값으로 /juso/coord 호출.
    """
    results = await _search_juso(query, count)
    return {"success": True, "data": results, "count": len(results)}


@router.get("/coord")
async def get_coord(
    query: Optional[str] = Query(None, description="검색할 주소 (자동으로 첫 번째 결과의 좌표 반환)"),
    admCd: Optional[str] = Query(None, description="행정구역코드"),
    rnMgtSn: Optional[str] = Query(None, description="도로명코드"),
    udrtYn: Optional[str] = Query(None, description="지하여부"),
    buldMnnm: Optional[str] = Query(None, description="건물본번"),
    buldSlno: Optional[str] = Query(None, description="건물부번"),
):
    """
    주소 → 좌표 반환.

    사용법 1: query만 전달 → 첫 번째 검색 결과의 좌표 반환
    사용법 2: admCd, rnMgtSn, udrtYn, buldMnnm, buldSlno 전달 → 해당 주소의 좌표 반환
    """
    # 방법 2: 키값으로 직접 좌표 조회
    if admCd and rnMgtSn:
        coord = await _get_coord(admCd, rnMgtSn, udrtYn or "0", buldMnnm or "0", buldSlno or "0")
        return {"success": True, "data": coord}

    # 방법 1: 주소 텍스트로 검색 후 첫 번째 결과의 좌표
    if not query:
        raise HTTPException(status_code=400, detail="query 또는 admCd+rnMgtSn 파라미터가 필요합니다.")

    results = await _search_juso(query, 1)
    if not results:
        raise HTTPException(status_code=404, detail=f"주소를 찾을 수 없습니다: {query}")

    addr = results[0]
    coord = await _get_coord(
        addr["adm_cd"], addr["rn_mgt_sn"], addr["udrt_yn"],
        addr["buld_mnnm"], addr["buld_slno"]
    )

    return {
        "success": True,
        "data": {
            "query":        query,
            "road_address": addr["road_address"],
            "jibun_address": addr["jibun_address"],
            "zip_code":     addr["zip_code"],
            "building_name": addr["building_name"],
            "sido":         addr["sido"],
            "sigungu":      addr["sigungu"],
            "lat":          coord["lat"],
            "lng":          coord["lng"],
        }
    }
