# verification/verify_mapping.py
# Input Mapping Closure 검증 스크립트
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.input_normalizer import normalize_input

FULL_INPUT = {
    'floor_area': 500, 'total_floor_area': 500, 'floor_count': 3,
    'elevator_count': 2, 'is_multi_use': 1, 'annual_energy_toe': 1000,
    'building_grade': 1, 'employee_count': 10, 'worker_count': 10,
    'is_factory_registered': 1, 'is_hazardous_material': 1,
    'electric_capacity': 200, 'gas_capacity_m3': 50, 'gas_capacity_kg': 100,
    'has_high_pressure_gas': 1, 'has_chemical_substance': 1,
    'has_boiler': 1, 'boiler_capacity_kw': 150, 'has_pressure_chamber': 1,
    'contract_amount_eok': 50, 'construction_amount': 5000000000,
    'is_construction_site': 1, 'TUNNEL_LENGTH': 600,
    'hospital_beds': 0, 'student_count': 0, 'contractor_count': 0,
    'water_capacity_m3': 0, 'registration_required': 1,
    'manufacturing_business': 1, 'business_start_date': '2020-01-01',
}

# 엔진이 실제로 조회하는 condition_code (3건 이상)
CONDITION_CODES = [
    'is_hazardous_material',     # 340건
    'building_area',             # 127건
    'employee_count',            # 119건
    'gas_capacity_kg',           # 112건
    'has_high_pressure_gas',     # 70건
    'contract_amount',           # 65건
    'has_chemical_substance',    # 64건
    'elevator_count',            # 59건
    'is_factory_registered',     # 53건
    'is_multi_use',              # 43건
    'electrical_capacity_kw',    # 38건
    'electric_capacity',         # 11건 (역방향 alias 보장 필요)
    'construction_amount',       # 35건
    'gas_capacity_m3',           # 31건
    'floor_count',               # 27건
    'annual_energy_toe',         # 24건
    'worker_count',              # 22건
    'building_grade',            # 13건
    'boiler_capacity_kw',        # 7건
    'is_construction_site',      # 7건
    'has_boiler',                # 5건
    'hospital_beds',             # 5건
    'manufacturing_business',    # 5건
    'business_start_date',       # 5건
    'TUNNEL_LENGTH',             # 4건
    'registration_required',     # 4건
    'student_count',             # 4건
    'has_pressure_chamber',      # 3건
    'contractor_count',          # 3건
    'water_capacity_m3',         # 3건
    'FLOOR_AREA',                # 2건 (대문자)
    'FLOOR_COUNT',               # 2건 (대문자)
]

norm = normalize_input(FULL_INPUT)

passed = [c for c in CONDITION_CODES if c in norm]
failed = [c for c in CONDITION_CODES if c not in norm]

print(f'PASS: {len(passed)}/{len(CONDITION_CODES)}')
print(f'FAIL: {failed if failed else "없음"}')
print()
print('[alias 검증]')
print(f'electric_capacity:    {norm.get("electric_capacity")}')
print(f'electrical_capacity_kw: {norm.get("electrical_capacity_kw")}')
print(f'building_area:        {norm.get("building_area")}')
print(f'FLOOR_AREA:           {norm.get("FLOOR_AREA")}')
print(f'FLOOR_COUNT:          {norm.get("FLOOR_COUNT")}')
print(f'contract_amount:      {norm.get("contract_amount")}')
print()
if not failed:
    print('CLOSURE: PASS -- 모든 condition_code 매핑 완료')
else:
    print(f'CLOSURE: FAIL -- {len(failed)}개 미해결')
