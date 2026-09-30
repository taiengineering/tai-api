#!/usr/bin/env python3
"""WO-E2E300-C1-EXACTNESS-CLOSEOUT-PATCH-005B — Frozen300 C1 Full Provisioner.

Provides payload builders (no I/O), verify functions (readback-based exactness),
and per-sector orchestrators with injectable seams for mock/test isolation.

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

import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from services.legal_rules import normalize_sector_db

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

# Reverse of _CST_SITE_TYPE_MAP: English site_type → Korean construction_type label.
# Mirrors construction_helpers.CONSTRUCTION_TYPE_MAP (BUILDING→건축, CIVIL→토목, SPECIALTY→공통).
_SITE_TYPE_TO_KOREAN: Dict[str, str] = {v: k for k, v in _CST_SITE_TYPE_MAP.items()}

# Fields compared in verify_mfg_c1_exact (sector must be INDUSTRIAL post-normalize).
_MFG_VERIFY_FIELDS: Tuple[str, ...] = (
    "name", "company_id", "sector", "site_type",
    "employee_count", "ksic_code", "electrical_capacity_kw",
)

# Fields compared in verify_bld_c1_exact.
_BLD_VERIFY_FIELDS: Tuple[str, ...] = (
    "name", "company_id", "sector", "site_type",
    "employee_count", "building_area", "floor_count", "electrical_capacity_kw",
)


# ─────────────────────────────────────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────────────────────────────────────

class StaleE2ECaseError(RuntimeError):
    """Duplicate E2E300 factory/site name detected — provisioning must not overwrite."""
    code = "STALE_E2E_CASE_FOUND"


class ProcessMasterUnavailableError(RuntimeError):
    """v_process_unified query failed or response malformed — fail-closed."""
    code = "PROCESS_MASTER_UNAVAILABLE"


class ProcessMasterNotFoundError(RuntimeError):
    """process_id not found in v_process_unified — INSERT forbidden."""
    code = "PROCESS_MASTER_NOT_FOUND"


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

    sector: normalize_sector_db("MANUFACTURING") → "INDUSTRIAL" (production canonical).
    NOT included: has_local_exhaust (MFG_NOT_BOUND_FIELDS — no verified C1 authority).
    has_high_pressure_gas/has_chemical_substance/has_boiler: stored as factory columns
      BUT are masked by run_safe_industrial_leg._SAFE_EXPLICIT_CONFIRM_FIELDS.
      Must be passed as consumer input overrides via extract_mfg_explicit_confirms().
    """
    sf = case_data.get("sector_fields") or {}
    return {
        "name":                   case_data["factory_name"],
        "company_id":             company_id,
        "sector":                 normalize_sector_db("MANUFACTURING"),  # → "INDUSTRIAL"
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
# Verify functions — readback-based exactness
# ─────────────────────────────────────────────────────────────────────────────

def _compare_fields(
    stored: dict,
    expected: dict,
    fields: Tuple[str, ...],
) -> Dict[str, Any]:
    """Compare stored vs expected for given fields. None expectation must match None actual."""
    mismatches: List[str] = []
    actual: Dict[str, Any] = {k: stored.get(k) for k in fields}
    for k in fields:
        exp_v = expected.get(k)
        act_v = actual[k]
        if exp_v is None:
            if act_v is not None:
                mismatches.append(k)
        elif isinstance(exp_v, (int, float)):
            if act_v is None or abs(float(act_v) - float(exp_v)) > 1e-9:
                mismatches.append(k)
        else:
            if act_v != exp_v:
                mismatches.append(k)
    return {
        "exact":     len(mismatches) == 0,
        "expected":  {k: expected.get(k) for k in fields},
        "actual":    actual,
        "mismatches": mismatches,
    }


def verify_mfg_c1_exact(stored_factory: Optional[dict], expected_payload: dict) -> dict:
    """Compare stored factory row against MFG expected payload.

    Returns {exact, expected, actual, mismatches}.
    pipeline_c1_exact invariant: must derive from this result, not from insert success.
    """
    if stored_factory is None:
        return {"exact": False, "expected": expected_payload, "actual": None,
                "mismatches": ["factory_readback_failed"]}
    return _compare_fields(stored_factory, expected_payload, _MFG_VERIFY_FIELDS)


def verify_bld_c1_exact(stored_factory: Optional[dict], expected_payload: dict) -> dict:
    """Compare stored factory row against BLD expected payload.

    Returns {exact, expected, actual, mismatches}.
    """
    if stored_factory is None:
        return {"exact": False, "expected": expected_payload, "actual": None,
                "mismatches": ["factory_readback_failed"]}
    return _compare_fields(stored_factory, expected_payload, _BLD_VERIFY_FIELDS)


def verify_cst_c1_exact(
    stored_site: Optional[dict],
    stored_factory: Optional[dict],
    case_data: dict,
    company_id: str,
) -> dict:
    """Compare stored site/factory against CST case expected values.

    Full factory bridge verification: site.factory_id == factory.id,
    company_id, name, sector=CONSTRUCTION, site_type=CONSTRUCTION,
    employee_count, construction_type (Korean), construction_amount (WON).
    """
    sf = case_data.get("sector_fields") or {}
    expected_site_type = normalize_cst_construction_type(sf.get("construction_type", "건축"))
    won = sf.get("construction_amount")
    expected_eok = normalize_cst_amount_to_eok(won) if won is not None else None
    expected_factory_construction_type = _SITE_TYPE_TO_KOREAN.get(expected_site_type)

    expected: Dict[str, Any] = {
        "site_name":                    case_data.get("factory_name"),
        "site_type":                    expected_site_type,
        "site_company_id":              company_id,
        "contract_amount":              expected_eok,
        "total_workers":                case_data.get("worker_count"),
        "factory_bridge":               True,
        "factory_site_factory_id_link": True,
        "factory_sector":               "CONSTRUCTION",
        "factory_site_type":            "CONSTRUCTION",
        "factory_company_id":           company_id,
        "factory_name":                 case_data.get("factory_name"),
        "factory_employee_count":       case_data.get("worker_count"),
        "factory_construction_type":    expected_factory_construction_type,
        "factory_construction_amount":  won,
    }

    if stored_site is None:
        return {"exact": False, "expected": expected, "actual": {},
                "mismatches": ["site_readback_failed"]}

    mismatches: List[str] = []
    actual: Dict[str, Any] = {
        "site_name":                    stored_site.get("site_name"),
        "site_type":                    stored_site.get("site_type"),
        "site_company_id":              stored_site.get("company_id"),
        "contract_amount":              stored_site.get("contract_amount"),
        "total_workers":                stored_site.get("total_workers"),
        "factory_bridge":               bool(stored_factory),
        "factory_site_factory_id_link": None,
        "factory_sector":               stored_factory.get("sector")               if stored_factory else None,
        "factory_site_type":            stored_factory.get("site_type")            if stored_factory else None,
        "factory_company_id":           stored_factory.get("company_id")           if stored_factory else None,
        "factory_name":                 stored_factory.get("name")                 if stored_factory else None,
        "factory_employee_count":       stored_factory.get("employee_count")       if stored_factory else None,
        "factory_construction_type":    stored_factory.get("construction_type")    if stored_factory else None,
        "factory_construction_amount":  stored_factory.get("construction_amount")  if stored_factory else None,
    }

    # Site checks
    if actual["site_name"] != expected["site_name"]:
        mismatches.append("site_name")
    if actual["site_type"] != expected["site_type"]:
        mismatches.append("site_type")
    if actual["site_company_id"] != company_id:
        mismatches.append("site_company_id")
    if expected_eok is not None:
        act_eok = actual["contract_amount"]
        if act_eok is None or abs(float(act_eok) - float(expected_eok)) > 1e-6:
            mismatches.append("contract_amount")
    if expected["total_workers"] is not None:
        act_w = actual["total_workers"]
        if act_w is None or int(act_w) != int(expected["total_workers"]):
            mismatches.append("total_workers")

    if not stored_factory:
        mismatches.append("factory_bridge")
    else:
        site_factory_id = stored_site.get("factory_id")
        factory_id_val = stored_factory.get("id")
        link_ok = site_factory_id is not None and site_factory_id == factory_id_val
        actual["factory_site_factory_id_link"] = link_ok
        if not link_ok:
            mismatches.append("factory_site_factory_id_link")
        if actual["factory_sector"] != "CONSTRUCTION":
            mismatches.append("factory_sector")
        if actual["factory_site_type"] != "CONSTRUCTION":
            mismatches.append("factory_site_type")
        if actual["factory_company_id"] != company_id:
            mismatches.append("factory_company_id")
        if actual["factory_name"] != case_data.get("factory_name"):
            mismatches.append("factory_name")
        if expected["factory_employee_count"] is not None:
            act_ec = actual["factory_employee_count"]
            if act_ec is None or int(act_ec) != int(expected["factory_employee_count"]):
                mismatches.append("factory_employee_count")
        if expected_factory_construction_type:
            if actual["factory_construction_type"] != expected_factory_construction_type:
                mismatches.append("factory_construction_type")
        if won is not None:
            act_won = actual["factory_construction_amount"]
            if act_won is None or abs(float(act_won) - float(won)) > 1e-9:
                mismatches.append("factory_construction_amount")

    return {
        "exact":      len(mismatches) == 0,
        "expected":   expected,
        "actual":     actual,
        "mismatches": mismatches,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Internal readback verifiers
# ─────────────────────────────────────────────────────────────────────────────

def _verify_process_readback(stored_rows: list, expected_processes: list) -> dict:
    """Multiset comparison of (process_id, source) tuples."""
    count_match = len(stored_rows) == len(expected_processes)
    if not expected_processes:
        return {"exact": count_match, "count_match": count_match}
    stored_counter: Counter = Counter(
        (r.get("process_id"), r.get("source")) for r in stored_rows
    )
    expected_counter: Counter = Counter(
        (p["process_id"], p.get("source", "DB")) for p in expected_processes
    )
    exact = count_match and stored_counter == expected_counter
    result: Dict[str, Any] = {"exact": exact, "count_match": count_match}
    missing = []
    for key, cnt in expected_counter.items():
        deficit = cnt - stored_counter.get(key, 0)
        for _ in range(deficit):
            missing.append({"process_id": key[0], "source": key[1]})
    if missing:
        result["missing_process_keys"] = missing
    return result


def _verify_work_readback(stored_rows: list, expected_works: list) -> dict:
    """Multiset comparison of (work_type, work_subtype, json_attrs); all stored must be active."""
    count_match = len(stored_rows) == len(expected_works)
    if not expected_works:
        return {"exact": count_match, "count_match": count_match}

    all_active = all(r.get("active") is True for r in stored_rows)

    def _wkey(w: dict) -> tuple:
        return (w.get("work_type"), w.get("work_subtype"),
                json.dumps(w.get("attributes") or {}, sort_keys=True))

    stored_counter: Counter = Counter(_wkey(r) for r in stored_rows)
    expected_counter: Counter = Counter(_wkey(w) for w in expected_works)
    exact = count_match and all_active and stored_counter == expected_counter

    result: Dict[str, Any] = {"exact": exact, "count_match": count_match, "all_active": all_active}
    if not all_active:
        result["inactive_types"] = [r.get("work_type") for r in stored_rows if r.get("active") is not True]
    if stored_counter != expected_counter:
        missing = []
        for key, cnt in expected_counter.items():
            deficit = cnt - stored_counter.get(key, 0)
            for _ in range(deficit):
                missing.append({"work_type": key[0], "work_subtype": key[1]})
        if missing:
            result["missing_work_keys"] = missing
    return result


def _verify_material_readback(stored_rows: list, expected_materials: list) -> dict:
    """Per-row check: find by master_key/name, then verify handling_mode_codes + is_active."""
    count_match = len(stored_rows) == len(expected_materials)
    if not expected_materials:
        return {"exact": count_match, "count_match": count_match}

    per_material = []
    for m in expected_materials:
        key = m.get("material_master_key")
        name = m.get("display_name") or m.get("material_name")
        found: Optional[dict] = None
        if key:
            found = next((r for r in stored_rows if r.get("material_master_key") == key), None)
        if found is None and name:
            found = next((r for r in stored_rows if r.get("material_name") == name), None)

        identifier = key or name or "UNKNOWN"
        if found is None:
            per_material.append({"identifier": identifier, "found": False, "exact": False})
            continue

        exp_handling = sorted(m.get("handling_mode_codes") or [])
        act_handling = sorted(found.get("handling_mode_codes") or [])
        handling_exact = exp_handling == act_handling
        active_exact = found.get("is_active") is True
        row_result: Dict[str, Any] = {
            "identifier":    identifier,
            "found":         True,
            "handling_exact": handling_exact,
            "active_exact":  active_exact,
            "exact":         handling_exact and active_exact,
        }
        if not handling_exact:
            row_result.update({"handling_expected": exp_handling, "handling_actual": act_handling})
        per_material.append(row_result)

    all_found = all(r["found"] for r in per_material)
    all_exact = all(r.get("exact", False) for r in per_material)
    return {
        "exact":        count_match and all_found and all_exact,
        "count_match":  count_match,
        "per_material": per_material,
    }


def _verify_equipment_readback(stored_rows: list, expected_equipment: list) -> dict:
    """Counter multiset comparison of equipment_type_code (handles duplicate codes)."""
    count_match = len(stored_rows) == len(expected_equipment)
    if not expected_equipment:
        return {"exact": count_match, "count_match": count_match}
    stored_counter: Counter = Counter(
        r.get("equipment_type_code") for r in stored_rows if r.get("equipment_type_code")
    )
    expected_counter: Counter = Counter(
        eq.get("equipment_type_code") for eq in expected_equipment if eq.get("equipment_type_code")
    )
    exact = count_match and stored_counter == expected_counter
    result: Dict[str, Any] = {"exact": exact, "count_match": count_match}
    missing = []
    for code, cnt in expected_counter.items():
        deficit = cnt - stored_counter.get(code, 0)
        for _ in range(deficit):
            missing.append(code)
    if missing:
        result["missing_equipment_codes"] = missing
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Equipment payload helper
# ─────────────────────────────────────────────────────────────────────────────

def _build_equipment_insert_payload(factory_id: str, eq: dict) -> dict:
    code = eq.get("equipment_type_code")
    return {
        "factory_id":          factory_id,
        "asset_name":          eq.get("asset_name") or eq.get("facility_name_std") or "E2E설비",
        "equipment_type_code": code,
        "quantity":            eq.get("quantity", 1),
        "is_operating":        True,
        "is_legal_target":     True,
        "operation_status":    "ACTIVE",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Default production seam implementations (READ-ONLY check + writes via services)
# ─────────────────────────────────────────────────────────────────────────────

def _default_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_stale_factory_check(supabase: Any, name: str, company_id: str) -> bool:
    res = (supabase.table("factories")
           .select("id").eq("name", name).eq("company_id", company_id).limit(1).execute())
    return bool(getattr(res, "data", None))


def _default_stale_site_check(supabase: Any, name: str, company_id: str) -> bool:
    res = (supabase.table("construction_sites")
           .select("id").eq("site_name", name).eq("company_id", company_id).limit(1).execute())
    return bool(getattr(res, "data", None))


def _default_factory_insert(supabase: Any, payload: dict) -> dict:
    res = supabase.table("factories").insert(payload).execute()
    data = list(getattr(res, "data", None) or [])
    if not data:
        raise RuntimeError("factories insert returned no row")
    return data[0]


def _default_factory_read(supabase: Any, factory_id: str) -> Optional[dict]:
    res = (supabase.table("factories")
           .select("*").eq("id", factory_id).limit(1).execute())
    data = list(getattr(res, "data", None) or [])
    return data[0] if data else None


def _default_process_insert(supabase: Any, factory_id: str, payload: dict) -> dict:
    source = payload.get("source", "DB")
    row = {**payload, "factory_id": factory_id, "is_active": True, "is_primary": False}
    if source == "DB":
        process_id = payload["process_id"]
        try:
            res = (supabase.table("v_process_unified")
                   .select("process_id, process_lv1, process_lv2, process_lv3, process_lv4, process_path")
                   .eq("process_id", process_id)
                   .limit(1).execute())
        except Exception as exc:
            raise ProcessMasterUnavailableError(
                f"PROCESS_MASTER_UNAVAILABLE: v_process_unified query failed for process_id={process_id!r}"
            ) from exc
        master_data = getattr(res, "data", None)
        if not isinstance(master_data, list):
            raise ProcessMasterUnavailableError(
                f"PROCESS_MASTER_UNAVAILABLE: v_process_unified response malformed for process_id={process_id!r}"
            )
        if not master_data:
            raise ProcessMasterNotFoundError(
                f"PROCESS_MASTER_NOT_FOUND: process_id={process_id!r} not in v_process_unified"
            )
        proc = master_data[0]
        for lv in ("process_lv1", "process_lv2", "process_lv3", "process_lv4"):
            if proc.get(lv) is not None:
                row[lv] = proc[lv]
        if proc.get("process_path") and not row.get("process_path"):
            row["process_path"] = proc["process_path"]
    ins_res = supabase.table("factory_process").insert(row).execute()
    ins_data = list(getattr(ins_res, "data", None) or [])
    if not ins_data:
        raise RuntimeError("factory_process insert returned no row")
    return ins_data[0]


def _default_process_read(supabase: Any, factory_id: str) -> List[dict]:
    res = (supabase.table("factory_process")
           .select("process_id, source")
           .eq("factory_id", factory_id).eq("is_active", True).execute())
    return list(getattr(res, "data", None) or [])


def _default_work_insert(supabase: Any, factory_id: str, payload: dict) -> dict:
    from services.work_source.store import create_work_fact
    return create_work_fact(supabase, factory_id, payload)


def _default_work_read(supabase: Any, factory_id: str) -> List[dict]:
    from services.work_source.store import load_work_rows_optional
    return load_work_rows_optional(supabase, factory_id)


def _default_material_insert(supabase: Any, factory_id: str, payload: dict) -> dict:
    from services.material_source.store import create_factory_material
    return create_factory_material(supabase, factory_id, payload)


def _default_material_read(supabase: Any, factory_id: str) -> List[dict]:
    from services.material_source.store import load_factory_material_rows_optional
    return load_factory_material_rows_optional(supabase, factory_id)


def _default_equipment_insert(supabase: Any, factory_id: str, payload: dict) -> dict:
    from services.equipment_source.store import validate_equipment_source_row
    validated = validate_equipment_source_row(payload)
    row = {k: v for k, v in validated.items() if v is not None}
    res = supabase.table("equipment_assets").insert(row).execute()
    data = list(getattr(res, "data", None) or [])
    if not data:
        raise RuntimeError("equipment_assets insert returned no row")
    return data[0]


def _default_equipment_read(supabase: Any, factory_id: str) -> List[dict]:
    from services.equipment_source.store import load_equipment_rows_optional
    return load_equipment_rows_optional(supabase, factory_id)


# ─────────────────────────────────────────────────────────────────────────────
# MFG C1 orchestrator
# ─────────────────────────────────────────────────────────────────────────────

def provision_mfg_c1(
    supabase: Any,
    case_data: dict,
    company_id: str,
    *,
    _stale_fn: Optional[Callable] = None,
    _factory_insert_fn: Optional[Callable] = None,
    _factory_read_fn: Optional[Callable] = None,
    _process_insert_fn: Optional[Callable] = None,
    _process_read_fn: Optional[Callable] = None,
    _work_insert_fn: Optional[Callable] = None,
    _work_read_fn: Optional[Callable] = None,
    _material_insert_fn: Optional[Callable] = None,
    _material_read_fn: Optional[Callable] = None,
    _equipment_insert_fn: Optional[Callable] = None,
    _equipment_read_fn: Optional[Callable] = None,
) -> dict:
    """Provision MFG C1 source: factory + process + work + material + equipment.

    pipeline_c1_exact derives from actual persisted readback comparison.
    PRODUCTION_WRITE: this function writes to DB (callers control via supabase client).
    """
    name = case_data["factory_name"]

    # 1. Stale guard
    stale_fn = _stale_fn or _default_stale_factory_check
    if stale_fn(supabase, name, company_id):
        raise StaleE2ECaseError(
            f"STALE_E2E_CASE_FOUND: factory_name={name!r} already exists for company_id={company_id!r}"
        )

    # 2. Build expected payload and insert factory
    expected_payload = build_mfg_factory_payload(case_data, company_id)
    ins_fn = _factory_insert_fn or _default_factory_insert
    stored = ins_fn(supabase, expected_payload)
    factory_id: str = stored["id"]

    # 3. Readback factory — pipeline_c1_exact cannot derive from insert success alone
    read_fn = _factory_read_fn or _default_factory_read
    stored_factory = read_fn(supabase, factory_id)
    factory_verify = verify_mfg_c1_exact(stored_factory, expected_payload)

    # 4. Insert processes (MFG pipeline-required)
    processes = case_data.get("processes") or []
    proc_ins = _process_insert_fn or _default_process_insert
    for p in processes:
        proc_ins(supabase, factory_id, {
            "process_id":   p["process_id"],
            "source":       p.get("source", "DB"),
            "process_path": p.get("process_path", ""),
        })
    proc_read = _process_read_fn or _default_process_read
    proc_rows = proc_read(supabase, factory_id)
    process_verify = _verify_process_readback(proc_rows, processes)

    # 5. Insert works
    works = case_data.get("works") or []
    work_ins = _work_insert_fn or _default_work_insert
    for w in works:
        work_ins(supabase, factory_id, {
            "work_type":    w["work_type"],
            "work_subtype": w.get("work_subtype"),
            "attributes":   w.get("attributes") or {},
        })
    work_read = _work_read_fn or _default_work_read
    work_rows = work_read(supabase, factory_id)
    work_verify = _verify_work_readback(work_rows, works)

    # 6. Insert materials
    materials = case_data.get("materials") or []
    mat_ins = _material_insert_fn or _default_material_insert
    for m in materials:
        mat_ins(supabase, factory_id, {
            "material_name":        m.get("display_name") or m.get("material_name"),
            "material_master_key":  m.get("material_master_key"),
            "handling_mode_codes":  m.get("handling_mode_codes") or [],
            "is_active":            True,
        })
    mat_read = _material_read_fn or _default_material_read
    mat_rows = mat_read(supabase, factory_id)
    material_verify = _verify_material_readback(mat_rows, materials)

    # 7. Insert equipment
    equipment = case_data.get("equipment") or []
    eq_ins = _equipment_insert_fn or _default_equipment_insert
    for eq in equipment:
        eq_ins(supabase, factory_id, _build_equipment_insert_payload(factory_id, eq))
    eq_read = _equipment_read_fn or _default_equipment_read
    eq_rows = eq_read(supabase, factory_id)
    equipment_verify = _verify_equipment_readback(eq_rows, equipment)

    # 8. Derive pipeline_c1_exact from all readback verifications
    pipeline_c1_exact = bool(
        factory_verify["exact"]
        and process_verify["exact"]
        and work_verify["exact"]
        and material_verify["exact"]
        and equipment_verify["exact"]
    )

    return {
        "factory_id":             factory_id,
        "site_id":                None,
        "pipeline_c1_exact":      pipeline_c1_exact,
        "direct_source_exact":    factory_verify["exact"],
        "process_source_exact":   process_verify["exact"],
        "work_source_exact":      work_verify["exact"],
        "material_source_exact":  material_verify["exact"],
        "equipment_source_exact": equipment_verify["exact"],
        "verify": {
            "factory":   factory_verify,
            "process":   process_verify,
            "work":      work_verify,
            "material":  material_verify,
            "equipment": equipment_verify,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# BLD C1 orchestrator
# ─────────────────────────────────────────────────────────────────────────────

def provision_bld_c1(
    supabase: Any,
    case_data: dict,
    company_id: str,
    *,
    _stale_fn: Optional[Callable] = None,
    _factory_insert_fn: Optional[Callable] = None,
    _factory_read_fn: Optional[Callable] = None,
    # NOTE: no _process_insert_fn — BLD processes are NOT_PIPELINE (BLD_NOT_PIPELINE_FIELDS)
    _work_insert_fn: Optional[Callable] = None,
    _work_read_fn: Optional[Callable] = None,
    _material_insert_fn: Optional[Callable] = None,
    _material_read_fn: Optional[Callable] = None,
    _equipment_insert_fn: Optional[Callable] = None,
    _equipment_read_fn: Optional[Callable] = None,
) -> dict:
    """Provision BLD C1 source: factory + work + material + equipment (no processes).

    BLD processes[] are NOT_PIPELINE: run_safe_building_leg does not read factory_process.
    pipeline_c1_exact derives from actual persisted readback comparison.
    """
    name = case_data["factory_name"]

    # 1. Stale guard
    stale_fn = _stale_fn or _default_stale_factory_check
    if stale_fn(supabase, name, company_id):
        raise StaleE2ECaseError(
            f"STALE_E2E_CASE_FOUND: factory_name={name!r} already exists for company_id={company_id!r}"
        )

    # 2. Build expected payload and insert factory
    expected_payload = build_bld_factory_payload(case_data, company_id)
    ins_fn = _factory_insert_fn or _default_factory_insert
    stored = ins_fn(supabase, expected_payload)
    factory_id: str = stored["id"]

    # 3. Readback factory
    read_fn = _factory_read_fn or _default_factory_read
    stored_factory = read_fn(supabase, factory_id)
    factory_verify = verify_bld_c1_exact(stored_factory, expected_payload)

    # 4. Insert works
    works = case_data.get("works") or []
    work_ins = _work_insert_fn or _default_work_insert
    for w in works:
        work_ins(supabase, factory_id, {
            "work_type":    w["work_type"],
            "work_subtype": w.get("work_subtype"),
            "attributes":   w.get("attributes") or {},
        })
    work_read = _work_read_fn or _default_work_read
    work_rows = work_read(supabase, factory_id)
    work_verify = _verify_work_readback(work_rows, works)

    # 5. Insert materials
    materials = case_data.get("materials") or []
    mat_ins = _material_insert_fn or _default_material_insert
    for m in materials:
        mat_ins(supabase, factory_id, {
            "material_name":       m.get("display_name") or m.get("material_name"),
            "material_master_key": m.get("material_master_key"),
            "handling_mode_codes": m.get("handling_mode_codes") or [],
            "is_active":           True,
        })
    mat_read = _material_read_fn or _default_material_read
    mat_rows = mat_read(supabase, factory_id)
    material_verify = _verify_material_readback(mat_rows, materials)

    # 6. Insert equipment
    equipment = case_data.get("equipment") or []
    eq_ins = _equipment_insert_fn or _default_equipment_insert
    for eq in equipment:
        eq_ins(supabase, factory_id, _build_equipment_insert_payload(factory_id, eq))
    eq_read = _equipment_read_fn or _default_equipment_read
    eq_rows = eq_read(supabase, factory_id)
    equipment_verify = _verify_equipment_readback(eq_rows, equipment)

    # 7. Derive pipeline_c1_exact from all readback verifications
    pipeline_c1_exact = bool(
        factory_verify["exact"]
        and work_verify["exact"]
        and material_verify["exact"]
        and equipment_verify["exact"]
    )

    return {
        "factory_id":             factory_id,
        "site_id":                None,
        "pipeline_c1_exact":      pipeline_c1_exact,
        "direct_source_exact":    factory_verify["exact"],
        "work_source_exact":      work_verify["exact"],
        "material_source_exact":  material_verify["exact"],
        "equipment_source_exact": equipment_verify["exact"],
        "verify": {
            "factory":   factory_verify,
            "work":      work_verify,
            "material":  material_verify,
            "equipment": equipment_verify,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# CST source-only provisioner (injectable seams — no auto_diagnose)
# ─────────────────────────────────────────────────────────────────────────────

def provision_cst_source(
    supabase: Any,
    case_data: dict,
    company_id: str,
    *,
    _site_insert_fn: Optional[Callable] = None,
    _factory_bridge_fn: Optional[Callable] = None,
    _site_read_fn: Optional[Callable] = None,
    _factory_read_fn: Optional[Callable] = None,
    _work_read_fn: Optional[Callable] = None,       # 005B: common source readback
    _material_read_fn: Optional[Callable] = None,   # 005B
    _equipment_read_fn: Optional[Callable] = None,  # 005B
    _stale_fn: Optional[Callable] = None,
    _now_iso_fn: Optional[Callable] = None,
) -> dict:
    """Create construction_sites row + factory bridge.

    Source-only: POST /sites is NOT used (auto_diagnose_and_schedule side-effect).
    Instead: direct construction_sites INSERT → create_factory_for_site bridge.

    pipeline_c1_exact derives from all readback verifications — never hardcoded.
    Common source (work/material/equipment) is proven empty via actual readback.

    Injectable seams (for tests):
      _site_insert_fn(supabase, payload, now_iso_fn) -> site_id (str)
      _factory_bridge_fn(supabase, site_row, now_iso_fn) -> factory_id (str | None)
      _site_read_fn(supabase, site_id) -> dict | None
      _factory_read_fn(supabase, factory_id) -> dict | None
      _work_read_fn(supabase, factory_id) -> list
      _material_read_fn(supabase, factory_id) -> list
      _equipment_read_fn(supabase, factory_id) -> list
      _stale_fn(supabase, name, company_id) -> bool
    """
    now_iso_fn = _now_iso_fn or _default_now_iso
    name = case_data["factory_name"]

    # Stale guard
    stale_fn = _stale_fn or _default_stale_site_check
    if stale_fn(supabase, name, company_id):
        raise StaleE2ECaseError(
            f"STALE_E2E_CASE_FOUND: site_name={name!r} already exists for company_id={company_id!r}"
        )

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

    # Readback site
    if _site_read_fn is not None:
        stored_site = _site_read_fn(supabase, site_id)
    else:
        res = supabase.table("construction_sites").select("*").eq("id", site_id).limit(1).execute()
        data = list(getattr(res, "data", None) or [])
        stored_site = data[0] if data else None

    # Readback factory bridge
    if _factory_read_fn is not None:
        stored_factory = _factory_read_fn(supabase, factory_id)
    else:
        res = supabase.table("factories").select("*").eq("id", factory_id).limit(1).execute()
        data = list(getattr(res, "data", None) or [])
        stored_factory = data[0] if data else None

    # Full factory bridge verification (includes company_id)
    cst_verify = verify_cst_c1_exact(stored_site, stored_factory, case_data, company_id)

    # Common source readback — proven empty (or exact) via actual readback
    work_read = _work_read_fn or _default_work_read
    work_rows = work_read(supabase, factory_id)
    work_verify = _verify_work_readback(work_rows, case_data.get("works") or [])

    mat_read = _material_read_fn or _default_material_read
    mat_rows = mat_read(supabase, factory_id)
    material_verify = _verify_material_readback(mat_rows, case_data.get("materials") or [])

    eq_read = _equipment_read_fn or _default_equipment_read
    eq_rows = eq_read(supabase, factory_id)
    equipment_verify = _verify_equipment_readback(eq_rows, case_data.get("equipment") or [])

    pipeline_c1_exact = bool(
        cst_verify["exact"]
        and work_verify["exact"]
        and material_verify["exact"]
        and equipment_verify["exact"]
    )

    return {
        "site_id":                site_id,
        "factory_id":             factory_id,
        "contract_amount_eok":    site_payload.get("contract_amount"),
        "site_type":              site_payload.get("site_type"),
        "pipeline_c1_exact":      pipeline_c1_exact,
        "direct_source_exact":    cst_verify["exact"],
        "work_source_exact":      work_verify["exact"],
        "material_source_exact":  material_verify["exact"],
        "equipment_source_exact": equipment_verify["exact"],
        "verify": {
            "site_factory": cst_verify,
            "work":         work_verify,
            "material":     material_verify,
            "equipment":    equipment_verify,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Sector router
# ─────────────────────────────────────────────────────────────────────────────

def provision_case(
    supabase: Any,
    case_data: dict,
    company_id: str,
    *,
    _mfg_seams: Optional[dict] = None,
    _bld_seams: Optional[dict] = None,
    _cst_seams: Optional[dict] = None,
) -> dict:
    """Route provisioning to sector-specific orchestrator.

    Passes seam dicts to allow per-sector mock injection in tests.
    """
    sector = case_data.get("sector")
    if sector == "MANUFACTURING":
        return provision_mfg_c1(supabase, case_data, company_id, **(_mfg_seams or {}))
    elif sector == "BUILDING":
        return provision_bld_c1(supabase, case_data, company_id, **(_bld_seams or {}))
    elif sector == "CONSTRUCTION":
        return provision_cst_source(supabase, case_data, company_id, **(_cst_seams or {}))
    else:
        raise ValueError(f"PROVISION_CASE_UNKNOWN_SECTOR: {sector!r}")


# ─────────────────────────────────────────────────────────────────────────────
# Manifest C1 entry builder
# ─────────────────────────────────────────────────────────────────────────────

def build_manifest_c1_entry(
    case_data: dict,
    provision_result: dict,
) -> dict:
    """Build manifest entry with pipeline_c1_exact + c1 sub-object.

    All exactness flags derive from provision_result (orchestrator output).
    direct_source_exact uses provision_result["direct_source_exact"] key.
    """
    sector = case_data.get("sector", "")
    direct_source_exact = bool(provision_result.get("direct_source_exact"))
    work_exact   = bool(provision_result.get("work_source_exact"))
    mat_exact    = bool(provision_result.get("material_source_exact"))
    equip_exact  = bool(provision_result.get("equipment_source_exact"))

    non_pipeline: Dict[str, str] = {}
    if sector == "BUILDING":
        for f in BLD_NOT_PIPELINE_FIELDS:
            non_pipeline[f] = "NOT_CURRENTLY_CONSUMED"
    elif sector == "CONSTRUCTION":
        for f in CST_NOT_PIPELINE_FIELDS:
            non_pipeline[f] = "NOT_CURRENTLY_CONSUMED"

    c1: Dict[str, Any] = {
        "direct_source_exact":    direct_source_exact,
        "work_source_exact":      work_exact,
        "material_source_exact":  mat_exact,
        "equipment_source_exact": equip_exact,
    }

    if sector == "MANUFACTURING":
        process_exact = bool(provision_result.get("process_source_exact"))
        c1["process_source_exact"] = process_exact
        pipeline_c1_exact = bool(
            direct_source_exact
            and process_exact
            and work_exact
            and mat_exact
            and equip_exact
        )
    else:
        c1["process_source_status"] = "NOT_REQUIRED"
        pipeline_c1_exact = bool(
            direct_source_exact
            and work_exact
            and mat_exact
            and equip_exact
        )

    entry: Dict[str, Any] = {
        "case_id":           case_data["case_id"],
        "sector":            sector,
        "factory_id":        provision_result.get("factory_id"),
        "site_id":           provision_result.get("site_id"),
        "pipeline_c1_exact": pipeline_c1_exact,
        "source_exact":      pipeline_c1_exact,  # legacy compat
        "c1":                c1,
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
        "direct_source":     {"status": "PROVISIONED" if provision_result.get("direct_source_exact") else "PENDING"},
        "work_source":       {"status": "PROVISIONED" if provision_result.get("work_source_exact")     else "EMPTY_OR_PENDING"},
        "material_source":   {"status": "PROVISIONED" if provision_result.get("material_source_exact") else "EMPTY_OR_PENDING"},
        "equipment_source":  {"status": "PROVISIONED" if provision_result.get("equipment_source_exact") else "EMPTY_OR_PENDING"},
    }
    if not_bound:
        evidence["not_bound"] = not_bound
    if non_pipeline:
        evidence["non_pipeline_baseline_fields"] = non_pipeline
    return evidence
