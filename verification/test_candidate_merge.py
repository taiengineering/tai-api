# verification/test_candidate_merge.py
# Phase 6: Candidate Integration 검증
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.legal_v510_svc import _merge_candidates

# Case 1: 동일 rule_id → merged 1건 (Step1 우선)
s1 = [{"candidate_id": "R100", "source_type": "APPOINT", "law_name": "Step1에서"}]
s2 = [{"candidate_id": "R100", "source_type": "APPOINT", "law_name": "Step2에서"}]
merged = _merge_candidates(s1, s2)
assert len(merged) == 1, f"Case1 FAIL: {len(merged)}"
assert merged[0]["law_name"] == "Step1에서", "Case1 Step1 우선 FAIL"
print("Case1 PASS: R100+R100 → 1건 (Step1 우선)")

# Case 2: 다른 rule_id → merged 2건
s1 = [{"candidate_id": "R100", "source_type": "APPOINT"}]
s2 = [{"candidate_id": "R200", "source_type": "INSPECT"}]
merged = _merge_candidates(s1, s2)
assert len(merged) == 2, f"Case2 FAIL: {len(merged)}"
print("Case2 PASS: R100+R200 → 2건")

# Case 3: Step1 없음 + Step2만 → Step2 전체
s1 = []
s2 = [{"candidate_id": "R300"}, {"candidate_id": "R400"}]
merged = _merge_candidates(s1, s2)
assert len(merged) == 2, f"Case3 FAIL: {len(merged)}"
print("Case3 PASS: Step2만 있으면 2건 전체")

# Case 4: Step1 다수 + Step2 일부 중복
s1 = [{"candidate_id": "R100"}, {"candidate_id": "R200"}, {"candidate_id": "R300"}]
s2 = [{"candidate_id": "R200"}, {"candidate_id": "R400"}]  # R200 중복
merged = _merge_candidates(s1, s2)
assert len(merged) == 4, f"Case4 FAIL: {len(merged)}"
print("Case4 PASS: 3+2(중복R200) → 4건")

# Case 5: 빈 candidate_id 허용 (uuid 생성된 것)
s1 = [{"candidate_id": ""}, {"candidate_id": "R100"}]
s2 = [{"candidate_id": ""}]
merged = _merge_candidates(s1, s2)
assert len(merged) == 3, f"Case5 FAIL: {len(merged)}"
print("Case5 PASS: 빈 candidate_id는 중복제거 안 함")

print()
print("ALL PASS (5/5) -- Candidate 밝합 정상")
