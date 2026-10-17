# routers/building_register.py v2.5.0
# 카카오 축약 주소 → juso.go.kr 전체형 자동 변환 추가
# - /diagnose: JUSO+건축물대장 API 연결 상태 직접 확인
# - 다단계 주소 폴백: 풀주소 → 시군구+도로명 → 도로명만 → 지번
# - bdMgtSn 없으면 jibunAddr로 재시도
# - 모든 예외 500 방지

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Any, List
import asyncio, re, requests, urllib3, os, traceback, time
from urllib.parse import unquote, quote
from supabase import create_client
from services.kr_public_api import get_proxies, kr_get
from tenacity import retry, stop_after_attempt, wait_fixed
from services.time import now_kst, serialize_business_datetime
from routers.auth import get_current_user
from services.company_scope import _ensure_factory_own
from services.building_register_hydration import fetch_h01_title_for_bdmgtsn, extract_h01_fields

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

router = APIRouter(tags=["building_register"])

SUPABASE_URL  = os.getenv("SUPABASE_URL")
SUPABASE_KEY  = os.getenv("SUPABASE_KEY")
JUSO_KEY      = os.environ.get("JUSO_API_KEY", "U01TX0FVVEgyMDI2MDMxODEyMjUxNjExNzc1MTc=")
BUILDING_KEY  = os.environ.get("BUILDING_API_KEY", "")
VERSION       = "2.4.0"

JUSO_URL      = "https://business.juso.go.kr/addrlink/addrLinkApi.do"
BUILDING_BASE = "https://apis.data.go.kr/1613000/BldRgstHubService"


# 건축물대장(data.go.kr) 호출 헤더 — python-requests UA는 게이트웨이에서
# 다르게 취급될 수 있어 브라우저 호환 UA + JSON Accept 명시
BUILDING_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; TAI-API/1.0)',
    'Accept': 'application/json',
}


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
# JUSO API — 다단계 폴백
# ============================================================

JUSO_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; TAI-API/1.0)',
    'Accept': 'application/json',
    'Accept-Charset': 'UTF-8',
}

@retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
def _juso_call_once(keyword: str) -> Optional[dict]:
    """JUSO API 단일 호출 — User-Agent 추가, firstSort 자동 판별, 재시도 3회"""
    try:
        # 도로명/지번 자동 판별
        has_road = any(x in keyword for x in ["로 ", "길 ", "대로 ", "로", "길", "대로"])
        first_sort = "road" if has_road else "location"

        _js, _jt = kr_get(JUSO_URL, params={
            "confmKey":     JUSO_KEY,
            "currentPage":  1,
            "countPerPage": 1,
            "keyword":      keyword,
            "resultType":   "json",
            "firstSort":    first_sort,
        }, headers=JUSO_HEADERS, timeout=15)
        if _js >= 400:
            raise requests.exceptions.HTTPError(f"JUSO HTTP {_js}")
        import json as _json
        data = _json.loads(_jt)

        if not isinstance(data, dict):
            return None

        results = data.get("results", {})
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
        print(f"[JUSO-RETRY] 연결 오류 재시도 중: {e}")
        raise  # tenacity가 재시도 처리
    except Exception as e:
        print(f"[JUSO ERROR] {e}")
        return None


# 카카오 축약 시도명 → 공식 전체명 변환 테이블
_KAKAO_SIDO_MAP = {
    "서울":  "서울특별시",
    "부산":  "부산광역시",
    "대구":  "대구광역시",
    "인천":  "인천광역시",
    "광주":  "광주광역시",
    "대전":  "대전광역시",
    "울산":  "울산광역시",
    "세종":  "세종특별자치시",
    "경기":  "경기도",
    "강원":  "강원특별자치도",
    "충북":  "충청북도",
    "충남":  "충청남도",
    "전북":  "전북특별자치도",
    "전남":  "전라남도",
    "경북":  "경상북도",
    "경남":  "경상남도",
    "제주":  "제주특별자치도",
}

def _normalize_kakao_address(address: str) -> str:
    """
    카카오 팝업에서 반환된 축약형 주소를 juso.go.kr 호환 전체형으로 변환
    예) "서울 강남구 테헤란로 152"  →  "서울특별시 강남구 테헤란로 152"
        "경기 성남시 분당구 판교로"  →  "경기도 성남시 분당구 판교로"
    """
    a = (address or "").strip()
    # 이미 전체형이면 그대로
    full_sidos = ("특별시", "광역시", "특별자치시", "특별자치도", "경기도",
                  "충청북도", "충청남도", "전라남도", "경상북도", "경상남도")
    if any(a.startswith(s) or s in a[:10] for s in full_sidos):
        return a

    for short, full in _KAKAO_SIDO_MAP.items():
        # "서울 " 또는 "서울\t" 로 시작하는 경우
        if re.match(rf"^{re.escape(short)}[\s　]", a):
            return full + " " + a[len(short):].lstrip()
    return a


def _make_keyword_candidates(address: str) -> List[str]:
    """
    입력 주소에서 여러 검색 키워드 후보 생성
    0. 카카오 축약형 → 전체형 변환 (최우선)
    1. 전체형 원본
    2. 시도 제거
    3. 번지 제거
    4. 시도 제거 + 번지 제거
    """
    a = (address or "").strip()
    if not a:
        return []

    normalized = _normalize_kakao_address(a)
    seen = set()
    candidates = []

    def add(s):
        s = s.strip()
        if s and s not in seen:
            seen.add(s)
            candidates.append(s)

    # 0. 카카오 변환본 우선
    add(normalized)
    # 1. 원본 (변환과 다를 경우)
    add(a)

    # 시도 제거
    sido_re = re.compile(
        r"^(서울특별시|부산광역시|대구광역시|인천광역시|광주광역시|대전광역시|"
        r"울산광역시|세종특별자치시|경기도|강원[도특별자치도]*|충청[남북]도|"
        r"전라[남북]도|전북특별자치도|경상[남북]도|제주특별자치도)\s*"
    )
    no_sido = sido_re.sub("", normalized).strip()
    add(no_sido)

    # 번지 제거
    no_num = re.sub(r"\s+\d+(-\d+)?$", "", normalized).strip()
    add(no_num)

    # 시도 + 번지 제거
    add(re.sub(r"\s+\d+(-\d+)?$", "", no_sido).strip())

    return candidates


def get_juso(address: str) -> Optional[dict]:
    """
    주소 → JUSO 결과 (다단계 폴백)
    bdMgtSn 없으면 도로명으로 재시도
    """
    for keyword in _make_keyword_candidates(address):
        result = _juso_call_once(keyword)
        if not result:
            continue

        bd = result.get("bdMgtSn", "").strip()
        if bd:
            print(f"[JUSO] ✅ 성공 bdMgtSn={bd} keyword={keyword[:25]}")
            return result

        # bdMgtSn 없으면 roadAddr로 재시도
        road = result.get("roadAddr", "").strip()
        if road and road != keyword:
            r2 = _juso_call_once(road)
            if r2 and r2.get("bdMgtSn", "").strip():
                print(f"[JUSO] ✅ roadAddr 재시도 성공 bdMgtSn={r2.get('bdMgtSn')}")
                return r2

        # 그래도 없으면 원래 결과 반환 (jibunAddr 등 나머지 정보라도)
        print(f"[JUSO] ⚠️ bdMgtSn 없음 — 원래 결과 반환")
        return result

    print(f"[JUSO] 모든 후보 실패: {address}")
    return None


async def get_juso_async(address: str) -> Optional[dict]:
    return await asyncio.to_thread(get_juso, address)


def _juso_search_list(keyword: str, current_page: int = 1, count_per_page: int = 20) -> dict:
    """
    도로명주소 검색 API(addrLinkApi.do) — 웹 팝업(Link URL)용 키와 승인이 다름.
    동일 confmKey로 목록만 조회할 때 사용. 프론트는 서버 경유만 한다.
    """
    params = {
        "confmKey": JUSO_KEY,
        "currentPage": current_page,
        "countPerPage": count_per_page,
        "keyword": keyword.strip(),
        "resultType": "json",
    }
    _js, _jt = kr_get(JUSO_URL, params=params, headers=JUSO_HEADERS, timeout=15)
    if _js >= 400:
        raise ValueError(f"JUSO HTTP {_js}")
    import json as _json
    data = _json.loads(_jt)
    if not isinstance(data, dict):
        raise ValueError("JUSO 응답 형식 오류")
    results = data.get("results") or {}
    common = results.get("common") or {}
    err = str(common.get("errorCode", "0"))
    if err != "0":
        raise ValueError(common.get("errorMessage") or f"JUSO 오류코드: {err}")
    juso = results.get("juso") or []
    if isinstance(juso, dict):
        juso = [juso]
    try:
        total = int(str(common.get("totalCount") or "0").strip() or "0")
    except (TypeError, ValueError):
        total = 0
    return {
        "items": juso,
        "totalCount": total,
        "currentPage": current_page,
        "countPerPage": count_per_page,
    }


@router.get("/juso-search")
async def juso_search(
    keyword: str = Query(..., min_length=1, description="도로명·지번·건물명"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    """도로명주소 검색 API 결과 목록 (프론트 주소 모달용)."""
    try:
        out = await asyncio.to_thread(_juso_search_list, keyword, page, size)
        return {"status": "success", "data": out}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=502, detail=f"JUSO 검색 오류: {str(e)}")


# ============================================================
# 건축물대장 API
# ============================================================

def _building_call_once(endpoint: str, sigungu: str, bjdong: str, bun: str, ji: str, rows: int, plat_gb: str) -> Optional[list]:
    """건축물대장 단일 호출 (platGbCd 고정) + 일시장애 재시도. 결과 없으면 None.

    data.go.kr 은 일시장애(05 SERVICETIMEOUT / 04 HTTP_ERROR)를 **HTTP 200 본문**으로도 반환한다
    ({"OpenAPI_ServiceResponse":{"cmmMsgHeader":{"returnReasonCode":"05"}}}). 따라서 상태코드가
    아니라 응답 본문으로 일시오류를 판정해 재시도한다(간헐적 05 때문에 정상 platGbCd 도 첫 시도가
    실패할 수 있음). 정상 무자료(totalCount==0)와 비일시 오류는 재시도 없이 즉시 None."""
    _MAX_ATTEMPTS = 4
    for _attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            _bparams = {
                "serviceKey": BUILDING_KEY,
                "sigunguCd":  sigungu,
                "bjdongCd":   bjdong,
                "platGbCd":   plat_gb,
                "bun":        bun,
                "ji":         ji,
                "numOfRows":  rows,
                "pageNo":     1,
                "_type":      "json"
            }
            # 한국 공공 API: curl_cffi(TLS 지문 우회)+프록시 경유. 표준 requests 는 data.go.kr code10.
            _status, _text = kr_get(f"{BUILDING_BASE}/{endpoint}", params=_bparams,
                                    headers=BUILDING_HEADERS, timeout=25)
            class _Resp:
                pass
            r = _Resp()
            r.status_code = _status
            r.text = _text
            def _rjson(_t=_text):
                import json as _json
                return _json.loads(_t)
            r.json = _rjson
            _btxt = (_text or "")[:400]
            print(f"[BUILDING] {endpoint} platGbCd={plat_gb} HTTP={_status} (attempt {_attempt}/{_MAX_ATTEMPTS})")

            # 일시장애 판정 — 상태코드(5xx)든 HTTP 200 본문의 오류봉투든 모두 감지.
            _transient = (
                r.status_code >= 500
                or "SERVICETIMEOUT" in _btxt
                or "HTTP_ERROR" in _btxt
                or "returnReasonCode>04" in _btxt
                or "returnReasonCode>05" in _btxt
                or '"returnReasonCode":"04"' in _btxt
                or '"returnReasonCode":"05"' in _btxt
                or '"returnReasonCode": "04"' in _btxt
                or '"returnReasonCode": "05"' in _btxt
            )
            if _transient:
                print(f"[BUILDING-RETRY] {endpoint} platGbCd={plat_gb} 일시오류(05/SERVICETIMEOUT) 재시도 {_attempt}/{_MAX_ATTEMPTS} body={_btxt[:120]}")
                if _attempt < _MAX_ATTEMPTS:
                    time.sleep(1.0 * _attempt)
                    continue
                return None

            if r.status_code != 200:
                print(f"[BUILDING-BODY] {endpoint} platGbCd={plat_gb} status={r.status_code} body={_btxt}")
                return None

            try:
                data = r.json()
            except Exception:
                print(f"[BUILDING] JSON 파싱 실패 응답: {_btxt}")
                return None

            resp = data.get("response") if isinstance(data, dict) else None
            if not isinstance(resp, dict):
                # 정상 구조가 아니면(오류봉투 등) 무자료 처리
                return None
            body = resp.get("body")
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
            print(f"[BUILDING] {endpoint} platGbCd={plat_gb} {len(items)}건")
            return items or None
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
                requests.exceptions.ChunkedEncodingError,
                OSError) as e:
            print(f"[BUILDING-RETRY] {endpoint} platGbCd={plat_gb} 연결/타임아웃 재시도 {_attempt}/{_MAX_ATTEMPTS}: {e}")
            if _attempt < _MAX_ATTEMPTS:
                time.sleep(1.0 * _attempt)
                continue
            return None
        except Exception as e:
            print(f"[BUILDING ERROR] {endpoint} platGbCd={plat_gb}: {e}")
            return None
    return None


def _building_get(endpoint: str, sigungu: str, bjdong: str, bun: str, ji: str, rows: int = 10, plat_gb: str = "0") -> Optional[list]:
    if not BUILDING_KEY:
        print(f"[BUILDING] BUILDING_API_KEY 미설정 — {endpoint} 스킵")
        return None
    # 호출 폭주(→ data.go.kr rate-limit 503) 방지: platGbCd=0 단일 조회. 실측상 대지(0)에서 정상 반환.
    return _building_call_once(endpoint, sigungu, bjdong, bun, ji, rows, "0")


def get_building_title(sigungu, bjdong, bun, ji="0000", plat_gb="0"):
    return _building_get("getBrTitleInfo", sigungu, bjdong, bun, ji, plat_gb=plat_gb)

def get_building_basis(sigungu, bjdong, bun, ji="0000", plat_gb="0"):
    return _building_get("getBrBasisOulnInfo", sigungu, bjdong, bun, ji, plat_gb=plat_gb)

def get_floor_outline(sigungu, bjdong, bun, ji="0000", plat_gb="0"):
    return _building_get("getBrFlrOulnInfo", sigungu, bjdong, bun, ji, rows=100, plat_gb=plat_gb)

def get_sewage_info(sigungu, bjdong, bun, ji="0000", plat_gb="0"):
    return _building_get("getBrExposPublcRqstInfo", sigungu, bjdong, bun, ji, plat_gb=plat_gb)


def _get_title_sync(bdmgtsn: str) -> Optional[List[dict]]:
    p = parse_bdmgtsn(bdmgtsn)
    if not p:
        return None
    pg = p.get("mountain", "0")
    t = get_building_title(p["sigunguCd"], p["bjdongCd"], p["bun"], p["ji"], plat_gb=pg)
    if not t:
        t = get_building_title(p["sigunguCd"], p["bjdongCd"], p["bun"], "0000", plat_gb=pg)
    return t


async def get_title_async(bdmgtsn: str) -> Optional[List[dict]]:
    return await asyncio.to_thread(_get_title_sync, bdmgtsn)


def fetch_all_building_data(bdmgtsn: str) -> dict:
    p = parse_bdmgtsn(bdmgtsn)
    if not p:
        return {}
    sg, bj, bun, ji = p["sigunguCd"], p["bjdongCd"], p["bun"], p["ji"]
    result = {"bdmgtsn": bdmgtsn, "parsed": p}
    # 자동채움은 표제부(title)만으로 충분(연면적·층수·용도·준공연도). 호출 폭주로 인한
    # data.go.kr rate-limit(503) 방지를 위해 기본개요·층별·오수는 조회하지 않는다.
    title = get_building_title(sg, bj, bun, ji) or get_building_title(sg, bj, bun, "0000")
    result["title"]  = title
    result["basis"]  = []
    result["floors"] = []
    result["sewage"] = []
    return result


def build_factory_update(juso: dict, building_data: dict, verified_pk: Optional[str] = None) -> dict:
    # WO-E2E2000-FIXOBJ05: building_register_updated_at / mgm_bldrgst_pk / building_height /
    # floor_count 는 H01 공식 수집 계약(fetch_h01_title_for_bdmgtsn + extract_h01_fields) 경로만
    # 설정. 이 함수는 주소·용도·구조 등 비인증 메타데이터만 반환한다.
    update: dict = {}
    if juso:
        update["bdmgtsn"] = juso.get("bdMgtSn", "")
        if juso.get("roadAddr"):  update["address_road"]    = juso.get("roadAddrPart1", "")
        if juso.get("jibunAddr"): update["address_jibun"]   = juso.get("jibunAddr", "")
        if juso.get("zipNo"):     update["zipcode"]         = juso.get("zipNo", "")
        if juso.get("siNm"):      update["address_sido"]    = juso.get("siNm", "")
        if juso.get("sggNm"):     update["address_sigungu"] = juso.get("sggNm", "")
        if juso.get("emdNm"):     update["address_dong"]    = juso.get("emdNm", "")

    title_items = building_data.get("title", []) or []
    # PATCH B: verified_pk 제공 시 정확한 본동만 선택 — 첫 행 대체 금지.
    if verified_pk:
        title = next(
            (i for i in title_items
             if str(i.get("mgmBldrgstPk") or "").strip() == verified_pk
             and i.get("mainAtchGbCdNm") == "주건축물"),
            None,
        )
    else:
        title = next((i for i in title_items if i.get("mainAtchGbCdNm") == "주건축물"), None)

    if title:
        update["main_purpose_code"]        = title.get("mainPurpsCd")
        update["main_purpose_name"]        = title.get("mainPurpsCdNm", "").strip() or None
        update["etc_purpose"]              = title.get("etcPurps", "").strip() or None
        update["building_structure_code"]  = title.get("strctCd")
        update["building_structure_name"]  = title.get("strctCdNm", "").strip() or None
        update["roof_code"]                = title.get("roofCd")
        update["roof_name"]                = title.get("roofCdNm", "").strip() or None
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
        if _to_int(title.get("ugrndFlrCnt")): update["underground_floor_count"] = _to_int(title.get("ugrndFlrCnt"))
        if title.get("useAprDay") and len(str(title["useAprDay"])) >= 4:
            update["completion_year"] = int(str(title["useAprDay"])[:4])
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
        "building_key": "설정됨" if BUILDING_KEY else "❌ 미설정",
        "juso_key":     "설정됨" if JUSO_KEY else "❌ 미설정",
    }


@router.get("/diagnose")
def diagnose(address: str = Query("인천광역시 서구 가좌로 123", description="테스트 주소")):
    """
    건축물대장 API 연결 상태 전체 진단
    - JUSO API 응답 확인
    - 건축물대장 API 응답 확인
    """
    result = {
        "version": VERSION,
        "address": address,
        "juso_key_set": bool(JUSO_KEY),
        "building_key_set": bool(BUILDING_KEY),
    }

    # 1. JUSO 테스트
    try:
        candidates = _make_keyword_candidates(address)
        result["keyword_candidates"] = candidates

        juso = None
        for kw in candidates:
            r = _juso_call_once(kw)
            if r:
                juso = r
                result["juso_keyword_used"] = kw
                break

        if juso:
            result["juso_status"] = "✅ 성공"
            result["juso_roadAddr"] = juso.get("roadAddr", "")
            result["juso_jibunAddr"] = juso.get("jibunAddr", "")
            result["juso_bdMgtSn"] = juso.get("bdMgtSn", "")
            result["juso_zipNo"] = juso.get("zipNo", "")
        else:
            result["juso_status"] = "❌ 결과 없음"
    except Exception as e:
        result["juso_status"] = f"❌ 오류: {str(e)}"
        result["juso_traceback"] = traceback.format_exc()
        return result

    # 2. 건축물대장 테스트
    bdmgtsn = juso.get("bdMgtSn", "").strip() if juso else ""
    if bdmgtsn:
        try:
            parsed = parse_bdmgtsn(bdmgtsn)
            result["bdmgtsn_parsed"] = parsed
            _pg = parsed.get("mountain", "0")
            title = get_building_title(parsed["sigunguCd"], parsed["bjdongCd"], parsed["bun"], parsed["ji"], plat_gb=_pg)
            if not title:
                title = get_building_title(parsed["sigunguCd"], parsed["bjdongCd"], parsed["bun"], "0000", plat_gb=_pg)
                result["title_fallback"] = "ji=0000으로 재시도"

            if title:
                result["building_status"] = "✅ 성공"
                result["building_title_count"] = len(title)
                t = title[0]
                result["building_summary"] = {
                    "mainPurpsCdNm": t.get("mainPurpsCdNm"),
                    "totArea": t.get("totArea"),
                    "grndFlrCnt": t.get("grndFlrCnt"),
                    "useAprDay": t.get("useAprDay"),
                }
            else:
                result["building_status"] = "⚠️ 결과 없음 (bdMgtSn은 있음)"
        except Exception as e:
            result["building_status"] = f"❌ 오류: {str(e)}"
    else:
        result["building_status"] = "⚠️ bdMgtSn 없음 — 건축물대장 조회 불가"

    return result


@router.get("/search")
async def search_building(
    address: str  = Query(..., description="도로명 또는 지번 주소"),
    save:    bool = Query(False)
):
    """주소 → 건축물대장 정보 조회 (지번/도로명 모두 지원)"""
    print(f"\n[SEARCH] START address={address}")

    # STAGE 1 — JUSO
    try:
        juso_data = await get_juso_async(address)
    except Exception as e:
        print(f"[SEARCH] JUSO 오류: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"주소 API 오류: {str(e)}")

    if not juso_data:
        raise HTTPException(
            status_code=404,
            detail=f"주소를 찾을 수 없습니다: '{address}' — 더 자세한 주소를 입력해주세요"
        )

    bdmgtsn = (juso_data.get("bdMgtSn") or "").strip()
    print(f"[SEARCH] JUSO OK bdmgtsn={bdmgtsn}")

    if not bdmgtsn:
        raise HTTPException(
            status_code=404,
            detail=f"건물관리번호를 찾을 수 없습니다 (주소는 찾았으나 건물 정보 없음)"
        )

    # STAGE 2 — 건축물대장 (표제부 + 기본개요 + 층별개요) : 구자산 방식 복원
    try:
        building_data = await asyncio.to_thread(fetch_all_building_data, bdmgtsn)
        title_data = building_data.get("title")
        print(
            f"[SEARCH] 표제부 {len(title_data) if title_data else 0}건 · "
            f"기본개요 {len(building_data.get('basis') or [])}건 · "
            f"층별개요 {len(building_data.get('floors') or [])}건"
        )
    except Exception as e:
        print(f"[SEARCH] 건축물대장 오류: {e}")
        raise HTTPException(status_code=500, detail=f"건축물대장 API 오류: {str(e)}")

    # STAGE 3 — 응답 조립
    try:
        if isinstance(title_data, list):
            title = next((i for i in title_data if i.get("mainAtchGbCdNm") == "주건축물"), None)
            if not title and title_data:
                title = title_data[0]
        else:
            title = {}

        title = title or {}

        use_approve_day = str(title.get("useAprDay") or "")
        completion_year = int(use_approve_day[:4]) if len(use_approve_day) >= 4 else None
        mp = title.get("mainPurpsCdNm") or ""
        main_purpose_name = mp.strip() if isinstance(mp, str) else ""

        data_out = {
            "bdmgtsn":                    bdmgtsn,
            "main_purpose_name":          main_purpose_name,
            "building_use_code":          main_purpose_name,
            "main_structure":             (title.get("strctCdNm") or "").strip() or None,
            "floor_count":                _safe_int(title.get("grndFlrCnt")),
            "underground_floor_count":    _safe_int(title.get("ugrndFlrCnt")),
            "building_area":              _safe_float(title.get("totArea")),
            "arch_area":                  _safe_float(title.get("archArea")),
            "land_area":                  _safe_float(title.get("platArea")),
            "use_approve_day":            use_approve_day,
            "completion_year":            completion_year,
            "ride_elevator_count":        _safe_int(title.get("rideUseElvtCnt")),
            "emergency_elevator_count":   _safe_int(title.get("emgenUseElvtCnt")),
            "earthquake_design_applied":  (
                title.get("rserthqkDsgnApplyYn") == "1"
                or title.get("erthqkDsgnApplyYn") == "Y"
            ),
            # JUSO 주소 정보
            "road_address":    juso_data.get("roadAddr", ""),
            "jibun_address":   juso_data.get("jibunAddr", ""),
            "zipcode":         juso_data.get("zipNo", ""),
            "address_sido":    juso_data.get("siNm", ""),
            "address_sigungu": juso_data.get("sggNm", ""),
            "address_dong":    juso_data.get("emdNm", ""),
        }

        # 층별개요(floors) 폴백 — 표제부에 연면적/층수가 비면 층별개요로 보완 (집합건물 등)
        floors = building_data.get("floors") or []
        if floors:
            if not data_out.get("building_area"):
                _area_sum = sum((_to_float(f.get("area")) or 0.0) for f in floors)
                if _area_sum > 0:
                    data_out["building_area"] = round(_area_sum, 2)
            if data_out.get("floor_count") is None:
                _grnd = [f for f in floors if str(f.get("flrGbCdNm") or "").strip() == "지상"]
                if _grnd:
                    data_out["floor_count"] = len(_grnd)

        # 구자산 전-필드 매핑 병합 — 화면 표시값 외 값도 전부 확보(프론트 키는 유지)
        try:
            _factory_data = build_factory_update(juso_data, building_data)
        except Exception:
            _factory_data = {}
        data_out = {**_factory_data, **{k: v for k, v in data_out.items() if v is not None}}

        print(f"[SEARCH] DONE fields={len(data_out)}")
        return {
            "status":  "success",
            "bdmgtsn": bdmgtsn,
            "juso":    juso_data,
            "data":    data_out,
            "summary": {
                "building_name":  title.get("bldNm", "").strip() or juso_data.get("bdNm", ""),
                "main_purpose":   main_purpose_name,
                "total_area":     _safe_float(title.get("totArea")),
                "floor_count":    _safe_int(title.get("grndFlrCnt")),
                "completion_year":completion_year,
                "elevator_count": _safe_int(title.get("rideUseElvtCnt")),
            }
        }
    except Exception as e:
        print(f"[SEARCH] 응답 조립 오류: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"응답 처리 오류: {str(e)}")


@router.post("/apply/{factory_id}")
def apply_building_register(
    factory_id: str,
    address: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
):
    """건축물대장 → factories 테이블 자동 저장 (PATCH C: 인증+소유권 필수)"""
    supabase = get_supabase()

    # PATCH C: 인증 + factory 소유권 확인
    current = get_current_user(authorization)
    _ensure_factory_own(supabase, factory_id, current)

    factory_res = supabase.table("factories").select(
        "id,name,address_road,address_jibun,bdmgtsn,mgm_bldrgst_pk"
    ).eq("id", factory_id).single().execute()

    if not factory_res.data:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다")

    factory    = factory_res.data
    query_addr = address or factory.get("address_road") or factory.get("address_jibun")
    if not query_addr:
        raise HTTPException(status_code=400, detail="주소가 없습니다. address 파라미터를 입력해주세요")

    juso = get_juso(query_addr)
    if not juso:
        raise HTTPException(status_code=404, detail=f"주소를 찾을 수 없습니다: {query_addr}")

    new_bdmgtsn = (juso.get("bdMgtSn") or "").strip()
    if not new_bdmgtsn:
        raise HTTPException(status_code=404, detail="건물관리번호를 찾을 수 없습니다")

    existing_bdmgtsn = str(factory.get("bdmgtsn") or "").strip()
    existing_mgm_pk  = str(factory.get("mgm_bldrgst_pk") or "").strip() or None

    # PATCH D: 이미 인증된 건물(기존 bdmgtsn+mgm_bldrgst_pk 확정)과 다른 건물번호 → 자동 덮어쓰기 차단
    if existing_bdmgtsn and existing_mgm_pk and new_bdmgtsn != existing_bdmgtsn:
        raise HTTPException(
            status_code=409,
            detail={
                "code":           "BUILDING_IDENTITY_MISMATCH",
                "message":        "이미 인증된 건물과 다른 건물관리번호입니다. 수동 확인이 필요합니다.",
                "existing_bdmgtsn": existing_bdmgtsn,
                "new_bdmgtsn":      new_bdmgtsn,
            },
        )

    # H01 공식 수집 경로 — fetch_h01_title_for_bdmgtsn + extract_h01_fields
    title_items = fetch_h01_title_for_bdmgtsn(new_bdmgtsn, existing_pk=existing_mgm_pk)

    h01_patch: dict = {}
    extracted: dict = {}
    if title_items:
        extracted = extract_h01_fields(title_items, existing_pk=existing_mgm_pk)
        pk = extracted.get("mgm_bldrgst_pk")
        has_numeric = (
            extracted.get("building_height") is not None
            or extracted.get("floor_count") is not None
        )
        if pk and has_numeric:
            # PATCH A: 미반환 수치를 명시적 None으로 — 기존 미인증 수치의 false-auth 방지
            h01_patch = {
                "mgm_bldrgst_pk": pk,
                "building_register_updated_at": serialize_business_datetime(now_kst()),
                "building_height": extracted.get("building_height"),
                "floor_count": extracted.get("floor_count"),
            }

    # PATCH C: 기존 PK 존재, 기존 bdmgtsn 부재 → H01에서 동일 PK 확인 필수
    if existing_mgm_pk and not existing_bdmgtsn:
        h01_confirmed_pk = extracted.get("mgm_bldrgst_pk")
        if h01_confirmed_pk != existing_mgm_pk:
            raise HTTPException(
                status_code=409,
                detail={
                    "code":                    "BUILDING_IDENTITY_UNRESOLVED",
                    "message":                 "기존 건물 PK와 새 건물관리번호의 동일성이 H01에서 확인되지 않았습니다. 수동 확인이 필요합니다.",
                    "existing_mgm_bldrgst_pk": existing_mgm_pk,
                    "h01_confirmed_pk":        h01_confirmed_pk,
                },
            )

    # PATCH B: H01 확인된 PK와 일치하는 본동 메타데이터만 사용 — PK 미확정이면 표제부 저장 금지
    verified_pk = h01_patch.get("mgm_bldrgst_pk")
    title_for_meta = title_items if verified_pk else []
    building_data = {"title": title_for_meta or [], "basis": [], "floors": [], "sewage": []}
    meta = build_factory_update(juso, building_data, verified_pk=verified_pk)

    # h01_patch가 meta를 덮어씀 (명시적 None 포함)
    final_update = {**meta, **h01_patch}

    if not final_update:
        return {"status": "warning", "message": "건축물대장 데이터 없음", "bdmgtsn": new_bdmgtsn}

    supabase.table("factories").update(final_update).eq("id", factory_id).execute()

    return {
        "status":         "success",
        "factory_id":     factory_id,
        "factory_name":   factory.get("name"),
        "bdmgtsn":        new_bdmgtsn,
        "h01_updated":    bool(h01_patch),
        "updated_fields": list(final_update.keys()),
        "updated_count":  len(final_update),
        "summary": {
            "floor_count":     h01_patch.get("floor_count"),
            "building_height": h01_patch.get("building_height"),
            "mgm_bldrgst_pk":  h01_patch.get("mgm_bldrgst_pk"),
            "completion_year": meta.get("completion_year"),
            "main_purpose":    meta.get("main_purpose_name"),
        },
    }


@router.get("/floor/{factory_id}")
def get_factory_floor_outline(factory_id: str):
    supabase    = get_supabase()
    factory_res = supabase.table("factories").select(
        "id,name,floor_outline_json,bdmgtsn"
    ).eq("id", factory_id).single().execute()
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
        "floors":       floor_data
    }


# ============================================================
# WO-E2E2000-FIXOBJ05-H01-PK-CONTRACT-BE-001
# PK 기반 건축물 식별 — 후보 조회 + 검증 적용 (DB WRITE 0 / DB WRITE 1)
# ============================================================

# ---------- 요청 모델 ----------

class ApplyVerifiedRequest(BaseModel):
    bdmgtsn: str = Field(..., description="건물관리번호 19자리")
    expected_mgm_bldrgst_pk: str = Field(..., description="사용자가 선택한 건축물대장 관리PK")


# ---------- GET /h01-candidates ----------

@router.get("/h01-candidates")
def get_h01_candidates(
    bdmgtsn: str = Query(..., description="건물관리번호 19자리"),
    authorization: Optional[str] = Header(None),
):
    """건물관리번호 → 건축물대장 주건축물 PK 후보 목록 조회 (DB WRITE 0).

    JUSO 검색을 거치지 않고 bdmgtsn 직접 사용. 복수 본동 모두 반환 — 첫 행 자동 선택 없음.
    """
    get_current_user(authorization)  # 인증 필수

    if not bdmgtsn or len(bdmgtsn) != 19 or not bdmgtsn.isdigit():
        raise HTTPException(status_code=400, detail={
            "code": "BDMGTSN_FORMAT_INVALID",
            "message": "bdmgtsn은 숫자 19자리여야 합니다.",
        })

    title_items = fetch_h01_title_for_bdmgtsn(bdmgtsn)
    if title_items is None:
        raise HTTPException(status_code=502, detail={
            "code": "SOURCE_UNAVAILABLE",
            "message": "건축물대장 API 조회에 실패했습니다. 잠시 후 다시 시도해주세요.",
        })

    candidates_raw = [i for i in title_items if i.get("mainAtchGbCdNm") == "주건축물"]

    if not candidates_raw:
        return {
            "status": "unresolved",
            "code": "SOURCE_IDENTITY_UNRESOLVED",
            "bdmgtsn": bdmgtsn,
            "candidates": [],
            "total": 0,
        }

    candidates = []
    for row in candidates_raw:
        pk = str(row.get("mgmBldrgstPk") or "").strip()
        if not pk:
            # PK 없는 행 — 동일성 검증 불가 → fail-closed (해당 행 건너뜀)
            continue
        candidates.append({
            "mgm_bldrgst_pk":       pk,
            "building_name":        (row.get("bldNm") or "").strip() or None,
            "address":              (row.get("platPlc") or row.get("newPlatPlc") or "").strip() or None,
            "main_purpose_name":    (row.get("mainPurpsCdNm") or "").strip() or None,
            "main_purpose_code":    row.get("mainPurpsCd"),
            "floor_count":          _safe_int(row.get("grndFlrCnt")),
            "underground_floor_count": _safe_int(row.get("ugrndFlrCnt")),
            "building_height":      _safe_float(row.get("heit")),
            "structure_name":       (row.get("strctCdNm") or "").strip() or None,
            "completion_year":      (
                int(str(row.get("useAprDay") or "")[:4])
                if row.get("useAprDay") and len(str(row.get("useAprDay"))) >= 4
                else None
            ),
        })

    if not candidates:
        return {
            "status": "unresolved",
            "code": "SOURCE_IDENTITY_UNRESOLVED",
            "bdmgtsn": bdmgtsn,
            "candidates": [],
            "total": 0,
        }

    return {
        "status": "success",
        "bdmgtsn": bdmgtsn,
        "candidates": candidates,
        "total": len(candidates),
        "note": "복수 후보 시 사용자가 정확한 건축물을 직접 선택해야 합니다." if len(candidates) > 1 else None,
    }


# ---------- POST /apply-verified/{factory_id} ----------

@router.post("/apply-verified/{factory_id}")
def apply_building_register_verified(
    factory_id: str,
    body: ApplyVerifiedRequest,
    authorization: Optional[str] = Header(None),
):
    """PK 검증 기반 건축물대장 적용 (H01 official fields only, single DB UPDATE).

    클라이언트 제출 PK를 서버가 H01 공식 재조회로 검증 후 일치 시에만 UPDATE.
    주소 재검색(JUSO) 없이 bdmgtsn 직접 사용. 기존 /apply 계약 불변.
    """
    # 인증 먼저 — get_supabase() 전에 토큰 검사 (SUPABASE_URL 미설정 환경도 401 선행)
    current  = get_current_user(authorization)
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)

    # 입력 형식 검증
    bdmgtsn = (body.bdmgtsn or "").strip()
    expected_pk = (body.expected_mgm_bldrgst_pk or "").strip()

    if not bdmgtsn or len(bdmgtsn) != 19 or not bdmgtsn.isdigit():
        raise HTTPException(status_code=400, detail={
            "code": "BDMGTSN_FORMAT_INVALID",
            "message": "bdmgtsn은 숫자 19자리여야 합니다.",
        })
    if not expected_pk:
        raise HTTPException(status_code=400, detail={
            "code": "EXPECTED_PK_MISSING",
            "message": "expected_mgm_bldrgst_pk가 비어 있습니다.",
        })

    # factory 조회 + BUILDING 섹터 확인
    factory_res = supabase.table("factories").select(
        "id,name,sector,bdmgtsn,mgm_bldrgst_pk,building_height,floor_count"
    ).eq("id", factory_id).single().execute()

    if not factory_res.data:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다")

    factory = factory_res.data
    sector  = str(factory.get("sector") or "").upper()

    if sector != "BUILDING":
        raise HTTPException(status_code=422, detail={
            "code": "SECTOR_NOT_BUILDING",
            "message": f"건축물 PK 인증은 BUILDING 섹터 전용입니다. 현재 섹터: {sector or 'UNKNOWN'}",
        })

    existing_pk  = str(factory.get("mgm_bldrgst_pk") or "").strip() or None

    # 기존 확정 PK ≠ 제출 PK → 409
    if existing_pk and existing_pk != expected_pk:
        raise HTTPException(status_code=409, detail={
            "code": "BUILDING_IDENTITY_MISMATCH",
            "message": "이미 확정된 건축물 PK와 다릅니다. 수동 확인이 필요합니다.",
            "existing_mgm_bldrgst_pk": existing_pk,
            "submitted_mgm_bldrgst_pk": expected_pk,
        })

    # H01 공식 표제부 재조회 — existing_pk=expected_pk 로 ji fallback 허용
    title_items = fetch_h01_title_for_bdmgtsn(bdmgtsn, existing_pk=expected_pk)

    if title_items is None:
        raise HTTPException(status_code=502, detail={
            "code": "SOURCE_UNAVAILABLE",
            "message": "건축물대장 API 조회에 실패했습니다. 잠시 후 다시 시도해주세요.",
        })

    if not title_items:
        return {
            "status": "unresolved",
            "code": "SOURCE_IDENTITY_UNRESOLVED",
            "h01_updated": False,
            "factory_id": factory_id,
            "message": "건축물대장에서 해당 건물 정보를 찾을 수 없습니다.",
        }

    # 제출 PK와 일치하는 주건축물 정확히 1건 확인
    extracted = extract_h01_fields(title_items, existing_pk=expected_pk)

    if not extracted:
        raise HTTPException(status_code=409, detail={
            "code": "BUILDING_IDENTITY_MISMATCH",
            "message": "제출한 PK와 H01 공식 조회 결과가 일치하지 않습니다. 후보를 다시 확인하세요.",
            "submitted_mgm_bldrgst_pk": expected_pk,
        })

    server_pk = extracted.get("mgm_bldrgst_pk", "")
    # 이중 안전 검증 — extract_h01_fields가 필터링하지만 명시적 비교
    if server_pk != expected_pk:
        raise HTTPException(status_code=409, detail={
            "code": "BUILDING_IDENTITY_MISMATCH",
            "message": "서버가 확인한 PK와 제출 PK가 다릅니다.",
            "server_mgm_bldrgst_pk": server_pk,
            "submitted_mgm_bldrgst_pk": expected_pk,
        })

    # H01 공식 수치 미확정 → 인증 완료 선언 금지
    has_numeric = (
        extracted.get("building_height") is not None
        or extracted.get("floor_count") is not None
    )

    if not has_numeric:
        return {
            "status": "partial",
            "code": "H01_NUMERIC_ABSENT",
            "h01_updated": False,
            "factory_id": factory_id,
            "mgm_bldrgst_pk": server_pk,
            "message": "PK는 확인됐으나 건물 높이·층수가 없어 공식 인증을 완료할 수 없습니다.",
        }

    # 멱등성: 동일 PK + 동일 수치이면 불필요한 UPDATE 없음
    cur_height = factory.get("building_height")
    cur_floor  = factory.get("floor_count")
    new_height = extracted.get("building_height")
    new_floor  = extracted.get("floor_count")

    if (existing_pk == server_pk
            and cur_height == new_height
            and cur_floor == new_floor):
        return {
            "status": "success",
            "h01_updated": False,
            "idempotent": True,
            "factory_id": factory_id,
            "mgm_bldrgst_pk": server_pk,
            "message": "동일 PK·동일 수치 — 불필요한 UPDATE 없음.",
        }

    # 단일 DB UPDATE
    h01_patch = {
        "bdmgtsn":                      bdmgtsn,
        "mgm_bldrgst_pk":               server_pk,
        "building_height":              new_height,
        "floor_count":                  new_floor,
        "building_register_updated_at": serialize_business_datetime(now_kst()),
    }

    supabase.table("factories").update(h01_patch).eq("id", factory_id).execute()

    return {
        "status":          "success",
        "h01_updated":     True,
        "factory_id":      factory_id,
        "factory_name":    factory.get("name"),
        "bdmgtsn":         bdmgtsn,
        "mgm_bldrgst_pk":  server_pk,
        "building_height": new_height,
        "floor_count":     new_floor,
        "updated_fields":  list(h01_patch.keys()),
    }
