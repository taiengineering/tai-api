# verification/full_sector_simulation.py
# TAI Full Sector Simulation Audit v1
import os, sys, time, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['TAI_USE_RUNTIME_ENGINE'] = 'false'

from supabase import create_client
from services.legal_v510_svc import run_diagnose_step1_v510
from services.obligation_standard_builder import build_obligations
from services.obligation_refinement import refine

sb = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_ROLE_KEY'])

# PHASE 1+2: 30개 사업장 프로파일 (Full Input)
PROFILES = [
    # ── BUILDING 10개 ──
    {"id":"B01","label":"소형사무실","sector":"BUILDING",
     "worker_count":5,"employee_count":5,"floor_area":200,"floor_count":3,
     "elevator_count":0,"is_multi_use":0,"electrical_capacity_kw":20,
     "annual_energy_toe":0,"is_hazardous_material":0},
    {"id":"B02","label":"중형사무실","sector":"BUILDING",
     "worker_count":30,"employee_count":30,"floor_area":1500,"floor_count":6,
     "elevator_count":1,"is_multi_use":0,"electrical_capacity_kw":150,
     "annual_energy_toe":0,"is_hazardous_material":0},
    {"id":"B03","label":"대형사무실","sector":"BUILDING",
     "worker_count":100,"employee_count":100,"floor_area":8000,"floor_count":15,
     "elevator_count":4,"is_multi_use":0,"electrical_capacity_kw":800,
     "annual_energy_toe":2000,"is_hazardous_material":0},
    {"id":"B04","label":"소형상가","sector":"BUILDING",
     "worker_count":10,"employee_count":10,"floor_area":300,"floor_count":2,
     "elevator_count":0,"is_multi_use":1,"electrical_capacity_kw":30,
     "annual_energy_toe":0,"is_hazardous_material":0},
    {"id":"B05","label":"대형상가","sector":"BUILDING",
     "worker_count":50,"employee_count":50,"floor_area":5000,"floor_count":5,
     "elevator_count":2,"is_multi_use":1,"electrical_capacity_kw":500,
     "annual_energy_toe":1500,"is_hazardous_material":0},
    {"id":"B06","label":"다중이용시설","sector":"BUILDING",
     "worker_count":40,"employee_count":40,"floor_area":3000,"floor_count":4,
     "elevator_count":2,"is_multi_use":1,"electrical_capacity_kw":300,
     "annual_energy_toe":800,"is_hazardous_material":0},
    {"id":"B07","label":"병원","sector":"BUILDING",
     "worker_count":80,"employee_count":200,"floor_area":6000,"floor_count":8,
     "elevator_count":4,"is_multi_use":1,"electrical_capacity_kw":600,
     "annual_energy_toe":3000,"hospital_beds":150,"is_hazardous_material":0},
    {"id":"B08","label":"학교","sector":"BUILDING",
     "worker_count":50,"employee_count":80,"floor_area":4000,"floor_count":4,
     "elevator_count":1,"is_multi_use":0,"electrical_capacity_kw":200,
     "annual_energy_toe":500,"student_count":500,"is_hazardous_material":0},
    {"id":"B09","label":"공공시설","sector":"BUILDING",
     "worker_count":60,"employee_count":60,"floor_area":5000,"floor_count":6,
     "elevator_count":2,"is_multi_use":1,"electrical_capacity_kw":400,
     "annual_energy_toe":1200,"is_hazardous_material":0},
    {"id":"B10","label":"위험시설사무실","sector":"BUILDING",
     "worker_count":25,"employee_count":25,"floor_area":2000,"floor_count":3,
     "elevator_count":0,"is_multi_use":0,"electrical_capacity_kw":200,
     "annual_energy_toe":0,"is_hazardous_material":1,"has_chemical_substance":1,
     "gas_capacity_kg":50,"gas_capacity_m3":20},
    # ── MANUFACTURING 10개 ──
    {"id":"M01","label":"소규모제조업","sector":"MANUFACTURING",
     "worker_count":10,"employee_count":10,"floor_area":300,
     "is_factory_registered":1,"is_hazardous_material":0,
     "has_high_pressure_gas":0,"has_chemical_substance":0,"electrical_capacity_kw":50},
    {"id":"M02","label":"중규모제조업","sector":"MANUFACTURING",
     "worker_count":50,"employee_count":50,"floor_area":1500,
     "is_factory_registered":1,"is_hazardous_material":0,
     "has_high_pressure_gas":0,"has_chemical_substance":0,"electrical_capacity_kw":200},
    {"id":"M03","label":"대규모제조업","sector":"MANUFACTURING",
     "worker_count":200,"employee_count":200,"floor_area":8000,
     "is_factory_registered":1,"is_hazardous_material":0,
     "has_high_pressure_gas":0,"has_chemical_substance":0,"electrical_capacity_kw":1000},
    {"id":"M04","label":"위험물취급","sector":"MANUFACTURING",
     "worker_count":30,"employee_count":30,"floor_area":1000,
     "is_factory_registered":1,"is_hazardous_material":1,
     "has_high_pressure_gas":0,"has_chemical_substance":0,
     "gas_capacity_kg":200,"electrical_capacity_kw":150},
    {"id":"M05","label":"화학물질취급","sector":"MANUFACTURING",
     "worker_count":40,"employee_count":40,"floor_area":2000,
     "is_factory_registered":1,"is_hazardous_material":1,"has_chemical_substance":1,
     "has_high_pressure_gas":0,"gas_capacity_kg":0,"electrical_capacity_kw":200},
    {"id":"M06","label":"고압가스사용","sector":"MANUFACTURING",
     "worker_count":35,"employee_count":35,"floor_area":1200,
     "is_factory_registered":1,"is_hazardous_material":1,"has_high_pressure_gas":1,
     "gas_capacity_kg":1000,"gas_capacity_m3":200,"electrical_capacity_kw":300},
    {"id":"M07","label":"에너지다소비","sector":"MANUFACTURING",
     "worker_count":80,"employee_count":80,"floor_area":5000,
     "is_factory_registered":1,"is_hazardous_material":0,
     "has_high_pressure_gas":0,"has_chemical_substance":0,
     "electrical_capacity_kw":2000,"annual_energy_toe":2500},
    {"id":"M08","label":"식품제조업","sector":"MANUFACTURING",
     "worker_count":25,"employee_count":25,"floor_area":800,
     "is_factory_registered":1,"is_hazardous_material":0,
     "has_high_pressure_gas":0,"has_chemical_substance":0,
     "manufacturing_business":1,"electrical_capacity_kw":100},
    {"id":"M09","label":"금속제조업","sector":"MANUFACTURING",
     "worker_count":60,"employee_count":60,"floor_area":3000,
     "is_factory_registered":1,"is_hazardous_material":1,
     "has_high_pressure_gas":1,"has_chemical_substance":1,
     "gas_capacity_kg":500,"gas_capacity_m3":100,"electrical_capacity_kw":500},
    {"id":"M10","label":"보일러설비제조","sector":"MANUFACTURING",
     "worker_count":45,"employee_count":45,"floor_area":2500,
     "is_factory_registered":1,"is_hazardous_material":1,
     "has_boiler":1,"boiler_capacity_kw":500,"has_pressure_chamber":1,
     "electrical_capacity_kw":400},
    # ── CONSTRUCTION 10개 ──
    {"id":"C01","label":"5억공사","sector":"CONSTRUCTION",
     "worker_count":5,"employee_count":5,"contract_amount_eok":5,
     "construction_amount":500000000,"is_construction_site":1,
     "is_hazardous_material":0},
    {"id":"C02","label":"20억공사","sector":"CONSTRUCTION",
     "worker_count":20,"employee_count":20,"contract_amount_eok":20,
     "construction_amount":2000000000,"is_construction_site":1,
     "is_hazardous_material":0},
    {"id":"C03","label":"50억공사","sector":"CONSTRUCTION",
     "worker_count":40,"employee_count":40,"contract_amount_eok":50,
     "construction_amount":5000000000,"is_construction_site":1,
     "is_hazardous_material":0},
    {"id":"C04","label":"100억공사","sector":"CONSTRUCTION",
     "worker_count":80,"employee_count":80,"contract_amount_eok":100,
     "construction_amount":10000000000,"is_construction_site":1,
     "is_hazardous_material":0},
    {"id":"C05","label":"300억공사","sector":"CONSTRUCTION",
     "worker_count":200,"employee_count":200,"contract_amount_eok":300,
     "construction_amount":30000000000,"is_construction_site":1,
     "is_hazardous_material":0},
    {"id":"C06","label":"터널공사","sector":"CONSTRUCTION",
     "worker_count":50,"employee_count":50,"contract_amount_eok":80,
     "construction_amount":8000000000,"is_construction_site":1,
     "TUNNEL_LENGTH":600,"is_hazardous_material":0},
    {"id":"C07","label":"교량공사","sector":"CONSTRUCTION",
     "worker_count":60,"employee_count":60,"contract_amount_eok":120,
     "construction_amount":12000000000,"is_construction_site":1,
     "is_hazardous_material":0},
    {"id":"C08","label":"건축공사","sector":"CONSTRUCTION",
     "worker_count":30,"employee_count":30,"contract_amount_eok":30,
     "construction_amount":3000000000,"is_construction_site":1,
     "is_hazardous_material":0},
    {"id":"C09","label":"플랜트공사","sector":"CONSTRUCTION",
     "worker_count":100,"employee_count":100,"contract_amount_eok":200,
     "construction_amount":20000000000,"is_construction_site":1,
     "is_hazardous_material":1},
    {"id":"C10","label":"고위험공정","sector":"CONSTRUCTION",
     "worker_count":50,"employee_count":50,"contract_amount_eok":60,
     "construction_amount":6000000000,"is_construction_site":1,
     "is_hazardous_material":1,"has_high_pressure_gas":1},
]

# PHASE 3: 전수 실행
results = []
for p in PROFILES:
    pid = p['id']; label = p['label']; sector = p['sector']
    inp = {k: v for k, v in p.items() if k not in ('id','label','sector')}

    body = type('B', (), {
        'sector': sector,
        'worker_count': inp.get('worker_count'),
        'employee_count': inp.get('employee_count'),
        'floor_area': inp.get('floor_area'),
        'total_floor_area': inp.get('floor_area'),
        'electric_capacity': inp.get('electrical_capacity_kw', 0),
        'floor_count': inp.get('floor_count', 1),
        'elevator_count': inp.get('elevator_count'),
        'contract_amount_eok': inp.get('contract_amount_eok'),
        'factory_id': None, 'building_use_type': None,
        'construction_work_type': None, 'ksic_major': None, 'facility_type': None,
        'input': {k: v for k, v in inp.items() if k not in (
            'worker_count','employee_count','floor_area','electrical_capacity_kw',
            'floor_count','elevator_count','contract_amount_eok')},
    })()

    t0 = time.time()
    try:
        r = run_diagnose_step1_v510(sb, body, [sector,'MANUFACTURING','INDUSTRIAL'], 'v5.10')
        cands = r['data'].get('candidates', [])
        obs = build_obligations(cands)
        refined = refine(obs)
        q = refined['quality']
        results.append({
            'id': pid, 'label': label, 'sector': sector,
            'candidates': len(cands),
            'web_usable': q['web_usable_count'],
            'task_usable': q['task_usable_count'],
            'elapsed': round(time.time()-t0, 2),
            'ok': True
        })
    except Exception as e:
        results.append({'id': pid, 'label': label, 'sector': sector,
                        'candidates': 0, 'ok': False, 'error': str(e)[:60]})

# 출력
print(f"{'ID':<4} {'label':<14} {'sector':<14} {'candidates':<11} {'web':<7} {'task':<7} {'elapsed'}")
print('-'*70)
for r in results:
    if r['ok']:
        print(f"{r['id']:<4} {r['label']:<14} {r['sector']:<14} {r['candidates']:<11} {r.get('web_usable','-'):<7} {r.get('task_usable','-'):<7} {r['elapsed']}s")
    else:
        print(f"{r['id']:<4} {r['label']:<14} ERROR: {r.get('error','')}")

# PHASE 5: Sensitivity
print()
print('=== PHASE 5: Sensitivity Audit ===')
SENS_TESTS = [
    ('employee_count', [10, 50, 100, 300, 1000],
     {'sector':'BUILDING','floor_area':2000,'floor_count':5,'elevator_count':1}),
    ('floor_area', [200, 1000, 3000, 5000, 10000],
     {'sector':'BUILDING','employee_count':30,'floor_count':5,'elevator_count':1}),
    ('gas_capacity_m3', [0, 100, 1000, 5000],
     {'sector':'MANUFACTURING','employee_count':30,'is_factory_registered':1,'is_hazardous_material':1,'has_high_pressure_gas':1}),
    ('annual_energy_toe', [0, 500, 2000, 5000],
     {'sector':'BUILDING','employee_count':50,'floor_area':5000,'elevator_count':2}),
]
for field, values, base_inp in SENS_TESTS:
    row = []
    for v in values:
        inp = dict(base_inp); inp[field] = v
        body = type('B',(),{'sector':inp['sector'],
            'worker_count':inp.get('worker_count',10),'employee_count':inp.get('employee_count',10),
            'floor_area':inp.get('floor_area',500),'total_floor_area':inp.get('floor_area',500),
            'electric_capacity':inp.get('electrical_capacity_kw',0),'floor_count':inp.get('floor_count',1),
            'elevator_count':inp.get('elevator_count'),'contract_amount_eok':inp.get('contract_amount_eok'),
            'factory_id':None,'building_use_type':None,'construction_work_type':None,
            'ksic_major':None,'facility_type':None,
            'input':{k:vv for k,vv in inp.items() if k not in ('sector','worker_count','employee_count','floor_area','electrical_capacity_kw','floor_count','elevator_count','contract_amount_eok')}})() 
        try:
            r2 = run_diagnose_step1_v510(sb, body, [inp['sector'],'MANUFACTURING','INDUSTRIAL'], 'v5.10')
            row.append(len(r2['data'].get('candidates',[])))
        except:
            row.append('ERR')
    print(f"  {field}: {list(zip(values, row))}")

json.dump(results, open('/tmp/simulation_results.json','w'), ensure_ascii=False)
print()
print('Done. /tmp/simulation_results.json 저장됨')
