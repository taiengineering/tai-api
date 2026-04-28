"""임시 디버그 — PostgREST 우회: cancel_reason을 OID 저장소로 사용. 해결 후 삭제."""
import os
import traceback
from datetime import datetime
from uuid import uuid4
from fastapi import APIRouter
from pydantic import BaseModel
from db.supabase_client import get_supabase
from services.payment_helpers import now_iso

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
    }


@router.post("/debug/billing-test")
def debug_billing_test(body: DebugBillingBody):
    """PostgREST PGRST204 우회 테스트:
    inicis_order_id 대신 cancel_reason에 OID 저장 → 조회도 cancel_reason으로"""
    try:
        supabase = get_supabase()
        oid = f"TAI-BIL-{datetime.now():%Y%m%d%H%M%S}-{uuid4().hex[:6].upper()}"
        now = now_iso()
        supply_amount = round(body.amount / 1.1)
        vat_amount = body.amount - supply_amount

        # STEP 1: INSERT (inicis_order_id 없이, cancel_reason에 OID 저장)
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
            "cancel_reason": oid,
            "created_at": now,
            "updated_at": now,
        }

        res = supabase.table("subscriptions").insert(sub_row).execute()
        if not res.data:
            return {"status": "error", "step": "INSERT", "error_msg": "empty result"}

        subscription_id = res.data[0]["id"]

        # STEP 2: 조회 테스트 (cancel_reason으로 검색)
        lookup = (
            supabase.table("subscriptions")
            .select("id, status, cancel_reason")
            .eq("cancel_reason", oid)
            .limit(1)
            .execute()
        )

        lookup_ok = bool(lookup.data and lookup.data[0]["id"] == subscription_id)

        # STEP 3: 테스트 데이터 정리 (삭제)
        supabase.table("subscriptions").delete().eq("id", subscription_id).execute()

        return {
            "status": "success",
            "method": "cancel_reason as OID carrier (PostgREST bypass)",
            "step1_insert": "OK",
            "step2_lookup_by_cancel_reason": "OK" if lookup_ok else "FAIL",
            "step3_cleanup": "deleted",
            "subscription_id": subscription_id,
            "oid": oid,
        }
    except Exception as e:
        tb = traceback.format_exc()
        return {
            "status": "error",
            "error_type": type(e).__name__,
            "error_msg": str(e),
            "traceback": tb,
        }
