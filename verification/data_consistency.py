"""
verification/data_consistency.py — obligation_type vs *_required 불일치 전수.
"""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TYPE_FLAG_MAP = {
    "NOTIFY":  "notify_required",
    "REPORT":  "report_required",
    "ACTION":  "action_required",
    "APPOINT": "appointment_required",
    "INSPECT": "inspection_required",
}

def run_consistency_audit(supabase) -> dict:
    rules = supabase.table("master_building_legal_rules_legacy_contaminated")        .select("rule_id,law_name,law_article,obligation_type,appointment_required,inspection_required,action_required,report_required,notify_required")        .eq("is_active", True).execute().data or []

    conflicts = []
    for r in rules:
        otype = (r.get("obligation_type") or "").strip().upper()
        if otype not in TYPE_FLAG_MAP: continue
        flag_field = TYPE_FLAG_MAP[otype]
        # conflict: 선언된 type의 required flag가 false이고 다른 flag도 전부 false
        all_false = not any(r.get(f) for f in TYPE_FLAG_MAP.values())
        if all_false:
            conflicts.append({"rule_id": r.get("rule_id",""),
                "law": r.get("law_name",""), "article": r.get("law_article",""),
                "obligation_type": otype, "flag_should_be": flag_field})

    by_type = {}
    for c in conflicts:
        t = c["obligation_type"]
        by_type[t] = by_type.get(t, 0) + 1

    return {
        "total_rules": len(rules),
        "conflict_count": len(conflicts),
        "conflict_by_type": by_type,
        "conflict_rate": round(len(conflicts) / len(rules) * 100, 1) if rules else 0,
        "sample_conflicts": conflicts[:10],
    }
