# verification/synthetic_facility_generator.py
# Phase 9-A — Synthetic Facility Generator + Engine Runner
# 실행: python3 verification/synthetic_facility_generator.py [100|500]
# 출력: /tmp/dataset_100.json / /tmp/dataset_500.json
import os, sys, random, json, time
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['TAI_USE_RUNTIME_ENGINE'] = 'false'

from supabase import create_client
from services.legal_v510_svc import run_diagnose_step1_v510

sb = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_ROLE_KEY'])
random.seed(2024)

# ─────────────────────────────────────────────
# 실제 DB 코드 (v_process_unified / equipment_assets 실데이터)
# ─────────────────────────────────────────────

# 산업군별 process_id pool (실 DB 기준)
PROCESS_POOL = {
    'BUILDING': [
        # 건설>설비
        {'pid': 'CP129', 'path': '건설>설비>공조>공조기 반입'},
        {'pid': 'CP134', 'path': '건설>설비>급배수>급수배관 설치'},
        {'pid': 'CP138', 'path': '건설>설비>소방기계>소방배관 설치'},
        {'pid': 'CP164', 'path': '건설>승강>승강기>승강기 반입'},
        {'pid': 'CP147', 'path': '건설>전기>수배전>수배전반 반입'},
        {'pid': 'CP152', 'path': '건설>전기>조명/동력>조명기구 설치'},
    ],
    'MANUFACTURING': [
        # 기계제조
        {'pid': 'IP000353', 'path': '기계제조>가공>절삭>절삭 가공'},
        {'pid': 'IP000354', 'path': '기계제조>가공>연삭>연삭 가공'},
        {'pid': 'IP000355', 'path': '기계제조>성형>프레스>프레스 성형'},
        {'pid': 'IP000356', 'path': '기계제조>접합>용접>용접 및 조립'},
        {'pid': 'IP000357', 'path': '기계제조>조립>시운전>시운전 및 조정'},
        {'pid': 'IP000358', 'path': '기계제조>검사>품질검사>품질 검사'},
        # 공정제조(화학)
        {'pid': 'IP000538', 'path': '공정제조>원료공급>저장·이송>원료 저장 및 이송'},
        {'pid': 'IP000539', 'path': '공정제조>반응>반응기 운전>반응 공정 운전'},
        {'pid': 'IP000540', 'path': '공정제조>분리>증류>증류 및 분리'},
        {'pid': 'IP000541', 'path': '공정제조>정제>여과·세정>정제 및 세정'},
        {'pid': 'IP000542', 'path': '공정제조>유틸리티>가열·냉각>열교환 및 냉각'},
        {'pid': 'IP000543', 'path': '공정제조>충전>탱크·드럼>충전 및 이송'},
        {'pid': 'IP000544', 'path': '공정제조>안전환경>누출·방폭>방폭 및 누출관리'},
        {'pid': 'IP000563', 'path': '공정제조>가공>혼합·용해>혼합 및 용해'},
        {'pid': 'IP000564', 'path': '공정제조>가공>반응>반응 공정'},
        {'pid': 'IP000565', 'path': '공정제조>가공>건조>건조 및 농축'},
        # KOSHA 제조
        {'pid': 'KOSHA-C-108-2017-P001', 'path': '마감>용접용단>용접작업>철골/배관 용접'},
        {'pid': 'KOSHA-M-125-2012-P001', 'path': '가공>배합>혼합기 운전>원료 배합 및 혼합'},
        {'pid': 'IP000208', 'path': '제조>가공>냉각>냉각 및 안정화'},
        {'pid': 'IP000475', 'path': '제조>생산>건조>건조 공정'},
    ],
    'CONSTRUCTION': [
        # 건설 건축/토목/철골
        {'pid': 'CP001', 'path': '건설>토공>가설/준비>현장조사'},
        {'pid': 'CP006', 'path': '건설>토공>굴착>터파기'},
        {'pid': 'CP007', 'path': '건설>토공>굴착>굴착'},
        {'pid': 'CP009', 'path': '건설>토공>굴착>흙막이 설치'},
        {'pid': 'CP023', 'path': '건설>기초>기초배근>기초 철근 가공'},
        {'pid': 'CP027', 'path': '건설>기초>기초거푸집>기초 거푸집 반입'},
        {'pid': 'CP031', 'path': '건설>기초>기초콘크리트>기초 콘크리트 타설'},
        {'pid': 'CP035', 'path': '건설>골조>철근>철근 가공'},
        {'pid': 'CP042', 'path': '건설>골조>거푸집>거푸집 제작'},
        {'pid': 'CP048', 'path': '건설>골조>콘크리트>콘크리트 타설'},
        {'pid': 'CP053', 'path': '건설>철골>철골제작>철골 가공'},
        {'pid': 'CP057', 'path': '건설>철골>철골설치>철골 반입'},
        {'pid': 'CP063', 'path': '건설>철골>데크플레이트>데크플레이트 반입'},
        {'pid': 'CP188', 'path': '건설>해체>내부철거>내장재 철거'},
        {'pid': 'CP192', 'path': '건설>해체>구조물해체>구조물 절단'},
        {'pid': 'CP196', 'path': '건설>토목>터널>천공'},
        {'pid': 'CP201', 'path': '건설>토목>교량>거더 반입'},
        {'pid': 'CP170', 'path': '건설>가스>가스배관>가스배관 설치'},
        {'pid': 'KOSHA-C-108-2017-P001', 'path': '마감>용접용단>용접작업>철골/배관 용접'},
    ],
}

# 산업군별 equipment_type_code pool (실 DB 기준)
EQUIPMENT_POOL = {
    'BUILDING': ['001','002','006','007','010','025','026','031','032','033','034','039'],
    'MANUFACTURING': [
        '001','006','007','008','010','011','012','013','014','015',
        '016','017','018','019','021','023','024','027','028','029',
        '030','036','037','040','CRANE','CONVEYOR','PRESS','PRESSURE_VESSEL',
    ],
    'CONSTRUCTION': ['021','025','CRANE'],
}

# 건설 construction_work_type pool (DB 실값)
CONSTRUCTION_WORK_TYPES = [
    '공통', 'NEW_CONSTRUCTION', 'FIRE_RISK_WORK', 'TUNNEL_CONSTRUCTION',
    'TUNNEL_SAFETY', 'electrical_construction', 'FIRE_FACILITY_INSTALLATION',
    'FLAMMABLE_GAS_WORK', '건축공사', '철근공사', 'all_construction',
]

# 산업군 프로파일
INDUSTRY_PROFILES = [
    # BUILDING
    {'name': '오피스빌딩',   'sector': 'BUILDING',      'weight': 8,  'hpg': False, 'hazmat': False},
    {'name': '상가복합',     'sector': 'BUILDING',      'weight': 7,  'hpg': False, 'hazmat': False},
    {'name': '병원',         'sector': 'BUILDING',      'weight': 5,  'hpg': False, 'hazmat': False},
    {'name': '학교',         'sector': 'BUILDING',      'weight': 5,  'hpg': False, 'hazmat': False},
    {'name': '호텔',         'sector': 'BUILDING',      'weight': 5,  'hpg': False, 'hazmat': False},
    {'name': '물류센터_B',   'sector': 'BUILDING',      'weight': 5,  'hpg': False, 'hazmat': False},
    # MANUFACTURING
    {'name': '금속가공',     'sector': 'MANUFACTURING', 'weight': 10, 'hpg': False, 'hazmat': True},
    {'name': '기계제조',     'sector': 'MANUFACTURING', 'weight': 8,  'hpg': False, 'hazmat': False},
    {'name': '전자부품',     'sector': 'MANUFACTURING', 'weight': 7,  'hpg': False, 'hazmat': False},
    {'name': '식품제조',     'sector': 'MANUFACTURING', 'weight': 6,  'hpg': False, 'hazmat': False},
    {'name': '화학공장',     'sector': 'MANUFACTURING', 'weight': 8,  'hpg': True,  'hazmat': True},
    {'name': '플라스틱',     'sector': 'MANUFACTURING', 'weight': 6,  'hpg': False, 'hazmat': False},
    # CONSTRUCTION
    {'name': '건축공사',     'sector': 'CONSTRUCTION',  'weight': 8,  'hpg': False, 'hazmat': False},
    {'name': '토목공사',     'sector': 'CONSTRUCTION',  'weight': 6,  'hpg': False, 'hazmat': False},
    {'name': '철골공사',     'sector': 'CONSTRUCTION',  'weight': 5,  'hpg': False, 'hazmat': False},
    {'name': '플랜트공사',   'sector': 'CONSTRUCTION',  'weight': 4,  'hpg': True,  'hazmat': True},
    {'name': '전기공사',     'sector': 'CONSTRUCTION',  'weight': 4,  'hpg': False, 'hazmat': False},
    {'name': '소방공사',     'sector': 'CONSTRUCTION',  'weight': 4,  'hpg': False, 'hazmat': False},
    {'name': '해체공사',     'sector': 'CONSTRUCTION',  'weight': 4,  'hpg': False, 'hazmat': False},
]

EMPLOYEE_OPTIONS = [1, 5, 10, 30, 50, 100, 300, 500, 1000]
FLOOR_AREA_OPTIONS = [100, 500, 1000, 5000, 10000, 50000]
ELECTRIC_OPTIONS = [50, 100, 300, 500, 1000, 5000]
CONTRACT_OPTIONS = [1, 5, 10, 50, 100, 300, 1000]  # 억원


def pick_profile():
    profiles = INDUSTRY_PROFILES
    weights = [p['weight'] for p in profiles]
    return random.choices(profiles, weights=weights, k=1)[0]


def make_facility(idx: int, profile: dict) -> dict:
    sector = profile['sector']
    employee_count = random.choice(EMPLOYEE_OPTIONS)
    floor_area = random.choice(FLOOR_AREA_OPTIONS)
    electric_kw = random.choice(ELECTRIC_OPTIONS)
    contract_eok = random.choice(CONTRACT_OPTIONS) if sector == 'CONSTRUCTION' else None

    # process_id: 실 DB pool에서 1~5개
    proc_pool = PROCESS_POOL.get(sector, [])
    n_proc = random.randint(1, min(5, len(proc_pool))) if proc_pool else 0
    processes = random.sample(proc_pool, n_proc) if proc_pool else []

    # equipment_type_code: 실 DB pool에서 1~10개
    eq_pool = EQUIPMENT_POOL.get(sector, [])
    n_eq = random.randint(1, min(10, len(eq_pool))) if eq_pool else 0
    equipments = random.sample(eq_pool, n_eq) if eq_pool else []

    # construction_work_types: CONSTRUCTION이면 1~5개
    work_types = []
    if sector == 'CONSTRUCTION':
        n_wt = random.randint(1, 5)
        work_types = random.sample(CONSTRUCTION_WORK_TYPES, min(n_wt, len(CONSTRUCTION_WORK_TYPES)))

    return {
        'idx': idx,
        'factory_name': f'{profile["name"]}_{idx:04d}',
        'industry': profile['name'],
        'sector': sector,
        'employee_count': employee_count,
        'floor_area': floor_area,
        'electrical_capacity_kw': electric_kw,
        'contract_amount_eok': contract_eok,
        'is_hazardous_material': 1 if profile['hazmat'] and random.random() > 0.4 else 0,
        'has_high_pressure_gas': 1 if profile['hpg'] and random.random() > 0.5 else 0,
        'gas_capacity_kg': random.choice([0, 100, 500, 1000]) if profile['hpg'] else 0,
        'elevator_count': random.choice([0, 1, 2, 4]) if sector == 'BUILDING' else 0,
        'is_multi_use': 1 if sector == 'BUILDING' and random.random() > 0.5 else 0,
        'annual_energy_toe': random.choice([0, 500, 2000, 5000]) if sector == 'BUILDING' else 0,
        'process_ids': [p['pid'] for p in processes],
        'process_paths': [p['path'] for p in processes],
        'equipment_type_codes': equipments,
        'construction_work_types': work_types,
        'construction_type': random.choice(['건축공사', '토목공사', '플랜트']) if sector == 'CONSTRUCTION' else None,
        'direct_workers': random.randint(5, 50) if sector == 'CONSTRUCTION' else None,
        'subcon_workers': random.randint(10, 100) if sector == 'CONSTRUCTION' else None,
    }


def run_step1(facility: dict) -> dict:
    sector = facility['sector']
    inp = {
        'employee_count': facility['employee_count'],
        'floor_area': facility['floor_area'],
        'electrical_capacity_kw': facility['electrical_capacity_kw'],
        'is_hazardous_material': facility['is_hazardous_material'],
        'has_high_pressure_gas': facility['has_high_pressure_gas'],
        'gas_capacity_kg': facility['gas_capacity_kg'],
        'elevator_count': facility['elevator_count'],
        'is_multi_use': facility['is_multi_use'],
        'annual_energy_toe': facility['annual_energy_toe'],
    }
    if facility['contract_amount_eok']:
        inp['contract_amount_eok'] = facility['contract_amount_eok']

    # processes: [{process_id, process_path}] 형태로 전달
    proc_list = [
        {'process_id': pid, 'process_path': path}
        for pid, path in zip(facility['process_ids'], facility['process_paths'])
    ]

    body = type('B', (), {
        'sector': sector,
        'factory_id': None,
        'worker_count': facility['employee_count'],
        'employee_count': facility['employee_count'],
        'floor_area': facility['floor_area'],
        'total_floor_area': facility['floor_area'],
        'electric_capacity': facility['electrical_capacity_kw'],
        'floor_count': 2,
        'elevator_count': facility['elevator_count'] or None,
        'contract_amount_eok': facility['contract_amount_eok'],
        'construction_type': facility['construction_type'],
        'direct_workers': facility['direct_workers'],
        'subcon_workers': facility['subcon_workers'],
        'building_use_type': None, 'construction_work_type': None,
        'ksic_major': None, 'facility_type': None,
        'input': inp,
    })()

    try:
        r = run_diagnose_step1_v510(sb, body, [sector, 'MANUFACTURING', 'INDUSTRIAL', 'BUILDING'], 'v5.10')
        data = r['data']
        candidates = data.get('candidates', [])
        presentation = data.get('presentation', {})
        meta = presentation.get('metadata', {})

        return {
            'ok': True,
            'candidate_count': len(candidates),
            'display_count': meta.get('display_count', 0),
            'reduction_rate': meta.get('reduction_rate', 0),
            'appointment_count': sum(1 for c in candidates if c.get('source_type') == 'APPOINT'),
            'inspect_count': sum(1 for c in candidates if c.get('source_type') == 'INSPECT'),
            'action_count': sum(1 for c in candidates if c.get('source_type') == 'ACTION'),
            'report_count': sum(1 for c in candidates if c.get('source_type') in ('REPORT', 'NOTIFY')),
            'top_laws': [g['law_name'] for g in (presentation.get('grouped_candidates') or [])[:5]],
        }
    except Exception as e:
        return {'ok': False, 'error': str(e)[:100], 'candidate_count': -1}


# ─────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────
N = int(sys.argv[1]) if len(sys.argv) > 1 else 100
print(f'=== Phase 9-A: Synthetic Facility Generator N={N} ===')

dataset = []
errors = 0

for i in range(N):
    profile = pick_profile()
    facility = make_facility(i, profile)
    t0 = time.time()
    result = run_step1(facility)
    elapsed = round(time.time() - t0, 2)

    row = {
        'input': {
            'idx': facility['idx'],
            'factory_name': facility['factory_name'],
            'industry': facility['industry'],
            'sector': facility['sector'],
            'employee_count': facility['employee_count'],
            'floor_area': facility['floor_area'],
            'electrical_capacity_kw': facility['electrical_capacity_kw'],
            'contract_amount_eok': facility['contract_amount_eok'],
            'is_hazardous_material': facility['is_hazardous_material'],
            'has_high_pressure_gas': facility['has_high_pressure_gas'],
            'process_ids': facility['process_ids'],
            'equipment_type_codes': facility['equipment_type_codes'],
            'construction_work_types': facility['construction_work_types'],
        },
        'step1': result,
        'candidate_count': result.get('candidate_count', -1),
        'display_count': result.get('display_count', 0),
        'reduction_rate': result.get('reduction_rate', 0),
        'elapsed': elapsed,
    }
    dataset.append(row)

    if not result['ok']:
        errors += 1

    if i % 20 == 0 or not result['ok']:
        status = f"cand={result.get('candidate_count','ERR')} disp={result.get('display_count','?')}"
        err_str = f" ERR={result.get('error','')[:40]}" if not result['ok'] else ''
        print(f"  [{i:>4}/{N}] {profile['name']:<12} emp={facility['employee_count']:>5} {status}{err_str}")

# 저장
out_path = f'/tmp/dataset_{N}.json'
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(dataset, f, ensure_ascii=False, indent=2)
print(f'\n저장: {out_path}  ({len(dataset)}건, 에러 {errors}건)')

# 간단 요약
ok_rows = [r for r in dataset if r['candidate_count'] >= 0]
if ok_rows:
    counts = [r['candidate_count'] for r in ok_rows]
    dcounts = [r['display_count'] for r in ok_rows]
    by_sector = defaultdict(list)
    for r in ok_rows:
        by_sector[r['input']['sector']].append(r['candidate_count'])

    print(f'\n=== 요약 ===')
    print(f'  성공: {len(ok_rows)}/{N}')
    print(f'  Candidate avg={sum(counts)/len(counts):.1f} min={min(counts)} max={max(counts)}')
    print(f'  Display avg={sum(dcounts)/len(dcounts):.1f}')
    print(f'  Reduction avg={sum(r["reduction_rate"] for r in ok_rows)/len(ok_rows):.1f}%')
    print(f'\n  섹터별 평균 Candidate:')
    for sec, vals in sorted(by_sector.items()):
        print(f'    {sec:<20} n={len(vals):>4} avg={sum(vals)/len(vals):>7.1f}')
