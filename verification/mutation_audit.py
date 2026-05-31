"""
verification/mutation_audit.py
경계값 변이 테스트. 49/50/51 등으로 통과/미통과 검증.
"""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.legal_rules import _evaluate_conditions

BOUNDARY_OPS = {">=", ">", "<=", "<"}
ALIAS = {"building_area": "floor_area", "electrical_capacity_kw": "electric_capacity",
         "contract_amount": "contract_amount_eok"}

def _fetch_all(supabase):
    rows, offset = [], 0
    while True:
        chunk = (supabase.table("master_building_legal_rules_legacy_contaminated")
            .select("rule_id,law_name,law_article,condition_code,condition_value,condition_operator_code,sector")
            .eq("is_active", True).range(offset, offset + 999).execute().data or [])
        rows.extend(chunk)
        if len(chunk) < 1000:
            break
        offset += 1000
    return rows

def _make_inputs(code, val, alias):
    field = alias.get(code, code)
    base = {"sector": "BUILDING", "employee_count": 10, "building_area": 500,
            "floor_area": 500, "is_factory_registered": 1}
    below = dict(base); below[field] = max(0, val - 1)
    exact = dict(base); exact[field] = val
    above = dict(base); above[field] = val + 1
    return below, exact, above

def run_mutation_audit(supabase) -> dict:
    rules = _fetch_all(supabase)
    total, passed, failed, skipped = 0, [], [], []

    for rule in rules:
        cop = (rule.get("condition_operator_code") or "").strip()
        if cop not in BOUNDARY_OPS:
            continue
        cval = rule.get("condition_value")
        ccode = (rule.get("condition_code") or "").strip()
        if not ccode or cval is None:
            continue
        try:
            boundary = float(str(cval))
        except:
            continue

        total += 1
        below, exact, above = _make_inputs(ccode, boundary, ALIAS)

        try:
            r_below, _ = _evaluate_conditions(below, [rule])
            r_exact, _ = _evaluate_conditions(exact, [rule])
            r_above, _ = _evaluate_conditions(above, [rule])

            if cop == ">=":
                ok = (not r_below) and bool(r_exact) and bool(r_above)
            elif cop == ">":
                ok = (not r_below) and (not r_exact) and bool(r_above)
            elif cop == "<=":
                ok = bool(r_below) and bool(r_exact) and (not r_above)
            elif cop == "<":
                ok = bool(r_below) and (not r_exact) and (not r_above)
            else:
                ok = True

            entry = {"rule_id": rule.get("rule_id",""), "law": rule.get("law_name",""),
                "code": ccode, "op": cop, "boundary": boundary,
                "below": bool(r_below), "exact": bool(r_exact), "above": bool(r_above)}
            if ok:
                passed.append(entry)
            else:
                failed.append(entry)
        except Exception as e:
            skipped.append({"rule_id": rule.get("rule_id",""), "error": str(e)})

    return {
        "total_boundary_rules": total,
        "passed": len(passed),
        "failed": len(failed),
        "skipped": len(skipped),
        "pass_rate": round(len(passed) / total * 100, 1) if total else 0,
        "failed_list": failed,
    }
