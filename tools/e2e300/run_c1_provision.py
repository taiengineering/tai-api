"""WO-E2E300-3SECTOR-PILOT-GATE-CLOSEOUT-005C PATCH-1 — Frozen300 C1 Pilot Runner.

Reproducible pilot execution entrypoint for 3-sector C1 provisioning.
Allowed pilot cases: MFG-001, BLD-001, CST-001 (exact set for execute=True).
PRODUCTION_WRITE = 0 without execute=True.
No LEG imports — C1 source provisioning only.

PATCH-1 changes from 005C:
  - case_file: required explicit parameter, no hardcoded/default path
  - SHA verification from actual file bytes before any DB access
  - execute=True requires exactly {MFG-001, BLD-001, CST-001}
  - manifest: case_sha field + cases array (run_leg_engine_matrix compatible)
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from provision_frozen_c1 import (
    build_c1_source_evidence,
    build_manifest_c1_entry,
    provision_case,
)

CASE_SHA = "20f39a93cc18dce4cec4229df0a001b6219de91bd926a0176509f5d313040efd"
PILOT_ALLOWED_CASES: frozenset = frozenset({"MFG-001", "BLD-001", "CST-001"})
PILOT_EXACT_CASE_IDS: frozenset = frozenset({"MFG-001", "BLD-001", "CST-001"})
MAX_PRODUCTION_CASES: int = 3

_SECTOR_ORDER = ["MANUFACTURING", "BUILDING", "CONSTRUCTION"]


class PilotCaseNotAllowedError(RuntimeError):
    """case_id not in PILOT_ALLOWED_CASES, or execute=True set != {MFG-001,BLD-001,CST-001}."""
    code = "PILOT_CASE_NOT_ALLOWED"


class StalePrefightError(RuntimeError):
    """Stale preflight detected — all-or-none gate blocked."""
    code = "STALE_PREFLIGHT_BLOCKED"


class CaseFileSHAMismatchError(RuntimeError):
    """case_universe_v1.json SHA mismatch — not the canonical frozen version."""
    code = "CASE_FILE_SHA_MISMATCH"


def _default_stale_check(supabase: Any, case_id: str, case_data: dict, company_id: str) -> bool:
    """Returns True if factory/site name already exists for company_id."""
    sector = case_data.get("sector")
    name = case_data["factory_name"]
    if sector == "CONSTRUCTION":
        res = (supabase.table("construction_sites")
               .select("id").eq("site_name", name).eq("company_id", company_id).limit(1).execute())
    else:
        res = (supabase.table("factories")
               .select("id").eq("name", name).eq("company_id", company_id).limit(1).execute())
    return bool(getattr(res, "data", None))


def run(
    case_ids: List[str],
    company_id: str,
    execute: bool,
    supabase: Any,
    case_file: Any,                                    # Path or str, REQUIRED — no default
    *,
    _provision_fn: Optional[Callable] = None,
    _stale_check_fn: Optional[Callable] = None,
    _runs_dir: Optional[Path] = None,
    _file_bytes_fn: Optional[Callable] = None,         # (Path) -> bytes, injectable for tests
) -> dict:
    """Provision C1 source for pilot cases.

    execute=False: DRY_RUN_ONLY — validates pilot gate, returns early (no SHA check, no DB).
    execute=True:
      1. individual pilot gate (each id in PILOT_ALLOWED_CASES)
      2. exact-3 gate (set must be exactly {MFG-001, BLD-001, CST-001})
      3. SHA verification from case_file bytes (CASE_FILE_SHA_MISMATCH if wrong)
      4. JSON parse → cases_by_id
      5. stale preflight — all-or-none
      6. sequential provision MFG → BLD → CST
      7. write artifacts + manifest
    """
    # Step 1: individual pilot gate (all paths)
    for case_id in case_ids:
        if case_id not in PILOT_ALLOWED_CASES:
            raise PilotCaseNotAllowedError(
                f"PILOT_CASE_NOT_ALLOWED: {case_id!r} not in {sorted(PILOT_ALLOWED_CASES)}"
            )

    # Step 2: DRY_RUN early exit — no case_file access, no DB touch
    if not execute:
        return {
            "status":     "DRY_RUN_ONLY",
            "case_ids":   list(case_ids),
            "company_id": company_id,
            "message":    "Pass execute=True to perform actual writes.",
        }

    # Step 3: exact-3 gate (execute=True only)
    if len(case_ids) != len(set(case_ids)):
        raise PilotCaseNotAllowedError(
            f"PILOT_EXACT_SET_REQUIRED: duplicate case_ids detected in {list(case_ids)}"
        )
    if set(case_ids) != PILOT_EXACT_CASE_IDS:
        raise PilotCaseNotAllowedError(
            f"PILOT_EXACT_SET_REQUIRED: execute=True requires exactly "
            f"{sorted(PILOT_EXACT_CASE_IDS)}, got {sorted(set(case_ids))}"
        )

    # Step 4: SHA verification from actual file bytes — before any DB access
    case_file_path = Path(case_file)
    bytes_fn = _file_bytes_fn or (lambda p: p.read_bytes())
    raw_bytes = bytes_fn(case_file_path)
    actual_sha = hashlib.sha256(raw_bytes).hexdigest()
    if actual_sha != CASE_SHA:
        raise CaseFileSHAMismatchError(
            f"CASE_FILE_SHA_MISMATCH: "
            f"expected={CASE_SHA[:12]}…  got={actual_sha[:12]}…"
        )

    # Step 5: JSON parse → cases_by_id
    data = json.loads(raw_bytes)
    cases_by_id: Dict[str, dict] = {c["case_id"]: c for c in data.get("cases", [])}

    # Step 6: stale preflight — all-or-none before first write
    stale_check_fn = _stale_check_fn or _default_stale_check
    stale_cases: List[str] = []
    for case_id in case_ids:
        case_data = cases_by_id[case_id]
        if stale_check_fn(supabase, case_id, case_data, company_id):
            stale_cases.append(case_id)
    if stale_cases:
        raise StalePrefightError(
            f"STALE_PREFLIGHT_BLOCKED: stale cases detected: {stale_cases}"
        )

    # Step 7: run directory
    runs_dir = Path(_runs_dir) if _runs_dir else (Path(__file__).parent.parent.parent / "e2e300_runs")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "cases").mkdir(exist_ok=True)

    # Step 8: sequential provision MFG → BLD → CST
    provision_fn = _provision_fn or provision_case
    ordered = sorted(
        case_ids,
        key=lambda cid: (
            _SECTOR_ORDER.index(cases_by_id[cid].get("sector", ""))
            if cases_by_id[cid].get("sector") in _SECTOR_ORDER else 99
        ),
    )

    manifest_cases: List[dict] = []
    for case_id in ordered:
        case_data = cases_by_id[case_id]
        provision_result = provision_fn(supabase, case_data, company_id)
        entry = build_manifest_c1_entry(case_data, provision_result)
        evidence = build_c1_source_evidence(case_data, provision_result)

        case_dir = run_dir / "cases" / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        (case_dir / "c1_source_evidence.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2)
        )
        manifest_cases.append(entry)

    # Step 9: write manifest (run_leg_engine_matrix compatible)
    manifest: Dict[str, Any] = {
        "run_id":     run_id,
        "case_sha":   CASE_SHA,          # required by run_leg_engine_matrix.load_manifest
        "company_id": company_id,
        "case_ids":   ordered,
        "cases":      manifest_cases,    # authority array for load_manifest / run_case
        "entries":    manifest_cases,    # legacy alias (same list)
        "all_exact":  all(e["pipeline_c1_exact"] for e in manifest_cases),
    }
    (run_dir / "provision_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2)
    )

    return {
        "status":   "PROVISIONED",
        "run_id":   run_id,
        "run_dir":  str(run_dir),
        "manifest": manifest,
    }
