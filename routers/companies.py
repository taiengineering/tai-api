#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TAI Companies 라우터 - 사업장 등록/관리
전역변수: company_type / contract_status / industry_type

엔드포인트:
GET    /companies                    사업장 목록 조회
POST   /companies                    사업장 등록
GET    /companies/{id}               사업장 상세 조회
PATCH  /companies/{id}               사업장 수정
DELETE /companies/{id}               사업장 비활성화
GET    /companies/{id}/users         소속 회원 목록
GET    /companies/{id}/factories     소속 시설 목록
POST   /companies/nts-verify         사업자등록정보 진위확인 (국세청)
POST   /companies/nts-status         사업자등록 상태조회 (국세청)
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import httpx
import os
from db.supabase_client import get_supabase

router = APIRouter(prefix="/companies", tags=["companies"])

# ── NTS 국세청 API 설정 ──────────────────────────────────────
NTS_BASE_URL = "https://api.odcloud.kr/api/nts-businessman/v1"
NTS_SERVICE_KEY = os.getenv(
    "NTS_BIZ_SERVICE_KEY",
    os.getenv("BUILDING_API_KEY", "da4e826323c2c9fef9f325bd4e39a3765d06ac1b582695bcbc475bc0a076255b")
)


async def _nts_post(endpoint: str, body: dict) -> dict:
    """국세청 NTS API POST 공통 호출"""
    url = f"{NTS_BASE_URL}{endpoint}"
    params = {"serviceKey": NTS_SERVICE_KEY, "returnType": "JSON"}
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
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


# ============================================================
# 스키마
# ============================================================

class CompanyCreate(BaseModel):
    # 기본 정보 (필수)
    name:                str

    # 사업자 정보
    company_type_code:   Optional[str] = "002"   # company_type: 001=법인/002=개인/003=간이/004=공공/005=비영리
    business_number:     Optional[str] = None    # 사업자번호
    corporation_number:  Optional[str] = None    # 법인번호
    representative_name: Optional[str] = None    # 대표자명
    established_date:    Optional[str] = None    # 설립일

    # 업종 정보
    business_type:       Optional[str] = None    # 업태 (텍스트)
    business_category:   Optional[str] = None    # 업종 (텍스트)
    industry_type_code:  Optional[str] = None    # industry_type 전역변수

    # 연락처
    contact_phone:       Optional[str] = None
    contact_email:       Optional[str] = None
    phone:               Optional[str] = None
    fax:                 Optional[str] = None
    website_url:         Optional[str] = None

    # 주소
    zipcode:             Optional[str] = None
    address_road:        Optional[str] = None
    address_jibun:       Optional[str] = None
    address_detail:      Optional[str] = None
    address_sido:        Optional[str] = None
    address_sigungu:     Optional[str] = None
    address_dong:        Optional[str] = None

    # 기타
    employee_count:      Optional[int] = None
    logo_url:            Optional[str] = None


class CompanyUpdate(BaseModel):
    name:                Optional[str] = None
    company_type_code:   Optional[str] = None
    business_number:     Optional[str] = None
    corporation_number:  Optional[str] = None
    representative_name: Optional[str] = None
    established_date:    Optional[str] = None
    business_type:       Optional[str] = None
    business_category:   Optional[str] = None
    industry_type_code:  Optional[str] = None
    contact_phone:       Optional[str] = None
    contact_email:       Optional[str] = None
    phone:               Optional[str] = None
    fax:                 Optional[str] = None
    website_url:         Optional[str] = None
    zipcode:             Optional[str] = None
    address_road:        Optional[str] = None
    address_jibun:       Optional[str] = None
    address_detail:      Optional[str] = None
    address_sido:        Optional[str] = None
    address_sigungu:     Optional[str] = None
    address_dong:        Optional[str] = None
    employee_count:      Optional[int] = None
    logo_url:            Optional[str] = None
    status_code:         Optional[str] = None    # contract_status 전역변수


# ============================================================
# NTS 사업자등록정보 진위확인  POST /companies/nts-verify
# ※ /{company_id} 보다 먼저 선언
# ============================================================

@router.post("/nts-verify")
async def nts_verify(body: dict):
    """
    국세청 사업자등록정보 진위확인.
    실제 NTS API: POST https://api.odcloud.kr/api/nts-businessman/v1/validate

    Request body:
    {
      "b_no": "1234567890",    # 사업자등록번호 10자리 (- 자동 제거)  [필수]
      "start_dt": "20200101",  # 개업일자 YYYYMMDD                   [필수]
      "p_nm": "홍길동",         # 대표자성명                           [필수]
      "p_nm2": "",             # 대표자성명2 (외국인만)
      "b_nm": "",              # 상호
      "corp_no": "",           # 법인등록번호 13자리
      "b_sector": "",          # 주업태명
      "b_type": "",            # 주종목명
      "b_adr": ""              # 사업장주소
    }
    """
    b_no = str(body.get("b_no", "")).replace("-", "").replace(" ", "")
    if not b_no or len(b_no) != 10 or not b_no.isdigit():
        raise HTTPException(status_code=400, detail="b_no: 10자리 숫자여야 합니다 ('-' 제외).")
    if not body.get("start_dt"):
        raise HTTPException(status_code=400, detail="start_dt: YYYYMMDD 형식의 개업일자가 필요합니다.")
    if not body.get("p_nm"):
        raise HTTPException(status_code=400, detail="p_nm: 대표자성명이 필요합니다.")

    biz_item = {
        "b_no":     b_no,
        "start_dt": str(body["start_dt"]).replace("-", ""),
        "p_nm":     body["p_nm"],
        "p_nm2":    body.get("p_nm2", ""),
        "b_nm":     body.get("b_nm", ""),
        "corp_no":  body.get("corp_no", ""),
        "b_sector": body.get("b_sector", ""),
        "b_type":   body.get("b_type", ""),
        "b_adr":    body.get("b_adr", ""),
    }

    result = await _nts_post("/validate", {"businesses": [biz_item]})
    items = result.get("data", [])
    item  = items[0] if items else {}

    return {
        "status": "success",
        "data": {
            "b_no":      b_no,
            "valid":     item.get("valid", ""),      # "01"=일치, "02"=불일치
            "valid_yn":  item.get("valid") == "01",  # bool
            "valid_msg": item.get("valid_msg", ""),
            "status":    item.get("status", {}),     # 상태조회 결과 (진위 성공 시)
            "nts_status_code": result.get("status_code"),
        }
    }


# ============================================================
# NTS 사업자등록 상태조회  POST /companies/nts-status
# ※ /{company_id} 보다 먼저 선언
# ============================================================

@router.post("/nts-status")
async def nts_status(body: dict):
    """
    국세청 사업자등록 상태조회.
    실제 NTS API: POST https://api.odcloud.kr/api/nts-businessman/v1/status

    Request body:
    {
      "b_no": "1234567890"   # 사업자등록번호 10자리 (- 자동 제거)
    }
    """
    b_no = str(body.get("b_no", "")).replace("-", "").replace(" ", "")
    if not b_no or len(b_no) != 10 or not b_no.isdigit():
        raise HTTPException(status_code=400, detail="b_no: 10자리 숫자여야 합니다 ('-' 제외).")

    result = await _nts_post("/status", {"b_no": [b_no]})
    items  = result.get("data", [])
    item   = items[0] if items else {}

    b_stt_cd  = item.get("b_stt_cd", "")
    status_map = {"01": "계속사업자", "02": "휴업자", "03": "폐업자"}

    return {
        "status": "success",
        "data": {
            "b_no":               b_no,
            "b_stt":              item.get("b_stt", ""),
            "b_stt_cd":           b_stt_cd,
            "b_stt_label":        status_map.get(b_stt_cd, item.get("b_stt", "")),
            "is_active":          b_stt_cd == "01",
            "is_closed":          b_stt_cd == "03",
            "tax_type":           item.get("tax_type", ""),
            "tax_type_cd":        item.get("tax_type_cd", ""),
            "end_dt":             item.get("end_dt", ""),
            "utcc_yn":            item.get("utcc_yn", ""),
            "tax_type_change_dt": item.get("tax_type_change_dt", ""),
            "invoice_apply_dt":   item.get("invoice_apply_dt", ""),
            "rbf_tax_type":       item.get("rbf_tax_type", ""),
            "rbf_tax_type_cd":    item.get("rbf_tax_type_cd", ""),
            "nts_status_code":    result.get("status_code"),
        }
    }


# ============================================================
# 1. 목록 조회
# ============================================================

@router.get("")
def get_companies(
    page:        int  = Query(default=1, ge=1),
    size:        int  = Query(default=20, ge=1, le=100),
    search:      Optional[str] = Query(default=None),
    status_code: Optional[str] = Query(default=None),
    sido:        Optional[str] = Query(default=None),
):
    supabase = get_supabase()
    query = supabase.table("companies").select("*", count="exact")

    if search:
        query = query.ilike("name", f"%{search}%")
    if status_code:
        query = query.eq("status_code", status_code)
    if sido:
        query = query.eq("address_sido", sido)

    offset = (page - 1) * size
    res = query.order("created_at", desc=True)\
               .range(offset, offset + size - 1)\
               .execute()

    return {
        "status": "success",
        "data": {
            "items":       res.data,
            "total":       res.count,
            "page":        page,
            "size":        size,
            "total_pages": -(-res.count // size) if res.count else 0,
        }
    }


# ============================================================
# 2. 사업장 등록
# ============================================================

@router.post("")
def create_company(req: CompanyCreate):
    supabase = get_supabase()

    # 사업자번호 중복 확인
    if req.business_number:
        dup = supabase.table("companies")\
            .select("id")\
            .eq("business_number", req.business_number)\
            .limit(1).execute()
        if dup.data:
            raise HTTPException(status_code=400, detail="이미 등록된 사업자번호입니다")

    # 법인번호 중복 확인
    if req.corporation_number:
        dup = supabase.table("companies")\
            .select("id")\
            .eq("corporation_number", req.corporation_number)\
            .limit(1).execute()
        if dup.data:
            raise HTTPException(status_code=400, detail="이미 등록된 법인번호입니다")

    now = datetime.now()
    company_code = f"COM-{now.strftime('%Y%m%d%H%M%S')}"

    data = {
        **req.dict(exclude_none=True),
        "company_code": company_code,
        "status_code":  "TRIAL",    # contract_status: 체험
        "is_active":    True,
        "created_at":   now.isoformat(),
        "updated_at":   now.isoformat(),
    }

    res = supabase.table("companies").insert(data).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="사업장 등록 실패")

    return {
        "status":  "success",
        "message": "사업장이 등록됐습니다",
        "data":    res.data[0],
    }


# ============================================================
# 3. 상세 조회
# ============================================================

@router.get("/{company_id}")
def get_company(company_id: str):
    supabase = get_supabase()
    res = supabase.table("companies")\
        .select("*")\
        .eq("id", company_id)\
        .single().execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="사업장을 찾을 수 없습니다")

    return {"status": "success", "data": res.data}


# ============================================================
# 4. 수정
# ============================================================

@router.patch("/{company_id}")
def update_company(company_id: str, req: CompanyUpdate):
    supabase = get_supabase()

    existing = supabase.table("companies")\
        .select("id").eq("id", company_id).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="사업장을 찾을 수 없습니다")

    update_data = {k: v for k, v in req.dict().items() if v is not None}
    update_data["updated_at"] = datetime.now().isoformat()

    res = supabase.table("companies")\
        .update(update_data).eq("id", company_id).execute()

    return {
        "status":  "success",
        "message": "사업장 정보가 수정됐습니다",
        "data":    res.data[0] if res.data else {},
    }


# ============================================================
# 5. 비활성화
# ============================================================

@router.delete("/{company_id}")
def delete_company(company_id: str):
    supabase = get_supabase()

    existing = supabase.table("companies")\
        .select("id").eq("id", company_id).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="사업장을 찾을 수 없습니다")

    supabase.table("companies").update({
        "is_active":   False,
        "status_code": "CANCELLED",   # contract_status: 해지
        "updated_at":  datetime.now().isoformat(),
    }).eq("id", company_id).execute()

    return {"status": "success", "message": "사업장이 비활성화됐습니다"}


# ============================================================
# 6. 소속 회원 목록
# ============================================================

@router.get("/{company_id}/users")
def get_company_users(company_id: str):
    supabase = get_supabase()
    res = supabase.table("users")\
        .select("id, name, email, phone, role_code, status_code, department, position, last_login_at")\
        .eq("company_id", company_id)\
        .order("created_at", desc=True).execute()

    return {"status": "success", "data": {"items": res.data, "total": len(res.data)}}


# ============================================================
# 7. 소속 시설 목록
# ============================================================

@router.get("/{company_id}/factories")
def get_company_factories(company_id: str):
    supabase = get_supabase()
    res = supabase.table("factories")\
        .select("id, name, site_type, address_road, employee_count, status_code, is_active")\
        .eq("company_id", company_id)\
        .order("created_at", desc=True).execute()

    return {"status": "success", "data": {"items": res.data, "total": len(res.data)}}
