"""Phase 10 — batch-evaluate all existing obligations into obligation_quality.

Run from repo root:
    # preview only (no DB writes):
    PYTHONPATH=. python scripts/run_quality_batch.py --dry-run
    # persist + auto-load admin queue on CORRECTION_REQUIRED:
    PYTHONPATH=. python scripts/run_quality_batch.py --commit

Reads factory_diagnosis_results(is_latest) -> inspection_required rules,
evaluates the population with the VERIFIED evaluator, prints coverage JSON.
Obligations without a Check report -> TRACE_REQUIRED (real, not fabricated).
"""
import argparse
import json

from db.supabase_client import get_supabase
from services.obligation_quality_batch import (
    collect_obligations_from_diagnosis,
    evaluate_population,
)
from services.obligation_quality_coverage import compute_coverage
from services.obligation_quality_store import record_evaluation


def load_diagnosis_rows(sb):
    res = (
        sb.table("factory_diagnosis_results")
        .select("result_data")
        .eq("is_latest", True)
        .execute()
    )
    return res.data or []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true", help="persist to obligation_quality + admin queue")
    ap.add_argument("--dry-run", action="store_true", help="evaluate + print only, no writes")
    args = ap.parse_args()
    commit = args.commit and not args.dry_run

    sb = get_supabase()
    rows = load_diagnosis_rows(sb)
    obligations, conflicts = collect_obligations_from_diagnosis(rows)
    results = evaluate_population(obligations, conflicts)
    coverage = compute_coverage(results)

    persisted = 0
    if commit:
        for r in results:
            record_evaluation(
                r["obligation_id"], r["quality_status"], r.get("quality_reason"), r.get("check_report_id")
            )
            persisted += 1

    print(json.dumps({
        "mode": "commit" if commit else "dry-run",
        "diagnosis_rows": len(rows),
        "obligation_count": len(obligations),
        "conflicts": len(conflicts),
        "coverage": coverage,
        "persisted": persisted,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
