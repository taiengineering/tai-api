"""Phase 10 — Obligation population batch helpers (service layer, no new engine).

Pure functions to (1) collect the distinct obligation population from latest
factory diagnosis results, and (2) evaluate the whole population with the
VERIFIED Phase 9 evaluator. Where an obligation has no Check EvidenceReport yet,
a well-formed EMPTY report is used — which the evaluator correctly maps to
TRACE_REQUIRED (근거 미관측 / 추적 필요), NOT a fabricated result.

IO (Supabase reads/writes) lives in scripts/run_quality_batch.py, not here.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from services.obligation_quality_evaluator import evaluate_quality


def empty_check_report(obligation_id: Optional[str] = None) -> Dict[str, Any]:
    """A well-formed Check report with nothing observed yet.

    Truthfully represents "no evidence/claim/chain observed" -> evaluator returns
    TRACE_REQUIRED. This is NOT a fake PASS; it encodes the real fact that the
    obligation has not been Check-evaluated.
    """
    return {
        "report_id": None,
        "status_summary": {"claim": {}, "evidence": {}, "chain": {}},
        "observation_records": [],
    }


def collect_obligations_from_diagnosis(
    diagnosis_rows: List[dict],
) -> Tuple[List[dict], Set[str]]:
    """Collect distinct obligations (by obligation_id) from latest diagnosis rows.

    Source = factory_diagnosis_results.result_data.inspection_required[] — the same
    rules the schedule gate consults (rule_id/rule_code = obligation_id).
    Returns (obligations, conflict_ids). conflict_ids = same obligation_id whose
    law linkage disagrees across rows (a real data anomaly -> CORRECTION).
    """
    by_id: Dict[str, dict] = {}
    conflicts: Set[str] = set()

    for row in diagnosis_rows:
        result_data = (row or {}).get("result_data") or {}
        for rule in (result_data.get("inspection_required") or []):
            oid = (rule.get("rule_id") or rule.get("rule_code") or "").strip()
            if not oid:
                continue
            ob = {
                "obligation_id": oid,
                "law_name": rule.get("law_name") or "",
                "law_article": rule.get("law_article") or "",
                "obligation_type": rule.get("obligation_type") or "",
                "obligation_summary": rule.get("obligation_summary") or rule.get("description") or "",
            }
            if oid in by_id:
                prev = by_id[oid]
                if (prev.get("law_name") or "") != (ob.get("law_name") or "") or (
                    prev.get("law_article") or ""
                ) != (ob.get("law_article") or ""):
                    conflicts.add(oid)
            else:
                by_id[oid] = ob

    return list(by_id.values()), conflicts


def evaluate_population(
    obligations: List[dict],
    conflicts: Optional[Set[str]] = None,
    reports_by_id: Optional[Dict[str, dict]] = None,
) -> List[Dict[str, Any]]:
    """Evaluate every obligation. Uses a real Check report if provided in
    reports_by_id, else an empty (not-yet-evaluated) report.
    """
    conflicts = conflicts or set()
    reports_by_id = reports_by_id or {}
    out: List[Dict[str, Any]] = []
    for ob in obligations:
        oid = ob.get("obligation_id")
        report = reports_by_id.get(oid) or empty_check_report(oid)
        is_conflict = oid in conflicts
        res = evaluate_quality(ob, report, duplicate=is_conflict)
        out.append({
            "obligation_id": oid,
            "quality_status": res["quality_status"],
            "quality_reason": res["quality_reason"],
            "check_report_id": report.get("report_id"),
        })
    return out
