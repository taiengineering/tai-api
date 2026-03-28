"""
행정안전부 안전정보 통합공개 조회 서비스 라우터 — v1.0.0
prefix: /safety-info

data.go.kr: 15073554
End Point: https://apis.data.go.kr/1741000/FcltsSafetyInfoService2025

주요 엔드포인트 (31종 시설안전정보 제공):
  GET /safety-info/facilities          시설물 기본정보 조회
  GET /safety-info/buildings            건축물 안전정보
  GET /safety-info/multi-use            다중이용시설 안전정보
  GET /safety-info/playground           어린이놀이시설
  GET /safety-info/childcare            어린이집
  GET /safety-info/hospital             병원시설
  GET /safety-info/hotel                호텔
  GET /safety-info/resort               휴양림
  GET /safety-info/types                제공 타입 목록
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import httpx
import os
import json
import xml.etree.ElementTree as ET

router = APIRouter(prefix="/safety-info", tags=["행안부안전정보"])

VERSION = "1.0.0"
SERVICE_KEY = os.getenv(
    "SAFETY_INFO_SERVICE_KEY",
    os.getenv("BUILDING_API_KEY", "da4e826323c2c9fef9f325bd4e39a3765d06ac1b582695bcbc475bc0a076255b")
)
SAFETY_BASE = "https://apis.data.go.kr/1741000/FcltsSafetyInfoService2025"

# 안전정보 타입 코드 맵
FACILITY_TYPES = {
    "facilities":     {"path": "/getFcltsInfoSearch_4",              "name": "시설물 기본정보"},
    "buildings":      {"path": "/getBuildSafetyInfoSearch_4",        "name": "건축물 안전정보"},
    "multi-use":      {"path": "/getMultiUseFacilitySafetyInfoSearch_4", "name": "다중이용시설 안전정보"},
    "playground":     {"path": "/getNlprkSafetyInfoSearch_4",         "name": "어린이놈이시설 안전정보"},
    "childcare":      {"path": "/getCrSafetyInfoSearch_4",            "name": "어린이집 안전정보"},
    "hospital":       {"path": "/getHospitalSafetyInfoSearch_4",      "name": "병원시설 인증정보"},
    "hotel":          {"path": "/getHotelSafetyInfoSearch_4",         "name": "호텔 안전정보"},
    "resort":         {"path": "/getRcrfctSafetyInfoSearch_4",        "name": "휴양림 안전정보"},
    "school":         {"path": "/getScleqipSafetyInfoSearch_4",       "name": "학교시설 안전정보"},
    "youth-training": {"path": "/getYouthTrainingSafetyInfoSearch_4", "name": "청소년수련시설 안전정보"},
    "amusement":      {"path": "/getAmuseSafetyInfoSearch_4",         "name": "유원시설 안전정보"},
    "performance":    {"path": "/getConcerthallSafetyInfoSearch_4",   "name": "공연장시설 안전정보"},
    "food":           {"path": "/getFoodfcltySafetyInfoSearch_4",     "name": "식품판매시설 안전정보"},
    "water-leisure":  {"path": "/getWaterLeisureSafetyInfoSearch_4",  "name": "수상레저시설 안전정보"},
    "harbor":         {"path": "/getHarborfcltySafetyInfoSearch_4",   "name": "항만시설 안전정보"},
    "hazmat":         {"path": "/getHlhsnSafetyInfoSearch_4",         "name": "유해화학물질취급시설 안전정보"},
    "traditional-market": {"path": "/getTrditMrktSafetyInfoSearch_4", "name": "전통시장 안전정보"},
    "long-term-care": {"path": "/getLongTermCareSafetyInfoSearch_4",  "name": "장기요양시설 안전정보"},
}


def _xml_to_dict(element) -> dict:
    """XML Element → dict 변환"""
    result = {}
    for child in element:
        tag = child.tag
        if len(child) > 0:
            result[tag] = _xml_to_dict(child)
        else:
            result[tag] = child.text or ""
    return result


async def _safety_get(path: str, params: dict) -> dict:
    """행안부 안전정보 API GET 공통 호출"""
    params["serviceKey"] = SERVICE_KEY
    params.setdefault("resultType", "json")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{SAFETY_BASE}{path}", params=params)
            resp.raise_for_status()
            text = resp.text

            # JSON 파싱 시도
            try:
                data = json.loads(text)
                if "response" in data:
                    return data["response"]
                return data
            except Exception:
                # XML fallback
                try:
                    root = ET.fromstring(text)
                    # items 추출
                    items_el = root.find(".//items")
                    items = []
                    if items_el is not None:
                        for item in items_el.findall("item"):
                            items.append(_xml_to_dict(item))
                    total = root.findtext(".//totalCount") or "0"
                    return {
                        "header": {
                            "resultCode": root.findtext(".//resultCode") or "00",
                            "resultMsg":  root.findtext(".//resultMsg") or ""
                        },
                        "body": {
                            "items":      {"item": items} if items else {},
                            "totalCount": int(total),
                            "pageNo":     int(root.findtext(".//pageNo") or 1),
                            "numOfRows":  int(root.findtext(".//numOfRows") or 10),
                        }
                    }
                except Exception:
                    return {"raw": text[:3000]}
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"행안부 안전정보 API 오류 {e.response.status_code}: {e.response.text[:200]}"
        )
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"행안부 API 연결 실패: {str(e)}")


# ─────────────────────────────────────────────────────
# GET /safety-info/types — 제공 타입 목록
# ─────────────────────────────────────────────────────
@router.get("/types")
def get_facility_types():
    """행안부 안전정보 API에서 제공하는 시설 타입 목록"""
    return {
        "status": "success",
        "data": [
            {"type": k, "name": v["name"], "endpoint": v["path"]}
            for k, v in FACILITY_TYPES.items()
        ]
    }


# ─────────────────────────────────────────────────────
# GET /safety-info/{facility_type} — 시설 타입별 안전정보
# facility_type: facilities, buildings, multi-use, playground, ...
# ─────────────────────────────────────────────────────
@router.get("/{facility_type}")
async def get_safety_info(
    facility_type: str,
    fclts_cd:    Optional[str] = Query(None, description="시설물 코드"),
    sido:        Optional[str] = Query(None, description="시도 (예: 서울특별시)"),
    sigungu:     Optional[str] = Query(None, description="시군구"),
    fclt_nm:     Optional[str] = Query(None, description="시설물명 검색"),
    page_no:     int = Query(1,  ge=1),
    num_of_rows: int = Query(10, ge=1, le=100),
):
    """
    행정안전부 안전정보 통합공개 조회.
    facility_type: facilities | buildings | multi-use | playground |
                   childcare | hospital | hotel | resort | school |
                   youth-training | amusement | performance | food |
                   water-leisure | harbor | hazmat | traditional-market |
                   long-term-care
    """
    if facility_type not in FACILITY_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"facility_type '{facility_type}' 지원되지 않습니다. "
                   f"/safety-info/types 에서 목록 확인하세요."
        )

    info = FACILITY_TYPES[facility_type]
    params: dict = {
        "pageNo":     page_no,
        "numOfRows":  num_of_rows,
        "resultType": "json",
    }
    if fclts_cd: params["fclts_cd"] = fclts_cd
    if sido:     params["sido"]     = sido
    if sigungu:  params["sigungu"]  = sigungu
    if fclt_nm:  params["fclt_nm"]  = fclt_nm

    result = await _safety_get(info["path"], params)
    return {
        "status":        "success",
        "facility_type": facility_type,
        "facility_name": info["name"],
        "data":          result,
    }
