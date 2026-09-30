"""Member Commercial Read API — WO-FE-SAFE-01.

GET /me/commercial/contract
  현재 SaaS 이용계약 + CV + Site Scope.
  Auth: get_current_user. company_id = auth token 파생. DB write = 0.

client company_id param = 없음.
admin commercial API 재사용 = 없음.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services import member_commercial_svc as svc

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
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "success", "data": data}
