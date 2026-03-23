# routers/building_register.py v1.2.0
# 각 단계 try/except + print 로그 추가 — Railway 로그에서 500 원인 확인용

from fastapi import APIRouter, HTTPException, Query
from datetime import datetime
from typing import Optional
import requests, urllib3, os, traceback
from supabase import create_client

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

router = APIRouter(tags=["building_register"])

SUPABASE_URL  = os.getenv("SUPABASE_URL")
SUPABASE_KEY  = os.getenv("SUPABASE_KEY")
JUSO_KEY      = os.environ.get("JUSO_API_KEY", "U01TX0FVVEgyMDI2MDMxODEyMjUxNjExNzc1MTc=")
BUILDING_KEY  = os.environ.get("BUILDING_API_KEY", "")
VERSION       = "1.2.0"

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
    """[STAGE 1] 도로명주소 → JUSO API → bdMgtSn"""
    print(f"[JUSO] 요청 주소: {road_addr}")
    try:
        r = requests.get(JUSO_URL, params={
            "confmKey":     JUSO_KEY,
            "currentPage":  1,
            "countPerPage": 1,
            "keyword":      road_addr,
            "resultType":   "json"
        }, verify=False, timeout=10)
        print(f"[JUSO] HTTP {r.status_code}")
        data = r.json()
        results = data.get("results", {})
        common = results.get("common", {})
        print(f"[JUSO] errorCode={common.get('errorCode')}, totalCount={common.get('totalCount')}")
        juso = results.get("juso", [])
        if isinstance(juso, dict):
            juso = [juso]
        if not juso:
            print("[JUSO] 결과 없음")
            return None
        first = juso[0]
        print(f"[JUSO] bdMgtSn={first.get('bdMgtSn')} roadAddr={first.get('roadAddr')}")
        return first
    except Exception as e:
        print(f"[JUSO ERROR] {e}\n{traceback.format_exc()}")
        return None


def _building_get(endpoint: str, sigungu: str, bjdong: str, bun: str, ji: str, rows: int = 10) -> Optional[list]:
    """[STAGE 2] 건축물대장 허브 API 공통 호출"""
    if not BUILDING_KEY:
        print(f"[BUILDING] BUILDING_API_KEY 미설정 — {endpoint} 스킵")
        return None
    try:
        url = f"{BUILDING_BASE}/{endpoint}"
        params = {
            "serviceKey": BUILDING_KEY,
            "sigunguCd":  sigungu,
            "bjdongCd":   bjdong,
            "bun":        bun,
            "ji":         ji,
            "numOfRows":  rows,
            "pageNo":     1,
            "_type":      "json"
        }
        print(f"[BUILDING] {endpoint} sigungu={sigungu} bjdong={bjdong} bun={bun} ji={ji}")
        r = requests.get(url, params=params, verify=False, timeout=10)
        print(f"[BUILDING] {endpoint} HTTP {r.status_code}")

        try:
            data = r.json()
        except Exception as je:
            print(f"[BUILDING] {endpoint} JSON 파싱 실패: {je} / 응답: {r.text[:200]}")
            return None

        response = data.get("response") if isinstance(data, dict) else None
        if not isinstance(response, dict):
            print(f"[BUILDING] {endpoint} response가 dict 아님: {type(response)}")
            return None

        body = response.get("body")
        if not isinstance(body, dict):
            print(f"[BUILDING] {endpoint} body가 dict 아님: {type(body)} / 값: {str(body)[:100]}")
            return None

        header = response.get("header", {})
        print(f"[BUILDING] {endpoint} resultCode={header.get('resultCode')} resultMsg={header.get('resultMsg')}")

        try:
            total = int(body.get("totalCount", 0))
        except (TypeError, ValueError):
            total = 0
        print(f"[BUILDING] {endpoint} totalCount={total}")

        if total == 0:
            return None

        items_wrap = body.get("items")
        if not isinstance(items_wrap, dict):
            print(f"[BUILDING] {endpoint} items가 dict 아님: {type(items_wrap)}")
            return None

        items = items_wrap.get("item")
        if items is None:
            print(f"[BUILDING] {endpoint} item이 None")
            return None
        if isinstance(items, dict):
            items = [items]

        print(f"[BUILDING] {endpoint} 결과 {len(items)}건")
        return items if items else None

    except Exception as e:
        print(f"[BUILDING ERROR] {endpoint}: {e}\n{traceback.format_exc()}")
        return None


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
    result  = {"bdmgtsn": bdmgtsn, "parsed": parsed}

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
        if _to_float(title.get("totArea")):   update["building_area"]           = _to_float(title.get("totArea"))
        if _to_float(title.get("platArea")):  update["land_area"]               = _to_float(title.get("platArea"))
        if _to_int(title.get("grndFlrCnt")):  update["floor_count"]             = _to_int(title.get("grndFlrCnt"))
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
        "building_key": "설정됨" if BUILDING_KEY else "미설정",
        "juso_key":     "설정됨" if JUSO_KEY else "미설정",
    }


@router.get("/search")
def search_building(
    address: str  = Query(..., description="도로명주소"),
    save:    bool = Query(False)
):
    print(f"\n{'='*50}")
    print(f"[SEARCH] 시작 address={address}")

    # STAGE 1 — JUSO
    try:
        juso = get_juso(address)
    except Exception as e:
        print(f"[SEARCH] STAGE1 예외: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"JUSO 조회 오류: {str(e)}")

    if not juso:
        raise HTTPException(status_code=404, detail="주소를 찾을 수 없습니다")

    bdmgtsn = juso.get("bdMgtSn", "")
    print(f"[SEARCH] STAGE1 완료 bdmgtsn={bdmgtsn}")

    if not bdmgtsn:
        raise HTTPException(status_code=404, detail="건물관리번호를 찾을 수 없습니다")

    # STAGE 2 — 건축물대장
    try:
        building_data = fetch_all_building_data(bdmgtsn)
        print(f"[SEARCH] STAGE2 완료 title={len(building_data.get('title') or [])}건")
    except Exception as e:
        print(f"[SEARCH] STAGE2 예외: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"건축물대장 조회 오류: {str(e)}")

    # STAGE 3 — 응답 JSON 조립
    try:
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

        data = build_factory_update(juso, building_data)
        print(f"[SEARCH] STAGE3 완료 data_keys={list(data.keys())[:5]}")

    except Exception as e:
        print(f"[SEARCH] STAGE3 예외: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"응답 조립 오류: {str(e)}")

    print(f"[SEARCH] 완료\n{'='*50}")
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
    supabase    = get_supabase()
    factory_res = supabase.table("factories").select("id,name,address_road,address_jibun,bdmgtsn").eq("id", factory_id).single().execute()
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
