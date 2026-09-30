"""Admin Commercial Read Service — WO-ADM-COMM-01-BE-READ-001 + WO-ADM-CONTRACT-01.

읽기 전용. DB write = 0. pricing engine 호출 = 0.

API-1: list_commercial_versions — saas_contract_commercial_versions
API-2: list_site_scopes          — saas_contract_site_scopes
API-3: get_entitlement_health    — canonical resolve + future scheduled detection

금지:
  - DB INSERT / UPDATE / DELETE
  - pricing engine 호출 (saas_pricing_composer_v2, preview_saas_price_v2)
  - Commercial Version 생성/수정
  - Site Scope 생성/수정
  - Renewal 실행
  - _fetch_all_cvs (underscore private) import 금지

API-4: list_payments_admin  — public.payments (company_id required, FK: quote_id/contract_id)
API-5: list_contracts_admin — public.contracts (company_id required, FK: contract_no)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.saas_commercial_version_time_v2 import (
    find_future_commercial_versions_v2,
    select_effective_commercial_version_v2,
)
from services.saas_entitlement_runtime_v2 import (
    SaasEntitlementRuntimeError,
    resolve_saas_entitlement_context_v2,
)
from services.time import now_kst

_CV_COLS = (
    "id, contract_id, version_no, commercial_schema_version, "
    "product_tier, pricing_mode, worker_capacity, payment_months, "
    "pricing_result_status, pricing_policy_version, "
    "effective_from, superseded_at, created_by, created_at"
)

_SS_COLS = (
    "id, commercial_version_id, entity_type, entity_id, "
    "sector, base_band_code, created_at"
)

_CANONICAL_ERROR_CODES = frozenset({
    "NO_ACTIVE_SAAS_CONTRACT",
    "AMBIGUOUS_ACTIVE_SAAS_CONTRACT",
    "CURRENT_CV_NOT_FOUND",
    "CURRENT_CV_AMBIGUOUS",
    "CURRENT_CV_SCHEMA_INVALID",
})


def _get(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


# ── API-1: Commercial Versions ────────────────────────────────────────────────

def list_commercial_versions(
    supabase,
    contract_id: str,
    page: int = 1,
    page_size: int = 50,
) -> Dict[str, Any]:
    """saas_contract_commercial_versions read. DB write = 0.

    ORDER BY version_no ASC (append-only history).
    """
    off = (page - 1) * page_size
    res = (
        supabase.table("saas_contract_commercial_versions")
        .select(_CV_COLS, count="exact")
        .eq("contract_id", contract_id)
        .order("version_no", desc=False)
        .range(off, off + page_size - 1)
        .execute()
    )
    items = res.data or []
    total = res.count if res.count is not None else len(items)
    total_pages = (total + page_size - 1) // page_size
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


# ── API-2: Site Scopes ────────────────────────────────────────────────────────

def list_site_scopes(
    supabase,
    commercial_version_id: str,
    page: int = 1,
    page_size: int = 100,
) -> Dict[str, Any]:
    """saas_contract_site_scopes read. DB write = 0."""
    off = (page - 1) * page_size
    res = (
        supabase.table("saas_contract_site_scopes")
        .select(_SS_COLS, count="exact")
        .eq("commercial_version_id", commercial_version_id)
        .range(off, off + page_size - 1)
        .execute()
    )
    items = res.data or []
    total = res.count if res.count is not None else len(items)
    total_pages = (total + page_size - 1) // page_size
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


# ── API-3: Entitlement Health ─────────────────────────────────────────────────

def get_entitlement_health(
    supabase,
    company_id: str,
) -> Dict[str, Any]:
    """Commercial 상태 관제 — canonical services 재사용. DB write = 0.

    future scheduled CV 존재는 ERROR가 아니다 (정상 예약 Renewal).

    canonical anomaly (SaasEntitlementRuntimeError) →
      HTTP 200 + health_status=ERROR + error_code
    """
    as_of = now_kst()

    try:
        resolution = resolve_saas_entitlement_context_v2(supabase, company_id, as_of)
    except SaasEntitlementRuntimeError as exc:
        return {
            "health_status": "ERROR",
            "company_id": company_id,
            "error_code": exc.code if exc.code in _CANONICAL_ERROR_CODES else "UNKNOWN_RUNTIME_ERROR",
            "contract_id": None,
            "current_cv_id": None,
            "current_cv_no": None,
            "product_tier": None,
            "future_scheduled_cv_ids": [],
        }

    contract_id = resolution.contract_id
    current_cv_id = resolution.commercial_version_id
    current_cv_no = resolution.commercial_version_no
    product_tier = resolution.product_tier

    # future scheduled CVs (정상 예약 Renewal 탐지)
    all_cvs_res = (
        supabase.table("saas_contract_commercial_versions")
        .select("id, version_no, effective_from, superseded_at")
        .eq("contract_id", contract_id)
        .order("version_no", desc=False)
        .execute()
    )
    all_cvs = all_cvs_res.data or []
    future_cvs = find_future_commercial_versions_v2(all_cvs, as_of)
    future_ids = [str(_get(cv, "id")) for cv in future_cvs if _get(cv, "id")]

    return {
        "health_status": "OK",
        "company_id": company_id,
        "error_code": None,
        "contract_id": contract_id,
        "current_cv_id": current_cv_id,
        "current_cv_no": current_cv_no,
        "product_tier": product_tier,
        "future_scheduled_cv_ids": future_ids,
    }


# ── API-4: Payments (chain read) ──────────────────────────────────────────────

_PAY_COLS = (
    "id, company_id, quote_id, contract_id, "
    "plan_code, product_type, payment_type, "
    "total_amount, supply_amount, vat_amount, "
    "status_code, service_status, "
    "pg_method, period_months, paid_at, created_at"
)


def list_payments_admin(
    supabase,
    company_id: str,
    page: int = 1,
    page_size: int = 20,
) -> Dict[str, Any]:
    """public.payments 직접 조회. v_payments_list 사용 안 함. DB write = 0.

    company_id 필수 (cross-company guard). quote_id / contract_id FK 포함.
    """
    off = (page - 1) * page_size
    res = (
        supabase.table("payments")
        .select(_PAY_COLS, count="exact")
        .eq("company_id", company_id)
        .order("created_at", desc=True)
        .range(off, off + page_size - 1)
        .execute()
    )
    items = res.data or []
    total = res.count if res.count is not None else len(items)
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total else 0,
    }


# ── API-5: Contracts (chain read) ─────────────────────────────────────────────

_CONTRACT_ADM_COLS = (
    "id, contract_no, company_id, "
    "service_type, status_code, "
    "start_date, end_date, "
    "total_amount, created_at"
)


def list_contracts_admin(
    supabase,
    company_id: str,
    page: int = 1,
    page_size: int = 20,
) -> Dict[str, Any]:
    """public.contracts 직접 조회. DB write = 0.

    company_id 필수 (cross-company guard). contract_no FK 포함.
    """
    off = (page - 1) * page_size
    res = (
        supabase.table("contracts")
        .select(_CONTRACT_ADM_COLS, count="exact")
        .eq("company_id", company_id)
        .order("created_at", desc=True)
        .range(off, off + page_size - 1)
        .execute()
    )
    items = res.data or []
    total = res.count if res.count is not None else len(items)
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total else 0,
    }
