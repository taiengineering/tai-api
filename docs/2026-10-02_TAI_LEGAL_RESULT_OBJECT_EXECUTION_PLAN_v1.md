# TAI 법령진단 결과 고도화 작업계획서
## Object Execution Plan v1

**상태:** PLANNED / IMPLEMENTATION NOT STARTED
**실행:** Claude
**설계·작업지시·독립검증:** GPT
**최종 승인:** Owner

---

# 1. 작업 목표

기존 법령결과 자산을 재사용하여 FREE / PAID / SaaS 결과 Surface를 오브젝트 방식으로 정합화한다.

이번 작업의 중심은 신규 기능 개발이 아니라:

1. 의미 오류 제거
2. 중복 계약 제거
3. 기존 canonical object 연결
4. Surface별 정보 위계 재구성
5. 산출물 계약 통일

이다.

---

# 2. 변경 금지 기준선

작업 전체에서 다음은 기본적으로 동결한다.

- 법령 적용판정 로직
- `obligations_raw` 생성 의미
- atom identity
- Evidence resolution
- Canonical source matching
- Legal Time normalization semantics
- SaaS operation schedule semantics
- 법령 SoT
- 법령 DB 데이터

필요하면 소비·표현 계층만 변경한다.

---

# 3. 실행 오브젝트

| Object | 상태 | 이번 작업 |
|---|---|---|
| OBJ-RSLT-01 Diagnosis Snapshot | KEEP | 변경 최소 |
| OBJ-RSLT-02 Obligation Identity | KEEP | 회귀검증 |
| OBJ-RSLT-03 Presentation | PATCH | reason/status 의미 경계 |
| OBJ-RSLT-04 Legal Time | CONNECT | PAID Web 연결 |
| OBJ-RSLT-05 Result Materials | KEEP | vocabulary 소비 검증 |
| OBJ-RSLT-06 Evidence | KEEP | 회귀검증 |
| OBJ-SURF-01 FREE | MODIFY | 정보위계·상태·CTA |
| OBJ-SURF-02 PAID | MODIFY | 타입·시기·구조 |
| OBJ-SURF-03 SaaS Snapshot | MODIFY | presentation 소비 |
| OBJ-OPS-01 SaaS Inventory | KEEP | 분리 경계 보존 |
| OBJ-OUT-01 Excel | KEEP | regression |
| OBJ-OUT-02 PDF | REPOINT | Premium Result 소비 |
| OBJ-VIS-01 Adaptive Visual | KEEP | 기존 자산 재사용 |

---

# 4. 작업 순서

## OBJ-WP-00 — Current Contract Freeze

### 목적

구현 전에 현재 계약을 증거로 고정한다.

### 조사 대상

- tai-api main
- tai-www main
- tai-admin main
- 최근 실제 FREE/PAID/SaaS 결과 sample
- 관련 테스트

### 산출물

- current SHA
- object/file map
- current API shape
- sample field matrix
- 테스트 baseline

### 금지

- 코드 수정
- DB write
- branch 생성
- PR 생성

### Exit

GPT가 Current Contract Map을 독립검증한다.

**HARD STOP**

---

## OBJ-WP-01 — Presentation Semantic Contract

### 대상

`OBJ-RSLT-03`

### 작업

1. `reason ← triggered_by`의 원천 의미 확인
2. 기존 key 호환성 유지 여부 결정
3. 고객 Surface label을 "판정에 사용된 사업장 정보" 계열로 정합화
4. `status ← check_result`가 법 적용상태가 아니라는 계약 명시
5. raw enum 고객 노출 차단 규칙 정의
6. FREE/PAID mapper parity 유지

### 금지

- triggered_by 재판정
- status 값 변환으로 법 적용여부 생성
- LLM 의미보충
- 법령엔진 변경

### 테스트

- mapper exact transport
- absent ≠ null
- FREE/PAID parity
- machine key hidden
- raw check_result customer DOM 0

### Exit

동일 raw obligation에서 FREE/PAID Presentation 의미가 일치한다.

**HARD STOP → GPT VERIFY**

---

## OBJ-WP-02 — Obligation Type Vocabulary Alignment

### 대상

`OBJ-RSLT-03`, `OBJ-SURF-01`, `OBJ-SURF-02`

### canonical source

실제 `enrichment.obligation_type`

현재 운영값 7종:

```text
ACTION
PROHIBIT
INSPECT
APPOINT
TRAINING
NOTIFY
REPORT
```

### 작업

- PAID 4종 dictionary 정정
- FREE와 PAID의 known type set 정합
- REPORT/NOTIFY group 여부는 Surface presentation으로만 처리
- 원본 type은 병합하지 않는다.
- 신규/미지 type은 fail-closed OTHER 처리

### 핵심 원칙

```text
canonical type ≠ UI grouping
```

원본 7종을 유지하면서 UI 필요에 따라 묶는다.

### Exit

7개 type fixture가 모두 올바른 고객표현을 가진다.

**HARD STOP → GPT VERIFY**

---

## OBJ-WP-03 — Legal Time Consumer Completion

### 대상

`OBJ-RSLT-04`, `OBJ-SURF-02`

### 현행

```text
API      = 있음
Excel    = 사용
SaaS     = 사용
PAID Web = adapter 유실
```

### 작업

1. public premium → frontend adapter에서 `legal_time_normalized` 보존
2. PAID internal contract에 additive 연결
3. Workbench에서 raw 원문과 normalized 의미의 역할 분리
4. Adaptive Visual V4의 source 검토
5. RAW_ONLY는 원문을 보존하고 임의 정규화하지 않음

### 금지

- frontend 독립 regex parser
- frontend 날짜 계산으로 법적 deadline 생성
- raw `when/cycle` 삭제
- Legal Time normalizer 복제

### Exit

동일 Legal Time Object가 Excel / PAID Web / SaaS에서 semantic parity를 가진다.

**HARD STOP → GPT VERIFY**

---

## OBJ-WP-04 — FREE Result Product Boundary

### 대상

`OBJ-SURF-01`

### 목표

FREE를 "결과를 많이 보여주는 화면"에서:

> 적용 법령과 핵심 법적 의무를 이해시키는 화면

으로 정리한다.

### 유지

- 진단에 사용된 정보
- 관련 법령
- 의무 목록
- obligation type
- 핵심 action
- 유료진단 CTA

### 재검토

- actor
- timing
- cycle
- condition
- evidence
- canonical source
- status
- reason

각 필드는 FREE 상품가치 기준으로 기본/접힘/미노출 중 하나로 분류한다.

### 필수 수정

- raw status 제거
- machine key 제거
- unsupported paid-value CTA 제거
- PAID에서 실제 제공하는 내용으로 CTA 정정

### 회귀

- 의무 건수
- 법령 건수
- 7 type
- 무료 결과 0건
- 결과조회 실패
- CTA route

### Exit

FREE만 사용해도 진단 목적은 완결되지만 PAID의 상세가치를 대체하지 않는다.

**HARD STOP → GPT VERIFY**

---

## OBJ-WP-05 — PAID Result Recomposition

### 대상

`OBJ-SURF-02`, `OBJ-VIS-01`

### 목표

기존 10-chapter 자산을 버리지 않고 정보 위계를 재정리한다.

### 1차 구조

```text
01 결과 표지
02 진단 사업장
03 핵심 결과
04 확인된 특징
05 결과 구성 시각화
06 법적 의무 Workbench
07 법령·조문
08 추가 확인 정보
09 Evidence
10 산출물
```

단, 실제 데이터가 없는 section은 생성하지 않는다.

### 시각화 원칙

기존 V1~V6를 유지한다.

- type
- content
- law
- legal time
- legal actor
- article

새 차트 엔진 생성 금지.

### Workbench 우선 위계

의무 한 건은 우선:

```text
해야 할 일
→ 수행주체
→ 법적 시점/주기
→ 조건
→ 법령/조문
→ 근거
```

값이 없는 필드는 자리만 만들지 않는다.

### Exit

PAID는 FREE보다 단순히 "더 많은 필드"가 아니라 **법적 의무를 이해할 수 있는 구조적 상품**이 된다.

**HARD STOP → GPT VERIFY**

---

## OBJ-WP-06 — PDF Contract Repoint

### 대상

`OBJ-OUT-02`

### 문제

현재 PDF는 `full_result`를 다시 해석한다.

### 목표

PDF를:

```text
Raw Result Consumer
```

에서:

```text
Paid Result Consumer
```

로 변경한다.

### 요구사항

- Web과 동일 Premium Result Contract 사용
- 별도 law grouping 의미 생성 금지
- 별도 risk 계산 금지
- 별도 obligation type mapping 금지
- Evidence는 Premium Evidence 사용
- 법적 시기는 Legal Time Object 사용

### 구현방법

구체적인 렌더 방식은 조사 후 작업지시에서 선택한다.

후보:
- Premium result → PDF-specific presentation
- Web report printable surface → PDF
- 기존 Gotenberg 유지 + 입력계약만 Premium으로 전환

이번 계획에서는 방식을 고정하지 않는다.

### Exit

같은 진단에 대해 Web / Excel / PDF의 핵심 숫자와 법적 의무가 동일하다.

**HARD STOP → GPT VERIFY**

---

## OBJ-WP-07 — SaaS Snapshot Enrichment

### 대상

`OBJ-SURF-03`

### 현재 기준

PR #100의:

```text
Section A = 이번 진단 snapshot
Section B = 현재 inspection inventory
```

분리는 변경하지 않는다.

### Section A 고도화

현재:
- 법령
- 조문
- what

만 표시한다.

필요 시 Presentation Object를 사용해:

- 의무 유형
- action
- actor
- legal time
- condition

등을 선택적으로 표현한다.

### Section B

현재 운영정보는 기존 Inspection/Operation Objects를 그대로 사용한다.

Snapshot 값을 운영상태로 복사하지 않는다.

### 금지

- 이번 진단 snapshot = 현재 inventory 로 간주
- legal_actor → assignee 자동 복사
- legal cycle → operation schedule 자동확정
- snapshot 실패 → current inventory로 fallback

### Exit

사용자가 한 화면에서 다음 차이를 즉시 이해한다.

> 이번에 무엇이 추출되었는가
> 지금 무엇을 관리하고 있는가

**HARD STOP → GPT VERIFY**

---

## OBJ-WP-08 — Cross-Surface Contract Verification

### 목적

세 Surface의 동일 의무를 비교한다.

### Fixture Matrix

최소:

- ACTION
- INSPECT
- APPOINT
- REPORT
- NOTIFY
- TRAINING
- PROHIBIT
- condition 있음/없음
- timing 있음/없음
- RAW_ONLY timing
- evidence 있음
- presentation key absent
- review_required
- NOT_APPLICABLE check_result
- 동일 조문 다중 obligation

### 검증축

```text
Identity
Legal Basis
Action
Actor
Condition
Legal Time
Type
Evidence
Customer Label
Operational Separation
```

### 필수 검증

동일 obligation에 대해:

```text
FREE 법적 의미
=
PAID 법적 의미
=
SaaS snapshot 법적 의미
```

이어야 한다.

단, 표시하는 정보량은 Surface별로 다를 수 있다.

### 실데이터 검증

fixture만으로 종료하지 않는다.

최근 저장결과에서:
- BUILDING
- MANUFACTURING
- CONSTRUCTION

각 sample을 대상으로 구조검증한다.

PAID/SaaS는 현재 운영표본이 작으므로 표본 수 부족을 성공 근거로 과장하지 않는다.

### Exit

Cross-Surface Semantic Matrix 전건 PASS.

**HARD STOP → GPT FINAL VERIFY**

---

# 5. 의존관계

```text
WP-00 Baseline
   ↓
WP-01 Presentation Semantic
   ↓
WP-02 Type Vocabulary
   ↓
WP-03 Legal Time
   ↓
 ┌───────────────┬───────────────┐
 ↓               ↓               ↓
WP-04 FREE     WP-05 PAID      WP-07 SaaS
                 ↓
              WP-06 PDF
                 ↓
              WP-08
          Cross-Surface Verify
```

FREE/PAID/SaaS를 동시에 뜯지 않는다.

공통 의미를 먼저 고친 뒤 각 Surface를 수정한다.

---

# 6. Claude 실행 규칙

각 Object 작업에서 Claude는 다음만 담당한다.

- 현재 코드 조사
- 영향 파일 조사
- 최소 구현
- 테스트 실행
- 증거 제출

Claude는 다음을 결정하지 않는다.

- 새로운 아키텍처
- Object 경계 변경
- 법적 의미 변경
- 성공 판정
- merge 여부
- deploy 여부

각 WP 완료 후 반드시 HARD STOP 한다.

---

# 7. Claude 증거 제출 규격

각 작업지시 완료 시 최소 다음 증거를 제출한다.

```text
1. BASE SHA / HEAD SHA
2. 변경 파일 목록
3. 변경 목적
4. 변경 전 계약
5. 변경 후 계약
6. 신규/수정 테스트
7. 테스트 결과
8. regression 결과
9. DB WRITE = 0 여부
10. 법령엔진 변경 = 0 여부
11. unrelated change = 0 여부
12. known limitation
```

UI 작업이면 추가:

```text
13. 주요 fixture별 render 결과
14. machine key 고객노출 0
15. absent field placeholder 생성 0
16. 모바일/데스크톱 구조 확인
```

---

# 8. GPT 검증 기준

GPT는 각 작업 후 다음을 독립검증한다.

### Contract

- Object 책임을 넘어섰는가
- 기존 canonical source를 우회했는가
- 중복 mapper를 만들었는가

### Semantics

- 법적 의미를 새로 만들었는가
- check_result를 applicability로 오해했는가
- 법적 주체와 운영 담당자를 섞었는가
- 법적 주기와 운영 일정을 섞었는가

### Data

- atom identity 유지
- fuzzy join 0
- fallback inference 0
- source text exact

### Surface

- FREE / PAID / SaaS 목적이 유지되는가
- 기계어가 고객에게 노출되는가
- 빈 UI를 불필요하게 생성하는가

---

# 9. 프로젝트 종료조건

다음 전부가 증거로 확인되어야 CLOSE 가능하다.

- P0 semantic defect 전부 해소
- 7 obligation types parity
- Legal Time consumer parity
- FREE product boundary 확정
- PAID value hierarchy 확정
- SaaS snapshot/inventory separation 보존
- PDF Premium Contract 전환
- Excel regression PASS
- Cross-Surface semantic matrix PASS
- BUILDING/MANUFACTURING/CONSTRUCTION sample PASS
- 신규 법령엔진 0
- 추정 법적 사실 0
- Owner Approval

---

# 10. 이번 단계 종료 상태

```text
RESEARCH       = COMPLETE FOR PLANNING
PLANNING       = COMPLETE
WORK PLAN      = COMPLETE

CODE CHANGE    = 0
DB WRITE       = 0
PR             = 0
MERGE          = 0
DEPLOY         = 0

NEXT           = WP-00부터 Claude 작업지시 발행
```
