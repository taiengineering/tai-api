# routers/pricing_validation_api.py — Pricing Validation & Audit Layer
"""
SaaS 가격 운영 안정화: Validation + Audit + Dangerous Guard.
Single Pricing Source: **price_master** (price_saas_plan / price_diagnosis_report = price_master 위 호환 뷰).
2026-07-23: 정본을 price_master(A) 단일로 확정(서비스=SaaS+법령진단). 레거시 product_pricing 교차검증 제거(테이블 격리 준비).
Billing 플랫폼 아님. 운영 안전장치.
"""

import logging
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
    """price_master 기반 price_saas_plan 무결성 검증."""
    try:
        sb = _sb()
        issues = []

        plans = sb.table("price_saas_plan").select(
            "id,plan_code,plan_name,display_name,monthly_base_fee,is_active,is_recommended,sector_code,sort_order,features"
        ).execute()

        active_plans = [p for p in (plans.data or []) if p.get("is_active")]
        inactive_plans = [p for p in (plans.data or []) if not p.get("is_active")]

        if not active_plans:
            issues.append({"severity": "CRITICAL", "type": "no_active_plans", "message": "활성 플랜이 0개입니다"})

        recommended = [p for p in active_plans if p.get("is_recommended")]
        if not recommended:
            issues.append({"severity": "WARNING", "type": "no_recommended", "message": "활성 추천상품이 0개입니다"})

        for p in inactive_plans:
            if p.get("is_recommended"):
                issues.append({"severity": "WARNING", "type": "inactive_recommended",
                               "plan_code": p.get("plan_code"), "message": f"비활성 추천상품: {p.get('plan_code')}"})

        for p in active_plans:
            if not p.get("display_name"):
                issues.append({"severity": "WARNING", "type": "missing_display_name",
                               "plan_code": p.get("plan_code"), "message": f"display_name 누락: {p.get('plan_code')}"})

        for p in active_plans:
            feat = p.get("features")
            if feat is not None and not isinstance(feat, (dict, list)):
                issues.append({"severity": "WARNING", "type": "invalid_features_json",
                               "plan_code": p.get("plan_code"), "message": f"features JSON 이상: {p.get('plan_code')}"})

        sectors = {}
        for p in active_plans:
            s = p.get("sector_code", "UNKNOWN")
            sectors[s] = sectors.get(s, 0) + 1

        # Payment 고아 plan_code (product_pricing 교차검증은 2026-07-23 제거)
        payments = sb.table("payments").select("plan_code,product_type") \
            .not_.is_("plan_code", "null").execute()
        saas_codes = {p["plan_code"] for p in (plans.data or [])}
        payment_codes = set(p["plan_code"] for p in (payments.data or []))
        for opc in (payment_codes - saas_codes):
            sev = "INFO" if "DIAG" in opc.upper() else "WARNING"
            issues.append({"severity": sev, "type": "payment_orphan_plan",
                           "plan_code": opc, "message": f"payment plan_code '{opc}' → saas_plan 미매칭"})

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


# ═══ Payment Mapping (deprecated) ═══

@router.get("/payment-mapping")
def check_payment_mapping():
    """[deprecated 2026-07-23] product_pricing 격리(A 단일 SSOT)로 교차매핑 폐기. price_saas_plan 목록만 반환."""
    try:
        sb = _sb()
        saas = sb.table("price_saas_plan").select(
            "plan_code,display_name,monthly_base_fee,is_active,sector_code"
        ).execute()
        return {"status": "success", "data": [], "note": "product_pricing 격리 — 정본 price_master 단일. 매핑 검증 폐기.",
                "saas_plans": saas.data or []}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Audit Log ═══

@router.get("/audit")
def get_audit_log(limit: int = 50):
    """가격 변경 이력."""
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
    """가격 변경 기록 수동 등록."""
    try:
        _sb().table("pricing_audit_log").insert(body.dict()).execute()
        return {"status": "success", "message": "audit 기록 완료"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Dangerous Operation Guard ═══

@router.get("/guard")
def check_dangerous_state():
    """위험 운영 상태 탐지 (price_master 기반)."""
    try:
        sb = _sb()
        dangers = []

        active = sb.table("price_saas_plan").select("id", count="exact").eq("is_active", True).execute()
        if (active.count or 0) == 0:
            dangers.append({"severity": "CRITICAL", "type": "all_plans_off", "message": "모든 플랜 비활성"})

        rec = sb.table("price_saas_plan").select("id", count="exact") \
            .eq("is_active", True).eq("is_recommended", True).execute()
        if (rec.count or 0) == 0:
            dangers.append({"severity": "WARNING", "type": "no_recommended", "message": "활성 추천상품 없음"})

        plans = sb.table("price_saas_plan").select("sector_code,is_active").execute()
        all_sectors = set(p["sector_code"] for p in (plans.data or []) if p.get("sector_code"))
        active_sectors = set(p["sector_code"] for p in (plans.data or []) if p.get("is_active") and p.get("sector_code"))
        for s in (all_sectors - active_sectors):
            dangers.append({"severity": "CRITICAL", "type": "sector_no_plan",
                            "sector": s, "message": f"{s} 섹터 활성 플랜 없음"})

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
    """가격 운영 요약 (price_master 기반)."""
    try:
        sb = _sb()
        saas = sb.table("price_saas_plan").select("plan_code,is_active,is_recommended,sector_code").execute()
        diag = sb.table("price_diagnosis_report").select("id", count="exact").execute()
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
            "audit_entries": audit.count or 0,
        }}
    except Exception as e:
        return {"status": "error", "message": str(e)}
