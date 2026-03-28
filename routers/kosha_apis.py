"""
한국산업안전보건공단(KOSHA) 공공 API 라우터 — v1.3.0
prefix: /kosha

v1.3.0:
  - MSDS getChemList: type=json 파라미터 추가 (XML→JSON 강제)
  - MSDS getChemDetail: type=json 파라미터 추가
  - kosha-guide: returnType=json 파라미터 추가
  - _kosha_get: XML fallback 파싱 개선 (xml.etree 미사용, 원문 반환 유지)

v1.2.0: MSDS 엔드포인트 msdschem/getChemList ✅
v1.1.0: kosha-guide koshaguide/getKoshaGuide ✅

대상 외부 API (apis.data.go.kr/B552468):
  GET /kosha/law-search                  안전보건법령 스마트검색
  GET /kosha/accident-cases              국내재해사례 게시판 조회
  GET /kosha/safety-materials            안전보건자료 링크 서비스
  GET /kosha/construction-accidents      건설업 일별 중대재해 현황
  GET /kosha/msds                        MSDS 화학물질 목록 조회 ✅
  GET /kosha/msds/sections               MSDS 섹션 목록
  GET /kosha/msds/{kmc_no}/detail        MSDS 섹션별 상세 조회 ✅
  GET /kosha/kosha-guide                 기술지원규정(코샤가이드) 조회 ✅
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import httpx
import os
import json

router = APIRouter(prefix="/kosha", tags=["KOSHA공공API"])

VERSION = "1.3.0"
SERVICE_KEY = os.getenv(
    "KOSHA_SERVICE_KEY",
    os.getenv("BUILDING_API_KEY", "da4e826323c2c9fef9f325bd4e39a3765d06ac1b582695bcbc475bc0a076255b")
)
KOSHA_BASE = "https://apis.data.go.kr/B552468"

MSDS_SECTIONS = {
    "01": "화학제품과 회사에 관한 정보",
    "02": "유해성·위험성",
    "03": "구성성분의 명칭 및 함유량",
    "04": "응급조치요령",
    "05": "폭발·화재시 대처방법",
    "06": "누출사고시 대처방법",
    "07": "취급 및 저장방법",
    "08": "노출방지 및 개인보호구",
    "09": "물리화학적 특성",
    "10": "안정성 및 반응성",
    "11": "독성에 관한 정보",
    "12": "환경에 미치는 영향",
    "13": "폐기시 주의사항",
    "14": "운송에 관한 정보",
    "15": "법적 규제현황",
    "16": "기타 참고사항",
}


async def _kosha_get(path: str, params: dict) -> dict:
    """KOSHA API GET 공통 호출 — JSON/XML 자동 파싱"""
    params["serviceKey"] = SERVICE_KEY
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{KOSHA_BASE}/{path}", params=params)
            resp.raise_for_status()
            text = resp.text
            try:
                data = json.loads(text)
                if "response" in data and isinstance(data["response"], dict):
                    return data["response"]
                return data
            except Exception:
                return {"raw_xml": text[:5000], "note": "XML 응답"}
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"KOSHA API 오류 {e.response.status_code}: {e.response.text[:200]}"
        )
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"KOSHA API 연결 실패: {str(e)}")


# ─────────────────────────────────────────────────────
# GET /kosha/law-search
# ─────────────────────────────────────────────────────
@router.get("/law-search")
async def law_search(
    keyword:     str = Query(..., description="검색어 (예: '보호구', '리프트')"),
    page_no:     int = Query(1,  ge=1),
    num_of_rows: int = Query(10, ge=1, le=100),
):
    """산업안전보건법령, KOSHA GUIDE, 중대재해처벌법 등 통합 AI 스마트검색."""
    result = await _kosha_get("srch/smartSearch", {
        "keyword":    keyword,
        "pageNo":     page_no,
        "numOfRows":  num_of_rows,
        "returnType": "json",
    })
    return {"status": "success", "data": result}


# ─────────────────────────────────────────────────────
# GET /kosha/accident-cases
# ─────────────────────────────────────────────────────
@router.get("/accident-cases")
async def accident_cases(
    business:    Optional[str] = Query(None, description="게시판 종류 (제조업/건설업/조선업 등)"),
    keyword:     Optional[str] = Query(None, description="제목 검색 키워드"),
    page_no:     int = Query(1,  ge=1),
    num_of_rows: int = Query(10, ge=1, le=100),
):
    """kosha.or.kr 국내재해사례 게시판 정보."""
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
# GET /kosha/safety-materials
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
    """안전보건자료(책자, OPS, 교안, 영상 등) 링크(URL) 조회."""
    params: dict = {"pageNo": page_no, "numOfRows": num_of_rows}
    if product_type:     params["productType"]    = product_type
    if industry:         params["industry"]        = industry
    if accident_type:    params["accidentType"]    = accident_type
    if foreign_language: params["foreignLanguage"] = foreign_language
    result = await _kosha_get("selectMediaList01/getselectMediaList01", params)
    return {"status": "success", "data": result}


# ─────────────────────────────────────────────────────
# GET /kosha/construction-accidents
# ─────────────────────────────────────────────────────
@router.get("/construction-accidents")
async def construction_accidents(
    year:        Optional[str] = Query(None, description="연도 (YYYY)"),
    month:       Optional[str] = Query(None, description="월 (MM)"),
    day:         Optional[str] = Query(None, description="일 (DD)"),
    page_no:     int = Query(1,  ge=1),
    num_of_rows: int = Query(10, ge=1, le=100),
):
    """건설업종 일별 중대재해 현황 (2017~2021년 데이터)."""
    params: dict = {"pageNo": page_no, "numOfRows": num_of_rows}
    if year:  params["year"]  = year
    if month: params["month"] = month
    if day:   params["day"]   = day
    result = await _kosha_get("constDsstr01/getconstDsstr01", params)
    return {"status": "success", "data": result}


# ─────────────────────────────────────────────────────
# GET /kosha/msds/sections  (반드시 /{kmc_no}/detail 보다 먼저 선언)
# ─────────────────────────────────────────────────────
@router.get("/msds/sections")
async def msds_sections():
    """MSDS 섹션 번호와 명칭 목록 반환."""
    return {
        "status": "success",
        "data": [{"section": k, "name": v} for k, v in MSDS_SECTIONS.items()]
    }


# ─────────────────────────────────────────────────────
# GET /kosha/msds  MSDS 화학물질 목록 ✅
# msdschem/getChemList — type=json 추가
# ─────────────────────────────────────────────────────
@router.get("/msds")
async def msds_list(
    material_name: Optional[str] = Query(None, description="화학물질명 검색"),
    cas_no:        Optional[str] = Query(None, description="CAS 번호 (예: 71-43-2)"),
    page_no:       int = Query(1,  ge=1),
    num_of_rows:   int = Query(10, ge=1, le=100),
):
    """
    공단 화학물질정보시스템 MSDS 화학물질 목록 조회.
    현재 20,568종 화학물질 서비스 중.
    """
    params: dict = {
        "pageNo":    page_no,
        "numOfRows": num_of_rows,
        "type":      "json",     # ✅ JSON 응답 강제
    }
    if material_name: params["materialName"] = material_name
    if cas_no:        params["casNo"]        = cas_no

    result = await _kosha_get("msdschem/getChemList", params)
    return {"status": "success", "data": result}


# ─────────────────────────────────────────────────────
# GET /kosha/msds/{kmc_no}/detail  MSDS 섹션별 상세 ✅
# ─────────────────────────────────────────────────────
@router.get("/msds/{kmc_no}/detail")
async def msds_detail(
    kmc_no:  str,
    section: str = Query("01", description="MSDS 섹션 01~16"),
):
    """화학물질 KMC 번호로 MSDS 섹션별 상세정보 조회."""
    section = section.zfill(2)
    if section not in MSDS_SECTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"section은 01~16 범위여야 합니다."
        )
    result = await _kosha_get(
        f"msdschem/getChemDetail{section}",
        {"kmcNo": kmc_no, "type": "json"}   # ✅ JSON 응답 강제
    )
    return {
        "status":       "success",
        "kmc_no":       kmc_no,
        "section":      section,
        "section_name": MSDS_SECTIONS[section],
        "data":         result,
    }


# ─────────────────────────────────────────────────────
# GET /kosha/kosha-guide  기술지원규정(코샤가이드) ✅
# returnType=json 추가
# ─────────────────────────────────────────────────────
@router.get("/kosha-guide")
async def kosha_guide(
    keyword:     Optional[str] = Query(None, description="검색어"),
    guide_no:    Optional[str] = Query(None, description="지침번호 (예: G-1, P-155)"),
    category:    Optional[str] = Query(None, description="분야코드 (G=일반, M=기계, C=화공, B=건설, H=보건)"),
    page_no:     int = Query(1,  ge=1),
    num_of_rows: int = Query(10, ge=1, le=100),
):
    """
    한국산업안전보건공단 기술지원규정(KOSHA GUIDE) 목록 조회.
    End Point: https://apis.data.go.kr/B552468/koshaguide
    """
    params: dict = {
        "pageNo":     page_no,
        "numOfRows":  num_of_rows,
        "returnType": "json",    # ✅ JSON 응답 강제
    }
    if keyword:  params["keyword"]  = keyword
    if guide_no: params["guideNo"]  = guide_no
    if category: params["category"] = category

    result = await _kosha_get("koshaguide/getKoshaGuide", params)
    return {"status": "success", "data": result}
