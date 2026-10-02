---
title: QA Taxonomy v1
version: 1.0.0
status: DESIGN
---

# QA Taxonomy v1

## 핵심 구조

```
어디를 검사하는가   →  SERVICE > AREA
무엇을 검사하는가   →  QA TYPE
구체적으로 무엇이 정상이어야 하는가  →  QA NAME
```

예시:

```
SaaS > 마이페이지 / FUNCTIONAL / 결제내역 정상 조회
SaaS > 마이페이지 / PERFORMANCE / 마이페이지 초기 표시 3초 이내
```

## Architecture Boundary

변경 대상:
- `qa_items` metadata (컬럼 3개 추가)
- QA Control API (필터 확장 + `/admin/qa/taxonomy`)
- Admin QA 화면 (항목 목록 + 필터 + 상세)

변경하지 않는 것:
- `scenario_id` / tai-qa 실행 로직 / GitHub Actions
- `qa_runs`, `qa_run_targets`, `qa_run_results`, callback
- scheduler / Slack / effective_status 계산 / runner contract

---

## 1. DB 설계

`qa_items`에 컬럼 3개 추가. 기존 필드는 전부 유지.

```sql
service_code  TEXT  -- WWW / SAAS / ADMIN / WORKER
area_code     TEXT  -- MYPAGE / AUTH / SEARCH / ...
qa_type       TEXT  -- CHECK constraint 적용
```

최종 스키마:

| 필드 | 구분 | 설명 |
|------|------|------|
| `scenario_id` | 기존 | 실행 코드 연결 고유 ID — 변경 금지 |
| `site_code` | 기존 | 기술적 실행 Host (WWW/SAFE/ADMIN) |
| `category` | LEGACY | 기존 분류 — backfill 참고 후 별도 WO에서 제거 판단 |
| `name` | 기존 | QA 이름 |
| `description` | 기존 | 실행 내용 설명 |
| `expected_summary` | 기존 | PASS 기대조건 |
| `priority` | 기존 | P0/P1/P2 |
| `runner_type` | 기존 | PLAYWRIGHT 등 |
| `enabled` | 기존 | 활성 여부 |
| `service_code` | **NEW** | 제품/서비스 구조 분류 |
| `area_code` | **NEW** | SERVICE 아래 업무 영역 |
| `qa_type` | **NEW** | 검사 종류 (CHECK enum) |

> `service_code ≠ site_code`: site_code는 실행 인프라, service_code는 사용자 관점 분류.

---

## 2. SERVICE 표준

| code | 화면 표시 | 의미 |
|------|-----------|------|
| `WWW` | 웹사이트 | 비회원/마케팅/공개서비스 |
| `SAAS` | SaaS | 회원·고객이 사용하는 서비스 |
| `ADMIN` | Admin | 운영자 백오피스 |
| `WORKER` | 작업자앱 | 작업자 모바일 영역 |

API는 별도 SERVICE가 아닌 QA TYPE(`API`)으로 분류.

---

## 3. AREA

SERVICE 아래 업무 영역. DB CHECK enum 미적용 — 계속 확장 가능.

```
WWW
 ├ LANDING
 ├ AUTH
 ├ SEARCH
 ├ FREE_DIAGNOSIS
 └ HEADER

SAAS
 ├ AUTH
 ├ DASHBOARD
 ├ MYPAGE
 ├ LEGAL
 ├ INSPECTION
 ├ EDUCATION
 ├ BILLING
 └ SUPPORT

ADMIN
 ├ QA
 ├ OPERATIONS
 ├ CUSTOMER
 ├ BILLING
 ├ SERVICE
 ├ MARKETING
 └ STATISTICS
```

실제 QA가 존재하는 영역부터 등록.

---

## 4. QA TYPE

| Code | 표시명 | 검사 대상 | 기존 표현 |
|------|--------|-----------|-----------|
| `AVAILABILITY` | 가용성/진입 | 페이지·서비스 정상 열림 | OPEN |
| `FUNCTIONAL` | 기능 | 버튼·저장·검색·이동 등 정상 동작 | FUNCTION |
| `INTEGRATION` | 연동 | Front/API/DB/외부서비스 연결 | |
| `E2E` | 전체 흐름 | 사용자 업무 처음부터 끝까지 완주 | |
| `API` | API | status/response/schema/contract | |
| `PERFORMANCE` | 성능 | 응답시간·로딩시간 | SPEED |
| `SECURITY` | 보안 | 인증·권한·접근제어 | |
| `DATA` | 데이터 | 저장값·정합성·누락·순서 | |
| `ACCESSIBILITY` | 접근성 | 키보드·접근성 규칙 | |
| `VISUAL` | 화면 | 레이아웃·시각 회귀 | |

용어 전환:
```
OPEN     → AVAILABILITY
FUNCTION → FUNCTIONAL
SPEED    → PERFORMANCE
```

`SMOKE`, `REGRESSION`, `RELEASE`는 QA TYPE이 아닌 **Test Suite** 개념 — `qa_type`과 혼용 금지.

---

## 5. QA NAME 규칙

공식: `[검사 대상] + [기대 상태/행동]`

| 좋은 예 | 피해야 할 예 |
|---------|-------------|
| 마이페이지 정상 진입 | 마이페이지 테스트 |
| 결제내역 정상 조회 | 기능 테스트 |
| 로그인 후 인증 상태 유지 | 로그인 QA |
| 대시보드 초기 표시 3초 이내 | OPEN 테스트 |

화면에서 SERVICE > AREA / QA TYPE이 이미 보이므로 이름에 중복 기재 불필요.

---

## 6. 기존 10개 QA Backfill 예

`scenario_id`는 절대 변경 금지 (runner contract).

backfill 전 tai-qa scenario source로 실제 검증 대상 최종 확인 필수.

| scenario_id | service_code | area_code | qa_type | QA NAME (안) |
|-------------|-------------|-----------|---------|--------------|
| P0-WWW-001 | WWW | LANDING | AVAILABILITY | 마케팅 사이트 메인 정상 진입 |
| P0-DIAG-001 | WWW | FREE_DIAGNOSIS | AVAILABILITY | 무료 법령진단 정상 진입 |
| P0-SRCH-001 | WWW | SEARCH | AVAILABILITY | 통합검색 정상 진입 |
| P0-SRCH-002 | WWW | SEARCH | FUNCTIONAL | 통합검색 결과 섹터 순서 유지 |
| P0-MYP-001 | SAAS | MYPAGE | AVAILABILITY | 마이페이지 대시보드 정상 진입 |
| P0-MYP-005 | SAAS | MYPAGE | FUNCTIONAL | 결제내역 정상 조회 |
| P0-SAAS-001 | SAAS | AUTH | E2E | 로그인 후 대시보드 정상 진입 |
| P0-WWW-003 | WWW | AUTH | E2E | 회원 로그인 완료 |
| P0-WWW-004 | WWW | HEADER | FUNCTIONAL | 로그인 후 헤더 인증 상태 유지 |
| P0-WWW-005 | WWW | HEADER | FUNCTIONAL | 헤더에서 마이페이지 정상 이동 |

---

## 7. API 변경

### 기존 필터 확장

```
GET /admin/qa/items

기존 (compatibility 유지)
  site_code
  category

추가
  service_code
  area_code
  qa_type
  priority
  effective_status
  enabled
```

### 신규 엔드포인트

```
GET /admin/qa/taxonomy

반환:
{
  "services": [...],
  "areas": { "WWW": [...], "SAAS": [...], ... },
  "qa_types": [...]
}
```

Frontend에서 `CATEGORY_OPTIONS` 하드코딩 제거 가능.

---

## 8. Admin 화면

### 항목 목록 테이블

| 상태 | 위치 | QA 종류 | QA 이름 | Priority | Runner | 마지막 QA | 소요시간 | 최근 오류 | 스케줄 | 활성 |
|------|------|---------|---------|----------|--------|-----------|----------|-----------|--------|------|

### 필터 UI

```
서비스 [SaaS ▼]  영역 [마이페이지 ▼]  QA 종류 [기능 ▼]  Priority [P0 ▼]  상태 [PASS ▼]  활성 [활성 ▼]
```

서비스 선택 → 영역 목록 종속 좁혀짐.

### 상세 화면 레이아웃

```
SaaS > 마이페이지
FUNCTIONAL
결제내역 정상 조회

상태: PASS   Priority: P0

───────────────────────
Scenario ID   P0-MYP-005
Host          WWW
Runner        PLAYWRIGHT
Description   ...
Expected      ...
Schedule      DAILY 08:00
```

기술 정보(`scenario_id`, `site_code`, `runner_type`)는 하단 섹션.

---

## 9. 구현 순서

1. **DB + Backfill**: `service_code`, `area_code`, `qa_type` 컬럼 추가 + 기존 10건 source 확인 후 backfill
2. **API**: `/admin/qa/items` 필터 확장 + `/admin/qa/taxonomy` 신규
3. **Admin UI**: 항목 목록 / 필터 / 상세 화면 변경
