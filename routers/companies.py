#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TAI Companies 라우터 - 사업장 등록/관리 v2.4.0

v2.4.0: 회사 로고 업로드 — file_type='logo' 는 공개 버킷 company-logos 저장 + 영구 public URL + companies.logo_url 반영.
v2.3.0: 인증·회사 스코프 (P13). nts/check-biz 공개, onboarding·create 로그인,
        get_companies ALL 전용, by-id 14개는 자기 회사(_ensure_own_company).
v2.2.0: 어드민 전체 목록(get_companies)에서 데모(체험) 테넌트 제외 (companies.is_demo)
v2.1.0: 사업자번호 중복 확인 API 추가
  - GET /companies/check-biz?business_number=  사업자번호 중복 확인 (등록/미등록 + 회사명 반환)
v2.0.0: 담당자/파일/계약이력/온보딩 API 추가
"""

from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form, Depends
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import httpx
import os
import re
import uuid
from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services.company_scope import _ensure_own_company
from services.time import now_kst, serialize_business_datetime

router = APIRouter(prefix="/companies", tags=["companies"])

NTS_BASE_URL    = "https://api.odcloud.kr/api/nts-businessman/v1"
NTS_SERVICE_KEY = os.getenv(
    "NTS_BIZ_SERVICE_KEY",
    os.getenv("BUILDING_API_KEY", "da4e826323c2c9fef9f325bd4e39a3765d06ac1b582695bcbc475bc0a076255b")
)


async def _nts_post(endpoint: str, body: dict) -> dict:
    url     = f"{NTS_BASE_URL}{endpoint}"
    params  = {"serviceKey": NTS_SERVICE_KEY, "returnType": "JSON"}
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, params=params, json=body, headers=headers)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"국세청 API 오류 {e.response.status_code}: {e.response.text[:300]}")
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"국세청 API 연결 실패: {str(e)}")


# ============================================================
# 스키마
# ============================================================

class CompanyCreate(BaseModel):
    name:                Optional[str] = None
    company_name:        Optional[str] = None  # 프론트 별칭 → DB name
    company_type_code:   Optional[str] = "002"
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
    created_by:          Optional[str] = None


class CompanyUpdate(BaseModel):
    name:                Optional[str] = None
    company_name:        Optional[str] = None  # 프론트 별칭 → DB name
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
    status_code:         Optional[str] = None


class ContactBody(BaseModel):
    contact_type: str
    name:         str
    phone:        str
    email:        Optional[str] = None
    position:     Optional[str] = None
    is_primary:   bool = False


class ContactUpdate(BaseModel):
    contact_type: Optional[str] = None
    name:         Optional[str] = None
    phone:        Optional[str] = None
    email:        Optional[str] = None
    position:     Optional[str] = None
    is_primary:   Optional[bool] = None


class FileBody(BaseModel):
    file_type:  str
    file_name:  str
    file_url:   str
    file_size:  Optional[int] = None


class ContractUrlBody(BaseModel):
    contract_url: str


class OnboardingFactory(BaseModel):
    name:            str
    site_type:       Optional[str] = None
    ksic_code:       Optional[str] = None
    ksic_name:       Optional[str] = None
    address_road:    Optional[str] = None
    address_sido:    Optional[str] = None
    address_sigungu: Optional[str] = None
    employee_count:  Optional[int] = None


class OnboardingContact(BaseModel):
    contact_type: str = "대표담당자"
    name:         str
    phone:        str
    email:        Optional[str] = None
    position:     Optional[str] = None
    is_primary:   bool = True


class OnboardingBody(BaseModel):
    company_name:        str
    company_type_code:   Optional[str] = "002"
    business_number:     Optional[str] = None
    representative_name: Optional[str] = None
    contact_phone:       Optional[str] = None
    contact_email:       Optional[str] = None
    address_road:        Optional[str] = None
    address_sido:        Optional[str] = None
    address_sigungu:     Optional[str] = None
    zipcode:             Optional[str] = None
    factory:             Optional[OnboardingFactory] = None
    contacts:            List[OnboardingContact] = []


# ============================================================
# NTS 국세청 API  — /{company_id} 앞에 선언
# ============================================================

@router.post("/nts-verify")
async def nts_verify(body: dict):
    b_no = str(body.get("b_no", "")).replace("-", "").replace(" ", "")
    if not b_no or len(b_no) != 10 or not b_no.isdigit():
        raise HTTPException(status_code=400, detail="b_no: 10자리 숫자여야 합니다.")
    if not body.get("start_dt"):
        raise HTTPException(status_code=400, detail="start_dt: YYYYMMDD 형식의 개업일자가 필요합니다.")
    if not body.get("p_nm"):
        raise HTTPException(status_code=400, detail="p_nm: 대표자성명이 필요합니다.")
    biz_item = {
        "b_no":     b_no, "start_dt": str(body["start_dt"]).replace("-", ""),
        "p_nm":     body["p_nm"], "p_nm2":   body.get("p_nm2", ""),
        "b_nm":     body.get("b_nm", ""), "corp_no":  body.get("corp_no", ""),
        "b_sector": body.get("b_sector", ""), "b_type":   body.get("b_type", ""),
        "b_adr":    body.get("b_adr", ""),
    }
    result = await _nts_post("/validate", {"businesses": [biz_item]})
    items = result.get("data", [])
    item  = items[0] if items else {}
    return {
        "status": "success",
        "data": {
            "b_no":      b_no,
            "valid":     item.get("valid", ""),
            "valid_yn":  item.get("valid") == "01",
            "valid_msg": item.get("valid_msg", ""),
            "status":    item.get("status", {}),
            "nts_status_code": result.get("status_code"),
        }
    }


@router.post("/nts-status")
async def nts_status(body: dict):
    b_no = str(body.get("b_no", "")).replace("-", "").replace(" ", "")
    if not b_no or len(b_no) != 10 or not b_no.isdigit():
        raise HTTPException(status_code=400, detail="b_no: 10자리 숫자여야 합니다.")
    result = await _nts_post("/status", {"b_no": [b_no]})
    items  = result.get("data", [])
    item   = items[0] if items else {}
    b_stt_cd   = item.get("b_stt_cd", "")
    status_map = {"01": "계속사업자", "02": "휴업자", "03": "폐업자"}
    return {
        "status": "success",
        "data": {
            "b_no":            b_no,
            "b_stt":           item.get("b_stt", ""),
            "b_stt_cd":        b_stt_cd,
            "b_stt_label":     status_map.get(b_stt_cd, item.get("b_stt", "")),
            "is_active":       b_stt_cd == "01",
            "is_closed":       b_stt_cd == "03",
            "tax_type":        item.get("tax_type", ""),
            "tax_type_cd":     item.get("tax_type_cd", ""),
            "end_dt":          item.get("end_dt", ""),
            "nts_status_code": result.get("status_code"),
        }
    }


# ============================================================
# 사업자번호 중복 확인  GET /companies/check-biz  v2.1.0
# 고정 경로 — /{company_id} 앞에 반드시 먼저 선언
# ============================================================

@router.get("/check-biz")
def check_biz(business_number: str = Query(..., description="사업자등록번호 (하이픈 임의)")):
    """
    사업자번호 중복 확인.
    - available: true  → 사용 가능 (미등록)
    - available: false → 이미 등록된 번호 + 회사명 반환
    """
    supabase    = get_supabase()
    bn_clean    = re.sub(r'[^0-9]', '', business_number)

    if not bn_clean or len(bn_clean) != 10:
        raise HTTPException(
            status_code=400,
            detail="사업자등록번호는 10자리 숫자여야 합니다 (하이픈 제외)."
        )

    res = supabase.table("companies").select(
        "id, name, business_number, representative_name"
    ).eq("business_number", bn_clean).eq("is_active", True).limit(1).execute()

    if res.data:
        co = res.data[0]
        return {
            "status":    "success",
            "available": False,
            "message":   "이미 등록된 사업자등록번호입니다.",
            "data": {
                "exists":              True,
                "business_number":     bn_clean,
                "company_id":          co["id"],
                "company_name":        co["name"],
                "representative_name": co.get("representative_name", ""),
            }
        }

    return {
        "status":    "success",
        "available": True,
        "message":   "사용 가능한 사업자등록번호입니다.",
        "data": {
            "business_number": bn_clean,
        }
    }


# ============================================================
# 온보딩 통합 등록  POST /companies/onboarding
# ============================================================

@router.post("/onboarding")
def onboarding(req: OnboardingBody, current: dict = Depends(get_current_user)):
    """회사 + 시설 + 담당자를 한 번에 등록."""
    supabase = get_supabase()
    now      = now_kst()
    result: dict = {}

    # 1. 회사 등록
    company_data = {
        "name":              req.company_name,
        "company_type_code": req.company_type_code,
        "company_code":      f"COM-{now.strftime('%Y%m%d%H%M%S')}",
        "status_code":       "TRIAL",
        "is_active":         True,
        "created_at":        now.isoformat(),
        "updated_at":        now.isoformat(),
    }
    for f in ("business_number", "representative_name", "contact_phone",
              "contact_email", "address_road", "address_sido", "address_sigungu", "zipcode"):
        v = getattr(req, f, None)
        if v:
            company_data[f] = v

    comp_res = supabase.table("companies").insert(company_data).execute()
    if not comp_res.data:
        raise HTTPException(status_code=500, detail="회사 등록 실패")
    company_id = comp_res.data[0]["id"]
    result["company"] = comp_res.data[0]

    # 2. 담당자 등록
    if req.contacts:
        contact_rows = []
        for c in req.contacts:
            contact_rows.append({
                "company_id":   company_id,
                "contact_type": c.contact_type,
                "name":         c.name,
                "phone":        c.phone,
                "email":        c.email,
                "position":     c.position,
                "is_primary":   c.is_primary,
                "is_active":    True,
                "created_at":   now.isoformat(),
                "updated_at":   now.isoformat(),
            })
        c_res = supabase.table("company_contacts").insert(contact_rows).execute()
        result["contacts"] = c_res.data or []

    # 3. 시설 등록
    if req.factory:
        f = req.factory
        fac_data = {
            "company_id":     company_id,
            "name":           f.name,
            "factories_code": f"FAC-{now.strftime('%Y%m%d%H%M%S')}",
            "status_code":    "ACTIVE",
            "is_active":      True,
            "created_at":     now.isoformat(),
            "updated_at":     now.isoformat(),
        }
        for fld in ("site_type", "ksic_code", "ksic_name", "address_road",
                    "address_sido", "address_sigungu", "employee_count"):
            v = getattr(f, fld, None)
            if v is not None:
                fac_data[fld] = v
        fac_res = supabase.table("factories").insert(fac_data).execute()
        result["factory"] = fac_res.data[0] if fac_res.data else {}

    return {
        "status":  "success",
        "message": f'"회사 {req.company_name}" 등록 완료',
        "data":    result,
    }


# ============================================================
# 1. 목록 조회
#    어드민 전체 목록 — 데모(체험) 테넌트는 제외(companies.is_demo).
#    고객용 단건 조회(GET /companies/{id})는 제외하지 않는다(데모 계정이 자기 회사를 봐야 함).
# ============================================================

@router.get("")
def get_companies(
    page:        int  = Query(default=1, ge=1),
    size:        int  = Query(default=20, ge=1, le=100),
    search:      Optional[str] = Query(default=None),
    status_code: Optional[str] = Query(default=None),
    sido:        Optional[str] = Query(default=None),
    created_by:  Optional[str] = Query(default=None),
    current:     dict = Depends(get_current_user),
):
    supabase = get_supabase()
    query    = supabase.table("companies").select("*", count="exact")
    query    = query.eq("is_demo", False)  # 데모(체험) 테넌트 제외
    if search:      query = query.ilike("name", f"%{search}%")
    if status_code: query = query.eq("status_code", status_code)
    if sido:        query = query.eq("address_sido", sido)
    if created_by:  query = query.eq("created_by", created_by)
    offset = (page - 1) * size
    res = query.order("created_at", desc=True).range(offset, offset + size - 1).execute()
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
def create_company(req: CompanyCreate, current: dict = Depends(get_current_user)):
    supabase = get_supabase()
    display_name = (req.name or req.company_name or "").strip()
    if not display_name:
        raise HTTPException(status_code=400, detail="회사명(name 또는 company_name)이 필요합니다")

    if req.business_number:
        dup = supabase.table("companies").select("id").eq(
            "business_number", re.sub(r'[^0-9]', '', req.business_number)
        ).limit(1).execute()
        if dup.data:
            raise HTTPException(status_code=400, detail="이미 등록된 사업자번호입니다")
    if req.corporation_number:
        dup = supabase.table("companies").select("id").eq(
            "corporation_number", req.corporation_number
        ).limit(1).execute()
        if dup.data:
            raise HTTPException(status_code=400, detail="이미 등록된 법인번호입니다")
    now = now_kst()
    payload = req.dict(exclude_none=True)
    payload.pop("company_name", None)
    payload["name"] = display_name
    data = {
        **payload,
        "company_code": f"COM-{now.strftime('%Y%m%d%H%M%S')}",
        "status_code":  "TRIAL",
        "is_active":    True,
        "created_at":   now.isoformat(),
        "updated_at":   now.isoformat(),
    }
    res = supabase.table("companies").insert(data).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="사업장 등록 실패")
    return {"status": "success", "message": "사업장이 등록됐습니다", "data": res.data[0]}


# ============================================================
# 3. 상세 조회
# ============================================================

@router.get("/{company_id}")
def get_company(company_id: str, current: dict = Depends(get_current_user)):
    supabase = get_supabase()
    _ensure_own_company(company_id, current, supabase, "사업장을 찾을 수 없습니다")
    res = supabase.table("companies").select("*").eq("id", company_id).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="사업장을 찾을 수 없습니다")
    return {"status": "success", "data": res.data}


# ============================================================
# 4. 수정
# ============================================================

@router.patch("/{company_id}")
def update_company(company_id: str, req: CompanyUpdate, current: dict = Depends(get_current_user)):
    supabase = get_supabase()
    _ensure_own_company(company_id, current, supabase, "사업장을 찾을 수 없습니다")
    existing = supabase.table("companies").select("id").eq("id", company_id).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="사업장을 찾을 수 없습니다")
    update_data = {k: v for k, v in req.dict().items() if v is not None}
    if "company_name" in update_data:
        update_data["name"] = update_data.pop("company_name")
    update_data["updated_at"] = serialize_business_datetime(now_kst())
    res = supabase.table("companies").update(update_data).eq("id", company_id).execute()
    return {"status": "success", "message": "사업장 정보가 수정됐습니다", "data": res.data[0] if res.data else {}}


# ============================================================
# 5. 비활성화
# ============================================================

@router.delete("/{company_id}")
def delete_company(company_id: str, current: dict = Depends(get_current_user)):
    supabase = get_supabase()
    _ensure_own_company(company_id, current, supabase, "사업장을 찾을 수 없습니다")
    existing = supabase.table("companies").select("id").eq("id", company_id).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="사업장을 찾을 수 없습니다")
    supabase.table("companies").update({
        "is_active":   False,
        "status_code": "CANCELLED",
        "updated_at":  serialize_business_datetime(now_kst()),
    }).eq("id", company_id).execute()
    return {"status": "success", "message": "사업장이 비활성화됐습니다"}


# ============================================================
# 6. 소속 회원 목록
# ============================================================

@router.get("/{company_id}/users")
def get_company_users(company_id: str, current: dict = Depends(get_current_user)):
    supabase = get_supabase()
    _ensure_own_company(company_id, current, supabase, "사업장을 찾을 수 없습니다")
    res = supabase.table("users").select(
        "id, name, email, phone, role_code, status_code, department, position, last_login_at"
    ).eq("company_id", company_id).order("created_at", desc=True).execute()
    return {"status": "success", "data": {"items": res.data, "total": len(res.data)}}


# ============================================================
# 7. 소속 시설 목록
# ============================================================

@router.get("/{company_id}/factories")
def get_company_factories(company_id: str, current: dict = Depends(get_current_user)):
    supabase = get_supabase()
    _ensure_own_company(company_id, current, supabase, "사업장을 찾을 수 없습니다")
    res = supabase.table("factories").select(
        "id, name, site_type, address_road, employee_count, status_code, is_active"
    ).eq("company_id", company_id).order("created_at", desc=True).execute()
    return {"status": "success", "data": {"items": res.data, "total": len(res.data)}}


# ============================================================
# 8. 담당자 목록
# ============================================================

@router.get("/{company_id}/contacts")
def get_company_contacts(company_id: str, current: dict = Depends(get_current_user)):
    supabase = get_supabase()
    _ensure_own_company(company_id, current, supabase, "사업장을 찾을 수 없습니다")
    res = supabase.table("company_contacts").select("*").eq(
        "company_id", company_id
    ).eq("is_active", True).order("is_primary", desc=True).order("sort_order").execute()
    return {"status": "success", "data": {"items": res.data or [], "total": len(res.data or [])}}


# ============================================================
# 9. 담당자 추가
# ============================================================

@router.post("/{company_id}/contacts")
def add_company_contact(company_id: str, body: ContactBody, current: dict = Depends(get_current_user)):
    supabase = get_supabase()
    _ensure_own_company(company_id, current, supabase, "사업장을 찾을 수 없습니다")
    if body.is_primary:
        supabase.table("company_contacts").update({"is_primary": False}).eq(
            "company_id", company_id
        ).eq("is_primary", True).execute()
    now = serialize_business_datetime(now_kst())
    res = supabase.table("company_contacts").insert({
        "company_id":   company_id,
        "contact_type": body.contact_type,
        "name":         body.name,
        "phone":        body.phone,
        "email":        body.email,
        "position":     body.position,
        "is_primary":   body.is_primary,
        "is_active":    True,
        "created_at":   now,
        "updated_at":   now,
    }).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="담당자 등록 실패")
    return {"status": "success", "message": "담당자가 추가됐습니다.", "data": res.data[0]}


# ============================================================
# 10. 담당자 수정
# ============================================================

@router.patch("/{company_id}/contacts/{contact_id}")
def update_company_contact(company_id: str, contact_id: str, body: ContactUpdate, current: dict = Depends(get_current_user)):
    supabase = get_supabase()
    _ensure_own_company(company_id, current, supabase, "사업장을 찾을 수 없습니다")
    chk = supabase.table("company_contacts").select("id, is_primary").eq(
        "id", contact_id
    ).eq("company_id", company_id).limit(1).execute()
    if not chk.data:
        raise HTTPException(status_code=404, detail="담당자를 찾을 수 없습니다.")
    if body.is_primary is True:
        supabase.table("company_contacts").update({"is_primary": False}).eq(
            "company_id", company_id
        ).eq("is_primary", True).neq("id", contact_id).execute()
    update_data = {k: v for k, v in body.dict().items() if v is not None}
    update_data["updated_at"] = serialize_business_datetime(now_kst())
    res = supabase.table("company_contacts").update(update_data).eq("id", contact_id).execute()
    return {"status": "success", "message": "담당자가 수정됐습니다.", "data": res.data[0] if res.data else {}}


# ============================================================
# 11. 담당자 삭제
# ============================================================

@router.delete("/{company_id}/contacts/{contact_id}")
def delete_company_contact(company_id: str, contact_id: str, current: dict = Depends(get_current_user)):
    supabase = get_supabase()
    _ensure_own_company(company_id, current, supabase, "사업장을 찾을 수 없습니다")
    chk = supabase.table("company_contacts").select("id, is_primary").eq(
        "id", contact_id
    ).eq("company_id", company_id).limit(1).execute()
    if not chk.data:
        raise HTTPException(status_code=404, detail="담당자를 찾을 수 없습니다.")
    if chk.data[0].get("is_primary"):
        raise HTTPException(status_code=400, detail="대표담당자는 삭제할 수 없습니다. 다른 담당자를 대표담당자로 설정한 후 삭제하세요.")
    supabase.table("company_contacts").update({
        "is_active":  False,
        "updated_at": serialize_business_datetime(now_kst()),
    }).eq("id", contact_id).execute()
    return {"status": "success", "message": "담당자가 삭제됐습니다."}


# ============================================================
# 12. 계약 이력
# ============================================================

@router.get("/{company_id}/contracts")
def get_company_contracts(company_id: str, current: dict = Depends(get_current_user)):
    supabase = get_supabase()
    _ensure_own_company(company_id, current, supabase, "사업장을 찾을 수 없습니다")
    res = supabase.table("contracts").select(
        "id, contract_no, service_type, plan_code, status_code, "
        "start_date, end_date, contract_amount, total_amount, paid_amount, "
        "max_factory_count, max_user_count, is_active, created_at"
    ).eq("company_id", company_id).order("created_at", desc=True).execute()
    return {"status": "success", "data": {"items": res.data or [], "total": len(res.data or [])}}


# ============================================================
# 13. 파일 등록
# ============================================================

@router.post("/{company_id}/files")
def add_company_file(company_id: str, body: FileBody, current: dict = Depends(get_current_user)):
    supabase = get_supabase()
    _ensure_own_company(company_id, current, supabase, "사업장을 찾을 수 없습니다")
    now = serialize_business_datetime(now_kst())
    res = supabase.table("company_files").insert({
        "company_id":  company_id,
        "file_type":   body.file_type,
        "file_name":   body.file_name,
        "file_url":    body.file_url,
        "file_size":   body.file_size,
        "is_active":   True,
        "uploaded_at": now,
        "created_at":  now,
    }).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="파일 등록 실패")
    return {"status": "success", "message": "파일이 등록됐습니다.", "data": res.data[0]}


# ============================================================
# 13-b. 파일 업로드 (multipart 수신 → Storage 저장)
#   [13] 화면(useMyCompanyLicenseUpload)은 multipart(file, file_type)로
#   POST /companies/{id}/upload-file 을 부르는데 서버에 라우트가 없어 404 였다.
#   useTaiApi.upload() 가 res.ok 를 안 봐서(①과 같은 원인) 404 본문이 넘어오고
#   json?.data?.url || json?.url || 'uploaded' 가 'uploaded' 로 떨어져
#   "사업자등록증이 업로드됐습니다" 거짓 성공이 떴다 — 파일은 어디에도 없었다.
#   실제 파일을 Storage 에 올리고 company_files 메타를 남긴 뒤 data.url 을 돌려준다.
# ============================================================

@router.post("/{company_id}/upload-file")
async def upload_company_file(
    company_id: str,
    file: UploadFile = File(...),
    file_type: str = Form("business_license"),
    current: dict = Depends(get_current_user),
):
    supabase = get_supabase()
    _ensure_own_company(company_id, current, supabase, "회사를 찾을 수 없습니다.")

    chk = supabase.table("companies").select("id").eq("id", company_id).limit(1).execute()
    if not chk.data:
        raise HTTPException(status_code=404, detail="회사를 찾을 수 없습니다.")

    is_logo = (file_type == "logo")

    MAX_SIZE = (2 * 1024 * 1024) if is_logo else (10 * 1024 * 1024)
    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(
            status_code=400,
            detail=("로고 이미지는 최대 2MB까지 가능합니다." if is_logo else "파일 크기가 초과되었습니다. (최대 10MB)"),
        )

    if is_logo:
        allowed_types = ["image/png", "image/jpeg", "image/svg+xml", "image/webp"]
        if file.content_type not in allowed_types:
            raise HTTPException(status_code=400, detail="로고는 PNG, JPG, SVG, WEBP 이미지만 업로드 가능합니다.")
    else:
        allowed_types = ["application/pdf", "image/jpeg", "image/png"]
        if file.content_type not in allowed_types:
            raise HTTPException(status_code=400, detail="PDF, JPG, PNG 파일만 업로드 가능합니다.")

    ext = file.filename.split(".")[-1] if (file.filename and "." in file.filename) else "bin"
    # 로고는 공개 버킷 company-logos(영구 public URL), 그 외는 비공개 company-files(1년 signed URL).
    bucket = "company-logos" if is_logo else "company-files"
    storage_path = f"{company_id}/{file_type}/{uuid.uuid4()}.{ext}"

    try:
        supabase.storage.from_(bucket).upload(
            storage_path, content, {"content-type": file.content_type}
        )
        if is_logo:
            pub = supabase.storage.from_(bucket).get_public_url(storage_path)
            if isinstance(pub, dict):
                file_url = (
                    pub.get("publicUrl")
                    or pub.get("publicURL")
                    or pub.get("public_url")
                    or pub.get("url")
                    or ""
                )
            else:
                file_url = pub or ""
            if file_url and not file_url.startswith("http"):
                base = (os.getenv("SUPABASE_URL") or "").rstrip("/")
                sep = "" if file_url.startswith("/") else "/"
                file_url = f"{base}{sep}{file_url}"
            file_url = file_url.rstrip("?")
        else:
            # 비공개 버킷이므로 public URL 대신 signed URL(1년) 을 발급한다.
            signed = supabase.storage.from_(bucket).create_signed_url(
                storage_path, 60 * 60 * 24 * 365
            )
            signed_url = ""
            if isinstance(signed, dict):
                signed_url = (
                    signed.get("signedURL")
                    or signed.get("signedUrl")
                    or signed.get("signed_url")
                    or signed.get("url")
                    or ""
                )
            elif isinstance(signed, str):
                signed_url = signed
            if signed_url and not signed_url.startswith("http"):
                base = (os.getenv("SUPABASE_URL") or "").rstrip("/")
                sep = "" if signed_url.startswith("/") else "/"
                signed_url = f"{base}{sep}{signed_url}"
            file_url = signed_url
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"파일 업로드 실패: {str(e)}")

    now = serialize_business_datetime(now_kst())
    # 로고는 companies.logo_url 에 즉시 반영(프론트가 별도 PATCH 없이 표시).
    if is_logo:
        try:
            supabase.table("companies").update(
                {"logo_url": file_url, "updated_at": now}
            ).eq("id", company_id).execute()
        except Exception:
            pass
    # company_files 실측 컬럼에 맞춘다(storage_path 컬럼은 존재하지 않는다).
    meta = {
        "company_id":  company_id,
        "file_type":   file_type,
        "file_name":   file.filename,
        "file_url":    file_url,
        "file_size":   len(content),
        "is_active":   True,
        "uploaded_at": now,
        "created_at":  now,
    }
    ins = supabase.table("company_files").insert(meta).execute()
    record = ins.data[0] if ins.data else None

    return {
        "status": "success",
        "message": "파일이 업로드됐습니다.",
        "data": {
            "url":       file_url,
            "file_url":  file_url,
            "file_name": file.filename,
            "file_type": file_type,
            "file_size": len(content),
            "record":    record,
        },
    }


# ============================================================
# 14. 파일 삭제
# ============================================================

@router.delete("/{company_id}/files/{file_id}")
def delete_company_file(company_id: str, file_id: str, current: dict = Depends(get_current_user)):
    supabase = get_supabase()
    _ensure_own_company(company_id, current, supabase, "사업장을 찾을 수 없습니다")
    chk = supabase.table("company_files").select("id").eq(
        "id", file_id
    ).eq("company_id", company_id).limit(1).execute()
    if not chk.data:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    supabase.table("company_files").update({
        "is_active":  False,
        "updated_at": serialize_business_datetime(now_kst()),
    }).eq("id", file_id).execute()
    return {"status": "success", "message": "파일이 삭제됐습니다."}


# ============================================================
# 15. 전자계약서 URL
# ============================================================

@router.patch("/{company_id}/contract-url")
def set_contract_url(company_id: str, body: ContractUrlBody, current: dict = Depends(get_current_user)):
    supabase = get_supabase()
    _ensure_own_company(company_id, current, supabase, "회사를 찾을 수 없습니다.")
    chk = supabase.table("companies").select("id").eq("id", company_id).limit(1).execute()
    if not chk.data:
        raise HTTPException(status_code=404, detail="회사를 찾을 수 없습니다.")
    now = serialize_business_datetime(now_kst())
    exist = supabase.table("company_files").select("id").eq(
        "company_id", company_id
    ).eq("file_type", "contract_url").limit(1).execute()
    if exist.data:
        supabase.table("company_files").update({
            "file_url":    body.contract_url,
            "is_active":   True,
            "updated_at":  now,
        }).eq("id", exist.data[0]["id"]).execute()
    else:
        supabase.table("company_files").insert({
            "company_id":  company_id,
            "file_type":   "contract_url",
            "file_name":   "전자계약서",
            "file_url":    body.contract_url,
            "is_active":   True,
            "uploaded_at": now,
            "created_at":  now,
        }).execute()
    return {"status": "success", "message": "전자계약서 URL이 저장됐습니다.", "data": {"contract_url": body.contract_url}}
