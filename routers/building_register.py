# routers/building_register.py v2.1.0
# 카카오 축약 주소 → juso.go.kr 전체형 자동 변환 추가
# - /diagnose: JUSO+건축물대장 API 연결 상태 직접 확인
# - 다단계 주소 폴백: 풀주소 → 시군구+도로명 → 도로명만 → 지번
# - bdMgtSn 없으면 jibunAddr로 재시도
# - 모든 예외 500 방지

from fastapi import APIRouter, HTTPException, Query
from datetime import datetime
from typing import Optional, Any, List
import asyncio, re, requests, urllib3, os, traceback
from urllib.parse import unquote, quote
from supabase import create_client
from tenacity import retry, stop_after_attempt, wait_fixed

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

router = APIRouter(tags=["building_register"])

SUPABASE_URL  = os.getenv("SUPABASE_URL")
SUPABASE_KEY  = os.getenv("SUPABASE_KEY")
JUSO_KEY      = os.environ.get("JUSO_API_KEY", "U01TX0FVVEgyMDI2MDMxODEyMjUxNjExNzc1MTc=")
BUILDING_KEY  = os.environ.get("BUILDING_API_KEY", "")
VERSION       = "2.4.0"

JUSO_URL      = "https://business.juso.go.kr/addrlink/addrLinkApi.do"
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

        r = requests.get(JUSO_URL, params={
            "confmKey":     JUSO_KEY,
            "currentPage":  1,
            "countPerPage": 1,
            "keyword":      keyword,
            "resultType":   "json",
            "firstSort":    first_sort,
        }, headers=JUSO_HEADERS, verify=False, timeout=10)
        r.raise_for_status()
        data = r.json()

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
        # "서울 " 또는 "서울	" 로 시작하는 경우
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
    r = requests.get(JUSO_URL, params=params, verify=False, timeout=15)
    r.raise_for_status()
    data = r.json()
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

def _building_get(endpoint: str, sigungu: str, bjdong: str, bun: str, ji: str, rows: int = 10, plat_gb: str = "0") -> Optional[list]:
    if not BUILDING_KEY:
        print(f"[BUILDING] BUILDING_API_KEY 미설정 — {endpoint} 스킵")
        return None
    plat_gb = "1" if str(plat_gb).strip() == "1" else "0"
    try:
        r = requests.get(f"{BUILDING_BASE}/{endpoint}", params={
            "serviceKey": BUILDING_KEY,
            "sigunguCd":  sigungu,
            "bjdongCd":   bjdong,
            "platGbCd":   plat_gb,
            "bun":        bun,
            "ji":         ji,
            "numOfRows":  rows,
            "pageNo":     1,
            "_type":      "json"
        }, verify=False, timeout=15)
        print(f"[BUILDING] {endpoint} HTTP={r.status_code}")
        try:
            data = r.json()
        except Exception:
            print(f"[BUILDING] JSON 파싱 실패 응답: {r.text[:100]}")
            return None

        resp = data.get("response") if isinstance(data, dict) else None
        if not isinstance(resp, dict):
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
        print(f"[BUILDING] {endpoint} {len(items)}건")
        return items or None
    except Exception as e:
        print(f"[BUILDING ERROR] {endpoint}: {e}")
        return None


def get_building_title(sigungu, bjdong, bun, ji="0000", plat_gb="0"):
    return _building_get("getBrTitleInfo", sigungu, bjdong, bun, ji, plat_gb=plat_gb)

def get_building_basis(sigungu, bjdong, bun, ji="0000", plat_gb="0"):
    return _building_get("getBrBasisOulnInfo", sigungu, bjdong, bun, ji, plat_gb=plat_gb)

def get_floor_outline(sigungu, bjdong, bun, ji="0000", plat_gb="0"):
    return _building_get("getBrFlrOulnInfo", sigungu, bjdong, bun, ji, rows=100, plat_gb=plat_gb)

def get_sewage_info(sigungu, bjdong, bun, ji="0000", plat_gb="0"):
    return _building_get("getBrExposPublcRqstInfo", sigungu, bjdong, bun, ji, plat_gb=plat_gb)


def _probe_send(method, url, params=None, proxies=None):
    o = {"method": method}
    try:
        if method == "urllib":
            import ssl, urllib.request
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            with urllib.request.urlopen(urllib.request.Request(url), context=ctx, timeout=15) as resp:
                o["http"] = getattr(resp, "status", None)
                txt = resp.read().decode("utf-8", "ignore")
                o["sent_url_pct25"] = "%25" in url
        else:
            r = requests.get(url, params=params, verify=False, timeout=20, proxies=proxies)
            o["http"] = r.status_code
            txt = r.text
            o["sent_url_pct25"] = "%25" in (r.request.url or "")
        try:
            import json as _j
            d = _j.loads(txt)
            resp = d.get("response") or {}
            o["resultCode"] = (resp.get("header") or {}).get("resultCode")
            o["totalCount"] = (resp.get("body") or {}).get("totalCount")
            err = (d.get("OpenAPI_ServiceResponse") or {}).get("cmmMsgHeader")
            if isinstance(err, dict):
                o["reason"] = err.get("returnReasonCode")
                o["errMsg"] = err.get("errMsg")
        except Exception:
            o["raw"] = txt[:150]
    except Exception as e:
        o["exception"] = f"{type(e).__name__}: {str(e)[:150]}"
    return o


def _outbound_proxies():
    """payment_helpers.get_proxies() 동일 — OUTBOUND_PROXY(이니시스 고정IP) 경유."""
    proxy = os.getenv("OUTBOUND_PROXY", "").strip()
    if not proxy:
        return None
    scheme, sep, rest = proxy.partition("://")
    if sep and "@" not in rest:
        user = os.getenv("PROXY_USER", "").strip()
        pw = os.getenv("PROXY_PASS", "").strip()
        if user and pw:
            proxy = f"{scheme}://{quote(user, safe='')}:{quote(pw, safe='')}@{rest}"
    return {"http": proxy, "https": proxy}


def _building_probe_key(sg, bj, bun, ji):
    """OUTBOUND_PROXY(이니시스 고정IP) 경유 + 후보 키 env 각각으로 레퍼런스(개포동, 34건) 검증."""
    def fp(name):
        v = os.getenv(name, "") or ""
        return {"set": bool(v), "len": len(v), "head4": v[:4], "tail6": v[-6:],
                "has_pct": "%" in v, "has_plus_slash_eq": any(c in v for c in ("+", "/", "="))}
    cands = ["DATA_GO_KR_SERVICE_KEY", "BUILDING_REGISTER_API_KEY", "BUILDING_API_KEY",
             "KOSHA_SERVICE_KEY", "FIRE_SERVICE_KEY", "SAFETY_INFO_SERVICE_KEY"]
    proxies = _outbound_proxies()
    out = {
        "_expected_totalCount": "약 34",
        "OUTBOUND_PROXY_set": bool(os.getenv("OUTBOUND_PROXY", "")),
        "proxy_used": bool(proxies),
        "env_fingerprints": {n: fp(n) for n in cands},
        "via_proxy": {},
    }
    base = f"{BUILDING_BASE}/getBrTitleInfo"
    tail = "sigunguCd=11680&bjdongCd=10300&bun=0012&ji=0000&numOfRows=10&pageNo=1&_type=json"
    for n in cands:
        k = os.getenv(n, "").strip()
        if not k:
            continue
        kp = k if "%" in k else quote(k, safe="")  # holiday _key_param 패턴
        out["via_proxy"][n] = _probe_send("requests_url", f"{base}?{tail}&serviceKey={kp}", None, proxies)
    return out

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
    pg = p.get("mountain", "0")
    result = {"bdmgtsn": bdmgtsn, "parsed": p}
    title = get_building_title(sg, bj, bun, ji, plat_gb=pg) or get_building_title(sg, bj, bun, "0000", plat_gb=pg)
    if title:
        ji = "0000"
    result["title"]  = title
    result["basis"]  = get_building_basis(sg, bj, bun, ji, plat_gb=pg)
    result["floors"] = get_floor_outline(sg, bj, bun, ji, plat_gb=pg)
    result["sewage"] = get_sewage_info(sg, bj, bun, ji, plat_gb=pg)
    return result


def build_factory_update(juso: dict, building_data: dict) -> dict:
    update = {"building_register_updated_at": datetime.now().isoformat()}
    if juso:
        update["bdmgtsn"] = juso.get("bdMgtSn", "")
        if juso.get("roadAddr"):  update["address_road"]    = juso.get("roadAddrPart1", "")
        if juso.get("jibunAddr"): update["address_jibun"]   = juso.get("jibunAddr", "")
        if juso.get("zipNo"):     update["zipcode"]         = juso.get("zipNo", "")
        if juso.get("siNm"):      update["address_sido"]    = juso.get("siNm", "")
        if juso.get("sggNm"):     update["address_sigungu"] = juso.get("sggNm", "")
        if juso.get("emdNm"):     update["address_dong"]    = juso.get("emdNm", "")

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
            result["building_probe"] = _building_probe_key(
                parsed["sigunguCd"], parsed["bjdongCd"], parsed["bun"], parsed["ji"])
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
    address: Optional[str] = Query(None)
):
    """건축물대장 → factories 테이블 자동 저장"""
    supabase    = get_supabase()
    factory_res = supabase.table("factories").select(
        "id,name,address_road,address_jibun,bdmgtsn"
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

    bdmgtsn = (juso.get("bdMgtSn") or "").strip()
    if not bdmgtsn:
        raise HTTPException(status_code=404, detail="건물관리번호를 찾을 수 없습니다")

    building_data = fetch_all_building_data(bdmgtsn)
    update_data   = build_factory_update(juso, building_data)

    if not update_data:
        return {"status": "warning", "message": "건축물대장 데이터 없음", "bdmgtsn": bdmgtsn}

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
        }
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
