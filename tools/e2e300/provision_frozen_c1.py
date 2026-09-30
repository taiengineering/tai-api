#!/usr/bin/env python3
"""WO-E2E300-FROZEN300-C1C8-PIPELINE-WIRING-005 — Frozen300 C1 Source Provisioner.

Provides pure payload builders (no I/O) for MFG/BLD factories and a
source-only CST site + factory bridge provisioner with injectable seams.

Authority: DEFINITION_consumer-pipeline_v1.md §13-A, §8-D.
Pipeline stage: C1 Consumer Source Facts ONLY.
C2~C8 delegated entirely to existing production seams.

Forbidden (never imported or called here):
  auto_diagnose_and_schedule, run_diagnosis, _finalize_saas_leg_http,
  _persist_saas_leg, _materialize_inspection_sets, SaasLegCommonFinalizer.

C1 NOT-BOUND:
  MFG has_local_exhaust — no verified C1 authority (PIPELINE_SOURCE = NOT_BOUND).

C1 NOT-PIPELINE (baseline only, NOT current LEG C1 consumed):
  BLD processes[]          — run_safe_building_leg does NOT read factory_process.
  CST construction_processes — assemble_construction_marketing_contract: NOT_CONSUMED.
  CST construction_works     — NOT_CONSUMED; no synthetic work_date.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, Tuple

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

# MFG USER_CONFIRM 3 (run_safe_industrial_leg._SAFE_EXPLICIT_CONFIRM_FIELDS subset).
# Frozen false values MUST be passed as explicit consumer overrides.  false ≠ missing.
MFG_EXPLICIT_CONFIRM_FIELDS: Tuple[str, ...] = (
    "has_high_pressure_gas",
    "has_chemical_substance",
    "has_boiler",
)

# has_local_exhaust: present in MFG frozen sector_fields but no verified C1 source authority.
MFG_NOT_BOUND_FIELDS: Tuple[str, ...] = ("has_local_exhaust",)

# BLD processes[]: current run_safe_building_leg does not consume factory_process.
BLD_NOT_PIPELINE_FIELDS: Tuple[str, ...] = ("processes",)

# CST construction_processes / construction_works: assemble_construction_marketing_contract
# marks these NOT_CONSUMED. No synthetic DB rows created. No work_date invented.
CST_NOT_PIPELINE_FIELDS: Tuple[str, ...] = ("construction_processes", "construction_works")

# Verified from construction_helpers.CONSTRUCTION_TYPE_MAP (reverse direction):
#   CONSTRUCTION_TYPE_MAP = {BUILDING→건축, CIVIL→토목, SPECIALTY→공통}
# Frozen Korean → construction_sites.site_type English (accepted by calc_safety_manager).
_CST_SITE_TYPE_MAP: Dict[str, str] = {
    "건축": "BUILDING",
    "토목": "CIVIL",
    "공통": "SPECIALTY",
}

_WON_PER_EOK: int = 100_000_000  # 1억원 = 100,000,000원


# ─────────────────────────────────────────────────────────────────────────────
# Amount normalization — once, no magnitude inference
# ─────────────────────────────────────────────────────────────────────────────

def normalize_cst_amount_to_eok(won_amount: float) -> float:
    """Convert construction_amount WON → 억원 (eok).

    Called exactly once per CST case.  No magnitude inference.
    Verified: frozen baseline uses WON (CST-001 = 59,890,000,000 WON = 598.9억).
    """
    return float(won_amount) / _WON_PER_EOK


# ─────────────────────────────────────────────────────────────────────────────
# construction_type normalization
# ─────────────────────────────────────────────────────────────────────────────

def normalize_cst_construction_type(frozen_type: str) -> str:
    """Map frozen Korean construction_type → construction_sites.site_type English.

    Derived from construction_helpers.CONSTRUCTION_TYPE_MAP reverse direction.
    Raises ValueError on unverified type (CST_CONSTRUCTION_TYPE_UNVERIFIED).
    """
    mapped = _CST_SITE_TYPE_MAP.get(str(frozen_type or "").strip())
    if mapped is None:
        raise ValueError(
            f"CST_CONSTRUCTION_TYPE_UNVERIFIED: {frozen_type!r} "
            f"not in {list(_CST_SITE_TYPE_MAP)}"
        )
    return mapped


# ─────────────────────────────────────────────────────────────────────────────
# MFG explicit confirm extractor
# ─────────────────────────────────────────────────────────────────────────────

def extract_mfg_explicit_confirms(case_data: dict) -> dict:
    """Extract USER_CONFIRM 3 from frozen MFG sector_fields.

    Returns only fields PRESENT in sector_fields.
    False is preserved exactly (false ≠ missing — run_safe_industrial_leg masks
    these to None before LEG; explicit false must override that mask).
    """
    sf = case_data.get("sector_fields") or {}
    result: Dict[str, Any] = {}
    for field in MFG_EXPLICIT_CONFIRM_FIELDS:
        if field in sf:
            result[field] = sf[field]
    return result


# ─────────────────────────────────────────────────────────────────────────────
# MFG factory payload builder
# ─────────────────────────────────────────────────────────────────────────────

def build_mfg_factory_payload(case_data: dict, company_id: str) -> dict:
    """Build factories INSERT payload for MFG case.

    Included: name, company_id, sector=MANUFACTURING, site_type, employee_count,
              ksic_code, electrical_capacity_kw.
    NOT included: has_local_exhaust (MFG_NOT_BOUND_FIELDS — no verified C1 authority).
    has_high_pressure_gas/has_chemical_substance/has_boiler: stored as factory columns
      BUT are masked by run_safe_industrial_leg._SAFE_EXPLICIT_CONFIRM_FIELDS.
      Must be passed as consumer input overrides via extract_mfg_explicit_confirms().
    """
    sf = case_data.get("sector_fields") or {}
    return {
        "name":                   case_data["factory_name"],
        "company_id":             company_id,
        "sector":                 "MANUFACTURING",
        "site_type":              case_data.get("site_type", "OFFICE"),
        "employee_count":         case_data.get("worker_count"),
        "ksic_code":              sf.get("ksic_code"),
        "electrical_capacity_kw": sf.get("electrical_capacity_kw"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# BLD factory payload builder
# ─────────────────────────────────────────────────────────────────────────────

def build_bld_factory_payload(case_data: dict, company_id: str) -> dict:
    """Build factories INSERT payload for BLD case.

    Included: name, company_id, sector=BUILDING, site_type,
              employee_count (=worker_count, maps to assembler's worker_count),
              building_area (CRITICAL — was missing pre-WO-005; assembler reads
              factories.building_area → total_floor_area VERIFIED_SOURCE),
              floor_count (assembler OWNED_EXACT),
              electrical_capacity_kw.
    NOT included: main_purpose_name (baseline metadata; no verified LEG C1 authority).
    NOT pipeline: processes[] (BLD_NOT_PIPELINE_FIELDS).
    """
    sf = case_data.get("sector_fields") or {}
    return {
        "name":                   case_data["factory_name"],
        "company_id":             company_id,
        "sector":                 "BUILDING",
        "site_type":              case_data.get("site_type", "BUILDING"),
        "employee_count":         case_data.get("worker_count"),  # worker_count → employee_count
        "building_area":          sf.get("building_area"),        # CRITICAL: VERIFIED_SOURCE
        "floor_count":            sf.get("floor_count"),          # OWNED_EXACT
        "electrical_capacity_kw": sf.get("electrical_capacity_kw"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# CST site payload builder
# ─────────────────────────────────────────────────────────────────────────────

def build_cst_site_payload(case_data: dict, company_id: str) -> dict:
    """Build construction_sites INSERT payload for CST case.

    - contract_amount: WON → eok (normalize_cst_amount_to_eok, called once).
    - site_type: Korean → English (normalize_cst_construction_type).
    - site_address: None when absent in frozen (no synthetic address invented).
    - construction_processes / construction_works: NOT included (CST_NOT_PIPELINE_FIELDS).
    - No work_date: construction_works not stored, no synthetic date.
    """
    sf = case_data.get("sector_fields") or {}
    won_amount = sf.get("construction_amount")
    eok = normalize_cst_amount_to_eok(won_amount) if won_amount is not None else None
    site_type = normalize_cst_construction_type(sf.get("construction_type", "건축"))
    return {
        "site_name":       case_data["factory_name"],
        "company_id":      company_id,
        "site_type":       site_type,
        "contract_amount": eok,
        "total_workers":   case_data.get("worker_count"),
        "site_address":    None,  # absent in frozen CST cases — no synthetic address
    }


# ─────────────────────────────────────────────────────────────────────────────
# CST source-only provisioner (injectable seams — no auto_diagnose)
# ─────────────────────────────────────────────────────────────────────────────

def _default_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def provision_cst_source(
    supabase: Any,
    case_data: dict,
    company_id: str,
    *,
    _site_insert_fn: Optional[Callable] = None,
    _factory_bridge_fn: Optional[Callable] = None,
    _now_iso_fn: Optional[Callable] = None,
) -> dict:
    """Create construction_sites row + factory bridge.

    Source-only: POST /sites is NOT used (auto_diagnose_and_schedule side-effect).
    Instead: direct construction_sites INSERT → create_factory_for_site bridge.

    Returns {site_id, factory_id, contract_amount_eok, site_type, pipeline_c1_exact}.

    Injectable seams (for tests):
      _site_insert_fn(supabase, payload, now_iso_fn) -> site_id (str)
      _factory_bridge_fn(supabase, site_row, now_iso_fn) -> factory_id (str | None)
    """
    now_iso_fn = _now_iso_fn or _default_now_iso

    site_payload = build_cst_site_payload(case_data, company_id)
    site_payload_full: Dict[str, Any] = {
        **site_payload,
        "is_active":   True,
        "status_code": "PLANNED",
        "created_at":  now_iso_fn(),
        "updated_at":  now_iso_fn(),
    }

    if _site_insert_fn is not None:
        site_id = _site_insert_fn(supabase, site_payload_full, now_iso_fn)
    else:
        from services.construction_svc import create_factory_for_site as _cffs  # noqa (import gate)
        res = supabase.table("construction_sites").insert(site_payload_full).execute()
        site_id = res.data[0]["id"]

    site_row: Dict[str, Any] = {**site_payload_full, "id": site_id, "company_id": company_id}

    if _factory_bridge_fn is not None:
        factory_id = _factory_bridge_fn(supabase, site_row, now_iso_fn)
    else:
        from services.construction_svc import create_factory_for_site
        factory_id = create_factory_for_site(supabase, site_row, now_iso_fn)

    if not factory_id:
        raise RuntimeError(
            f"CST_FACTORY_BRIDGE_FAILED: site_id={site_id} factory_id not created"
        )

    return {
        "site_id":             site_id,
        "factory_id":          factory_id,
        "contract_amount_eok": site_payload.get("contract_amount"),
        "site_type":           site_payload.get("site_type"),
        "pipeline_c1_exact":   True,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Manifest C1 entry builder
# ─────────────────────────────────────────────────────────────────────────────

def build_manifest_c1_entry(
    case_data: dict,
    provision_result: dict,
    *,
    work_source_exact: bool = False,
    material_source_exact: bool = False,
    equipment_source_exact: bool = False,
) -> dict:
    """Build manifest entry with pipeline_c1_exact + c1 sub-object.

    pipeline_c1_exact = direct_source_exact AND work/material/equipment exact.
    source_exact: legacy compat — same value as pipeline_c1_exact.
    """
    sector = case_data.get("sector", "")
    direct_source_exact = bool(provision_result.get("pipeline_c1_exact"))

    non_pipeline: Dict[str, str] = {}
    if sector == "BUILDING":
        for f in BLD_NOT_PIPELINE_FIELDS:
            non_pipeline[f] = "NOT_CURRENTLY_CONSUMED"
    elif sector == "CONSTRUCTION":
        for f in CST_NOT_PIPELINE_FIELDS:
            non_pipeline[f] = "NOT_CURRENTLY_CONSUMED"

    pipeline_c1_exact = bool(
        direct_source_exact
        and work_source_exact
        and material_source_exact
        and equipment_source_exact
    )

    entry: Dict[str, Any] = {
        "case_id":           case_data["case_id"],
        "sector":            sector,
        "factory_id":        provision_result.get("factory_id"),
        "site_id":           provision_result.get("site_id"),
        "pipeline_c1_exact": pipeline_c1_exact,
        "source_exact":      pipeline_c1_exact,  # legacy compat
        "c1": {
            "direct_source_exact":    direct_source_exact,
            "work_source_exact":      work_source_exact,
            "material_source_exact":  material_source_exact,
            "equipment_source_exact": equipment_source_exact,
        },
    }
    if non_pipeline:
        entry["baseline_non_pipeline"] = non_pipeline
    return entry


# ─────────────────────────────────────────────────────────────────────────────
# C1 source evidence builder
# ─────────────────────────────────────────────────────────────────────────────

def build_c1_source_evidence(case_data: dict, provision_result: dict) -> dict:
    """Build c1_source_evidence.json content for a case."""
    sector = case_data.get("sector", "")
    sf = case_data.get("sector_fields") or {}

    not_bound: Dict[str, Any] = {}
    non_pipeline: Dict[str, Any] = {}

    if sector == "MANUFACTURING":
        for f in MFG_NOT_BOUND_FIELDS:
            if f in sf:
                not_bound[f] = {
                    "frozen_value": sf[f],
                    "reason":       "PIPELINE_SOURCE_NOT_BOUND: no verified C1 authority",
                }

    elif sector == "BUILDING":
        for f in BLD_NOT_PIPELINE_FIELDS:
            val = case_data.get(f)
            if val:
                non_pipeline[f] = {
                    "frozen_count": len(val) if isinstance(val, list) else 1,
                    "status":       "NOT_CURRENTLY_CONSUMED",
                    "note":         "run_safe_building_leg does not read factory_process",
                }

    elif sector == "CONSTRUCTION":
        for f in CST_NOT_PIPELINE_FIELDS:
            val = case_data.get(f)
            if val:
                non_pipeline[f] = {
                    "frozen_count": len(val) if isinstance(val, list) else 1,
                    "status":       "NOT_CURRENTLY_CONSUMED",
                    "note":         "assemble_construction_marketing_contract: NOT_CONSUMED table",
                }

    evidence: Dict[str, Any] = {
        "case_id":           case_data["case_id"],
        "sector":            sector,
        "factory_id":        provision_result.get("factory_id"),
        "site_id":           provision_result.get("site_id"),
        "pipeline_c1_exact": provision_result.get("pipeline_c1_exact", False),
        "direct_source":     {"status": "PROVISIONED" if provision_result.get("pipeline_c1_exact") else "PENDING"},
        "work_source":       {"status": "PROVISIONED" if provision_result.get("work_source_exact")     else "EMPTY_OR_PENDING"},
        "material_source":   {"status": "PROVISIONED" if provision_result.get("material_source_exact") else "EMPTY_OR_PENDING"},
        "equipment_source":  {"status": "PROVISIONED" if provision_result.get("equipment_source_exact") else "EMPTY_OR_PENDING"},
    }
    if not_bound:
        evidence["not_bound"] = not_bound
    if non_pipeline:
        evidence["non_pipeline_baseline_fields"] = non_pipeline
    return evidence
