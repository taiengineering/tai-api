# verification/behavioral_validation.py
# LEG Behavioral Validation Audit v1
# 실행: TAI_USE_RUNTIME_ENGINE=false python3 verification/behavioral_validation.py
import os, sys, time, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['TAI_USE_RUNTIME_ENGINE'] = 'false'

from supabase import create_client
from services.legal_v510_svc import run_diagnose_step1_v510

sb = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_ROLE_KEY'])

def run(inp):
    sector = inp.get('sector', 'BUILDING')
    body = type('B', (), {
        'sector': sector,
        'worker_count': inp.get('worker_count', 10),
        'employee_count': inp.get('employee_count', 10),
        'floor_area': inp.get('floor_area', 500),
        'total_floor_area': inp.get('floor_area', 500),
        'electric_capacity': inp.get('electrical_capacity_kw', 0),
        'electrical_capacity_kw': inp.get('electrical_capacity_kw', 0),
        'floor_count': inp.get('floor_count', 1),
        'elevator_count': inp.get('elevator_count'),
        'contract_amount_eok': inp.get('contract_amount_eok'),
        'factory_id': None, 'building_use_type': None,
        'construction_work_type': None, 'ksic_major': None, 'facility_type': None,
        'input': {k: v for k, v in inp.items() if k not in (
            'sector','worker_count','employee_count','floor_area',
            'electrical_capacity_kw','floor_count','elevator_count','contract_amount_eok')},
    })()
    r = run_diagnose_step1_v510(sb, body, [sector,'MANUFACTURING','INDUSTRIAL'], 'v5.10')
    return len(r['data'].get('candidates', []))

# ───────────────────────────────────────────────────
# PHASE 3: 입력 변화 테스트 (기준선 대비 delta)
# ───────────────────────────────────────────────────
print('=== PHASE 3: 입력 변화 테스트 ===')

BASE_B = {'sector':'BUILDING','worker_count':30,'employee_count':30,'floor_area':2000,'floor_count':5,'elevator_count':1}
BASE_M = {'sector':'MANUFACTURING','worker_count':30,'employee_count':30,'floor_area':1500,'is_factory_registered':1}
BASE_C = {'sector':'CONSTRUCTION','worker_count':30,'employee_count':30,'contract_amount_eok':30}

base_b = run(BASE_B)
base_m = run(BASE_M)
base_c = run(BASE_C)

print(f'BUILDING   기준: {base_b}')
print(f'MANUFACTURING 기준: {base_m}')
print(f'CONSTRUCTION 기준: {base_c}')
print()

tests = [
    # ── BUILDING 변화 ──
    ('B+위험물',    {**BASE_B, 'is_hazardous_material':1}),
    ('B+화학물질',  {**BASE_B, 'has_chemical_substance':1}),
    ('B+고압가스',  {**BASE_B, 'has_high_pressure_gas':1, 'gas_capacity_kg':100}),
    ('B+보일러',    {**BASE_B, 'has_boiler':1, 'boiler_capacity_kw':200}),
    ('B+has_crane', {**BASE_B, 'has_crane':1}),          # DEAD 예상
    ('B+has_high_work', {**BASE_B, 'has_high_work':1}),  # DEAD 예상
    ('B+has_blasting',  {**BASE_B, 'has_blasting':1}),   # DEAD 예상
    ('B+에너지2500', {**BASE_B, 'annual_energy_toe':2500}),
    ('B+building_grade1', {**BASE_B, 'building_grade':1}),
    ('B+다중이용',  {**BASE_B, 'is_multi_use':1}),
    # ── MANUFACTURING 변화 ──
    ('M+위험물',    {**BASE_M, 'is_hazardous_material':1}),
    ('M+고압가스',  {**BASE_M, 'has_high_pressure_gas':1, 'gas_capacity_kg':500}),
    ('M+화학물질',  {**BASE_M, 'has_chemical_substance':1}),
    ('M+보일러',    {**BASE_M, 'has_boiler':1}),
    ('M+gas_m3_100', {**BASE_M, 'is_hazardous_material':1, 'has_high_pressure_gas':1, 'gas_capacity_m3':100}),
    ('M+에너지2500', {**BASE_M, 'annual_energy_toe':2500}),
    ('M+manufacturing_biz', {**BASE_M, 'manufacturing_business':1}),
    # ── CONSTRUCTION 변화 ──
    ('C+위험물',    {**BASE_C, 'is_hazardous_material':1}),
    ('C+고압가스',  {**BASE_C, 'has_high_pressure_gas':1, 'gas_capacity_kg':200}),
    ('C+터널600m',  {**BASE_C, 'TUNNEL_LENGTH':600}),
    ('C+has_crane', {**BASE_C, 'has_crane':1}),           # DEAD 예상
    ('C+has_blasting', {**BASE_C, 'has_blasting':1}),     # DEAD 예상
    ('C+300억',    {**BASE_C, 'contract_amount_eok':300}),
]

results = []
for label, inp in tests:
    base = base_b if label.startswith('B') else (base_m if label.startswith('M') else base_c)
    cnt = run(inp)
    delta = cnt - base
    impact = 'HIGH' if abs(delta)>=20 else ('MEDIUM' if abs(delta)>=5 else ('LOW' if abs(delta)>0 else 'DEAD'))
    results.append({'label': label, 'base': base, 'result': cnt, 'delta': delta, 'impact': impact})
    print(f'{label:<22} base={base} result={cnt} delta={delta:+d} [{impact}]')

# ───────────────────────────────────────────────────
# PHASE 4: 전 필드 영향도 분류
# ───────────────────────────────────────────────────
print()
print('=== PHASE 4: 영향도 분류 ===')
for impact in ['HIGH','MEDIUM','LOW','DEAD']:
    items = [r['label'] for r in results if r['impact'] == impact]
    print(f'{impact}: {items}')

# ───────────────────────────────────────────────────
# PHASE 5: 민감도 — 연속 값 변화
# ───────────────────────────────────────────────────
print()
print('=== PHASE 5: 연속값 민감도 ===')
SENS = [
    ('employee_count', [5,10,30,50,100,300,1000],
     {'sector':'BUILDING','floor_area':2000,'floor_count':5,'elevator_count':1}),
    ('floor_area', [100,500,1000,3000,5000,10000],
     {'sector':'BUILDING','employee_count':30,'floor_count':5}),
    ('gas_capacity_m3', [0,10,100,1000,5000],
     {'sector':'MANUFACTURING','employee_count':30,'is_factory_registered':1,
      'is_hazardous_material':1,'has_high_pressure_gas':1}),
    ('contract_amount_eok', [3,10,30,50,100,300],
     {'sector':'CONSTRUCTION','employee_count':30}),
    ('annual_energy_toe', [0,500,2000,5000],
     {'sector':'BUILDING','employee_count':50,'floor_area':5000}),
    ('has_crane', [0,1],   # DEAD 검증
     {'sector':'CONSTRUCTION','employee_count':30,'contract_amount_eok':30}),
    ('has_blasting', [0,1],  # DEAD 검증
     {'sector':'CONSTRUCTION','employee_count':30,'contract_amount_eok':30}),
]
for field, values, base in SENS:
    row = []
    for v in values:
        inp = dict(base); inp[field] = v
        row.append((v, run(inp)))
    deltas = [r[1]-row[0][1] for r in row]
    max_delta = max(abs(d) for d in deltas)
    impact = 'HIGH' if max_delta>=20 else ('MEDIUM' if max_delta>=5 else ('LOW' if max_delta>0 else 'DEAD'))
    print(f'{field:<25} {row} [{impact}]')

json.dump(results, open('/tmp/behavioral_results.json','w'), ensure_ascii=False)
print()
print('Done.')
