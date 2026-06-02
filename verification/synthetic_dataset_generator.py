# verification/synthetic_dataset_generator.py
# Phase 7 -- Synthetic Dataset 생성 및 엔진 품질 검증
# 실행: TAI_USE_RUNTIME_ENGINE=false python3 verification/synthetic_dataset_generator.py
import os, sys, random, csv, time
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['TAI_USE_RUNTIME_ENGINE'] = 'false'

from supabase import create_client
from services.legal_v510_svc import run_diagnose_step1_v510

sb = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_ROLE_KEY'])
random.seed(42)

PROCESS_POOLS = {
    'MANUFACTURING': [
        {'process_id':'KOSHA-C-108-2017-P001','process_path':'마감>용접용단>용접작업>철골/배관 용접'},
        {'process_id':'IP000353','process_path':'기계제조>가공>절삭>절삭 가공'},
        {'process_id':'IP000777','process_path':'제련>표면처리>도장>도장 공정'},
        {'process_id':'IP000475','process_path':'제조>생산>건조>건조 공정'},
        {'process_id':'KOSHA-M-125-2012-P001','process_path':'가공>배합>혼합기 운전>원료 배합 및 혼합'},
        {'process_id':'IP000208','process_path':'제조>가공>냉각>냉각 및 안정화'},
        {'process_id':'IP000538','process_path':'공정제조>원료공급>저장·이송>원료 저장 및 이송'},
    ],
    'CONSTRUCTION': [
        {'process_id':'CP001','process_path':'건설>토공>가설/준비>현장조사'},
        {'process_id':'CP006','process_path':'건설>토공>굴착>터파기'},
        {'process_id':'CP007','process_path':'건설>토공>굴착>굴착'},
        {'process_id':'CP009','process_path':'건설>토공>굴착>흙막이 설치'},
        {'process_id':'KOSHA-C-108-2017-P001','process_path':'마감>용접용단>용접작업>철골/배관 용접'},
    ],
    'LOGISTICS': [
        {'process_id':'IP005100','process_path':'물류·유통>입고>하역>입고 및 하역'},
        {'process_id':'KOSHA-V2-49xx-P001','process_path':'반입>하역>상차 준비>차량 접안 및 위치 조정'},
        {'process_id':'KOSHA-V2-49xx-P005','process_path':'보관>창고운영>입고 보관>입고 화물 적치'},
    ],
    'CHEMICAL': [
        {'process_id':'IP000538','process_path':'공정제조>원료공급>저장·이송>원료 저장 및 이송'},
        {'process_id':'KOSHA-P-178-2022-P001','process_path':'가스분리>흡착>PSA 운전>흡착탑 전환 운전'},
        {'process_id':'KOSHA-M-125-2012-P001','process_path':'가공>배합>혼합기 운전>원료 배합 및 혼합'},
    ],
    'FOOD': [
        {'process_id':'IP000475','process_path':'제조>생산>건조>건조 공정'},
        {'process_id':'IP000208','process_path':'제조>가공>냉각>냉각 및 안정화'},
        {'process_id':'IP005100','process_path':'물류·유통>입고>하역>입고 및 하역'},
    ],
    'BUILDING': [],
}

EQUIPMENT_POOLS = {
    'MANUFACTURING': ['021','014','036','024','023','027','029'],
    'CONSTRUCTION':  ['021','025','CRANE'],
    'LOGISTICS':     ['025','026','024','CONVEYOR'],
    'CHEMICAL':      ['027','028','029','015','014'],
    'FOOD':          ['014','019','025','031'],
    'BUILDING':      ['025','026','031','032'],
}

INDUSTRY_CONFIG = {
    'MANUFACTURING': {'sector':'MANUFACTURING','weight':35,'name_prefix':'제조업'},
    'CONSTRUCTION':  {'sector':'CONSTRUCTION', 'weight':20,'name_prefix':'건설업'},
    'LOGISTICS':     {'sector':'MANUFACTURING','weight':15,'name_prefix':'물류업'},
    'CHEMICAL':      {'sector':'MANUFACTURING','weight':10,'name_prefix':'화학업'},
    'FOOD':          {'sector':'MANUFACTURING','weight':10,'name_prefix':'식품업'},
    'BUILDING':      {'sector':'BUILDING',     'weight':10,'name_prefix':'일반건물'},
}

def pick_industry():
    industries = list(INDUSTRY_CONFIG.keys())
    weights = [INDUSTRY_CONFIG[i]['weight'] for i in industries]
    return random.choices(industries, weights=weights, k=1)[0]

def pick_employee_count():
    r = random.random()
    if r < 0.40: return random.randint(1, 49)
    if r < 0.80: return random.randint(50, 299)
    return random.randint(300, 1000)

def make_profile(idx, industry):
    cfg = INDUSTRY_CONFIG[industry]
    employee_count = pick_employee_count()
    floor_area = random.choice([200,500,1000,2000,5000,10000,20000])

    proc_pool = PROCESS_POOLS.get(industry, [])
    if proc_pool:
        n_processes = random.randint(1, min(4, len(proc_pool)))
        processes = random.sample(proc_pool, n_processes)
    else:
        processes = []

    equip_pool = EQUIPMENT_POOLS.get(industry, [])
    n_equip = random.randint(1, min(3, len(equip_pool))) if equip_pool else 0
    equipments = random.sample(equip_pool, n_equip) if equip_pool else []

    contract_eok = random.choice([5,20,50,100,300]) if cfg['sector'] == 'CONSTRUCTION' else None

    return {
        'idx': idx,
        'factory_name': f'{cfg["name_prefix"]}_{idx:04d}',
        'industry': industry,
        'sector': cfg['sector'],
        'employee_count': employee_count,
        'floor_area': floor_area,
        'process_ids': [p['process_id'] for p in processes],
        'process_paths': [p['process_path'] for p in processes],
        'equipment_type_codes': equipments,
        'is_hazardous_material': 1 if industry in ('CHEMICAL','MANUFACTURING') and random.random() > 0.5 else 0,
        'has_high_pressure_gas': 1 if industry == 'CHEMICAL' and random.random() > 0.6 else 0,
        'gas_capacity_kg': random.choice([0,100,500,1000]) if industry == 'CHEMICAL' else 0,
        'electrical_capacity_kw': random.choice([50,200,500,1000,2000]) if employee_count > 50 else random.choice([20,50,100]),
        'annual_energy_toe': random.choice([0,500,2000,5000]) if industry == 'BUILDING' and employee_count > 100 else 0,
        'elevator_count': random.choice([0,1,2,4]) if industry == 'BUILDING' else 0,
        'is_multi_use': 1 if industry == 'BUILDING' and random.random() > 0.5 else 0,
        'contract_amount_eok': contract_eok,
        # 건설 전용 추가 필드
        'construction_type': random.choice(['건축공사','토목공사']) if cfg['sector'] == 'CONSTRUCTION' else None,
        'direct_workers': random.randint(5, 30) if cfg['sector'] == 'CONSTRUCTION' else None,
        'subcon_workers': random.randint(10, 50) if cfg['sector'] == 'CONSTRUCTION' else None,
    }

def run_step1(profile):
    sector = profile['sector']
    inp = {
        'employee_count': profile['employee_count'],
        'floor_area': profile['floor_area'],
        'is_hazardous_material': profile['is_hazardous_material'],
        'has_high_pressure_gas': profile['has_high_pressure_gas'],
        'gas_capacity_kg': profile['gas_capacity_kg'],
        'electrical_capacity_kw': profile['electrical_capacity_kw'],
        'annual_energy_toe': profile['annual_energy_toe'],
        'elevator_count': profile['elevator_count'],
        'is_multi_use': profile['is_multi_use'],
    }
    if sector == 'CONSTRUCTION' and profile['contract_amount_eok']:
        inp['contract_amount_eok'] = profile['contract_amount_eok']

    # body 속성: _apply_construction_conditions()이 읽는 모든 필드 포함
    body = type('B', (), {
        'sector': sector,
        'factory_id': None,
        'worker_count': profile['employee_count'],
        'employee_count': profile['employee_count'],
        'floor_area': profile['floor_area'],
        'total_floor_area': profile['floor_area'],
        'electric_capacity': profile['electrical_capacity_kw'],
        'floor_count': 2,
        'elevator_count': profile['elevator_count'] or None,
        'contract_amount_eok': profile['contract_amount_eok'],
        'construction_type': profile['construction_type'],    # Phase 7-C 추가
        'direct_workers': profile['direct_workers'],          # Phase 7-C 추가
        'subcon_workers': profile['subcon_workers'],          # Phase 7-C 추가
        'building_use_type': None, 'construction_work_type': None,
        'ksic_major': None, 'facility_type': None,
        'input': inp,
    })()

    try:
        r = run_diagnose_step1_v510(sb, body, [sector,'MANUFACTURING','INDUSTRIAL'], 'v5.10')
        cands = r['data'].get('candidates', [])
        return {
            'candidate_count': len(cands),
            'appointment_count': sum(1 for c in cands if c.get('source_type') == 'APPOINT'),
            'inspection_count': sum(1 for c in cands if c.get('source_type') == 'INSPECT'),
            'action_count': sum(1 for c in cands if c.get('source_type') == 'ACTION'),
            'report_count': sum(1 for c in cands if c.get('source_type') in ('REPORT','NOTIFY')),
            'law_names': list({c.get('law_name','') for c in cands if c.get('law_name')}),
        }
    except Exception as e:
        return {'error': str(e)[:100], 'candidate_count': -1}

# ── 메인 ──
N = int(os.environ.get('SYNTHETIC_N', '500'))
print(f'=== Phase 7: Synthetic Dataset 생성 N={N} ===')
results = []
law_counter = defaultdict(int)
equip_impact = defaultdict(list)
process_impact = defaultdict(list)

for i in range(N):
    industry = pick_industry()
    profile = make_profile(i, industry)
    t0 = time.time()
    step1 = run_step1(profile)
    elapsed = round(time.time()-t0, 2)

    row = {
        'idx': i,
        'industry': industry,
        'sector': profile['sector'],
        'employee_count': profile['employee_count'],
        'floor_area': profile['floor_area'],
        'contract_amount_eok': profile['contract_amount_eok'] or 0,
        'process_ids': ','.join(profile['process_ids']),
        'equipment_codes': ','.join(profile['equipment_type_codes']),
        'is_hazardous': profile['is_hazardous_material'],
        'has_hpg': profile['has_high_pressure_gas'],
        **{k: step1.get(k, 0) for k in ('candidate_count','appointment_count','inspection_count','action_count','report_count')},
        'elapsed': elapsed,
        'error': step1.get('error', ''),
    }
    results.append(row)

    if i % 50 == 0:
        print(f'  [{i}/{N}] {industry} emp={profile["employee_count"]} contract={profile["contract_amount_eok"]} -> candidates={step1.get("candidate_count","ERR")}')

    ccount = step1.get('candidate_count', 0)
    if ccount > 0:
        for eq in profile['equipment_type_codes']:
            equip_impact[eq].append(ccount)
        for pid in profile['process_ids']:
            process_impact[pid].append(ccount)
        for law in step1.get('law_names', []):
            law_counter[law] += 1

# ── CSV 저장 ──
csv_path = '/tmp/synthetic_results.csv'
with open(csv_path, 'w', newline='', encoding='utf-8') as f:
    if results:
        w = csv.DictWriter(f, fieldnames=results[0].keys())
        w.writeheader()
        w.writerows(results)
print(f'\nCSV 저장: {csv_path}')

# ── 분석 ──
counts = [r['candidate_count'] for r in results if r['candidate_count'] >= 0]
print(f'\n=== 분석 1: Candidate 수 분포 ===')
print(f'  0건:        {sum(1 for c in counts if c == 0):>5}')
print(f'  1~5건:      {sum(1 for c in counts if 1 <= c <= 5):>5}')
print(f'  6~20건:     {sum(1 for c in counts if 6 <= c <= 20):>5}')
print(f'  21~100건:   {sum(1 for c in counts if 21 <= c <= 100):>5}')
print(f'  100건 이상:  {sum(1 for c in counts if c > 100):>5}')
print(f'  평균: {sum(counts)/len(counts):.1f}  min={min(counts)}  max={max(counts)}')

print(f'\n=== 분석 2: 산업군별 평균 Candidate ===')
by_industry = defaultdict(list)
for r in results:
    if r['candidate_count'] >= 0:
        by_industry[r['industry']].append(r['candidate_count'])
for ind, vals in sorted(by_industry.items()):
    print(f'  {ind:<15} n={len(vals):>4} avg={sum(vals)/len(vals):>7.1f} min={min(vals):>4} max={max(vals):>4}')

# 건설 공사금액별 세부 분석
con_rows = [r for r in results if r['industry'] == 'CONSTRUCTION' and r['candidate_count'] >= 0]
if con_rows:
    print(f'\n=== 분석 2-B: 건설 공사금액별 Candidate ===')
    for eok in [5, 20, 50, 100, 300]:
        vals = [r['candidate_count'] for r in con_rows if r['contract_amount_eok'] == eok]
        if vals:
            print(f'  {eok}억:  n={len(vals):>3} avg={sum(vals)/len(vals):.1f}')

print(f'\n=== 분석 3: 설비별 영향도 (Candidate 평균) ===')
for eq, vals in sorted(equip_impact.items(), key=lambda x: -sum(x[1])/len(x[1])):
    print(f'  equipment_type_code={eq:<12} n={len(vals):>4} avg={sum(vals)/len(vals):>7.1f}')

print(f'\n=== 분석 4: 상위 10대 적용 법령 ===')
for law, cnt in sorted(law_counter.items(), key=lambda x: -x[1])[:10]:
    print(f'  [{cnt:>4}] {law}')

print(f'\n=== 에러 요약 ===')
errors = [r for r in results if r.get('error')]
print(f'  에러 {len(errors)}/{N}')
if errors[:3]:
    for e in errors[:3]:
        print(f'    idx={e["idx"]} industry={e["industry"]}: {e["error"]}')

print(f'\n완료. CSV: {csv_path}')
