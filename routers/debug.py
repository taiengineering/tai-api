"""임시 디버그 — billing_prepare 500 에러 traceback 캡처 + Supabase URL 확인. 해결 후 삭제."""
import os
import traceback
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["debug"])


class DebugBillingBody(BaseModel):
    user_id: str = "e6d6da1b-ec93-4a69-a570-a6dae9959427"
    product_type: str = "SAAS_BUILDING"
    amount: int = 1000
    goodname: str = "debug test"
    plan_code: str = "TEST"


@router.get("/debug/env-check")
def debug_env_check():
    """Railway 환경변수 확인 (값은 마스킹). 해결 후 삭제."""
    supabase_url = os.environ.get("SUPABASE_URL", "NOT_SET")
    return {
        "SUPABASE_URL": supabase_url[:40] + "..." if len(supabase_url) > 40 else supabase_url,
        "SUPABASE_URL_contains_vwlahtg": "vwlahtg" in supabase_url,
        "SUPABASE_URL_contains_xntdkrj": "xntdkrj" in supabase_url,
        "SUPABASE_SERVICE_KEY": "SET" if os.environ.get("SUPABASE_SERVICE_KEY") else "NOT_SET",
        "SUPABASE_KEY": "SET" if os.environ.get("SUPABASE_KEY") else "NOT_SET",
        "INICIS_BILLING_MID": os.environ.get("INICIS_BILLING_MID", "NOT_SET")[:6] + "..." if os.environ.get("INICIS_BILLING_MID") else "NOT_SET",
        "INICIS_BILLING_SIGN_KEY": "SET" if os.environ.get("INICIS_BILLING_SIGN_KEY") else "NOT_SET",
        "INICIS_BILLING_INIAPI_KEY": "SET" if os.environ.get("INICIS_BILLING_INIAPI_KEY") else "NOT_SET",
        "INICIS_CLIENT_IP": os.environ.get("INICIS_CLIENT_IP", "NOT_SET"),
    }


@router.post("/debug/billing-test")
def debug_billing_test(body: DebugBillingBody):
    try:
        from routers.payment_billing import billing_prepare, BillingPrepareBody
        test_body = BillingPrepareBody(
            user_id=body.user_id,
            product_type=body.product_type,
            amount=body.amount,
            goodname=body.goodname,
            plan_code=body.plan_code,
        )
        result = billing_prepare(test_body)
        return {"status": "success", "data": result}
    except Exception as e:
        tb = traceback.format_exc()
        return {
            "status": "error",
            "error_type": type(e).__name__,
            "error_msg": str(e),
            "traceback": tb,
        }
