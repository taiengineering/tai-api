# verification/test_candidate_presentation.py
# Phase 8-B: Candidate Presentation Layer 검증
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.candidate_presentation import (
    group_candidates,
    build_display_candidates,
    build_candidate_presentation,
)

raw = [
    # 전기안전관리법 시행규칙 제2조 -- 21건
    *[
        {"candidate_id": f"ELEC-{i}", "law_name": "전기안전관리법 시행규칙",
         "article_no": "제2조", "source_type": "INSPECT",
         "condition_code": "electrical_capacity_kw", "evidence_chain": [{"rule_id": f"ELEC-{i}"}]}
        for i in range(21)
    ],
    # 고압가스 안전관리법 시행규칙 제5조 -- 25건
    *[
        {"candidate_id": f"GAS-{i}", "law_name": "고압가스 안전관리법 시행규칙",
         "article_no": "제5조", "source_type": "APPOINT",
         "condition_code": "gas_capacity_kg", "evidence_chain": [{"rule_id": f"GAS-{i}"}]}
        for i in range(25)
    ],
    # 중대재해처벌법 -- 5건
    *[
        {"candidate_id": f"MAJOR-{i}", "law_name": "중대재해처벌법",
         "article_no": "제4조", "source_type": "ACTION",
         "condition_code": None, "evidence_chain": [{"rule_id": f"MAJOR-{i}"}]}
        for i in range(5)
    ],
]

# Case 1: group_candidates
groups = group_candidates(raw)
assert len(groups) == 3, f"Case1 FAIL: group 수={len(groups)}"
print(f"Case1 PASS: raw={len(raw)}건 → group={len(groups)}건")

# Case 2: candidate_count 확인
gc = {g['group_key']: g for g in groups}
assert gc['전기안전관리법 시행규칙|제2조']['candidate_count'] == 21
assert gc['고압가스 안전관리법 시행규칙|제5조']['candidate_count'] == 25
assert gc['중대재해처벌법|제4조']['candidate_count'] == 5
print("Case2 PASS: candidate_count 정확")

# Case 3: 우선순위 정렬 -- APPOINT(점수100)가 첫 번째
assert groups[0]['group_key'] == '고압가스 안전관리법 시행규칙|제5조', f"Case3 FAIL: {groups[0]['group_key']}"
print("Case3 PASS: APPOINT 그룹이 첫 번째 (우선순위 정렬)")

# Case 4: build_display_candidates
display = build_display_candidates(groups)
assert len(display) == 3
assert display[0]['priority_label'] == 'HIGH'    # APPOINT=100
assert display[1]['priority_label'] == 'HIGH'    # INSPECT=90
assert display[2]['priority_label'] == 'LOW'     # ACTION=50
print("Case4 PASS: priority_label HIGH/HIGH/LOW")

# Case 5: build_candidate_presentation
presentation = build_candidate_presentation(raw)
assert presentation['metadata']['raw_count'] == 51
assert presentation['metadata']['group_count'] == 3
assert presentation['metadata']['display_count'] == 3
expected_reduction = round((51-3)/51*100, 1)
assert presentation['metadata']['reduction_rate'] == expected_reduction
print(f"Case5 PASS: raw=51 display=3 reduction={presentation['metadata']['reduction_rate']}%")

# Case 6: raw candidate 원본 보존 (삭제 안 됨)
assert len(raw) == 51, "Case6 FAIL: raw candidate 변형됨"
print("Case6 PASS: raw candidate 51건 원본 보존")

print()
print("ALL PASS (6/6) -- Phase 8-B Candidate Presentation Layer")
