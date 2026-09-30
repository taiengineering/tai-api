"""WO-E2E300-3SECTOR-PILOT-GATE-CLOSEOUT-005C — Frozen300 C1 Pilot Runner.

Reproducible pilot execution entrypoint for 3-sector C1 provisioning.
Allowed pilot cases: MFG-001, BLD-001, CST-001.
PRODUCTION_WRITE = 0 without execute=True.
No LEG imports — C1 source provisioning only.
"""
from __future__ import annotations

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

PILOT_ALLOWED_CASES: frozenset = frozenset({"MFG-001", "BLD-001", "CST-001"})
MAX_PRODUCTION_CASES: int = 3

_UNIVERSE_PATH = (
    Path(__file__).parent.parent.parent
    / "TAI_E2E200" / "consumer-ui300" / "cases" / "case_universe_v1.json"
)

_SECTOR_ORDER = ["MANUFACTURING", "BUILDING", "CONSTRUCTION"]


class PilotCaseNotAllowedError(RuntimeError):
    """case_id not in PILOT_ALLOWED_CASES — pilot gate blocks execution."""
    code = "PILOT_CASE_NOT_ALLOWED"


class StalePrefightError(RuntimeError):
    """Stale preflight detected for one or more cases — all-or-none gate blocked."""
    code = "STALE_PREFLIGHT_BLOCKED"


def _default_cases_fn() -> Dict[str, dict]:
    data = json.loads(_UNIVERSE_PATH.read_bytes())
    return {c["case_id"]: c for c in data["cases"]}


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
    *,
    _provision_fn: Optional[Callable] = None,
    _stale_check_fn: Optional[Callable] = None,
    _runs_dir: Optional[Path] = None,
    _cases_fn: Optional[Callable] = None,
) -> dict:
    """Provision C1 source for pilot cases.

    execute=False: DRY_RUN_ONLY — validates inputs only, no DB writes.
    execute=True: runs stale preflight then provisions sequentially MFG→BLD→CST.

    Artifacts written to: <runs_dir>/<run_id>/provision_manifest.json
                          <runs_dir>/<run_id>/cases/<case_id>/c1_source_evidence.json
    """
    # Pilot gate
    for case_id in case_ids:
        if case_id not in PILOT_ALLOWED_CASES:
            raise PilotCaseNotAllowedError(
                f"PILOT_CASE_NOT_ALLOWED: {case_id!r} not in {sorted(PILOT_ALLOWED_CASES)}"
            )

    if len(case_ids) > MAX_PRODUCTION_CASES:
        raise ValueError(
            f"PILOT_MAX_EXCEEDED: requested {len(case_ids)} > MAX_PRODUCTION_CASES={MAX_PRODUCTION_CASES}"
        )

    if not execute:
        return {
            "status":     "DRY_RUN_ONLY",
            "case_ids":   list(case_ids),
            "company_id": company_id,
            "message":    "Pass execute=True to perform actual writes.",
        }

    # Load case data
    cases_fn = _cases_fn or _default_cases_fn
    cases_by_id: Dict[str, dict] = cases_fn()

    # Stale preflight — all-or-none before first write
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

    # Run directory
    runs_dir = Path(_runs_dir) if _runs_dir else (Path(__file__).parent.parent.parent / "e2e300_runs")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "cases").mkdir(exist_ok=True)

    # Sequential provision in MFG → BLD → CST order
    provision_fn = _provision_fn or provision_case
    ordered = sorted(
        case_ids,
        key=lambda cid: (
            _SECTOR_ORDER.index(cases_by_id[cid].get("sector", ""))
            if cases_by_id[cid].get("sector") in _SECTOR_ORDER else 99
        ),
    )

    manifest_entries: List[dict] = []
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
        manifest_entries.append(entry)

    manifest: Dict[str, Any] = {
        "run_id":     run_id,
        "company_id": company_id,
        "case_ids":   ordered,
        "entries":    manifest_entries,
        "all_exact":  all(e["pipeline_c1_exact"] for e in manifest_entries),
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
