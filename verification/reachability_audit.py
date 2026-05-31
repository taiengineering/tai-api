"""
verification/reachability_audit.py
2002 Rule 전수 역검증. Supabase 1000 row limit 회피 위해 pagination 사용.
"""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.legal_rules import _evaluate_conditions
from verification.reverse_input_generator import generate_input

def _fetch_all(supabase):
    rows, offset = [], 0
    while True:
        chunk = (supabase.table("master_building_legal_rules_legacy_contaminated")
            .select("*").eq("is_active", True)
            .range(offset, offset + 999).execute().data or [])
        rows.extend(chunk)
        if len(chunk) < 1000:
            break
        offset += 1000
    return rows

def run_reachability_audit(supabase) -> dict:
    rules = _fetch_all(supabase)
    total = len(rules)
    reachable, unreachable, no_condition, data_error = [], [], [], []

    for rule in rules:
        rid = rule.get("rule_id", "")
        gen = generate_input(rule)
        inp = gen["input_payload"]
        reason = gen.get("reason", "")

        if not gen["generated"]:
            no_condition.append({"rule_id": rid, "reason": reason,
                "law": rule.get("law_name", ""), "article": rule.get("law_article", "")})
            continue

        try:
            applicable, _ = _evaluate_conditions(inp, [rule])
            if applicable:
                reachable.append(rid)
            else:
                unreachable.append({
                    "rule_id": rid, "law": rule.get("law_name", ""),
                    "article": rule.get("law_article", ""),
                    "condition_code": rule.get("condition_code", ""),
                    "condition_value": str(rule.get("condition_value", "")),
                    "operator": rule.get("condition_operator_code", ""),
                })
        except Exception as e:
            data_error.append({"rule_id": rid, "error": str(e)})

    reachable_count = len(reachable) + len(no_condition)
    return {
        "total": total,
        "reachable": reachable_count,
        "truly_reachable": len(reachable),
        "no_condition_pass": len(no_condition),
        "unreachable": len(unreachable),
        "data_error": len(data_error),
        "reachability_pct": round(reachable_count / total * 100, 1) if total else 0,
        "unreachable_list": unreachable[:20],
    }
