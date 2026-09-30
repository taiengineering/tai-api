"""Member Commercial Read Service — WO-FE-SAFE-01.

GET /me/commercial/contract

Auth authority: current_user.company_id only.
Client company_id param = 0.
DB write = 0. pricing = 0. renewal = 0.

State machine:
  NO_COMPANY          — company_id 없음
  NO_ACTIVE_CONTRACT  — NO_ACTIVE_SAAS_CONTRACT canonical error
  ERROR               — AMBIGUOUS / CURRENT_CV_* canonical error
  ACTIVE              — 정상 계약 + CV 확인

금지:
  - INSERT / UPDATE / DELETE
  - pricing / preview / repricing
  - payment prepare / renewal apply
  - admin_commercial API 재사용
  - _fetch_all_cvs (underscore private) import
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.saas_entitlement_runtime_v2 import (
    SaasEntitlementRuntimeError,
    resolve_saas_entitlement_context_v2,
)
from services.time import now_kst

_CONTRACT_COLS = (
    "id, contract_no, company_id, quote_id, "
    "service_type, status_code, is_active, "
    "start_date, end_date, "
    "contract_amount, vat_amount, total_amount, paid_amount, paid_at, "
    "created_at"
)

_CV_COLS = (
    "id, contract_id, version_no, commercial_schema_version, "
    "product_tier, pricing_mode, worker_capacity, payment_months, "
    "pricing_result_status, pricing_policy_version, "
    "effective_from, superseded_at, created_at"
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

_NO_COMPANY_RESULT: Dict[str, Any] = {
    "state": "NO_COMPANY",
    "error_code": None,
    "contract": None,
    "commercial_version": None,
    "site_scopes": [],
}


def _get(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _annotate_scopes_with_names(
    supabase,
    company_id: str,
    scopes: List[Dict],
) -> None:
    """Batch lookup factory/construction_site names. N+1=0.

    factory   → public.factories.name
    site      → public.construction_sites.site_name
    cross-company or missing → entity_ref_ok=False, entity_name=None
    """
    factory_ids = list({
        str(_get(s, "entity_id"))
        for s in scopes
        if _get(s, "entity_type") == "factory" and _get(s, "entity_id")
    })
    site_ids = list({
        str(_get(s, "entity_id"))
        for s in scopes
        if _get(s, "entity_type") == "site" and _get(s, "entity_id")
    })

    factory_map: Dict[str, Any] = {}
    if factory_ids:
        fres = (
            supabase.table("factories")
            .select("id, company_id, name")
            .in_("id", factory_ids)
            .execute()
        )
        for row in (fres.data or []):
            factory_map[str(_get(row, "id"))] = row

    site_map: Dict[str, Any] = {}
    if site_ids:
        sres = (
            supabase.table("construction_sites")
            .select("id, company_id, site_name")
            .in_("id", site_ids)
            .execute()
        )
        for row in (sres.data or []):
            site_map[str(_get(row, "id"))] = row

    for scope in scopes:
        etype = _get(scope, "entity_type")
        eid = _get(scope, "entity_id")
        if eid is None:
            scope["entity_name"] = None
            scope["entity_ref_ok"] = False
            continue
        eid_str = str(eid)
        if etype == "factory":
            row = factory_map.get(eid_str)
            if row is None or str(_get(row, "company_id")) != str(company_id):
                scope["entity_name"] = None
                scope["entity_ref_ok"] = False
            else:
                scope["entity_name"] = _get(row, "name")
                scope["entity_ref_ok"] = True
        elif etype == "site":
            row = site_map.get(eid_str)
            if row is None or str(_get(row, "company_id")) != str(company_id):
                scope["entity_name"] = None
                scope["entity_ref_ok"] = False
            else:
                scope["entity_name"] = _get(row, "site_name")
                scope["entity_ref_ok"] = True
        else:
            scope["entity_name"] = None
            scope["entity_ref_ok"] = False


def get_member_commercial_contract(
    supabase,
    company_id: Optional[str],
) -> Dict[str, Any]:
    """현재 이용계약 + CV + Site Scope. company_id = auth authority. DB write = 0.

    Returns state dict with keys: state, error_code, contract, commercial_version, site_scopes.
    """
    if not company_id:
        return dict(_NO_COMPANY_RESULT)

    as_of = now_kst()

    try:
        resolution = resolve_saas_entitlement_context_v2(supabase, company_id, as_of)
    except SaasEntitlementRuntimeError as exc:
        code = exc.code if exc.code in _CANONICAL_ERROR_CODES else "UNKNOWN_RUNTIME_ERROR"
        if code == "NO_ACTIVE_SAAS_CONTRACT":
            return {
                "state": "NO_ACTIVE_CONTRACT",
                "error_code": code,
                "contract": None,
                "commercial_version": None,
                "site_scopes": [],
            }
        return {
            "state": "ERROR",
            "error_code": code,
            "contract": None,
            "commercial_version": None,
            "site_scopes": [],
        }

    # contract exact read — canonical resolver가 고른 id만
    ct_res = (
        supabase.table("contracts")
        .select(_CONTRACT_COLS)
        .eq("id", resolution.contract_id)
        .execute()
    )
    contract = (ct_res.data or [None])[0]
    if contract and str(_get(contract, "company_id")) != str(company_id):
        return {
            "state": "ERROR",
            "error_code": "CONTRACT_COMPANY_MISMATCH",
            "contract": None,
            "commercial_version": None,
            "site_scopes": [],
        }

    # CV exact read — canonical resolver가 고른 id만
    cv_res = (
        supabase.table("saas_contract_commercial_versions")
        .select(_CV_COLS)
        .eq("id", resolution.commercial_version_id)
        .execute()
    )
    cv = (cv_res.data or [None])[0]

    # Site Scopes — canonical CV id로만
    ss_res = (
        supabase.table("saas_contract_site_scopes")
        .select(_SS_COLS)
        .eq("commercial_version_id", resolution.commercial_version_id)
        .execute()
    )
    scopes = ss_res.data or []
    _annotate_scopes_with_names(supabase, company_id, scopes)

    return {
        "state": "ACTIVE",
        "error_code": None,
        "contract": contract,
        "commercial_version": cv,
        "site_scopes": scopes,
    }
