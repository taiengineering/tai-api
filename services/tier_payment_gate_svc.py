"""Authenticated SaaS tier gate — READ + RESOLVE + COMPARE only.

WO-COMMON-TIER-PAYMENT-GATE-MODULARIZE-001 / B2.
mutation 0. 결제·계약·구독·LEG 실행 0. 금액(delta/VAT) 0 — 그건 B3.
필요 플랜은 B1 resolve_plan 을 직접 호출한다(공식 복제 금지).
"""
from __future__ import annotations

from services.pricing_resolver_svc import load_prices, resolve_plan

# construction_sites.contract_amount 는 억원. price_master criteria 는 원.
_EOK_TO_WON = 100_000_000

_FACTORY_SECTORS = frozenset({"INDUSTRY", "BUILDING"})
_SITE_SECTORS = frozenset({"CONSTRUCTION"})

_PLAN_VIEW_KEYS = ("tier_code", "display_name", "sort_order", "amount", "billing_unit")


class TierGateError(Exception):
    """도메인 오류. code 를 라우터가 HTTP 로 번역한다."""

    def __init__(self, code: str, message: str = ""):
        self.code = code
        self.message = message or code
        super().__init__(self.message)


def evaluate_saas_tier_gate(supabase, current, *, factory_id=None, site_id=None) -> dict:
    """현재 계약 tier vs 필요 tier. current 는 인증 주체(ownership 은 라우터)."""
    _ = current
    fid = _id_or_none(factory_id)
    sid = _id_or_none(site_id)
    if (fid is None) == (sid is None):
        raise TierGateError(
            "INVALID_TARGET",
            "factory_id 또는 site_id 중 하나만 전달해야 합니다.",
        )

    if fid:
        entity = _load_factory(supabase, fid)
        target = "factory"
    else:
        entity = _load_site(supabase, sid)
        target = "site"

    company_id = entity.get("company_id")
    contract = _load_unique_active_saas(supabase, company_id)
    current_plan = _match_current_plan(supabase, contract.get("plan_code"))
    sector = (current_plan.get("sector") or "").strip().upper()

    if target == "factory" and sector not in _FACTORY_SECTORS:
        raise TierGateError(
            "ENTITY_SECTOR_MISMATCH",
            "대상과 계약 업종이 일치하지 않습니다.",
        )
    if target == "site" and sector not in _SITE_SECTORS:
        raise TierGateError(
            "ENTITY_SECTOR_MISMATCH",
            "대상과 계약 업종이 일치하지 않습니다.",
        )

    metric, pricing_value = _metric_for(sector, entity)
    resolved = resolve_plan(supabase, "SAAS", sector, pricing_value)
    if resolved.get("status") != "success" or not resolved.get("data"):
        raise TierGateError("PRICING_NOT_FOUND", "필요 플랜을 산정할 수 없습니다.")
    required_plan = resolved["data"]

    current_order = _sort_order(current_plan)
    required_order = _sort_order(required_plan)
    status = "FIT" if current_order >= required_order else "UPGRADE_REQUIRED"

    return {
        "status": status,
        "sector": sector,
        "current_plan": _plan_view(current_plan),
        "required_plan": _plan_view(required_plan),
        "metric": metric,
    }


def _id_or_none(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _load_factory(supabase, factory_id: str) -> dict:
    rows = (
        supabase.table("factories")
        .select("id, company_id, employee_count, building_area")
        .eq("id", factory_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows:
        raise TierGateError("ENTITY_NOT_FOUND", "시설을 찾을 수 없습니다")
    return rows[0]


def _load_site(supabase, site_id: str) -> dict:
    rows = (
        supabase.table("construction_sites")
        .select("id, company_id, contract_amount")
        .eq("id", site_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows:
        raise TierGateError("ENTITY_NOT_FOUND", "현장을 찾을 수 없습니다.")
    return rows[0]


def _load_unique_active_saas(supabase, company_id) -> dict:
    if not company_id:
        raise TierGateError("NO_ACTIVE_SAAS_CONTRACT", "활성 SaaS 계약이 없습니다.")
    rows = (
        supabase.table("contracts")
        .select("id, plan_code, company_id, service_type, status_code, is_active")
        .eq("company_id", company_id)
        .eq("service_type", "SAAS")
        .eq("status_code", "ACTIVE")
        .eq("is_active", True)
        .execute()
        .data
        or []
    )
    if not rows:
        raise TierGateError("NO_ACTIVE_SAAS_CONTRACT", "활성 SaaS 계약이 없습니다.")
    if len(rows) >= 2:
        raise TierGateError(
            "AMBIGUOUS_ACTIVE_SAAS_CONTRACT",
            "활성 SaaS 계약이 2건 이상입니다.",
        )
    return rows[0]


def _match_current_plan(supabase, plan_code) -> dict:
    wanted = (plan_code or "").strip().upper()
    if not wanted:
        raise TierGateError(
            "UNKNOWN_CURRENT_PLAN",
            "현재 계약 플랜을 가격표에서 찾을 수 없습니다.",
        )
    rows = load_prices(supabase, "SAAS")
    matched = [
        r for r in rows if (r.get("tier_code") or "").strip().upper() == wanted
    ]
    if not matched:
        raise TierGateError(
            "UNKNOWN_CURRENT_PLAN",
            "현재 계약 플랜을 가격표에서 찾을 수 없습니다.",
        )
    if len(matched) >= 2:
        raise TierGateError(
            "AMBIGUOUS_CURRENT_PLAN",
            "현재 계약 플랜이 가격표에서 2건 이상 일치합니다.",
        )
    return matched[0]


def _as_scale(raw):
    """None/빈문자/NaN/음수 → MISSING. 0 은 유효."""
    if raw is None or raw == "":
        raise TierGateError("MISSING_SCALE_VALUE", "규모 값이 없습니다.")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise TierGateError("MISSING_SCALE_VALUE", "규모 값이 없습니다.") from None
    if value != value or value < 0:
        raise TierGateError("MISSING_SCALE_VALUE", "규모 값이 없습니다.")
    return value


def _maybe_int(value):
    if isinstance(value, float) and value == int(value):
        return int(value)
    return value


def _metric_for(sector: str, entity: dict):
    if sector == "INDUSTRY":
        raw = _as_scale(entity.get("employee_count"))
        value = _maybe_int(raw)
        metric = {"type": "employee_count", "value": value, "unit": "명"}
        return metric, value
    if sector == "BUILDING":
        raw = _as_scale(entity.get("building_area"))
        value = _maybe_int(raw)
        metric = {"type": "building_area", "value": value, "unit": "㎡"}
        return metric, value
    if sector == "CONSTRUCTION":
        source = _as_scale(entity.get("contract_amount"))
        pricing_value = _maybe_int(source * _EOK_TO_WON)
        metric = {
            "type": "construction_amount",
            "value": pricing_value,
            "unit": "원",
            "source_value": _maybe_int(source),
            "source_unit": "억원",
        }
        return metric, pricing_value
    raise TierGateError(
        "ENTITY_SECTOR_MISMATCH",
        "대상과 계약 업종이 일치하지 않습니다.",
    )


def _sort_order(plan: dict) -> float:
    raw = plan.get("sort_order")
    if raw is None or raw == "":
        raise TierGateError("INVALID_PLAN_ORDER", "플랜 순위를 비교할 수 없습니다.")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise TierGateError("INVALID_PLAN_ORDER", "플랜 순위를 비교할 수 없습니다.") from None
    if value != value:
        raise TierGateError("INVALID_PLAN_ORDER", "플랜 순위를 비교할 수 없습니다.")
    return value


def _plan_view(plan: dict) -> dict:
    return {k: plan.get(k) for k in _PLAN_VIEW_KEYS}
