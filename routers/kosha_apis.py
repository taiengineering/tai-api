"""
한국산업안전보건공단(KOSHA) 공공 API 라우터 — v1.1.0
prefix: /kosha

v1.1.0:
  - kosha-guide 엔드포인트 수정:
    koshaGuideApiService/getKoshaGuideList → koshaguide/getKoshaGuide
  - _kosha_get 응답 파싱 개선: response.body / body / 전체 구조 모두 처리
  - returnType 기본값 제거 (XML 기본 응답 허용 → JSON 우선 파싱)
  - MSDS 엔드포인트 수정 확인 필요 (msdsInfoSvc/getMsdsList 추정값 유지)

대상 외부 API (apis.data.go.kr/B552468):
  GET /kosha/law-search             안전보건법령 스마트검색
  GET /kosha/accident-cases         국내재해사례 게시판 조회
  GET /kosha/safety-materials       안전보건자료 링크 서비스
  GET /kosha/construction-accidents 건설업 일별 중대재해 현황
  GET /kosha/msds                   물질안전보건자료(MSDS) 조회
  GET /kosha/kosha-guide            기술지원규정(코샤가이드) 조회 ✅ 확인됨
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import httpx
import os
import json

router = APIRouter(prefix="/kosha", tags=["KOSHA공공API"])

VERSION = "1.1.0"
SERVICE_KEY = os.getenv(
    "KOSHA_SERVICE_KEY",
    os.getenv("BUILDING_API_KEY", "da4e826323c2c9fef9f325bd4e39a3765d06ac1b582695bcbc475bc0a076255b")
)
KOSHA_BASE = "https://apis.data.go.kr/B552468"


async def _kosha_get(path: str, params: dict) -> dict:
    """KOSHA API GET 공통 호출 — JSON/XML 자동 파싱"""
    params["serviceKey"] = SERVICE_KEY
    # returnType은 각 엔드포인트별로 지정 (기본 제거)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{KOSHA_BASE}/{path}", params=params)
            resp.raise_for_status()
            ct = resp.headers.get("content-type", "")
            text = resp.text

            # JSON 파싱 시도
            try:
                data = json.loads(text)
                # response.body 구조 → body로 평탄화
                if "response" in data and isinstance(data["response"], dict):
                    return data["response"]
                return data
            except Exception:
                # XML이면 원문 반환
                return {"raw_xml": text[:5000], "note": "XML 응답. 파싱 필요 시 추가 처리"}
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"KOSHA API 오류 {e.response.status_code}: {e.response.text[:200]}"
        )
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"KOSHA API 연결 실패: {str(e)}")


# ─────────────────────────────────────────────────────
# GET /kosha/law-search  안전보건법령 스마트검색
# ─────────────────────────────────────────────────────
@router.get("/law-search")
async def law_search(
    keyword: str = Query(..., description="검색어 (예: '보호구', '처장', '리프트')"),
    page_no:     int = Query(1,  ge=1),
    num_of_rows: int = Query(10, ge=1, le=100),
):
    """
    산업안전보건법령, KOSHA GUIDE, 중대재해처벌법 등 통합 AI 스마트검색.
    유사단어도 자동 검색됨.
    """
    result = await _kosha_get("srch/smartSearch", {
        "keyword":   keyword,
        "pageNo":    page_no,
        "numOfRows": num_of_rows,
        "returnType": "json",
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
    callApiId는 필수 고정값.
    """
    params: dict = {
        "callApiId":  "국내재해사례 게시판 조회",
        "pageNo":     page_no,
        "numOfRows":  num_of_rows,
    }
    if business: params["business"] = business
    if keyword:  params["keyword"]  = keyword

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
    """한국산업안전보건공단 안전보건자료(책자, OPS, 교안, 영상 등) 링크(URL) 조회."""
    params: dict = {"pageNo": page_no, "numOfRows": num_of_rows}
    if product_type:     params["productType"]    = product_type
    if industry:         params["industry"]        = industry
    if accident_type:    params["accidentType"]    = accident_type
    if foreign_language: params["foreignLanguage"] = foreign_language

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
    (현재 2017~2021년 데이터 제공)
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
    cas_no:        Optional[str] = Query(None, description="CAS 번호 (예: 71-43-2)"),
    page_no:       int = Query(1,  ge=1),
    num_of_rows:   int = Query(10, ge=1, le=100),
):
    """
    공단 화학물질정보시스템(msds.kosha.or.kr) 화학물질 안전보건자료 목록 조회.
    현재 20,568종 화학물질 서비스 중.
    """
    params: dict = {"pageNo": page_no, "numOfRows": num_of_rows}
    if material_name: params["materialName"] = material_name
    if cas_no:        params["casNo"]        = cas_no

    result = await _kosha_get("msdsInfoSvc/getMsdsList", params)
    return {"status": "success", "data": result}


# ─────────────────────────────────────────────────────
# GET /kosha/kosha-guide  기술지원규정(코샤가이드) 조회
# End Point: https://apis.data.go.kr/B552468/koshaguide
# 실제 엔드포인트: koshaguide/getKoshaGuide  ✅ 확인됨
# ─────────────────────────────────────────────────────
@router.get("/kosha-guide")
async def kosha_guide(
    keyword:     Optional[str] = Query(None, description="검색어 (지침명, 코드 등)"),
    guide_no:    Optional[str] = Query(None, description="지침번호 (예: G-1, P-155 등)"),
    category:    Optional[str] = Query(None, description="분야코드 (G=일반, M=기계, C=화공, B=건설, H=보건 등)"),
    page_no:     int = Query(1,  ge=1),
    num_of_rows: int = Query(10, ge=1, le=100),
):
    """
    한국산업안전보건공단 기술지원규정(KOSHA GUIDE) 목록 조회.
    분야, 지침번호, 명칭, 등록일, 분류내용 제공.
    End Point: https://apis.data.go.kr/B552468/koshaguide
    """
    params: dict = {"pageNo": page_no, "numOfRows": num_of_rows}
    if keyword:  params["keyword"]  = keyword
    if guide_no: params["guideNo"]  = guide_no
    if category: params["category"] = category

    # ✅ 실제 확인된 엔드포인트
    result = await _kosha_get("koshaguide/getKoshaGuide", params)
    return {"status": "success", "data": result}
