# routers/payment_activation_api.py — Commercial Activation & E2E Validation
"""
결제 → 구독 → Tenant 활성화 E2E 검증 + 운영 Guard.
Billing 플랫폼 아님. 상업 활성화 안정성 레이어.
Single Pricing Source: price_saas_plan.

[2026-08-15 P0-보정1] 인증 경계 추가: 전 엔드포인트 SUPER_ADMIN(role_code==001).
  공용 자산 재사용: routers.matching_deps._require_admin (get_current_user + role 001).
  수동 활성화 감사 주체(changed_by)는 하드코딩 'admin' 대신 인증 사용자(current_user["id"])로 서버 확정.
  결제 business logic·PG flow 무변경 — 인증/감사주체만 보정.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends

from routers.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/payment", tags=["결제검증"])


def _sb():
    from db.supabase_client import get_supabase
    return get_supabase()


# ═══ E2E Chain Validation ═══

@router.get("/e2e-validate")
def validate_payment_e2e(current_user: dict = Depends(get_current_user)):
    """결제 → 구독 → Tenant 전체 흐름 검증."""
    try:
        sb = _sb()
        issues = []

        # 1. Payment 현황
        payments = sb.table("payments").select("id,status_code,plan_code,subscription_id,product_type,total_amount,user_id,company_id").execute()
        pay_data = payments.data or []
        pay_pending = [p for p in pay_data if p.get("status_code") == "PENDING"]
        pay_paid = [p for p in pay_data if p.get("status_code") == "PAID"]
        pay_no_sub = [p for p in pay_data if not p.get("subscription_id")]

        # 2. Subscription 현황
        subs = sb.table("subscriptions").select("id,status,plan_code,user_id,company_id,factory_id,started_at").execute()
        sub_data = subs.data or []
        sub_active = [s for s in sub_data if s.get("status") == "ACTIVE"]
        sub_pending = [s for s in sub_data if s.get("status") == "PENDING"]
        sub_no_factory = [s for s in sub_data if not s.get("factory_id")]

        # 3. Pricing Source 검증
        saas_plans = sb.table("price_saas_plan").select("plan_code,is_active,monthly_base_fee").execute()
        active_codes = {p["plan_code"] for p in (saas_plans.data or []) if p.get("is_active")}

        # 4. Issues 탐지
        # 결제 성공 0건
        if not pay_paid:
            issues.append({"severity": "CRITICAL", "type": "no_paid_payments",
                          "message": f"결제 성공 0건 (\uc804\uccb4 {len(pay_data)}건 \uc911 {len(pay_pending)}건 PENDING)"})

        # 활성 구독 0건
        if not sub_active:
            issues.append({"severity": "CRITICAL", "type": "no_active_subscriptions",
                          "message": f"활성 구독 0건 ({len(sub_pending)}건 PENDING)"})

        # 구독에 factory 미연결
        if sub_no_factory:
            issues.append({"severity": "WARNING", "type": "subscription_no_factory",
                          "message": f"구독 {len(sub_no_factory)}건에 factory 미연결"})

        # 결제에 구독 미연결
        if pay_no_sub:
            issues.append({"severity": "INFO", "type": "payment_no_subscription",
                          "message": f"결제 {len(pay_no_sub)}건에 subscription 미연결"})

        # 비활성 plan_code로 결제
        for p in pay_data:
            pc = p.get("plan_code")
            if pc and pc not in active_codes and "DIAG" not in (pc or "").upper():
                issues.append({"severity": "WARNING", "type": "payment_inactive_plan",
                              "plan_code": pc, "message": f"비활성 플랜 결제: {pc}"})

        # 중복 구독 (\ub3d9\uc77c user+plan 활\uc131)
        seen_user_plan = set()
        for s in sub_active:
            key = f"{s.get('user_id')}_{s.get('plan_code')}"
            if key in seen_user_plan:
                issues.append({"severity": "CRITICAL", "type": "duplicate_subscription",
                              "plan_code": s.get("plan_code"), "message": f"중복 활성 구독: {s.get('plan_code')}"})
            seen_user_plan.add(key)

        return {"status": "success", "data": {
            "payments": {"total": len(pay_data), "pending": len(pay_pending), "paid": len(pay_paid), "no_subscription": len(pay_no_sub)},
            "subscriptions": {"total": len(sub_data), "active": len(sub_active), "pending": len(sub_pending), "no_factory": len(sub_no_factory)},
            "pricing": {"active_plans": len(active_codes)},
            "issues": issues,
            "issue_count": len(issues),
            "critical_count": sum(1 for i in issues if i["severity"] == "CRITICAL"),
            "commercial_ready": len(pay_paid) > 0 and len(sub_active) > 0,
        }}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Commercial Activation Guard ═══

@router.get("/activation-guard")
def check_activation_guard(current_user: dict = Depends(get_current_user)):
    """상\uc5c5 \ud65c\uc131\ud654 \uc704\ud5d8 \ud0d0\uc9c0."""
    try:
        sb = _sb()
        dangers = []

        # 1. \ud65c\uc131 \ud50c\ub79c \uc5c6\uc74c
        active = sb.table("price_saas_plan").select("id", count="exact").eq("is_active", True).execute()
        if (active.count or 0) == 0:
            dangers.append({"severity": "CRITICAL", "type": "no_active_plans", "message": "\uacb0\uc81c \uac00\ub2a5\ud55c \ud65c\uc131 \ud50c\ub79c 0\uac1c"})

        # 2. TEST \ud50c\ub79c \uc874\uc7ac \ud655\uc778
        tests = sb.table("price_saas_plan").select("plan_code") \
            .eq("is_active", True).ilike("plan_code", "%TEST%").execute()
        if not tests.data:
            dangers.append({"severity": "WARNING", "type": "no_test_plans", "message": "TEST \ud50c\ub79c \uc5c6\uc74c (\uac80\uc99d \ubd88\uac00)"})

        # 3. KG\uc774\ub2c8\uc2dc\uc2a4 \uc2b9\uc778 \uc0c1\ud0dc (\uacb0\uc81c \uc131\uacf5 0\uac74\uc73c\ub85c \ud310\ub2e8)
        paid = sb.table("payments").select("id", count="exact").eq("status_code", "PAID").execute()
        if (paid.count or 0) == 0:
            dangers.append({"severity": "CRITICAL", "type": "pg_not_approved",
                          "message": "KG\uc774\ub2c8\uc2dc\uc2a4 \uc2b9\uc778 \ub300\uae30 \ub610\ub294 PG \uc5f0\ub3d9 \ubbf8\uc644\ub8cc (\uc131\uacf5 \uacb0\uc81c 0\uac74)"})

        # 4. Orphan \uacb0\uc81c (PAID\uc778\ub370 subscription \uc5c6\uc74c)
        orphan = sb.table("payments").select("id", count="exact") \
            .eq("status_code", "PAID").is_("subscription_id", "null").execute()
        if (orphan.count or 0) > 0:
            dangers.append({"severity": "CRITICAL", "type": "orphan_paid_no_sub",
                          "message": f"\uacb0\uc81c \uc131\uacf5\uc778\ub370 \uad6c\ub3c5 \ubbf8\uc5f0\uacb0: {orphan.count}\uac74"})

        # 5. \ud65c\uc131 \uad6c\ub3c5\uc778\ub370 factory \uc5c6\uc74c
        active_no_fac = sb.table("subscriptions").select("id", count="exact") \
            .eq("status", "ACTIVE").is_("factory_id", "null").execute()
        if (active_no_fac.count or 0) > 0:
            dangers.append({"severity": "CRITICAL", "type": "active_sub_no_factory",
                          "message": f"\ud65c\uc131 \uad6c\ub3c5\uc778\ub370 \uc0ac\uc5c5\uc7a5 \ubbf8\uc5f0\uacb0: {active_no_fac.count}\uac74"})

        return {"status": "success", "data": {
            "dangers": dangers,
            "danger_count": len(dangers),
            "critical_count": sum(1 for d in dangers if d["severity"] == "CRITICAL"),
            "safe": sum(1 for d in dangers if d["severity"] == "CRITICAL") == 0,
        }}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Status Summary ═══

@router.get("/status-summary")
def payment_status_summary(current_user: dict = Depends(get_current_user)):
    """\uacb0\uc81c/\uad6c\ub3c5 \uc0c1\ud0dc \uc694\uc57d."""
    try:
        sb = _sb()

        # Payment \uc0c1\ud0dc\ubcc4
        pay = sb.table("payments").select("status_code,product_type").execute()
        pay_status = {}
        pay_type = {}
        for p in (pay.data or []):
            s = p.get("status_code", "UNKNOWN")
            pay_status[s] = pay_status.get(s, 0) + 1
            t = p.get("product_type", "UNKNOWN")
            pay_type[t] = pay_type.get(t, 0) + 1

        # Subscription \uc0c1\ud0dc\ubcc4
        subs = sb.table("subscriptions").select("status,plan_code").execute()
        sub_status = {}
        for s in (subs.data or []):
            st = s.get("status", "UNKNOWN")
            sub_status[st] = sub_status.get(st, 0) + 1

        return {"status": "success", "data": {
            "payment_by_status": pay_status,
            "payment_by_type": pay_type,
            "subscription_by_status": sub_status,
            "total_payments": len(pay.data or []),
            "total_subscriptions": len(subs.data or []),
        }}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Activation Chain (\uad6c\ub3c5 \u2192 SaaS \ud65c\uc131\ud654) ═══

@router.post("/activate-subscription/{subscription_id}")
def activate_subscription(subscription_id: str, current_user: dict = Depends(get_current_user)):
    """\uad6c\ub3c5 \uc218\ub3d9 \ud65c\uc131\ud654 (\uc6b4\uc601\uc790 \uc804\uc6a9)."""
    try:
        sb = _sb()

        # 1. \uad6c\ub3c5 \ud655\uc778
        sub = sb.table("subscriptions").select("*").eq("id", subscription_id).limit(1).execute()
        if not sub.data:
            return {"status": "error", "message": "\uad6c\ub3c5\uc744 \ucc3e\uc744 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4"}

        s = sub.data[0]
        if s.get("status") == "ACTIVE":
            return {"status": "error", "message": "\uc774\ubbf8 \ud65c\uc131 \uc0c1\ud0dc\uc785\ub2c8\ub2e4"}

        # 2. plan_code \uac80\uc99d
        plan = sb.table("price_saas_plan").select("plan_code,display_name,monthly_base_fee,is_active,sector_code") \
            .eq("plan_code", s["plan_code"]).limit(1).execute()

        plan_valid = False
        plan_info = None
        if plan.data:
            plan_info = plan.data[0]
            plan_valid = plan_info.get("is_active", False)

        if not plan_valid:
            return {"status": "error", "message": f"\ube44\ud65c\uc131 \ud50c\ub79c: {s['plan_code']}. \ud65c\uc131\ud654 \ubd88\uac00."}

        # 3. \ud65c\uc131\ud654
        now = datetime.now(timezone.utc).isoformat()
        sb.table("subscriptions").update({
            "status": "ACTIVE",
            "started_at": now,
            "updated_at": now,
        }).eq("id", subscription_id).execute()

        # 4. Audit
        try:
            sb.table("pricing_audit_log").insert({
                "table_name": "subscriptions",
                "record_id": subscription_id,
                "plan_code": s["plan_code"],
                "action": "ACTIVATE",
                "old_value": s.get("status"),
                "new_value": "ACTIVE",
                "changed_by": current_user["id"],
                "change_reason": "\uc218\ub3d9 \ud65c\uc131\ud654",
            }).execute()
        except Exception:
            pass

        return {"status": "success", "message": f"{s['plan_code']} \uad6c\ub3c5 \ud65c\uc131\ud654 \uc644\ub8cc", "data": {
            "subscription_id": subscription_id,
            "plan_code": s["plan_code"],
            "sector": plan_info.get("sector_code") if plan_info else None,
            "status": "ACTIVE",
        }}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Orphan Detection ═══

@router.get("/orphans")
def detect_orphans(current_user: dict = Depends(get_current_user)):
    """\uace0\uc544 \uacb0\uc81c/\uad6c\ub3c5 \ud0d0\uc9c0."""
    try:
        sb = _sb()

        # PAID but no subscription
        paid_no_sub = sb.table("payments").select("id,plan_code,total_amount,paid_at") \
            .eq("status_code", "PAID").is_("subscription_id", "null").execute()

        # ACTIVE subscription but no factory
        active_no_fac = sb.table("subscriptions").select("id,plan_code,user_id,started_at") \
            .eq("status", "ACTIVE").is_("factory_id", "null").execute()

        # PENDING payment > 7 days
        week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        stale_pending = sb.table("payments").select("id,plan_code,created_at") \
            .eq("status_code", "PENDING").lt("created_at", week_ago).execute()

        return {"status": "success", "data": {
            "paid_no_subscription": paid_no_sub.data or [],
            "active_no_factory": active_no_fac.data or [],
            "stale_pending_payments": stale_pending.data or [],
        }}
    except Exception as e:
        return {"status": "error", "message": str(e)}
