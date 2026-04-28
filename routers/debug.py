"""임시 디버그 — psycopg2 직접 SQL 테스트. 해결 후 삭제."""
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


@router.get("/debug/db-columns")
def debug_db_columns():
    """psycopg2로 실제 DB에서 subscriptions 컨럼 확인"""
    try:
        import psycopg2
        import psycopg2.extras
        url = os.environ.get("DATABASE_URL", "")
        conn = psycopg2.connect(url)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT column_name, data_type, is_nullable 
                FROM information_schema.columns 
                WHERE table_schema = 'public' AND table_name = 'subscriptions'
                ORDER BY ordinal_position
            """)
            cols = [dict(zip(['column_name','data_type','is_nullable'], r)) for r in cur.fetchall()]

            # inicis_order_id 없으면 자동 생성
            col_names = [c['column_name'] for c in cols]
            added = []
            if 'inicis_order_id' not in col_names:
                cur.execute("ALTER TABLE public.subscriptions ADD COLUMN inicis_order_id text")
                conn.commit()
                added.append('inicis_order_id')

            # billing_key_id NOT NULL 확인 및 수정
            bk = next((c for c in cols if c['column_name'] == 'billing_key_id'), None)
            if bk and bk['is_nullable'] == 'NO':
                cur.execute("ALTER TABLE public.subscriptions ALTER COLUMN billing_key_id DROP NOT NULL")
                conn.commit()
                added.append('billing_key_id_now_nullable')

        conn.close()
        return {"status": "ok", "columns": col_names, "auto_fixed": added}
    except Exception as e:
        return {"status": "error", "error": str(e), "traceback": traceback.format_exc()}


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

        found = find_subscription_by_oid(oid)
        lookup_ok = found and str(found["id"]) == sub_id

        supabase = get_supabase()
        supabase.table("subscriptions").delete().eq("id", sub_id).execute()

        return {
            "status": "success",
            "method": "psycopg2 direct SQL",
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
