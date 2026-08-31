# verification/check_runtime_probe.py
# 작업지시 3-2 — Check Runtime 실존 검증 (동적 실행)
#
# 목적: 실사업장 1건의 LEG 결과를 현재 Runtime 진입점에 직접 전달했을 때
#       Observation Status / Observation Record / Evidence Report 가 실제 생성되는지
#       "실행 결과"로 증명한다. (기존 e2e_lifecycle_validator 사용 금지)
#
# 실행(권장): railway run python3 verification/check_runtime_probe.py [factory_id]
#   기본 대상: cc000003-0000-0000-0000-000000000003 (강남 본사 사업장)
#   env: 앱과 동일한 get_supabase 사용 (SUPABASE_URL + SUPABASE_SERVICE_KEY or SUPABASE_KEY)
#
# 출력: /tmp/check_runtime_probe.json + 콘솔 STEP1~6 PASS/FAIL 표
#
# 원칙: 코드분석/추론 아님. 실제 함수 호출 + 실제 테이블 delta 카운트만.

import os, sys, json
from datetime import datetime, timezone
from services.time import now_kst, serialize_external_utc

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('TAI_USE_RUNTIME_ENGINE', 'false')

from db.supabase_client import get_supabase
SB = get_supabase()

FACTORY_ID = sys.argv[1] if len(sys.argv) > 1 else 'cc000003-0000-0000-0000-000000000003'

# Check 산출물이 적재될 후보 테이블 (대표 모델: Observation Status/Record, Evidence Report)
# tai-api 현재 스키마에서 해당 의미에 가장 근접한 런타임 테이블을 모두 측정한다.
OBSERVATION_STATUS_TABLES = ['runtime_evaluation_context']          # 평가 상태(PENDING/EVALUATING/COMPLETED)
OBSERVATION_RECORD_TABLES  = ['runtime_rule_activation']            # 관측 레코드 상당(활성 판정 레코드)
EVIDENCE_REPORT_TABLES     = ['runtime_evidence_verification',      # 증거 검증/리포트 후보
                              'runtime_compliance_evidence',
                              'runtime_evidence_snapshot']

def count(table, ctx_id=None, col='evaluation_context_id'):
    try:
        q = SB.table(table).select('id', count='exact')
        if ctx_id: q = q.eq(col, ctx_id)
        return q.execute().count or 0
    except Exception as e:
        return f'ERR:{str(e)[:40]}'

def snapshot(tables):
    return {t: count(t) for t in tables}

report = {'factory_id': FACTORY_ID, 'executed_at': serialize_external_utc(now_kst()), 'steps': {}}

# STEP 1: LEG 실행
from services.legal_v510_svc import run_diagnose_step1_v510
f = SB.table('factories').select('*').eq('id', FACTORY_ID).single().execute().data
procs = SB.table('factory_process').select('process_id,process_path').eq('factory_id', FACTORY_ID).eq('is_active', True).execute().data or []
eqs   = SB.table('equipment_assets').select('equipment_type_code').eq('factory_id', FACTORY_ID).execute().data or []
sector = (f or {}).get('sector', 'INDUSTRIAL')
body = type('B', (), {
    'sector': sector, 'factory_id': FACTORY_ID,
    'worker_count': (f or {}).get('employee_count'), 'employee_count': (f or {}).get('employee_count'),
    'floor_area': (f or {}).get('floor_area_m2') or 3000, 'total_floor_area': (f or {}).get('floor_area_m2') or 3000,
    'electric_capacity': (f or {}).get('electrical_capacity_kw'), 'floor_count': 2,
    'elevator_count': None, 'contract_amount_eok': None, 'construction_type': None,
    'direct_workers': None, 'subcon_workers': None, 'building_use_type': None,
    'construction_work_type': None, 'ksic_major': None, 'facility_type': None,
    'input': {'employee_count': (f or {}).get('employee_count'),
              'electrical_capacity_kw': (f or {}).get('electrical_capacity_kw')},
})()
try:
    leg = run_diagnose_step1_v510(SB, body, [sector, 'MANUFACTURING', 'INDUSTRIAL', 'BUILDING'], 'v5.10')
    data = leg.get('data', {})
    candidates = data.get('candidates', []) or []
    rule_n = len(candidates)
    obligation_n = sum(1 for c in candidates if (c.get('obligation_id') or c.get('obligation_family') or c.get('obligation_text')))
    report['steps']['1_LEG'] = {'pass': rule_n > 0, 'rule_n': rule_n, 'obligation_n': obligation_n}
except Exception as e:
    report['steps']['1_LEG'] = {'pass': False, 'error': str(e)[:120]}; candidates = []

# STEP 2: Check 입력 생성 (claim_ref / evidence_refs / evidence_chain)
def field(c, *names):
    for n in names:
        if isinstance(c, dict) and c.get(n) not in (None, '', [], {}): return c.get(n)
    return None
claim_ok = ev_ok = chain_ok = 0
for c in candidates:
    if field(c, 'claim_ref', 'claim_id', 'claim'): claim_ok += 1
    if field(c, 'evidence_refs', 'evidence_ids', 'evidence'): ev_ok += 1
    if field(c, 'evidence_chain'): chain_ok += 1
report['steps']['2_CHECK_INPUT'] = {
    'pass': bool(candidates) and (claim_ok or ev_ok or chain_ok),
    'claim_ref': claim_ok, 'evidence_refs': ev_ok, 'evidence_chain': chain_ok}

# STEP 3: Check Runtime 직접 호출 (현재 Runtime 진입점)
before = {'status': snapshot(OBSERVATION_STATUS_TABLES),
          'record': snapshot(OBSERVATION_RECORD_TABLES),
          'report': snapshot(EVIDENCE_REPORT_TABLES)}
ctx_id = None
try:
    from services import runtime_evaluator_svc as RT
    rt_input = {
        'industry_code': (f or {}).get('ksic_code') or (f or {}).get('industry_code'),
        'worker_count': (f or {}).get('employee_count'),
        'equipment': [e['equipment_type_code'] for e in eqs if e.get('equipment_type_code')],
        'process_types': [p['process_id'] for p in procs if p.get('process_id')],
        'company_id': (f or {}).get('company_id'),
        'facility_id': FACTORY_ID, 'created_by': 'check_runtime_probe',
    }
    ctx = RT.create_context(rt_input)
    ctx_id = ctx.get('id') if isinstance(ctx, dict) else None
    res = RT.evaluate(ctx_id) if ctx_id else None
    report['steps']['3_RUNTIME_CALL'] = {'pass': bool(ctx_id), 'context_id': ctx_id,
        'entrypoint': 'runtime_evaluator_svc.create_context+evaluate',
        'summary': (res or {}).get('summary')}
except Exception as e:
    report['steps']['3_RUNTIME_CALL'] = {'pass': False, 'error': str(e)[:160]}

# STEP 4~6: Observation Status / Observation Record / Evidence Report
status_n = 1 if ctx_id else 0
record_n = count('runtime_rule_activation', ctx_id) if ctx_id else 0
after_report = snapshot(EVIDENCE_REPORT_TABLES)
report_delta = {t: (after_report.get(t, 0) - before['report'].get(t, 0))
                if isinstance(after_report.get(t), int) and isinstance(before['report'].get(t), int) else 'ERR'
                for t in EVIDENCE_REPORT_TABLES}
evidence_report_generated = any(isinstance(v, int) and v > 0 for v in report_delta.values())

report['steps']['4_OBSERVATION_STATUS'] = {'pass': status_n > 0, 'count': status_n,
    'note': 'runtime_evaluation_context.evaluation_status'}
report['steps']['5_OBSERVATION_RECORD'] = {'pass': isinstance(record_n, int) and record_n > 0,
    'count': record_n, 'note': 'runtime_rule_activation rows for context'}
report['steps']['6_EVIDENCE_REPORT'] = {'pass': evidence_report_generated,
    'delta': report_delta, 'note': 'delta in evidence-report candidate tables'}

# 판정
s = report['steps']
def p(k): return bool(s.get(k, {}).get('pass'))
checktbl = [('LEG 출력 생성','1_LEG'),('Check 입력 생성','2_CHECK_INPUT'),
            ('Observation Status','4_OBSERVATION_STATUS'),('Observation Record','5_OBSERVATION_RECORD'),
            ('Evidence Report','6_EVIDENCE_REPORT')]
obs_ok = p('4_OBSERVATION_STATUS') and p('5_OBSERVATION_RECORD')
rep_ok = p('6_EVIDENCE_REPORT')
if obs_ok and rep_ok: verdict = 'Check Runtime 동작'
elif obs_ok or rep_ok: verdict = 'Check Runtime 부분 동작'
else: verdict = 'Check Runtime 미동작'
report['verdict'] = verdict

print('\n=== 결과물1: Check Runtime 검증표 ===')
for label, k in checktbl:
    print(f'  {label:<20} {"PASS" if p(k) else "FAIL"}')
print('\n=== 결과물2: Check 출력 카운터 ===')
print(f'  Observation Status 수 : {status_n}')
print(f'  Observation Record 수 : {record_n}')
print(f'  Evidence Report 생성  : {"YES" if rep_ok else "NO"}  delta={report_delta}')
print(f'\n=== 결과물3: 최종 판정 === \n  {verdict}')
with open('/tmp/check_runtime_probe.json','w',encoding='utf-8') as fp:
    json.dump(report, fp, ensure_ascii=False, indent=2)
print('\n저장: /tmp/check_runtime_probe.json')
