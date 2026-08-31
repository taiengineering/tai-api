# verification/e2e_lifecycle_validator.py
# Phase 10-A — Synthetic Company Lifecycle Validation (E2E)
#
# 검증 흐름:
#   Company 생성 → Factory 생성 → Process 등록 → Equipment 등록
#   → DB 직접 조회 → Condition 변환 → Diagnosis → Candidate → Presentation
#
# 절대 금지: Input Payload 직접 생성 — 반드시 DB 등록 후 조회 사용
#
# 실행: python3 verification/e2e_lifecycle_validator.py [10|30|100]
# 출력: /tmp/validation_run_001.json 등

import os, sys, json, math, uuid
from datetime import datetime
from services.time import now_kst, serialize_business_datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['TAI_USE_RUNTIME_ENGINE'] = 'false'

from supabase import create_client
from services.legal_v510_svc import run_diagnose_step1_v510
from services.code_condition_resolver import build_code_condition_context

sb = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_ROLE_KEY'])

# factories.sector CHECK constraint 허용값:
#   BUILDING, INDUSTRIAL, CONSTRUCTION, SPECIAL_FACILITY, COMMON
# 진단 엔진은 MANUFACTURING을 허용하므로 factory 저장 시에만 INDUSTRIAL로 매핑한다.
FACTORY_SECTOR_MAP = {'MANUFACTURING': 'INDUSTRIAL'}

COMPANY_TEMPLATES = [
    {
        'label': 'Company-MFG-001', 'name': '금속가공_E2E_001',
        'sector': 'MANUFACTURING', 'employee_count': 120, 'floor_area': 5000,
        'electrical_capacity_kw': 500, 'is_hazardous_material': 1, 'has_high_pressure_gas': 0,
        'processes': [
            {'process_id': 'IP000353', 'process_path': '기계제조>가공>절삭>절삭 가공'},
            {'process_id': 'KOSHA-C-108-2017-P001', 'process_path': '마감>용접용단>용접작업>철골/배관 용접'},
        ],
        'equipments': [
            {'equipment_type_code': '021', 'asset_name': '천장크레인_E2E'},
            {'equipment_type_code': '027', 'asset_name': '고압가스저장탱크_E2E'},
        ],
        'work_types': [], 'contract_amount_eok': None,
    },
    {
        'label': 'Company-MFG-002', 'name': '화학공장_E2E_002',
        'sector': 'MANUFACTURING', 'employee_count': 80, 'floor_area': 3000,
        'electrical_capacity_kw': 300, 'is_hazardous_material': 1, 'has_high_pressure_gas': 1,
        'gas_capacity_kg': 500,
        'processes': [
            {'process_id': 'IP000563', 'process_path': '공정제조>가공>혼합·용해>혼합 및 용해'},
            {'process_id': 'IP000566', 'process_path': '공정제조>포장>충전>충전 및 포장'},
        ],
        'equipments': [
            {'equipment_type_code': '028', 'asset_name': 'LPG저장탱크_E2E'},
            {'equipment_type_code': 'PRESSURE_VESSEL', 'asset_name': '압력용기_E2E'},
        ],
        'work_types': [], 'contract_amount_eok': None,
    },
    {
        'label': 'Company-MFG-003', 'name': '식품공장_E2E_003',
        'sector': 'MANUFACTURING', 'employee_count': 50, 'floor_area': 2000,
        'electrical_capacity_kw': 200, 'is_hazardous_material': 0, 'has_high_pressure_gas': 0,
        'processes': [
            {'process_id': 'IP000542', 'process_path': '공정제조>유틸리티>가열·냉각>열교환 및 냉각'},
            {'process_id': 'IP000566', 'process_path': '공정제조>포장>충전>충전 및 포장'},
        ],
        'equipments': [
            {'equipment_type_code': '014', 'asset_name': '보일러_E2E'},
            {'equipment_type_code': '019', 'asset_name': '냉동설비_E2E'},
        ],
        'work_types': [], 'contract_amount_eok': None,
    },
    {
        'label': 'Company-BLD-001', 'name': '오피스빌딩_E2E_001',
        'sector': 'BUILDING', 'employee_count': 200, 'floor_area': 15000,
        'electrical_capacity_kw': 1000, 'is_hazardous_material': 0, 'has_high_pressure_gas': 0,
        'elevator_count': 4, 'annual_energy_toe': 2000, 'is_multi_use': 1,
        'processes': [],
        'equipments': [
            {'equipment_type_code': '001', 'asset_name': '수전변압기_E2E'},
            {'equipment_type_code': '025', 'asset_name': '승강기_E2E'},
            {'equipment_type_code': '031', 'asset_name': '스프링클러_E2E'},
        ],
        'work_types': [], 'contract_amount_eok': None,
    },
    {
        'label': 'Company-BLD-002', 'name': '물류센터_E2E_002',
        'sector': 'BUILDING', 'employee_count': 150, 'floor_area': 50000,
        'electrical_capacity_kw': 2000, 'is_hazardous_material': 0, 'has_high_pressure_gas': 0,
        'elevator_count': 2, 'annual_energy_toe': 5000, 'is_multi_use': 0,
        'processes': [],
        'equipments': [
            {'equipment_type_code': 'CONVEYOR', 'asset_name': '컨베이어_E2E'},
            {'equipment_type_code': '025', 'asset_name': '화물승강기_E2E'},
            {'equipment_type_code': '001', 'asset_name': '수전설비_E2E'},
        ],
        'work_types': [], 'contract_amount_eok': None,
    },
    {
        'label': 'Company-CON-001', 'name': '철골공사_E2E_001',
        'sector': 'CONSTRUCTION', 'employee_count': 80, 'floor_area': 10000,
        'electrical_capacity_kw': 300, 'is_hazardous_material': 0, 'has_high_pressure_gas': 0,
        'contract_amount_eok': 100, 'construction_type': '건축공사',
        'direct_workers': 30, 'subcon_workers': 50,
        'processes': [
            {'process_id': 'CP057', 'process_path': '건설>철골>철골설치>철골 반입'},
            {'process_id': 'CP053', 'process_path': '건설>철골>철골제작>철골 가공'},
        ],
        'equipments': [
            {'equipment_type_code': 'CRANE', 'asset_name': '타워크레인_E2E'},
        ],
        'work_types': ['all_construction', 'NEW_CONSTRUCTION'],
    },
    {
        'label': 'Company-CON-002', 'name': '플랜트공사_E2E_002',
        'sector': 'CONSTRUCTION', 'employee_count': 200, 'floor_area': 30000,
        'electrical_capacity_kw': 1000, 'is_hazardous_material': 1, 'has_high_pressure_gas': 1,
        'gas_capacity_kg': 1000, 'contract_amount_eok': 300,
        'construction_type': '플랜트', 'direct_workers': 80, 'subcon_workers': 120,
        'processes': [
            {'process_id': 'KOSHA-C-108-2017-P001', 'process_path': '마감>용접용단>용접작업>철골/배관 용접'},
            {'process_id': 'CP170', 'process_path': '건설>가스>가스배관>가스배관 설치'},
        ],
        'equipments': [
            {'equipment_type_code': '021', 'asset_name': '크레인_E2E'},
            {'equipment_type_code': '027', 'asset_name': '고압가스설비_E2E'},
        ],
        'work_types': ['all_construction', 'FLAMMABLE_GAS_WORK'],
    },
]


def step_create_company(tmpl):
    try:
        res = sb.table('companies').insert({'name': tmpl['name'], 'business_type': tmpl['sector'], 'is_active': True}).execute()
        return (res.data[0]['id'], 'PASS') if res.data else (None, 'FAIL:no_data')
    except Exception as e:
        return None, f'FAIL:{str(e)[:60]}'


def step_create_factory(tmpl, company_id):
    try:
        # factories.sector check constraint 충족 — MANUFACTURING→INDUSTRIAL (저장 시에만)
        factory_sector = FACTORY_SECTOR_MAP.get(tmpl['sector'], tmpl['sector'])
        res = sb.table('factories').insert({
            'company_id': company_id, 'name': tmpl['name'], 'sector': factory_sector,
            'employee_count': tmpl['employee_count'], 'electrical_capacity_kw': tmpl['electrical_capacity_kw'],
            'is_active': True,
        }).execute()
        return (res.data[0]['id'], 'PASS') if res.data else (None, 'FAIL:no_data')
    except Exception as e:
        return None, f'FAIL:{str(e)[:60]}'


def step_register_processes(tmpl, factory_id):
    if not tmpl.get('processes'):
        return [], 'PASS:empty'
    try:
        rows = [{'factory_id': factory_id, 'process_id': p['process_id'],
                 'process_path': p['process_path'], 'is_active': True,
                 'is_primary': False, 'source': 'E2E_TEST'} for p in tmpl['processes']]
        res = sb.table('factory_process').insert(rows).execute()
        return ([r['process_id'] for r in res.data], 'PASS') if res.data else ([], 'FAIL:no_data')
    except Exception as e:
        return [], f'FAIL:{str(e)[:60]}'


def step_register_equipments(tmpl, factory_id):
    if not tmpl.get('equipments'):
        return [], 'PASS:empty'
    try:
        rows = [{'factory_id': factory_id, 'equipment_type_code': eq['equipment_type_code'],
                 'asset_name': eq['asset_name'], 'is_operating': True, 'is_legal_target': True}
                for eq in tmpl['equipments']]
        res = sb.table('equipment_assets').insert(rows).execute()
        return ([r['equipment_type_code'] for r in res.data], 'PASS') if res.data else ([], 'FAIL:no_data')
    except Exception as e:
        return [], f'FAIL:{str(e)[:60]}'


def step_query_from_db(factory_id):
    """절대 금지: Input Payload 직접 생성. 반드시 DB 조회."""
    try:
        proc_res = sb.table('factory_process').select('process_id,process_path').eq('factory_id', factory_id).eq('is_active', True).execute()
        eq_res = sb.table('equipment_assets').select('equipment_type_code').eq('factory_id', factory_id).eq('is_operating', True).execute()
        proc_rows = proc_res.data or []
        eq_rows = eq_res.data or []
        queried_procs = [{'process_id': r['process_id'], 'process_path': r.get('process_path', '')} for r in proc_rows if r.get('process_id')]
        queried_codes = list({r['equipment_type_code'] for r in eq_rows if r.get('equipment_type_code')})
        return queried_procs, queried_codes, 'PASS'
    except Exception as e:
        return [], [], f'FAIL:{str(e)[:60]}'


def step_run_diagnosis(tmpl, factory_id, queried_processes, queried_eq_codes):
    sector = tmpl['sector']
    inp = {
        'employee_count': tmpl['employee_count'],
        'floor_area': tmpl['floor_area'],
        'electrical_capacity_kw': tmpl['electrical_capacity_kw'],
        'is_hazardous_material': tmpl.get('is_hazardous_material', 0),
        'has_high_pressure_gas': tmpl.get('has_high_pressure_gas', 0),
        'gas_capacity_kg': tmpl.get('gas_capacity_kg', 0),
        'elevator_count': tmpl.get('elevator_count', 0),
        'annual_energy_toe': tmpl.get('annual_energy_toe', 0),
        'is_multi_use': tmpl.get('is_multi_use', 0),
    }
    if tmpl.get('contract_amount_eok'):
        inp['contract_amount_eok'] = tmpl['contract_amount_eok']

    body = type('B', (), {
        'sector': sector, 'factory_id': factory_id,
        'worker_count': tmpl['employee_count'], 'employee_count': tmpl['employee_count'],
        'floor_area': tmpl['floor_area'], 'total_floor_area': tmpl['floor_area'],
        'electric_capacity': tmpl['electrical_capacity_kw'], 'floor_count': 2,
        'elevator_count': tmpl.get('elevator_count') or None,
        'contract_amount_eok': tmpl.get('contract_amount_eok'),
        'construction_type': tmpl.get('construction_type'),
        'direct_workers': tmpl.get('direct_workers'),
        'subcon_workers': tmpl.get('subcon_workers'),
        'building_use_type': None, 'construction_work_type': None,
        'ksic_major': None, 'facility_type': None, 'input': inp,
    })()

    try:
        r = run_diagnose_step1_v510(sb, body, [sector, 'MANUFACTURING', 'INDUSTRIAL', 'BUILDING'], 'v5.10')
        data = r['data']
        candidates = data.get('candidates', [])
        presentation = data.get('presentation', {})
        meta = presentation.get('metadata', {})

        # Condition: DB 조회 데이터 기반 (직접 생성 금지)
        condition_ctx = build_code_condition_context(
            processes=queried_processes,
            equipments=queried_eq_codes,
            work_types=tmpl.get('work_types', []),
            supabase=sb,
        )
        return {
            'candidate_count': len(candidates),
            'display_count': meta.get('display_count', 0),
            'reduction_rate': meta.get('reduction_rate', 0),
            'condition_ctx': condition_ctx,
            'presentation_meta': meta,
            'input_snapshot': inp,
        }, 'PASS'
    except Exception as e:
        return {}, f'FAIL:{str(e)[:80]}'


def cleanup(company_id, factory_id):
    try:
        if factory_id:
            sb.table('factory_process').delete().eq('factory_id', factory_id).eq('source', 'E2E_TEST').execute()
            sb.table('equipment_assets').delete().eq('factory_id', factory_id).execute()
            sb.table('factories').delete().eq('id', factory_id).execute()
        if company_id:
            sb.table('companies').delete().eq('id', company_id).execute()
    except Exception:
        pass


def run_wave(wave_n, templates, run_label, out_path):
    print(f'\n=== Phase 10-A: {run_label} ({wave_n}개 Company) ===')
    run_res = sb.table('synthetic_company_runs').insert({
        'run_label': run_label, 'company_count': wave_n,
        'meta': {'wave': wave_n, 'started_at': serialize_business_datetime(now_kst())},
    }).execute()
    run_id = run_res.data[0]['id'] if run_res.data else str(uuid.uuid4())

    results = []
    pass_count = fail_count = 0
    cat = {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'E': 0, 'F': 0}

    for i, tmpl in enumerate(templates[:wave_n]):
        print(f'\n  [{i+1:>3}/{wave_n}] {tmpl["label"]}')
        company_id = factory_id = None
        res = {'company_label': tmpl['label'], 'sector': tmpl['sector'],
               'pass_company': False, 'pass_factory': False, 'pass_process': False,
               'pass_condition': False, 'pass_rule': False, 'pass_candidate': False,
               'pass_presentation': False, 'failure_category': None, 'error_message': None}

        # Step 1
        company_id, s = step_create_company(tmpl)
        res['pass_company'] = s == 'PASS'
        if not res['pass_company']:
            res.update({'failure_category': 'A', 'error_message': s})
            cat['A'] += 1; fail_count += 1
            print(f'      ❌ Company: {s}')
            results.append(res); continue
        print(f'      ✅ Company: {company_id}')

        # Step 2
        factory_id, s = step_create_factory(tmpl, company_id)
        res['pass_factory'] = s == 'PASS'
        if not res['pass_factory']:
            res.update({'failure_category': 'A', 'error_message': s})
            cat['A'] += 1; fail_count += 1
            cleanup(company_id, None)
            print(f'      ❌ Factory: {s}')
            results.append(res); continue
        print(f'      ✅ Factory: {factory_id}')

        # Step 3
        saved_pids, s = step_register_processes(tmpl, factory_id)
        res['process_ids'] = saved_pids
        if not s.startswith('PASS'):
            res.update({'failure_category': 'A', 'error_message': s})
            cat['A'] += 1; fail_count += 1
            cleanup(company_id, factory_id)
            print(f'      ❌ Process: {s}')
            results.append(res); continue
        print(f'      ✅ Process 등록: {len(saved_pids)}개')

        # Step 4
        saved_codes, s = step_register_equipments(tmpl, factory_id)
        res['equipment_type_codes'] = saved_codes
        if not s.startswith('PASS'):
            res.update({'failure_category': 'A', 'error_message': s})
            cat['A'] += 1; fail_count += 1
            cleanup(company_id, factory_id)
            print(f'      ❌ Equipment: {s}')
            results.append(res); continue
        print(f'      ✅ Equipment 등록: {len(saved_codes)}개')

        # Step 5: DB 조회 (직접 생성 금지)
        q_procs, q_codes, s = step_query_from_db(factory_id)
        res['pass_process'] = s.startswith('PASS')
        if not res['pass_process']:
            res.update({'failure_category': 'B', 'error_message': s})
            cat['B'] += 1; fail_count += 1
            cleanup(company_id, factory_id)
            print(f'      ❌ DB 조회: {s}')
            results.append(res); continue
        print(f'      ✅ DB 조회: proc={len(q_procs)} equip={len(q_codes)}')

        # Step 6: Diagnosis
        diag, s = step_run_diagnosis(tmpl, factory_id, q_procs, q_codes)
        if s != 'PASS':
            res.update({'failure_category': 'D', 'error_message': s})
            cat['D'] += 1; fail_count += 1
            cleanup(company_id, factory_id)
            print(f'      ❌ Diagnosis: {s}')
            results.append(res); continue

        cond_ctx = diag.get('condition_ctx', {})
        cand_n = diag.get('candidate_count', 0)
        disp_n = diag.get('display_count', 0)
        has_proc = bool(tmpl.get('processes'))

        res.update({
            'pass_condition': len(cond_ctx) > 0 or not has_proc,
            'pass_rule': cand_n > 0,
            'pass_candidate': cand_n > 0,
            'pass_presentation': disp_n > 0,
            'candidate_count': cand_n,
            'display_count': disp_n,
            'reduction_rate': diag.get('reduction_rate', 0),
            'condition_ctx': cond_ctx,
            'input_snapshot': diag.get('input_snapshot', {}),
            'presentation_meta': diag.get('presentation_meta', {}),
        })

        if not res['pass_condition'] and has_proc: res['failure_category'] = 'C'; cat['C'] += 1
        elif not res['pass_rule']: res['failure_category'] = 'D'; cat['D'] += 1
        elif not res['pass_candidate']: res['failure_category'] = 'E'; cat['E'] += 1
        elif not res['pass_presentation']: res['failure_category'] = 'F'; cat['F'] += 1

        all_pass = all([res['pass_company'], res['pass_factory'], res['pass_process'],
                        res['pass_rule'], res['pass_candidate'], res['pass_presentation']])
        if all_pass:
            pass_count += 1
            print(f'      ✅ ALL PASS — cand={cand_n} disp={disp_n} cond={list(cond_ctx.keys())[:4]}')
        else:
            fail_count += 1
            print(f'      ⚠️  PARTIAL — cat={res["failure_category"]} cand={cand_n} cond={len(cond_ctx)}')

        try:
            sb.table('synthetic_company_results').insert({
                'run_id': run_id, 'company_id': company_id, 'factory_id': factory_id,
                'company_label': res['company_label'], 'sector': res['sector'],
                'process_ids': res.get('process_ids', []),
                'equipment_type_codes': res.get('equipment_type_codes', []),
                'construction_work_types': tmpl.get('work_types', []),
                'candidate_count': res.get('candidate_count'),
                'display_count': res.get('display_count'),
                'reduction_rate': res.get('reduction_rate'),
                'condition_ctx': res.get('condition_ctx', {}),
                'pass_company': res['pass_company'], 'pass_factory': res['pass_factory'],
                'pass_process': res['pass_process'], 'pass_condition': res.get('pass_condition', False),
                'pass_rule': res.get('pass_rule', False), 'pass_candidate': res.get('pass_candidate', False),
                'pass_presentation': res.get('pass_presentation', False),
                'failure_category': res.get('failure_category'),
                'input_snapshot': res.get('input_snapshot', {}),
                'presentation_meta': res.get('presentation_meta', {}),
            }).execute()
        except Exception as e:
            print(f'      ⚠️  결과 저장 실패: {str(e)[:60]}')

        cleanup(company_id, factory_id)
        results.append(res)

    report = {
        'run_id': run_id, 'run_label': run_label, 'wave': wave_n,
        'executed_at': serialize_business_datetime(now_kst()),
        'summary': {
            'company_count': wave_n, 'pass_count': pass_count, 'fail_count': fail_count,
            'pass_rate': round(pass_count / wave_n * 100, 1) if wave_n else 0,
            'failure_categories': cat,
        },
        'results': results,
    }
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f'\n=== {run_label} 완료 ===')
    print(f'  PASS: {pass_count}/{wave_n} ({report["summary"]["pass_rate"]}%)')
    print(f'  FAIL: {fail_count}/{wave_n}  Failure: {cat}')
    print(f'  저장: {out_path}')
    return report


if __name__ == '__main__':
    wave = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    if wave <= len(COMPANY_TEMPLATES):
        tpls = COMPANY_TEMPLATES[:wave]
    else:
        tpls = (COMPANY_TEMPLATES * math.ceil(wave / len(COMPANY_TEMPLATES)))[:wave]
    run_no = '001' if wave == 10 else ('002' if wave == 30 else '003')
    run_wave(wave, tpls, f'wave_{wave}', f'/tmp/validation_run_{run_no}.json')
