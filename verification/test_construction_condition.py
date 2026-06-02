# verification/test_construction_condition.py
# Phase 7-C: 건설 Condition Recovery 검증
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['TAI_USE_RUNTIME_ENGINE'] = 'false'

from services.legal_v510_svc import _apply_construction_conditions

# 검증 1: contract_amount_eok=50억 → 50억원 = 5,000,000,000원
body = type('B', (), {
    'contract_amount_eok': 50,
    'construction_type': '건축공사',
    'direct_workers': 20,
    'subcon_workers': 30,
})()
inp = {}
_apply_construction_conditions(inp, body, 'CONSTRUCTION')
assert inp['contract_amount'] == 5_000_000_000, f"FAIL contract_amount: {inp.get('contract_amount')}"
assert inp['construction_amount'] == 5_000_000_000, f"FAIL construction_amount: {inp.get('construction_amount')}"
assert inp['is_construction_site'] == 1, f"FAIL is_construction_site: {inp.get('is_construction_site')}"
assert inp['contract_amount_eok'] == 50
assert inp['construction_type'] == '건축공사'
print('Case1 PASS: contract_amount_eok=50 → contract_amount=5,000,000,000')

# 검증 2: MANUFACTURING 섹터는 적용 안 됨
body2 = type('B', (), {'contract_amount_eok': 100, 'construction_type': None, 'direct_workers': None, 'subcon_workers': None})()
inp2 = {}
_apply_construction_conditions(inp2, body2, 'MANUFACTURING')
assert 'contract_amount' not in inp2, "FAIL: MANUFACTURING에 contract_amount 생겼다"
assert 'is_construction_site' not in inp2
print('Case2 PASS: MANUFACTURING sector → 어떤 Condition도 주입 안 됨')

# 검증 3: contract_amount_eok=None, inp에 직접 원화 입력 시
body3 = type('B', (), {'contract_amount_eok': None, 'construction_type': None, 'direct_workers': None, 'subcon_workers': None})()
inp3 = {'contract_amount': 10_000_000_000}  # 직접 원화 입력
_apply_construction_conditions(inp3, body3, 'CONSTRUCTION')
assert inp3['contract_amount'] == 10_000_000_000
assert inp3['construction_amount'] == 10_000_000_000
assert inp3['is_construction_site'] == 1
print('Case3 PASS: inp에 직접 원화 입력 시 construction_amount 동기화')

# 검증 4: Rule 조건 시뮬레이션 (condition_code 매칭)
from services.legal_rules import _check_rule_conditions
rule_contract = {'condition_code': 'contract_amount', 'condition_value': 5_000_000_000, 'condition_operator_code': 'gte'}
ctx = {'contract_amount': 5_000_000_000, 'is_construction_site': 1}
assert _check_rule_conditions(rule_contract, ctx) == True, 'FAIL: contract_amount Rule 미적용'
print('Case4 PASS: contract_amount>=5억 Rule 적용 확인')

rule_construction = {'condition_code': 'construction_amount', 'condition_value': 5_000_000_000, 'condition_operator_code': 'gte'}
ctx2 = {'construction_amount': 5_000_000_000}
assert _check_rule_conditions(rule_construction, ctx2) == True, 'FAIL: construction_amount Rule 미적용'
print('Case5 PASS: construction_amount>=5억 Rule 적용 확인')

rule_site = {'condition_code': 'is_construction_site', 'condition_value': 1, 'condition_operator_code': 'gte'}
ctx3 = {'is_construction_site': 1}
assert _check_rule_conditions(rule_site, ctx3) == True, 'FAIL: is_construction_site Rule 미적용'
print('Case6 PASS: is_construction_site=1 Rule 적용 확인')

print()
print('ALL PASS (6/6) -- Phase 7-C Construction Condition Recovery')
