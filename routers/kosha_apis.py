"""
한국산업안전보건공단(KOSHA) 공공 API 라우터 — v1.5.0
prefix: /kosha

v1.5.0:
  [ADD] GET /kosha/construction-safety-light  — 건설현장 안전 신호등
  [ADD] GET /kosha/risk-assessment-accredited — 위험성평가 인정사업장 현황

v1.4.0:
  - MSDS XML 전용 파싱 함수 분리
  - MSDS 파라미터명 수정: chemNm/casNo

대상 외부 API (apis.data.go.kr/B552468):
  GET /kosha/law-search                    안전보건법령 스마트검색
  GET /kosha/accident-cases                국내재해사례 게시판 조회
  GET /kosha/accident-cases/attachments    국내재해사례 첨부파일 경로
  GET /kosha/safety-materials              안전보건자료 링크 서비스
  GET /kosha/construction-accidents        건설업 일별 중대재해 현황
  GET /kosha/construction-safety-light     건설현장 안전 신호등 ★신규
  GET /kosha/risk-assessment-accredited    위험성평가 인정사업장 현황 ★신규
  GET /kosha/msds                          MSDS 화학물질 목록 조회
  GET /kosha/msds/sections                 MSDS 섹션 목록
  GET /kosha/msds/{kmc_no}/detail          MSDS 섹션별 상세 조회
  GET /kosha/kosha-guide                   기술지원규정(KOSHA GUIDE) 조회
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import httpx
import os
import json
import xml.etree.ElementTree as ET

router = APIRouter(prefix="/kosha", tags=["KOSHA공공API"])

VERSION = "1.5.0"
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


def _parse_xml_response(text: str) -> dict:
    """KOSHA XML 응답 파싱 → dict"""
    try:
        root = ET.fromstring(text)
        result_code = root.findtext(".//resultCode") or "00"
        result_msg  = root.findtext(".//resultMsg") or ""
        total_count = root.findtext(".//totalCount")
        page_no     = root.findtext(".//pageNo")
        num_of_rows = root.findtext(".//numOfRows")
        items = []
        items_el = root.find(".//items")
        if items_el is not None:
            for item_el in items_el.findall("item"):
                item = {}
                for child in item_el:
                    item[child.tag] = child.text or ""
                items.append(item)
        return {
            "header": {"resultCode": result_code, "resultMsg": result_msg},
            "body": {
                "items":      items,
                "totalCount": int(total_count) if total_count else 0,
                "pageNo":     int(page_no)     if page_no     else 1,
                "numOfRows":  int(num_of_rows) if num_of_rows else 10,
            }
        }
    except Exception as e:
        return {"raw_xml": text[:3000], "parse_error": str(e)}


async def _kosha_get(path: str, params: dict) -> dict:
    """KOSHA API GET 공통 호출 — JSON 우선, XML fallback"""
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
                return _parse_xml_response(text)
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"KOSHA API 오류 {e.response.status_code}: {e.response.text[:200]}"
        )
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"KOSHA API 연결 실패: {str(e)}")


# ─────────────────────────────────────────────────────
# 법령 스마트검색
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
# 국내재해사례
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


@router.get("/accident-cases/attachments")
async def accident_case_attachments(
    board_no:    str = Query(..., description="재해사례 게시판 번호"),
    page_no:     int = Query(1,  ge=1),
    num_of_rows: int = Query(10, ge=1, le=100),
):
    """국내재해사례 첨부파일(PDF 등) 다운로드 경로 조회."""
    result = await _kosha_get("disaster_attach_api02/Disaster_attach_api02", {
        "callApiId":  "국내재해사례 게시판 첨부파일 조회",
        "boardno":    board_no,
        "pageNo":     page_no,
        "numOfRows":  num_of_rows,
    })
    return {"status": "success", "data": result}


# ─────────────────────────────────────────────────────
# 안전보건자료
# ─────────────────────────────────────────────────────
@router.get("/safety-materials")
async def safety_materials(
    product_type:     Optional[str] = Query(None, description="제작형태"),
    industry:         Optional[str] = Query(None, description="업종 (공통/제조/건설/서비스/기타)"),
    accident_type:    Optional[str] = Query(None, description="재해유형"),
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
# 건설업 중대재해
# ─────────────────────────────────────────────────────
@router.get("/construction-accidents")
async def construction_accidents(
    year:        Optional[str] = Query(None, description="연도 (YYYY)"),
    month:       Optional[str] = Query(None, description="월 (MM)"),
    day:         Optional[str] = Query(None, description="일 (DD)"),
    page_no:     int = Query(1,  ge=1),
    num_of_rows: int = Query(10, ge=1, le=100),
):
    """건설업종 일별 중대재해 현황 (작업공종, 기인물, 재해종류, 재해개요, 위험성 감소대책)."""
    params: dict = {"pageNo": page_no, "numOfRows": num_of_rows}
    if year:  params["year"]  = year
    if month: params["month"] = month
    if day:   params["day"]   = day
    result = await _kosha_get("constDsstr01/getconstDsstr01", params)
    return {"status": "success", "data": result}


# ─────────────────────────────────────────────────────
# ★ 신규: 건설현장 안전 신호등
# ─────────────────────────────────────────────────────
@router.get("/construction-safety-light")
async def construction_safety_light(
    sido:        Optional[str] = Query(None, description="시도명 (예: 서울특별시)"),
    sigungu:     Optional[str] = Query(None, description="시군구명"),
    site_nm:     Optional[str] = Query(None, description="현장명 검색"),
    signal:      Optional[str] = Query(None, description="신호등 결과 (적색/황색/녹색)"),
    page_no:     int = Query(1,  ge=1),
    num_of_rows: int = Query(20, ge=1, le=100),
):
    """
    건설재해예방전문지도기관 기술지도 대상 중소규모 건설현장의
    최근 기술지도 결과를 신호등(RED/YELLOW/GREEN)으로 표시.

    - 적색: 위험 (시정조치 필요)
    - 황색: 주의
    - 녹색: 양호

    산업안전보건법 제73조(건설공사의 산업재해 예방 지도) 기반.
    현재 기술지도 진행 중인 사업장만 표출.
    """
    params: dict = {
        "pageNo":    page_no,
        "numOfRows": num_of_rows,
    }
    if sido:     params["sido"]    = sido
    if sigungu:  params["sigungu"] = sigungu
    if site_nm:  params["siteNm"]  = site_nm
    if signal:   params["signal"]  = signal

    result = await _kosha_get("constructSafety/getConstructSafetySignal", params)
    return {"status": "success", "endpoint": "건설현장 안전 신호등", "data": result}


# ─────────────────────────────────────────────────────
# ★ 신규: 위험성평가 인정사업장 현황
# ─────────────────────────────────────────────────────
@router.get("/risk-assessment-accredited")
async def risk_assessment_accredited(
    company_nm:  Optional[str] = Query(None, description="사업장명 검색"),
    sido:        Optional[str] = Query(None, description="시도 (예: 서울특별시)"),
    industry:    Optional[str] = Query(None, description="업종"),
    page_no:     int = Query(1,  ge=1),
    num_of_rows: int = Query(20, ge=1, le=100),
):
    """
    한국산업안전보건공단 위험성평가 인정사업장 현황.
    인정일, 유효기간, 관할노동지청 등 포함.

    - 인정 유효기간: 인정일로부터 3년
    - 유효기간 만료 3개월 전부터 재인정 신청 가능
    - 2021.10.5 ~ 현재 인정 사업장 제공
    """
    params: dict = {
        "pageNo":    page_no,
        "numOfRows": num_of_rows,
    }
    if company_nm: params["companyNm"] = company_nm
    if sido:       params["sido"]      = sido
    if industry:   params["industry"]  = industry

    result = await _kosha_get("riskAssmt/getRiskAssmtAccdtInfo", params)
    return {"status": "success", "endpoint": "위험성평가 인정사업장", "data": result}


# ─────────────────────────────────────────────────────
# MSDS
# ─────────────────────────────────────────────────────
@router.get("/msds/sections")
async def msds_sections():
    """MSDS 섹션 번호와 명칭 목록."""
    return {
        "status": "success",
        "data": [{"section": k, "name": v} for k, v in MSDS_SECTIONS.items()]
    }


@router.get("/msds")
async def msds_list(
    chem_nm:     Optional[str] = Query(None, description="화학물질명 검색 (chemNm)"),
    cas_no:      Optional[str] = Query(None, description="CAS 번호 (casNo, 예: 71-43-2)"),
    page_no:     int = Query(1,  ge=1),
    num_of_rows: int = Query(10, ge=1, le=100),
):
    """공단 화학물질정보시스템 MSDS 화학물질 목록 조회 (XML 전용 응답)."""
    params: dict = {"pageNo": page_no, "numOfRows": num_of_rows}
    if chem_nm: params["chemNm"] = chem_nm
    if cas_no:  params["casNo"]  = cas_no
    result = await _kosha_get("msdschem/getChemList", params)
    return {"status": "success", "data": result}


@router.get("/msds/{kmc_no}/detail")
async def msds_detail(
    kmc_no:  str,
    section: str = Query("01", description="MSDS 섹션 01~16"),
):
    """화학물질 KMC 번호로 MSDS 섹션별 상세정보 조회."""
    section = section.zfill(2)
    if section not in MSDS_SECTIONS:
        raise HTTPException(status_code=400, detail="section은 01~16 범위")
    result = await _kosha_get(
        f"msdschem/getChemDetail{section}",
        {"kmcNo": kmc_no}
    )
    return {
        "status":       "success",
        "kmc_no":       kmc_no,
        "section":      section,
        "section_name": MSDS_SECTIONS[section],
        "data":         result,
    }


# ─────────────────────────────────────────────────────
# KOSHA GUIDE
# ─────────────────────────────────────────────────────
@router.get("/kosha-guide")
async def kosha_guide(
    keyword:     Optional[str] = Query(None, description="검색어"),
    guide_no:    Optional[str] = Query(None, description="지침번호 (예: G-1, P-155)"),
    category:    Optional[str] = Query(None, description="분야코드 (G=일반, M=기계, C=화공, B=건설, H=보건)"),
    page_no:     int = Query(1,  ge=1),
    num_of_rows: int = Query(10, ge=1, le=100),
):
    """한국산업안전보건공단 기술지원규정(KOSHA GUIDE) 목록 조회."""
    params: dict = {
        "pageNo":     page_no,
        "numOfRows":  num_of_rows,
        "returnType": "json",
    }
    if keyword:  params["keyword"]  = keyword
    if guide_no: params["guideNo"]  = guide_no
    if category: params["category"] = category
    result = await _kosha_get("koshaguide/getKoshaGuide", params)
    return {"status": "success", "data": result}
