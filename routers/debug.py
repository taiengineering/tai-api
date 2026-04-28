"""임시 디버그 — PostgREST 우회 방식 테스트. 해결 후 삭제."""
import os
import traceback
from datetime import datetime
from uuid import uuid4
from fastapi import APIRouter
from pydantic import BaseModel
from db.supabase_client import get_supabase
from services.payment_helpers import now_iso, sha256, ts_ms

router = APIRouter(tags=["debug"])


class DebugBillingBody(BaseModel):
    user_id: str = "e6d6da1b-ec93-4a69-a570-a6dae9959427"
    product_type: str = "SAAS_BUILDING"
    amount: int = 1000
    goodname: str = "debug test"
    plan_code: str = "TEST"


@router.get("/debug/env-check")
def debug_env_check():
    supabase_url = os.environ.get("SUPABASE_URL", "NOT_SET")
    return {
        "SUPABASE_URL": supabase_url[:40] + "..." if len(supabase_url) > 40 else supabase_url,
        "SUPABASE_URL_contains_vwlahtg": "vwlahtg" in supabase_url,
        "INICIS_BILLING_MID": (os.environ.get("INICIS_BILLING_MID") or "NOT_SET")[:6] + "...",
    }


@router.post("/debug/billing-test")
def debug_billing_test(body: DebugBillingBody):
    """PostgREST 우회: inicis_order_id 없이 INSERT → RPC로 업데이트"""
    try:
        supabase = get_supabase()
        oid = f"TAI-BIL-{datetime.now():%Y%m%d%H%M%S}-{uuid4().hex[:6].upper()}"
        now = now_iso()
        supply_amount = round(body.amount / 1.1)
        vat_amount = body.amount - supply_amount

        # STEP 1: inicis_order_id 없이 INSERT (PostgREST가 아는 컬럼만)
        sub_row = {
            "user_id": body.user_id,
            "product_type": body.product_type,
            "plan_code": body.plan_code,
            "plan_name": body.goodname,
            "amount": body.amount,
            "supply_amount": supply_amount,
            "vat_amount": vat_amount,
            "billing_cycle": "monthly",
            "status": "PENDING",
            "created_at": now,
            "updated_at": now,
        }

        res = supabase.table("subscriptions").insert(sub_row).execute()
        if not res.data:
            return {"status": "error", "step": 1, "error_msg": "INSERT returned empty"}

        subscription_id = res.data[0]["id"]

        # STEP 2: inicis_order_id를 RPC로 업데이트 (PostgREST 캐시 우회)
        update_res = supabase.rpc("update_subscription_oid", {
            "sub_id": subscription_id,
            "oid": oid,
        }).execute()

        return {
            "status": "success",
            "method": "2-step: INSERT without oid + RPC update",
            "subscription_id": subscription_id,
            "oid": oid,
            "step1_insert": "OK",
            "step2_rpc_update": update_res.data,
        }
    except Exception as e:
        tb = traceback.format_exc()
        return {
            "status": "error",
            "error_type": type(e).__name__,
            "error_msg": str(e),
            "traceback": tb,
        }
