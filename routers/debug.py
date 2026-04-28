"""임시 디버그 — direct_sql 모듈 테스트. 해결 후 삭제."""
import os
import traceback
from datetime import datetime
from uuid import uuid4
from fastapi import APIRouter
from pydantic import BaseModel
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
    db_url = os.environ.get("DATABASE_URL", "NOT_SET")
    return {
        "DATABASE_URL": db_url[:30] + "..." if len(db_url) > 30 else db_url,
        "DATABASE_URL_set": db_url != "NOT_SET" and len(db_url) > 10,
    }


@router.post("/debug/billing-test")
def debug_billing_test(body: DebugBillingBody):
    """psycopg2 직접 SQL로 subscriptions INSERT/SELECT 테스트"""
    try:
        from db.direct_sql import insert_subscription, find_subscription_by_oid
        from db.supabase_client import get_supabase

        oid = f"TAI-BIL-{datetime.now():%Y%m%d%H%M%S}-{uuid4().hex[:6].upper()}"
        now = now_iso()
        supply = round(body.amount / 1.1)
        vat = body.amount - supply

        # STEP 1: 직접 SQL INSERT (PostgREST 우회)
        row = insert_subscription({
            "user_id": body.user_id,
            "product_type": body.product_type,
            "plan_code": body.plan_code,
            "plan_name": body.goodname,
            "amount": body.amount,
            "supply_amount": supply,
            "vat_amount": vat,
            "billing_cycle": "monthly",
            "status": "PENDING",
            "inicis_order_id": oid,
            "created_at": now,
            "updated_at": now,
        })
        sub_id = str(row.get("id", ""))

        # STEP 2: 직접 SQL SELECT by inicis_order_id
        found = find_subscription_by_oid(oid)
        lookup_ok = found and str(found["id"]) == sub_id

        # STEP 3: PostgREST로 id 기반 삭제 (이건 된다)
        supabase = get_supabase()
        supabase.table("subscriptions").delete().eq("id", sub_id).execute()

        return {
            "status": "success",
            "method": "psycopg2 direct SQL (PostgREST bypass)",
            "step1_insert": "OK",
            "step2_lookup": "OK" if lookup_ok else "FAIL",
            "step3_cleanup": "deleted",
            "subscription_id": sub_id,
            "oid": oid,
        }
    except Exception as e:
        return {
            "status": "error",
            "error_type": type(e).__name__,
            "error_msg": str(e),
            "traceback": traceback.format_exc(),
        }
