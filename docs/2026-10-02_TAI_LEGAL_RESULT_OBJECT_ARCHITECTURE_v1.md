# TAI 법령진단 결과 고도화 기획서
## Object Architecture v1

**상태:** DRAFT / PLANNING
**대상:** 무료 법령진단 · 유료 법령진단 · TAI Safe SaaS 법령진단 결과
**역할:** GPT 설계·기획·작업지시·검증 / Claude 조사·실행 / Owner 승인
**원칙:** 신규 법령엔진 생성 금지. 현재 canonical 결과와 기존 자산을 재사용한다.

---

# 1. 목적

본 프로젝트의 목적은 법령엔진 결과를 다시 만드는 것이 아니다.

현재 법령엔진이 생성하는 동일한 법적 의무 결과를 기준으로 다음 세 고객 Surface의 역할을 명확히 분리한다.

- 무료진단: **무엇이 적용되는가**
- 유료진단: **무엇을 해야 하며, 어떤 근거와 조건을 가지고 있는가**
- SaaS: **그 의무를 현재 어떻게 운영·관리할 것인가**

결과 데이터는 하나이되 Surface의 질문과 정보 위계는 서로 다르게 한다.

---

# 2. 설계 원칙

## 2.1 One Result, Multiple Surfaces

법령 결과를 FREE·PAID·SaaS가 각각 재해석하지 않는다.

```text
Diagnosis Snapshot
        │
        ├── Obligation Presentation
        ├── Legal Time
        ├── Result Materials
        └── Legal Evidence
                │
        ┌───────┼─────────┐
        │       │         │
      FREE     PAID      SaaS
```

같은 법령의무에 서로 다른 의미를 붙이는 것을 금지한다.

## 2.2 Object First

각 오브젝트는 하나의 책임과 하나의 의미만 가진다.

Surface가 다른 오브젝트 내부 데이터를 임의로 해석하지 않는다. 연결은 공개 계약을 통해서만 한다.

## 2.3 Existing Asset First

다음은 신규 생성하지 않는다.

- 법령결과 엔진
- 6W 엔진
- 법적 시기 엔진
- 법령 시각화 엔진
- 법령 원문 매칭 엔진
- SaaS 의무 재생성 엔진

현재 구현된 mapper, normalizer, materializer, evidence/source-text, operation bridge를 재사용한다.

## 2.4 Fail Closed

원천에 없는 값을 추정해서 채우지 않는다.

특히 다음을 생성하지 않는다.

- 위험도 점수
- 위험 %
- 임의 우선순위
- 임의 deadline
- 추정 담당자
- 추정 제출기관
- 의무별 추정 처벌
- 없는 자격요건·서식·준비서류

## 2.5 Adaptive Presentation

모든 의무에 6W 표를 강제로 보여주지 않는다.

최근 운영 데이터에서 `where/how`는 사실상 존재하지 않고, `when/cycle`도 일부 의무에만 존재한다.

따라서:

> 값이 있는 정보만 의미 있는 위치에 표시한다.

빈 차트, 빈 카드, `-`, "해당 없음"을 대량 생성하지 않는다.

---

# 3. Canonical Object Map

## OBJ-RSLT-01. Diagnosis Snapshot Object

**의미:** 한 번의 법령진단 실행에서 실제 생성된 결과

**현재 원천**
- `full_result.obligations_raw[]`
- `applicable_count`
- engine/version metadata

**책임**
- 당시 실행 결과를 보존한다.
- 현재 운영 상태와 섞지 않는다.

**금지**
- 최신 결과로 대체
- 현재 inspection inventory로 대체
- Surface별 독립 재판정

**상태:** KEEP

---

## OBJ-RSLT-02. Obligation Identity Object

**의미:** 법적 의무 한 건의 추적 가능한 identity

**주요 값**
- `atom_id`
- `source_atom_ids`
- `source_index`

**책임**
- Snapshot → Presentation → Evidence → Operation 간 연결축 제공

**원칙**
- fuzzy match 금지
- 법령명+조문+문장 유사도로 임의 연결 금지
- 가능한 경우 atom identity를 우선한다.

**상태:** KEEP / CORE

---

## OBJ-RSLT-03. Obligation Presentation Object

**현재 구현**
`services/obligation_presentation_mapper.py`

**의미:** 법령엔진 의무를 고객 Surface가 소비할 수 있도록 동일 의미로 운반하는 표현 객체

현재 주요 계약:

| Presentation | 원천 |
|---|---|
| action | obligation_detail.what |
| actor | obligation_detail.who |
| timing | obligation_detail.when |
| cycle | enrichment.inspection_cycle |
| condition | obligation_detail.condition |
| recipient | obligation_detail.recipient |
| where | obligation_detail.where |
| how | obligation_detail.how |
| legal_basis | law_name + law_article |
| evidence | evidence |
| status | check_result |

**확정 유지**
`action`, `actor`, `timing`, `cycle`, `condition`, `recipient`, `where`, `how`, `legal_basis`, `evidence`는 원천값 운반 계약으로 유지한다.

### 의미 교정 필요

현재:

`reason ← triggered_by`

는 데이터 연결 자체는 유지할 수 있으나 고객 의미가 잘못될 가능성이 있다.

`triggered_by`의 실제 의미는:

> 판정 과정에서 사용된 사업장 입력 정보

이지 반드시:

> 이 법이 적용되는 법적 이유

가 아니다.

따라서 내부 호환성을 깨뜨리지 않는 범위에서 고객 Surface 문구는 우선:

**"판정에 사용된 사업장 정보"**

계열로 교정한다.

**상태:** KEEP + SEMANTIC PATCH

---

## OBJ-RSLT-04. Legal Time Object

**현재 구현**
`services/legal_time_normalizer.py`

**의미:** 법령에 명시된 시간·시점·주기의 deterministic 구조화

구조:

```text
timing
cycle
 ├ source_text
 ├ status = NORMALIZED | RAW_ONLY
 ├ type
 ├ operator
 ├ value
 ├ unit
 └ basis_text
```

지원 의미:
- RECURRING
- EVENT_DEADLINE
- CONTINUOUS
- IMMEDIATE
- ONE_TIME
- RAW_ONLY

**원칙**
- 법령 원문 우선
- ambiguous text 추측 금지
- 법적 시점과 회사 운영일정 분리

**현재 상태**
- Backend: 연결됨
- PAID Excel: 연결됨
- SaaS inspection read model: 연결됨
- PAID Web: public adapter에서 소비 연결이 끊겨 있음

**상태:** KEEP + CONNECT

---

## OBJ-RSLT-05. Result Materials Object

**현재 구현**
`paid_result_materializer.py`

**의미:** 개별 의무를 바꾸지 않고 결과 전체에서 파생 가능한 객관적 집계 사실

현재 자산:
- Overview
- Law Portfolio
- Duty vs Prohibition
- Applicability Basis
- Legal Basis Bundle
- Verification Summary
- Information Gaps
- Legal Actor Map
- Recipient Map
- Legal Timing Profile
- Timing Character
- Exact Duplicate Groups
- Article Bundles
- Compliance Profile
- Coverage
- Execution Seed
- Diagnosis Findings

**책임**
COUNT / GROUP / DISTINCT / EXACT 조합 등 deterministic aggregate까지만 담당한다.

**금지**
- 위험평가
- 중요도 결정
- 회사 우선순위 결정
- 법률적 해석문 생성

**상태:** KEEP

---

## OBJ-RSLT-06. Legal Evidence Object

구성:
- 법령명
- 조문
- evidence
- canonical source text
- article evidence

**현재 자산**
- `paid_result_evidence_v1`
- `paid_result_source_text_v1`

**원칙**
- EXACT 연결
- 원문 fallback 추정 금지
- `duty.what`을 법령 원문으로 가장하지 않는다.

**상태:** KEEP

---

# 4. Surface Objects

## OBJ-SURF-01. Free Result Object

### 사용자 질문

> "우리 사업장에 어떤 법령과 의무가 적용되는가?"

### 화면의 역할

FREE는 진단 자체에서 종료한다. 이후 서비스는 CTA로 연결한다.

### 기본 노출

1. 진단에 사용된 정보
2. 관련 법령
3. 확인된 법적 의무
4. 의무 유형
5. 최소한의 실행 이해 정보
6. 상세진단 CTA

### 노출 축소 원칙

FREE에서 PAID의 전체 evidence/workbench 역할을 선소비하지 않는다.

특히 다음은 기본 상세정보로 과다 노출하지 않는다.

- 법령 원문 전체
- 상세 근거 체계
- 관리 구조 분석
- Evidence appendix
- 유료 보고서 수준의 시각화

### 즉시 교정 대상

현재 raw `check_result`가 그대로 "상태"로 표시될 수 있다.

실데이터에서는:

`check_result = NOT_APPLICABLE`
동시에
`consumer_status = applicable`

인 사례가 다수 존재한다.

따라서 `check_result`를 법 적용 여부처럼 표시해서는 안 된다.

FREE 고객 Surface에서는 raw enum 노출을 금지한다.

### CTA 계약

유료진단이 현재 지원하지 않는 다음 가치의 확정 약속을 제거한다.

- 자격요건
- 임의 기한
- 준비서류
- 신고방법
- 처벌 리스크
- 우선순위 행동계획

유료진단 실제 가치에 맞춰 CTA를 다시 정의한다.

**상태:** MODIFY

---

## OBJ-SURF-02. Paid Result Object

### 사용자 질문

> "확인된 의무를 실제로 이해하고 대응하려면 무엇을 알아야 하는가?"

### 핵심 가치

FREE의 단순 확장이 아니라 다음을 제공한다.

1. 사업장 결과 전체 구조
2. 의무별 해야 할 일
3. 법령상 수행주체
4. 조건
5. 법적 시점·주기
6. 법령·조문
7. 근거 원문
8. 결과 구성 시각화
9. 정보공백
10. Excel/PDF 산출물

### 기존 자산 재사용

현재 V1~V6 adaptive visualization을 유지한다.

- 의무 성격
- 의무 유형
- 법령 구성
- 법적 시점
- 법령상 수행주체
- 조문 구성

시각화 개수는 고정하지 않는다.

### 확정 수정 사항

#### A. 의무유형 vocabulary

현재 PAID는 4종만 명시적으로 처리하지만 실제 운영 데이터는 7종이다.

정식 타입:

- ACTION
- PROHIBIT
- INSPECT
- APPOINT
- TRAINING
- NOTIFY
- REPORT

모든 타입을 원본 의미대로 표현하도록 정합화한다.

#### B. Legal Time

Backend와 Excel에 이미 존재하는 `legal_time_normalized`를 PAID Web까지 연결한다.

기존 raw `timing/cycle`은 원문 표현으로 유지할 수 있으나, 구조화된 법적 시기 정보가 존재하면 그 객체를 기준으로 표현한다.

#### C. 적용 사유

`triggered_by`를 "법적 적용 사유"로 확대 해석하지 않는다.

#### D. 위험 표현

현재 Product Contract가 만들지 않는 위험점수·위험도·우선순위를 UI에서도 만들지 않는다.

**상태:** MODIFY / EXISTING ASSET REUSE

---

## OBJ-SURF-03. SaaS Diagnosis Snapshot Object

### 사용자 질문

> "이번 법령진단 실행에서 무엇이 추출되었는가?"

현재 main의 PR #100 구조를 기준으로 한다.

**Source**
`GET /legal-engine/diagnose/snapshot/{diagnosis_id}`

### 역할

현재의:
- 추출 의무 건수
- 실행 시각
- engine version
- 법령/조문/의무 미리보기

구조를 유지한다.

여기에 필요 시 `Obligation Presentation Object`를 연결해 결과를 더 읽기 쉽게 만들 수 있다.

단, 이 오브젝트는 **현재 관리상태를 소유하지 않는다.**

**상태:** KEEP + ENHANCE

---

## OBJ-OPS-01. SaaS Operation Inventory Object

### 사용자 질문

> "지금 우리 사업장은 어떤 법정의무를 관리하고 있는가?"

현재:
- inspection set
- legal obligation atom
- legal operation presentation
- legal time
- operation cycle
- anchor
- next planned date
- 담당/상태

등의 운영 자산을 가진다.

### 절대 분리

다음 두 값은 다른 의미이다.

```text
법령상 수행주체 ≠ 실제 담당자
법적 시점/주기 ≠ 회사 운영 예정일
```

Snapshot Object와 Operation Inventory Object의 데이터는 서로 대체하지 않는다.

**상태:** KEEP

---

# 5. Output Objects

## OBJ-OUT-01. Paid Excel Object

**Source:** `premium_result_v1`

현재 방향을 유지한다.

Excel에서 독립 법령해석 또는 재판정을 하지 않는다.

Legal Time과 Evidence도 현재 Premium contract를 통해 소비한다.

**상태:** KEEP

---

## OBJ-OUT-02. Paid PDF Object

현재 가장 큰 구조적 부채 중 하나다.

현재 PDF는 Web/Excel과 달리 `full_result`를 다시 열어:

- rules_table
- applicable_rules
- obligations
- summary
- law groups

등을 별도로 조립한다.

이를 장기 정본으로 인정하지 않는다.

### 목표 계약

```text
Premium Result Object
       │
       ├── Web
       ├── Excel
       └── PDF
```

PDF는 별도의 법령결과 해석자가 아니라 **동일 Product Result의 출력 Surface**가 되어야 한다.

**상태:** REPOINT

---

# 6. Visualization Object

새 Visualization Engine은 만들지 않는다.

현재 PAID `premium.js / AdaptiveVisuals`가 가진 visual eligibility 구조를 재사용한다.

차트 컴포넌트는 데이터 의미를 판단하지 않는다.

```text
Result Materials
      ↓
Surface visual specification
      ↓
Generic Chart Renderer
```

Chart Renderer는 "빈 그릇"이다.

의미 판단은 PAID Surface가 가진다.

---

# 7. 고객 정보 위계

## FREE

```text
사업장
↓
적용 법령
↓
확인된 의무
↓
유료 상세진단
```

## PAID

```text
사업장 결과
↓
결과 구조
↓
확인사항
↓
법적 의무 Workbench
↓
법령/조문/원문
↓
Excel / PDF
```

## SaaS

```text
이번 진단 결과
↓
현재 관리상태
↓
일정 / 담당 / 증빙 / 실행
```

세 Surface를 하나의 화면으로 합치지 않는다.

---

# 8. Field Classification

각 필드는 구현 전에 다음 등급으로 관리한다.

### DIRECT

원천을 그대로 운반한다.

예:
- action
- actor
- condition
- legal basis
- evidence

### DERIVED-DETERMINISTIC

확정된 규칙으로만 계산한다.

예:
- 법령별 건수
- 수행주체별 건수
- legal time normalization
- article count

### PRESENTATION

법적 사실을 바꾸지 않는 고객 표현이다.

예:
- enum → 한국어 라벨
- 시각화 형태
- section ordering

### OPERATIONAL

SaaS에서만 생성되는 회사 운영값이다.

예:
- assignee
- schedule anchor
- next planned date
- completion state

### VERIFY

의미가 혼동될 수 있어 검증 전 강한 문구를 쓰지 않는다.

현재 대표:
- `triggered_by → reason`
- `check_result`
- legacy collector penalty
- submit_org collector

---

# 9. 현재 확정 문제 목록

### P0 — 정확성

1. FREE raw `check_result` 고객노출
2. PAID 의무유형 vocabulary 4종 ↔ 실제 7종 불일치
3. PAID Web에서 `legal_time_normalized` 유실
4. PDF가 Premium Result를 사용하지 않고 독자 재해석

### P1 — 상품가치/의미

5. `triggered_by`를 "적용 사유"로 과장할 가능성
6. FREE 유료 CTA가 실제 PAID 계약보다 많은 기능을 약속
7. FREE에서 PAID 수준 정보 일부 선노출
8. PAID 정보가 많지만 위계가 복잡함

### P2 — 고도화

9. SaaS Snapshot에서 Presentation Object 활용
10. PAID/SaaS 실제 운영표본 확대 검증
11. 세 Surface visual consistency

---

# 10. 성공 기준

본 프로젝트는 다음 조건을 모두 만족할 때 완료한다.

1. 동일 의무가 FREE/PAID/SaaS에서 서로 다른 법적 의미로 표현되지 않는다.
2. 고객 화면에 raw machine enum이 노출되지 않는다.
3. 7개 실제 obligation type이 의미 손실 없이 표시된다.
4. Legal Time은 하나의 shared object를 소비한다.
5. FREE는 "무엇이 적용되는가"에 집중한다.
6. PAID는 FREE 대비 명확한 상세가치를 제공한다.
7. SaaS는 Snapshot과 Operation State를 끝까지 분리한다.
8. Web/Excel/PDF가 동일 Paid Result Contract를 기준으로 한다.
9. 법령 결과에 없는 사실을 UI가 생성하지 않는다.
10. 신규 법령엔진·신규 시각화엔진을 만들지 않는다.
