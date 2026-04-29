"""
KOSHA 공공 API 라우터 — v1.8.0
prefix: /kosha

v1.8.0 개정 (공공데이터포털 확인 기반):
  - safety-materials:       callApiId = 1030 (필수 고정값)
  - construction-accidents: callApiId = 1010 (필수 고정값)
  - construction-safety-light: 경로 constplan/getconstplan, callApiId = 1020
  - kosha-guide: API 폐기 확인 → 대체 안전보건법령 스마트검색으로 전환
  - accident-cases: callApiId 파라미터값을 문자열로 유지
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import httpx
import os
import json
import xml.etree.ElementTree as ET

router = APIRouter(prefix="/kosha", tags=["KOSHA공공API"])

def _get_service_key() -> str:
    return (
        os.getenv("DATA_GO_KR_SERVICE_KEY")
        or os.getenv("KOSHA_SERVICE_KEY")
        or os.getenv("BUILDING_API_KEY", "")
    )

KOSHA_BASE = "https://apis.data.go.kr/B552468"

MSDS_SECTIONS = {
    "01": "화학제품과 회사엔 관한 정보", "02": "유해성·위험성",
    "03": "구성성분의 명칭 및 함유량", "04": "응급조치요령",
    "05": "폭발·화재시 대처방법", "06": "누출사고시 대처방법",
    "07": "취급 및 저장방법", "08": "노출방지 및 개인보호구",
    "09": "물리화학적 특성", "10": "안정성 및 반응성",
    "11": "독성에 관한 정보", "12": "환경에 미치는 영향",
    "13": "폐기시 주의사항", "14": "운송에 관한 정보",
    "15": "법적 규제현황", "16": "기타 참고사항",
}


def _xml_items(root: ET.Element) -> list:
    items = []
    for items_el in root.findall(".//items"):
        for item_el in items_el:
            item = {c.tag: c.text or "" for c in item_el}
            if item:
                items.append(item)
    return items


def _parse_xml_response(text: str) -> dict:
    try:
        root = ET.fromstring(text)
        result_code = root.findtext(".//resultCode") or "00"
        result_msg  = root.findtext(".//resultMsg") or ""
        total_count = root.findtext(".//totalCount")
        page_no     = root.findtext(".//pageNo")
        num_of_rows = root.findtext(".//numOfRows")
        items = _xml_items(root)
        return {
            "header": {"resultCode": result_code, "resultMsg": result_msg},
            "body": {
                "items":      items,
                "totalCount": int(total_count) if total_count else 0,
                "pageNo":     int(page_no)     if page_no     else 1,
                "numOfRows":  int(num_of_rows) if num_of_rows else 10,
            },
        }
    except Exception as e:
        return {"raw_xml": text[:3000], "parse_error": str(e)}


async def _kosha_get_raw(path: str, params: dict) -> tuple:
    params["serviceKey"] = _get_service_key()
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{KOSHA_BASE}/{path}", params=params)
        return resp.text, resp.status_code


async def _kosha_get(path: str, params: dict) -> dict:
    params["serviceKey"] = _get_service_key()
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


# ── 디버그 raw 엔드포인트 ────────────────────────────

@router.get("/debug-raw/safety-materials")
async def debug_raw_safety_materials(page_no: int = Query(1), num_of_rows: int = Query(2)):
    """callApiId=1030 필수"""
    text, status = await _kosha_get_raw(
        "selectMediaList01/getselectMediaList01",
        {"callApiId": "1030", "pageNo": page_no, "numOfRows": num_of_rows}
    )
    return {"http_status": status, "raw": text[:3000]}

@router.get("/debug-raw/construction-accidents")
async def debug_raw_const_acc(page_no: int = Query(1), num_of_rows: int = Query(2)):
    """callApiId=1010 필수"""
    text, status = await _kosha_get_raw(
        "constDsstr01/getconstDsstr01",
        {"callApiId": "1010", "pageNo": page_no, "numOfRows": num_of_rows}
    )
    return {"http_status": status, "raw": text[:3000]}

@router.get("/debug-raw/safety-light")
async def debug_raw_safety_light(page_no: int = Query(1), num_of_rows: int = Query(2)):
    """constplan/getconstplan + callApiId=1020"""
    text, status = await _kosha_get_raw(
        "constplan/getconstplan",
        {"callApiId": "1020", "pageNo": page_no, "numOfRows": num_of_rows}
    )
    return {"http_status": status, "raw": text[:3000]}

@router.get("/debug-raw/accident-cases")
async def debug_raw_accident(page_no: int = Query(1), num_of_rows: int = Query(2)):
    """callApiId=국내재해사례 게시판 조회"""
    text, status = await _kosha_get_raw(
        "disaster_api02/getdisaster_api02",
        {"callApiId": "국내재해사례 게시판 조회", "pageNo": page_no, "numOfRows": num_of_rows}
    )
    return {"http_status": status, "raw": text[:3000]}


# ── 정식 엔드포인트 ───────────────────────────────────────

@router.get("/law-search")
async def law_search(
    keyword: str = Query(...),
    page_no: int = Query(1, ge=1),
    num_of_rows: int = Query(10, ge=1, le=100),
):
    result = await _kosha_get("srch/smartSearch", {
        "keyword": keyword, "pageNo": page_no,
        "numOfRows": num_of_rows, "returnType": "json",
    })
    return {"status": "success", "data": result}


@router.get("/accident-cases")
async def accident_cases(
    business: Optional[str] = Query(None),
    keyword:  Optional[str] = Query(None),
    page_no:  int = Query(1, ge=1),
    num_of_rows: int = Query(10, ge=1, le=100),
):
    # callApiId: 문자열 고정값 (고정값이지만 문자열 형식)
    params: dict = {
        "callApiId": "국내재해사례 게시판 조회",
        "pageNo": page_no, "numOfRows": num_of_rows,
    }
    if business: params["business"] = business
    if keyword:  params["keyword"]  = keyword
    result = await _kosha_get("disaster_api02/getdisaster_api02", params)
    return {"status": "success", "data": result}


@router.get("/accident-cases/attachments")
async def accident_case_attachments(
    board_no: str = Query(...),
    page_no:  int = Query(1, ge=1),
    num_of_rows: int = Query(10, ge=1, le=100),
):
    result = await _kosha_get("disaster_attach_api02/Disaster_attach_api02", {
        "callApiId": "국내재해사례 게시판 첨부파일 조회",
        "boardno": board_no, "pageNo": page_no, "numOfRows": num_of_rows,
    })
    return {"status": "success", "data": result}


@router.get("/safety-materials")
async def safety_materials(
    product_type:     Optional[str] = Query(None),
    industry:         Optional[str] = Query(None),
    accident_type:    Optional[str] = Query(None),
    foreign_language: Optional[str] = Query(None),
    page_no:  int = Query(1, ge=1),
    num_of_rows: int = Query(10, ge=1, le=100),
):
    # callApiId=1030 필수 고정값 (포털 문서 확인)
    params: dict = {
        "callApiId": "1030",
        "pageNo": page_no, "numOfRows": num_of_rows,
    }
    if product_type:     params["productType"]    = product_type
    if industry:         params["industry"]        = industry
    if accident_type:    params["accidentType"]    = accident_type
    if foreign_language: params["foreignLanguage"] = foreign_language
    result = await _kosha_get("selectMediaList01/getselectMediaList01", params)
    return {"status": "success", "data": result}


@router.get("/construction-accidents")
async def construction_accidents(
    year:  Optional[str] = Query(None),
    month: Optional[str] = Query(None),
    day:   Optional[str] = Query(None),
    page_no: int = Query(1, ge=1),
    num_of_rows: int = Query(10, ge=1, le=100),
):
    # callApiId=1010 필수 고정값 (포털 문서 확인)
    params: dict = {
        "callApiId": "1010",
        "pageNo": page_no, "numOfRows": num_of_rows,
    }
    if year:  params["year"]  = year
    if month: params["month"] = month
    if day:   params["day"]   = day
    result = await _kosha_get("constDsstr01/getconstDsstr01", params)
    return {"status": "success", "data": result}


@router.get("/construction-safety-light")
async def construction_safety_light(
    sido:    Optional[str] = Query(None),
    sigungu: Optional[str] = Query(None),
    site_nm: Optional[str] = Query(None),
    signal:  Optional[str] = Query(None),
    page_no: int = Query(1, ge=1),
    num_of_rows: int = Query(20, ge=1, le=100),
):
    # 경로: constplan/getconstplan, callApiId=1020 (포털 문서 확인)
    params: dict = {
        "callApiId": "1020",
        "pageNo": page_no, "numOfRows": num_of_rows,
    }
    if sido:    params["sido"]    = sido
    if sigungu: params["sigungu"] = sigungu
    if site_nm: params["siteNm"]  = site_nm
    if signal:  params["signal"]  = signal
    result = await _kosha_get("constplan/getconstplan", params)
    return {"status": "success", "endpoint": "건설현장 안전 신호등", "data": result}


@router.get("/risk-assessment-accredited")
async def risk_assessment_accredited(
    company_nm: Optional[str] = Query(None),
    sido:       Optional[str] = Query(None),
    industry:   Optional[str] = Query(None),
    page_no:    int = Query(1, ge=1),
    num_of_rows: int = Query(20, ge=1, le=100),
):
    params: dict = {"pageNo": page_no, "numOfRows": num_of_rows}
    if company_nm: params["companyNm"] = company_nm
    if sido:       params["sido"]      = sido
    if industry:   params["industry"]  = industry
    result = await _kosha_get("riskAssmt/getRiskAssmtAccdtInfo", params)
    return {"status": "success", "endpoint": "위험성평가 인정사업장", "data": result}


@router.get("/msds/sections")
async def msds_sections():
    return {"status": "success", "data": [{"section": k, "name": v} for k, v in MSDS_SECTIONS.items()]}


@router.get("/msds")
async def msds_list(
    chem_nm: Optional[str] = Query(None),
    cas_no:  Optional[str] = Query(None),
    page_no: int = Query(1, ge=1),
    num_of_rows: int = Query(10, ge=1, le=100),
):
    params: dict = {"pageNo": page_no, "numOfRows": num_of_rows}
    if chem_nm: params["chemNm"] = chem_nm
    if cas_no:  params["casNo"]  = cas_no
    result = await _kosha_get("msdschem/getChemList", params)
    return {"status": "success", "data": result}


@router.get("/msds/{kmc_no}/detail")
async def msds_detail(kmc_no: str, section: str = Query("01")):
    section = section.zfill(2)
    if section not in MSDS_SECTIONS:
        raise HTTPException(status_code=400, detail="section은 01~16 범위")
    result = await _kosha_get(f"msdschem/getChemDetail{section}", {"kmcNo": kmc_no})
    return {"status": "success", "kmc_no": kmc_no, "section": section,
            "section_name": MSDS_SECTIONS[section], "data": result}


@router.get("/kosha-guide")
async def kosha_guide(
    keyword:  Optional[str] = Query(None),
    guide_no: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    page_no:  int = Query(1, ge=1),
    num_of_rows: int = Query(10, ge=1, le=100),
):
    """
    KOSHA GUIDE API는 공공데이터포털에서 폐기 확인됨.
    대체: 안전보건법령 스마트검색(srch/smartSearch)으로 진행.
    """
    params: dict = {"pageNo": page_no, "numOfRows": num_of_rows, "returnType": "json"}
    # keyword 없으면 기본 검색어 사용
    params["keyword"] = keyword or (guide_no or "KOSHA GUIDE")
    result = await _kosha_get("srch/smartSearch", params)
    return {"status": "success", "note": "KOSHA GUIDE API 폐기, 대체: 안전보건법령 스마트검색", "data": result}
