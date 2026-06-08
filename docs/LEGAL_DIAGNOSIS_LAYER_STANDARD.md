# 법령진단 레이어 표준 인터페이스 정의서

> 근거: LEGAL_DIAGNOSIS_LAYER_SURVEY.md (1단계 조사)
>       LEGAL_DIAGNOSIS_LAYER_PROBLEMS.md (2단계 문제점)
>       draft_slot binding_field 실측 / factories 컬럼 실측
> 목적: 각 레이어 경계의 입출력 형태를 표준으로 정의
> 원칙: 엔진(Compiler Core) 내부 수정 없음. 엔진이 요구하는 형태에 맞춰 나머지를 표준화.

## 0. 엔진이 실제로 평가하는 것 (변경 불가 — 표준의 기준)

draft_slot binding_field 실측 결과:

```
IF_NUMERIC (수치 비교):
  employee_count     164슬롯  ← 소비자 입력 가능
  area_size           12슬롯  ← 소비자 입력 가능
  monetary_value       6슬롯  ← 소비자 입력 가능
  voltage_level      142슬롯  ← 소비자 입력 가능
  power_capacity      15슬롯  ← 소비자 입력 가능
  storage_capacity    23슬롯  ← SaaS 추가 입력
  distance_value     415슬롯  ← SaaS 추가 입력
  concentration_level 110슬롯 ← SaaS 추가 입력
  NULL(미바인딩)    1,702슬롯  ← 평가 불가 (수용)

IF_SCOPE (범주 매칭):
  facility_type      220슬롯  ← 소비자 입력 가능
  equipment_type     260슬롯  ← SaaS 추가 입력
  process_type        33슬롯  ← SaaS 추가 입력
  NULL(미바인딩)     215슬롯  ← 평가 불가 (수용)
```

FIELD_MAP이 이 binding_field를 factories 컬럼에 매핑함.

## 표준 1: 소비자 입력 → 엔진 입력 [Layer 1→2]

### 표준 입력 스키마 (StandardDiagnosisInput)
- 필수(모든 섹터): sector (BUILDING|INDUSTRIAL|CONSTRUCTION), employee_count
- BUILDING: building_area, building_use_code(→facility_type), floor_count
- INDUSTRIAL: building_area, industry_type_code(KSIC)
- CONSTRUCTION: construction_amount(원), construction_type
- 공통 선택: electrical_capacity_kw(→voltage/power), gas_capacity_m3(→storage), hazardous_material, contractor_count
- SaaS 추가(무료=null): equipment_type, process_type, concentration_level, distance_value

### 표준 변환 규칙 (Layer 1 → factories INSERT)
```
sector                → factories.sector
employee_count        → factories.employee_count
building_area         → factories.building_area
building_use_code     → factories.building_use_code  ★ 현재 누락 (P-1-01)
floor_count           → factories.floor_count        ★ 현재 누락 (P-1-01)
industry_type_code    → factories.ksic_code
construction_amount   → factories.construction_amount
construction_type     → factories.construction_type
electrical_capacity_kw → factories.electrical_capacity_kw
gas_capacity_m3       → factories.gas_capacity_m3
hazardous_material    → factories.hazardous_material
contractor_count      → factories.contractor_count
메타: name '[ANON] {sector} {timestamp}', is_active false
```
**P-1-01 해소:** building_use_code와 floor_count를 factories INSERT에 포함.

## 표준 2: 엔진 입력 → 법령엔진 [Layer 2→3]

### 표준 FIELD_MAP (factories 컬럼 → draft_slot binding_field)
```
employee_count       → employee_count        ✅ 있음
building_area        → area_size             ✅ 있음
construction_amount  → monetary_value        ✅ 있음
electrical_capacity_kw → voltage_level       ✅ 있음
electrical_capacity_kw → power_capacity      ✅ 있음 (중복 매핑)
gas_capacity_m3      → storage_capacity      ★ 추가 필요
building_use_code    → facility_type         ★ 추가 필요
ksic_code            → facility_type         (INDUSTRIAL 대체)
construction_type    → facility_type         (CONSTRUCTION 대체)
equipment_type       → equipment_type        ★ 추가 (SaaS)
process_type         → process_type          ★ 추가 (SaaS)
concentration_level  → concentration_level   ★ 추가 (SaaS)
distance_value       → distance_value        ★ 추가 (SaaS)
```
주의: FIELD_MAP 추가만. compare/status 로직은 건드리지 않는다.

## 표준 3: 법령엔진 → 검증엔진 [Layer 3→4]

### 표준 fallback 규칙 (task_candidate 없을 때)
```
task_candidate가 없으면:
  applicability_candidates의 draft_id로 executable_draft 조회
  → law_name, obligation_type, title 가져옴
  FallbackRule { draft_id, law_name, obligation_type, rule_type, description, status }
```
**P-3-01 해소:** fallback이 draft에서 law_name, type을 가져옴. 엔진 평가 결과(facility_applicability)는 안 바꾼다.

## 표준 4: 검증엔진 → 정제 [Layer 4→5]

### 표준 Step1Result
- 메타: sector, engine_version, rule_version, evaluated_at
- 집계: total_rules_checked, applicable_count, not_applicable_count, risk_level(HIGH|MEDIUM|LOW)
- rules_table[] (flat, wrapper 아님): rule_id, law_name(필수), law_article, obligation_summary(필수), rule_type(필수), bucket(appointment|inspection|action|report), is_applicable, condition_met, risk_contribution
- 버킷별 뷰: appointment_required/inspection_required/action_required/report_required
- key_obligations[]: category, label, count, items[]{title, description, law_name, evidence[text]}
- law_badges[]: law_name, count, category
- construction_summary (CONSTRUCTION만)

**P-3-01 해소:** rules_table 모든 row에 law_name, rule_type 필수.
**[4→5] 해소:** obligations를 flat items로 통일. wrapper 금지. evidence는 text 배열.

## 표준 5: 정제 → 출력 [Layer 5→6]

### 표준 저장: anonymous_diagnosis_results.result_data(jsonb) ← Step1Result 그대로

### 표준 조회 (GET /anonymous-diagnosis/{token})
{ status, data: { sector, risk_level, applicable_count, evaluated_at, rules_table[], key_obligations[], law_badges[], appointment/inspection/action/report_required[], construction_summary, engine_version } }

### 표준 Transform (POST /transform)
- obligations → key_obligations.items[]를 순회 (wrapper 아니라 flat items)
- evidence → 각 item의 evidence[text] 배열 그대로
- _partial_from_full과 _build_partial을 _build_standard_output(full_result) 하나로 통합

**[4→5] 해소:** Transform이 flat items 순회. **[5→6] 해소:** partial 함수 통합.

## 요약: 표준이 해소하는 문제

| 문제 | 표준 해소 방법 |
|------|---------------|
| P-1-01 building_use_code 누락 | 표준1: INSERT 컬럼 포함 |
| P-1-01 floor_count 누락 | 표준1: INSERT 컬럼 포함 |
| P-3-01 fallback law_name 누락 | 표준3: fallback이 draft에서 가져옴 |
| P-3-01 bucket 불일치 | 표준4: rules_table에 bucket 필수 |
| [2→3] FIELD_MAP 미매핑 | 표준2: facility_type 등 추가 |
| [4→5] obligations wrapper | 표준4: flat items 통일 |
| [4→5] evidence 유실 | 표준4: evidence를 text 배열로 |
| [5→6] partial 불일치 | 표준5: 함수 통합 |
| [2→3] 785슬롯 MISSING_DATA | 수용 (무료 진단 한계) |
| [2→3] 1,917슬롯 NULL binding | 수용 (엔진 내부 미바인딩) |

## 적용 순서
1. Layer 1→2: create_temp_factory INSERT 확장
2. Layer 2→3: FIELD_MAP 확장
3. Layer 3→4: fallback 보강 (draft에서 law_name 조회)
4. Layer 4→5: obligations flat 통일, evidence text 배열
5. Layer 5→6: partial 함수 통합, 조회 응답 통일
6. 검증: 섹터별 테스트
