#!/usr/bin/env python3
"""WO-E2E300-PERSISTENCE-FREE-LEG-HARNESS-004 PATCH-004B — Engine Matrix.

Reads provision_manifest.json (written by data_driven_runner.mjs --phase provision).
Dispatches each case to the production write-free LEG seam:
  MANUFACTURING → run_safe_industrial_leg(supabase, factory_id, consumer_input)
  BUILDING      → run_safe_building_leg(supabase, factory_id, consumer_input)
  CONSTRUCTION  → run_safe_construction_leg(supabase, site_id, consumer_input)

DB WRITE fence: WriteBlockedBuilder wraps every builder in the chain.
  Any .insert/.update/.upsert/.delete at ANY chain depth → AssertionError.
  .rpc() on the Supabase client → AssertionError.
  Read chain (.select→.eq→.limit→.execute) passes through.

Forbidden imports (never present in this module):
  _finalize_saas_leg_http, _persist_saas_leg, _materialize_inspection_sets,
  SaasLegCommonFinalizer, apply_saas_v2_initial_payment_runtime.

CLI:
  --manifest   <provision_manifest.json>   (required)
  --case-file  <case_universe_v1.json>     (required — SHA-verified against CASE_SHA)
  --output-dir <dir>                       (required)
  --case-id    <MFG-001>                   (optional: single case)
  --sector     MANUFACTURING|BUILDING|CONSTRUCTION  (optional: filter)

Writes per case:
  <output-dir>/cases/<case_id>/engine_result.json    — raw result + execution_validation
  <output-dir>/cases/<case_id>/execution_verdict.json — verdict summary
Writes aggregate:
  <output-dir>/engine_matrix_summary.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

CASE_SHA = "20f39a93cc18dce4cec4229df0a001b6219de91bd926a0176509f5d313040efd"

_WRITE_OPS = frozenset(("insert", "update", "upsert", "delete"))

# LEG output sector values differ from case universe sector names.
_SECTOR_TO_LEG_SECTOR: Dict[str, str] = {
    "MANUFACTURING": "INDUSTRIAL",
    "BUILDING":      "BUILDING",
    "CONSTRUCTION":  "CONSTRUCTION",
}

# LEG system-error statuses that indicate an engine-level failure.
_LEG_SYSTEM_ERROR_STATUSES = frozenset({
    "REPO_QUERY_ERROR",
    "INTERNAL_ERROR",
    "INPUT_REJECTED",
})


# ─────────────────────────────────────────────────────────────────────────────
# DB write fence — chain-preserving proxy
# ─────────────────────────────────────────────────────────────────────────────

def _is_builder(obj: Any) -> bool:
    """True when obj is a Supabase builder that accepts further chaining."""
    return (
        obj is not None
        and not isinstance(obj, (bool, int, float, str, bytes, type(None)))
        and hasattr(obj, "execute")
        and callable(getattr(obj, "execute", None))
    )


class WriteBlockedBuilder:
    """Chain-preserving proxy for any Supabase builder.

    Blocks .insert/.update/.upsert/.delete at every depth.
    Read methods return WriteBlockedBuilder-wrapped results so chains like
    .select().eq().update() are still blocked.
    Only the final .execute() response is returned unwrapped.
    """
    def __init__(self, inner: Any) -> None:
        self.__dict__["_inner"] = inner

    def __getattr__(self, name: str) -> Any:
        if name in _WRITE_OPS:
            def _blocked(*a: Any, **kw: Any) -> None:
                raise AssertionError(
                    f"E2E300_ENGINE_MATRIX_DB_WRITE_BLOCKED: .{name}() is forbidden"
                )
            return _blocked
        attr = getattr(self.__dict__["_inner"], name)
        if not callable(attr):
            return attr
        def _proxy_call(*a: Any, **kw: Any) -> Any:
            result = attr(*a, **kw)
            return WriteBlockedBuilder(result) if _is_builder(result) else result
        return _proxy_call

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "_inner":
            self.__dict__["_inner"] = value
        else:
            setattr(self.__dict__["_inner"], name, value)


class WriteBlockedSupabase:
    """Wraps a real or mock Supabase client.

    .table() returns a WriteBlockedBuilder.
    .rpc() is unconditionally blocked (no read RPC allowlist yet).
    All other attributes proxied transparently.
    """
    def __init__(self, inner: Any) -> None:
        self.__dict__["_inner"] = inner

    def table(self, name: str) -> WriteBlockedBuilder:
        return WriteBlockedBuilder(self.__dict__["_inner"].table(name))

    def rpc(self, *a: Any, **kw: Any) -> None:
        raise AssertionError("E2E300_ENGINE_MATRIX_RPC_BLOCKED: .rpc() is forbidden")

    def __getattr__(self, name: str) -> Any:
        return getattr(self.__dict__["_inner"], name)


# ─────────────────────────────────────────────────────────────────────────────
# Manifest loading (SHA against manifest field only)
# ─────────────────────────────────────────────────────────────────────────────

def load_manifest(manifest_path: str) -> dict:
    raw = Path(manifest_path).read_text(encoding="utf-8")
    manifest = json.loads(raw)
    stored_sha = manifest.get("case_sha", "")
    if stored_sha != CASE_SHA:
        raise ValueError(
            f"MANIFEST_CASE_SHA_MISMATCH: "
            f"expected={CASE_SHA[:12]}…  got={str(stored_sha)[:12]}…"
        )
    return manifest


# ─────────────────────────────────────────────────────────────────────────────
# Case universe loading — SHA computed from actual file bytes
# ─────────────────────────────────────────────────────────────────────────────

def load_case_universe(case_file: str) -> Dict[str, dict]:
    """Load case universe JSON.  SHA-verified against CASE_SHA from actual bytes.

    Raises ValueError on SHA mismatch or duplicate case_id.
    """
    path = Path(case_file)
    raw_bytes = path.read_bytes()
    actual_sha = hashlib.sha256(raw_bytes).hexdigest()
    if actual_sha != CASE_SHA:
        raise ValueError(
            f"CASE_FILE_SHA_MISMATCH: "
            f"expected={CASE_SHA[:12]}…  got={actual_sha[:12]}…"
        )
    data = json.loads(raw_bytes.decode("utf-8"))
    seen_ids: set = set()
    for c in data.get("cases", []):
        cid = c["case_id"]
        if cid in seen_ids:
            raise ValueError(f"CASE_FILE_DUPLICATE_CASE_ID: {cid!r}")
        seen_ids.add(cid)
    return {c["case_id"]: c for c in data.get("cases", [])}


# ─────────────────────────────────────────────────────────────────────────────
# Frozen consumer override adapter
# ─────────────────────────────────────────────────────────────────────────────

def build_frozen_consumer_overrides(case_data: dict, sector: str) -> dict:
    """Extract consumer override fields from frozen case sector_fields.

    MANUFACTURING: has_high_pressure_gas / has_chemical_substance / has_boiler
      These are USER_CONFIRM fields that run_safe_industrial_leg masks to None
      before LEG.  Frozen false/true values must be passed explicitly.
      False = explicit "not present"; absent key = None = "not yet confirmed".

    BUILDING / CONSTRUCTION: production assembler (OWNED_EXACT + VERIFIED_SOURCE +
      assemble_construction_marketing_contract) is the source authority.
      No sector_fields → SafeXxxConsumerInput mapping is production-verified.
      Invented aliases (building_use_code → building_use_type, etc.) = forbidden.

    Never converts None/absent to false.  Never adds alias fields.
    """
    sf = case_data.get("sector_fields") or {}

    if sector == "MANUFACTURING":
        overrides: Dict[str, Any] = {}
        for field in ("has_high_pressure_gas", "has_chemical_substance", "has_boiler"):
            if field in sf:
                overrides[field] = sf[field]
        return overrides

    # BLD / CST: assembler is authority — empty override dict.
    return {}


def build_consumer_input(case_data: dict, sector: str) -> Any:
    """Build SafeXxxConsumerInput from frozen case + consumer_input.

    Priority: frozen sector_fields overrides first, then explicit consumer_input.
    None = not overriding (exclude_none=True); false/0 = explicit override.
    """
    from schemas.legal_engine import (
        SafeBuildingConsumerInput,
        SafeConstructionConsumerInput,
        SafeIndustrialConsumerInput,
    )
    _SCHEMA_MAP: Dict[str, Any] = {
        "MANUFACTURING": SafeIndustrialConsumerInput,
        "BUILDING":      SafeBuildingConsumerInput,
        "CONSTRUCTION":  SafeConstructionConsumerInput,
    }
    schema_cls = _SCHEMA_MAP.get(sector)
    if schema_cls is None:
        raise ValueError(f"UNKNOWN_SECTOR_FOR_CONSUMER_INPUT: {sector!r}")

    frozen_overrides = build_frozen_consumer_overrides(case_data, sector)
    explicit_ci: dict = case_data.get("consumer_input") or {}
    merged = {**frozen_overrides, **explicit_ci}
    return schema_cls(**merged)


# ─────────────────────────────────────────────────────────────────────────────
# LEG result contract validator
# ─────────────────────────────────────────────────────────────────────────────

def validate_engine_result(result: dict, expected_sector: str) -> dict:
    """Validate the engine result against the LEG output contract.

    Contract (minimum):
      full_result.engine_family == "LEG"
      full_result.fallback_used is False
      full_result.leg_status NOT IN system-error set
      full_result.leg_trace_id non-empty
      full_result.obligations_raw is list
      full_result.applicable_count is int == len(obligations_raw)

    Returns dict with 'valid' bool, 'errors' list, and per-field verdicts.
    """
    errors: List[str] = []

    if not isinstance(result, dict):
        return {"valid": False, "errors": ["RESULT_NOT_DICT"]}

    full_result = result.get("full_result")
    if not isinstance(full_result, dict):
        errors.append("FULL_RESULT_NOT_DICT")
        return {
            "valid": False, "errors": errors,
            "engine_family": None, "fallback_used": None,
            "leg_status": None, "leg_trace_id_present": False,
            "obligations_raw_list": False, "applicable_count_exact": False,
        }

    # engine_family
    engine_family = full_result.get("engine_family")
    if engine_family != "LEG":
        errors.append(f"ENGINE_FAMILY_NOT_LEG:{engine_family!r}")

    # fallback_used — must be exactly False (not falsy)
    fallback_used = full_result.get("fallback_used")
    if fallback_used is not False:
        errors.append(f"FALLBACK_USED_NOT_FALSE:{fallback_used!r}")

    # leg_status — must not be a system error
    leg_status = full_result.get("leg_status")
    if leg_status in _LEG_SYSTEM_ERROR_STATUSES:
        errors.append(f"LEG_STATUS_SYSTEM_ERROR:{leg_status!r}")

    # leg_trace_id — must be non-empty
    trace_id = full_result.get("leg_trace_id") or full_result.get("trace_id") or ""
    leg_trace_id_present = bool(trace_id)
    if not leg_trace_id_present:
        errors.append("LEG_TRACE_ID_MISSING")

    # obligations_raw — must be a list
    obligations_raw = full_result.get("obligations_raw")
    obligations_raw_list = isinstance(obligations_raw, list)
    if not obligations_raw_list:
        errors.append(f"OBLIGATIONS_RAW_NOT_LIST:{type(obligations_raw).__name__!r}")

    # applicable_count — must be int and == len(obligations_raw)
    applicable_count = full_result.get("applicable_count")
    applicable_count_exact = False
    if not isinstance(applicable_count, int):
        errors.append(f"APPLICABLE_COUNT_NOT_INT:{type(applicable_count).__name__!r}")
    elif obligations_raw_list:
        if applicable_count == len(obligations_raw):
            applicable_count_exact = True
        else:
            errors.append(
                f"APPLICABLE_COUNT_MISMATCH:"
                f"applicable_count={applicable_count},"
                f"len(obligations_raw)={len(obligations_raw)}"
            )

    # sector (optional check — absent = skip)
    expected_leg_sector = _SECTOR_TO_LEG_SECTOR.get(expected_sector)
    actual_sector = full_result.get("sector")
    if expected_leg_sector and actual_sector and actual_sector != expected_leg_sector:
        errors.append(
            f"SECTOR_MISMATCH:expected={expected_leg_sector!r},actual={actual_sector!r}"
        )

    return {
        "valid":                 len(errors) == 0,
        "errors":                errors,
        "engine_family":         engine_family,
        "fallback_used":         fallback_used,
        "leg_status":            leg_status,
        "leg_trace_id_present":  leg_trace_id_present,
        "obligations_raw_list":  obligations_raw_list,
        "applicable_count_exact": applicable_count_exact,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Dispatch — injectable seams for tests
# ─────────────────────────────────────────────────────────────────────────────

def dispatch(
    supabase_wrapped: Any,
    manifest_case: dict,
    consumer_input: Any,
    *,
    _industrial_seam:   Optional[Any] = None,
    _building_seam:     Optional[Any] = None,
    _construction_seam: Optional[Any] = None,
) -> dict:
    """Dispatch to correct write-free LEG seam.  Returns raw seam result dict.

    Statuses from this function: 'OK' | 'BLOCKED'.
    Validation happens in run_case() after this call.
    """
    sector     = manifest_case["sector"]
    case_id    = manifest_case["case_id"]
    factory_id = manifest_case.get("factory_id")
    site_id    = manifest_case.get("site_id")

    if sector == "MANUFACTURING":
        if not factory_id:
            return {"status": "BLOCKED", "reason": "FACTORY_ID_REQUIRED_FOR_MANUFACTURING",
                    "case_id": case_id, "sector": sector}
        if _industrial_seam is None:
            from services.safe_industrial_leg_runtime import run_safe_industrial_leg
            _industrial_seam = run_safe_industrial_leg
        raw = _industrial_seam(supabase_wrapped, factory_id, consumer_input)
        return {"status": "OK", "case_id": case_id, "sector": sector,
                "contract_version":  raw.get("contract_version"),
                "unresolved_fields": raw.get("unresolved_fields"),
                "full_result":       raw.get("full_result")}

    if sector == "BUILDING":
        if not factory_id:
            return {"status": "BLOCKED", "reason": "FACTORY_ID_REQUIRED_FOR_BUILDING",
                    "case_id": case_id, "sector": sector}
        if _building_seam is None:
            from services.safe_building_leg_runtime import run_safe_building_leg
            _building_seam = run_safe_building_leg
        raw = _building_seam(supabase_wrapped, factory_id, consumer_input)
        return {"status": "OK", "case_id": case_id, "sector": sector,
                "contract_version":  raw.get("contract_version"),
                "unresolved_fields": raw.get("unresolved_fields"),
                "full_result":       raw.get("full_result")}

    if sector == "CONSTRUCTION":
        if not site_id:
            return {"status": "BLOCKED", "reason": "SITE_ID_REQUIRED_FOR_CONSTRUCTION",
                    "case_id": case_id, "sector": sector}
        from services.safe_construction_leg_runtime import ConstructionSiteBridgeError
        if _construction_seam is None:
            from services.safe_construction_leg_runtime import run_safe_construction_leg
            _construction_seam = run_safe_construction_leg
        try:
            raw = _construction_seam(supabase_wrapped, site_id, consumer_input)
        except ConstructionSiteBridgeError as exc:
            return {"status": "BLOCKED", "reason": "CONSTRUCTION_SITE_BRIDGE_ERROR",
                    "case_id": case_id, "sector": sector, "detail": str(exc)}
        return {"status": "OK", "case_id": case_id, "sector": sector,
                "contract_version":  raw.get("contract_version"),
                "unresolved_fields": raw.get("unresolved_fields"),
                "full_result":       raw.get("full_result"),
                "factory_id":        raw.get("factory_id")}

    return {"status": "BLOCKED", "reason": f"UNKNOWN_SECTOR:{sector!r}",
            "case_id": case_id, "sector": sector}


# ─────────────────────────────────────────────────────────────────────────────
# Per-case runner
# ─────────────────────────────────────────────────────────────────────────────

def run_case(
    supabase_raw: Any,
    manifest_case: dict,
    case_universe: Dict[str, dict],
    *,
    _industrial_seam:   Optional[Any] = None,
    _building_seam:     Optional[Any] = None,
    _construction_seam: Optional[Any] = None,
) -> dict:
    """Run one case through the engine matrix.

    Returns a status dict with 'status' in:
      'OK'      — seam dispatched + LEG contract valid
      'FAIL'    — seam dispatched but LEG contract invalid
      'BLOCKED' — cannot run (missing ids, unknown sector, not in universe)
      'SKIPPED' — source_exact=False
      'ERROR'   — unexpected exception
    """
    case_id = manifest_case["case_id"]
    sector  = manifest_case["sector"]

    # source_exact gate
    if not manifest_case.get("source_exact"):
        return {"status": "SKIPPED", "reason": "SOURCE_NOT_EXACT",
                "case_id": case_id, "sector": sector}

    # Frozen universe identity gate
    case_data = case_universe.get(case_id)
    if case_data is None:
        return {"status": "BLOCKED", "reason": "CASE_NOT_FOUND_IN_FROZEN_UNIVERSE",
                "case_id": case_id, "sector": sector}

    # Consumer input build
    try:
        consumer_input = build_consumer_input(case_data, sector)
    except Exception as exc:
        return {"status": "ERROR", "reason": f"CONSUMER_INPUT_ERROR:{exc}",
                "case_id": case_id, "sector": sector}

    supabase_wrapped = WriteBlockedSupabase(supabase_raw)
    try:
        result = dispatch(
            supabase_wrapped, manifest_case, consumer_input,
            _industrial_seam=_industrial_seam,
            _building_seam=_building_seam,
            _construction_seam=_construction_seam,
        )
    except Exception as exc:
        return {"status": "ERROR", "reason": f"SEAM_ERROR:{type(exc).__name__}:{exc}",
                "case_id": case_id, "sector": sector}

    # LEG result contract validation (only for dispatched OK cases)
    if result.get("status") == "OK":
        validation = validate_engine_result(result, sector)
        result["execution_validation"] = validation
        if not validation["valid"]:
            result["status"] = "FAIL"
            result["reason"] = "ENGINE_RESULT_INVALID"
            result["validation_errors"] = validation["errors"]

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Output writers
# ─────────────────────────────────────────────────────────────────────────────

def write_case_result(output_dir: str, case_id: str, result: dict) -> None:
    """Write engine_result.json with structured fields. full_result NOT transformed."""
    case_dir = Path(output_dir) / "cases" / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    engine_result = {
        "case_id":             result.get("case_id"),
        "sector":              result.get("sector"),
        "status":              result.get("status"),
        "contract_version":    result.get("contract_version"),
        "unresolved_fields":   result.get("unresolved_fields"),
        "full_result":         result.get("full_result"),
        "execution_validation": result.get("execution_validation"),
    }
    (case_dir / "engine_result.json").write_text(
        json.dumps(engine_result, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


def write_execution_verdict(output_dir: str, case_id: str, result: dict) -> None:
    """Write execution_verdict.json — compact verdict with semantic_status=NOT_EVALUATED."""
    case_dir = Path(output_dir) / "cases" / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    validation = result.get("execution_validation") or {}
    verdict = {
        "case_id":              case_id,
        "status":               result.get("status"),
        "engine_family":        validation.get("engine_family"),
        "fallback_used":        validation.get("fallback_used"),
        "leg_status":           validation.get("leg_status"),
        "leg_trace_id_present": validation.get("leg_trace_id_present"),
        "obligations_raw_list": validation.get("obligations_raw_list"),
        "applicable_count_exact": validation.get("applicable_count_exact"),
        "semantic_status":      "NOT_EVALUATED",
    }
    (case_dir / "execution_verdict.json").write_text(
        json.dumps(verdict, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


def write_summary(output_dir: str, results: List[dict]) -> dict:
    """Write engine_matrix_summary.json with sector counts and execution metrics."""
    total           = len(results)
    execution_pass  = sum(1 for r in results if r.get("status") == "OK")
    execution_fail  = sum(1 for r in results if r.get("status") == "FAIL")
    blocked         = sum(1 for r in results if r.get("status") == "BLOCKED")
    skipped         = sum(1 for r in results if r.get("status") == "SKIPPED")
    error           = sum(1 for r in results if r.get("status") == "ERROR")

    sector_counts: Dict[str, int] = {}
    for r in results:
        s = r.get("sector", "UNKNOWN")
        sector_counts[s] = sector_counts.get(s, 0) + 1

    fallback_used_count = sum(
        1 for r in results
        if r.get("execution_validation", {}).get("fallback_used") is True
    )
    system_error_count = sum(
        1 for r in results
        if any(
            "LEG_STATUS_SYSTEM_ERROR" in str(e)
            for e in (r.get("execution_validation") or {}).get("errors", [])
        )
    )

    summary = {
        "case_sha":           CASE_SHA,
        "total":              total,
        "sector_counts":      sector_counts,
        "execution_pass":     execution_pass,
        "execution_fail":     execution_fail,
        "blocked":            blocked,
        "skipped":            skipped,
        "error":              error,
        "fallback_used_count": fallback_used_count,
        "system_error_count":  system_error_count,
        "semantic_status":    "NOT_EVALUATED",
        "all_pass":           execution_fail == 0 and error == 0,
        "results": [
            {
                "case_id": r.get("case_id"),
                "sector":  r.get("sector"),
                "status":  r.get("status"),
                "reason":  r.get("reason"),
            }
            for r in results
        ],
    }
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    (Path(output_dir) / "engine_matrix_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return summary


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="E2E300 Engine Matrix Harness")
    parser.add_argument("--manifest",   required=True, help="Path to provision_manifest.json")
    parser.add_argument("--case-file",  required=True, help="Path to case_universe_v1.json (SHA-verified)")
    parser.add_argument("--output-dir", required=True, help="Output directory for results")
    parser.add_argument("--case-id",    default=None,  help="Filter: run single case")
    parser.add_argument("--sector",     default=None,
                        choices=["MANUFACTURING", "BUILDING", "CONSTRUCTION"],
                        help="Filter: sector")
    args = parser.parse_args()

    manifest      = load_manifest(args.manifest)
    case_universe = load_case_universe(args.case_file)

    from db.supabase_client import get_supabase
    supabase_raw = get_supabase()

    cases: list = manifest.get("cases", [])
    if args.case_id:
        cases = [c for c in cases if c["case_id"] == args.case_id]
    if args.sector:
        cases = [c for c in cases if c["sector"] == args.sector]

    results: List[dict] = []
    for mc in cases:
        result = run_case(supabase_raw, mc, case_universe)
        write_case_result(args.output_dir, mc["case_id"], result)
        write_execution_verdict(args.output_dir, mc["case_id"], result)
        status = result.get("status", "?")
        reason = result.get("reason", "")
        suffix = f" ({reason})" if reason else ""
        print(f"[E2E300] {mc['case_id']} ({mc['sector']}) → {status}{suffix}")
        results.append(result)

    summary = write_summary(args.output_dir, results)
    print(
        f"[E2E300] summary: total={summary['total']}  "
        f"pass={summary['execution_pass']}  fail={summary['execution_fail']}  "
        f"blocked={summary['blocked']}  skipped={summary['skipped']}  error={summary['error']}"
    )
    if not summary["all_pass"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
