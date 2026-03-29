"""
국세청 사업자등록정보 진위확인 및 상태조회 라우터 — v1.0.0
prefix: /biz-verify

외부 API: https://api.odcloud.kr/api/nts-businessman/v1
인증키: BUILDING_API_KEY (Railway 환경변수 재사용)

엔드포인트:
  POST /biz-verify/validate     사업자등록정보 진위확인 (1회 1개)
  POST /biz-verify/validate/bulk 진위확인 배치 (최대 100개)
  POST /biz-verify/status       사업자등록 상태조회 (1회 1개)
  POST /biz-verify/status/bulk  상태조회 배치 (최대 100개)
···
"""
from fastapi import APIRouter, HTTPException
from typing import Optional
import httpx
import os

router = APIRouter(prefix="/biz-verify", tags=["사업자진위확인"])

VERSION = "1.0.0"

# 국세청 사업자 API
NTS_BASE_URL = "https://api.odcloud.kr/api/nts-businessman/v1"
# Railway 환경변수에서 인증키 읽기
# BUILDING_API_KEY 재사용: 동일한 키값이 data.go.kr에서 발급됨
NTS_SERVICE_KEY = os.getenv(
    "NTS_BIZ_SERVICE_KEY",
    os.getenv("BUILDING_API_KEY", "da4e826323c2c9fef9f325bd4e39a3765d06ac1b582695bcbc475bc0a076255b")
)


async def _call_nts(endpoint: str, body: dict) -> dict:
    """
    국세청 NTS API 호출 공통 함수.
    endpoint: '/validate' 또는 '/status'
    """
    url = f"{NTS_BASE_URL}{endpoint}"
    params = {
        "serviceKey": NTS_SERVICE_KEY,
        "returnType": "JSON",
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, params=params, json=body, headers=headers)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"국세청 API 오류 {e.response.status_code}: {e.response.text[:300]}"
        )
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"국세청 API 연결 실패: {str(e)}")


# ─────────────────────────────────────────────────────
# POST /biz-verify/validate  사업자등록정보 진위확인 (1개)
# ─────────────────────────────────────────────────────
@router.post("/validate")
async def validate_business(body: dict):
    """
    사업자등록정보 진위확인 (단건)

    Request body:
    {
      "b_no": "1234567890",         # 사업자등록번호 (10자리 숫자, '-' 제외) [필수]
      "start_dt": "20200101",       # 개업일자 YYYYMMDD [필수]
      "p_nm": "홍길동",             # 대표자성명 [필수]
      "p_nm2": "",                   # 대표자성명2 (외국인일 경우 한글명)
      "b_nm": "(주)테스트",          # 상호
      "corp_no": "",                 # 법인등록번호 (13자리)
      "b_sector": "",               # 주업태명
      "b_type": "",                 # 주종목명
      "b_adr": ""                   # 사업장주소
    }
    """
    b_no = body.get("b_no", "").replace("-", "").replace(" ", "")
    if not b_no or len(b_no) != 10 or not b_no.isdigit():
        raise HTTPException(status_code=400, detail="b_no: '-' 없는 10자리 숫자여야 합니다.")
    if not body.get("start_dt"):
        raise HTTPException(status_code=400, detail="start_dt: YYYYMMDD 형식의 개업일자가 필요합니다.")
    if not body.get("p_nm"):
        raise HTTPException(status_code=400, detail="p_nm: 대표자성명이 필요합니다.")

    # NTS API request 리스트 형식으로 변환
    biz_item = {
        "b_no":     b_no,
        "start_dt": body["start_dt"].replace("-", ""),
        "p_nm":     body["p_nm"],
        "p_nm2":    body.get("p_nm2", ""),
        "b_nm":     body.get("b_nm", ""),
        "corp_no":  body.get("corp_no", ""),
        "b_sector": body.get("b_sector", ""),
        "b_type":   body.get("b_type", ""),
        "b_adr":    body.get("b_adr", ""),
    }

    result = await _call_nts("/validate", {"businesses": [biz_item]})
    data_list = result.get("data", [])
    item = data_list[0] if data_list else {}

    return {
        "status": "success",
        "data": {
            "b_no":       b_no,
            "valid":      item.get("valid", ""),          # 01=Valid, 02=Invalid
            "valid_yn":   item.get("valid") == "01",       # 진위 여부 bool
            "valid_msg":  item.get("valid_msg", ""),
            "status":     item.get("status", {}),         # 상태조회 결과 (진위 성공 시)
            "raw":        item,
            "nts_status": result.get("status_code"),
        }
    }


# ─────────────────────────────────────────────────────
# POST /biz-verify/validate/bulk  진위확인 배치 (최대 100개)
# ─────────────────────────────────────────────────────
@router.post("/validate/bulk")
async def validate_businesses_bulk(body: dict):
    """
    사업자등록정보 진위확인 배치 (단건 API와 동일한 NTS 포맷)

    Request body:
    {
      "businesses": [
        { "b_no": "1234567890", "start_dt": "20200101", "p_nm": "홍길동", ... },
        ...
      ]
    }
    """
    businesses = body.get("businesses", [])
    if not businesses:
        raise HTTPException(status_code=400, detail="businesses 배열이 필요합니다.")
    if len(businesses) > 100:
        raise HTTPException(status_code=413, detail="1회 호출에 최대 100개까지만 가능합니다.")

    # b_no 정제
    cleaned = []
    for b in businesses:
        b_no = str(b.get("b_no", "")).replace("-", "").replace(" ", "")
        if not b_no or len(b_no) != 10 or not b_no.isdigit():
            raise HTTPException(status_code=400, detail=f"b_no '{b.get('b_no')}': 10자리 숫자여야 합니다.")
        cleaned.append({
            "b_no":     b_no,
            "start_dt": str(b.get("start_dt", "")).replace("-", ""),
            "p_nm":     b.get("p_nm", ""),
            "p_nm2":    b.get("p_nm2", ""),
            "b_nm":     b.get("b_nm", ""),
            "corp_no":  b.get("corp_no", ""),
            "b_sector": b.get("b_sector", ""),
            "b_type":   b.get("b_type", ""),
            "b_adr":    b.get("b_adr", ""),
        })

    result = await _call_nts("/validate", {"businesses": cleaned})
    items  = result.get("data", [])

    # 구조화
    mapped = []
    for item in items:
        mapped.append({
            "b_no":      item.get("b_no", ""),
            "valid":     item.get("valid", ""),
            "valid_yn":  item.get("valid") == "01",
            "valid_msg": item.get("valid_msg", ""),
            "status":    item.get("status", {}),
        })

    return {
        "status":      "success",
        "request_cnt": result.get("request_cnt", len(cleaned)),
        "valid_cnt":   result.get("valid_cnt", 0),
        "data":        mapped,
        "nts_status":  result.get("status_code"),
    }


# ─────────────────────────────────────────────────────
# POST /biz-verify/status  사업자등록 상태조회 (단건)
# ─────────────────────────────────────────────────────
@router.post("/status")
async def get_business_status(body: dict):
    """
    사업자등록 상태조회 (단건)

    Request body:
    {
      "b_no": "1234567890"   # 사업자등록번호 (10자리 숫자, '-' 제외)
    }
    """
    b_no = str(body.get("b_no", "")).replace("-", "").replace(" ", "")
    if not b_no or len(b_no) != 10 or not b_no.isdigit():
        raise HTTPException(status_code=400, detail="b_no: '-' 없는 10자리 숫자여야 합니다.")

    result = await _call_nts("/status", {"b_no": [b_no]})
    data_list = result.get("data", [])
    item = data_list[0] if data_list else {}

    # 나는 상태 해석
    b_stt_cd = item.get("b_stt_cd", "")
    status_map = {"01": "계속사업자", "02": "휴업자", "03": "폐업자"}

    return {
        "status": "success",
        "data": {
            "b_no":               b_no,
            "b_stt":              item.get("b_stt", ""),
            "b_stt_cd":           b_stt_cd,
            "b_stt_label":        status_map.get(b_stt_cd, item.get("b_stt", "")),
            "is_active":          b_stt_cd == "01",       # 계속사업자 여부 bool
            "is_closed":          b_stt_cd == "03",       # 폐업 여부 bool
            "tax_type":           item.get("tax_type", ""),
            "tax_type_cd":        item.get("tax_type_cd", ""),
            "end_dt":             item.get("end_dt", ""),  # 폐업일 YYYYMMDD
            "utcc_yn":            item.get("utcc_yn", ""),
            "tax_type_change_dt": item.get("tax_type_change_dt", ""),
            "invoice_apply_dt":   item.get("invoice_apply_dt", ""),
            "rbf_tax_type":       item.get("rbf_tax_type", ""),
            "rbf_tax_type_cd":    item.get("rbf_tax_type_cd", ""),
            "raw":                item,
            "nts_status":         result.get("status_code"),
        }
    }


# ─────────────────────────────────────────────────────
# POST /biz-verify/status/bulk  상태조회 배치 (최대 100개)
# ─────────────────────────────────────────────────────
@router.post("/status/bulk")
async def get_businesses_status_bulk(body: dict):
    """
    사업자등록 상태조회 배치

    Request body:
    {
      "b_no_list": ["1234567890", "0987654321", ...]
    }
    """
    b_no_list = body.get("b_no_list", [])
    if not b_no_list:
        raise HTTPException(status_code=400, detail="b_no_list 배열이 필요합니다.")
    if len(b_no_list) > 100:
        raise HTTPException(status_code=413, detail="1회 호출에 최대 100개까지만 가능합니다.")

    cleaned = []
    for b_no in b_no_list:
        b = str(b_no).replace("-", "").replace(" ", "")
        if not b or len(b) != 10 or not b.isdigit():
            raise HTTPException(status_code=400, detail=f"b_no '{b_no}': 10자리 숫자여야 합니다.")
        cleaned.append(b)

    result = await _call_nts("/status", {"b_no": cleaned})
    items  = result.get("data", [])

    status_map = {"01": "계속사업자", "02": "휴업자", "03": "폐업자"}
    mapped = []
    for item in items:
        cd = item.get("b_stt_cd", "")
        mapped.append({
            "b_no":        item.get("b_no", ""),
            "b_stt":       item.get("b_stt", ""),
            "b_stt_cd":    cd,
            "b_stt_label": status_map.get(cd, item.get("b_stt", "")),
            "is_active":   cd == "01",
            "is_closed":   cd == "03",
            "tax_type":    item.get("tax_type", ""),
            "tax_type_cd": item.get("tax_type_cd", ""),
            "end_dt":      item.get("end_dt", ""),
        })

    return {
        "status":      "success",
        "request_cnt": result.get("request_cnt", len(cleaned)),
        "match_cnt":   result.get("match_cnt", 0),
        "data":        mapped,
        "nts_status":  result.get("status_code"),
    }
