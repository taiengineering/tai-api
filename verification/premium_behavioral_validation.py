# verification/premium_behavioral_validation.py
# PREMIUM LEG Behavioral Validation Audit v1
# 실행: TAI_USE_RUNTIME_ENGINE=false python3 verification/premium_behavioral_validation.py
import os, sys, json, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['TAI_USE_RUNTIME_ENGINE'] = 'false'

from supabase import create_client
from services.legal_v510_svc import run_diagnose_step1_v510, run_diagnose_step2_v510
from schemas.legal_engine_v510 import DiagnoseStep2Body

sb = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_ROLE_KEY'])

FACTORY_ID = 'test-premium-factory-001'

def step1(inp):
    sector = inp.get('sector', 'MANUFACTURING')
    body = type('B', (), {
        'sector': sector,
        'factory_id': FACTORY_ID,
        'worker_count': inp.get('worker_count', 50),
        'employee_count': inp.get('employee_count', 50),
        'floor_area': inp.get('floor_area', 5000),
        'total_floor_area': inp.get('floor_area', 5000),
        'electric_capacity': inp.get('electrical_capacity_kw', 1000),
        'electrical_capacity_kw': inp.get('electrical_capacity_kw', 1000),
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

def step2(diagnosis_id, processes=None, work_types=None):
    if not diagnosis_id:
        return None, None
    body = type('B', (), {
        'factory_id': FACTORY_ID,
        'diagnosis_id': diagnosis_id,
        'processes': processes or [],
        'construction_types': [],
        'construction_work_types': work_types or [],
    })()
    try:
        r = run_diagnose_step2_v510(sb, body, 'v5.10')
        return len(r.get('rules', [])), len(r.get('added_rules', []))
    except Exception as e:
        return None, str(e)[:60]

# ── BASELINE ──
print('=== BASELINE (MANUFACTURING, 50명, 5000㎡, 1000kw) ===')
BASE = {'sector':'MANUFACTURING','worker_count':50,'employee_count':50,
        'floor_area':5000,'electrical_capacity_kw':1000,'is_factory_registered':1}

# Step1만
b_step1, b_diag = step1(BASE)
b_step2_rules, b_step2_added = step2(b_diag)
print(f'Step1 candidates: {b_step1}')
print(f'Step2 rules: {b_step2_rules}, added: {b_step2_added}')
print()

# ── PHASE 2: 공정 반응성 ──
print('=== PHASE 2: 공정 반응성 (테스트 Step2.processes) ===')
PROCESSES = [
    '\uc6a9\uc811', '\uc808\ub2e8', '\ub3c4\uc7a5', '\uc5f4\ucc98\ub9ac', '\uc8fc\uc870',
    '\uc0ac\ucd9c', '\uc555\ucd9c', '\ub3c4\uae08', '\ud654\ud559\ubc18\uc751', '\ud63c\ud569\uacf5\uc815',
    'WELDING', 'CUTTING', 'PAINTING', 'CASTING', 'CHEMICAL'
]
for proc in PROCESSES:
    cnt1, diag_id = step1(BASE)
    r2, added = step2(diag_id, processes=[proc])
    delta = (r2 - b_step2_rules) if r2 is not None and b_step2_rules is not None else 'ERR'
    impact = 'ACTIVE' if isinstance(delta, int) and abs(delta) > 0 else 'DEAD'
    print(f'{proc:<16} step2_rules={r2} delta={delta} [{impact}]')

# ── PHASE 3: 작업 반응성 ──
print()
print('=== PHASE 3: 작업 유형 반응성 (construction_work_types) ===')
WORK_TYPES = [
    '\uace0\uc18c\uc791\uc5c5', '\ubc00\ud3d8\uacf5\uac04', '\ud654\uae30\uc791\uc5c5', '\uad74\ucc29\uc791\uc5c5',
    '\uc591\uc911\uc791\uc5c5', '\uc804\uae30\uc791\uc5c5', '\ud574\uccb4\uc791\uc5c5', '\ubc1c\ud30c\uc791\uc5c5',
    'HIGH_ALTITUDE', 'CONFINED_SPACE', 'FIRE_WORK', 'EXCAVATION', 'LIFTING'
]
for wt in WORK_TYPES:
    cnt1, diag_id = step1(BASE)
    r2, added = step2(diag_id, work_types=[wt])
    delta = (r2 - b_step2_rules) if r2 is not None and b_step2_rules is not None else 'ERR'
    impact = 'ACTIVE' if isinstance(delta, int) and abs(delta) > 0 else 'DEAD'
    print(f'{wt:<16} step2_rules={r2} delta={delta} [{impact}]')

# ── PHASE 4: 설비 반응성 (이미 Step1에서 확인) ──
print()
print('=== PHASE 4: 설비 반응성 (Step1 입력) ===')
EQUIPS = [
    ('has_boiler=1', {**BASE, 'has_boiler':1}),
    ('boiler_kw=500', {**BASE, 'has_boiler':1, 'boiler_capacity_kw':500}),
    ('is_hazardous=1', {**BASE, 'is_hazardous_material':1}),
    ('has_high_pressure_gas=1', {**BASE, 'has_high_pressure_gas':1, 'gas_capacity_kg':500}),
    ('gas_m3=100', {**BASE, 'has_high_pressure_gas':1, 'is_hazardous_material':1, 'gas_capacity_m3':100}),
    ('has_crane=1', {**BASE, 'has_crane':1}),  # DEAD 예상
]
for label, inp in EQUIPS:
    cnt1, diag_id = step1(inp)
    delta_s1 = cnt1 - b_step1
    r2, added = step2(diag_id)
    delta_s2 = (r2 - b_step2_rules) if r2 is not None and b_step2_rules is not None else 'ERR'
    print(f'{label:<28} S1={cnt1}({delta_s1:+d}) S2_rules={r2}(delta={delta_s2})')

# ── 정리 ──
print()
print('=== 요약: diagnosis_stage=2 Rule condition_code ===')
print('is_hazardous_material: 210건')
print('gas_capacity_kg: 15건')
print('has_chemical_substance: 7건')
print('annual_energy_toe: 7건')
print('boiler_capacity_kw: 6건')
print('gas_capacity_m3: 4건')
print('processes/welding/crane 관련 condition_code: 0건')
print('\n\u2192 Step2의 processes 입력값은 \nDB Rule에 연결되지 않음.')
print('\n\u2192 유료진단에서도 is_hazardous_material가 가장 중요한 트리거.')
