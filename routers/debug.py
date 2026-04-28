"""임시 디버그 — billing_prepare 500 에러 traceback 캡처. 해결 후 삭제."""
import traceback
from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional

router = APIRouter(tags=["debug"])

class DebugBillingBody(BaseModel):
    user_id: str = "e6d6da1b-ec93-4a69-a570-a6dae9959427"
    product_type: str = "SAAS_BUILDING"
    amount: int = 1000
    goodname: str = "debug test"
    plan_code: str = "TEST"

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
