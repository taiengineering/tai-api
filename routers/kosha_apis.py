"""
한국산업안전보건공단(KOSHA) 공공 API 라우터 — v1.0.0
prefix: /kosha

대상 외부 API (apis.data.go.kr/B552468):
  GET /kosha/law-search          안전보건법령 스마트검색
  GET /kosha/accident-cases      국내재해사례 게시판 조회
  GET /kosha/safety-materials    안전보건자료 링크 서비스
  GET /kosha/construction-accidents 건설업 일별 중대재해 현황
  GET /kosha/msds                물질안전보건자료(MSDS) 조회
  GET /kosha/kosha-guide         기술지원규정(코샵가이드) 조회
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import httpx
import os

router = APIRouter(prefix="/kosha", tags=["KOSHA공공API"])

VERSION = "1.0.0"
SERVICE_KEY = os.getenv(
    "KOSHA_SERVICE_KEY",
    os.getenv("BUILDING_API_KEY", "da4e826323c2c9fef9f325bd4e39a3765d06ac1b582695bcbc475bc0a076255b")
)
KOSHA_BASE = "https://apis.data.go.kr/B552468"


async def _kosha_get(path: str, params: dict) -> dict:
    """KOSHA API GET 공통 호출"""
    params["serviceKey"] = SERVICE_KEY
    params.setdefault("returnType", "json")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{KOSHA_BASE}/{path}", params=params)
            resp.raise_for_status()
            ct = resp.headers.get("content-type", "")
            if "json" in ct:
                return resp.json()
            # XML fallback → 원문 반환
            return {"raw_xml": resp.text[:3000]}
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"KOSHA API 오류 {e.response.status_code}: {e.response.text[:200]}")
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"KOSHA API 연결 실패: {str(e)}")


# ─────────────────────────────────────────────────────
# GET /kosha/law-search  안전보건법령 스마트검색
# ─────────────────────────────────────────────────────
@router.get("/law-search")
async def law_search(
    keyword: str = Query(..., description="검색어 (예: '보호구', '처장', '리프트')"),
    page_no:      int = Query(1,  ge=1, description="페이지 번호"),
    num_of_rows:  int = Query(10, ge=1, le=100, description="페이지당 결과 수"),
):
    """
    산업안전보건법령, KOSHA GUIDE, 중대재해처벨법 등 통합 검색.
    AI 기반으로 유사단어도 검색됨.
    """
    result = await _kosha_get("srch/smartSearch", {
        "keyword":    keyword,
        "pageNo":     page_no,
        "numOfRows":  num_of_rows,
    })
    return {"status": "success", "data": result}


# ─────────────────────────────────────────────────────
# GET /kosha/accident-cases  국내재해사례 게시판
# ─────────────────────────────────────────────────────
@router.get("/accident-cases")
async def accident_cases(
    business:    Optional[str] = Query(None, description="게시판 종류 (제조업/건설업/조선업 등)"),
    keyword:     Optional[str] = Query(None, description="제목 검색 키워드"),
    page_no:     int = Query(1,  ge=1),
    num_of_rows: int = Query(10, ge=1, le=100),
):
    """
    kosha.or.kr 국내재해사례 게시판 정보.
    callApiId는 고정값.
    """
    params: dict = {
        "callApiId":  "국내재해사례 게시판 조회",
        "pageNo":     page_no,
        "numOfRows":  num_of_rows,
    }
    if business:
        params["business"] = business
    if keyword:
        params["keyword"] = keyword

    result = await _kosha_get("disaster_api02/getdisaster_api02", params)
    return {"status": "success", "data": result}


# ─────────────────────────────────────────────────────
# GET /kosha/safety-materials  안전보건자료 링크
# ─────────────────────────────────────────────────────
@router.get("/safety-materials")
async def safety_materials(
    product_type:     Optional[str] = Query(None, description="제작형태 코드"),
    industry:         Optional[str] = Query(None, description="업종 (제조/건설/서비스/공통/기타)"),
    accident_type:    Optional[str] = Query(None, description="재해유형 코드"),
    foreign_language: Optional[str] = Query(None, description="외국어 구분"),
    page_no:          int = Query(1,  ge=1),
    num_of_rows:      int = Query(10, ge=1, le=100),
):
    """
    한국산업안전보건공단 안전보건자료(책자, OPS, 교안, 영상 등) 링크(URL) 조회.
    """
    params: dict = {"pageNo": page_no, "numOfRows": num_of_rows}
    if product_type:     params["productType"]     = product_type
    if industry:         params["industry"]         = industry
    if accident_type:    params["accidentType"]     = accident_type
    if foreign_language: params["foreignLanguage"]  = foreign_language

    result = await _kosha_get("selectMediaList01/getselectMediaList01", params)
    return {"status": "success", "data": result}


# ─────────────────────────────────────────────────────
# GET /kosha/construction-accidents  건설업 일별 중대재해
# ─────────────────────────────────────────────────────
@router.get("/construction-accidents")
async def construction_accidents(
    year:        Optional[str] = Query(None, description="연도 (YYYY)"),
    month:       Optional[str] = Query(None, description="월 (MM)"),
    day:         Optional[str] = Query(None, description="일 (DD)"),
    page_no:     int = Query(1,  ge=1),
    num_of_rows: int = Query(10, ge=1, le=100),
):
    """
    건설업종에 대한 일별 중대재해 현황 조회.
    작업공종, 기인물, 재해종류, 재해개요, 위험성감소대책 제공.
    (현재 2017엠c2021년 데이터 제공)
    """
    params: dict = {"pageNo": page_no, "numOfRows": num_of_rows}
    if year:  params["year"]  = year
    if month: params["month"] = month
    if day:   params["day"]   = day

    result = await _kosha_get("constDsstr01/getconstDsstr01", params)
    return {"status": "success", "data": result}


# ─────────────────────────────────────────────────────
# GET /kosha/msds  물질안전보건자료(MSDS) 조회
# ─────────────────────────────────────────────────────
@router.get("/msds")
async def msds_search(
    material_name: Optional[str] = Query(None, description="화학물질명 (CAS번호도 가능)"),
    cas_no:        Optional[str] = Query(None, description="CAS 번호"),
    page_no:       int = Query(1,  ge=1),
    num_of_rows:   int = Query(10, ge=1, le=100),
):
    """
    공단 화학물질정보시스템(msds.kosha.or.kr) 화학물질 안전보건자료 목록 조회.
    """
    params: dict = {"pageNo": page_no, "numOfRows": num_of_rows}
    if material_name: params["materialName"] = material_name
    if cas_no:        params["casNo"]        = cas_no

    # MSDS API 엔드포인트
    result = await _kosha_get("msdsInfoSvc/getMsdsList", params)
    return {"status": "success", "data": result}


# ─────────────────────────────────────────────────────
# GET /kosha/kosha-guide  기술지원규정(코샵가이드) 조회
# ─────────────────────────────────────────────────────
@router.get("/kosha-guide")
async def kosha_guide(
    keyword:     Optional[str] = Query(None, description="검색어"),
    category:    Optional[str] = Query(None, description="분야 (일반/기계/화공/건설/보건)"),
    guide_no:    Optional[str] = Query(None, description="지침번호"),
    page_no:     int = Query(1,  ge=1),
    num_of_rows: int = Query(10, ge=1, le=100),
):
    """
    한국산업안전보건공단 기술지원규정(KOSHA GUIDE) 목록 조회.
    분야, 지침번호, 명칭, 등록일, 분류내용 제공.
    """
    params: dict = {"pageNo": page_no, "numOfRows": num_of_rows}
    if keyword:   params["keyword"]  = keyword
    if category:  params["category"] = category
    if guide_no:  params["guideNo"]  = guide_no

    # 코샵가이드 API 엔드포인트
    result = await _kosha_get("koshaGuideApiService/getKoshaGuideList", params)
    return {"status": "success", "data": result}
