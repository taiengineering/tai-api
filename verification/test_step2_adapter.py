# verification/test_step2_adapter.py
# Step2 Condition->Rule Adapter 검증
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.legal_v510_svc import (
    _equipment_rule_match,
    _work_type_rule_match,
    _evaluate_step2_rule,
)

# Case 1: equipment_type_code=021, input에 021 있음 → 적용
rule_crane = {"equipment_type_code": "021", "condition_code": None, "construction_work_type": None}
input_with_021 = {"equipment_type_codes": ["021", "025"], "construction_work_types": []}
assert _equipment_rule_match(rule_crane, input_with_021) == True, "Case1 FAIL"
print("Case1 PASS: equipment_type_code=021, input [021,025] → 적용")

# Case 2: equipment_type_code=021, input에 025만 → 미적용
input_with_025 = {"equipment_type_codes": ["025"], "construction_work_types": []}
assert _equipment_rule_match(rule_crane, input_with_025) == False, "Case2 FAIL"
print("Case2 PASS: equipment_type_code=021, input [025] → 미적용")

# Case 3: equipment_type_code 없는 Rule → 항상 통과
rule_no_equip = {"equipment_type_code": None, "condition_code": None, "construction_work_type": None}
assert _equipment_rule_match(rule_no_equip, input_with_025) == True, "Case3 FAIL"
print("Case3 PASS: equipment_type_code 없음 → 항상 통과")

# Case 4: construction_work_type=철골공사, input에 철골공사 있음 → 적용
rule_steel = {"equipment_type_code": None, "condition_code": None, "construction_work_type": "철골공사"}
input_steel = {"equipment_type_codes": [], "construction_work_types": ["철골공사", "토목공사"]}
assert _work_type_rule_match(rule_steel, input_steel) == True, "Case4 FAIL"
print("Case4 PASS: construction_work_type=철골공사, input [철골공사,토목공사] → 적용")

# Case 5: construction_work_type=철골공사, input에 없음 → 미적용
input_no_steel = {"equipment_type_codes": [], "construction_work_types": ["토목공사"]}
assert _work_type_rule_match(rule_steel, input_no_steel) == False, "Case5 FAIL"
print("Case5 PASS: construction_work_type=철골공사, input [토목공사] → 미적용")

# Case 6: 복합 -- condition_code 없고 equipment_type_code=021, 입력에 021 → 적용
rule_combined = {"equipment_type_code": "021", "condition_code": None, "condition_value": None, "construction_work_type": None}
assert _evaluate_step2_rule(rule_combined, input_with_021) == True, "Case6 FAIL"
print("Case6 PASS: 콤디션없음+equipment=021 → 적용")

# Case 7: condition_code 있고 context에 없음 → 미적용
rule_with_condition = {"equipment_type_code": None, "condition_code": "employee_count",
                       "condition_value": 50, "condition_operator_code": "gte",
                       "construction_work_type": None}
ctx_no_employee = {"equipment_type_codes": [], "construction_work_types": []}
assert _evaluate_step2_rule(rule_with_condition, ctx_no_employee) == False, "Case7 FAIL"
print("Case7 PASS: condition_code=employee_count>=50, context에 없음 → 미적용")

# Case 8: condition_code 있고 context에 있고 조건 충족 → 적용
ctx_with_employee = {"employee_count": 100, "equipment_type_codes": [], "construction_work_types": []}
assert _evaluate_step2_rule(rule_with_condition, ctx_with_employee) == True, "Case8 FAIL"
print("Case8 PASS: condition_code=employee_count>=50, context=100 → 적용")

print()
print("ALL PASS (8/8) -- condition_1_field 의존성 제거")
