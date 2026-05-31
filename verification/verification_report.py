"""verification/verification_report.py — JSON 결과 → 요약 출력."""
import json, sys
data = json.load(open("verification/VERIFICATION_RESULT.json"))
r, m, c = data["reachability"], data["mutation"], data["consistency"]
print(f"Reachability: {r['reachable']}/{r['total']} ({r['reachability_pct']}%)")
print(f"Mutation PASS: {m['passed']}/{m['total_boundary_rules']} ({m['pass_rate']}%)")
print(f"DataConflict: {c['conflict_count']} ({c['conflict_rate']}%)")
