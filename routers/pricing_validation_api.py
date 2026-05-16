# routers/pricing_validation_api.py — Pricing Validation & Audit Layer
"""
SaaS 가격 운영 안정화: Validation + Audit + Dangerous Guard.
Single Pricing Source: price_saas_plan + price_diagnosis_report.
Billing 플랫폼 아님. 운영 안전장치.
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pricing", tags=["가격검증"])


def _sb():
    from db.supabase_client import get_supabase
    return get_supabase()


# ═══ Validation ═══

@router.get("/validate")
def validate_pricing():
    """전체 Pricing 무결성 검증."""
    try:
        sb = _sb()
        issues = []

        # 1. price_saas_plan 검증
        plans = sb.table("price_saas_plan").select(
            "id,plan_code,plan_name,display_name,monthly_base_fee,is_active,is_recommended,sector_code,sort_order,features"
        ).execute()

        active_plans = [p for p in (plans.data or []) if p.get("is_active")]
        inactive_plans = [p for p in (plans.data or []) if not p.get("is_active")]

        # 활성 플랜 0개 → CRITICAL
        if not active_plans:
            issues.append({"severity": "CRITICAL", "type": "no_active_plans", "message": "활성 플랜이 0개입니다"})

        # 추천상품 0개
        recommended = [p for p in active_plans if p.get("is_recommended")]
        if not recommended:
            issues.append({"severity": "WARNING", "type": "no_recommended", "message": "활성 추천상품이 0개입니다"})

        # 비활성 추천상품
        for p in inactive_plans:
            if p.get("is_recommended"):
                issues.append({"severity": "WARNING", "type": "inactive_recommended",
                              "plan_code": p["plan_code"], "message": f"비활성 추천상품: {p['plan_code']}"})

        # display_name 누락
        for p in active_plans:
            if not p.get("display_name"):
                issues.append({"severity": "WARNING", "type": "missing_display_name",
                              "plan_code": p["plan_code"], "message": f"display_name 누락: {p['plan_code']}"})

        # features JSON 검증
        for p in active_plans:
            feat = p.get("features")
            if feat is not None and not isinstance(feat, (dict, list)):
                issues.append({"severity": "WARNING", "type": "invalid_features_json",
                              "plan_code": p["plan_code"], "message": f"features JSON 이상: {p['plan_code']}"})

        # sector별 활성 플랜 수
        sectors = {}
        for p in active_plans:
            s = p.get("sector_code", "UNKNOWN")
            sectors[s] = sectors.get(s, 0) + 1

        # 2. product_pricing ↔ price_saas_plan 정합성
        products = sb.table("product_pricing").select("plan_code,plan_name,price_monthly,is_active").execute()
        saas_codes = {p["plan_code"] for p in (plans.data or [])}

        for prod in (products.data or []):
            pc = prod.get("plan_code")
            if pc and pc not in saas_codes:
                issues.append({"severity": "WARNING", "type": "product_orphan",
                              "plan_code": pc, "message": f"product_pricing '{pc}' → saas_plan 미매칭"})
            elif pc and pc in saas_codes:
                saas = next((p for p in (plans.data or []) if p["plan_code"] == pc), {})
                saas_fee = float(saas.get("monthly_base_fee") or 0)
                prod_fee = float(prod.get("price_monthly") or 0)
                if saas_fee != prod_fee:
                    issues.append({"severity": "CRITICAL", "type": "price_mismatch",
                                  "plan_code": pc,
                                  "message": f"\uac00\uaca9 \ubd88\uc77c\uce58: product={int(prod_fee):,} vs saas={int(saas_fee):,}"})

        # 3. Payment 고\uc544 plan_code
        payments = sb.table("payments").select("plan_code,product_type") \
            .not_.is_("plan_code", "null").execute()
        payment_codes = set(p["plan_code"] for p in (payments.data or []))
        orphan_payment_codes = payment_codes - saas_codes
        # DIAG 코드는 진단 전용이므로 WARNING만
        for opc in orphan_payment_codes:
            sev = "INFO" if "DIAG" in opc.upper() else "WARNING"
            issues.append({"severity": sev, "type": "payment_orphan_plan",
                          "plan_code": opc, "message": f"payment plan_code '{opc}' \u2192 saas_plan \ubbf8\ub9e4\uce6d"})

        return {"status": "success", "data": {
            "total_plans": len(plans.data or []),
            "active_plans": len(active_plans),
            "recommended": len(recommended),
            "sectors": sectors,
            "issues": issues,
            "issue_count": len(issues),
            "critical_count": sum(1 for i in issues if i["severity"] == "CRITICAL"),
        }}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Payment Mapping ═══

@router.get("/payment-mapping")
def check_payment_mapping():
    """결제\uc0c1\ud488 \u2194 Pricing \ub9e4\ud551 \uac80\uc99d."""
    try:
        sb = _sb()
        products = sb.table("product_pricing").select("*").execute()
        saas = sb.table("price_saas_plan").select("plan_code,display_name,monthly_base_fee,is_active,sector_code").execute()
        saas_map = {p["plan_code"]: p for p in (saas.data or [])}

        mappings = []
        for prod in (products.data or []):
            pc = prod["plan_code"]
            matched = saas_map.get(pc)
            mappings.append({
                "product_plan_code": pc,
                "product_name": prod.get("plan_name"),
                "product_price": prod.get("price_monthly"),
                "product_active": prod.get("is_active"),
                "saas_matched": matched is not None,
                "saas_price": float(matched["monthly_base_fee"]) if matched else None,
                "saas_active": matched.get("is_active") if matched else None,
                "price_match": float(prod.get("price_monthly") or 0) == float(matched.get("monthly_base_fee") or 0) if matched else False,
            })

        return {"status": "success", "data": mappings}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Audit Log ═══

@router.get("/audit")
def get_audit_log(limit: int = 50):
    """\uac00\uaca9 \ubcc0\uacbd \uc774\ub825."""
    try:
        resp = _sb().table("pricing_audit_log").select("*") \
            .order("created_at", desc=True).limit(limit).execute()
        return {"status": "success", "data": resp.data or []}
    except Exception as e:
        return {"status": "error", "message": str(e)}


class AuditEntry(BaseModel):
    table_name: str = "price_saas_plan"
    record_id: str
    plan_code: Optional[str] = None
    action: str
    field_changed: Optional[str] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    changed_by: str = "admin"
    change_reason: Optional[str] = None


@router.post("/audit")
def create_audit_entry(body: AuditEntry):
    """\uac00\uaca9 \ubcc0\uacbd \uae30\ub85d \uc218\ub3d9 \ub4f1\ub85d."""
    try:
        _sb().table("pricing_audit_log").insert(body.dict()).execute()
        return {"status": "success", "message": "audit \uae30\ub85d \uc644\ub8cc"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Dangerous Operation Guard ═══

@router.get("/guard")
def check_dangerous_state():
    """\uc704\ud5d8 \uc6b4\uc601 \uc0c1\ud0dc \ud0d0\uc9c0."""
    try:
        sb = _sb()
        dangers = []

        # 1. \ud65c\uc131 \ud50c\ub79c 0\uac1c
        active = sb.table("price_saas_plan").select("id", count="exact").eq("is_active", True).execute()
        if (active.count or 0) == 0:
            dangers.append({"severity": "CRITICAL", "type": "all_plans_off", "message": "\ubaa8\ub4e0 \ud50c\ub79c \ube44\ud65c\uc131"})

        # 2. \ucd94\ucc9c\uc0c1\ud488 0\uac1c
        rec = sb.table("price_saas_plan").select("id", count="exact") \
            .eq("is_active", True).eq("is_recommended", True).execute()
        if (rec.count or 0) == 0:
            dangers.append({"severity": "WARNING", "type": "no_recommended", "message": "\ud65c\uc131 \ucd94\ucc9c\uc0c1\ud488 \uc5c6\uc74c"})

        # 3. sector\ubcc4 \ud65c\uc131 \ud50c\ub79c \uc5c6\uc74c
        plans = sb.table("price_saas_plan").select("sector_code,is_active").execute()
        all_sectors = set(p["sector_code"] for p in (plans.data or []) if p.get("sector_code"))
        active_sectors = set(p["sector_code"] for p in (plans.data or []) if p.get("is_active") and p.get("sector_code"))
        missing = all_sectors - active_sectors
        for s in missing:
            dangers.append({"severity": "CRITICAL", "type": "sector_no_plan",
                          "sector": s, "message": f"{s} \uc139\ud130 \ud65c\uc131 \ud50c\ub79c \uc5c6\uc74c"})

        # 4. product_pricing stale
        products = sb.table("product_pricing").select("plan_code,price_monthly").execute()
        saas = sb.table("price_saas_plan").select("plan_code,monthly_base_fee").execute()
        saas_map = {p["plan_code"]: float(p.get("monthly_base_fee") or 0) for p in (saas.data or [])}
        for prod in (products.data or []):
            pc = prod["plan_code"]
            if pc in saas_map and float(prod.get("price_monthly") or 0) != saas_map[pc]:
                dangers.append({"severity": "CRITICAL", "type": "price_mismatch",
                              "plan_code": pc, "message": f"product_pricing '{pc}' \uac00\uaca9 \ubd88\uc77c\uce58"})

        return {"status": "success", "data": {
            "dangers": dangers,
            "danger_count": len(dangers),
            "critical_count": sum(1 for d in dangers if d["severity"] == "CRITICAL"),
            "safe": len(dangers) == 0,
        }}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Summary ═══

@router.get("/summary")
def pricing_summary():
    """\uac00\uaca9 \uc6b4\uc601 \uc694\uc57d."""
    try:
        sb = _sb()
        saas = sb.table("price_saas_plan").select("plan_code,is_active,is_recommended,sector_code").execute()
        diag = sb.table("price_diagnosis_report").select("id", count="exact").execute()
        products = sb.table("product_pricing").select("id", count="exact").execute()
        audit = sb.table("pricing_audit_log").select("id", count="exact").execute()

        active = [p for p in (saas.data or []) if p.get("is_active")]
        sectors = {}
        for p in active:
            s = p.get("sector_code", "UNKNOWN")
            sectors[s] = sectors.get(s, 0) + 1

        return {"status": "success", "data": {
            "saas_plans_total": len(saas.data or []),
            "saas_plans_active": len(active),
            "saas_recommended": sum(1 for p in active if p.get("is_recommended")),
            "sectors": sectors,
            "diagnosis_tiers": diag.count or 0,
            "product_pricing": products.count or 0,
            "audit_entries": audit.count or 0,
        }}
    except Exception as e:
        return {"status": "error", "message": str(e)}
