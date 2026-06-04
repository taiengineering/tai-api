# -*- coding: utf-8 -*-
# 2-2단계: 조건 Coverage 확보 — v2 → v3
# 법령분석/검증/Check/정제/평가 없음. 조건 어휘 포함여부 식별 + 부족분 보강만.
#
# 파이프라인: gen.py(v1 골격) → enrich.py(v2 상세) → cov.py(v3 Coverage 보강)
# resolver 키 정확일치 process_id/equipment_code만 주입 (code_condition_resolver 엔진 어휘 준수)
#
# 실행: python3 verification/datasets/cov.py  (결과: e2e_verification_dataset_v3.json)
import json
from collections import OrderedDict

v2 = json.load(open('e2e_verification_dataset_v2.json'))
rows = v2['rows']
byid = {r['dataset_id']: r for r in rows}

# ── 조건 어휘 매핑 (code_condition_resolver / condition_normalizer 기준) ──
# process_id → condition_code (DB process_lv3 실값 → resolver 매핑 결과)
PROC_COND = {
  'IP000353': None,        # 절삭 (매핑없음)
  'KOSHA-C-108-2017-P001': None,  # 용접작업 (매핑없음)
  'IP000563': None,        # 혼합·용해 (매핑없음)
  'IP000566': None,        # 충전 (매핑없음)
  'IP000542': 'has_heat_treatment',  # 가열·냉각
  'CP057': None,           # 철골설치 (매핑없음)
  'CP053': None,           # 철골제작 (매핑없음)
  'CP170': 'has_gas_piping',  # 가스배관
  # v3 보강 (resolver 키 정확일치)
  'IP000356': 'has_welding', 'IP000005': 'has_cutting', 'IP001108': 'has_painting',
  'IP000782': 'has_plating', 'KOSHA-M-56-2020-P002': 'has_injection',
  'IP000781': 'has_heat_treatment', 'IP000564': 'has_chemical_reaction',
  'CP122': 'has_piping', 'CP042': 'has_formwork', 'CP006': 'has_excavation',
  'CP192': 'has_demolition', 'CP196': 'has_tunnel',
}
EQ_COND = {
  '001':'has_transformer','010':'has_generator','014':'has_boiler','019':'has_refrigeration',
  '021':'has_crane','023':'has_press','025':'has_elevator','027':'has_high_pressure_gas',
  '028':'has_lpg_storage','029':'has_hazardous_material_facility','030':'has_hazardous_storage',
  '031':'has_sprinkler','CONVEYOR':'has_conveyor','CRANE':'has_crane','PRESSURE_VESSEL':'has_pressure_vessel',
}
WORK_COND = {
  '철골공사':'construction_steel','고소작업':'construction_high_work','양중':'construction_lifting',
  '화기작업':'construction_fire_work','비계':'construction_scaffold','굴착':'construction_excavation',
  '토목공사':'construction_civil','건축공사':'construction_building','해체공사':'construction_demolition',
  '해체':'construction_demolition','터널공사':'construction_tunnel','발파':'construction_blasting',
  '전기공사':'construction_electrical','교량공사':'construction_bridge',
}
EQ_LABEL = {'010':'비상발전기','023':'프레스'}

def add_proc(did, pid):
    r=byid[did]
    if pid not in [p['process_id'] for p in r['processes']]: r['processes'].append({'process_id':pid})
def add_eq(did, code):
    r=byid[did]
    if code not in [e['equipment_type_code'] for e in r['equipments']]:
        r['equipments'].append({'equipment_type_code':code,'asset_name':EQ_LABEL.get(code,code)})
def add_work(did, w):
    r=byid[did]
    if w not in r['work_types']: r['work_types'].append(w)

# ── v3 보강: 부족 조건을 기존 사업장에 현실적으로 주입 ──
add_proc('IND-016','IP000356'); add_proc('IND-001','IP000005')
add_proc('IND-005','IP001108'); add_eq('IND-005','023')
add_proc('IND-011','IP000782'); add_proc('IND-007','KOSHA-M-56-2020-P002')
add_proc('IND-006','IP000781'); add_proc('IND-002','IP000564')
add_proc('CON-014','CP122'); add_proc('CON-003','CP042'); add_proc('CON-004','CP006')
add_proc('CON-010','CP196'); add_proc('CON-009','CP192'); add_work('CON-013','전기공사')
add_eq('BLD-010','010'); add_eq('BLD-005','010')

# ── 전체 Dataset이 생성하는 condition_code 집합 ──
present = set()
for r in rows:
    for p in r['processes']:
        c = PROC_COND.get(p['process_id']);  present.add(c) if c else None
    for e in r['equipments']:
        c = EQ_COND.get(e['equipment_type_code']);  present.add(c) if c else None
    for w in r['work_types']:
        c = WORK_COND.get(w);  present.add(c) if c else None
    if r['input'].get('is_hazardous_material') or r['input'].get('gas_capacity_kg',0)>0:
        present.add('is_hazardous_material')

REQUIRED = OrderedDict([
 ('[산업] 용접','has_welding'),('[산업] 절단','has_cutting'),('[산업] 도장','has_painting'),
 ('[산업] 도금','has_plating'),('[산업] 사출','has_injection'),('[산업] 열처리','has_heat_treatment'),
 ('[산업] 프레스','has_press'),('[산업] 압축기','has_compressor'),('[산업] 보일러','has_boiler'),
 ('[산업] 압력용기','has_pressure_vessel'),('[산업] 크레인','has_crane'),('[산업] 지게차','has_forklift'),
 ('[산업] 냉동설비','has_refrigeration'),('[산업] 고압가스','has_high_pressure_gas'),
 ('[건설] 굴착','construction_excavation'),('[건설] 철골','construction_steel'),
 ('[건설] 고소작업','construction_high_work'),('[건설] 해체','construction_demolition'),
 ('[건설] 터널','construction_tunnel'),('[건설] 배관','has_piping'),
 ('[건설] 전기','construction_electrical'),('[건설] 기계설비','construction_machinery'),
 ('[건설] 거푸집','has_formwork'),('[건설] 비계','construction_scaffold'),
 ('[특수] LPG','has_lpg_storage'),('[특수] 위험물저장','has_hazardous_storage'),
 ('[특수] 주유취급','has_high_pressure_gas'),('[특수] 가스충전','has_high_pressure_gas'),
 ('[특수] 폐기물소각','has_hazardous_material_facility'),('[특수] 냉동창고','has_refrigeration'),
 ('[건물] 수전설비','has_transformer'),('[건물] 비상발전기','has_generator'),
 ('[건물] 승강기','has_elevator'),('[건물] 소방설비','has_sprinkler'),
 ('[건물] 냉동기','has_refrigeration'),('[건물] 보일러','has_boiler'),
])
ENGINE_GAP = {'has_compressor','has_forklift','construction_machinery'}  # resolver 매핑 부재 (엔진 영역)

covered=sum(1 for cc in REQUIRED.values() if cc in present)
for r in rows:
    eqs=[e['equipment_type_code'] for e in r['equipments']]
    FAC={'001','025','026','027','028','029','030','031','032','033','034','037','039'}
    MAC={'008','010','011','012','013','014','015','016','017','018','019','021','023','024','036','040','CRANE','CONVEYOR','PRESS','PRESSURE_VESSEL'}
    r['_counts']={'facility':len(set(c for c in eqs if c in FAC))+1,'process':len(r['processes']),
                  'equipment':len(set(c for c in eqs if c in MAC)),'work':len(r['work_types']),
                  'hazmat':len(r.get('hazmat_handling',[]))}

v3={'version':'v3','generated':'2026-06-02',
    'description':'2-2단계: 조건 Coverage 보강. resolver 키 정확일치 process_id/equipment_code 주입으로 법령엔진 소비조건 확보.',
    'total':len(rows),'sector_distribution':v2['sector_distribution'],
    'coverage_present_conditions':sorted(present),
    'coverage_summary':{'required':len(REQUIRED),'covered':covered,'engine_gap':len(ENGINE_GAP)},
    'rows':rows}
json.dump(v3,open('e2e_verification_dataset_v3.json','w'),ensure_ascii=False,indent=2)
print('covered',covered,'/',len(REQUIRED),'| present',len(present))
