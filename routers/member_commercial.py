"""Member Commercial Read API — WO-FE-SAFE-01.

GET /me/commercial/contract
  현재 SaaS 이용계약 + CV + Site Scope.
  Auth: get_current_user. company_id = auth token 파생. DB write = 0.

client company_id param = 없음.
admin commercial API 재사용 = 없음.
"""
from fastapi import APIRouter, Depends

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
