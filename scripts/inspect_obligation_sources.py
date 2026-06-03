"""Phase 10 — read-only diagnostic v2: see the REAL obligation data.

No writes. Shows:
  - work_schedules breakdown: total, by source_type, how many have rule_code,
    distinct rule_code count, samples.
  - latest diagnosis result_data.rules / key_obligations shape + samples.
Goal: stop guessing filters — ground the batch source on actual rows.

    PYTHONPATH=. python scripts/inspect_obligation_sources.py
"""
import json
from collections import Counter

from db.supabase_client import get_supabase


def inspect_work_schedules(sb):
    try:
        res = (
            sb.table("work_schedules")
            .select("rule_code, source_type, status_code, law_name, law_article")
            .limit(2000)
            .execute()
        )
        rows = res.data or []
        by_source = Counter((r.get("source_type") or "<none>") for r in rows)
        with_rule = [r for r in rows if (r.get("rule_code") or "").strip()]
        rule_by_source = Counter((r.get("source_type") or "<none>") for r in with_rule)
        distinct_rule_codes = sorted({(r.get("rule_code") or "").strip() for r in with_rule})
        samples = [
            {k: r.get(k) for k in ("rule_code", "source_type", "status_code", "law_name", "law_article")}
            for r in rows[:8]
        ]
        return {
            "total": len(rows),
            "by_source_type": dict(by_source),
            "rows_with_rule_code": len(with_rule),
            "rule_code_by_source_type": dict(rule_by_source),
            "distinct_rule_code_count": len(distinct_rule_codes),
            "distinct_rule_code_sample": distinct_rule_codes[:10],
            "row_samples": samples,
        }
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:200]}


def inspect_diagnosis_rules(sb):
    try:
        res = (
            sb.table("factory_diagnosis_results")
            .select("id, factory_id, rule_count, result_data")
            .eq("is_latest", True)
            .limit(5)
            .execute()
        )
        out = []
        for row in (res.data or []):
            rd = row.get("result_data") or {}
            rules = rd.get("rules") if isinstance(rd, dict) else None
            keyobs = rd.get("key_obligations") if isinstance(rd, dict) else None
            out.append({
                "id": row.get("id"),
                "rule_count_col": row.get("rule_count"),
                "rules_len": len(rules) if isinstance(rules, list) else None,
                "rules_sample": (rules[0] if isinstance(rules, list) and rules else None),
                "key_obligations_len": len(keyobs) if isinstance(keyobs, list) else None,
                "key_obligations_sample": (keyobs[0] if isinstance(keyobs, list) and keyobs else None),
            })
        return out
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:200]}


def main():
    sb = get_supabase()
    report = {
        "work_schedules": inspect_work_schedules(sb),
        "latest_diagnosis_rules": inspect_diagnosis_rules(sb),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
