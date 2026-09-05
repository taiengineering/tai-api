"""회원 회사정보 API (BACKEND-1) — GET/PUT /me/company.

- 신원/ownership 은 Bearer 토큰(get_current_user -> public.users row)에서만 파생.
  client 가 company_id/user_id 를 보낼 수 없다(Pydantic extra=forbid).
- GET: 자기 회사 반환(없으면 data=null, 404 아님).
- PUT: 회사 법적정보 수정/생성. 역할 001/002/010 만 허용.
- SoT=public.companies. payments/tax_invoice_requests 는 건드리지 않는다.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services import member_company_svc as svc

router = APIRouter(prefix="/me", tags=["회원 회사정보"])

# 회사 법적정보 수정 허용 역할: 최고관리자/관리자/대표이사
PUT_ALLOWED_ROLES = {"001", "002", "010"}


class MemberCompanyBody(BaseModel):
    name: Optional[str] = None
    business_number: Optional[str] = None
    representative_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    zipcode: Optional[str] = None
    address_road: Optional[str] = None
    address_detail: Optional[str] = None
    business_type: Optional[str] = None
    business_category: Optional[str] = None

    class Config:
        extra = "forbid"  # company_id/user_id/created_by/status_code/company_code 등 주입 거부


@router.get("/company")
def get_my_company(current_user: dict = Depends(get_current_user)):
    """자기 회사정보 조회. company_id 없으면 data=null(정상)."""
    if not current_user.get("id"):
        raise HTTPException(status_code=401, detail="사용자 식별에 실패했습니다.")
    sb = get_supabase()
    data = svc.get_member_company(sb, current_user)
    return {"status": "success", "data": data}


@router.put("/company")
def put_my_company(body: MemberCompanyBody, current_user: dict = Depends(get_current_user)):
    """자기 회사정보 수정/생성(company-less 는 생성+연결). 역할 게이팅."""
    if not current_user.get("id"):
        raise HTTPException(status_code=401, detail="사용자 식별에 실패했습니다.")
    role = (current_user.get("role_code") or "").strip()
    if role not in PUT_ALLOWED_ROLES:
        raise HTTPException(status_code=403, detail="회사정보 수정 권한이 없습니다.")

    sb = get_supabase()
    payload = body.dict(exclude_unset=True)  # 전달된 필드만 -> 부분수정
    try:
        data = svc.upsert_member_company(sb, current_user, payload)
    except svc.MemberCompanyError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e
    return {"status": "success", "data": data}
