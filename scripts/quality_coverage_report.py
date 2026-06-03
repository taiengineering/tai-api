"""Phase 10 — read obligation_quality + admin_obligation_queue from the DB and
print the coverage report. Mirrors what GET /admin/obligations/coverage returns,
but runnable before the router is deployed.

RLS-protected tables -> needs service_role key. Run with Railway env injected:
    railway run sh -c 'PYTHONPATH=. python scripts/quality_coverage_report.py'
"""
import json
from collections import Counter

from db.supabase_client import get_supabase
from services.obligation_quality_coverage import compute_coverage


def main():
    sb = get_supabase()
    oq = sb.table("obligation_quality").select("obligation_id, quality_status, quality_reason").execute()
    rows = oq.data or []

    queue = sb.table("admin_obligation_queue").select("status").execute()
    queue_by_status = Counter((r.get("status") or "<none>") for r in (queue.data or []))

    print(json.dumps({
        "obligation_quality_rows": len(rows),
        "coverage": compute_coverage(rows),
        "admin_obligation_queue_total": len(queue.data or []),
        "admin_obligation_queue_by_status": dict(queue_by_status),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
