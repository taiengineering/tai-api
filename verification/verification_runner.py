"""
verification/verification_runner.py
python3 verification/verification_runner.py
"""
import os, sys, json, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from supabase import create_client
from verification.reachability_audit import run_reachability_audit
from verification.mutation_audit import run_mutation_audit
from verification.data_consistency import run_consistency_audit

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])

print("== 1/3 Reachability Audit ==")
t0 = time.time()
reach = run_reachability_audit(sb)
print(f"  total={reach['total']} reachable={reach['reachable']} unreachable={reach['unreachable']} {reach['reachability_pct']}% ({time.time()-t0:.1f}s)")

print("== 2/3 Mutation Audit ==")
t0 = time.time()
mut = run_mutation_audit(sb)
print(f"  boundary_rules={mut['total_boundary_rules']} passed={mut['passed']} failed={mut['failed']} {mut['pass_rate']}% ({time.time()-t0:.1f}s)")

print("== 3/3 Data Consistency Audit ==")
t0 = time.time()
con = run_consistency_audit(sb)
print(f"  conflicts={con['conflict_count']} ({con['conflict_rate']}%) {con['conflict_by_type']} ({time.time()-t0:.1f}s)")

result = {"reachability": reach, "mutation": mut, "consistency": con}
open("verification/VERIFICATION_RESULT.json","w").write(json.dumps(result, ensure_ascii=False, indent=2))

# PASS 판정
print()
r_pct = reach["reachability_pct"]
m_rate = mut["pass_rate"]
conflicts = con["conflict_count"]
if r_pct >= 99 and conflicts == 0 and mut["failed"] == 0:
    verdict = "PASS"
elif r_pct >= 95:
    verdict = "WARNING"
else:
    verdict = "BLOCK"
print(f"== VERDICT: {verdict} ==")
print(f"  Reachability: {r_pct}%  MutationPass: {m_rate}%  DataConflict: {conflicts}")
