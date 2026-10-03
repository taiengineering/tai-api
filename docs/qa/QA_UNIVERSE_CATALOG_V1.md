---
title: QA Universe Catalog v1
version: 1.0.0
work_order: WO-QA-UNIVERSE-CATALOG-MODULE-PATTERN-001
status: COMPLETE
authored_at: 2026-10-02
code_change: 0
db_change: 0
production_mutation: 0
---

# QA Universe Catalog v1

TAI 전체 QA 항목 정의 + Reusable Module Pattern 분류.  
추측 QA: 0 (source 직접 확인 항목만 포함).

---

## Base Sources

| SoT 문서 | 버전/SHA |
|---------|---------|
| `docs/qa/QA_SURFACE_INVENTORY_V1.md` | v1.2.0 @ 58134ae0 |
| `docs/qa/QA_TAXONOMY_V1.md` | v1.0.0 |
| `docs/qa/QA_UNIVERSE_MODULARIZATION_MASTER_PLAN_V1.md` | v1.0.0 |
| tai-www @ main | 73adaf86 |
| tai-admin (SAFE) @ main | be4ff2c7 |
| tai-admin (ADMIN) @ feat/admin-rebuild | 6d9e89ea |
| tai-api @ main | 59b60f6a (+ taxonomy Phase1 feat) |
| tai-qa @ main | 631af37b |

---

## ADMIN UNVERIFIED 26개 판정 결과

Surface Inventory v1.2.0의 ADMIN UNVERIFIED 26개를 소스 직접 확인 후 판정.

| SURFACE | ROUTE_NAME | 판정 | 근거 |
|---------|-----------|------|------|
| 운영자 대시보드 | root/index | VERIFIED | pages/index/index.vue — GET /companies, /subscriptions, /admin/stats, /payments, /matching/admin/dashboard |
| QA 현황 | qa-dashboard | VERIFIED | admin-vue3/src/pages/qa/dashboard.vue — GET /admin/qa/summary |
| QA 설정 | qa-settings | VERIFIED | admin-vue3/src/pages/qa/settings.vue — GET /admin/qa/items + PATCH .../schedule (CM-002 결함) |
| 푸시 테스트 | push-test | VERIFIED | pages/push-test/index.vue 존재 — api.taieng.co.kr push 엔드포인트 |
| 서비스 이행 | stats-fulfillment | VERIFIED | GET /stats/fulfillment?days=N |
| 워커 활동 | stats-workers | VERIFIED | GET /stats/workers?days=N |
| 콘텐츠 | marketing-contents | VERIFIED | GET /admin/marketing/contents |
| 배포 관리 | marketing-publish | VERIFIED | GET /admin/marketing/publish-jobs |
| 고객(Customer) | marketing-customers | VERIFIED | GET/POST /admin/marketing/customers |
| 행동(Journey) | marketing-journeys | VERIFIED | GET/POST /admin/marketing/journeys |
| 관계(Relation) | marketing-relations | VERIFIED | GET/POST /admin/marketing/customer-journeys, journey-channels |
| 전략(Strategy) | marketing-strategies | VERIFIED | GET/POST /admin/marketing/strategies |
| 계약(Contract) | marketing-contracts | VERIFIED | GET/POST /admin/marketing/contracts |
| 어댑터(Adapter) | marketing-adapters | VERIFIED | GET/POST /admin/marketing/adapters |
| 큐(Queue) | marketing-queue | VERIFIED | GET/POST /admin/marketing/queue |
| 스케줄러(Scheduler) | marketing-schedulers | VERIFIED | GET/POST /admin/marketing/schedulers |
| 설비 엔진 | engine-equipment | VERIFIED | GET/PATCH /engine-equipment/models, /engine-equipment/assets, /engine-equipment/stats |
| 모델 엔진 | engine-model | VERIFIED | GET /engine-model/stats, /engine-model/filters |
| 공정 엔진(산업) | engine-process-industry | VERIFIED | GET /engine-industry/stats |
| 공정 엔진(건설) | engine-process-construction | VERIFIED | GET /byulpyo/kcsc-process, /byulpyo/kcsc-work, POST /byulpyo/kcsc-sync |
| 문서 엔진 | engine-document | VERIFIED | GET /document-forms |
| 문서 스키마 | document-schema | VERIFIED | GET /document-schema/{dt}, GET /document-schema/integrity/{dt} |
| QA 엔진 | engine-qa | VERIFIED | POST /legal-engine/qa-run |
| 스케줄 엔진 | engine-schedule | VERIFIED | GET/POST /inspection-schedule/rules, /sets, /generate |
| 문서출력 | document-output | VERIFIED | GET /watch-engine/documents/summary, /mvp, /generated |
| 다이어그램 | diagram-gallery | VERIFIED | Supabase REST diagram_templates (anon key, READ-ONLY) |

**결과: VERIFIED 26 / EXCLUDED 0**  
ADMIN ACTIVE VERIFIED: 56 + 26 = **82개**

---

## 범례

| 필드 | 값 |
|------|----|
| AUTO | Y=완전자동화, P=부분자동화(수동조건), N=자동화불가 |
| SAFE | Y=프로덕션 안전, C=조건부(CONDITIONAL, NOTES 참고), N=프로덕션 실행 금지 |
| RUNNER | PW=Playwright, API=HTTP only, HYB=PW+API, MANUAL |
| STATUS | EXISTING=기존 scenario 존재, NEW=신규, MANUAL_ONLY=자동화 불가, BLOCKED=선결조건 필요 |

---

## Module Pattern 표준

| Pattern | 설명 |
|---------|------|
| `PAGE_OPEN` | 페이지 정상 열림 확인 |
| `AUTH_LOGIN` | 인증 로그인 선행 |
| `AUTH_GUARD` | 비인증 접근 차단 확인 |
| `NAVIGATE` | 링크/버튼 통한 화면 이동 |
| `LIST_LOAD` | 목록 데이터 정상 로드 |
| `DETAIL_LOAD` | 상세 데이터 정상 로드 |
| `FORM_SUBMIT` | 폼 제출 정상 처리 |
| `FORM_VALIDATION` | 폼 유효성 검사 |
| `SAVE_UPDATE` | 저장/수정 정상 처리 |
| `DELETE_CONFIRM` | 삭제 확인 흐름 |
| `SEARCH_RESULT` | 검색/필터 결과 확인 |
| `FILTER_RESULT` | 필터 적용 결과 확인 |
| `API_SUCCESS` | API 정상 응답 확인 |
| `API_CONTRACT` | API 응답 schema/필드 검증 |
| `API_ERROR` | API 오류 응답 처리 확인 |
| `ACCESS_DENY` | 권한 없는 접근 거부 확인 |
| `TENANT_ISOLATION` | 테넌트 데이터 격리 확인 |
| `DATA_MATCH` | 화면 표시값/API 응답 정합 |
| `DATA_PERSISTENCE` | 저장 후 재조회 데이터 유지 |
| `E2E_FLOW` | 업무 전체 흐름 완주 |
| `PERF_PAGE_LOAD` | 페이지 로딩 시간 |
| `PERF_API_RESPONSE` | API 응답 시간 |
| `VISUAL_BASELINE` | 시각적 회귀 |
| `A11Y_BASIC` | 기본 접근성 |

---

## 1. WWW 서비스 (taieng.co.kr)

```
AUTH_BOUNDARY: localStorage access_token (클라이언트 사이드)
               서버사이드 가드 없음 (Cloudflare Functions 미적용)
EXTERNAL: tai-api / Inicis / Supabase OAuth
```

### AREA: LANDING

| QA_ID | PRI | TYPE | QA_NAME | SOURCE | AUTO | SAFE | RUNNER | MODULE_PATTERN | EXISTING | STATUS |
|-------|-----|------|---------|--------|------|------|--------|----------------|----------|--------|
| P0-WWW-001 | P0 | AVAILABILITY | 마케팅 사이트 메인 정상 진입 | GET / | Y | Y | PW | PAGE_OPEN | P0-WWW-001 | EXISTING |
| P1-WWW-LANDING-FNC-001 | P1 | FUNCTIONAL | 메인 공지 배너 정상 표시 | GET /notices/active | Y | Y | PW | PAGE_OPEN + LIST_LOAD | — | NEW |
| P1-WWW-LANDING-AVL-001 | P1 | AVAILABILITY | 요금제 페이지 정상 진입 | GET /pricing | Y | Y | PW | PAGE_OPEN | — | NEW |
| P1-WWW-LANDING-FNC-002 | P1 | FUNCTIONAL | 요금제 목록 정상 표시 | GET /public/pricing/all | Y | Y | PW | PAGE_OPEN + LIST_LOAD | — | NEW |
| P2-WWW-LANDING-AVL-001 | P2 | AVAILABILITY | 서비스 소개(SaaS) 정상 진입 | GET /service/saas | Y | Y | PW | PAGE_OPEN | — | NEW |
| P2-WWW-LANDING-AVL-002 | P2 | AVAILABILITY | 서비스 소개(진단) 정상 진입 | GET /service/diagnosis | Y | Y | PW | PAGE_OPEN | — | NEW |
| P2-WWW-LANDING-AVL-003 | P2 | AVAILABILITY | 타겟 랜딩(업주) 정상 진입 | GET /for-business-owner | Y | Y | PW | PAGE_OPEN | — | NEW |
| P2-WWW-LANDING-AVL-004 | P2 | AVAILABILITY | 타겟 랜딩(안전관리자) 정상 진입 | GET /for-safety-manager | Y | Y | PW | PAGE_OPEN | — | NEW |
| P2-WWW-LANDING-AVL-005 | P2 | AVAILABILITY | 회사 소개 정상 진입 | GET /about | Y | Y | PW | PAGE_OPEN | — | NEW |
| P2-WWW-LANDING-AVL-006 | P2 | AVAILABILITY | FAQ 정상 진입 | GET /faq | Y | Y | PW | PAGE_OPEN | — | NEW |

> **P0-WWW-001 EXPECTED**: GET / 응답 200, 메인 랜딩 핵심 요소(헤더/CTA) 정상 렌더링, API fatal error 없음

### AREA: AUTH

| QA_ID | PRI | TYPE | QA_NAME | SOURCE | AUTO | SAFE | RUNNER | MODULE_PATTERN | EXISTING | STATUS |
|-------|-----|------|---------|--------|------|------|--------|----------------|----------|--------|
| P0-WWW-003 | P0 | E2E | 회원 로그인 완료 | GET /log-in → POST /auth/login | Y | C | PW | E2E_FLOW + AUTH_LOGIN | P0-WWW-003 | EXISTING |
| P1-WWW-AUTH-FNC-001 | P1 | FUNCTIONAL | 회원 가입 이메일 정상 처리 | POST /auth/register | Y | C | PW | FORM_SUBMIT | — | NEW |
| P1-WWW-AUTH-SEC-001 | P1 | SECURITY | 비로그인 상태 마이페이지 접근 차단 | /mypage/* | Y | Y | PW | AUTH_GUARD | — | NEW |
| P1-WWW-AUTH-INT-001 | P1 | INTEGRATION | 카카오 소셜 로그인 연동 | Supabase OAuth → POST /auth/ensure-user | P | C | PW | E2E_FLOW | — | NEW |
| P1-WWW-AUTH-INT-002 | P1 | INTEGRATION | 구글 소셜 로그인 연동 | Supabase OAuth → POST /auth/ensure-user | P | C | PW | E2E_FLOW | — | NEW |
| P1-WWW-AUTH-FNC-002 | P1 | FUNCTIONAL | 초대 링크 수락 정상 처리 | GET /invite → GET + POST /user-invites/{token}/* | Y | C | PW | E2E_FLOW + FORM_SUBMIT | — | NEW |

> **P0-WWW-003 EXPECTED**: 이메일+비밀번호 입력 → 로그인 성공 → access_token localStorage 저장, 대시보드 리다이렉트 확인  
> **SAFE=C**: 전용 QA 계정 사용 필수 (실 고객 계정 사용 금지)

### AREA: FREE_DIAGNOSIS

| QA_ID | PRI | TYPE | QA_NAME | SOURCE | AUTO | SAFE | RUNNER | MODULE_PATTERN | EXISTING | STATUS |
|-------|-----|------|---------|--------|------|------|--------|----------------|----------|--------|
| P0-DIAG-001 | P0 | AVAILABILITY | 무료 법령진단 정상 진입 | GET /free-diagnosis | Y | Y | PW | PAGE_OPEN | P0-DIAG-001 | EXISTING |
| P1-WWW-DIAG-FNC-001 | P1 | FUNCTIONAL | 무료진단 마법사 Step 완주 | GET /free-diagnosis → POST /diagnosis/run | Y | Y | PW | E2E_FLOW + FORM_SUBMIT | — | NEW |
| P1-WWW-DIAG-FNC-002 | P1 | FUNCTIONAL | 무료진단 결과 정상 표시 | GET /free-diagnosis-result | Y | Y | PW | PAGE_OPEN + DETAIL_LOAD | — | NEW |
| P1-WWW-DIAG-AVL-001 | P1 | AVAILABILITY | 유료진단 안내 정상 진입 | GET /paid-diagnosis | Y | C | PW | AUTH_LOGIN + PAGE_OPEN | — | NEW |
| P1-WWW-DIAG-FNC-003 | P1 | FUNCTIONAL | 유료진단 결과 정상 조회 | GET /paid-diagnosis-result | Y | C | PW | DETAIL_LOAD | — | NEW |
| P1-WWW-DIAG-API-001 | P1 | API | 무료진단 실행 API 정상 응답 | POST /diagnosis/run | Y | Y | API | API_CONTRACT | — | NEW |

> **P0-DIAG-001 EXPECTED**: GET /free-diagnosis 응답 200, 진단 마법사 Step1 요소 렌더링, API fatal error 없음  
> **SAFE=C (P1-WWW-DIAG-AVL-001)**: /paid-diagnosis 회원 전용 — memberGate 비로그인 → /log-in redirect. AUTH_LOGIN 선행 필요.  
> **SAFE=C (P1-WWW-DIAG-FNC-003)**: 진단 토큰이 존재하는 계정 사전 조건 필요

### AREA: SEARCH

| QA_ID | PRI | TYPE | QA_NAME | SOURCE | AUTO | SAFE | RUNNER | MODULE_PATTERN | EXISTING | STATUS |
|-------|-----|------|---------|--------|------|------|--------|----------------|----------|--------|
| P0-SRCH-001 | P0 | AVAILABILITY | 통합검색 정상 진입 | GET /safety-search | Y | Y | PW | PAGE_OPEN | P0-SRCH-001 | EXISTING |
| P0-SRCH-002 | P0 | FUNCTIONAL | 통합검색 결과 섹터 순서 유지 | GET /safety-search?q=지게차 | Y | Y | PW | SEARCH_RESULT | P0-SRCH-002 | EXISTING |
| P1-WWW-SEARCH-FNC-001 | P1 | FUNCTIONAL | 지식센터 허브 목록 정상 로드 | GET /kb → GET /public/knowledge | Y | Y | PW | PAGE_OPEN + LIST_LOAD | — | NEW |
| P2-WWW-SEARCH-AVL-001 | P2 | AVAILABILITY | 검색 상세(지식) 정상 진입 | GET /safety-search/knowledge/{id} | Y | Y | PW | DETAIL_LOAD | — | NEW |
| P2-WWW-SEARCH-AVL-002 | P2 | AVAILABILITY | 검색 상세(법령) 정상 진입 | GET /safety-search/legal/{id} | Y | Y | PW | DETAIL_LOAD | — | NEW |
| P2-WWW-SEARCH-AVL-003 | P2 | AVAILABILITY | 지식센터 상세 정상 진입 | GET /kb/{slug} | Y | Y | PW | DETAIL_LOAD | — | NEW |

> **P0-SRCH-001 EXPECTED**: GET /safety-search 응답 200, 검색 입력 필드 렌더링, API fatal error 없음  
> **P0-SRCH-002 EXPECTED**: 검색어 '지게차' 입력 후 결과 표시 → 법령/지식/사례 섹터 존재, 순서 불변

### AREA: HEADER

| QA_ID | PRI | TYPE | QA_NAME | SOURCE | AUTO | SAFE | RUNNER | MODULE_PATTERN | EXISTING | STATUS |
|-------|-----|------|---------|--------|------|------|--------|----------------|----------|--------|
| P0-WWW-004 | P0 | FUNCTIONAL | 로그인 후 헤더 인증 상태 유지 | / + localStorage access_token | Y | C | PW | AUTH_LOGIN + PAGE_OPEN | P0-WWW-004 | EXISTING |
| P0-WWW-005 | P0 | FUNCTIONAL | 헤더에서 마이페이지 정상 이동 | a[href*="mypage"] → GET /mypage/ | Y | C | PW | AUTH_LOGIN + NAVIGATE | P0-WWW-005 | EXISTING |
| P1-WWW-HEADER-FNC-001 | P1 | FUNCTIONAL | 비로그인 헤더 정상 표시 | / (access_token 없음) | Y | Y | PW | PAGE_OPEN | — | NEW |
| P1-WWW-HEADER-SEC-001 | P1 | SECURITY | 로그인/회원가입 링크 비로그인 상태 노출 | / | Y | Y | PW | AUTH_GUARD | — | NEW |
| P2-WWW-HEADER-VIS-001 | P2 | VISUAL | 헤더 로그인 상태 Visual 회귀 | / | Y | Y | PW | VISUAL_BASELINE | — | NEW |

> **P0-WWW-004 EXPECTED**: QA 계정 로그인 후 / 접근 → 헤더에 로그인 상태 표시(사용자명/아바타), 로그인 버튼 미표시  
> **P0-WWW-005 EXPECTED**: 헤더 마이페이지 링크 클릭 → taieng.co.kr/mypage/ 정상 이동, HTTP 200

### AREA: CONTENT

| QA_ID | PRI | TYPE | QA_NAME | SOURCE | AUTO | SAFE | RUNNER | MODULE_PATTERN | EXISTING | STATUS |
|-------|-----|------|---------|--------|------|------|--------|----------------|----------|--------|
| P2-WWW-CONTENT-AVL-001 | P2 | AVAILABILITY | 재해사례 목록 정상 진입 | GET /accident-cases | Y | Y | PW | PAGE_OPEN + LIST_LOAD | — | NEW |
| P2-WWW-CONTENT-AVL-002 | P2 | AVAILABILITY | 재해사례 상세 정상 진입 | GET /accident/{id} | Y | Y | PW | DETAIL_LOAD | — | NEW |
| P2-WWW-CONTENT-AVL-003 | P2 | AVAILABILITY | 안전뉴스 목록 정상 진입 | GET /safety-news | Y | Y | PW | PAGE_OPEN + LIST_LOAD | — | NEW |
| P2-WWW-CONTENT-AVL-004 | P2 | AVAILABILITY | 법령개정 뉴스 정상 진입 | GET /law-updates | Y | Y | PW | PAGE_OPEN + LIST_LOAD | — | NEW |
| P2-WWW-CONTENT-AVL-005 | P2 | AVAILABILITY | 판례 검색 정상 진입 | GET /precedent-search | Y | Y | PW | PAGE_OPEN | — | NEW |
| P2-WWW-CONTENT-AVL-006 | P2 | AVAILABILITY | 동적 카테고리 페이지 정상 진입 | GET /safety/{subject} | Y | Y | PW | PAGE_OPEN | — | NEW |

### AREA: CONTACT

| QA_ID | PRI | TYPE | QA_NAME | SOURCE | AUTO | SAFE | RUNNER | MODULE_PATTERN | EXISTING | STATUS |
|-------|-----|------|---------|--------|------|------|--------|----------------|----------|--------|
| P2-WWW-CONTACT-FNC-001 | P2 | FUNCTIONAL | 도입 문의 폼 정상 제출 | GET /contact → POST /inquiries | Y | C | PW | FORM_SUBMIT | — | NEW |
| P2-WWW-CONTACT-FNC-002 | P2 | FUNCTIONAL | 전문가 매칭 요청 정상 제출 | GET /fix-request → POST /expert-matching/* | P | C | PW | FORM_SUBMIT | — | NEW |

---

## 2. SAAS 서비스 (safe.taieng.co.kr + taieng.co.kr/mypage/*)

```
AUTH_BOUNDARY: router.beforeEach() → useAuth().requireAuth()
               공개 경로: /login, /tai-survey, /forgot-password, /reset-password
               role_code 기반 nav gate
API_CLIENT: useTaiApi (Bearer token)
NOTE: MYPAGE는 tai-www 정적 HTML, API는 tai-api
```

### AREA: AUTH

| QA_ID | PRI | TYPE | QA_NAME | SOURCE | AUTO | SAFE | RUNNER | MODULE_PATTERN | EXISTING | STATUS |
|-------|-----|------|---------|--------|------|------|--------|----------------|----------|--------|
| P0-SAAS-001 | P0 | E2E | SaaS 로그인 후 대시보드 정상 진입 | GET /login → POST /auth/login → /safety-dashboard | Y | C | PW | E2E_FLOW + AUTH_LOGIN | P0-SAAS-001 | EXISTING |
| P1-SAAS-AUTH-FNC-001 | P1 | FUNCTIONAL | SaaS 로그아웃 정상 처리 | 로그아웃 버튼 → localStorage 제거 → /login | Y | C | PW | E2E_FLOW | — | NEW |
| P1-SAAS-AUTH-SEC-001 | P1 | SECURITY | 비인증 상태 인증 필요 페이지 접근 차단 | /safety-dashboard (미로그인) | Y | Y | PW | AUTH_GUARD | — | NEW |
| P2-SAAS-AUTH-FNC-001 | P2 | FUNCTIONAL | 비밀번호 찾기 이메일 발송 | POST /auth/forgot-password | Y | C | PW | FORM_SUBMIT | — | NEW |
| P2-SAAS-AUTH-FNC-002 | P2 | FUNCTIONAL | 비밀번호 재설정 정상 처리 | POST /auth/reset-password | Y | C | PW | FORM_SUBMIT | — | NEW |

> **P0-SAAS-001 EXPECTED**: SaaS QA 계정 로그인 → /safety-dashboard 정상 렌더링, 작업일정/날씨 섹션 표시, API fatal error 없음

### AREA: DASHBOARD

| QA_ID | PRI | TYPE | QA_NAME | SOURCE | AUTO | SAFE | RUNNER | MODULE_PATTERN | EXISTING | STATUS |
|-------|-----|------|---------|--------|------|------|--------|----------------|----------|--------|
| P1-SAAS-DASH-AVL-001 | P1 | AVAILABILITY | SaaS 대시보드 정상 진입 | GET /safety-dashboard | Y | C | PW | AUTH_LOGIN + PAGE_OPEN | — | NEW |
| P1-SAAS-DASH-FNC-001 | P1 | FUNCTIONAL | 대시보드 작업일정 목록 로드 | GET /work-schedules | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |
| P2-SAAS-DASH-AVL-001 | P2 | AVAILABILITY | 알림 목록 정상 진입 | GET /alert-list | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |

### AREA: MYPAGE

| QA_ID | PRI | TYPE | QA_NAME | SOURCE | AUTO | SAFE | RUNNER | MODULE_PATTERN | EXISTING | STATUS |
|-------|-----|------|---------|--------|------|------|--------|----------------|----------|--------|
| P0-MYP-001 | P0 | AVAILABILITY | 마이페이지 대시보드 정상 진입 | GET taieng.co.kr/mypage/ | Y | C | PW | AUTH_LOGIN + PAGE_OPEN | P0-MYP-001 | EXISTING |
| P0-MYP-005 | P0 | FUNCTIONAL | 결제내역 정상 조회 | GET taieng.co.kr/mypage/payments/ → GET /payments | Y | C | PW | AUTH_LOGIN + LIST_LOAD | P0-MYP-005 | EXISTING |
| P1-SAAS-MYP-AVL-001 | P1 | AVAILABILITY | 계약 목록 정상 진입 | GET taieng.co.kr/mypage/contracts | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |
| P1-SAAS-MYP-FNC-001 | P1 | FUNCTIONAL | 프로필 수정 정상 저장 | PATCH /auth/me | Y | C | PW | AUTH_LOGIN + SAVE_UPDATE | — | NEW |
| P1-SAAS-MYP-FNC-002 | P1 | FUNCTIONAL | 회사정보 정상 조회/수정 | GET/POST /factories | Y | C | PW | AUTH_LOGIN + DETAIL_LOAD | — | NEW |
| P1-SAAS-MYP-SEC-001 | P1 | SECURITY | 비로그인 마이페이지 접근 차단 | /mypage/* (access_token 없음) | Y | Y | PW | AUTH_GUARD | — | NEW |
| P1-SAAS-MYP-DATA-001 | P1 | DATA | 결제내역 화면 표시값/API 정합 | GET /payments → 화면 렌더링 | Y | C | PW | AUTH_LOGIN + DATA_MATCH | — | NEW |
| P1-SAAS-MYP-AVL-002 | P1 | AVAILABILITY | 온보딩 페이지 정상 진입 | GET taieng.co.kr/mypage/onboarding | Y | C | PW | AUTH_LOGIN + PAGE_OPEN | — | NEW |
| P1-SAAS-MYP-E2E-001 | P1 | E2E | 결제 Checkout 흐름 검증 | GET /mypage/checkout → Inicis V023 | N | N | MANUAL | E2E_FLOW | — | MANUAL_ONLY |
| P2-SAAS-MYP-AVL-001 | P2 | AVAILABILITY | 파트너 대시보드 정상 진입 | GET /mypage/partner/ | Y | C | PW | AUTH_LOGIN + PAGE_OPEN | — | NEW |

> **P0-MYP-001 EXPECTED**: 마이페이지 대시보드 정상 렌더링, 계약/결제 요약 섹션 표시, API fatal error 없음  
> **P0-MYP-005 EXPECTED**: 결제내역 목록 1개 이상 또는 "내역 없음" 정상 표시, HTTP 200  
> **P1-SAAS-MYP-E2E-001 NOTES**: 실결제(Inicis) PROD_SAFE=N, MANUAL 실행 전용

### AREA: INSPECTION

| QA_ID | PRI | TYPE | QA_NAME | SOURCE | AUTO | SAFE | RUNNER | MODULE_PATTERN | EXISTING | STATUS |
|-------|-----|------|---------|--------|------|------|--------|----------------|----------|--------|
| P1-SAAS-INSP-AVL-001 | P1 | AVAILABILITY | 내 점검 목록 정상 진입 | GET /my-inspection | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |
| P1-SAAS-INSP-FNC-001 | P1 | FUNCTIONAL | 점검 작업대 항목 저장 | POST /inspection/result/{id}/items | Y | C | HYB | AUTH_LOGIN + SAVE_UPDATE | — | NEW |
| P1-SAAS-INSP-FNC-002 | P1 | FUNCTIONAL | 점검 상세 조회/보정 | GET /inspection/{id}/view | Y | C | PW | AUTH_LOGIN + DETAIL_LOAD | — | NEW |
| P2-SAAS-INSP-AVL-001 | P2 | AVAILABILITY | 점검 달력 정상 진입 | GET /inspection-calendar | Y | C | PW | AUTH_LOGIN + PAGE_OPEN | — | NEW |
| P2-SAAS-INSP-FNC-001 | P2 | FUNCTIONAL | 점검 세트 관리 정상 동작 | GET /inspection-sets | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |

### AREA: EDUCATION

| QA_ID | PRI | TYPE | QA_NAME | SOURCE | AUTO | SAFE | RUNNER | MODULE_PATTERN | EXISTING | STATUS |
|-------|-----|------|---------|--------|------|------|--------|----------------|----------|--------|
| P1-SAAS-EDU-AVL-001 | P1 | AVAILABILITY | 교육 과정 목록 정상 진입 | GET /education-list | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |
| P1-SAAS-EDU-FNC-001 | P1 | FUNCTIONAL | 교육 과정 배정 | POST /educations/{id}/assign | Y | C | HYB | AUTH_LOGIN + FORM_SUBMIT | — | NEW |
| P1-SAAS-EDU-AVL-002 | P1 | AVAILABILITY | TBM 목록 정상 진입 | GET /tbm-list | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |
| P1-SAAS-EDU-FNC-002 | P1 | FUNCTIONAL | TBM 작성 정상 제출 | POST /tbms | Y | C | PW | AUTH_LOGIN + FORM_SUBMIT | — | NEW |
| P2-SAAS-EDU-FNC-001 | P2 | FUNCTIONAL | 교육 세팅 템플릿 관리 | GET/POST /education-templates | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |
| P2-SAAS-EDU-AVL-001 | P2 | AVAILABILITY | 안전회의 기록 목록 진입 | GET /safety-meeting-list | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |

### AREA: BILLING

| QA_ID | PRI | TYPE | QA_NAME | SOURCE | AUTO | SAFE | RUNNER | MODULE_PATTERN | EXISTING | STATUS |
|-------|-----|------|---------|--------|------|------|--------|----------------|----------|--------|
| P1-SAAS-BILL-AVL-001 | P1 | AVAILABILITY | 내 계약 정상 조회 | GET /me/commercial/contract | Y | C | PW | AUTH_LOGIN + DETAIL_LOAD | — | NEW |
| P1-SAAS-BILL-DATA-001 | P1 | DATA | 내 계약 정보 화면/API 정합 | GET /me/commercial/contract → 화면 | Y | C | PW | AUTH_LOGIN + DATA_MATCH | — | NEW |
| P1-SAAS-BILL-FNC-001 | P1 | FUNCTIONAL | 진단 구매 요청 정상 처리 | POST /payments/purchase-diagnosis | P | C | HYB | AUTH_LOGIN + FORM_SUBMIT | — | NEW |
| P2-SAAS-BILL-AVL-001 | P2 | AVAILABILITY | 진단 결과 이력 정상 진입 | GET /diagnosis-results | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |

### AREA: SETTINGS

| QA_ID | PRI | TYPE | QA_NAME | SOURCE | AUTO | SAFE | RUNNER | MODULE_PATTERN | EXISTING | STATUS |
|-------|-----|------|---------|--------|------|------|--------|----------------|----------|--------|
| P1-SAAS-SET-FNC-001 | P1 | FUNCTIONAL | 내 프로필 수정 정상 저장 | PUT /me | Y | C | PW | AUTH_LOGIN + SAVE_UPDATE | — | NEW |
| P1-SAAS-SET-FNC-002 | P1 | FUNCTIONAL | 회사 정보 수정 정상 저장 | PUT /companies/{id} | Y | C | PW | AUTH_LOGIN + SAVE_UPDATE | — | NEW |
| P1-SAAS-SET-FNC-003 | P1 | FUNCTIONAL | 사업장 관리 목록 정상 로드 | GET /factories | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |
| P1-SAAS-SET-FNC-004 | P1 | FUNCTIONAL | 권한 관리 정상 조회/수정 | GET/PUT /permissions | Y | C | PW | AUTH_LOGIN + SAVE_UPDATE | — | NEW |
| P2-SAAS-SET-FNC-001 | P2 | FUNCTIONAL | 조직 설정 정상 조회 | GET /org-settings | Y | C | PW | AUTH_LOGIN + DETAIL_LOAD | — | NEW |
| P2-SAAS-SET-FNC-002 | P2 | FUNCTIONAL | 설비 관리 목록 정상 로드 | GET /equipment-assets | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |
| P2-SAAS-SET-FNC-003 | P2 | FUNCTIONAL | 설비 QR 관리 정상 동작 | GET /equipment-assets/{id}/qr | Y | C | PW | AUTH_LOGIN + DETAIL_LOAD | — | NEW |

### AREA: CONSTRUCTION

| QA_ID | PRI | TYPE | QA_NAME | SOURCE | AUTO | SAFE | RUNNER | MODULE_PATTERN | EXISTING | STATUS |
|-------|-----|------|---------|--------|------|------|--------|----------------|----------|--------|
| P1-SAAS-CON-AVL-001 | P1 | AVAILABILITY | 공사장 목록 정상 진입 | GET /construction-site-list | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |
| P1-SAAS-CON-FNC-001 | P1 | FUNCTIONAL | 건설 Step1 공사 진행 | POST /construction/step1 | Y | C | PW | AUTH_LOGIN + FORM_SUBMIT | — | NEW |
| P1-SAAS-CON-AVL-002 | P1 | AVAILABILITY | 공정 목록 정상 진입 | GET /construction-processes | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |
| P1-SAAS-CON-AVL-003 | P1 | AVAILABILITY | 인력 명부 정상 진입 | GET /construction-workers | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |
| P1-SAAS-CON-AVL-004 | P1 | AVAILABILITY | 공사 점검 정상 진입 | GET /construction-inspections | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |
| P2-SAAS-CON-FNC-001 | P2 | FUNCTIONAL | 공정 추출 정상 처리 | POST /construction-extraction | Y | C | HYB | AUTH_LOGIN + FORM_SUBMIT | — | NEW |

### AREA: RISK

| QA_ID | PRI | TYPE | QA_NAME | SOURCE | AUTO | SAFE | RUNNER | MODULE_PATTERN | EXISTING | STATUS |
|-------|-----|------|---------|--------|------|------|--------|----------------|----------|--------|
| P1-SAAS-RISK-AVL-001 | P1 | AVAILABILITY | 위험도 평가 목록 정상 진입 | GET /risk-assessments | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |
| P1-SAAS-RISK-FNC-001 | P1 | FUNCTIONAL | 위험도 평가 입력 정상 저장 | POST /risk-assessments/{id}/assess | Y | C | PW | AUTH_LOGIN + FORM_SUBMIT | — | NEW |
| P2-SAAS-RISK-FNC-001 | P2 | FUNCTIONAL | 위험도 리포트 발행 | POST /risk-assessments/{id}/publish | Y | C | PW | AUTH_LOGIN + FORM_SUBMIT | — | NEW |
| P2-SAAS-RISK-FNC-002 | P2 | FUNCTIONAL | 평가 척도 관리 CRUD | GET/POST /risk-assessment-scales | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |

### AREA: DOCUMENT

| QA_ID | PRI | TYPE | QA_NAME | SOURCE | AUTO | SAFE | RUNNER | MODULE_PATTERN | EXISTING | STATUS |
|-------|-----|------|---------|--------|------|------|--------|----------------|----------|--------|
| P2-SAAS-DOC-AVL-001 | P2 | AVAILABILITY | 서식 라이브러리 정상 진입 | GET /document-templates | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |
| P2-SAAS-DOC-AVL-002 | P2 | AVAILABILITY | 일정 목록 정상 진입 | GET /work-schedules | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |
| P2-SAAS-DOC-AVL-003 | P2 | AVAILABILITY | 엔진 문서 정상 진입 | GET /engine-documents/{id}/download | Y | C | PW | AUTH_LOGIN + DETAIL_LOAD | — | NEW |
| P2-SAAS-DOC-AVL-004 | P2 | AVAILABILITY | 엔진 일정 정상 진입 | GET /engine-schedules | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |

### AREA: SUPPORT

| QA_ID | PRI | TYPE | QA_NAME | SOURCE | AUTO | SAFE | RUNNER | MODULE_PATTERN | EXISTING | STATUS |
|-------|-----|------|---------|--------|------|------|--------|----------------|----------|--------|
| P2-SAAS-SUP-FNC-001 | P2 | FUNCTIONAL | 고객센터 문의 정상 제출 | POST /contacts | Y | C | PW | AUTH_LOGIN + FORM_SUBMIT | — | NEW |
| P2-SAAS-SUP-AVL-001 | P2 | AVAILABILITY | 도움말 정상 진입 | GET /help-articles | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |
| P2-SAAS-SUP-FNC-002 | P2 | FUNCTIONAL | 사용성 설문 정상 제출 | POST /surveys/response | Y | Y | PW | FORM_SUBMIT | — | NEW |

### AREA: QA

> NOTE: SAAS 앱(/qa/*) = ADMIN 앱(/qa/*) 이중 UI. 동일 /admin/qa/* API 호출. CM-001/CM-002 공유.

| QA_ID | PRI | TYPE | QA_NAME | SOURCE | AUTO | SAFE | RUNNER | MODULE_PATTERN | EXISTING | STATUS |
|-------|-----|------|---------|--------|------|------|--------|----------------|----------|--------|
| P1-SAAS-QA-AVL-001 | P1 | AVAILABILITY | QA 대시보드 정상 진입 | GET /admin/qa/summary | Y | C | PW | AUTH_LOGIN + PAGE_OPEN | — | NEW |
| P1-SAAS-QA-FNC-001 | P1 | FUNCTIONAL | QA 항목 목록 정상 로드 | GET /admin/qa/items | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |
| P1-SAAS-QA-FNC-002 | P1 | FUNCTIONAL | QA 항목 상세 정상 조회 | GET /admin/qa/items (page_size=100) | Y | C | PW | AUTH_LOGIN + DETAIL_LOAD | — | NEW |
| P1-SAAS-QA-FNC-003 | P1 | FUNCTIONAL | QA 실행 이력 정상 조회 | GET /admin/qa/runs | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |
| P1-SAAS-QA-FNC-004 | P1 | FUNCTIONAL | QA 수동 실행 트리거 | POST /admin/qa/runs | Y | C | HYB | AUTH_LOGIN + FORM_SUBMIT | — | NEW |
| P1-SAAS-QA-SEC-001 | P1 | SECURITY | 비관리자 QA 페이지 접근 차단 | GET /qa/* (role_code ≠ '001') | Y | C | PW | ACCESS_DENY | — | NEW |
| P1-SAAS-QA-FNC-005 | P1 | FUNCTIONAL | QA 스케줄 수정 정상 저장 | PATCH /admin/qa/items/{id}/schedule | Y | C | HYB | AUTH_LOGIN + SAVE_UPDATE | — | NEW |

---

## 3. ADMIN 서비스 (admin.taieng.co.kr)

```
AUTH_BOUNDARY: JWT Bearer (Operator role 전용)
SOURCE: tai-admin/admin-vue3/ @ feat/admin-rebuild
NOTE: qa/dashboard.vue = GET /admin/qa/summary / qa/settings.vue = GET /admin/qa/items + PATCH .../schedule (CM-002)
```

### AREA: DASHBOARD

| QA_ID | PRI | TYPE | QA_NAME | SOURCE | AUTO | SAFE | RUNNER | MODULE_PATTERN | EXISTING | STATUS |
|-------|-----|------|---------|--------|------|------|--------|----------------|----------|--------|
| P1-ADMIN-DASH-AVL-001 | P1 | AVAILABILITY | 운영자 대시보드 정상 진입 | GET / (index) | Y | C | PW | AUTH_LOGIN + PAGE_OPEN | — | NEW |
| P1-ADMIN-DASH-FNC-001 | P1 | FUNCTIONAL | 대시보드 핵심 지표 4종 로드 | GET /companies, /subscriptions, /admin/stats, /payments | Y | C | PW | AUTH_LOGIN + DATA_MATCH | — | NEW |
| P1-ADMIN-DASH-SEC-001 | P1 | SECURITY | 비인증 Admin 접근 차단 | admin.taieng.co.kr (JWT 없음) | Y | Y | PW | AUTH_GUARD | — | NEW |

### AREA: OPERATIONS

| QA_ID | PRI | TYPE | QA_NAME | SOURCE | AUTO | SAFE | RUNNER | MODULE_PATTERN | EXISTING | STATUS |
|-------|-----|------|---------|--------|------|------|--------|----------------|----------|--------|
| P1-ADMIN-OPS-AVL-001 | P1 | AVAILABILITY | 관제홈 정상 진입 | GET /ops/home | Y | C | PW | AUTH_LOGIN + PAGE_OPEN | — | NEW |
| P1-ADMIN-OPS-AVL-002 | P1 | AVAILABILITY | 감사로그 목록 정상 로드 | GET /admin/audit-logs | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |
| P1-ADMIN-OPS-FNC-001 | P1 | FUNCTIONAL | QA 항목 목록 정상 로드 (Admin) | GET /admin/qa/items | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |
| P1-ADMIN-OPS-FNC-002 | P1 | FUNCTIONAL | QA 항목 enabled 토글 | PATCH /admin/qa/items/{id} | Y | C | HYB | AUTH_LOGIN + SAVE_UPDATE | — | NEW |
| P1-ADMIN-OPS-FNC-003 | P1 | FUNCTIONAL | QA 수동 실행 dispatch | POST /admin/qa/runs | Y | C | HYB | AUTH_LOGIN + FORM_SUBMIT | — | NEW |
| P1-ADMIN-OPS-FNC-004 | P1 | FUNCTIONAL | QA 실행 이력 목록 로드 | GET /admin/qa/runs | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |
| P1-ADMIN-OPS-FNC-005 | P1 | FUNCTIONAL | 운영 자동화 승인/완료 처리 | POST /automation/runs/{id}/approve | Y | C | HYB | AUTH_LOGIN + FORM_SUBMIT | — | NEW |
| P1-ADMIN-OPS-AVL-003 | P1 | AVAILABILITY | QA 현황 대시보드 정상 진입 | GET /admin/qa/summary | Y | C | PW | AUTH_LOGIN + PAGE_OPEN | — | NEW |
| P1-ADMIN-OPS-AVL-004 | P1 | AVAILABILITY | QA 설정 페이지 정상 진입 | GET /admin/qa/items | Y | C | PW | AUTH_LOGIN + PAGE_OPEN | — | NEW |
| P1-ADMIN-OPS-FNC-006 | P1 | FUNCTIONAL | QA 스케줄 수정 (CM-002 결함 수정 후) | PATCH /admin/qa/items/{id}/schedule | Y | C | HYB | AUTH_LOGIN + SAVE_UPDATE | — | BLOCKED |
| P2-ADMIN-OPS-AVL-001 | P2 | AVAILABILITY | 자동 QA 대시보드 정상 진입 | Supabase REST auto_qa_checks | Y | C | PW | AUTH_LOGIN + PAGE_OPEN | — | NEW |
| P2-ADMIN-OPS-AVL-002 | P2 | AVAILABILITY | 내부 API 모니터 정상 진입 | GET /internal-api-registry | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |

### AREA: CUSTOMER

| QA_ID | PRI | TYPE | QA_NAME | SOURCE | AUTO | SAFE | RUNNER | MODULE_PATTERN | EXISTING | STATUS |
|-------|-----|------|---------|--------|------|------|--------|----------------|----------|--------|
| P1-ADMIN-CUST-AVL-001 | P1 | AVAILABILITY | 고객 360 정상 진입 | GET /companies/{id}/360 | Y | C | PW | AUTH_LOGIN + DETAIL_LOAD | — | NEW |
| P1-ADMIN-CUST-FNC-001 | P1 | FUNCTIONAL | 회사 관리 목록 정상 로드 | GET /companies | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |
| P1-ADMIN-CUST-FNC-002 | P1 | FUNCTIONAL | 회사 생성/수정 정상 처리 | POST/PATCH /companies | Y | C | HYB | AUTH_LOGIN + FORM_SUBMIT | — | NEW |
| P1-ADMIN-CUST-FNC-003 | P1 | FUNCTIONAL | 시설 관리 목록 정상 로드 | GET /factories | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |
| P1-ADMIN-CUST-FNC-004 | P1 | FUNCTIONAL | 회원 관리 목록 정상 로드 | GET /users | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |
| P1-ADMIN-CUST-FNC-005 | P1 | FUNCTIONAL | 문의 관리 목록/상세 조회 | GET /admin/inquiries | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |
| P2-ADMIN-CUST-AVL-001 | P2 | AVAILABILITY | 온보딩 현황 정상 진입 | GET /companies/{id}/onboarding | Y | C | PW | AUTH_LOGIN + DETAIL_LOAD | — | NEW |

### AREA: BILLING

| QA_ID | PRI | TYPE | QA_NAME | SOURCE | AUTO | SAFE | RUNNER | MODULE_PATTERN | EXISTING | STATUS |
|-------|-----|------|---------|--------|------|------|--------|----------------|----------|--------|
| P0-ADMIN-BILL-FNC-001 | P0 | FUNCTIONAL | 결제원장 목록 정상 로드 | GET /payments | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |
| P0-ADMIN-BILL-FNC-002 | P0 | FUNCTIONAL | 구독/계약 목록 정상 로드 | GET /contracts | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |
| P1-ADMIN-BILL-AVL-001 | P1 | AVAILABILITY | 경영지표 정상 진입 | GET /stats/business | Y | C | PW | AUTH_LOGIN + PAGE_OPEN | — | NEW |
| P1-ADMIN-BILL-FNC-001 | P1 | FUNCTIONAL | 결제원장 상세/원장 조회 | GET /payments/{id}/ledger | Y | C | PW | AUTH_LOGIN + DETAIL_LOAD | — | NEW |
| P1-ADMIN-BILL-FNC-002 | P1 | FUNCTIONAL | 계약 활성화 처리 | PATCH /contracts/{id}/activate | Y | C | HYB | AUTH_LOGIN + SAVE_UPDATE | — | NEW |
| P1-ADMIN-BILL-FNC-003 | P1 | FUNCTIONAL | 세금계산서 관리 목록 | GET /payments/admin/tax-invoices | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |
| P1-ADMIN-BILL-FNC-004 | P1 | FUNCTIONAL | 실행 게이트 상태 조회 | GET /payments/ops/gate-readiness | Y | C | PW | AUTH_LOGIN + DETAIL_LOAD | — | NEW |
| P1-ADMIN-BILL-FNC-005 | P1 | FUNCTIONAL | 견적서 목록/상세 정상 로드 | GET /admin/quotes | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |
| P1-ADMIN-BILL-FNC-006 | P1 | FUNCTIONAL | 견적서 발행 정상 처리 | POST /admin/quotes/{id}/issue | Y | C | HYB | AUTH_LOGIN + FORM_SUBMIT | — | NEW |
| P1-ADMIN-BILL-FNC-007 | P1 | FUNCTIONAL | 가격 설정 조회 | GET /price/summary-cards | Y | C | PW | AUTH_LOGIN + DETAIL_LOAD | — | NEW |
| P1-ADMIN-BILL-SEC-001 | P1 | SECURITY | 결제 취소/환불 비인증 접근 차단 | POST /payments/{id}/cancel (role check) | Y | C | HYB | ACCESS_DENY | — | NEW |
| P1-ADMIN-BILL-DATA-001 | P1 | DATA | 결제원장 화면/API 금액 정합 | GET /payments → 화면 표시 금액 | Y | C | PW | AUTH_LOGIN + DATA_MATCH | — | NEW |
| P1-ADMIN-BILL-FNC-008 | P1 | FUNCTIONAL | 결제 수동 환불 처리 | POST /payments/{id}/refund | P | N | MANUAL | AUTH_LOGIN + FORM_SUBMIT | — | MANUAL_ONLY |

> **P0-ADMIN-BILL-FNC-001 EXPECTED**: 결제원장 목록 정상 렌더링, 페이지 로드 후 데이터 표시, fatal error 없음  
> **P0-ADMIN-BILL-FNC-002 EXPECTED**: 계약 목록 정상 렌더링, 계약 상태 표시, fatal error 없음  
> **NOTES P1-ADMIN-BILL-FNC-008**: 실환불(PROD_SAFE=N) — staging/test 계정 환경에서만 자동화 가능

### AREA: SERVICE

| QA_ID | PRI | TYPE | QA_NAME | SOURCE | AUTO | SAFE | RUNNER | MODULE_PATTERN | EXISTING | STATUS |
|-------|-----|------|---------|--------|------|------|--------|----------------|----------|--------|
| P1-ADMIN-SVC-AVL-001 | P1 | AVAILABILITY | 익명 법령진단 목록 정상 로드 | GET /anonymous-diagnosis/admin/list | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |
| P1-ADMIN-SVC-AVL-002 | P1 | AVAILABILITY | 법령진단 리포트 뷰어 정상 진입 | GET /legal-engine/result/{id} | Y | C | PW | AUTH_LOGIN + DETAIL_LOAD | — | NEW |
| P1-ADMIN-SVC-FNC-001 | P1 | FUNCTIONAL | 진단 연결 처리 | GET /system-codes/diagnosis_* | Y | C | PW | AUTH_LOGIN + FORM_SUBMIT | — | NEW |
| P1-ADMIN-SVC-AVL-003 | P1 | AVAILABILITY | 교육 이수현황 정상 진입 | GET /companies (MOCK 포함) | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |
| P1-ADMIN-SVC-FNC-002 | P1 | FUNCTIONAL | SaaS 권한 관리 조회/수정 | GET/PATCH /permissions | Y | C | PW | AUTH_LOGIN + SAVE_UPDATE | — | NEW |
| P1-ADMIN-SVC-FNC-003 | P1 | FUNCTIONAL | 플랫폼 권한 조회/수정 | GET/PATCH /permissions/platform | Y | C | PW | AUTH_LOGIN + SAVE_UPDATE | — | NEW |
| P1-ADMIN-SVC-FNC-004 | P1 | FUNCTIONAL | SaaS FAQ 관리 CRUD | GET /admin/site-faqs | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |
| P2-ADMIN-SVC-AVL-001 | P2 | AVAILABILITY | 매뉴얼 목록 정상 진입 | GET /admin/manual | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |
| P2-ADMIN-SVC-AVL-002 | P2 | AVAILABILITY | 교육 마스터(MOCK) 정상 진입 | GET /system-codes/* (MOCK) | Y | C | PW | AUTH_LOGIN + PAGE_OPEN | — | NEW |
| P2-ADMIN-SVC-AVL-003 | P2 | AVAILABILITY | SaaS 알림 설정(MOCK) 정상 진입 | 로컬 상태 MOCK | Y | C | PW | AUTH_LOGIN + PAGE_OPEN | — | NEW |

### AREA: COMMUNICATION

| QA_ID | PRI | TYPE | QA_NAME | SOURCE | AUTO | SAFE | RUNNER | MODULE_PATTERN | EXISTING | STATUS |
|-------|-----|------|---------|--------|------|------|--------|----------------|----------|--------|
| P1-ADMIN-COMM-AVL-001 | P1 | AVAILABILITY | 메일 목록 정상 로드 | GET /mail/list | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |
| P1-ADMIN-COMM-FNC-001 | P1 | FUNCTIONAL | 메일 상세 정상 조회 | GET /mail/{id} | Y | C | PW | AUTH_LOGIN + DETAIL_LOAD | — | NEW |
| P1-ADMIN-COMM-AVL-002 | P1 | AVAILABILITY | 공지사항 목록 정상 로드 | GET /notices | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |
| P1-ADMIN-COMM-FNC-002 | P1 | FUNCTIONAL | 공지사항 등록 정상 처리 | POST /notices | Y | C | PW | AUTH_LOGIN + FORM_SUBMIT | — | NEW |
| P2-ADMIN-COMM-AVL-001 | P2 | AVAILABILITY | 알림센터 정상 진입 | GET /notifications/feed | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |
| P2-ADMIN-COMM-FNC-001 | P2 | FUNCTIONAL | 푸시 테스트 정상 동작 | push endpoint | Y | C | HYB | AUTH_LOGIN + FORM_SUBMIT | — | NEW |

### AREA: MARKETING

| QA_ID | PRI | TYPE | QA_NAME | SOURCE | AUTO | SAFE | RUNNER | MODULE_PATTERN | EXISTING | STATUS |
|-------|-----|------|---------|--------|------|------|--------|----------------|----------|--------|
| P1-ADMIN-MKT-AVL-001 | P1 | AVAILABILITY | 마케팅 대시보드 정상 진입 | GET /admin/marketing/dashboard | Y | C | PW | AUTH_LOGIN + PAGE_OPEN | — | NEW |
| P1-ADMIN-MKT-AVL-002 | P1 | AVAILABILITY | 지식인 관리 목록 정상 로드 | Supabase naver_kin_log | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |
| P1-ADMIN-MKT-FNC-001 | P1 | FUNCTIONAL | 발행 운영 요청 목록 로드 | GET /admin/marketing/publish/options/* | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |
| P1-ADMIN-MKT-AVL-003 | P1 | AVAILABILITY | 콘텐츠 목록 정상 로드 | GET /admin/marketing/contents | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |
| P1-ADMIN-MKT-AVL-004 | P1 | AVAILABILITY | 배포 관리 목록 정상 로드 | GET /admin/marketing/publish-jobs | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |
| P1-ADMIN-MKT-AVL-005 | P1 | AVAILABILITY | 성과 정상 진입 | GET /admin/marketing/performance | Y | C | PW | AUTH_LOGIN + PAGE_OPEN | — | NEW |
| P1-ADMIN-MKT-FNC-002 | P1 | FUNCTIONAL | 채널 활성화/비활성화 처리 | POST /admin/marketing/channels/{code}/activate | Y | C | HYB | AUTH_LOGIN + SAVE_UPDATE | — | NEW |
| P1-ADMIN-MKT-AVL-006 | P1 | AVAILABILITY | 고객 레지스트리 목록 로드 | GET /admin/marketing/customers | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |
| P1-ADMIN-MKT-AVL-007 | P1 | AVAILABILITY | Journey 레지스트리 목록 로드 | GET /admin/marketing/journeys | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |
| P1-ADMIN-MKT-FNC-003 | P1 | FUNCTIONAL | Strategy 생성 정상 처리 | POST /admin/marketing/strategies | Y | C | HYB | AUTH_LOGIN + FORM_SUBMIT | — | NEW |
| P1-ADMIN-MKT-FNC-004 | P1 | FUNCTIONAL | Contract 활성화 처리 | POST /admin/marketing/contracts/{code}/activate | Y | C | HYB | AUTH_LOGIN + SAVE_UPDATE | — | NEW |
| P1-ADMIN-MKT-AVL-008 | P1 | AVAILABILITY | 큐 목록 정상 로드 | GET /admin/marketing/queue | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |
| P1-ADMIN-MKT-FNC-005 | P1 | FUNCTIONAL | 스케줄러 run-once 실행 | POST /admin/marketing/scheduler/run-once | Y | C | HYB | AUTH_LOGIN + FORM_SUBMIT | — | NEW |
| P1-ADMIN-MKT-FNC-006 | P1 | FUNCTIONAL | 마케팅 감사 목록 로드 | GET /admin/marketing/audit | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |

### AREA: STATISTICS

| QA_ID | PRI | TYPE | QA_NAME | SOURCE | AUTO | SAFE | RUNNER | MODULE_PATTERN | EXISTING | STATUS |
|-------|-----|------|---------|--------|------|------|--------|----------------|----------|--------|
| P1-ADMIN-STAT-AVL-001 | P1 | AVAILABILITY | 운영개요 정상 진입 | GET /stats/overview?days=N | Y | C | PW | AUTH_LOGIN + PAGE_OPEN | — | NEW |
| P1-ADMIN-STAT-AVL-002 | P1 | AVAILABILITY | 진단 퍼널 정상 진입 | GET /stats/funnel?days=N | Y | C | PW | AUTH_LOGIN + PAGE_OPEN | — | NEW |
| P1-ADMIN-STAT-AVL-003 | P1 | AVAILABILITY | 고객사·사업장 통계 정상 진입 | GET /stats/customers?days=N | Y | C | PW | AUTH_LOGIN + PAGE_OPEN | — | NEW |
| P1-ADMIN-STAT-AVL-004 | P1 | AVAILABILITY | 매출·결제 통계 정상 진입 | GET /stats/revenue?days=N | Y | C | PW | AUTH_LOGIN + PAGE_OPEN | — | NEW |
| P1-ADMIN-STAT-AVL-005 | P1 | AVAILABILITY | 서비스 이행 통계 정상 진입 | GET /stats/fulfillment?days=N | Y | C | PW | AUTH_LOGIN + PAGE_OPEN | — | NEW |
| P1-ADMIN-STAT-AVL-006 | P1 | AVAILABILITY | 워커 활동 통계 정상 진입 | GET /stats/workers?days=N | Y | C | PW | AUTH_LOGIN + PAGE_OPEN | — | NEW |
| P1-ADMIN-STAT-DATA-001 | P1 | DATA | 운영개요 지표 화면/API 정합 | GET /stats/overview → 화면 | Y | C | PW | AUTH_LOGIN + DATA_MATCH | — | NEW |

### AREA: DEVTOOLS

| QA_ID | PRI | TYPE | QA_NAME | SOURCE | AUTO | SAFE | RUNNER | MODULE_PATTERN | EXISTING | STATUS |
|-------|-----|------|---------|--------|------|------|--------|----------------|----------|--------|
| P1-ADMIN-DEV-FNC-001 | P1 | FUNCTIONAL | 전역변수 목록/수정 정상 동작 | GET/PATCH /system-codes | Y | C | PW | AUTH_LOGIN + SAVE_UPDATE | — | NEW |
| P1-ADMIN-DEV-AVL-001 | P1 | AVAILABILITY | 법규 엔진 대시보드 정상 진입 | GET /legal-engine/dashboard | Y | C | PW | AUTH_LOGIN + PAGE_OPEN | — | NEW |
| P1-ADMIN-DEV-FNC-002 | P1 | FUNCTIONAL | AI 룰 생성/초안 저장 | POST /legal-engine/parse | Y | C | HYB | AUTH_LOGIN + FORM_SUBMIT | — | NEW |
| P1-ADMIN-DEV-AVL-002 | P1 | AVAILABILITY | 관제센터 정상 진입 | GET /control-runtime/health | Y | C | PW | AUTH_LOGIN + PAGE_OPEN | — | NEW |
| P1-ADMIN-DEV-FNC-003 | P1 | FUNCTIONAL | 크론 관리 목록/수동 실행 | GET /cron/scheduler-status, POST /cron/jobs/{code}/run | Y | C | HYB | AUTH_LOGIN + LIST_LOAD | — | NEW |
| P1-ADMIN-DEV-AVL-003 | P1 | AVAILABILITY | Watch Engine 정상 진입 | GET /watch-engine/* | Y | C | PW | AUTH_LOGIN + PAGE_OPEN | — | NEW |
| P2-ADMIN-DEV-AVL-001 | P2 | AVAILABILITY | 설비 엔진 정상 진입 | GET /engine-equipment/stats | Y | C | PW | AUTH_LOGIN + PAGE_OPEN | — | NEW |
| P2-ADMIN-DEV-AVL-002 | P2 | AVAILABILITY | 모델 엔진 정상 진입 | GET /engine-model/stats | Y | C | PW | AUTH_LOGIN + PAGE_OPEN | — | NEW |
| P2-ADMIN-DEV-AVL-003 | P2 | AVAILABILITY | 공정 엔진(산업) 정상 진입 | GET /engine-industry/stats | Y | C | PW | AUTH_LOGIN + PAGE_OPEN | — | NEW |
| P2-ADMIN-DEV-AVL-004 | P2 | AVAILABILITY | 공정 엔진(건설) 정상 진입 | GET /byulpyo/kcsc-process | Y | C | PW | AUTH_LOGIN + PAGE_OPEN | — | NEW |
| P2-ADMIN-DEV-AVL-005 | P2 | AVAILABILITY | 스케줄 엔진 정상 진입 | GET /inspection-schedule/rules | Y | C | PW | AUTH_LOGIN + PAGE_OPEN | — | NEW |
| P2-ADMIN-DEV-AVL-006 | P2 | AVAILABILITY | 문서 엔진 정상 진입 | GET /document-forms | Y | C | PW | AUTH_LOGIN + PAGE_OPEN | — | NEW |
| P2-ADMIN-DEV-AVL-007 | P2 | AVAILABILITY | 문서 스키마 정상 진입 | GET /document-schema/{dt} | Y | C | PW | AUTH_LOGIN + PAGE_OPEN | — | NEW |
| P2-ADMIN-DEV-FNC-001 | P2 | FUNCTIONAL | QA 엔진 진단 실행 | POST /legal-engine/qa-run | Y | C | HYB | AUTH_LOGIN + FORM_SUBMIT | — | NEW |
| P2-ADMIN-DEV-AVL-008 | P2 | AVAILABILITY | 문서출력 정상 진입 | GET /watch-engine/documents/summary | Y | C | PW | AUTH_LOGIN + PAGE_OPEN | — | NEW |
| P2-ADMIN-DEV-AVL-009 | P2 | AVAILABILITY | 다이어그램 갤러리 정상 진입 | Supabase REST diagram_templates | Y | C | PW | AUTH_LOGIN + LIST_LOAD | — | NEW |

---

## 4. API Backend (api.taieng.co.kr)

```
AUTH_BOUNDARY: JWT Bearer /admin/* — Operator
               X-Internal-Secret /internal/*
               인증 불필요 /public/*
NOTE: API QA는 UI와 독립적인 API 계약/보안 검증. UI QA와 중복되지 않음.
```

### AREA: QA API

| QA_ID | PRI | TYPE | QA_NAME | SOURCE | AUTO | SAFE | RUNNER | MODULE_PATTERN | EXISTING | STATUS |
|-------|-----|------|---------|--------|------|------|--------|----------------|----------|--------|
| P0-API-QA-API-001 | P0 | API | QA 수동 실행 생성 API 정상 응답 | POST /admin/qa/runs | Y | C | API | API_CONTRACT | — | NEW |
| P0-API-QA-API-002 | P0 | API | QA 결과 콜백 수신 API 정상 처리 | POST /internal/qa/runs/{run_id}/results | Y | C | API | API_CONTRACT | — | NEW |
| P0-API-QA-API-003 | P0 | API | QA 스케줄 틱 정상 처리 | POST /internal/scheduler/qa/tick | Y | C | API | API_CONTRACT | — | NEW |
| P1-API-QA-API-001 | P1 | API | QA 요약 API 응답 구조 검증 | GET /admin/qa/summary | Y | Y | API | API_CONTRACT | — | NEW |
| P1-API-QA-API-002 | P1 | API | QA 항목 목록 API 필터 동작 검증 | GET /admin/qa/items?service_code=WWW | Y | C | API | API_CONTRACT | — | NEW |
| P1-API-QA-API-003 | P1 | API | QA Taxonomy API 4종 서비스 반환 | GET /admin/qa/taxonomy | Y | Y | API | API_CONTRACT | — | NEW |
| P1-API-QA-API-004 | P1 | API | QA 실행 이력 목록 API 검증 | GET /admin/qa/runs | Y | C | API | API_CONTRACT | — | NEW |
| P1-API-QA-API-005 | P1 | API | QA 항목 enabled 수정 API 검증 | PATCH /admin/qa/items/{id} | Y | C | API | API_CONTRACT | — | NEW |
| P1-API-QA-SEC-001 | P1 | SECURITY | QA API 비인증 접근 차단 | GET /admin/qa/summary (Bearer 없음) | Y | Y | API | ACCESS_DENY | — | NEW |

> **P0-API-QA-API-001 EXPECTED**: POST body {qa_item_ids:[id]} → 201, {status:"success", data:{id,run_status}, dispatch:"OK"/"SKIPPED"/"ERROR"}  
> **P0-API-QA-API-002 EXPECTED**: POST X-Internal-Secret valid → 200, 결과 DB 저장 확인  
> **P0-API-QA-API-003 EXPECTED**: POST X-Internal-Secret valid → 200, 스케줄 tick 처리 완료

### AREA: AUTH API

| QA_ID | PRI | TYPE | QA_NAME | SOURCE | AUTO | SAFE | RUNNER | MODULE_PATTERN | EXISTING | STATUS |
|-------|-----|------|---------|--------|------|------|--------|----------------|----------|--------|
| P0-API-AUTH-API-001 | P0 | API | 로그인 API 정상 응답 | POST /auth/login | Y | C | API | API_CONTRACT | — | NEW |
| P0-API-AUTH-SEC-001 | P0 | SECURITY | 잘못된 자격증명 로그인 거부 | POST /auth/login (wrong pw) | Y | Y | API | API_ERROR | — | NEW |
| P1-API-AUTH-API-001 | P1 | API | 회원가입 API 응답 구조 검증 | POST /auth/register | Y | C | API | API_CONTRACT | — | NEW |
| P1-API-AUTH-API-002 | P1 | API | 소셜 ensure-user API 검증 | POST /auth/ensure-user | Y | C | API | API_CONTRACT | — | NEW |
| P1-API-AUTH-API-003 | P1 | API | 내 정보 수정 API 검증 | PATCH /auth/me | Y | C | API | API_CONTRACT | — | NEW |

> **P0-API-AUTH-API-001 EXPECTED**: 유효 자격증명 → 200, {access_token, expires_in, user_id} 포함  
> **P0-API-AUTH-SEC-001 EXPECTED**: 잘못된 비밀번호 → 401/400, 토큰 미발급

### AREA: DIAGNOSIS API

| QA_ID | PRI | TYPE | QA_NAME | SOURCE | AUTO | SAFE | RUNNER | MODULE_PATTERN | EXISTING | STATUS |
|-------|-----|------|---------|--------|------|------|--------|----------------|----------|--------|
| P0-API-DIAG-API-001 | P0 | API | 무료진단 실행 API 정상 응답 | POST /diagnosis/run | Y | Y | API | API_CONTRACT | — | NEW |
| P1-API-DIAG-API-001 | P1 | API | 진단 결과 조회 API 검증 | GET /diagnosis/result/{token} | Y | C | API | API_CONTRACT | — | NEW |
| P1-API-DIAG-API-002 | P1 | API | 유료진단 가격 티어 API 검증 | GET /diagnosis/price-tier | Y | Y | API | API_CONTRACT | — | NEW |
| P1-API-DIAG-API-003 | P1 | API | 유료진단 결과 조회 API 검증 | GET /diagnosis/paid-result/{token} | Y | C | API | API_CONTRACT | — | NEW |

> **P0-API-DIAG-API-001 EXPECTED**: POST 유효 진단 입력 → 200, {token, result_summary} 포함, 30초 이내 응답

### AREA: PAYMENT API

| QA_ID | PRI | TYPE | QA_NAME | SOURCE | AUTO | SAFE | RUNNER | MODULE_PATTERN | EXISTING | STATUS |
|-------|-----|------|---------|--------|------|------|--------|----------------|----------|--------|
| P0-API-PAY-API-001 | P0 | API | 결제 내역 조회 API 정상 응답 | GET /payments | Y | C | API | API_CONTRACT | — | NEW |
| P0-API-PAY-API-002 | P0 | API | 계약 정보 조회 API 정상 응답 | GET /me/commercial/contract | Y | C | API | API_CONTRACT | — | NEW |
| P1-API-PAY-API-001 | P1 | API | 견적서 목록 API 검증 | GET /admin/quotes | Y | C | API | API_CONTRACT | — | NEW |
| P1-API-PAY-API-002 | P1 | API | 진단 구매 API 검증 | POST /payments/purchase-diagnosis | Y | C | API | API_CONTRACT | — | NEW |
| P1-API-PAY-SEC-001 | P1 | SECURITY | 결제 내역 타 사용자 접근 차단 | GET /payments (다른 company_id) | Y | C | API | TENANT_ISOLATION | — | NEW |

> **P0-API-PAY-API-001 EXPECTED**: GET (인증) → 200, {items: Array, total: number} 구조, items 각 {id, amount, status} 포함  
> **P0-API-PAY-API-002 EXPECTED**: GET (인증) → 200, {contract_status, plan_code, expires_at} 포함

### AREA: PUBLIC API

| QA_ID | PRI | TYPE | QA_NAME | SOURCE | AUTO | SAFE | RUNNER | MODULE_PATTERN | EXISTING | STATUS |
|-------|-----|------|---------|--------|------|------|--------|----------------|----------|--------|
| P0-API-PUB-API-001 | P0 | API | 공지사항 API 정상 응답 | GET /notices/active | Y | Y | API | API_CONTRACT | — | NEW |
| P0-API-PUB-API-002 | P0 | API | 통합검색 API 정상 응답 | GET /public/safety-search?q=지게차 | Y | Y | API | API_CONTRACT + SEARCH_RESULT | — | NEW |
| P1-API-PUB-API-001 | P1 | API | 요금제 조회 API 검증 | GET /public/pricing/all | Y | Y | API | API_CONTRACT | — | NEW |

> **P0-API-PUB-API-001 EXPECTED**: GET → 200, {items: Array} (비어있어도 정상), 인증 불필요  
> **P0-API-PUB-API-002 EXPECTED**: GET ?q=지게차 → 200, {results:[{type, items}]} 포함, 응답 5초 이내

---

## Module Pattern Summary

전체 Catalog의 MODULE_PATTERN 집계.

| MODULE_PATTERN | QA 수 | 대표 QA | 필요 Runner | REUSE 등급 |
|----------------|-------|---------|------------|-----------|
| `PAGE_OPEN` | 55 | P0-WWW-001, P0-DIAG-001, P0-SRCH-001 | PW | **REUSE_CORE** |
| `AUTH_LOGIN` | 145 | P0-SAAS-001, P0-MYP-001 (선행 패턴) | PW | **REUSE_CORE** |
| `LIST_LOAD` | 60 | P0-MYP-005, P1-ADMIN-BILL-FNC-001 | PW/HYB | **REUSE_CORE** |
| `AUTH_GUARD` | 5 | P1-WWW-AUTH-SEC-001, P1-SAAS-AUTH-SEC-001 | PW/API | **REUSE_CORE** |
| `API_CONTRACT` | 24 | P0-API-QA-API-001, P0-API-AUTH-API-001 | API | **REUSE_CORE** |
| `E2E_FLOW` | 8 | P0-SAAS-001, P0-WWW-003 | PW | **REUSE_CORE** |
| `DETAIL_LOAD` | 20 | P1-SAAS-MYP-FNC-002 | PW | **REUSE_CORE** |
| `FORM_SUBMIT` | 29 | P1-WWW-AUTH-FNC-001, P0-API-QA-API-001 | PW/HYB | **REUSE_CORE** |
| `SAVE_UPDATE` | 14 | P1-SAAS-SET-FNC-001 | PW/HYB | **REUSE_CORE** |
| `ACCESS_DENY` | 3 | P1-ADMIN-BILL-SEC-001, P1-SAAS-QA-SEC-001 | PW/API | **REUSE_CORE** |
| `DATA_MATCH` | 5 | P1-SAAS-MYP-DATA-001, P1-ADMIN-BILL-DATA-001 | PW/HYB | **REUSE_OPTIONAL** |
| `SEARCH_RESULT` | 2 | P0-SRCH-002, P0-API-PUB-API-002 | PW | **REUSE_OPTIONAL** |
| `NAVIGATE` | 1 | P0-WWW-005 | PW | **REUSE_OPTIONAL** |
| `TENANT_ISOLATION` | 1 | P1-API-PAY-SEC-001 | API | **REUSE_OPTIONAL** |
| `API_ERROR` | 1 | P0-API-AUTH-SEC-001 | API | **REUSE_OPTIONAL** |
| `FILTER_RESULT` | 0 | — | API | **REUSE_OPTIONAL** |
| `DATA_PERSISTENCE` | 0 | — | — | LOCAL |
| `PERF_PAGE_LOAD` | 0 | — | — | LOCAL |
| `PERF_API_RESPONSE` | 0 | — | — | LOCAL |
| `VISUAL_BASELINE` | 1 | P2-WWW-HEADER-VIS-001 | PW | LOCAL |
| `A11Y_BASIC` | 0 | — | — | LOCAL |
| `DELETE_CONFIRM` | 0 | — | — | LOCAL |

> **PERFORMANCE / ACCESSIBILITY / VISUAL**: source에서 측정 기준이 명시된 항목 없음 → P2 대상 추후 WO에서 별도 정의

---

## 최종 통계

```
TOTAL QA:     219

P0:            22
P1:           139
P2:            58

WWW:           41
SAAS:          64
ADMIN:         88
API:           26

AVAILABILITY:  89
FUNCTIONAL:    86
E2E:            3
SECURITY:      10
API:           24
DATA:           4
INTEGRATION:    2
VISUAL:         1
PERFORMANCE:    0
ACCESSIBILITY:  0

AUTOMATABLE YES:     213
AUTOMATABLE PARTIAL:   5
AUTOMATABLE NO:        1 (Inicis 결제 MANUAL_ONLY)

PROD_SAFE YES:         44
PROD_SAFE CONDITIONAL: 173
PROD_SAFE NO:           2

EXISTING:      10  (P0-WWW-001/003/004/005, P0-DIAG-001, P0-SRCH-001/002, P0-MYP-001/005, P0-SAAS-001)
NEW:          206
MANUAL_ONLY:    2  (Inicis 결제 / 수동 환불)
BLOCKED:        1  (P1-ADMIN-OPS-FNC-006: CM-002 스케줄 결함)

ADMIN UNVERIFIED 처리:
  VERIFIED:   26  (소스 직접 확인)
  EXCLUDED:    0

UNVERIFIED:    0  (QA 미생성 = source 근거 없음, 추측 금지 원칙 준수)
```

---

## 기존 10개 Scenario 연결 확인

| scenario_id | 이 Catalog 위치 | STATUS | MODULE_PATTERN 신규 태깅 |
|-------------|----------------|--------|------------------------|
| P0-WWW-001 | WWW/LANDING | EXISTING | PAGE_OPEN |
| P0-DIAG-001 | WWW/FREE_DIAGNOSIS | EXISTING | PAGE_OPEN |
| P0-SRCH-001 | WWW/SEARCH | EXISTING | PAGE_OPEN |
| P0-SRCH-002 | WWW/SEARCH | EXISTING | SEARCH_RESULT |
| P0-MYP-001 | SAAS/MYPAGE | EXISTING | AUTH_LOGIN + PAGE_OPEN |
| P0-MYP-005 | SAAS/MYPAGE | EXISTING | AUTH_LOGIN + LIST_LOAD |
| P0-SAAS-001 | SAAS/AUTH | EXISTING | E2E_FLOW + AUTH_LOGIN |
| P0-WWW-003 | WWW/AUTH | EXISTING | E2E_FLOW + AUTH_LOGIN |
| P0-WWW-004 | WWW/HEADER | EXISTING | AUTH_LOGIN + PAGE_OPEN |
| P0-WWW-005 | WWW/HEADER | EXISTING | AUTH_LOGIN + NAVIGATE |

10/10 연결 완료.
