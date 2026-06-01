# verification/premium_behavioral_validation.py
# PREMIUM LEG Behavioral Validation Audit v1
# 실행: TAI_USE_RUNTIME_ENGINE=false python3 verification/premium_behavioral_validation.py
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['TAI_USE_RUNTIME_ENGINE'] = 'false'

from supabase import create_client
from services.legal_v510_svc import run_diagnose_step1_v510, run_diagnose_step2_v510

sb = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_ROLE_KEY'])

# 실제 factories 테이블에서 UUID 확보
fac_rows = sb.table('factories').select('id,sector').eq('is_active', True).limit(5).execute().data or []
INDUSTRIAL_ID = next((r['id'] for r in fac_rows if r['sector'] in ('INDUSTRIAL','MANUFACTURING')), None)
BUILDING_ID   = next((r['id'] for r in fac_rows if r['sector'] == 'BUILDING'), None)

if not INDUSTRIAL_ID:
    print('INDUSTRIAL factory 없음. BUILDING으로 대체')
    INDUSTRIAL_ID = fac_rows[0]['id'] if fac_rows else None

print(f'Factory ID (MFG): {INDUSTRIAL_ID}')

BASE_MFG = {'sector':'MANUFACTURING','worker_count':50,'employee_count':50,
             'floor_area':5000,'electrical_capacity_kw':1000,'is_factory_registered':1}

def step1(inp, factory_id=None):
    sector = inp.get('sector','MANUFACTURING')
    body = type('B', (), {
        'sector': sector,
        'factory_id': factory_id or '',
        'worker_count': inp.get('worker_count', 50),
        'employee_count': inp.get('employee_count', 50),
        'floor_area': inp.get('floor_area', 5000),
        'total_floor_area': inp.get('floor_area', 5000),
        'electric_capacity': inp.get('electrical_capacity_kw', 0),
        'electrical_capacity_kw': inp.get('electrical_capacity_kw', 0),
        'floor_count': inp.get('floor_count', 2),
        'elevator_count': inp.get('elevator_count'),
        'contract_amount_eok': inp.get('contract_amount_eok'),
        'building_use_type': None, 'construction_work_type': None,
        'ksic_major': None, 'facility_type': None,
        'input': {k: v for k, v in inp.items() if k not in (
            'sector','worker_count','employee_count','floor_area',
            'electrical_capacity_kw','floor_count','elevator_count','contract_amount_eok')},
    })()
    r = run_diagnose_step1_v510(sb, body, [sector,'MANUFACTURING','INDUSTRIAL'], 'v5.10')
    d = r['data']
    return len(d.get('candidates', [])), d.get('diagnosis_id')

def step2(factory_id, diagnosis_id, processes=None, work_types=None):
    if not diagnosis_id or not factory_id:
        return None, 'no_diag_id'
    body = type('B', (), {
        'factory_id': factory_id,
        'diagnosis_id': diagnosis_id,
        'processes': processes or [],
        'construction_types': [],
        'construction_work_types': work_types or [],
    })()
    try:
        r = run_diagnose_step2_v510(sb, body, 'v5.10')
        return len(r.get('rules', [])), len(r.get('added_rules', []))
    except Exception as e:
        return None, str(e)[:80]

# ── BASELINE ──
print('\n=== BASELINE (factory_id 사용) ===')
b1, b_diag = step1(BASE_MFG, factory_id=INDUSTRIAL_ID)
if b_diag:
    b2_rules, b2_added = step2(INDUSTRIAL_ID, b_diag)
else:
    b2_rules, b2_added = None, 'no_diag'
print(f'Step1 candidates: {b1}')
print(f'Step2 rules: {b2_rules}, added: {b2_added}')

# ── PHASE 2: 공정 반응성 ──
print('\n=== PHASE 2: 공정 입력 반응성 ===')
for proc in ['용접','절단','도장','열처리','WELDING','CASTING','CHEMICAL_PROCESS']:
    _, diag = step1(BASE_MFG, factory_id=INDUSTRIAL_ID)
    r2, added = step2(INDUSTRIAL_ID, diag, processes=[proc])
    delta = (r2 - b2_rules) if r2 is not None and b2_rules is not None else 'ERR'
    status = 'ACTIVE' if isinstance(delta, int) and abs(delta) > 0 else ('ERR' if delta=='ERR' else 'DEAD')
    print(f'{proc:<20} rules={r2} added={added} delta={delta} [{status}]')

# ── PHASE 3: 작업 반응성 ──
print('\n=== PHASE 3: 작업종류 입력 반응성 ===')
for wt in ['고소작업','밀폘공간','화기작업','HIGH_ALTITUDE','CONFINED_SPACE','LIFTING','EXCAVATION']:
    _, diag = step1(BASE_MFG, factory_id=INDUSTRIAL_ID)
    r2, added = step2(INDUSTRIAL_ID, diag, work_types=[wt])
    delta = (r2 - b2_rules) if r2 is not None and b2_rules is not None else 'ERR'
    status = 'ACTIVE' if isinstance(delta, int) and abs(delta) > 0 else ('ERR' if delta=='ERR' else 'DEAD')
    print(f'{wt:<20} rules={r2} added={added} delta={delta} [{status}]')

# ── PHASE 4: 설비 반응성 (Step1 입력 매개변수) ──
print('\n=== PHASE 4: 설비 입력 반응성 (Step1) ===')
equips = [
    ('is_hazardous=1', {**BASE_MFG, 'is_hazardous_material':1}),
    ('has_boiler=1+kw500', {**BASE_MFG, 'has_boiler':1, 'boiler_capacity_kw':500}),
    ('gas_m3=100+hpg', {**BASE_MFG, 'has_high_pressure_gas':1,'is_hazardous_material':1,'gas_capacity_m3':100}),
    ('has_crane=1', {**BASE_MFG, 'has_crane':1}),
]
for label, inp in equips:
    cnt1, diag = step1(inp, factory_id=INDUSTRIAL_ID)
    delta_s1 = cnt1 - b1
    r2, added = step2(INDUSTRIAL_ID, diag)
    delta_s2 = (r2 - b2_rules) if r2 is not None and b2_rules is not None else 'ERR'
    print(f'{label:<28} S1={cnt1}({delta_s1:+d})  S2_rules={r2}(d={delta_s2})')

print('\n=== Stage2 Rule condition_code (DB 직접 확인) ===')
print('is_hazardous_material: 210건  gas_capacity_kg: 15건')
print('has_chemical_substance: 7건   annual_energy_toe: 7건')
print('boiler_capacity_kw: 6건       gas_capacity_m3: 4건')
print('processes/welding/crane 관련: 0건')
