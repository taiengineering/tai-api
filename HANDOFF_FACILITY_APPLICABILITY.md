# Facility Applicability Evaluation — 핸드오프 문서

## 작업 일시

2026-05-11

## 작업 요약

프롬프트 "Facility Applicability Evaluation Engine" 19단계 실행 완료.
30개 시설 × 864개 Draft = 25,920건 적합성 평가.

---

## 핵심 원칙 (준수 확인)

- ✅ 법 적용 확정 없음
- ✅ 의무 확정 없음
- ✅ 누락 데이터 보정 없음 (MISSING_DATA 73.5% 정직하게 유지)
- ✅ 단위 환산 없음 (kVA≠V, m³≠리터 → AMBIGUOUS 처리)
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
| facility_applicability | 25,920 | 시설×Draft 적합성 평가 |
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
| NO_FACILITY_COLUMN | 21,600 | facility에 해당 칼럼 없음 (concentration, distance) |
| FACILITY_VALUE_NULL | 6,770 | 칼럼 있으나 값 없음 |
| DIRECT_COMPARE | 4,777 | 직접 숫자 비교 수행 |
| SCOPE_FIELD_EXISTS | 1,953 | Scope 칼럼 존재 확인 |
| UNIT_MISMATCH_POSSIBLE | 1,290 | 단위 불일치 가능성 (kVA/m³ 등) |

---

## DB 직접 검증

| 검증 | 결과 |
|---|---|
| 건수 일치 | ✅ 25,920 + 36,390 + 0 |
| MATCH 숫자 비교 정확성 | ✅ employee_count>=2 vs 50→MATCH, area>=100 vs 3000→MATCH |
| NOT_MATCHED 숫자 비교 정확성 | ✅ employee<=2 vs 50→NOT, power>=700 vs 100→NOT |
| 법 적용 확정 | ✅ 없음 |
| 누락 보정 | ✅ 없음 |

---

## Field Binding 매핑

| binding_field | facility_column | match_quality |
|---|---|---|
| employee_count | employee_count | DIRECT |
| area_size | building_area | DIRECT |
| power_capacity | electrical_capacity_kw | DIRECT |
| voltage_level | transformer_capacity_kva | AMBIGUOUS (kVA≠V) |
| storage_capacity | gas_capacity_m3 | AMBIGUOUS (m³≠리터) |
| facility_type | site_type | AMBIGUOUS |
| process_type | ksic_code | AMBIGUOUS |
| monetary_value | construction_amount | AMBIGUOUS |
| equipment_type | (equipment_assets JOIN) | EQUIPMENT_JOIN |
| concentration_level | 없음 | MISSING |
| distance_value | 없음 | MISSING |

---

## 누적 DB 테이블 총괄

이번 세션 테이블 19개, 총 레코드 약 960K건.

---

## 다음 단계 후보

1. **Penalty Candidate & Obligation-Penalty Mapping Engine**
2. **Task/Schedule Candidate** — 작업/일정 후보 생성
3. **Residual Coverage Engine** — 미처리 조문 탐지
4. **MISSING_DATA 해소** — facility 칼럼 확장 (concentration, distance)
5. **AMBIGUOUS 해소** — 단위 통일 레이어 추가
