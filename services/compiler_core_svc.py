"""Compiler Core — shared candidate fetch for routers and diagnosis services.

Reads pre-materialized runtime tables (facility_applicability, task_candidate, …).
Does not run batch evaluation; see scripts/run_facility_applicability.py for that.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from services import compiler_engine_gateway as compiler_gw

COMPILER_VERSION = "v3.0-deterministic"
COMPILER_WARNING = "All results are CANDIDATES. Not legal conclusions."

APPLICABILITY_MATCH_STATUSES = ("MATCH_CANDIDATE", "POSSIBLE_CANDIDATE")


def fetch_compiler_candidates(
    sb,
    factory_id: str,
    *,
    applicability_statuses: Optional[List[str]] = None,
    penalty_limit: int = 50,
) -> Dict[str, Any]:
    """
    Load Compiler Core candidate rows for a factory.

  Used by:
    - routers/compiler_core.py POST /evaluate-facility
    - services/diagnosis_service.py DiagnosisService.evaluate
    - services/diagnosis_runtime_step1.py (factory_id present)
    """
    fid = (factory_id or "").strip()
    if not fid:
        raise ValueError("factory_id is required")

    statuses = list(applicability_statuses or APPLICABILITY_MATCH_STATUSES)

    app_rows = compiler_gw.fetch_facility_applicability_by_factory(sb, fid, statuses)

    task_result = (
        sb.table("task_candidate")
        .select(
            "id, task_type, source_action_family, obligation_family, "
            "applicability_status, status"
        )
        .eq("factory_id", fid)
        .execute()
    )

    sched_result = (
        sb.table("schedule_candidate")
        .select(
            "id, schedule_type, source_family, source_relation_type, task_type, status"
        )
        .eq("factory_id", fid)
        .execute()
    )

    penalty_result = (
        sb.table("penalty_obligation_relation")
        .select(
            "id, penalty_candidate_id, rule_candidate_id, "
            "obligation_family, via_reference, status"
        )
        .limit(200)
        .execute()
    )

    review_result = (
        sb.table("compliance_review_queue")
        .select("id, issue_type, detail, status")
        .eq("factory_id", fid)
        .execute()
    )

    pkg_result = (
        sb.table("compliance_package").select("*").eq("factory_id", fid).execute()
    )

    penalties = penalty_result.data or []
    return {
        "factory_id": fid,
        "compiler_version": COMPILER_VERSION,
        "warning": COMPILER_WARNING,
        "applicability_candidates": app_rows,
        "task_candidates": task_result.data or [],
        "schedule_candidates": sched_result.data or [],
        "penalty_relations": penalties[:penalty_limit],
        "penalty_candidates": penalties[:penalty_limit],
        "review_queue": review_result.data or [],
        "residuals": review_result.data or [],
        "compliance_package": pkg_result.data[0] if pkg_result.data else None,
    }
