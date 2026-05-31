"""
Full Refinement Integrity Audit
3395 Candidate → 3395 Obligation 전수 무결성 검증
예외 허용 0 / 손실 허용 0 / 관계 깨짐 허용 0
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.legal_v510_svc import run_diagnose_step1_v510
from services.obligation_standard_builder import build_obligations
from services.obligation_refinement import refine
from supabase import create_client

sb = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_ROLE_KEY'])
body = type('B',(),{
    'sector':'BUILDING','worker_count':10,'floor_area':500,'employee_count':10,
    'total_floor_area':500,'electric_capacity':0,'floor_count':1,
    'factory_id':None,'building_use_type':None,'construction_work_type':None,
    'contract_amount_eok':None,'ksic_major':None,'facility_type':None,'input':{}
})()

t0 = time.time()
result = run_diagnose_step1_v510(sb, body, ['BUILDING'], 'v5.10')
candidates = result['data'].get('candidates', [])
obligations = build_obligations(candidates)
refined = refine(obligations)
elapsed = time.time() - t0

obs   = refined['obligations']
groups = refined['groups']
idx   = refined['index']

PASS = True
findings = []

def fail(code, msg, count=None):
    global PASS
    PASS = False
    entry = f'[FAIL] {code}: {msg}'
    if count: entry += f' ({count}건)'
    findings.append(entry)

def ok(code, msg):
    findings.append(f'[PASS] {code}: {msg}')

print('=' * 60)
print('FULL REFINEMENT INTEGRITY AUDIT')
print(f'처리시간: {elapsed:.1f}s')
print('=' * 60)

# ── CHECK 1: 3395 → 3395 손실 없음 ────────────────────
n_cands = len(candidates)
n_obs   = len(obs)
if n_obs != n_cands:
    fail('C01_COUNT', f'손실 발생: {n_cands} → {n_obs}', n_cands - n_obs)
else:
    ok('C01_COUNT', f'{n_obs}건 전수 변환 완료')

# ── CHECK 2: orphan (group에 미포함 obligation) ─────────
grouped_ids = set()
for g in groups:
    for oid in g['obligation_ids']:
        grouped_ids.add(oid)
orphans = [o for o in obs if o.get('obligation_id','') not in grouped_ids]
if orphans:
    fail('C02_ORPHAN', 'Group에 미포함 Obligation 존재', len(orphans))
else:
    ok('C02_ORPHAN', f'모든 Obligation이 Group에 포함됨')

# ── CHECK 3: evidence 없는 obligation ──────────────────
missing_ev = [o for o in obs if not (o.get('evidence') or {}).get('chain')]
if missing_ev:
    fail('C03_EVIDENCE', 'evidence.chain 없는 Obligation', len(missing_ev))
else:
    ok('C03_EVIDENCE', f'3395건 전체 evidence 존재')

# ── CHECK 4: law_name 없음 ─────────────────────────────
no_law = [o for o in obs if not (o.get('law_name') or '').strip()]
if no_law:
    fail('C04_LAW_NAME', 'law_name 없는 Obligation', len(no_law))
else:
    ok('C04_LAW_NAME', 'law_name 100% 존재')

# ── CHECK 5: article_no 없음 ───────────────────────────
no_art = [o for o in obs if not (o.get('article_no') or '').strip()]
if no_art:
    fail('C05_ARTICLE_NO', 'article_no 없는 Obligation', len(no_art))
else:
    ok('C05_ARTICLE_NO', 'article_no 100% 존재')

# ── CHECK 6: broken parent_reference ──────────────────
broken_parent = []
for o in obs:
    pr = (o.get('parent_reference') or '').strip()
    if pr and pr not in idx:
        broken_parent.append(o.get('obligation_id',''))
if broken_parent:
    fail('C06_PARENT_LINK', 'parent_reference가 존재하지 않는 Obligation', len(broken_parent))
else:
    ok('C06_PARENT_LINK', 'broken parent_reference 없음')

# ── CHECK 7: duplicate obligation_id ──────────────────
id_counts = {}
for o in obs:
    oid = o.get('obligation_id','')
    id_counts[oid] = id_counts.get(oid, 0) + 1
dups = {k: v for k, v in id_counts.items() if v > 1}
if dups:
    fail('C07_DUPLICATE_ID', 'obligation_id 중복', len(dups))
else:
    ok('C07_DUPLICATE_ID', '중복 obligation_id 없음')

# ── CHECK 8: broken evidence_chain ────────────────────
broken_ev = []
for o in obs:
    chain = (o.get('evidence') or {}).get('chain') or []
    for ev in chain:
        if not ev.get('rule_id'):
            broken_ev.append(o.get('obligation_id',''))
            break
if broken_ev:
    fail('C08_BROKEN_EVIDENCE', 'rule_id 없는 evidence_chain', len(broken_ev))
else:
    ok('C08_BROKEN_EVIDENCE', 'evidence_chain 무결')

# ── CHECK 9: cross-law contamination ──────────────────
cross_law = []
for g in groups:
    g_law = g['law_name']
    for oid in g['obligation_ids']:
        o = idx.get(oid)
        if o and (o.get('law_name') or '') != g_law:
            cross_law.append(oid)
if cross_law:
    fail('C09_CROSS_LAW', 'Group내 law_name 불일치', len(cross_law))
else:
    ok('C09_CROSS_LAW', 'law_name 오염 없음')

# ── CHECK 10: cross-article contamination ─────────────
cross_art = []
for g in groups:
    g_art = g['article_no']
    for oid in g['obligation_ids']:
        o = idx.get(oid)
        if o and (o.get('article_no') or '') != g_art:
            cross_art.append(oid)
if cross_art:
    fail('C10_CROSS_ART', 'Group내 article_no 불일치', len(cross_art))
else:
    ok('C10_CROSS_ART', 'article_no 오염 없음')

# ── 결과 출력 ─────────────────────────────────────────
print()
for f in findings:
    print(f)

print()
print('=' * 60)
n_pass = sum(1 for f in findings if f.startswith('[PASS]'))
n_fail = sum(1 for f in findings if f.startswith('[FAIL]'))
print(f'PASS: {n_pass}/10  FAIL: {n_fail}/10')
print('=' * 60)
print('AUDIT RESULT:', 'PASS' if PASS else 'FAIL')
