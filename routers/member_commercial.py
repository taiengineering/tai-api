"""Member Commercial Read API — WO-FE-SAFE-01 + WO-COMM-V3-07C.

GET /me/commercial/contract
  현재 SaaS 이용계약 + CV + Site Scope.
  Auth: get_current_user. company_id = auth token 파생. DB write = 0.

GET /me/commercial/subscription
  RS1 정기결제 상태 + next_billing_at. payment_months=1 전용.

POST /me/commercial/subscription/cancel
  RS1 구독 해지. client subscription_id input = 0.

client company_id param = 없음.
admin commercial API 재사용 = 없음.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services import member_commercial_svc as svc
from services.member_commercial_svc import CommercialRuntimeStateInvalidError
from services import member_subscription_svc as sub_svc
from services.member_subscription_svc import MemberSubscriptionError

router = APIRouter(prefix="/me", tags=["회원 이용계약"])


@router.get("/commercial/contract")
def get_commercial_contract(
    current: dict = Depends(get_current_user),
):
    """현재 SaaS 이용계약 + CV + Site Scope. DB write = 0.

    company_id = auth token 파생. client param 없음.
    state: ACTIVE | NO_COMPANY | NO_ACTIVE_CONTRACT | ERROR
    """
    supabase = get_supabase()
    company_id = current.get("company_id")
    data = svc.get_member_commercial_contract(supabase, company_id)
    return {"status": "success", "data": data}


@router.get("/commercial/runtime-gate")
def get_runtime_gate(
    factory_id: Optional[str] = Query(None),
    site_id: Optional[str] = Query(None),
    current: dict = Depends(get_current_user),
):
    """Commercial V3 실행 게이트. entitlement + site scope 판정. DB write = 0.

    generation=COMMERCIAL_V3: can_execute=true|false + status
    generation=NOT_COMMERCIAL_V3: legacy fallback 신호 (SAFE가 /payments/tier-gate로 fallback)
    """
    supabase = get_supabase()
    company_id = current.get("company_id")
    try:
        data = svc.get_member_runtime_gate(
            supabase,
            company_id,
            factory_id=factory_id,
            site_id=site_id,
        )
    except CommercialRuntimeStateInvalidError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "COMMERCIAL_RUNTIME_STATE_INVALID", "reason": exc.code},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "success", "data": data}


def _get_contract_context(supabase, company_id: Optional[str]):
    """현재 contract_id + payment_months. contract 없으면 (None, None)."""
    if not company_id:
        return None, None
    ctx = svc.get_member_commercial_contract(supabase, company_id)
    if ctx.get("state") != "ACTIVE":
        return None, None
    contract = ctx.get("contract") or {}
    cv = ctx.get("commercial_version") or {}
    contract_id = str(contract.get("id") or "")
    payment_months = cv.get("payment_months")
    return contract_id or None, payment_months


@router.get("/commercial/subscription")
def get_commercial_subscription(
    current: dict = Depends(get_current_user),
):
    """RS1 정기결제 상태 조회. DB write = 0.

    payment_months=1 → subscription state + next_billing_at.
    payment_months≠1 → state=NOT_RECURRING.
    billing_key 원문 반환 없음.
    """
    supabase = get_supabase()
    company_id = current.get("company_id")
    contract_id, payment_months = _get_contract_context(supabase, company_id)
    data = sub_svc.get_member_subscription(
        supabase, company_id, contract_id, payment_months
    )
    return {"status": "success", "data": data}


class SubscriptionCancelBody(BaseModel):
    reason: Optional[str] = None


@router.post("/commercial/subscription/cancel")
def cancel_commercial_subscription(
    body: SubscriptionCancelBody,
    current: dict = Depends(get_current_user),
):
    """RS1 정기결제 해지. 다음 자동결제 중단.

    contract 활성/end_date 변경 없음. 환불 없음. Remote BillKey revoke = 0.
    client subscription_id input = 0. 서버가 contract → payment → subscription 파생.
    """
    supabase = get_supabase()
    company_id = current.get("company_id")
    contract_id, payment_months = _get_contract_context(supabase, company_id)
    try:
        data = sub_svc.cancel_member_subscription(
            supabase, company_id, contract_id, payment_months
        )
    except MemberSubscriptionError as exc:
        raise HTTPException(
            status_code=exc.http_status,
            detail={"code": exc.code, "message": exc.message},
        )
    return {"status": "success", "data": data}
