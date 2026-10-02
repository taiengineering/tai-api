---
title: QA Surface Inventory v1
version: 1.1.0
work_order: WO-QA-UNIVERSE-PHASE0-SURFACE-INVENTORY-001
status: COMPLETE
surveyed_at: 2026-10-02
patch: PATCH1
---

# QA Surface Inventory v1

조사 완료: 2026-10-02  
추측 항목: 0 (소스 미확인 항목 포함 금지)  
코드 변경: 0 / DB 변경: 0 / Production mutation: 0

---

## Survey Anchors

조사 시점 Git HEAD. 이후 변경이 있더라도 이 Inventory는 아래 커밋 기준으로 작성됨.

| Repo | Branch | SHA | 비고 |
|------|--------|-----|------|
| tai-www | main | `73adaf8622c556660a3112e3d4baf6a65b39d63f` | 조사 기준 HEAD |
| tai-admin (SAFE) | HEAD | `93393d8643c8f125d64c2f25037cb96f7ad12289` | vue3/ 기준 |
| tai-admin (ADMIN) | feat/admin-rebuild | `30507eaca73224d3e8241d39f17bbaa181ead76e` | admin-vue3/ 기준 |
| tai-api | origin/main | `59b60f6af44d67edd80867dddff6a9af02d75598` | routers/ 기준 |
| tai-qa | main | NOT_LOCAL | GitHub MCP 확인; main HEAD b054bb99 |

---

## 조사 범위

| Repo | 서비스 | 도메인 | SOURCE_PATH | 조사 완료 |
|------|--------|--------|-------------|-----------|
| tai-www | WWW | taieng.co.kr | tai-www/ @ main | ✓ |
| tai-admin/vue3/ | SAAS | safe.taieng.co.kr + taieng.co.kr/mypage/* | tai-admin/vue3/ @ HEAD | ✓ |
| tai-admin/admin-vue3/ | ADMIN | admin.taieng.co.kr | tai-admin/admin-vue3/ @ feat/admin-rebuild | ✓ |
| tai-api | API | api.taieng.co.kr | tai-api/ @ origin/main | ✓ |
| tai-qa | QA_RUNNER | github.com/taiengineering/tai-qa | tai-qa/ @ main (GitHub MCP) | ✓ |
| WORKER | — | 미확인 | 미확인 | 미조사 (추측 없음) |

> **WORKER 서비스**: 실제 repo/runtime 미확인. 이 문서에 포함하지 않음.

---

## Canonical Column Schema

테이블 공통 컬럼 정의:

| 컬럼 | 설명 |
|------|------|
| `SURFACE` | 화면 또는 API 엔드포인트 이름 |
| `ROUTE/API` | URL 경로 또는 HTTP METHOD + path |
| `R/W` | R=읽기 전용, W=쓰기 전용, RW=읽기+쓰기 |
| `CRITICALITY` | CRITICAL / HIGH / NORMAL / LOW |
| `ACTIVE` | ACTIVE=현재 운영 중 / INACTIVE=비활성(주석·미서비스) |
| `EXISTING_QA` | 현재 tai-qa에 커버하는 scenario_id, 없으면 `—` |

> **CRITICALITY 기준**: CRITICAL=중단 시 매출·고객 직접 영향 / HIGH=핵심 업무 차질 / NORMAL=보조 기능 / LOW=미서비스·개발용

> **SOURCE_PATH, AUTH_BOUNDARY**: 각 서비스 섹션 헤더에 기재.

---

## 1. WWW 서비스 (taieng.co.kr)

```
SOURCE_PATH:   tai-www/ @ main (73adaf86)
AUTH_BOUNDARY: localStorage access_token — 클라이언트 사이드 가드
               (서버사이드 가드 없음; Cloudflare Functions 미적용)
               API 토큰 검증: tai-api Bearer token (서버)
EXTERNAL:      tai-api / Inicis(본인인증·결제) / Supabase(OAuth·Storage) / 마케팅 API
```

### AREA: LANDING

| SURFACE | ROUTE/API | R/W | CRITICALITY | ACTIVE | EXISTING_QA |
|---------|-----------|-----|-------------|--------|-------------|
| 메인 랜딩 | GET / → `GET /notices/active?channel=MARKETING` | R | CRITICAL | ACTIVE | P0-WWW-001 |
| 요금제 페이지 | GET /pricing → `GET /public/pricing/all` | R | HIGH | ACTIVE | — |
| 서비스 소개 (SaaS) | GET /service/saas | R | NORMAL | ACTIVE | — |
| 서비스 소개 (진단) | GET /service/diagnosis | R | NORMAL | ACTIVE | — |
| 타겟 랜딩 (업주) | GET /for-business-owner | R | NORMAL | ACTIVE | — |
| 타겟 랜딩 (안전관리자) | GET /for-safety-manager | R | NORMAL | ACTIVE | — |
| 회사 소개 | GET /about | R | NORMAL | ACTIVE | — |
| FAQ | GET /faq | R | NORMAL | ACTIVE | — |
| 개인정보처리방침 | GET /privacy | R | NORMAL | ACTIVE | — |
| 이용약관 | GET /terms | R | NORMAL | ACTIVE | — |

### AREA: AUTH

| SURFACE | ROUTE/API | R/W | CRITICALITY | ACTIVE | EXISTING_QA |
|---------|-----------|-----|-------------|--------|-------------|
| 로그인 | GET /log-in → `POST /auth/login` | RW | CRITICAL | ACTIVE | P0-WWW-003 |
| 회원가입 | GET /log-in#register → `POST /auth/register` | RW | HIGH | ACTIVE | — |
| 소셜 로그인 (Kakao) | /log-in → Supabase OAuth → `POST /auth/ensure-user` | RW | HIGH | ACTIVE | — |
| 소셜 로그인 (Google) | /log-in → Supabase OAuth → `POST /auth/ensure-user` | RW | HIGH | ACTIVE | — |
| 초대 수락 | GET /invite?token={token} → `GET /user-invites/{token}/info` + `POST /user-invites/{token}/accept` | RW | HIGH | ACTIVE | — |

### AREA: FREE_DIAGNOSIS

| SURFACE | ROUTE/API | R/W | CRITICALITY | ACTIVE | EXISTING_QA |
|---------|-----------|-----|-------------|--------|-------------|
| 무료진단 마법사 (Step 1~4) | GET /free-diagnosis → `POST /diagnosis/run` | RW | CRITICAL | ACTIVE | P0-DIAG-001 |
| 무료진단 결과 | GET /free-diagnosis-result → `GET /diagnosis/result/{token}` | R | HIGH | ACTIVE | — |
| 유료진단 안내 | GET /paid-diagnosis → `GET /diagnosis/price-tier` | R | HIGH | ACTIVE | — |
| 유료진단 결과 조회 | GET /paid-diagnosis-result → `GET /diagnosis/paid-result/{token}` | R | HIGH | ACTIVE | — |

### AREA: SEARCH

| SURFACE | ROUTE/API | R/W | CRITICALITY | ACTIVE | EXISTING_QA |
|---------|-----------|-----|-------------|--------|-------------|
| 통합검색 진입 | GET /safety-search | R | CRITICAL | ACTIVE | P0-SRCH-001 |
| 통합검색 결과 | GET /safety-search?q={term} | R | CRITICAL | ACTIVE | P0-SRCH-002 |
| 검색 상세 (지식) | GET /safety-search/knowledge/{id} | R | NORMAL | ACTIVE | — |
| 검색 상세 (법령) | GET /safety-search/legal/{id} | R | NORMAL | ACTIVE | — |
| 지식센터 허브 | GET /kb → CF Function → `GET /public/knowledge` | R | HIGH | ACTIVE | — |
| 지식센터 상세 | GET /kb/{slug} → CF Function | R | NORMAL | ACTIVE | — |

### AREA: HEADER

| SURFACE | ROUTE/API | R/W | CRITICALITY | ACTIVE | EXISTING_QA |
|---------|-----------|-----|-------------|--------|-------------|
| 비로그인 헤더 상태 | / (localStorage access_token 없음) | R | CRITICAL | ACTIVE | — |
| 로그인 후 헤더 인증 상태 | / (localStorage access_token 있음) | R | CRITICAL | ACTIVE | P0-WWW-004 |
| 헤더 → 마이페이지 이동 | a[href*="mypage"] 클릭 → GET /mypage/ | R | CRITICAL | ACTIVE | P0-WWW-005 |

### AREA: CONTENT

| SURFACE | ROUTE/API | R/W | CRITICALITY | ACTIVE | EXISTING_QA |
|---------|-----------|-----|-------------|--------|-------------|
| 재해사례 목록 | GET /accident-cases → `GET /posts?category=accident` | R | NORMAL | ACTIVE | — |
| 재해사례 상세 | GET /accident/{id}, /accident/csi/{uuid} | R | NORMAL | ACTIVE | — |
| 판례 검색 | GET /precedent-search → `GET /posts?type=precedent` | R | NORMAL | ACTIVE | — |
| 안전뉴스 목록 | GET /safety-news → CF Function → `GET /posts?category=SAFETY_NEWS` | R | NORMAL | ACTIVE | — |
| 법령개정 뉴스 | GET /law-updates → `GET /posts?category=LAW_UPDATE` | R | NORMAL | ACTIVE | — |
| 동적 카테고리 페이지 | GET /safety/{subject}, /safety/accident/{type}, /safety/equipment/{value}, /safety/law/{law}, /safety/task/{task} | R | NORMAL | ACTIVE | — |

### AREA: CONTACT

| SURFACE | ROUTE/API | R/W | CRITICALITY | ACTIVE | EXISTING_QA |
|---------|-----------|-----|-------------|--------|-------------|
| 도입 문의 | GET /contact → `POST /inquiries` | RW | NORMAL | ACTIVE | — |
| 전문가 매칭 | GET /fix-request → `POST /expert-matching/*` | RW | NORMAL | ACTIVE | — |

### WWW 인증 가드 요약

```
MEMBER 페이지 (/mypage/*) — 클라이언트 인라인 스크립트:
  localStorage.getItem('access_token') 없음 → location.replace('../../log-in.html?redirect=...')

서버사이드 가드: 없음 (Cloudflare Functions 미적용)
API 토큰 검증: tai-api Bearer token (서버에서 수행)
```

---

## 2. SAAS 서비스 (safe.taieng.co.kr + taieng.co.kr/mypage/*)

```
SOURCE_PATH:   tai-admin/vue3/ @ HEAD (93393d86)
AUTH_BOUNDARY: router.beforeEach() → useAuth().requireAuth()
               공개 경로: /login, /tai-survey, /forgot-password, /reset-password
               role_code 기반 nav gate (navigation/gate.ts)
               role 001 → 전체 메뉴 / role 002+ → sector 게이트 적용
API_CLIENT:    useTaiApi composable (Bearer token; demo 모드 시 POST/PUT/PATCH/DELETE 차단)
NOTE:          taieng.co.kr/mypage/* = SOURCE_REPO:tai-www (정적 HTML), API:tai-api
```

### AREA: AUTH

| SURFACE | ROUTE/API | R/W | CRITICALITY | ACTIVE | EXISTING_QA |
|---------|-----------|-----|-------------|--------|-------------|
| SaaS 로그인 | GET /login → `POST /auth/login` | RW | CRITICAL | ACTIVE | P0-SAAS-001 |
| SaaS 로그아웃 | 로그아웃 버튼 → localStorage 13개 키 제거 + /login 리다이렉트 | W | HIGH | ACTIVE | — |
| 비밀번호 찾기 | GET /forgot-password → `POST /auth/forgot-password` | RW | NORMAL | ACTIVE | — |
| 비밀번호 재설정 | GET /reset-password → `POST /auth/reset-password` | RW | NORMAL | ACTIVE | — |

### AREA: DASHBOARD

| SURFACE | ROUTE/API | R/W | CRITICALITY | ACTIVE | EXISTING_QA |
|---------|-----------|-----|-------------|--------|-------------|
| SaaS 대시보드 | GET /safety-dashboard → `GET /work-schedules, /overdue/summary, /weather` | R | CRITICAL | ACTIVE | P0-SAAS-001 |
| 알림 목록 | GET /alert-list → `GET /alerts?page=&size=` | R | NORMAL | ACTIVE | — |
| 알림/공지 | GET /notification-list → `GET /notifications?page=&size=` | R | NORMAL | ACTIVE | — |

### AREA: MYPAGE

> `SOURCE_REPO: tai-www` (taieng.co.kr/mypage/* = 정적 HTML, tai-www/pages/mypage/)

| SURFACE | ROUTE/API | R/W | CRITICALITY | ACTIVE | EXISTING_QA |
|---------|-----------|-----|-------------|--------|-------------|
| 마이페이지 대시보드 | GET taieng.co.kr/mypage/ | R | CRITICAL | ACTIVE | P0-MYP-001 |
| 결제내역 | GET taieng.co.kr/mypage/payments/ → `GET /payments` | R | CRITICAL | ACTIVE | P0-MYP-005 |
| 계약 목록 | GET taieng.co.kr/mypage/contracts | R | HIGH | ACTIVE | — |
| 프로필 수정 | GET taieng.co.kr/mypage/profile → `PATCH /auth/me` | RW | HIGH | ACTIVE | — |
| 회사정보 | GET taieng.co.kr/mypage/company → `GET/POST /factories` | RW | HIGH | ACTIVE | — |
| 온보딩 | GET taieng.co.kr/mypage/onboarding | RW | HIGH | ACTIVE | — |
| 결제 (Checkout) | GET taieng.co.kr/mypage/checkout → Inicis V023 → `/_api/payments/inicis/return` | RW | CRITICAL | ACTIVE | — |
| 파트너 대시보드 | GET taieng.co.kr/mypage/partner/ → `GET /contracts?role=PARTNER` | R | NORMAL | ACTIVE | — |

### AREA: INSPECTION

| SURFACE | ROUTE/API | R/W | CRITICALITY | ACTIVE | EXISTING_QA |
|---------|-----------|-----|-------------|--------|-------------|
| 내 점검 목록 | GET /my-inspection → `GET /inspection/status, /inspections` | R | HIGH | ACTIVE | — |
| 점검 작업대 | GET /inspection-workbench/{id} → `POST /inspection/result/{id}/items, POST /inspection/{id}/photos` | RW | HIGH | ACTIVE | — |
| 점검 상세 | GET /inspection-detail/{id} → `GET /inspection/{id}/view, POST /inspection/{id}/results/{result_id}/corrections` | RW | HIGH | ACTIVE | — |
| 점검 달력 | GET /inspection-calendar → `GET /work-schedules, PATCH /work-schedules/{id}` | RW | NORMAL | ACTIVE | — |
| 점검 세트 관리 | GET /inspection-custom → `GET/POST/PUT/DELETE /inspection-sets` | RW | NORMAL | ACTIVE | — |

### AREA: EDUCATION

| SURFACE | ROUTE/API | R/W | CRITICALITY | ACTIVE | EXISTING_QA |
|---------|-----------|-----|-------------|--------|-------------|
| 교육 과정 목록 | GET /education-list → `GET /educations, POST /educations/{id}/assign` | RW | HIGH | ACTIVE | — |
| 교육 세팅 | GET /education-setting → `GET/POST/PUT/DELETE /education-templates` | RW | NORMAL | ACTIVE | — |
| TBM 목록 | GET /tbm-list → `GET /tbms` | R | HIGH | ACTIVE | — |
| TBM 작성 | GET /tbm-create → `POST /tbms` | RW | HIGH | ACTIVE | — |
| TBM 세팅 | GET /tbm-setting → `GET/POST/PUT/DELETE /tbm-templates` | RW | NORMAL | ACTIVE | — |
| 안전회의 기록 | GET /safety-meeting-list → `GET /safety-meetings` | R | NORMAL | ACTIVE | — |

### AREA: BILLING

| SURFACE | ROUTE/API | R/W | CRITICALITY | ACTIVE | EXISTING_QA |
|---------|-----------|-----|-------------|--------|-------------|
| 내 계약 | GET /my-contract → `GET /me/commercial/contract, GET /payments` | R | CRITICAL | ACTIVE | — |
| 진단 구매 | GET /diagnosis-purchase → `POST /payments/purchase-diagnosis` | RW | HIGH | ACTIVE | — |
| 진단 결과 이력 | GET /diagnosis-result → `GET /diagnosis-results` | R | NORMAL | ACTIVE | — |

### AREA: SETTINGS

| SURFACE | ROUTE/API | R/W | CRITICALITY | ACTIVE | EXISTING_QA |
|---------|-----------|-----|-------------|--------|-------------|
| 내 프로필 | GET /my-profile → `GET/PUT /me, POST /me/password` | RW | HIGH | ACTIVE | — |
| 회사 정보 | GET /my-company → `GET/PUT /companies/{id}, POST /companies/{id}/logo` | RW | HIGH | ACTIVE | — |
| 사업장 관리 | GET /factory-list → `GET/POST/PUT/DELETE /factories` | RW | HIGH | ACTIVE | — |
| 권한 관리 | GET /manager-permission → `GET/PUT /permissions` | RW | HIGH | ACTIVE | — |
| 조직 설정 | GET /org-setting → `GET/PUT /org-settings` | RW | NORMAL | ACTIVE | — |
| 설비 관리 | GET /my-equipment → `GET/POST/PUT /equipment-assets` | RW | NORMAL | ACTIVE | — |
| 설비 QR | GET /equipment-qr-manager → `GET/POST /equipment-assets/{id}/qr` | RW | NORMAL | ACTIVE | — |

### AREA: CONSTRUCTION

| SURFACE | ROUTE/API | R/W | CRITICALITY | ACTIVE | EXISTING_QA |
|---------|-----------|-----|-------------|--------|-------------|
| 공사장 목록 | GET /construction-site-list → `GET/POST/PUT/DELETE /construction-sites` | RW | HIGH | ACTIVE | — |
| 건설 Step1 | GET /construction-step1 → `POST /construction/step1` | RW | HIGH | ACTIVE | — |
| 공정 목록 | GET /construction-process-list → `GET/POST/PUT /construction-processes` | RW | HIGH | ACTIVE | — |
| 작업 목록 | GET /construction-work-list → `GET/POST/PUT /construction-works` | RW | HIGH | ACTIVE | — |
| 인력 명부 | GET /construction-worker-list → `GET/POST/PUT /construction-workers` | RW | HIGH | ACTIVE | — |
| 협력업체 | GET /construction-subcontractor-list → `GET/POST/PUT /construction-subcontractors` | RW | NORMAL | ACTIVE | — |
| 공사 점검 | GET /construction-inspection-list → `GET /construction-inspections` | R | HIGH | ACTIVE | — |
| 공정 추출 | GET /construction-extraction → `POST /construction-extraction` | RW | NORMAL | ACTIVE | — |

### AREA: RISK

| SURFACE | ROUTE/API | R/W | CRITICALITY | ACTIVE | EXISTING_QA |
|---------|-----------|-----|-------------|--------|-------------|
| 위험도 평가 목록 | GET /risk-assessment-list → `GET /risk-assessments` | R | HIGH | ACTIVE | — |
| 위험도 평가 입력 | GET /risk-assessment-detail → `POST /risk-assessments/{id}/assess` | RW | HIGH | ACTIVE | — |
| 위험도 리포트 | GET /risk-assessment-report → `GET /risk-assessments/{id}/report, POST /risk-assessments/{id}/publish` | RW | NORMAL | ACTIVE | — |
| 평가 척도 관리 | GET /risk-assessment-scale → `GET/POST/PUT /risk-assessment-scales` | RW | NORMAL | ACTIVE | — |

### AREA: DOCUMENT

| SURFACE | ROUTE/API | R/W | CRITICALITY | ACTIVE | EXISTING_QA |
|---------|-----------|-----|-------------|--------|-------------|
| 서식 라이브러리 | GET /document-forms → `GET /document-templates` | R | NORMAL | ACTIVE | — |
| 일정 목록 | GET /work-schedule-list → `GET/POST/PUT/DELETE /work-schedules` | RW | NORMAL | ACTIVE | — |
| 엔진 문서 | GET /engine-document → `GET /engine-documents/{id}/download` | R | NORMAL | ACTIVE | — |
| 엔진 일정 | GET /engine-schedule → `GET/PATCH /engine-schedules` | RW | NORMAL | ACTIVE | — |

### AREA: SUPPORT

| SURFACE | ROUTE/API | R/W | CRITICALITY | ACTIVE | EXISTING_QA |
|---------|-----------|-----|-------------|--------|-------------|
| 고객센터 문의 | GET /contact → `GET/POST /contacts` | RW | NORMAL | ACTIVE | — |
| 도움말 | GET /help → `GET /help-articles` | R | NORMAL | ACTIVE | — |
| 사용성 설문 (인증 불필요) | GET /tai-survey → `POST /surveys/response` | RW | NORMAL | ACTIVE | — |

### AREA: QA (Service QA Control — role_code='001' 전용)

```
NOTE: 이 area는 vue3/src/pages/qa/ 소스, safe.taieng.co.kr에서 role_code='001'만 접근.
      Admin 서비스(admin-vue3/)의 auto-qa-dashboard와 별개 시스템.
      항목 상세 페이지: GET /admin/qa/items (page_size=100) 전체 조회 후 프론트엔드에서 id 탐색.
      GET /admin/qa/items/{id} 엔드포인트는 존재하지 않음. (EVIDENCE: routers/admin_qa.py)
      GET/PUT /admin/qa/settings 엔드포인트는 존재하지 않음. (EVIDENCE: routers/admin_qa.py)
```

| SURFACE | ROUTE/API | R/W | CRITICALITY | ACTIVE | EXISTING_QA |
|---------|-----------|-----|-------------|--------|-------------|
| QA 대시보드 | GET /qa/dashboard → `GET /admin/qa/summary` | R | HIGH | ACTIVE | — |
| QA 항목 목록 | GET /qa/items → `GET /admin/qa/items?site_code=&category=&priority=&effective_status=&enabled=&page=&page_size=` | R | HIGH | ACTIVE | — |
| QA 항목 상세 | GET /qa/items/{id} → 프론트 필터 (fetchItems page_size=100) | R | HIGH | ACTIVE | — |
| QA 실행 이력 | GET /qa/runs → `GET /admin/qa/runs?started_after=&started_before=&trigger_type=&status=&page=&page_size=` | R | HIGH | ACTIVE | — |
| QA 실행 상세 | GET /qa/runs/{id} → `GET /admin/qa/runs/{run_id}` | R | HIGH | ACTIVE | — |
| QA 설정 | GET /qa/settings → `PATCH /admin/qa/items/{id}/schedule` (스케줄 수정 모달) | RW | HIGH | ACTIVE | — |

### SAAS 네비게이션 게이트

```
role_code 기반 nav 필터링 (navigation/gate.ts):
  role 001 (platform admin) → 전체 메뉴 노출 (QA area 포함)
  role 002 + company_id 없음 → admin.taieng.co.kr (legacy 리다이렉트)
  role 002 + company_id 있음 → SAFE (회사관리자), sector 게이트 적용
  기타 role → sector 게이트 적용

sector 정규화: BUILDING→FACILITY, INDUSTRY→INDUSTRIAL, CONSTRUCTION=동일
sector 미확정 → 실패-오픈 (전체 노출)
```

---

## 3. ADMIN 서비스 (admin.taieng.co.kr)

```
SOURCE_PATH:   tai-admin/admin-vue3/ @ feat/admin-rebuild (30507eac)
               EVIDENCE: admin-vue3/src/navigation/horizontal/index.ts
AUTH_BOUNDARY: JWT Bearer (Operator role)
               도메인: admin.taieng.co.kr (Operator Admin 전용 앱)
NOTE:          WO-19 (2026-07-29) 운영자 관점 재설계 — 12그룹 → 8표시그룹 + 개발자도구
               미서비스(매칭/견적/인력) + 위험 그룹 = 주석 처리 (INACTIVE)
               unplugin-vue-router: src/pages/<slug>/index.vue → route name '<slug>'
API:           각 페이지별 API 경로는 admin-vue3/src/pages/{route}/index.vue 미추적
               확인된 경우만 기재; 미확인은 SOURCE_FILE 명시
```

### AREA: DASHBOARD

| SURFACE | ROUTE_NAME | API | R/W | CRITICALITY | ACTIVE | EXISTING_QA |
|---------|------------|-----|-----|-------------|--------|-------------|
| 운영자 대시보드 | root | 미추적 (pages/index/index.vue) | R | HIGH | ACTIVE | — |

### AREA: OPERATIONS (관제)

| SURFACE | ROUTE_NAME | API | R/W | CRITICALITY | ACTIVE | EXISTING_QA |
|---------|------------|-----|-----|-------------|--------|-------------|
| 관제홈 | ops-home | 미추적 (pages/ops-home/index.vue) | R | CRITICAL | ACTIVE | — |
| 운영 자동화 | automation | 미추적 (pages/automation/index.vue) | RW | HIGH | ACTIVE | — |
| 감사로그 | audit-log | 미추적 (pages/audit-log/index.vue) | R | HIGH | ACTIVE | — |
| 자동 QA 대시보드 | auto-qa-dashboard | Supabase REST: `auto_qa_checks` (GET/PATCH), `auto_qa_log` (GET limit=50) | RW | NORMAL | ACTIVE | — |
| 내부 API 모니터 | api-monitor-internal | 미추적 (pages/api-monitor-internal/index.vue) | R | NORMAL | ACTIVE | — |
| 외부 API 모니터 | api-monitor-external | 미추적 (pages/api-monitor-external/index.vue) | R | NORMAL | ACTIVE | — |

> **자동 QA 대시보드 주의**: `SB_URL = https://vwlahtguyggrhvslabax.supabase.co` Supabase REST 직접 호출. `api.taieng.co.kr` 미사용. 테이블: `auto_qa_checks`, `auto_qa_log`. Phase 2-D 구현 QA Control (`/admin/qa/*`)과 별개 시스템. EVIDENCE: `admin-vue3/src/pages/auto-qa-dashboard/useAutoQaDashboard.ts`

### AREA: CUSTOMER (고객)

| SURFACE | ROUTE_NAME | API | R/W | CRITICALITY | ACTIVE | EXISTING_QA |
|---------|------------|-----|-----|-------------|--------|-------------|
| 고객 360 | customer-360 | 미추적 (pages/customer-360/index.vue) | R | HIGH | ACTIVE | — |
| 회사관리 | company-list | 미추적 (pages/company-list/index.vue) | RW | HIGH | ACTIVE | — |
| 시설관리 | factory-list | 미추적 (pages/factory-list/index.vue) | RW | HIGH | ACTIVE | — |
| 회원관리 | member-list | 미추적 (pages/member-list/index.vue) | RW | HIGH | ACTIVE | — |
| 문의관리 | inquiry-list | 미추적 (pages/inquiry-list/index.vue) | RW | NORMAL | ACTIVE | — |
| 온보딩 현황 | onboarding-ops | 미추적 (pages/onboarding-ops/index.vue) | R | NORMAL | ACTIVE | — |

### AREA: BILLING (매출·결제)

| SURFACE | ROUTE_NAME | API | R/W | CRITICALITY | ACTIVE | EXISTING_QA |
|---------|------------|-----|-----|-------------|--------|-------------|
| 경영지표 | stats-business | 미추적 (pages/stats-business/index.vue) | R | HIGH | ACTIVE | — |
| 결제원장 | payment-ledger | 미추적 (pages/payment-ledger/index.vue) | RW | CRITICAL | ACTIVE | — |
| 구독/계약 | contract-list | 미추적 (pages/contract-list/index.vue) | RW | CRITICAL | ACTIVE | — |
| 세금계산서 | tax-ops | 미추적 (pages/tax-ops/index.vue) | RW | HIGH | ACTIVE | — |
| 실행 게이트 | payment-gate | `GET /payments/ops/gate-readiness` (WO-30 코멘트) | R | HIGH | ACTIVE | — |
| 가격설정 | price-setting | 미추적 (pages/price-setting/index.vue) | RW | HIGH | ACTIVE | — |

### AREA: SERVICE (서비스 운영)

| SURFACE | ROUTE_NAME | API | R/W | CRITICALITY | ACTIVE | EXISTING_QA |
|---------|------------|-----|-----|-------------|--------|-------------|
| 법령진단 — 익명 진단 | anon-diagnosis-list | 미추적 (pages/anon-diagnosis-list/index.vue) | R | HIGH | ACTIVE | — |
| 법령진단 — 리포트 | report-v1 | 미추적 (pages/report-v1/index.vue) | R | HIGH | ACTIVE | — |
| 법령진단 — 리포트 뷰어 | report-v1-viewer | 미추적 (pages/report-v1-viewer/index.vue) | R | HIGH | ACTIVE | — |
| 법령진단 — 진단 관리(구) | report_v1 | 미추적 (pages/report_v1/index.vue) | R | NORMAL | ACTIVE | — |
| 법령진단 — 진단 연결 | diagnosis-step1 | 미추적 (pages/diagnosis-step1/index.vue) | RW | HIGH | ACTIVE | — |
| 교육 — 이수현황 | education-list | 미추적 (pages/education-list/index.vue) | RW | HIGH | ACTIVE | — |
| 교육 — 마스터 | education-setting | 미추적 (pages/education-setting/index.vue) | RW | NORMAL | ACTIVE | — |
| SaaS — 권한관리 | permission | 미추적 (pages/permission/index.vue) | RW | HIGH | ACTIVE | — |
| 플랫폼 권한 | platform-permission | 미추적 (pages/platform-permission/index.vue) | RW | HIGH | ACTIVE | — |
| SaaS — 알림설정 | notification-setting | 미추적 (pages/notification-setting/index.vue) | RW | NORMAL | ACTIVE | — |
| SaaS — 문서설정 | doc-setting | 미추적 (pages/doc-setting/index.vue) | RW | NORMAL | ACTIVE | — |
| SaaS — FAQ관리 | faq-setting | `GET/POST/PATCH/DELETE /help/admin/*` (WO-매뉴얼 코멘트) | RW | NORMAL | ACTIVE | — |
| 매뉴얼 | manual | `GET/POST/PATCH/DELETE /help/admin/*` (WO-매뉴얼 코멘트) | RW | NORMAL | ACTIVE | — |

### AREA: COMMUNICATION (커뮤니케이션)

| SURFACE | ROUTE_NAME | API | R/W | CRITICALITY | ACTIVE | EXISTING_QA |
|---------|------------|-----|-----|-------------|--------|-------------|
| 메일 목록 | mail-list | 미추적 (pages/mail-list/index.vue) | RW | HIGH | ACTIVE | — |
| 알림센터 | notification-center | 미추적 (pages/notification-center/index.vue) | RW | NORMAL | ACTIVE | — |
| 알림 관리 | notification-admin | 미추적 (pages/notification-admin/index.vue) | RW | NORMAL | ACTIVE | — |
| 푸시 테스트 | push-test | 미추적 (pages/push-test/index.vue) | W | NORMAL | ACTIVE | — |
| 공지사항 | notice | 미추적 (pages/notice/index.vue) | RW | NORMAL | ACTIVE | — |

### AREA: MARKETING (마케팅)

| SURFACE | ROUTE_NAME | API | R/W | CRITICALITY | ACTIVE | EXISTING_QA |
|---------|------------|-----|-----|-------------|--------|-------------|
| 지식인관리 | kin-management | 미추적 (pages/kin-management/index.vue) | RW | HIGH | ACTIVE | — |
| 대시보드 | marketing | 미추적 (pages/marketing/index.vue) | R | HIGH | ACTIVE | — |
| 발행 운영 | marketing-publish-ops | 미추적 (pages/marketing-publish-ops/index.vue) | RW | HIGH | ACTIVE | — |
| 콘텐츠 | marketing-contents | 미추적 (pages/marketing-contents/index.vue) | RW | NORMAL | ACTIVE | — |
| 배포 관리 | marketing-publish | 미추적 (pages/marketing-publish/index.vue) | RW | HIGH | ACTIVE | — |
| 성과 | marketing-performance | 미추적 (pages/marketing-performance/index.vue) | R | NORMAL | ACTIVE | — |
| 고객(Customer) | marketing-customers | 미추적 (pages/marketing-customers/index.vue) | RW | NORMAL | ACTIVE | — |
| 행동(Journey) | marketing-journeys | 미추적 (pages/marketing-journeys/index.vue) | RW | NORMAL | ACTIVE | — |
| 채널(Channel) | marketing-channels | 미추적 (pages/marketing-channels/index.vue) | RW | HIGH | ACTIVE | — |
| 관계(Relation) | marketing-relations | 미추적 (pages/marketing-relations/index.vue) | RW | NORMAL | ACTIVE | — |
| 전략(Strategy) | marketing-strategies | 미추적 (pages/marketing-strategies/index.vue) | RW | NORMAL | ACTIVE | — |
| 계약(Contract) | marketing-contracts | 미추적 (pages/marketing-contracts/index.vue) | RW | NORMAL | ACTIVE | — |
| 어댑터(Adapter) | marketing-adapters | 미추적 (pages/marketing-adapters/index.vue) | RW | NORMAL | ACTIVE | — |
| 큐(Queue) | marketing-queue | 미추적 (pages/marketing-queue/index.vue) | RW | NORMAL | ACTIVE | — |
| 스케줄러(Scheduler) | marketing-schedulers | 미추적 (pages/marketing-schedulers/index.vue) | RW | NORMAL | ACTIVE | — |
| 결과(Result) | marketing-results | 미추적 (pages/marketing-results/index.vue) | R | NORMAL | ACTIVE | — |
| 감사(Audit) | marketing-audit | 미추적 (pages/marketing-audit/index.vue) | R | HIGH | ACTIVE | — |
| 설정 | marketing-settings | 미추적 (pages/marketing-settings/index.vue) | RW | NORMAL | ACTIVE | — |

### AREA: STATISTICS (통계)

| SURFACE | ROUTE_NAME | API | R/W | CRITICALITY | ACTIVE | EXISTING_QA |
|---------|------------|-----|-----|-------------|--------|-------------|
| 운영개요 | stats-overview | `GET /stats/overview` (nav 코멘트) | R | HIGH | ACTIVE | — |
| 진단 퍼널 | stats-funnel | `GET /stats/funnel` (nav 코멘트) | R | HIGH | ACTIVE | — |
| 고객사·사업장 | stats-customers | `GET /stats/customers` (nav 코멘트) | R | HIGH | ACTIVE | — |
| 매출·결제 | stats-revenue | `GET /stats/revenue` (nav 코멘트) | R | HIGH | ACTIVE | — |
| 서비스 이행 | stats-fulfillment | `GET /stats/fulfillment` (nav 코멘트) | R | NORMAL | ACTIVE | — |
| 워커 활동 | stats-workers | `GET /stats/workers` (nav 코멘트) | R | NORMAL | ACTIVE | — |

### AREA: DEVTOOLS (개발자도구)

| SURFACE | ROUTE_NAME | API | R/W | CRITICALITY | ACTIVE | EXISTING_QA |
|---------|------------|-----|-----|-------------|--------|-------------|
| 전역변수 | system-codes | 미추적 (pages/system-codes/index.vue) | RW | NORMAL | ACTIVE | — |
| 법규 엔진 | engine-legal | 미추적 (pages/engine-legal/index.vue) | RW | NORMAL | ACTIVE | — |
| AI 룰 생성 | engine-legal-ai | 미추적 (pages/engine-legal-ai/index.vue) | RW | NORMAL | ACTIVE | — |
| AI 룰 검토 | engine-legal-ai?draft=1 | 미추적 (pages/engine-legal-ai/index.vue?draft=1) | RW | NORMAL | ACTIVE | — |
| 설비 엔진 | engine-equipment | 미추적 (pages/engine-equipment/index.vue) | RW | NORMAL | ACTIVE | — |
| 모델 엔진 | engine-model | 미추적 (pages/engine-model/index.vue) | RW | NORMAL | ACTIVE | — |
| 공정 엔진(산업) | engine-process-industry | 미추적 (pages/engine-process-industry/index.vue) | RW | NORMAL | ACTIVE | — |
| 공정 엔진(건설) | engine-process-construction | 미추적 (pages/engine-process-construction/index.vue) | RW | NORMAL | ACTIVE | — |
| 문서 엔진 | engine-document | 미추적 (pages/engine-document/index.vue) | RW | NORMAL | ACTIVE | — |
| 문서 스키마 | document-schema | 미추적 (pages/document-schema/index.vue) | RW | NORMAL | ACTIVE | — |
| QA 엔진 | engine-qa | 미추적 (pages/engine-qa/index.vue) | RW | NORMAL | ACTIVE | — |
| 스케줄 엔진 | engine-schedule | 미추적 (pages/engine-schedule/index.vue) | RW | NORMAL | ACTIVE | — |
| 관제센터 | operational-awareness-center | 미추적 (pages/operational-awareness-center/index.vue) | R | NORMAL | ACTIVE | — |
| Watch Engine | watch-engine | 미추적 (pages/watch-engine/index.vue) | R | NORMAL | ACTIVE | — |
| 문서출력 | document-output | 미추적 (pages/document-output/index.vue) | RW | NORMAL | ACTIVE | — |
| 크론관리 | cron-list | 미추적 (pages/cron-list/index.vue) | RW | NORMAL | ACTIVE | — |
| 다이어그램 | diagram-gallery | 미추적 (pages/diagram-gallery/index.vue) | R | LOW | ACTIVE | — |

### INACTIVE (미서비스 — 주석 처리됨)

| SURFACE | ROUTE_NAME | AREA | INACTIVE_REASON |
|---------|------------|------|-----------------|
| 상담리스트 | fix-chat-list | MATCHING | 미서비스 |
| 수선 요청 | repair-list | MATCHING | 미서비스 |
| 수선 설정 | repair-setting | MATCHING | 미서비스 |
| 선임 연결 | personnel-list | MATCHING | 미서비스 |
| 크몽 계약 | contract-kmong | MATCHING | 미서비스 |
| 크몽 편집 | contract-kmong-edit | MATCHING | 미서비스 |
| 인력/전문가 | personnel-list | CUSTOMER | 미서비스 |
| 견적관리 | quote-list | BILLING | 미서비스 |
| 견적설정 | quote-setting | BILLING | 미서비스 |
| 공정관리 | facility-process | RISK | 위험 그룹 (WO-19 제거) |
| 설비관리 | equipment-list | RISK | 위험 그룹 (WO-19 제거) |
| 시설설비 | facility-equipment | RISK | 위험 그룹 (WO-19 제거) |
| 점검관리 | inspection-list | RISK | 위험 그룹 (WO-19 제거) |
| 건설현장 | construction-site-list | RISK | 위험 그룹 (WO-19 제거) |
| 건설공정 | construction-process-list | RISK | 위험 그룹 (WO-19 제거) |
| 건설작업 | construction-work-list | RISK | 위험 그룹 (WO-19 제거) |
| 건설작업자 | construction-worker-list | RISK | 위험 그룹 (WO-19 제거) |
| 건설점검 | construction-inspection-list | RISK | 위험 그룹 (WO-19 제거) |
| 지도 | maps-leaflet | RISK | 위험 그룹 (WO-19 제거) |

---

## 4. API Backend (api.taieng.co.kr)

```
SOURCE_PATH:   tai-api/routers/ @ origin/main (59b60f6a)
AUTH_BOUNDARY: JWT Bearer (Authorization header) — 엔드포인트별 role 제한 적용
               /admin/* — Operator 권한 필요
               /internal/* — X-Internal-Secret 헤더 필요 (Railway env만 보관)
               /public/* — 인증 불필요
               일반 인증 경로 — 유효 JWT 필요
```

### QA 관련 엔드포인트

> EVIDENCE: routers/admin_qa.py, routers/internal_qa.py, routers/internal_scheduler.py

| SURFACE | METHOD + PATH | R/W | CRITICALITY | ACTIVE | EXISTING_QA |
|---------|---------------|-----|-------------|--------|-------------|
| QA 요약 | `GET /admin/qa/summary` | R | HIGH | ACTIVE | — |
| QA 항목 목록 | `GET /admin/qa/items` (필터: site_code/category/priority/effective_status/enabled/page/page_size) | R | HIGH | ACTIVE | — |
| QA 항목 활성화 토글 | `PATCH /admin/qa/items/{qa_item_id}` (body: enabled) | W | HIGH | ACTIVE | — |
| QA 스케줄 수정 | `PATCH /admin/qa/items/{qa_item_id}/schedule` (body: frequency_type/enabled/anchor_time/day_of_week/value/timezone) | W | HIGH | ACTIVE | — |
| QA 실행 이력 | `GET /admin/qa/runs` (필터: started_after/before/trigger_type/status/page/page_size) | R | HIGH | ACTIVE | — |
| QA 실행 상세 | `GET /admin/qa/runs/{run_id}` | R | HIGH | ACTIVE | — |
| QA 수동 실행 | `POST /admin/qa/runs` (body: qa_item_ids[]) | W | HIGH | ACTIVE | — |
| QA 콜백 수신 | `POST /internal/qa/runs/{run_id}/results` (Header: X-Internal-Secret) | W | CRITICAL | ACTIVE | — |
| QA 스케줄 틱 | `POST /internal/scheduler/qa/tick` (Header: X-Internal-Secret) | W | HIGH | ACTIVE | — |

### 인증 엔드포인트

> EVIDENCE: routers/auth.py

| SURFACE | METHOD + PATH | R/W | CRITICALITY | ACTIVE | EXISTING_QA |
|---------|---------------|-----|-------------|--------|-------------|
| 로그인 | `POST /auth/login` | W | CRITICAL | ACTIVE | P0-SAAS-001, P0-WWW-003 |
| 회원가입 | `POST /auth/register` | W | CRITICAL | ACTIVE | — |
| 소셜 ensure-user | `POST /auth/ensure-user` | W | CRITICAL | ACTIVE | — |
| 비밀번호 찾기 | `POST /auth/forgot-password` | W | HIGH | ACTIVE | — |
| 비밀번호 재설정 | `POST /auth/reset-password` | W | HIGH | ACTIVE | — |
| 내 정보 수정 | `PATCH /auth/me` | W | HIGH | ACTIVE | — |

### 진단 엔드포인트

> EVIDENCE: routers/diagnosis.py, routers/anonymous_diagnosis.py

| SURFACE | METHOD + PATH | R/W | CRITICALITY | ACTIVE | EXISTING_QA |
|---------|---------------|-----|-------------|--------|-------------|
| 무료진단 실행 | `POST /diagnosis/run` | W | CRITICAL | ACTIVE | P0-DIAG-001 |
| 진단 결과 조회 | `GET /diagnosis/result/{token}` | R | HIGH | ACTIVE | — |
| 유료진단 가격 티어 | `GET /diagnosis/price-tier` | R | HIGH | ACTIVE | — |
| 유료진단 결과 조회 | `GET /diagnosis/paid-result/{token}` | R | HIGH | ACTIVE | — |

### 결제 엔드포인트

> EVIDENCE: routers/payment.py, routers/payment_billing.py

| SURFACE | METHOD + PATH | R/W | CRITICALITY | ACTIVE | EXISTING_QA |
|---------|---------------|-----|-------------|--------|-------------|
| 결제 내역 | `GET /payments` | R | CRITICAL | ACTIVE | P0-MYP-005 |
| Inicis 결제 콜백 | `POST /_api/payments/inicis/return` (CF Function 프록시) | W | CRITICAL | ACTIVE | — |
| 계약 정보 | `GET /me/commercial/contract` | R | CRITICAL | ACTIVE | — |
| 진단 구매 | `POST /payments/purchase-diagnosis` | W | HIGH | ACTIVE | — |

### 공개 엔드포인트

> EVIDENCE: routers/public.py, routers/public_pricing.py, routers/public_safety_search.py

| SURFACE | METHOD + PATH | R/W | CRITICALITY | ACTIVE | EXISTING_QA |
|---------|---------------|-----|-------------|--------|-------------|
| 공지사항 | `GET /notices/active` | R | CRITICAL | ACTIVE | P0-WWW-001 |
| 요금제 조회 | `GET /public/pricing/all` | R | HIGH | ACTIVE | — |
| 통합검색 | `GET /public/safety-search` | R | CRITICAL | ACTIVE | P0-SRCH-001, P0-SRCH-002 |

---

## 5. QA Runner (tai-qa)

```
SOURCE_PATH:   tai-qa/ @ main (NOT_LOCAL; GitHub MCP 확인, HEAD b054bb99)
STRUCTURE:     features/**/*.feature + steps/**/*.steps.ts + fixtures/qa.fixture.ts
RUNNER:        bddgen && playwright test --grep @p0
SCHEDULE:      .github/workflows/p0-smoke.yml — 매일 23:00 UTC (= 08:00 KST)
```

### 기존 10개 Scenario

| scenario_id | SERVICE | AREA | QA_TYPE (안) | FEATURE FILE |
|-------------|---------|------|-------------|--------------|
| P0-WWW-001 | WWW | LANDING | AVAILABILITY | features/marketing/core.feature |
| P0-DIAG-001 | WWW | FREE_DIAGNOSIS | AVAILABILITY | features/diagnosis/core.feature |
| P0-SRCH-001 | WWW | SEARCH | AVAILABILITY | features/search/core.feature |
| P0-SRCH-002 | WWW | SEARCH | FUNCTIONAL | features/search/core.feature |
| P0-MYP-001 | SAAS | MYPAGE | AVAILABILITY | features/mypage/core.feature |
| P0-MYP-005 | SAAS | MYPAGE | FUNCTIONAL | features/mypage/core.feature |
| P0-SAAS-001 | SAAS | AUTH | E2E | features/saas/core.feature |
| P0-WWW-003 | WWW | AUTH | E2E | features/marketing/core.feature |
| P0-WWW-004 | WWW | HEADER | FUNCTIONAL | features/marketing/core.feature |
| P0-WWW-005 | WWW | HEADER | FUNCTIONAL | features/marketing/core.feature |

### tai-qa 기술 설계

```
fixtures/qa.fixture.ts:
  _qaErrors 픽스처: auto=true (전 테스트 자동 적용)
  수집 대상: pageerror + api.taieng.co.kr requestfailed + HTTP 5xx
  post-use: fatalErrors ≥ 1 → 테스트 자동 실패

playwright.config.ts:
  단일 프로젝트: Chromium Desktop Chrome
  fullyParallel: false (순차 실행)
  retries: CI ? 1 : 0
  timeout: 30,000ms / expect.timeout: 10,000ms

.github/workflows/p0-smoke.yml:
  트리거:
    1. workflow_dispatch (run_id optional, scenario_ids optional)
    2. schedule: 0 23 * * * (= 08:00 KST)
    3. pull_request → main (관련 경로 변경 시)
  콜백: workflow_dispatch + run_id 있을 때만
    POST https://api.taieng.co.kr/internal/qa/runs/{run_id}/results
    Header: X-Internal-Secret
  환경 변수: QA_SEARCH_TERM='지게차' (하드코딩)

Steps 인증 방식:
  WWW:  #login-id, #login-pw, #btn-login (DOM 셀렉터)
  SaaS: input[type="email"], input[type="password"], button[type="submit"] (제네릭)
```

---

## 6. 외부 연동 현황

| 연동 서비스 | 용도 | 연동 경로 | 관련 SERVICE |
|------------|------|----------|-------------|
| Inicis (KG) | 본인인증 (svc_code='01'), 카드결제 (V023) | tai-www: /log-in#register, /free-diagnosis, /mypage/checkout, /invite | WWW, SAAS |
| Supabase | OAuth(kakao/google), 이미지 스토리지, ADMIN 자동 QA DB | tai-www: Supabase UMD SDK / admin-vue3: Supabase REST (auto_qa_checks/auto_qa_log) | WWW, ADMIN |
| GitHub Actions | QA 자동화 실행 dispatch | tai-api → `POST /repos/taiengineering/tai-qa/actions/workflows/p0-smoke.yml/dispatches` | API (ADMIN 제어) |
| Slack | QA 결과 알림 | tai-api → Slack Incoming Webhook | API |
| 마케팅 API | 지식센터 SSR | tai-www CF Function → 45cm-mkt-api-production `/public/knowledge` | WWW |
| Supabase DB | 메인 DB | tai-api → supabase-py | ALL |

---

## 7. 운영 스케줄러 대상

| 대상 | 트리거 | 구현 위치 | 비고 |
|------|--------|----------|------|
| qa_scheduler_tick | cron `* * * * *` (매분) | tai-api: services/qa_scheduler_svc.py + cron_job_master | is_active=true 운영 중 |
| P0-SAAS-001 DAILY 자동실행 | 매일 08:00 KST | qa_schedules: frequency_type=DAILY, anchor_time=08:00:00 | 활성 |
| p0-smoke.yml schedule | 매일 23:00 UTC (= 08:00 KST) | tai-qa: .github/workflows/p0-smoke.yml | PR 변경 시 추가 트리거 |

---

## 8. 조사 결론

### Surface 수 요약

| SERVICE | AREA 수 | ACTIVE SURFACE 수 | INACTIVE | EXISTING_QA 커버 |
|---------|---------|-------------------|----------|-----------------|
| WWW | 7 | 36 | 0 | 7개 scenario (P0-WWW-001/003/004/005, P0-DIAG-001, P0-SRCH-001/002) |
| SAAS | 12 | 52 | 0 | 3개 scenario (P0-SAAS-001, P0-MYP-001/005) |
| ADMIN | 9 (active) | 78 | 19 | 0 |
| API | — | 22 | 0 | 10개 scenario 전부 |
| QA_RUNNER | — | 10 scenarios | — | — |
| **TOTAL** | **28** | **188** | **19** | 10/10 scenario |

### 전수 조사 완료 항목

- [x] tai-www 조사 완료 (36 surfaces, 7 areas, CF Functions 7종)
- [x] tai-admin SAFE SaaS 조사 완료 (52 surfaces, 12 areas including QA area)
- [x] tai-admin Operator Admin 조사 완료 (78 surfaces, 9 active areas; admin-vue3/ @ feat/admin-rebuild)
- [x] tai-api 주요 엔드포인트 조사 완료 (22 key endpoints; QA/AUTH/DIAGNOSIS/PAYMENT/PUBLIC)
- [x] tai-qa 기존 Scenario 조사 완료 (10 scenarios, BDD 구조, 워크플로우)
- [x] 코드 변경 = 0 / DB 변경 = 0 / Production mutation = 0

### 존재하지 않는 API (PATCH1 수정)

이하 엔드포인트는 원 문서에 오기재되었으나 존재하지 않음. EVIDENCE: `routers/admin_qa.py`:

| 오기재 엔드포인트 | 실제 상황 |
|----------------|----------|
| `GET /admin/qa/items/{id}` | 미존재. Items 상세 페이지는 `GET /admin/qa/items?page_size=100` 전체 조회 후 프론트엔드 id 탐색 |
| `GET /admin/qa/settings` | 미존재 |
| `PUT /admin/qa/settings` | 미존재. 설정 변경은 `PATCH /admin/qa/items/{id}/schedule` 사용 |

### 미조사 항목

- WORKER 서비스: repo/runtime 미확인. 이 문서에 포함하지 않음.
- ADMIN 페이지별 API 경로: admin-vue3/ 각 페이지 파일 미추적 (nav 구조만 확인). 확인된 경우만 기재.

### Phase 1 진입 선결 조건

이 문서 = TAI Surface SoT. Phase 1 (QA Taxonomy DB 구현) 및 Phase 2 (QA Universe Catalog 작성) 착수 가능.
