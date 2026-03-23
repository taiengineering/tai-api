# routers/building_register.py v1.5.0
# 지번주소 → 도로명주소 자동 변환 + Connection reset 재시도

from fastapi import APIRouter, HTTPException, Query
from datetime import datetime
from typing import Optional, Any, List
import asyncio
import re
import requests, urllib3, os, traceback, time
from supabase import create_client

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

router = APIRouter(tags=["building_register"])

SUPABASE_URL  = os.getenv("SUPABASE_URL")
SUPABASE_KEY  = os.getenv("SUPABASE_KEY")
JUSO_KEY      = os.environ.get("JUSO_API_KEY", "U01TX0FVVEgyMDI2MDMxODEyMjUxNjExNzc1MTc=")
BUILDING_KEY  = os.environ.get("BUILDING_API_KEY", "")
VERSION       = "1.5.0"

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


def _safe_int(val: Any) -> Optional[int]:
    try:
        return int(val) if val not in (None, "", "null") else None
    except (TypeError, ValueError):
        return None


def _safe_float(val: Any) -> Optional[float]:
    try:
        return float(val) if val not in (None, "", "null") else None
    except (TypeError, ValueError):
        return None


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
# JUSO API — 지번/도로명 모두 처리
# ============================================================

def _juso_call_once(keyword: str) -> Optional[dict]:
    """JUSO API 단일 호출 (재시도 포함). 첫 결과 반환"""
    last_err = None
    for attempt in range(3):
        try:
            r = requests.get(JUSO_URL, params={
                "confmKey":     JUSO_KEY,
                "currentPage":  1,
                "countPerPage": 1,
                "keyword":      keyword,
                "resultType":   "json",
            }, verify=False, timeout=15)
            r.raise_for_status()
            data = r.json()

            if not isinstance(data, dict):
                return None

            results = data.get("results", {})
            if not isinstance(results, dict):
                return None

            common = results.get("common", {})
            error_code = common.get("errorCode", "0")
            if error_code != "0":
                print(f"[JUSO] 오류코드={error_code} keyword={keyword[:20]}")
                return None

            total = int(common.get("totalCount", 0) or 0)
            print(f"[JUSO] keyword={keyword[:30]} totalCount={total}")

            juso = results.get("juso", [])
            if isinstance(juso, dict):
                juso = [juso]
            return juso[0] if juso else None

        except (requests.exceptions.ConnectionError,
                requests.exceptions.ChunkedEncodingError) as e:
            last_err = e
            wait = attempt + 1
            print(f"[JUSO-RETRY] {attempt+1}/3 — {wait}초 대기: {e}")
            time.sleep(wait)
            continue
        except Exception as e:
            print(f"[JUSO ERROR] {e}")
            return None

    print(f"[JUSO ERROR] 3회 실패: {last_err}")
    return None


def _get_juso_info_sync(address: str) -> Optional[dict]:
    """
    지번주소 · 도로명주소 모두 처리
    1단계: 입력 주소로 검색
    2단계: roadAddr 있으면 도로명으로 재검색 (더 정확한 bdMgtSn)
    3단계: 둘 다 실패 시 jibunAddr로 재검색
    """
    print(f"[JUSO] 검색 시작: {address}")

    # 1단계
    result = _juso_call_once(address)

    if not result:
        print(f"[JUSO] 1단계 결과 없음")
        return None

    road_addr  = (result.get("roadAddr") or "").strip()
    jibun_addr = (result.get("jibunAddr") or "").strip()
    bdmgtsn    = (result.get("bdMgtSn") or "").strip()

    print(f"[JUSO] 1단계 결과 bdMgtSn={bdmgtsn} roadAddr={road_addr}")

    # bdMgtSn이 있으면 바로 반환
    if bdmgtsn:
        # 2단계: 도로명으로 재검색해서 더 정확한 결과 시도
        if road_addr and road_addr != address.strip():
            road_result = _juso_call_once(road_addr)
            if road_result and road_result.get("bdMgtSn"):
                print(f"[JUSO] 2단계 도로명 재검색 성공 bdMgtSn={road_result.get('bdMgtSn')}")
                return road_result
        return result

    # bdMgtSn 없는 경우
    # 3단계: 지번주소로 재검색
    if jibun_addr and jibun_addr != address.strip():
        print(f"[JUSO] 3단계 지번주소로 재검색: {jibun_addr}")
        jibun_result = _juso_call_once(jibun_addr)
        if jibun_result and jibun_result.get("bdMgtSn"):
            return jibun_result

    # 4단계: 도로명으로 재검색
    if road_addr and road_addr != address.strip():
        print(f"[JUSO] 4단계 도로명으로 재검색: {road_addr}")
        road_result = _juso_call_once(road_addr)
        if road_result and road_result.get("bdMgtSn"):
            return road_result

    # 그래도 없으면 원래 결과 반환 (bdMgtSn 없어도)
    return result if result else None


def get_juso(address: str) -> Optional[dict]:
    """동기 JUSO 호출 (apply 엔드포인트용)"""
    return _get_juso_info_sync(address)


async def get_juso_info(road_addr: str) -> Optional[dict]:
    return await asyncio.to_thread(_get_juso_info_sync, road_addr)


# ============================================================
# 건축물대장 API
# ============================================================

def _building_get(endpoint: str, sigungu: str, bjdong: str, bun: str, ji: str, rows: int = 10) -> Optional[list]:
    if not BUILDING_KEY:
        print(f"[BUILDING] BUILDING_API_KEY 미설정 — {endpoint} 스킵")
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
        print(f"[BUILDING] {endpoint} HTTP {r.status_code}")

        try:
            data = r.json()
        except Exception as je:
            print(f"[BUILDING] JSON 파싱 실패: {je}")
            return None

        response = data.get("response") if isinstance(data, dict) else None
        if not isinstance(response, dict):
            return None

        body = response.get("body")
        if not isinstance(body, dict):
            print(f"[BUILDING] body 이상: {type(body)} {str(body)[:50]}")
            return None

        header = response.get("header", {})
        print(f"[BUILDING] {endpoint} resultCode={header.get('resultCode')}")

        try:
            total = int(body.get("totalCount", 0))
        except (TypeError, ValueError):
            total = 0
        print(f"[BUILDING] {endpoint} totalCount={total}")

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


def _get_br_title_info_sync(bdmgtsn: str) -> Optional[List[dict]]:
    parsed = parse_bdmgtsn(bdmgtsn)
    if not parsed:
        return None
    sigungu = parsed["sigunguCd"]
    bjdong  = parsed["bjdongCd"]
    bun     = parsed["bun"]
    ji      = parsed["ji"]
    title = get_building_title(sigungu, bjdong, bun, ji)
    if not title:
        title = get_building_title(sigungu, bjdong, bun, "0000")
    return title


async def get_br_title_info(bdmgtsn: str) -> Optional[List[dict]]:
    return await asyncio.to_thread(_get_br_title_info_sync, bdmgtsn)


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
        "building_key": "설정됨" if BUILDING_KEY else "미설정",
        "juso_key":     "설정됨" if JUSO_KEY else "미설정",
    }


@router.get("/search")
async def search_building(
    address: str  = Query(..., description="도로명 또는 지번 주소"),
    save:    bool = Query(False)
):
    """
    주소(도로명 또는 지번) → 건축물대장 정보 조회
    지번 입력 시 도로명으로 자동 변환 후 조회
    """
    print(f"[BUILD-1] 주소 검색: {address}")

    # STAGE 1 — JUSO (지번→도로명 자동 변환 포함)
    try:
        juso_data = await get_juso_info(address)
        print(f"[BUILD-2] JUSO 결과: {juso_data}")
    except Exception as e:
        print(f"[BUILD-ERR-JUSO] {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"주소 API 오류: {str(e)}")

    if not juso_data:
        raise HTTPException(status_code=404, detail="주소를 찾을 수 없습니다. 도로명 또는 지번 주소를 더 정확하게 입력해주세요.")

    bdmgtsn = (
        juso_data.get("bdMgtSn") or
        juso_data.get("bdmgtsn") or ""
    ).strip()
    print(f"[BUILD-3] bdMgtSn: {bdmgtsn}")

    if not bdmgtsn:
        raise HTTPException(status_code=404, detail="건물관리번호(bdMgtSn)를 찾을 수 없습니다. 건물 주소를 입력해주세요.")

    # STAGE 2 — 건축물대장 표제부
    try:
        title_data = await get_br_title_info(bdmgtsn)
        print(f"[BUILD-4] 표제부 건수: {len(title_data) if title_data else 0}")
    except Exception as e:
        print(f"[BUILD-ERR-TITLE] {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"건축물대장 API 오류: {str(e)}")

    if isinstance(title_data, list):
        title = next((i for i in title_data if i.get("mainAtchGbCdNm") == "주건축물"), None)
        if not title and title_data:
            title = title_data[0]
        elif not title:
            title = {}
    elif isinstance(title_data, dict):
        items = title_data.get("items") or title_data.get("data") or []
        title = items[0] if items else title_data
    else:
        title = {}

    print(f"[BUILD-5] 표제부 파싱 완료")

    # STAGE 3 — 응답 직렬화
    try:
        use_approve_day = str(title.get("useAprDay") or title.get("use_approve_day") or "")
        completion_year = int(use_approve_day[:4]) if len(use_approve_day) >= 4 else None
        mp = title.get("mainPurpsCdNm") or title.get("main_purpose_name") or ""
        main_purpose_name = mp.strip() if isinstance(mp, str) else str(mp or "")

        result = {
            "status": "success",
            "data": {
                "bdmgtsn":                 bdmgtsn,
                "road_address":            juso_data.get("roadAddr", ""),
                "jibun_address":           juso_data.get("jibunAddr", ""),
                "zipcode":                 juso_data.get("zipNo", ""),
                "main_purpose_name":       main_purpose_name,
                "floor_count":             _safe_int(title.get("grndFlrCnt") or title.get("floor_count")),
                "underground_floor_count": _safe_int(title.get("ugrndFlrCnt") or title.get("underground_floor_count")),
                "building_area":           _safe_float(title.get("totArea") or title.get("building_area")),
                "arch_area":               _safe_float(title.get("archArea") or title.get("arch_area")),
                "use_approve_day":         use_approve_day,
                "completion_year":         completion_year,
                "ride_elevator_count":     _safe_int(title.get("rideUseElvtCnt") or title.get("ride_elevator_count")),
                "emergency_elevator_count":_safe_int(title.get("emgenUseElvtCnt") or title.get("emergency_elevator_count")),
                "earthquake_design_applied": (
                    title.get("erthqkDsgnApplyYn") == "Y" or
                    title.get("rserthqkDsgnApplyYn") == "1" or
                    title.get("earthquake_design_applied") is True
                ),
                "structure": (title.get("strctCdNm") or "").strip(),
            },
        }
        print(f"[BUILD-6] 완료")
        return result

    except Exception as e:
        print(f"[BUILD-ERR-SERIAL] {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"응답 처리 오류: {str(e)}")


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

    bdmgtsn = (juso.get("bdMgtSn") or "").strip()
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
    return {
        "status":       "success",
        "factory_id":   factory_id,
        "factory_name": factory.get("name"),
        "floor_count":  len(floor_data),
        "floors":       floor_data,
    }
