"""
routers/diagnosis_autofill.py — v1.0.0

BE-05: diagnosis 입력 자동조회 API

엔드포인트:
  GET /diagnosis/autofill/building-register?address=  건축물대장 자동채움
  GET /diagnosis/autofill/business?biz_no=            국세청 사업자상태조회
  GET /diagnosis/autofill/address?query=              도로명주소 검색 (juso.go.kr)

금기:
  - 카카오 API 사용 금지
  - 개인정보(주민번호·여권번호) 수집 금지

환경변수:
  BUILDING_REGISTER_API_KEY  공공데이터포털 건축물대장 API 키
  JUSO_CONFIRM_KEY           도로명주소 API 인증키 (juso.go.kr)
  NTS_API_KEY                국세청 사업자상태조회 API 키 (선택)
"""
from __future__ import annotations
import os, logging, httpx
from fastapi import APIRouter, Query, HTTPException
from typing import Optional

log    = logging.getLogger(__name__)
router = APIRouter(prefix="/diagnosis/autofill", tags=["진단자동조회"])

# ── 환경변수 ───────────────────────────────────────────────────────────────
BUILDING_API_KEY = os.environ.get("BUILDING_REGISTER_API_KEY", "")
JUSO_CONFIRM_KEY = os.environ.get("JUSO_CONFIRM_KEY", "")
NTS_API_KEY      = os.environ.get("NTS_API_KEY", "")

# 공공데이터포털 건축물대장 base URL
BUILDING_BASE = "https://apis.data.go.kr/1613000/BldRgstHubService"
# 도로명주소 API base URL (juso.go.kr)
JUSO_BASE     = "https://business.juso.go.kr/addrlink/addrLinkApi.do"
# 국세청 사업자상태조회
NTS_BASE      = "https://api.odcloud.kr/api/nts-businessman/v1/status"


# ── 공통 HTTP 헬퍼 ────────────────────────────────────────────────────────
async def _get_json(url: str, params: dict, timeout: int = 15) -> dict:
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.get(url, params=params)
        if r.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"외부 API 오류: {r.status_code}")
        return r.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="외부 API 타임아웃")
    except httpx.ConnectError as e:
        raise HTTPException(status_code=503, detail=f"외부 API 연결 실패: {e}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"{type(e).__name__}: {str(e)[:100]}")


async def _post_json(url: str, json_body: dict, params: dict | None = None, timeout: int = 15) -> dict:
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.post(url, json=json_body, params=params or {})
        if r.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"외부 API 오류: {r.status_code}")
        return r.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="외부 API 타임아웃")
    except httpx.ConnectError as e:
        raise HTTPException(status_code=503, detail=f"외부 API 연결 실패: {e}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"{type(e).__name__}: {str(e)[:100]}")


# ── 건축물 주구조 코드 → 한글 매핑 ─────────────────────────────────────────
STRUCTURE_CODE_MAP = {
    "1": "RC",   # 철근콘크리트
    "2": "S",    # 철골
    "3": "SRC",  # 철골철근콘크리트
    "4": "MASONRY",  # 조적조
    "5": "WOOD", # 목조
    "99": "OTHER",
}


# ─────────────────────────────────────────────────────────────────────────
# GET /diagnosis/autofill/address
# ─────────────────────────────────────────────────────────────────────────
@router.get("/address")
async def autofill_address(
    query: str = Query(..., description="검색 주소 (예: 테헤란로 152)"),
    page:  int = Query(1, ge=1),
    size:  int = Query(10, ge=1, le=30),
):
    """
    도로명주소 검색 (행정안전부 juso.go.kr API).
    카카오 주소 API 대체재 — 동일 구조의 결과 반환.
    JUSO_CONFIRM_KEY 미설정 시 mock 결과 반환.
    """
    if not JUSO_CONFIRM_KEY:
        log.warning("[AUTOFILL] JUSO_CONFIRM_KEY 미설정 — mock 응답 반환")
        return {
            "status": "mock",
            "query": query,
            "total": 1,
            "items": [{
                "road_address": f"{query} (mock)",
                "jibun_address": "",
                "zip_code": "00000",
                "sido": "",
                "sigungu": "",
                "detail_address": "",
            }],
        }

    data = await _get_json(JUSO_BASE, {
        "confmKey":   JUSO_CONFIRM_KEY,
        "currentPage": page,
        "countPerPage": size,
        "keyword":    query,
        "resultType": "json",
    })

    results_raw = (data.get("results") or {}).get("juso") or []
    items = [
        {
            "road_address":   r.get("roadAddr", ""),
            "jibun_address":  r.get("jibunAddr", ""),
            "zip_code":       r.get("zipNo", ""),
            "sido":           r.get("siNm", ""),
            "sigungu":        r.get("sggNm", ""),
            "detail_address": r.get("detBdNmList", ""),
            # 건축물대장 조회용 관리번호
            "mgm_bldrgst_pk": r.get("admCd", "") + r.get("rnMgtSn", ""),
        }
        for r in results_raw
    ]
    total_count = int((data.get("results") or {}).get("common", {}).get("totalCount", 0))

    return {"status": "success", "query": query, "total": total_count, "items": items}


# ─────────────────────────────────────────────────────────────────────────
# GET /diagnosis/autofill/building-register
# ─────────────────────────────────────────────────────────────────────────
@router.get("/building-register")
async def autofill_building_register(
    address: str = Query(..., description="건물 도로명 주소 (예: 서울특별시 강남구 테헤란로 152)"),
    sigungu_cd: Optional[str] = Query(None, description="시군구코드 5자리 (옵션, 정확도 향상)"),
):
    """
    공공데이터포털 건축물대장 자동채움 API.
    diagnosis_input_fields.auto_source='building_register' 필드에 사용.

    반환 필드:
      main_structure  : 주구조 코드 (RC/S/SRC/MASONRY/WOOD/OTHER)
      building_area   : 건물면적 ㎡
      total_floor_area: 연면적 ㎡
      floors_above    : 지상층수
      floors_below    : 지하층수
      build_year      : 사용승인연도
      purpose_code    : 주용도코드명
      elevator_count  : 승강기 수

    BUILDING_REGISTER_API_KEY 미설정 시 mock 결과 반환.
    """
    if not BUILDING_API_KEY:
        log.warning("[AUTOFILL] BUILDING_REGISTER_API_KEY 미설정 — mock 응답 반환")
        return {
            "status": "mock",
            "address": address,
            "data": {
                "main_structure":    "RC",
                "building_area":     1200.5,
                "total_floor_area":  8400.0,
                "floors_above":      7,
                "floors_below":      2,
                "build_year":        2005,
                "purpose_code":      "업무시설",
                "elevator_count":    2,
            },
        }

    # ① 주소로 관리번호 조회 (건축물대장 표제부 검색)
    search_url = f"{BUILDING_BASE}/getBrTitleInfo"
    search_params = {
        "serviceKey": BUILDING_API_KEY,
        "numOfRows":  "1",
        "pageNo":     "1",
        "_type":      "json",
        "newPlatPlc": address,
    }
    if sigungu_cd:
        search_params["sigunguCd"] = sigungu_cd

    raw = await _get_json(search_url, search_params)
    items = ((raw.get("response") or {}).get("body") or {}).get("items") or {}
    item_list = items.get("item") if isinstance(items, dict) else items
    if not item_list:
        return {"status": "not_found", "address": address, "data": {}}

    bld = item_list[0] if isinstance(item_list, list) else item_list

    # 주구조 코드 → 내부 enum 변환
    struct_raw   = str(bld.get("strctCdNm") or bld.get("strctCd") or "")
    main_struct  = STRUCTURE_CODE_MAP.get(struct_raw, "OTHER") if struct_raw.isdigit() else (
        "RC" if "콘크리트" in struct_raw else
        "S"  if "철골" in struct_raw and "콘크리트" not in struct_raw else
        "SRC" if "철골철근" in struct_raw else
        "MASONRY" if "조적" in struct_raw else
        "WOOD" if "목조" in struct_raw else "OTHER"
    )

    def _safe_float(v) -> Optional[float]:
        try: return float(v)
        except (TypeError, ValueError): return None

    def _safe_int(v) -> Optional[int]:
        try: return int(v)
        except (TypeError, ValueError): return None

    year_raw = bld.get("useAprDay") or bld.get("crtnDay") or ""
    build_year = _safe_int(str(year_raw)[:4]) if year_raw else None

    return {
        "status": "success",
        "address": address,
        "data": {
            "main_structure":    main_struct,
            "building_area":     _safe_float(bld.get("area")),
            "total_floor_area":  _safe_float(bld.get("totArea")),
            "floors_above":      _safe_int(bld.get("grndFlrCnt")),
            "floors_below":      _safe_int(bld.get("ugrndFlrCnt")),
            "build_year":        build_year,
            "purpose_code":      bld.get("mainPurpsCdNm") or bld.get("mainPurpsCd"),
            "elevator_count":    _safe_int(bld.get("rideUseElvtCnt")),
        },
        "raw_mgm_bldrgst_pk": bld.get("mgmBldrgstPk"),
    }


# ─────────────────────────────────────────────────────────────────────────
# GET /diagnosis/autofill/business
# ─────────────────────────────────────────────────────────────────────────
@router.get("/business")
async def autofill_business(
    biz_no: str = Query(..., description="사업자등록번호 10자리 (하이픈 제거, 예: 1234567890)"),
):
    """
    국세청 사업자상태조회 API (공공데이터포털 odcloud).
    개인정보(주민번호·여권번호) 수집 금지 — 사업자 상태·업태만 반환.

    반환 필드:
      biz_no          : 사업자번호
      tax_type        : 과세유형 (부가세 과세/면세/간이 등)
      tax_type_cd     : 과세유형 코드
      end_dt          : 폐업일 (있으면 폐업 사업자)
      status          : ACTIVE | CLOSED | UNKNOWN

    NTS_API_KEY 미설정 시 mock 결과 반환.
    """
    # 숫자만 추출
    clean_no = "".join(filter(str.isdigit, biz_no))
    if len(clean_no) != 10:
        raise HTTPException(status_code=422, detail="사업자등록번호는 숫자 10자리여야 합니다.")

    if not NTS_API_KEY:
        log.warning("[AUTOFILL] NTS_API_KEY 미설정 — mock 응답 반환")
        return {
            "status": "mock",
            "biz_no": clean_no,
            "data": {
                "biz_no":     clean_no,
                "tax_type":   "부가가치세 일반과세자",
                "tax_type_cd": "01",
                "end_dt":     None,
                "status":     "ACTIVE",
            },
        }

    raw = await _post_json(
        NTS_BASE,
        json_body={"b_no": [clean_no]},
        params={"serviceKey": NTS_API_KEY},
    )

    items = raw.get("data") or []
    if not items:
        return {"status": "not_found", "biz_no": clean_no, "data": {}}

    item      = items[0]
    end_dt    = item.get("end_dt") or None
    tax_type  = item.get("tax_type") or ""
    biz_status = "CLOSED" if end_dt else "ACTIVE"

    return {
        "status": "success",
        "biz_no": clean_no,
        "data": {
            "biz_no":      clean_no,
            "tax_type":    tax_type,
            "tax_type_cd": item.get("tax_type_cd"),
            "end_dt":      end_dt,
            "status":      biz_status,
        },
    }
