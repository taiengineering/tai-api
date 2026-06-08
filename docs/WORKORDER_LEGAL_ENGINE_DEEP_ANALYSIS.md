# 작업지시서: 법령엔진 정밀 분석 (단위 정합 설계 전)

> 목적: 엔진이 어떤 로직으로 어떤 데이터를 추출/비교하는지 정밀 분석.
>       단위 정합을 설계하기 전에 엔진 동작을 완전히 이해한다.
> 원칙: 분석만. 수정 절대 금지. 코드/DB에서 사실만 기록.
> 배경: 단위 정합(Layer 2→3)이 엔진 평가 로직 수정으로 이어지면
>       13번째 재개발 위험. 먼저 엔진을 완전히 파악해야 안전한 설계 가능.

## 분석 대상: 추출 → 비교 전체 흐름

### Part A: 데이터 추출 (배치 — 법령 텍스트 → draft_slot)

엔진이 법령 텍스트에서 조건을 어떻게 추출하는지:

```
A-1. 법령 원문 → numeric_constraint
  - 어떤 스크립트/서비스가 추출하는가?
  - "50명 이상", "3000㎡" 같은 텍스트를 어떻게 파싱하는가?
  - value, unit을 어떻게 분리하는가?
  - 단위 정규화를 하는가? (안 하면 어디서 해야 하는가?)
  파일: scripts/ 중 numeric_constraint 생성 스크립트
       services/ 중 관련 서비스

A-2. numeric_constraint → rule_candidate_slot
  - 어떻게 변환되는가?
  - binding_field가 여기서 결정되는가?
  - unit이 보존되는가 변환되는가?

A-3. rule_candidate_slot → draft_slot
  - IF_NUMERIC / IF_SCOPE section이 어떻게 결정되는가?
  - binding_field, operator, value, unit이 어떻게 채워지는가?
  - 이 단계에서 단위 정규화 기회가 있는가?
```

### Part B: 조건 비교 (런타임 — factory vs draft_slot)

엔진이 시설과 조건을 어떻게 비교하는지:

```
B-1. FIELD_MAP 전체 분석
  - 10개 키 전부: factory 컬럼 → binding_field
  - 각 매핑의 quality 등급 (DIRECT / AMBIGUOUS / MISSING)
  - quality 등급이 어떻게 결정되었는가? (하드코딩? 규칙?)
  파일: services/facility_applicability_eval.py

B-2. compare_numeric 로직
  - 6개 연산자(>=, <=, >, <, ==, !=) 처리
  - 단위를 보는가? (안 봄 → 그래서 AMBIGUOUS 회피)
  - 값만 비교하는가?

B-3. evaluate_numeric_check 흐름
  - binding_field → FIELD_MAP → factory 값
  - quality=AMBIGUOUS면 왜 비교를 건너뛰는가?
  - UNIT_MISMATCH_POSSIBLE 판정 기준은?

B-4. evaluate_scope_check 흐름
  - facility_type 등 범주 매칭
  - 값 비교를 하는가, 존재만 보는가?
  - 왜 그렇게 설계되었는가?

B-5. aggregate_applicability_status
  - 7개 규칙으로 최종 status 결정
  - MATCH/POSSIBLE/AMBIGUOUS/MISSING/NOT 우선순위
```

### Part C: 단위 정합 가능 지점 분석

```
C-1. 단위 정규화를 넣을 수 있는 지점 후보:
  후보 1: A-1 (numeric_constraint 추출 시) — 배치, 원본 데이터
  후보 2: A-3 (draft_slot 생성 시) — 배치
  후보 3: draft_slot에 normalized 컬럼 추가 — 배치, 비파괴
  후보 4: B-2 (compare 시점) — 엔진 평가 로직 (위험)

  각 후보의:
    - 엔진 평가 로직 수정 필요 여부
    - 기존 데이터 영향 여부
    - 위험도

C-2. binding_field별 정합 난이도 (이미 실측됨, 재확인):
  쉬움(1:1): employee_count(명/인), area_size(m2/㎡)
  중간(배율): power_capacity(kW/W), monetary_value(억/만원),
             distance_value(m/cm/mm)
  어려움(차원): voltage_level(V/kV/kVA), storage_capacity(kg/L/톤),
              concentration_level(%/ppm)

C-3. 각 난이도별로 어느 지점에서 정합하는 게 안전한가?
```

## 산출물

파일: docs/LEGAL_ENGINE_DEEP_ANALYSIS.md

```markdown
# 법령엔진 정밀 분석

## Part A: 추출 흐름
  A-1 법령→numeric_constraint: [파일, 로직, 단위 처리]
  A-2 numeric_constraint→slot: [변환, binding_field 결정]
  A-3 slot→draft_slot: [section 결정, 단위 정규화 기회]

## Part B: 비교 흐름
  B-1 FIELD_MAP: [10키 전체표, quality 등급, 결정 기준]
  B-2 compare_numeric: [연산자, 단위 처리]
  B-3 evaluate_numeric_check: [AMBIGUOUS 회피 이유]
  B-4 evaluate_scope_check: [값비교 vs 존재확인]
  B-5 aggregate: [7규칙 우선순위]

## Part C: 단위 정합 설계 옵션
  C-1 정합 지점 후보 [4개, 각 위험도]
  C-2 난이도별 분류
  C-3 안전한 정합 전략 제안

## 결론
  - 엔진을 건드리지 않고 단위 정합이 가능한가?
  - 가능하면 어느 지점에서?
  - 불가능하면 무엇이 선행되어야 하는가?
```

## 주의

- 수정 절대 금지 (분석만)
- 엔진 평가 로직을 이해하는 것이 목적
- 추측 금지 — 코드에서 실제 로직 인용 (파일:행)
- 단위 정규화 "방법"이 아니라 "어디서 가능한지" 분석
- DB 확인은 Supabase MCP (project_id: vwlahtguyggrhvslabax)
- GPT가 설계한 부분과 실제 구현이 다를 수 있으니 코드 기준으로 기록
