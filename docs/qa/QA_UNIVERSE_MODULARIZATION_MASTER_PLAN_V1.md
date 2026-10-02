---
title: QA Universe Modularization Master Plan v1
version: 1.0.0
work_order: WO-QA-UNIVERSE-MODULARIZATION-001
status: DESIGN
---

# WO-QA-UNIVERSE-MODULARIZATION-001
## QA Universe Modularization Master Plan v1

### 최종 목표

```
TAI 전체 서비스
        ↓
SERVICE > AREA
        ↓
QA TYPE
        ↓
QA ITEM / QA NAME
        ↓
Reusable QA Module
        ↓
Scenario
        ↓
Runner
        ↓
Result
        ↓
Admin QA Control
```

최종 산출물 4개:

| 문서 | 내용 |
|------|------|
| `QA_TAXONOMY_V1` | QA를 어떻게 분류하는가 |
| `QA_UNIVERSE_CATALOG_V1` | TAI에서 무엇을 검사해야 하는가 |
| `QA_MODULE_CATALOG_V1` | 반복 검사를 어떻게 재사용하는가 |
| `tai-qa scenarios` | 실제 자동검사는 어떻게 실행되는가 |

---

## 전체 작업 순서

```
STEP 0  전체 Source / Route / API 조사
  ↓
STEP 1  QA Taxonomy 구조 완성 (DB → API → Admin)
  ↓
STEP 2  기존 10 QA Backfill
  ↓
STEP 3  TAI 전체 QA Universe 작성 (구현 없음)
  ↓
STEP 4  QA Universe Review (중복/누락/불필요 제거)
  ↓
STEP 5  반복 Pattern 추출
  ↓
STEP 6  Reusable QA Module 설계
  ↓
STEP 7  공용 Module 구현
  ↓
STEP 8  전체 Scenario 구현 (Scenario = Module 조합)
  ↓
STEP 9  P0부터 자동화 연결
  ↓
STEP 10 P1/P2 확대
  ↓
STEP 11 Admin Coverage 관제
  ↓
STEP 12 FULL REGRESSION
```

### 핵심 Gate

```
Taxonomy 완성
→ GPT 독립검증
→ 전체 Source 조사
→ QA Universe Catalog 작성
→ GPT + Owner 검토
→ Module 설계
→ 구현
```

Taxonomy 구현 후 마음대로 QA 구현 금지. QA 목록이 확정되어야 어떤 Module이 필요한지 알 수 있다.

---

## Phase 0 — 기준선 동결 및 조사

구현하지 않음. 실제 조사만.

### 조사 대상 repo

```
tai-www
tai-admin
tai-api
tai-qa
```

작업자 앱은 실제 repo/runtime 확인 후 `WORKER` 서비스 코드 추가. 추측으로 넣지 않음.

### 조사 항목

- 실제 Route/Page
- API Endpoint
- 주요 Form/Action
- 로그인/권한 경계
- 업무 Flow
- 외부 연동
- 중요 DB 결과
- 현재 QA Scenario
- 기존 E2E/fixture/test
- 운영 Scheduler 대상

### 산출물

```
docs/qa/QA_SURFACE_INVENTORY_V1.md
```

컬럼: `SERVICE | AREA | SURFACE | ROUTE/API | ACTION | CRITICALITY`

### Exit Condition

```
실제 서비스 Surface 전수조사 완료
추측 항목 = 0
Production mutation = 0
```

---

## Phase 1 — QA Taxonomy Canonical

→ 상세 설계: `docs/qa/QA_TAXONOMY_V1.md`

### DB 변경

`qa_items`에 컬럼 3개 추가:

```sql
service_code  TEXT CHECK (service_code IN ('WWW','SAAS','ADMIN','WORKER'))
area_code     TEXT  -- 제한 없음, 대문자 코드 규칙만 강제
qa_type       TEXT CHECK (qa_type IN (
  'AVAILABILITY','FUNCTIONAL','INTEGRATION','E2E','API',
  'PERFORMANCE','SECURITY','DATA','ACCESSIBILITY','VISUAL'
))
```

기존 `category` = LEGACY 유지 (consumer 전환 완료 후 별도 WO에서 제거 판단).

### API 변경

- `GET /admin/qa/items` — `service_code`, `area_code`, `qa_type` 필터 추가
- `GET /admin/qa/taxonomy` 신규 — services/areas/qa_types 반환

### Admin 변경

- 항목 목록: `상태 / 위치(SERVICE>AREA) / QA종류 / QA이름 / Priority / Runner / 최근실행 / 소요시간 / 오류 / 스케줄 / 활성`
- 필터: 서비스 선택 → 영역 목록 종속 좁혀짐
- 상세: 업무 정보 상단, 기술 정보(`scenario_id`, `site_code` 등) 하단

### Phase 1 Exit

```
기존 10 Scenario 실행 결과 불변
scheduler / callback / GitHub workflow / qa_runs schema 불변
scenario_id 불변
```

---

## Phase 2 — TAI 전체 QA Universe 작성

Phase 0 Surface 조사 완료 후 착수. Phase 1 구조 완성 후 착수.

각 Surface마다 10개 질문 적용:

```
1. 열려야 하는가?               → AVAILABILITY
2. 어떤 기능이 동작해야 하는가?  → FUNCTIONAL
3. 다른 시스템과 연결되는가?     → INTEGRATION
4. 업무 전체 Flow가 완주되어야 하는가? → E2E
5. API 계약이 있는가?            → API
6. 속도 기준이 필요한가?         → PERFORMANCE
7. 권한/보안 경계가 있는가?      → SECURITY
8. 데이터 정합성을 확인해야 하는가? → DATA
9. 접근성 대상인가?              → ACCESSIBILITY
10. Visual regression 가치가 있는가? → VISUAL
```

### 산출물

```
docs/qa/QA_UNIVERSE_CATALOG_V1.md
```

컬럼:

```
QA_ID | SERVICE | AREA | QA_TYPE | QA_NAME
SOURCE_ROUTE/API | PRECONDITION | ACTION | EXPECTED
PRIORITY | PROD_SAFE | AUTOMATABLE | MODULE_PATTERN | RUNNER
```

이 문서 = TAI가 검사해야 하는 전체 QA의 SoT.

---

## Phase 3 — QA Pattern 분석

Universe 완성 후 모듈화. 처음부터 Module 상상하여 만들지 않음.

전체 Catalog에서 같은 실행 형태 집계:

```
페이지 접속 + status + 핵심요소 확인   → PATTERN-PAGE-OPEN
로그인 후 지정 메뉴 이동               → PATTERN-AUTH-NAVIGATE
API status + response contract         → PATTERN-API-CONTRACT
...
```

### 모듈화 원칙

```
같은 검증 방식 2~3회 이상 반복 → 공용 Module 후보
1회만 존재                    → Scenario local
```

---

## Phase 4 — Reusable QA Module Library

Phase 3 결과로 확정. 예상 Module Family (실제 생성 여부는 Phase 3 기준):

```
Navigation       open page, route transition, redirect
Authentication   login, logout, session 유지, protected route
Functional       click/action, form submit, save/update, delete
Search           query, empty result, ordering, filter
API              status, response contract, required fields, error
Integration      frontend→API, API→DB, external adapter
Data             displayed data consistency, canonical field
Performance      page load, API response duration
Security         unauthenticated denial, unauthorized denial, tenant boundary
Visual           critical page visual regression
Accessibility    critical interaction accessibility
```

핵심: Service별 복제 금지. `authenticate(profile)` 처럼 Parameter 기반 재사용.

---

## Phase 5 — Scenario = Module 조합

최종 Scenario는 복잡한 코드 직접 보유 금지.

예:

```
SaaS > 마이페이지 / FUNCTIONAL / 결제내역 정상 조회

AUTHENTICATE(saas_user)
→ OPEN(mypage/payment-history)
→ ASSERT_PAGE_READY()
→ ASSERT_LIST_VISIBLE()
→ ASSERT_NO_FATAL_ERROR()
```

URL/인증방식 변경 시 공용 Module 한 곳만 수정.

---

## Phase 6 — BDD 구조 정리

기존 `tai-qa` 구조 유지:

```
features/**/*.feature
steps/**/*.steps.ts
fixtures/qa.fixture.ts
```

목표:

```
Feature   = 업무 의미
Scenario  = QA Item
Steps     = 공용 의미 단위
Fixture   = 기술 구현 재사용
```

`.feature` 파일에 Playwright 구현 세부사항 금지.

```gherkin
Scenario: 결제내역 정상 조회
  Given QA SaaS 회원으로 로그인한다
  When 마이페이지 결제내역으로 이동한다
  Then 결제내역 화면이 정상 표시된다
```

---

## Phase 7 — Priority / Suite 구성

QA TYPE(무엇을 검사)과 Suite(언제/어떤 묶음) 분리.

| Suite | 대상 |
|-------|------|
| `P0_SMOKE` | AVAILABILITY + 핵심 FUNCTIONAL + 핵심 E2E |
| `DAILY` | P0 전체 |
| `RELEASE` | P0 전체 + 영향 AREA P1 |
| `FULL_REGRESSION` | 전체 Functional + API + Data + Security-safe + Performance |

---

## Phase 8 — 실행 전략

### Production Safety 원칙

Production에서 허용:

```
READ / LOGIN / NAVIGATE / SEARCH / SAFE FORM / NON-DESTRUCTIVE
```

Production에서 금지 (fixture/staging 분리):

```
실제 결제 / 삭제 / 대량등록 / 외부 발송
```

---

## Phase 9 — Admin 운영 화면 완성

v1: `SERVICE → AREA → QA TYPE` 필터로 운영.  
항목 증가 후: Tree/Group UI 추가.

최종 목표 화면:

```
SaaS
 ├ 대시보드        AVAILABILITY 1/1 PASS  FUNCTIONAL 4/4 PASS
 ├ 마이페이지      AVAILABILITY 1/1       FUNCTIONAL 7/8       SECURITY 2/2
 └ 점검
```

---

## Phase 10 — Coverage 관제

```
SERVICE   AREA        Required  Automated  PASS
SAAS      MYPAGE      12        10         9
SAAS      INSPECTION  28        20         20
WWW       SEARCH       8         8          8
```

지표:

```
Required QA / Automated QA / Automation Coverage % / PASS Coverage % / P0 Coverage %
```

목표: "테스트 수"가 아니라 "필요한 QA 중 얼마나 자동화됐고 현재 얼마나 정상인가".
