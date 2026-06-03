"""Phase 10 — batch-evaluate all existing obligations into obligation_quality.

Real obligation source (confirmed by live DB probe):
  factory_diagnosis_results(is_latest).result_data.rules  — obligation_id = rule_code.
  (work_schedules has no rule_code/law linkage — not an obligation catalogue.)

Run from repo root:
    # preview only (no DB writes), default source = diagnosis:
    PYTHONPATH=. python scripts/run_quality_batch.py --dry-run
    # persist + auto-load admin queue on CORRECTION_REQUIRED (needs service_role key):
    SUPABASE_SERVICE_KEY=... PYTHONPATH=. python scripts/run_quality_batch.py --commit
    # alternate source:
    PYTHONPATH=. python scripts/run_quality_batch.py --source work_schedules --dry-run

Obligations without a Check report -> TRACE_REQUIRED (real, not fabricated).

NOTE: --commit writes to obligation_quality / admin_obligation_queue which have RLS
enabled. The Supabase client must use the service_role key (SUPABASE_SERVICE_KEY),
which bypasses RLS. The anon key (SUPABASE_KEY) can read for --dry-run but cannot
write. This guard fails fast with a clear message instead of an RLS traceback.
"""
import argparse
import json
import os

from db.supabase_client import get_supabase
from services.obligation_quality_batch import (
    collect_obligations_from_diagnosis,
    collect_obligations_from_work_schedules,
    evaluate_population,
)
from services.obligation_quality_coverage import compute_coverage
from services.obligation_quality_store import record_evaluation


def load_work_schedule_rows(sb):
    res = (
        sb.table("work_schedules")
        .select("rule_code, law_name, law_article, obligation_type, description, summary, source_type")
        .execute()
    )
    return res.data or []


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
    ap.add_argument("--source", choices=["diagnosis", "work_schedules"], default="diagnosis")
    ap.add_argument("--commit", action="store_true", help="persist to obligation_quality + admin queue")
    ap.add_argument("--dry-run", action="store_true", help="evaluate + print only, no writes")
    args = ap.parse_args()
    commit = args.commit and not args.dry_run

    if commit and not os.environ.get("SUPABASE_SERVICE_KEY"):
        print(json.dumps({
            "error": "SUPABASE_SERVICE_KEY_NOT_SET",
            "message": "--commit writes to RLS-protected tables and requires the service_role key. "
                       "Set SUPABASE_SERVICE_KEY (Supabase dashboard > Project Settings > API > service_role) "
                       "then retry. --dry-run works with the anon key.",
        }, ensure_ascii=False, indent=2))
        raise SystemExit(1)

    sb = get_supabase()
    if args.source == "work_schedules":
        rows = load_work_schedule_rows(sb)
        obligations, conflicts = collect_obligations_from_work_schedules(rows)
    else:
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
        "source": args.source,
        "mode": "commit" if commit else "dry-run",
        "source_rows": len(rows),
        "obligation_count": len(obligations),
        "conflicts": len(conflicts),
        "coverage": coverage,
        "persisted": persisted,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
