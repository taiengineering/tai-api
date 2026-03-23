# routers/building_register.py v1.1.0
# 수정: body 빈문자열/null 방어, BUILDING_KEY 미설정 시 스킵,
#       get_juso try/except, /search data 필드 추가

from fastapi import APIRouter, HTTPException, Query
from datetime import datetime
from typing import Optional
import requests, urllib3, os
from supabase import create_client

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

router = APIRouter(tags=["building_register"])

SUPABASE_URL  = os.getenv("SUPABASE_URL")
SUPABASE_KEY  = os.getenv("SUPABASE_KEY")
JUSO_KEY      = os.environ.get("JUSO_API_KEY", "U01TX0FVVEgyMDI2MDMxODEyMjUxNjExNzc1MTc=")
BUILDING_KEY  = os.environ.get("BUILDING_API_KEY", "")
VERSION       = "1.1.0"

JUSO_URL      = "https://www.juso.go.kr/addrlink/addrLinkApi.do"
BUILDING_BASE = "https://apis.data.go.kr/1613000/BldRgstHubService"


def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def parse_bdmgtsn(bdmgtsn: str) -> dict:
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
    """도로명주소 → JUSO API → bdMgtSn. 실패 시 None 반환"""
    try:
        r = requests.get(JUSO_URL, params={
            "confmKey":     JUSO_KEY,
            "currentPage":  1,
            "countPerPage": 1,
            "keyword":      road_addr,
            "resultType":   "json"
        }, verify=False, timeout=10)
        data = r.json()
        results = data.get("results", {})
        juso = results.get("juso", [])
        if isinstance(juso, dict):
            juso = [juso]
        return juso[0] if juso else None
    except Exception as e:
        print(f"[JUSO ERROR] {e}")
        return None


def _building_get(endpoint: str, sigungu: str, bjdong: str, bun: str, ji: str, rows: int = 10) -> Optional[list]:
    """
    건축물대장 허브 API 공통 호출
    - BUILDING_KEY 미설정 → None
    - body 빈문자열/null → None
    - totalCount 정수 처리
    - items null/dict 정규화
    - 요청/파싱 실패 → None
    """
    if not BUILDING_KEY:
        print("[WARN] BUILDING_API_KEY not set — skipping hub call")
        return None

    try:
        r = requests.get(f"{BUILDING_BASE}/{endpoint}", params={
            "serviceKey": BUILDING_KEY,
            "sigunguCd":  sigungu,
            "bjdongCd":   bjdong,
            "bun":        bun,
            "ji":         ji,
            "numOfRows":  rows,
            "pageNo":     1,
            "_type":      "json"
        }, verify=False, timeout=10)
        data = r.json()
    except Exception as e:
        print(f"[BUILDING ERROR] {endpoint}: {e}")
        return None

    response = data.get("response") if isinstance(data, dict) else None
    if not isinstance(response, dict):
        return None

    body = response.get("body")
    if not isinstance(body, dict):
        return None

    try:
        total = int(body.get("totalCount", 0))
    except (TypeError, ValueError):
        total = 0

    if total == 0:
        return None

    items_wrap = body.get("items")
    if not isinstance(items_wrap, dict):
        return None

    items = items_wrap.get("item")
    if items is None:
        return None
    if isinstance(items, dict):
        items = [items]

    return items if items else None


def get_building_title(sigungu, bjdong, bun, ji="0000"):
    return _building_get("getBrTitleInfo", sigungu, bjdong, bun, ji)

def get_building_basis(sigungu, bjdong, bun, ji="0000"):
    return _building_get("getBrBasisOulnInfo", sigungu, bjdong, bun, ji)

def get_floor_outline(sigungu, bjdong, bun, ji="0000"):
    return _building_get("getBrFlrOulnInfo", sigungu, bjdong, bun, ji, rows=100)

def get_sewage_info(sigungu, bjdong, bun, ji="0000"):
    return _building_get("getBrExposPublcRqstInfo", sigungu, bjdong, bun, ji)


def fetch_all_building_data(bdmgtsn: str) -> dict:
    parsed = parse_bdmgtsn(bdmgtsn)
    if not parsed:
        return {}

    sigungu = parsed["sigunguCd"]
    bjdong  = parsed["bjdongCd"]
    bun     = parsed["bun"]
    ji      = parsed["ji"]

    result = {"bdmgtsn": bdmgtsn, "parsed": parsed}

    title = get_building_title(sigungu, bjdong, bun, ji)
    if not title:
        title = get_building_title(sigungu, bjdong, bun, "0000")
        if title:
            ji = "0000"
    result["title"]  = title
    result["basis"]  = get_building_basis(sigungu, bjdong, bun, ji)
    result["floors"] = get_floor_outline(sigungu, bjdong, bun, ji)
    result["sewage"] = get_sewage_info(sigungu, bjdong, bun, ji)
    return result


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


def build_factory_update(juso: dict, building_data: dict) -> dict:
    """건축물대장 데이터 → factories 업데이트 + 설문 자동채움 필드"""
    update = {"building_register_updated_at": datetime.now().isoformat()}

    if juso:
        update["bdmgtsn"] = juso.get("bdMgtSn", "")
        if juso.get("roadAddr"):   update["address_road"]    = juso.get("roadAddrPart1", "")
        if juso.get("jibunAddr"):  update["address_jibun"]   = juso.get("jibunAddr", "")
        if juso.get("zipNo"):      update["zipcode"]         = juso.get("zipNo", "")
        if juso.get("siNm"):       update["address_sido"]    = juso.get("siNm", "")
        if juso.get("sggNm"):      update["address_sigungu"] = juso.get("sggNm", "")
        if juso.get("emdNm"):      update["address_dong"]    = juso.get("emdNm", "")

    title_items = building_data.get("title", []) or []
    title = next((i for i in title_items if i.get("mainAtchGbCdNm") == "주건축물"), None)
    if not title and title_items:
        title = title_items[0]

    if title:
        update["mgm_bldrgst_pk"]           = title.get("mgmBldrgstPk")
        update["main_purpose_code"]        = title.get("mainPurpsCd")
        update["main_purpose_name"]        = title.get("mainPurpsCdNm", "").strip() or None
        update["etc_purpose"]              = title.get("etcPurps", "").strip() or None
        update["building_structure_code"]  = title.get("strctCd")
        update["building_structure_name"]  = title.get("strctCdNm", "").strip() or None
        update["roof_code"]                = title.get("roofCd")
        update["roof_name"]                = title.get("roofCdNm", "").strip() or None
        update["building_height"]          = _to_float(title.get("heit"))
        update["building_coverage_ratio"]  = _to_float(title.get("bcRat"))
        update["floor_area_ratio"]         = _to_float(title.get("vlRat"))
        update["arch_area"]                = _to_float(title.get("archArea"))
        update["ride_elevator_count"]      = _to_int(title.get("rideUseElvtCnt"))
        update["emergency_elevator_count"] = _to_int(title.get("emgenUseElvtCnt"))
        update["indoor_mech_parking_count"]= _to_int(title.get("indrMechUtcnt"))
        update["indoor_auto_parking_count"]= _to_int(title.get("indrAutoUtcnt"))
        update["indoor_auto_parking_area"] = _to_float(title.get("indrAutoArea"))
        update["use_approve_day"]          = title.get("useAprDay")
        update["permit_day"]               = title.get("pmsDay")
        update["construction_start_day"]   = title.get("stcnsDay")
        update["earthquake_design_applied"]= title.get("rserthqkDsgnApplyYn") == "1"

        # 설문 자동채움 표준 필드
        if _to_float(title.get("totArea")):    update["building_area"]           = _to_float(title.get("totArea"))
        if _to_float(title.get("platArea")):   update["land_area"]               = _to_float(title.get("platArea"))
        if _to_int(title.get("grndFlrCnt")):   update["floor_count"]             = _to_int(title.get("grndFlrCnt"))
        if _to_int(title.get("ugrndFlrCnt")): update["underground_floor_count"] = _to_int(title.get("ugrndFlrCnt"))
        if title.get("useAprDay") and len(title["useAprDay"]) >= 4:
            update["completion_year"] = int(title["useAprDay"][:4])
        if title.get("mainPurpsCdNm"):
            update["building_use_code"] = title.get("mainPurpsCdNm", "").strip()
        if _to_int(title.get("rideUseElvtCnt")):
            update["elevator_count"] = _to_int(title.get("rideUseElvtCnt"))

    basis_items = building_data.get("basis", []) or []
    if basis_items:
        b = basis_items[0]
        update["land_use_zone"]      = b.get("jiyukCdNm", "").strip() or None
        update["land_district_zone"] = b.get("jiguCdNm", "").strip() or None
        update["land_planning_zone"] = b.get("guyukCdNm", "").strip() or None

    floors = building_data.get("floors", [])
    if floors:
        update["floor_outline_json"] = [
            {"floor": f.get("flrNo"), "purpose": f.get("mainPurpsCdNm", "").strip(), "area": _to_float(f.get("area"))}
            for f in floors
        ]

    sewage = building_data.get("sewage", [])
    if sewage:
        s = sewage[0]
        update["sewage_facility_type"]     = s.get("etcPurps", "").strip() or s.get("mainPurpsCdNm", "").strip() or None
        update["sewage_facility_capacity"] = _to_float(s.get("capaPsper"))

    return {k: v for k, v in update.items() if v is not None}


# ============================================================
# 엔드포인트
# ============================================================

@router.get("/test")
def test():
    return {
        "message":      "Building Register API",
        "version":      VERSION,
        "building_key": "설정됨" if BUILDING_KEY else "미설정 (대장 조회 불가)",
        "juso_key":     "설정됨" if JUSO_KEY else "미설정",
    }


@router.get("/search")
def search_building(
    address: str  = Query(..., description="도로명주소"),
    save:    bool = Query(False)
):
    """
    주소 → 건축물대장 정보 조회
    응답 data 필드: 설문 pickBuildingRecordFromSearchJson 자동채움용
    (building_area, floor_count, main_purpose_name, completion_year 등)
    """
    juso = get_juso(address)
    if not juso:
        raise HTTPException(status_code=404, detail="주소를 찾을 수 없습니다")

    bdmgtsn = juso.get("bdMgtSn", "")
    if not bdmgtsn:
        raise HTTPException(status_code=404, detail="건물관리번호를 찾을 수 없습니다")

    building_data = fetch_all_building_data(bdmgtsn)

    title_items = building_data.get("title", []) or []
    title = next((i for i in title_items if i.get("mainAtchGbCdNm") == "주건축물"), None)
    if not title and title_items:
        title = title_items[0]

    summary = {}
    if title:
        summary = {
            "building_name":           title.get("bldNm", "").strip() or juso.get("bdNm", ""),
            "road_address":            title.get("newPlatPlc", ""),
            "total_area":              _to_float(title.get("totArea")),
            "land_area":               _to_float(title.get("platArea")),
            "arch_area":               _to_float(title.get("archArea")),
            "floor_count":             _to_int(title.get("grndFlrCnt")),
            "underground_floor_count": _to_int(title.get("ugrndFlrCnt")),
            "height":                  _to_float(title.get("heit")),
            "main_purpose":            title.get("mainPurpsCdNm", "").strip(),
            "structure":               title.get("strctCdNm", "").strip(),
            "use_approve_day":         title.get("useAprDay"),
            "elevator_count":          _to_int(title.get("rideUseElvtCnt")),
            "emergency_elevator_count":_to_int(title.get("emgenUseElvtCnt")),
            "earthquake_design":       title.get("rserthqkDsgnApplyYn") == "1",
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

    # 설문 자동채움용 data (build_factory_update 결과)
    data = build_factory_update(juso, building_data)

    return {
        "status":    "success",
        "bdmgtsn":   bdmgtsn,
        "juso":      juso,
        "summary":   summary,
        "zone_info": zone_info,
        "data":      data,
        "floor_count_from_floors": len(building_data.get("floors", []) or []),
        "has_sewage": bool(building_data.get("sewage")),
        "raw": {
            "title_count": len(title_items),
            "basis_count": len(basis_items),
            "floor_count": len(building_data.get("floors", []) or []),
        }
    }


@router.post("/apply/{factory_id}")
def apply_building_register(
    factory_id: str,
    address: Optional[str] = Query(None)
):
    supabase   = get_supabase()
    factory_res= supabase.table("factories").select("id,name,address_road,address_jibun,bdmgtsn").eq("id", factory_id).single().execute()

    if not factory_res.data:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다")

    factory    = factory_res.data
    query_addr = address or factory.get("address_road") or factory.get("address_jibun")
    if not query_addr:
        raise HTTPException(status_code=400, detail="주소가 없습니다")

    juso = get_juso(query_addr)
    if not juso:
        raise HTTPException(status_code=404, detail=f"주소를 찾을 수 없습니다: {query_addr}")

    bdmgtsn = juso.get("bdMgtSn", "")
    if not bdmgtsn:
        raise HTTPException(status_code=404, detail="건물관리번호를 찾을 수 없습니다")

    building_data = fetch_all_building_data(bdmgtsn)
    update_data   = build_factory_update(juso, building_data)

    if not update_data:
        return {"status": "warning", "message": "건축물대장에서 가져온 데이터가 없습니다", "bdmgtsn": bdmgtsn}

    supabase.table("factories").update(update_data).eq("id", factory_id).execute()

    return {
        "status":         "success",
        "factory_id":     factory_id,
        "factory_name":   factory.get("name"),
        "bdmgtsn":        bdmgtsn,
        "updated_fields": list(update_data.keys()),
        "updated_count":  len(update_data),
        "summary": {
            "building_area":   update_data.get("building_area"),
            "floor_count":     update_data.get("floor_count"),
            "completion_year": update_data.get("completion_year"),
            "main_purpose":    update_data.get("main_purpose_name"),
            "elevator_count":  update_data.get("elevator_count"),
            "structure":       update_data.get("building_structure_name"),
            "land_use_zone":   update_data.get("land_use_zone"),
        }
    }


@router.get("/floor/{factory_id}")
def get_factory_floor_outline(factory_id: str):
    supabase    = get_supabase()
    factory_res = supabase.table("factories").select("id,name,floor_outline_json,bdmgtsn").eq("id", factory_id).single().execute()

    if not factory_res.data:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다")

    factory    = factory_res.data
    floor_data = factory.get("floor_outline_json")

    if not floor_data:
        return {"status": "warning", "message": "층별개요 없음. POST /apply 먼저 실행", "factory_id": factory_id}

    return {"status": "success", "factory_id": factory_id, "factory_name": factory.get("name"), "floor_count": len(floor_data), "floors": floor_data}
