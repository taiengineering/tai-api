# routers/building_register.py
# 건축물대장 API 라우터
# - GET  /building-register/search?address=    주소 → 건축물 정보 조회 (저장 안함)
# - POST /building-register/apply/{factory_id} 건축물 정보 → factories 자동 채움
# - GET  /building-register/floor/{factory_id} 층별개요 조회
# - GET  /building-register/test               버전 확인

from fastapi import APIRouter, HTTPException, Query
from db.supabase_client import get_supabase
from datetime import datetime
from typing import Optional, Any, List
import requests
import urllib3
import os

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

router = APIRouter(tags=["building_register"])

JUSO_KEY     = os.environ.get("JUSO_API_KEY", "U01TX0FVVEgyMDI2MDMxODEyMjUxNjExNzc1MTc=")
BUILDING_KEY = os.environ.get("BUILDING_API_KEY", "")
VERSION      = "1.0.0"

JUSO_URL     = "https://www.juso.go.kr/addrlink/addrLinkApi.do"
BUILDING_BASE = "https://apis.data.go.kr/1613000/BldRgstHubService"


# ============================================================
# 헬퍼 함수
# ============================================================

def parse_bdmgtsn(bdmgtsn: str) -> dict:
    """
    bdMgtSn 25자리 파싱
    [0:5]  시군구코드
    [5:10] 법정동코드
    [10]   산여부 (0:일반, 1:산)
    [11:15] 번 (4자리)
    [15:19] 지 (4자리)
    [19:25] 일련번호
    """
    if not bdmgtsn or len(bdmgtsn) < 19:
        return {}
    return {
        "sigunguCd": bdmgtsn[0:5],
        "bjdongCd":  bdmgtsn[5:10],
        "mountain":  bdmgtsn[10],
        "bun":       bdmgtsn[11:15],
        "ji":        bdmgtsn[15:19],
    }


def get_juso(road_addr: str) -> Optional[dict]:
    """도로명주소 → JUSO API → bdMgtSn"""
    try:
        r = requests.get(JUSO_URL, params={
            "confmKey":     JUSO_KEY,
            "currentPage":  1,
            "countPerPage": 1,
            "keyword":      road_addr,
            "resultType":   "json"
        }, verify=False, timeout=10)
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    results = data.get("results")
    if not isinstance(results, dict):
        return None
    juso = results.get("juso")
    if isinstance(juso, dict):
        return juso
    if isinstance(juso, list) and juso:
        return juso[0]
    return None


def _building_get(endpoint: str, sigungu: str, bjdong: str, bun: str, ji: str, rows: int = 10) -> Optional[List[dict]]:
    """
    건축물대장 API 공통 호출.
    공공데이터포털은 건축물이 없거나 오류 시 body 가 빈 문자열("")이거나,
    items 가 null 인 경우가 있어 기존 코드에서 AttributeError → 500 이 났음.
    """
    if not (BUILDING_KEY and str(BUILDING_KEY).strip()):
        return None
    try:
        r = requests.get(
            f"{BUILDING_BASE}/{endpoint}",
            params={
                "serviceKey": BUILDING_KEY,
                "sigunguCd":  sigungu,
                "bjdongCd":   bjdong,
                "bun":        bun,
                "ji":         ji,
                "numOfRows":  rows,
                "pageNo":     1,
                "_type":      "json",
            },
            verify=False,
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError, TypeError):
        return None

    if not isinstance(data, dict):
        return None
    resp = data.get("response")
    if not isinstance(resp, dict):
        return None

    header = resp.get("header")
    if isinstance(header, dict):
        rc = str(header.get("resultCode", "00"))
        if rc not in ("00", "0"):
            return None

    body = resp.get("body")
    # 결과 없음/오류 시 body 가 dict 가 아닌 경우가 많음
    if not isinstance(body, dict):
        return None

    try:
        total = int(str(body.get("totalCount", "0")))
    except (TypeError, ValueError):
        total = 0
    if total == 0:
        return None

    items_wrap = body.get("items")
    if not isinstance(items_wrap, dict):
        return None
    items: Any = items_wrap.get("item")
    if items is None:
        return None
    if isinstance(items, dict):
        return [items]
    if isinstance(items, list):
        return items
    return None


def get_building_title(sigungu: str, bjdong: str, bun: str, ji: str = "0000") -> Optional[list]:
    return _building_get("getBrTitleInfo", sigungu, bjdong, bun, ji)


def get_building_basis(sigungu: str, bjdong: str, bun: str, ji: str = "0000") -> Optional[list]:
    return _building_get("getBrBasisOulnInfo", sigungu, bjdong, bun, ji)


def get_floor_outline(sigungu: str, bjdong: str, bun: str, ji: str = "0000") -> Optional[list]:
    return _building_get("getBrFlrOulnInfo", sigungu, bjdong, bun, ji, rows=100)


def get_sewage_info(sigungu: str, bjdong: str, bun: str, ji: str = "0000") -> Optional[list]:
    return _building_get("getBrExposPublcRqstInfo", sigungu, bjdong, bun, ji)


def fetch_all_building_data(bdmgtsn: str) -> dict:
    """bdMgtSn 기반 전체 건축물대장 정보 수집"""
    parsed = parse_bdmgtsn(bdmgtsn)
    if not parsed:
        return {}

    sigungu = parsed["sigunguCd"]
    bjdong  = parsed["bjdongCd"]
    bun     = parsed["bun"]
    ji      = parsed["ji"]

    result = {"bdmgtsn": bdmgtsn, "parsed": parsed}

    # 1. 표제부 (ji 원본 → ji=0000 fallback)
    title = get_building_title(sigungu, bjdong, bun, ji)
    if not title:
        title = get_building_title(sigungu, bjdong, bun, "0000")
        if title:
            ji = "0000"  # 이후 조회에도 0000 사용
    result["title"] = title

    # 2. 기본개요 (지역지구구역)
    basis = get_building_basis(sigungu, bjdong, bun, ji)
    result["basis"] = basis

    # 3. 층별개요
    floors = get_floor_outline(sigungu, bjdong, bun, ji)
    result["floors"] = floors

    # 4. 오수정화시설
    sewage = get_sewage_info(sigungu, bjdong, bun, ji)
    result["sewage"] = sewage

    return result


def build_factory_update(juso: dict, building_data: dict) -> dict:
    """건축물대장 데이터 → factories 업데이트 딕셔너리 생성"""
    update = {
        "building_register_updated_at": datetime.now().isoformat()
    }

    # JUSO 기본 정보
    if juso:
        bdmgtsn = juso.get("bdMgtSn", "")
        update["bdmgtsn"] = bdmgtsn

        # 도로명 주소 (기존 값이 없을 때만)
        if juso.get("roadAddr"):
            update["address_road"] = juso.get("roadAddrPart1", "")
        if juso.get("jibunAddr"):
            update["address_jibun"] = juso.get("jibunAddr", "")
        if juso.get("zipNo"):
            update["zipcode"] = juso.get("zipNo", "")
        if juso.get("siNm"):
            update["address_sido"] = juso.get("siNm", "")
        if juso.get("sggNm"):
            update["address_sigungu"] = juso.get("sggNm", "")
        if juso.get("emdNm"):
            update["address_dong"] = juso.get("emdNm", "")

    # 표제부 — 주건축물 우선 선택
    title_items = building_data.get("title", []) or []
    title = None
    for item in title_items:
        if item.get("mainAtchGbCdNm") == "주건축물":
            title = item
            break
    if not title and title_items:
        title = title_items[0]

    if title:
        update["mgm_bldrgst_pk"]         = title.get("mgmBldrgstPk")
        update["main_purpose_code"]       = title.get("mainPurpsCd")
        update["main_purpose_name"]       = title.get("mainPurpsCdNm", "").strip() or None
        update["etc_purpose"]             = title.get("etcPurps", "").strip() or None
        update["building_structure_code"] = title.get("strctCd")
        update["building_structure_name"] = title.get("strctCdNm", "").strip() or None
        update["roof_code"]               = title.get("roofCd")
        update["roof_name"]               = title.get("roofCdNm", "").strip() or None
        update["building_height"]         = _to_float(title.get("heit"))
        update["building_coverage_ratio"] = _to_float(title.get("bcRat"))
        update["floor_area_ratio"]        = _to_float(title.get("vlRat"))
        update["arch_area"]               = _to_float(title.get("archArea"))
        update["ride_elevator_count"]     = _to_int(title.get("rideUseElvtCnt"))
        update["emergency_elevator_count"]= _to_int(title.get("emgenUseElvtCnt"))
        update["indoor_mech_parking_count"]= _to_int(title.get("indrMechUtcnt"))
        update["indoor_auto_parking_count"]= _to_int(title.get("indrAutoUtcnt"))
        update["indoor_auto_parking_area"] = _to_float(title.get("indrAutoArea"))
        update["use_approve_day"]          = title.get("useAprDay")
        update["permit_day"]               = title.get("pmsDay")
        update["construction_start_day"]   = title.get("stcnsDay")
        update["earthquake_design_applied"]= title.get("rserthqkDsgnApplyYn") == "1"

        # factories 기본 컬럼도 채움
        if _to_float(title.get("totArea")):
            update["building_area"] = _to_float(title.get("totArea"))
        if _to_float(title.get("platArea")):
            update["land_area"] = _to_float(title.get("platArea"))
        if _to_int(title.get("grndFlrCnt")):
            update["floor_count"] = _to_int(title.get("grndFlrCnt"))
        if _to_int(title.get("ugrndFlrCnt")):
            update["underground_floor_count"] = _to_int(title.get("ugrndFlrCnt"))
        if title.get("useAprDay") and len(title["useAprDay"]) >= 4:
            update["completion_year"] = int(title["useAprDay"][:4])
        if title.get("mainPurpsCdNm"):
            update["building_use_code"] = title.get("mainPurpsCdNm", "").strip()
        # 승강기 수
        if _to_int(title.get("rideUseElvtCnt")):
            update["elevator_count"] = _to_int(title.get("rideUseElvtCnt"))

    # 기본개요 — 지역지구구역
    basis_items = building_data.get("basis", []) or []
    if basis_items:
        b = basis_items[0]
        update["land_use_zone"]      = b.get("jiyukCdNm", "").strip() or None
        update["land_district_zone"] = b.get("jiguCdNm", "").strip() or None
        update["land_planning_zone"] = b.get("guyukCdNm", "").strip() or None

    # 층별개요 JSON
    floors = building_data.get("floors", [])
    if floors:
        update["floor_outline_json"] = [
            {
                "floor":   f.get("flrNo"),
                "purpose": f.get("mainPurpsCdNm", "").strip(),
                "area":    _to_float(f.get("area")),
            }
            for f in floors
        ]

    # 오수정화시설
    sewage = building_data.get("sewage", [])
    if sewage:
        s = sewage[0]
        update["sewage_facility_type"]     = s.get("etcPurps", "").strip() or s.get("mainPurpsCdNm", "").strip() or None
        update["sewage_facility_capacity"] = _to_float(s.get("capaPsper"))

    # None 값 제거
    return {k: v for k, v in update.items() if v is not None}


def _to_float(v) -> Optional[float]:
    try:
        f = float(v)
        return f if f != 0 else None
    except (TypeError, ValueError):
        return None


def _to_int(v) -> Optional[int]:
    try:
        i = int(v)
        return i if i != 0 else None
    except (TypeError, ValueError):
        return None


# ============================================================
# 엔드포인트
# ============================================================

@router.get("/test")
def test():
    return {"message": "Building Register API", "version": VERSION}


@router.get("/search")
def search_building(
    address: str = Query(..., description="도로명주소"),
    save: bool  = Query(False, description="True이면 factory_id와 함께 저장")
):
    """
    주소 입력 → 건축물대장 전체 정보 조회 (미리보기용)
    저장하지 않음 — 저장은 POST /apply/{factory_id} 사용
    """
    # JUSO 조회
    juso = get_juso(address)
    if not juso:
        raise HTTPException(status_code=404, detail="주소를 찾을 수 없습니다")

    bdmgtsn = juso.get("bdMgtSn", "")
    if not bdmgtsn:
        raise HTTPException(status_code=404, detail="건물관리번호를 찾을 수 없습니다")

    # 건축물대장 전체 조회
    building_data = fetch_all_building_data(bdmgtsn)

    # 설문/프론트 자동입력용 — factories 컬럼명과 동일한 키 (json.data)
    data_preview = build_factory_update(juso, building_data)

    # 요약 생성
    title_items = building_data.get("title", []) or []
    title = None
    for item in title_items:
        if item.get("mainAtchGbCdNm") == "주건축물":
            title = item
            break
    if not title and title_items:
        title = title_items[0]

    summary = {}
    if title:
        summary = {
            "building_name":   title.get("bldNm", "").strip() or juso.get("bdNm", ""),
            "road_address":    title.get("newPlatPlc", ""),
            "total_area":      _to_float(title.get("totArea")),
            "land_area":       _to_float(title.get("platArea")),
            "arch_area":       _to_float(title.get("archArea")),
            "floor_count":     _to_int(title.get("grndFlrCnt")),
            "underground_floor_count": _to_int(title.get("ugrndFlrCnt")),
            "height":          _to_float(title.get("heit")),
            "main_purpose":    title.get("mainPurpsCdNm", "").strip(),
            "structure":       title.get("strctCdNm", "").strip(),
            "use_approve_day": title.get("useAprDay"),
            "elevator_count":  _to_int(title.get("rideUseElvtCnt")),
            "emergency_elevator_count": _to_int(title.get("emgenUseElvtCnt")),
            "earthquake_design": title.get("rserthqkDsgnApplyYn") == "1",
        }

    basis_items = building_data.get("basis", []) or []
    zone_info = {}
    if basis_items:
        b = basis_items[0]
        zone_info = {
            "land_use_zone":      b.get("jiyukCdNm", "").strip(),
            "land_district_zone": b.get("jiguCdNm", "").strip(),
            "land_planning_zone": b.get("guyukCdNm", "").strip(),
        }

    return {
        "status":      "success",
        "bdmgtsn":     bdmgtsn,
        "juso":        juso,
        "data":        data_preview,
        "summary":     summary,
        "zone_info":   zone_info,
        "floor_count_from_floors": len(building_data.get("floors", []) or []),
        "has_sewage":  bool(building_data.get("sewage")),
        "raw": {
            "title_count":  len(title_items),
            "basis_count":  len(basis_items),
            "floor_count":  len(building_data.get("floors", []) or []),
        }
    }


@router.post("/apply/{factory_id}")
def apply_building_register(
    factory_id: str,
    address: Optional[str] = Query(None, description="직접 주소 입력 (없으면 factories.address_road 사용)")
):
    """
    건축물대장 정보를 조회하여 factories 테이블에 자동으로 저장
    - 기존에 입력된 값은 유지하고 건축물대장 데이터로 보완
    - 연면적, 층수, 승강기, 사용승인일, 주용도, 구조, 지역지구구역 등 전체 저장
    """
    supabase = get_supabase()

    # factory 조회
    factory_res = supabase.table("factories")\
        .select("id, name, address_road, address_jibun, bdmgtsn")\
        .eq("id", factory_id)\
        .single().execute()

    if not factory_res.data:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다")

    factory = factory_res.data

    # 주소 결정
    query_addr = address or factory.get("address_road") or factory.get("address_jibun")
    if not query_addr:
        raise HTTPException(status_code=400, detail="주소가 없습니다. address 파라미터를 입력해주세요")

    # JUSO 조회
    juso = get_juso(query_addr)
    if not juso:
        raise HTTPException(status_code=404, detail=f"주소를 찾을 수 없습니다: {query_addr}")

    bdmgtsn = juso.get("bdMgtSn", "")
    if not bdmgtsn:
        raise HTTPException(status_code=404, detail="건물관리번호를 찾을 수 없습니다")

    # 건축물대장 전체 조회
    building_data = fetch_all_building_data(bdmgtsn)

    # factories 업데이트 딕셔너리 생성
    update_data = build_factory_update(juso, building_data)

    if not update_data:
        return {
            "status":  "warning",
            "message": "건축물대장에서 가져온 데이터가 없습니다",
            "bdmgtsn": bdmgtsn,
        }

    # DB 업데이트
    supabase.table("factories")\
        .update(update_data)\
        .eq("id", factory_id)\
        .execute()

    return {
        "status":        "success",
        "factory_id":    factory_id,
        "factory_name":  factory.get("name"),
        "bdmgtsn":       bdmgtsn,
        "updated_fields": list(update_data.keys()),
        "updated_count":  len(update_data),
        "summary": {
            "building_area":    update_data.get("building_area"),
            "floor_count":      update_data.get("floor_count"),
            "completion_year":  update_data.get("completion_year"),
            "main_purpose":     update_data.get("main_purpose_name"),
            "elevator_count":   update_data.get("elevator_count"),
            "structure":        update_data.get("building_structure_name"),
            "land_use_zone":    update_data.get("land_use_zone"),
        }
    }


@router.get("/floor/{factory_id}")
def get_factory_floor_outline(factory_id: str):
    """시설의 층별개요 조회"""
    supabase = get_supabase()

    factory_res = supabase.table("factories")\
        .select("id, name, floor_outline_json, bdmgtsn")\
        .eq("id", factory_id)\
        .single().execute()

    if not factory_res.data:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다")

    factory = factory_res.data
    floor_data = factory.get("floor_outline_json")

    if not floor_data:
        return {
            "status":  "warning",
            "message": "층별개요 데이터가 없습니다. POST /building-register/apply/{factory_id} 먼저 실행하세요",
            "factory_id": factory_id,
        }

    return {
        "status":      "success",
        "factory_id":  factory_id,
        "factory_name": factory.get("name"),
        "floor_count": len(floor_data),
        "floors":      floor_data,
    }
