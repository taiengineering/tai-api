"""Phase 10 — read-only diagnostic: locate the real obligation population.

No writes. Probes candidate source tables + the latest diagnosis result_data
shape so we can ground the batch on ACTUAL data (the diagnosis-based source
returned 0 obligations in this environment).

    PYTHONPATH=. python scripts/inspect_obligation_sources.py
"""
import json

from db.supabase_client import get_supabase

# Candidate tables that might hold the obligation catalogue.
CANDIDATE_TABLES = [
    "factory_diagnosis_results",
    "master_rules",
    "evidence_candidate",
    "obligation_candidate",
    "obligations",
    "obligation",
    "legal_obligations",
    "refined_obligation",
    "obligation_refined",
    "work_schedules",
]


def probe_table(sb, table):
    try:
        res = sb.table(table).select("*", count="exact").limit(1).execute()
        sample_keys = sorted(res.data[0].keys()) if res.data else []
        return {"table": table, "exists": True, "count": res.count, "sample_keys": sample_keys}
    except Exception as e:  # noqa: BLE001
        return {"table": table, "exists": False, "error": str(e)[:160]}


def inspect_diagnosis(sb):
    try:
        res = (
            sb.table("factory_diagnosis_results")
            .select("id, factory_id, is_latest, result_data")
            .eq("is_latest", True)
            .limit(5)
            .execute()
        )
        out = []
        for row in (res.data or []):
            rd = row.get("result_data") or {}
            insp = rd.get("inspection_required")
            out.append({
                "id": row.get("id"),
                "factory_id": row.get("factory_id"),
                "result_data_keys": sorted(rd.keys()) if isinstance(rd, dict) else str(type(rd)),
                "inspection_required_len": len(insp) if isinstance(insp, list) else None,
                "inspection_required_sample": (insp[0] if isinstance(insp, list) and insp else None),
            })
        return out
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:200]}


def main():
    sb = get_supabase()
    report = {
        "candidate_tables": [probe_table(sb, t) for t in CANDIDATE_TABLES],
        "latest_diagnosis": inspect_diagnosis(sb),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
