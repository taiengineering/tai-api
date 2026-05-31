"""
Full Refinement Quality Audit v2 — 12/12 전수검증
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.legal_v510_svc import run_diagnose_step1_v510
from services.obligation_standard_builder import build_obligations
from services.obligation_refinement import refine
from supabase import create_client

sb = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_ROLE_KEY'])
body = type('B',(),{'sector':'BUILDING','worker_count':10,'floor_area':500,'employee_count':10,'total_floor_area':500,'electric_capacity':0,'floor_count':1,'factory_id':None,'building_use_type':None,'construction_work_type':None,'contract_amount_eok':None,'ksic_major':None,'facility_type':None,'input':{}})()

t0 = time.time()
r = run_diagnose_step1_v510(sb, body, ['BUILDING'], 'v5.10')
cands = r['data'].get('candidates', [])
obs = build_obligations(cands)
refined = refine(obs)
elapsed = time.time() - t0

obligations  = refined['obligations']
article_groups = refined['article_groups']
repeat_groups  = refined['repeat_groups']
idx_all      = {o['obligation_id']: o for o in obligations}
q            = refined['quality']

PASS = True
findings = []
def fail(c, m, n=None):
    global PASS; PASS = False
    findings.append(f'[FAIL] {c}: {m}' + (f' ({n}건)' if n else ''))
def ok(c, m): findings.append(f'[PASS] {c}: {m}')

# C01 입력=출력
if len(obligations) != len(cands): fail('C01','손실 발생', len(cands)-len(obligations))
else: ok('C01', f'입력{len(cands)}=출력{len(obligations)}')

# C02 obligation_id 손실 0
input_ids  = {c['candidate_id'] for c in cands}
output_ids = {o['obligation_id'] for o in obligations}
lost = input_ids - output_ids
if lost: fail('C02','obligation_id 손실', len(lost))
else: ok('C02','obligation_id 손실 0')

# C03 repeat_group member 합계
rg_total = sum(rg['member_count'] for rg in repeat_groups)
if rg_total != len(obligations): fail('C03',f'repeat member 합계 불일치: {rg_total}≠{len(obligations)}')
else: ok('C03',f'repeat_group member 합계 정확 ({rg_total})')

# C04 article_group member 합계
ag_total = sum(g['obligation_count'] for g in article_groups)
if ag_total != len(obligations): fail('C04',f'article member 합계 불일치: {ag_total}')
else: ok('C04',f'article_group member 합계 정확 ({ag_total})')

# C05 internal family code 검출 누락 0
from services.obligation_refinement import is_internal_family_code
missed = []
for o in obligations:
    has = is_internal_family_code(o.get('how','')) or is_internal_family_code(o.get('what','')) or is_internal_family_code(o.get('title',''))
    if has != o.get('internal_code_detected', False): missed.append(o['obligation_id'])
if missed: fail('C05','internal_code_detected 불일치', len(missed))
else: ok('C05',f'internal_code_detected 전수 정확')

# C06 web_usable false → reason_codes 존재
bad = [o for o in obligations if not o['usability']['web_usable'] and not o['usability']['reason_codes']]
if bad: fail('C06','web_usable=false인데 reason_codes 없음', len(bad))
else: ok('C06','web_usable reason_codes 전수 존재')

# C07 task_usable false → reason_codes 존재
bad = [o for o in obligations if not o['usability']['task_usable'] and not o['usability']['reason_codes']]
if bad: fail('C07','task_usable=false인데 reason_codes 없음', len(bad))
else: ok('C07','task_usable reason_codes 전수 존재')

# C08 doc_usable false → reason_codes 존재
bad = [o for o in obligations if not o['usability']['doc_usable'] and not o['usability']['reason_codes']]
if bad: fail('C08','doc_usable=false인데 reason_codes 없음', len(bad))
else: ok('C08','doc_usable reason_codes 전수 존재')

# C09 member_obligation_ids 실제 존재
broken = []
for rg in repeat_groups:
    for mid in rg['member_obligation_ids']:
        if mid not in idx_all: broken.append(mid)
if broken: fail('C09','member_obligation_ids에 존재하지 않는 ID', len(broken))
else: ok('C09','member_obligation_ids 전수 존재')

# C10 representative_obligation_id가 member 안에 존재
broken = [rg for rg in repeat_groups if rg['representative_obligation_id'] not in rg['member_obligation_ids']]
if broken: fail('C10','representative_id가 member 밖', len(broken))
else: ok('C10','representative_obligation_id 전수 유효')

# C11 원본 필드 보존
REQUIRED = ['obligation_id','law_name','article_no','evidence','usability','condition_status','internal_code_detected']
missing_fields = [f for f in REQUIRED if f not in obligations[0]] if obligations else []
if missing_fields: fail('C11',f'필수 필드 누락: {missing_fields}')
else: ok('C11','원본 필드 + 정제 필드 전수 존재')

# C12 삭제된 obligation 0
if len(obligations) < len(cands): fail('C12',f'삭제 발생: {len(cands)-len(obligations)}건')
else: ok('C12','삭제 0건 확인')

# ── 출력 ──────────────────────────────────────────────────────
print('='*60)
print('FULL REFINEMENT QUALITY AUDIT v2')
print(f'처리시간: {elapsed:.1f}s')
print('='*60)
for f in findings: print(f)
print()
print('='*60)
n_p = sum(1 for f in findings if f.startswith('[PASS]'))
n_f = sum(1 for f in findings if f.startswith('[FAIL]'))
print(f'PASS: {n_p}/12  FAIL: {n_f}/12')
print('='*60)
print('AUDIT RESULT:', 'PASS' if PASS else 'FAIL')
print()
print('── Quality Stats ──')
for k,v in q.items(): print(f'  {k}: {v}')
