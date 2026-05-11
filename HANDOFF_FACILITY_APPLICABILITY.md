# Facility Applicability Evaluation — 핸드오프 문서

## 작업 일시

2026-05-11

## 작업 요약

프롬프트 "Facility Applicability Evaluation Engine" 19단계 실행 완료.
30건 시설 xd7 864건 Draft = 25,920건 적합성 평가 완료.

---

## 핵심 원칙 (준수 확인)

- ✅ 법 적용 확정 없음
- ✅ 의무 확정 없음
- ✅ 누락 데이터 보정 없음 (MISSING_DATA 73.5% 정직 유지)
- ✅ 단위 환산 없음 (kVA≠V → AMBIGUOUS)
- ✅ Candidate→Truth 승격 없음

---

## 실행 스크립트

```bash
cd /Users/taiwangsim/Desktop/tai-engineering/tai-api
railway run python3 scripts/run_facility_applicability.py
```

---

## 생성 테이블

| 테이블 | 건수 | 역할 |
|---|---|---|
| facility_applicability | 25,920 | 시설xd7Draft 적합성 평가 |
| facility_applicability_detail | 36,390 | 개별 검증 상세 |
| facility_applicability_issue | 0 | 이슈 |

---

## 실행 결과

### Applicability Status

| status | 건수 | 비율 |
|---|---|---|
| MISSING_DATA | 19,057 | 73.5% |
| MATCH_CANDIDATE | 3,045 | 11.7% |
| POSSIBLE_CANDIDATE | 1,918 | 7.4% |
| AMBIGUOUS | 1,103 | 4.3% |
| NOT_MATCHED | 797 | 3.1% |

### Detail Result

| result | 건수 |
|---|---|
| MISSING_DATA | 28,370 |
| MATCH_CANDIDATE | 3,684 |
| POSSIBLE_CANDIDATE | 1,953 |
| AMBIGUOUS | 1,290 |
| NOT_MATCHED | 1,093 |

### Detail Reason

| reason | 건수 | 설명 |
|---|---|---|
| NO_FACILITY_COLUMN | 21,600 | facility에 해당 칼럼 없음 |
| FACILITY_VALUE_NULL | 6,770 | 칼럼 있으나 값 NULL |
| DIRECT_COMPARE | 4,777 | 직접 숫자 비교 |
| SCOPE_FIELD_EXISTS | 1,953 | Scope 칼럼 존재 |
| UNIT_MISMATCH_POSSIBLE | 1,290 | 단위 불일치 가능성 |

### Field Binding

| binding_field | facility_column | quality |
|---|---|---|
| employee_count | employee_count | DIRECT |
| area_size | building_area | DIRECT |
| power_capacity | electrical_capacity_kw | DIRECT |
| voltage_level | transformer_capacity_kva | AMBIGUOUS (kVA≠V) |
| storage_capacity | gas_capacity_m3 | AMBIGUOUS (m³≠리터) |
| facility_type | site_type | AMBIGUOUS |
| process_type | ksic_code | AMBIGUOUS |
| concentration_level | — | MISSING |
| distance_value | — | MISSING |

---

## DB 직접 검증

| 검증 | 결과 |
|---|---|
| 건수 일치 | ✅ 25,920 + 36,390 |
| MATCH 비교 정확성 | ✅ employee≥50 vs 2→MATCH, area≥100 vs 3000→MATCH |
| NOT_MATCHED 비교 정확성 | ✅ employee≤2 vs 50→NOT, power≥700 vs 100→NOT |
| 법 적용 확정 | ✅ 없음 |
| 누락 보정 | ✅ 없음 |

---

## 누적 DB 테이블 (이번 세션 전체)

| 테이블 | 건수 | 작업 |
|---|---|---|
| constraint_node | 284,579 | Constraint Graph |
| constraint_edge | 54,122 | Constraint Graph |
| numeric_constraint | 10,329 | Numeric Extraction |
| numeric_family_relation | 8,791 | Numeric Extraction |
| numeric_family_candidate | 10,329 | Numeric Family |
| numeric_graph_relation | 6,934 | Numeric Family |
| rule_candidate | 34,456 | Rule Candidate IR |
| rule_candidate_slot | 146,595 | Rule Candidate IR |
| rule_candidate_relation | 59,116 | Rule Candidate IR |
| compatibility_validation | 59,116 | Compatibility |
| compatibility_issue | 757 | Compatibility |
| executable_draft | 10,725 | Executable Draft |
| draft_slot | 50,133 | Executable Draft |
| draft_condition_graph | 10,725 | Executable Draft |
| facility_applicability | 25,920 | Facility Applicability |
| facility_applicability_detail | 36,390 | Facility Applicability |
| facility_applicability_issue | 0 | Facility Applicability |

이번 세션 테이블 19개, 총 레코드 약 917K건.

---

## 다음 단계 후보

1. **Penalty Candidate & Obligation-Penalty Mapping** — 벌칙/과태료 연결
2. **Task/Schedule Candidate** — 작업/일정 후보 생성
3. **Residual Coverage Engine** — 미처리 조문 탐지
4. **MISSING_DATA 해소** — facility 칼럼 확장으로 평가율 향상 가능
