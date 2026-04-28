"""임시 디버그 — billing 500 에러 진단 + RPC 우회 테스트. 해결 후 삭제."""
import os
import traceback
import json as _json
from fastapi import APIRouter
from pydantic import BaseModel
from db.supabase_client import get_supabase

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
    """RPC 방식으로 빌링 prepare 테스트 (PostgREST 캐시 우회)"""
    try:
        from services.payment_helpers import now_iso, sha256, ts_ms
        from datetime import datetime
        from uuid import uuid4

        supabase = get_supabase()

        mid = os.environ.get("INICIS_BILLING_MID", "")
        sign_key = os.environ.get("INICIS_BILLING_SIGN_KEY", "")
        if not mid or not sign_key:
            return {"status": "error", "error_msg": "INICIS_BILLING_MID or SIGN_KEY not set"}

        oid = f"TAI-BIL-{datetime.now():%Y%m%d%H%M%S}-{uuid4().hex[:6].upper()}"
        now = now_iso()
        supply_amount = round(body.amount / 1.1)
        vat_amount = body.amount - supply_amount

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
            "inicis_order_id": oid,
            "created_at": now,
            "updated_at": now,
        }

        # RPC 방식으로 INSERT (PostgREST 스키마 캐시 우회)
        rpc_res = supabase.rpc("create_subscription", {"data": sub_row}).execute()
        rpc_data = rpc_res.data

        if not rpc_data:
            return {"status": "error", "error_msg": "RPC returned empty"}

        subscription_id = rpc_data.get("id") if isinstance(rpc_data, dict) else rpc_data

        # 테스트 데이터 정리 (PENDING 상태로 남겨두면 문제없음)
        return {
            "status": "success",
            "method": "RPC (PostgREST cache bypass)",
            "subscription_id": subscription_id,
            "oid": oid,
            "rpc_data": rpc_data,
        }
    except Exception as e:
        tb = traceback.format_exc()
        return {
            "status": "error",
            "error_type": type(e).__name__,
            "error_msg": str(e),
            "traceback": tb,
        }
