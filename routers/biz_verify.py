"""
국세청 사업자등록정보 진위확인 및 상태조회 — v2.0.0 (Capability Wrapper Migration)

Wrapper: transport only (request parse, error translate, response format)
Capability: biz-verify/core (_cap_call_nts, _cap_clean_bno, _cap_validate, _cap_status)
Adapter: 없음 (DB 의존 0)

v2.0.0 (2026-05-25): Thin wrapper migration — capability/wrapper separation
v1.0.0 (2026-04-15): Initial

prefix: /biz-verify
외부 API: https://api.odcloud.kr/api/nts-businessman/v1
"""
from fastapi import APIRouter, HTTPException
import httpx
import os

router = APIRouter(prefix="/biz-verify", tags=["사업자진위확인"])

NTS_BASE_URL = "https://api.odcloud.kr/api/nts-businessman/v1"
NTS_SERVICE_KEY = os.getenv("NTS_BIZ_SERVICE_KEY", os.getenv("BUILDING_API_KEY", ""))

STATUS_MAP = {"01": "계속사업자", "02": "휴업자", "03": "폐업자"}


# ═══════════════════════════════════════════════════════
# Capability Core (framework/DB 모름)
# ═══════════════════════════════════════════════════════

def _cap_clean_bno(b_no: str) -> str:
    """사업자번호 정제. framework 모름."""
    cleaned = str(b_no).replace("-", "").replace(" ", "")
    if not cleaned or len(cleaned) != 10 or not cleaned.isdigit():
        raise ValueError(f"b_no: '-' 없는 10자리 숫자여야 합니다. got='{b_no}'")
    return cleaned


def _cap_build_biz_item(body: dict, b_no: str) -> dict:
    """NTS API 요청 항목 빌드. framework 모름."""
    return {
        "b_no": b_no,
        "start_dt": str(body.get("start_dt", "")).replace("-", ""),
        "p_nm": body.get("p_nm", ""),
        "p_nm2": body.get("p_nm2", ""),
        "b_nm": body.get("b_nm", ""),
        "corp_no": body.get("corp_no", ""),
        "b_sector": body.get("b_sector", ""),
        "b_type": body.get("b_type", ""),
        "b_adr": body.get("b_adr", ""),
    }


async def _cap_call_nts(endpoint: str, body: dict) -> dict:
    """국세청 NTS API 호출. framework 모름 (httpx만 사용)."""
    url = f"{NTS_BASE_URL}{endpoint}"
    params = {"serviceKey": NTS_SERVICE_KEY, "returnType": "JSON"}
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, params=params, json=body, headers=headers)
        resp.raise_for_status()
        return resp.json()


def _cap_map_validate_result(item: dict, b_no: str) -> dict:
    """진위확인 결과 매핑. framework 모름."""
    return {
        "b_no": b_no,
        "valid": item.get("valid", ""),
        "valid_yn": item.get("valid") == "01",
        "valid_msg": item.get("valid_msg", ""),
        "status": item.get("status", {}),
        "raw": item,
    }


def _cap_map_status_result(item: dict) -> dict:
    """상태조회 결과 매핑. framework 모름."""
    cd = item.get("b_stt_cd", "")
    return {
        "b_no": item.get("b_no", ""),
        "b_stt": item.get("b_stt", ""),
        "b_stt_cd": cd,
        "b_stt_label": STATUS_MAP.get(cd, item.get("b_stt", "")),
        "is_active": cd == "01",
        "is_closed": cd == "03",
        "tax_type": item.get("tax_type", ""),
        "tax_type_cd": item.get("tax_type_cd", ""),
        "end_dt": item.get("end_dt", ""),
    }


# ═══════════════════════════════════════════════════════
# Wrapper (transport only)
# ═══════════════════════════════════════════════════════

@router.post("/validate")
async def validate_business(body: dict):
    """사업자등록정보 진위확인 (단건). API 응답 100% 기존 호환."""
    try:
        b_no = _cap_clean_bno(body.get("b_no", ""))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not body.get("start_dt"):
        raise HTTPException(status_code=400, detail="start_dt: YYYYMMDD 형식의 개업일자가 필요합니다.")
    if not body.get("p_nm"):
        raise HTTPException(status_code=400, detail="p_nm: 대표자성명이 필요합니다.")

    biz_item = _cap_build_biz_item(body, b_no)
    try:
        result = await _cap_call_nts("/validate", {"businesses": [biz_item]})
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"국세청 API 오류 {e.response.status_code}: {e.response.text[:300]}")
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"국세청 API 연결 실패: {str(e)}")

    item = (result.get("data") or [{}])[0]
    return {"status": "success", "data": {**_cap_map_validate_result(item, b_no), "nts_status": result.get("status_code")}}


@router.post("/validate/bulk")
async def validate_businesses_bulk(body: dict):
    """사업자등록정보 진위확인 배치 (최대 100개). API 응답 100% 기존 호환."""
    businesses = body.get("businesses", [])
    if not businesses:
        raise HTTPException(status_code=400, detail="businesses 배열이 필요합니다.")
    if len(businesses) > 100:
        raise HTTPException(status_code=413, detail="1회 호출에 최대 100개까지만 가능합니다.")

    cleaned = []
    for b in businesses:
        try:
            b_no = _cap_clean_bno(b.get("b_no", ""))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        cleaned.append(_cap_build_biz_item(b, b_no))

    try:
        result = await _cap_call_nts("/validate", {"businesses": cleaned})
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        raise HTTPException(status_code=502, detail=f"국세청 API 오류: {str(e)}")

    mapped = [{"b_no": i.get("b_no", ""), "valid": i.get("valid", ""), "valid_yn": i.get("valid") == "01", "valid_msg": i.get("valid_msg", ""), "status": i.get("status", {})} for i in result.get("data", [])]
    return {"status": "success", "request_cnt": result.get("request_cnt", len(cleaned)), "valid_cnt": result.get("valid_cnt", 0), "data": mapped, "nts_status": result.get("status_code")}


@router.post("/status")
async def get_business_status(body: dict):
    """사업자등록 상태조회 (단건). API 응답 100% 기존 호환."""
    try:
        b_no = _cap_clean_bno(body.get("b_no", ""))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        result = await _cap_call_nts("/status", {"b_no": [b_no]})
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        raise HTTPException(status_code=502, detail=f"국세청 API 오류: {str(e)}")

    item = (result.get("data") or [{}])[0]
    mapped = _cap_map_status_result(item)
    return {"status": "success", "data": {**mapped, "utcc_yn": item.get("utcc_yn", ""), "tax_type_change_dt": item.get("tax_type_change_dt", ""), "invoice_apply_dt": item.get("invoice_apply_dt", ""), "rbf_tax_type": item.get("rbf_tax_type", ""), "rbf_tax_type_cd": item.get("rbf_tax_type_cd", ""), "raw": item, "nts_status": result.get("status_code")}}


@router.post("/status/bulk")
async def get_businesses_status_bulk(body: dict):
    """사업자등록 상태조회 배치 (최대 100개). API 응답 100% 기존 호환."""
    b_no_list = body.get("b_no_list", [])
    if not b_no_list:
        raise HTTPException(status_code=400, detail="b_no_list 배열이 필요합니다.")
    if len(b_no_list) > 100:
        raise HTTPException(status_code=413, detail="1회 호출에 최대 100개까지만 가능합니다.")

    cleaned = []
    for b_no in b_no_list:
        try:
            cleaned.append(_cap_clean_bno(b_no))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    try:
        result = await _cap_call_nts("/status", {"b_no": cleaned})
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        raise HTTPException(status_code=502, detail=f"국세청 API 오류: {str(e)}")

    mapped = [_cap_map_status_result(i) for i in result.get("data", [])]
    return {"status": "success", "request_cnt": result.get("request_cnt", len(cleaned)), "match_cnt": result.get("match_cnt", 0), "data": mapped, "nts_status": result.get("status_code")}
