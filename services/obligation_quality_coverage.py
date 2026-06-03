"""Phase 10 — Quality Coverage (pure aggregation, no DB, no new engine).

Given obligation_quality rows -> distribution + top-10 reason causes.
"""
from __future__ import annotations

from typing import Any, Dict, List

from services.obligation_quality_evaluator import READY, TRACE_REQUIRED, CORRECTION_REQUIRED


def compute_coverage(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """rows: [{obligation_id, quality_status, quality_reason}, ...]"""
    total = len(rows)
    distribution = {READY: 0, TRACE_REQUIRED: 0, CORRECTION_REQUIRED: 0}
    reason_counts: Dict[str, int] = {}
    unclassified = 0

    for r in rows:
        status = r.get("quality_status")
        if status in distribution:
            distribution[status] += 1
        else:
            unclassified += 1
        reason = r.get("quality_reason")
        if reason:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

    top_reasons = [
        {"reason": k, "count": v}
        for k, v in sorted(reason_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
    ]
    classified = distribution[READY] + distribution[TRACE_REQUIRED] + distribution[CORRECTION_REQUIRED]

    return {
        "total": total,
        "distribution": distribution,
        "top_reasons": top_reasons,
        "unclassified": unclassified,
        "fully_classified": total > 0 and classified == total,
    }
