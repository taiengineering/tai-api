#!/usr/bin/env python3
"""WO-E2E300-PERSISTENCE-FREE-LEG-HARNESS-004 — Engine Matrix.

Reads provision_manifest.json (written by data_driven_runner.mjs --phase provision).
Dispatches each case to the production write-free LEG seam:
  MANUFACTURING → run_safe_industrial_leg(supabase, factory_id, consumer_input)
  BUILDING      → run_safe_building_leg(supabase, factory_id, consumer_input)
  CONSTRUCTION  → run_safe_construction_leg(supabase, site_id, consumer_input)

DB WRITE fence: WriteBlockedSupabase wraps the real client — any .insert/.update/
  .upsert/.delete call on a table builder raises AssertionError immediately.

Forbidden imports (never present in this module):
  _finalize_saas_leg_http, _persist_saas_leg, _materialize_inspection_sets,
  SaasLegCommonFinalizer, apply_saas_v2_initial_payment_runtime.

CLI:
  --manifest   <provision_manifest.json>  (required)
  --case-file  <case_universe_v1.json>    (optional: consumer_input lookup)
  --output-dir <dir>                      (required)
  --case-id    <MFG-001>                  (optional: single case)
  --sector     MANUFACTURING|BUILDING|CONSTRUCTION  (optional: filter)

Writes:
  <output-dir>/cases/<case_id>/engine_result.json  — per case
  <output-dir>/engine_matrix_summary.json           — aggregate
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

CASE_SHA = "20f39a93cc18dce4cec4229df0a001b6219de91bd926a0176509f5d313040efd"

_WRITE_OPS = frozenset(("insert", "update", "upsert", "delete"))


# ─────────────────────────────────────────────────────────────────────────────
# DB write fence
# ─────────────────────────────────────────────────────────────────────────────

class WriteBlockedTable:
    """Proxy for a Supabase table builder — blocks all write operations."""
    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def __getattr__(self, name: str) -> Any:
        if name in _WRITE_OPS:
            def _blocked(*a: Any, **kw: Any) -> None:
                raise AssertionError(
                    f"E2E300_ENGINE_MATRIX_DB_WRITE_BLOCKED: .{name}() is forbidden"
                )
            return _blocked
        return getattr(self._inner, name)


class WriteBlockedSupabase:
    """Wraps a real or mock Supabase client; routes .table() through WriteBlockedTable."""
    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def table(self, name: str) -> WriteBlockedTable:
        return WriteBlockedTable(self._inner.table(name))

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


# ─────────────────────────────────────────────────────────────────────────────
# Manifest & case universe
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


def load_case_universe(case_file: Optional[str]) -> Dict[str, dict]:
    if not case_file:
        return {}
    raw = Path(case_file).read_text(encoding="utf-8")
    data = json.loads(raw)
    return {c["case_id"]: c for c in data.get("cases", [])}


# ─────────────────────────────────────────────────────────────────────────────
# Consumer input builder
# ─────────────────────────────────────────────────────────────────────────────

def build_consumer_input(case_data: Optional[dict], sector: str) -> Any:
    """Build SafeXxxConsumerInput from case's consumer_input field (or empty).

    None field → not passed as override (exclude_none=True semantics).
    false/0   → passed as explicit override — falsy-filter FORBIDDEN.
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
    raw: dict = (case_data or {}).get("consumer_input") or {}
    return schema_cls(**raw)


# ─────────────────────────────────────────────────────────────────────────────
# Dispatch — injectable seams for tests
# ─────────────────────────────────────────────────────────────────────────────

def dispatch(
    supabase_wrapped: Any,
    manifest_case: dict,
    consumer_input: Any,
    *,
    _industrial_seam: Optional[Any] = None,
    _building_seam:   Optional[Any] = None,
    _construction_seam: Optional[Any] = None,
) -> dict:
    """Dispatch to correct write-free LEG seam based on sector.

    Returns dict with 'status' in {'OK', 'BLOCKED'}.
    Seam functions are lazy-loaded (real) unless injected via _*_seam params (tests).
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
        result = _industrial_seam(supabase_wrapped, factory_id, consumer_input)
        return {"status": "OK", "case_id": case_id, "sector": sector, **result}

    if sector == "BUILDING":
        if not factory_id:
            return {"status": "BLOCKED", "reason": "FACTORY_ID_REQUIRED_FOR_BUILDING",
                    "case_id": case_id, "sector": sector}
        if _building_seam is None:
            from services.safe_building_leg_runtime import run_safe_building_leg
            _building_seam = run_safe_building_leg
        result = _building_seam(supabase_wrapped, factory_id, consumer_input)
        return {"status": "OK", "case_id": case_id, "sector": sector, **result}

    if sector == "CONSTRUCTION":
        if not site_id:
            return {"status": "BLOCKED", "reason": "SITE_ID_REQUIRED_FOR_CONSTRUCTION",
                    "case_id": case_id, "sector": sector}
        from services.safe_construction_leg_runtime import ConstructionSiteBridgeError
        if _construction_seam is None:
            from services.safe_construction_leg_runtime import run_safe_construction_leg
            _construction_seam = run_safe_construction_leg
        try:
            result = _construction_seam(supabase_wrapped, site_id, consumer_input)
        except ConstructionSiteBridgeError as exc:
            return {"status": "BLOCKED", "reason": "CONSTRUCTION_SITE_BRIDGE_ERROR",
                    "case_id": case_id, "sector": sector, "detail": str(exc)}
        return {"status": "OK", "case_id": case_id, "sector": sector, **result}

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
    _industrial_seam: Optional[Any] = None,
    _building_seam:   Optional[Any] = None,
    _construction_seam: Optional[Any] = None,
) -> dict:
    """Run one case through the engine matrix. Returns status dict."""
    case_id = manifest_case["case_id"]
    sector  = manifest_case["sector"]

    if not manifest_case.get("source_exact"):
        return {"status": "SKIPPED", "reason": "SOURCE_NOT_EXACT",
                "case_id": case_id, "sector": sector}

    case_data = case_universe.get(case_id)
    try:
        consumer_input = build_consumer_input(case_data, sector)
    except Exception as exc:
        return {"status": "ERROR", "reason": f"CONSUMER_INPUT_ERROR:{exc}",
                "case_id": case_id, "sector": sector}

    supabase_wrapped = WriteBlockedSupabase(supabase_raw)
    try:
        return dispatch(
            supabase_wrapped, manifest_case, consumer_input,
            _industrial_seam=_industrial_seam,
            _building_seam=_building_seam,
            _construction_seam=_construction_seam,
        )
    except Exception as exc:
        return {"status": "ERROR", "reason": f"SEAM_ERROR:{type(exc).__name__}:{exc}",
                "case_id": case_id, "sector": sector}


# ─────────────────────────────────────────────────────────────────────────────
# Output writers
# ─────────────────────────────────────────────────────────────────────────────

def write_case_result(output_dir: str, case_id: str, result: dict) -> None:
    case_dir = Path(output_dir) / "cases" / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "engine_result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


def write_summary(output_dir: str, results: List[dict]) -> dict:
    total   = len(results)
    ok      = sum(1 for r in results if r.get("status") == "OK")
    blocked = sum(1 for r in results if r.get("status") == "BLOCKED")
    skipped = sum(1 for r in results if r.get("status") == "SKIPPED")
    error   = sum(1 for r in results if r.get("status") == "ERROR")
    summary = {
        "total":   total,
        "ok":      ok,
        "blocked": blocked,
        "skipped": skipped,
        "error":   error,
        "all_ok":  ok == total,
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
    parser.add_argument("--case-file",  default=None,  help="Path to case_universe_v1.json")
    parser.add_argument("--output-dir", required=True, help="Output directory for results")
    parser.add_argument("--case-id",    default=None,  help="Filter: run single case")
    parser.add_argument("--sector",     default=None,
                        choices=["MANUFACTURING", "BUILDING", "CONSTRUCTION"],
                        help="Filter: sector")
    args = parser.parse_args()

    manifest     = load_manifest(args.manifest)
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
        status = result.get("status", "?")
        reason = result.get("reason", "")
        suffix = f" ({reason})" if reason else ""
        print(f"[E2E300] {mc['case_id']} ({mc['sector']}) → {status}{suffix}")
        results.append(result)

    summary = write_summary(args.output_dir, results)
    print(
        f"[E2E300] summary: total={summary['total']}  ok={summary['ok']}  "
        f"blocked={summary['blocked']}  skipped={summary['skipped']}  error={summary['error']}"
    )
    if not summary["all_ok"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
