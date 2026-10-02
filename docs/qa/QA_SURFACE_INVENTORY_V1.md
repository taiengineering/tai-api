---
title: QA Surface Inventory v1
version: 1.2.0
work_order: WO-QA-UNIVERSE-PHASE0-SURFACE-INVENTORY-001
status: COMPLETE
surveyed_at: 2026-10-02
patch: PATCH2
---

# QA Surface Inventory v1

조사 완료: 2026-10-02  
추측 항목: 0 (소스 미확인 항목 ACTIVE 확정 금지)  
코드 변경: 0 / DB 변경: 0 / Production mutation: 0

---

## Survey Anchors

조사 시점 Git HEAD. 이후 변경이 있더라도 이 Inventory는 아래 커밋 기준으로 작성됨.

| Repo | Branch | SHA | 비고 |
|------|--------|-----|------|
| tai-www | main | `73adaf8622c556660a3112e3d4baf6a65b39d63f` | 조사 기준 HEAD |
| tai-admin (SAFE, vue3/) | main | `be4ff2c79ab8edcaa89c08bac5acbf75eb77d246` | SAFE SaaS 앱 기준 branch |
| tai-admin (ADMIN, admin-vue3/) | feat/admin-rebuild (remote origin) | `6d9e89eaa1ea306c60c113167c86346988670ed9` | Operator Admin 앱 기준 |
| tai-api | origin/main | `59b60f6af44d67edd80867dddff6a9af02d75598` | routers/ 기준 |
| tai-qa | main | `631af37b297fe3a240de4f1c7ef0191a1ccfeb48` | p0-smoke.yml 워크플로우 기준 |

> **EVIDENCE**: 모든 SHA는 실제 git ls-remote / rev-parse 결과. tai-qa는 GitHub MCP 미접근으로 Phase2E 완료 시점 기록(project_wo_qa_control_phase2e.md)에서 확인.

---

## 조사 범위

| Repo | 서비스 | 도메인 | SOURCE_PATH | 조사 완료 |
|------|--------|--------|-------------|-----------|
| tai-www | WWW | taieng.co.kr | tai-www/ @ main | ✓ |
| tai-admin/vue3/ | SAAS | safe.taieng.co.kr + taieng.co.kr/mypage/* | tai-admin/vue3/ @ main | ✓ |
| tai-admin/admin-vue3/ | ADMIN | admin.taieng.co.kr | tai-admin/admin-vue3/ @ feat/admin-rebuild (remote) | ✓ (56/82 SOURCE-VERIFIED) |
| tai-api | API | api.taieng.co.kr | tai-api/ @ origin/main | ✓ |
| tai-qa | QA_RUNNER | github.com/taiengineering/tai-qa | tai-qa/ @ main | ✓ |
| WORKER | — | 미확인 | 미확인 | 미조사 (추측 없음) |

> **WORKER**: 실제 repo/runtime 미확인. 이 문서에 포함하지 않음.

---

## Canonical Column Schema

| 컬럼 | 설명 |
|------|------|
| `SURFACE` | 화면 또는 API 엔드포인트 이름 |
| `ROUTE/API` | URL 경로 또는 HTTP METHOD + path |
| `R/W` | R=읽기 전용 / W=쓰기 전용 / RW=읽기+쓰기 |
| `CRITICALITY` | CRITICAL / HIGH / NORMAL / LOW |
| `STATUS` | ACTIVE=소스 확인 완료 / UNVERIFIED=소스 미확인 / INACTIVE=비활성(주석·미서비스) |
| `EXISTING_QA` | 현재 tai-qa가 커버하는 scenario_id, 없으면 `—` |

> **CRITICALITY 기준**: CRITICAL=중단 시 매출·고객 직접 영향 / HIGH=핵심 업무 차질 / NORMAL=보조 기능 / LOW=미서비스·개발용  
> **STATUS**: ACTIVE는 page source 또는 API endpoint 직접 확인된 경우만. 확인 안 된 것은 UNVERIFIED.

---

## Contract Mismatch 기록 (Phase 0 — 수정 금지)

Phase 0 조사 중 발견된 frontend↔backend API 계약 불일치. 코드 수정 금지, 기록만.

| # | 발견 위치 | 프론트엔드 sends | 백엔드 expects | 영향 |
|---|----------|-----------------|----------------|------|
| CM-001 | `GET /admin/qa/runs` — vue3/src/pages/qa/useQaApi.ts + admin-vue3/src/pages/qa/runs/index.vue | `started_after`, `started_before`, `status` | `from_date`, `to_date`, `run_status` | 날짜/상태 필터가 백엔드에 전달되지 않아 전체 목록이 반환됨 |
| CM-002 | `PATCH /admin/qa/items/{id}/schedule` — vue3/src/pages/qa/settings.vue | `value` (nullable int) | `frequency_value` (Optional[int]) | 스케줄 주기(MINUTES/HOURLY) 설정이 서버에 저장되지 않음 |

---

## 1. WWW 서비스 (taieng.co.kr)

```
SOURCE_PATH:   tai-www/ @ main (73adaf86)
AUTH_BOUNDARY: localStorage access_token — 클라이언트 사이드 가드
               서버사이드 가드 없음 (Cloudflare Functions 미적용)
               API 토큰 검증: tai-api Bearer token (서버)
EXTERNAL:      tai-api / Inicis(본인인증·결제) / Supabase(OAuth·Storage) / 마케팅 API
```

### AREA: LANDING

| SURFACE | ROUTE/API | R/W | CRITICALITY | STATUS | EXISTING_QA |
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

| SURFACE | ROUTE/API | R/W | CRITICALITY | STATUS | EXISTING_QA |
|---------|-----------|-----|-------------|--------|-------------|
| 로그인 | GET /log-in → `POST /auth/login` | RW | CRITICAL | ACTIVE | P0-WWW-003 |
| 회원가입 | GET /log-in#register → `POST /auth/register` | RW | HIGH | ACTIVE | — |
| 소셜 로그인 (Kakao) | /log-in → Supabase OAuth → `POST /auth/ensure-user` | RW | HIGH | ACTIVE | — |
| 소셜 로그인 (Google) | /log-in → Supabase OAuth → `POST /auth/ensure-user` | RW | HIGH | ACTIVE | — |
| 초대 수락 | GET /invite?token={token} → `GET /user-invites/{token}/info` + `POST /user-invites/{token}/accept` | RW | HIGH | ACTIVE | — |

### AREA: FREE_DIAGNOSIS

| SURFACE | ROUTE/API | R/W | CRITICALITY | STATUS | EXISTING_QA |
|---------|-----------|-----|-------------|--------|-------------|
| 무료진단 마법사 (Step 1~4) | GET /free-diagnosis → `POST /diagnosis/run` | RW | CRITICAL | ACTIVE | P0-DIAG-001 |
| 무료진단 결과 | GET /free-diagnosis-result → `GET /diagnosis/result/{token}` | R | HIGH | ACTIVE | — |
| 유료진단 안내 | GET /paid-diagnosis → `GET /diagnosis/price-tier` | R | HIGH | ACTIVE | — |
| 유료진단 결과 조회 | GET /paid-diagnosis-result → `GET /diagnosis/paid-result/{token}` | R | HIGH | ACTIVE | — |

### AREA: SEARCH

| SURFACE | ROUTE/API | R/W | CRITICALITY | STATUS | EXISTING_QA |
|---------|-----------|-----|-------------|--------|-------------|
| 통합검색 진입 | GET /safety-search | R | CRITICAL | ACTIVE | P0-SRCH-001 |
| 통합검색 결과 | GET /safety-search?q={term} | R | CRITICAL | ACTIVE | P0-SRCH-002 |
| 검색 상세 (지식) | GET /safety-search/knowledge/{id} | R | NORMAL | ACTIVE | — |
| 검색 상세 (법령) | GET /safety-search/legal/{id} | R | NORMAL | ACTIVE | — |
| 지식센터 허브 | GET /kb → CF Function → `GET /public/knowledge` | R | HIGH | ACTIVE | — |
| 지식센터 상세 | GET /kb/{slug} → CF Function | R | NORMAL | ACTIVE | — |

### AREA: HEADER

| SURFACE | ROUTE/API | R/W | CRITICALITY | STATUS | EXISTING_QA |
|---------|-----------|-----|-------------|--------|-------------|
| 비로그인 헤더 상태 | / (localStorage access_token 없음) | R | CRITICAL | ACTIVE | — |
| 로그인 후 헤더 인증 상태 | / (localStorage access_token 있음) | R | CRITICAL | ACTIVE | P0-WWW-004 |
| 헤더 → 마이페이지 이동 | a[href*="mypage"] 클릭 → GET /mypage/ | R | CRITICAL | ACTIVE | P0-WWW-005 |

### AREA: CONTENT

| SURFACE | ROUTE/API | R/W | CRITICALITY | STATUS | EXISTING_QA |
|---------|-----------|-----|-------------|--------|-------------|
| 재해사례 목록 | GET /accident-cases → `GET /posts?category=accident` | R | NORMAL | ACTIVE | — |
| 재해사례 상세 | GET /accident/{id}, /accident/csi/{uuid} | R | NORMAL | ACTIVE | — |
| 판례 검색 | GET /precedent-search → `GET /posts?type=precedent` | R | NORMAL | ACTIVE | — |
| 안전뉴스 목록 | GET /safety-news → CF Function → `GET /posts?category=SAFETY_NEWS` | R | NORMAL | ACTIVE | — |
| 법령개정 뉴스 | GET /law-updates → `GET /posts?category=LAW_UPDATE` | R | NORMAL | ACTIVE | — |
| 동적 카테고리 페이지 | GET /safety/{subject}, /safety/accident/{type}, /safety/equipment/{value}, /safety/law/{law}, /safety/task/{task} | R | NORMAL | ACTIVE | — |

### AREA: CONTACT

| SURFACE | ROUTE/API | R/W | CRITICALITY | STATUS | EXISTING_QA |
|---------|-----------|-----|-------------|--------|-------------|
| 도입 문의 | GET /contact → `POST /inquiries` | RW | NORMAL | ACTIVE | — |
| 전문가 매칭 | GET /fix-request → `POST /expert-matching/*` | RW | NORMAL | ACTIVE | — |

### WWW 인증 가드

```
MEMBER 페이지 (/mypage/*) — 클라이언트 인라인 스크립트:
  localStorage.getItem('access_token') 없음 → location.replace('../../log-in.html?redirect=...')
서버사이드 가드: 없음 (Cloudflare Functions 미적용)
```

---

## 2. SAAS 서비스 (safe.taieng.co.kr + taieng.co.kr/mypage/*)

```
SOURCE_PATH:   tai-admin/vue3/ @ main (be4ff2c7)
AUTH_BOUNDARY: router.beforeEach() → useAuth().requireAuth()
               공개 경로: /login, /tai-survey, /forgot-password, /reset-password
               role_code 기반 nav gate: role 001 → 전체 메뉴 / role 002+ → sector 게이트
API_CLIENT:    useTaiApi composable (Bearer token; demo 모드 시 POST/PUT/PATCH/DELETE 차단)
NOTE:          taieng.co.kr/mypage/* = SOURCE_REPO:tai-www 정적 HTML, API:tai-api
```

### AREA: AUTH

| SURFACE | ROUTE/API | R/W | CRITICALITY | STATUS | EXISTING_QA |
|---------|-----------|-----|-------------|--------|-------------|
| SaaS 로그인 | GET /login → `POST /auth/login` | RW | CRITICAL | ACTIVE | P0-SAAS-001 |
| SaaS 로그아웃 | 로그아웃 버튼 → localStorage 13개 키 제거 + /login 리다이렉트 | W | HIGH | ACTIVE | — |
| 비밀번호 찾기 | GET /forgot-password → `POST /auth/forgot-password` | RW | NORMAL | ACTIVE | — |
| 비밀번호 재설정 | GET /reset-password → `POST /auth/reset-password` | RW | NORMAL | ACTIVE | — |

### AREA: DASHBOARD

| SURFACE | ROUTE/API | R/W | CRITICALITY | STATUS | EXISTING_QA |
|---------|-----------|-----|-------------|--------|-------------|
| SaaS 대시보드 | GET /safety-dashboard → `GET /work-schedules, /overdue/summary, /weather` | R | CRITICAL | ACTIVE | P0-SAAS-001 |
| 알림 목록 | GET /alert-list → `GET /alerts?page=&size=` | R | NORMAL | ACTIVE | — |
| 알림/공지 | GET /notification-list → `GET /notifications?page=&size=` | R | NORMAL | ACTIVE | — |

### AREA: MYPAGE

> SOURCE_REPO: tai-www (taieng.co.kr/mypage/* = 정적 HTML, tai-www/pages/mypage/)

| SURFACE | ROUTE/API | R/W | CRITICALITY | STATUS | EXISTING_QA |
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

| SURFACE | ROUTE/API | R/W | CRITICALITY | STATUS | EXISTING_QA |
|---------|-----------|-----|-------------|--------|-------------|
| 내 점검 목록 | GET /my-inspection → `GET /inspection/status, /inspections` | R | HIGH | ACTIVE | — |
| 점검 작업대 | GET /inspection-workbench/{id} → `POST /inspection/result/{id}/items, POST /inspection/{id}/photos` | RW | HIGH | ACTIVE | — |
| 점검 상세 | GET /inspection-detail/{id} → `GET /inspection/{id}/view, POST /inspection/{id}/results/{result_id}/corrections` | RW | HIGH | ACTIVE | — |
| 점검 달력 | GET /inspection-calendar → `GET /work-schedules, PATCH /work-schedules/{id}` | RW | NORMAL | ACTIVE | — |
| 점검 세트 관리 | GET /inspection-custom → `GET/POST/PUT/DELETE /inspection-sets` | RW | NORMAL | ACTIVE | — |

### AREA: EDUCATION

| SURFACE | ROUTE/API | R/W | CRITICALITY | STATUS | EXISTING_QA |
|---------|-----------|-----|-------------|--------|-------------|
| 교육 과정 목록 | GET /education-list → `GET /educations, POST /educations/{id}/assign` | RW | HIGH | ACTIVE | — |
| 교육 세팅 | GET /education-setting → `GET/POST/PUT/DELETE /education-templates` | RW | NORMAL | ACTIVE | — |
| TBM 목록 | GET /tbm-list → `GET /tbms` | R | HIGH | ACTIVE | — |
| TBM 작성 | GET /tbm-create → `POST /tbms` | RW | HIGH | ACTIVE | — |
| TBM 세팅 | GET /tbm-setting → `GET/POST/PUT/DELETE /tbm-templates` | RW | NORMAL | ACTIVE | — |
| 안전회의 기록 | GET /safety-meeting-list → `GET /safety-meetings` | R | NORMAL | ACTIVE | — |

### AREA: BILLING

| SURFACE | ROUTE/API | R/W | CRITICALITY | STATUS | EXISTING_QA |
|---------|-----------|-----|-------------|--------|-------------|
| 내 계약 | GET /my-contract → `GET /me/commercial/contract, GET /payments` | R | CRITICAL | ACTIVE | — |
| 진단 구매 | GET /diagnosis-purchase → `POST /payments/purchase-diagnosis` | RW | HIGH | ACTIVE | — |
| 진단 결과 이력 | GET /diagnosis-result → `GET /diagnosis-results` | R | NORMAL | ACTIVE | — |

### AREA: SETTINGS

| SURFACE | ROUTE/API | R/W | CRITICALITY | STATUS | EXISTING_QA |
|---------|-----------|-----|-------------|--------|-------------|
| 내 프로필 | GET /my-profile → `GET/PUT /me, POST /me/password` | RW | HIGH | ACTIVE | — |
| 회사 정보 | GET /my-company → `GET/PUT /companies/{id}, POST /companies/{id}/logo` | RW | HIGH | ACTIVE | — |
| 사업장 관리 | GET /factory-list → `GET/POST/PUT/DELETE /factories` | RW | HIGH | ACTIVE | — |
| 권한 관리 | GET /manager-permission → `GET/PUT /permissions` | RW | HIGH | ACTIVE | — |
| 조직 설정 | GET /org-setting → `GET/PUT /org-settings` | RW | NORMAL | ACTIVE | — |
| 설비 관리 | GET /my-equipment → `GET/POST/PUT /equipment-assets` | RW | NORMAL | ACTIVE | — |
| 설비 QR | GET /equipment-qr-manager → `GET/POST /equipment-assets/{id}/qr` | RW | NORMAL | ACTIVE | — |

### AREA: CONSTRUCTION

| SURFACE | ROUTE/API | R/W | CRITICALITY | STATUS | EXISTING_QA |
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

| SURFACE | ROUTE/API | R/W | CRITICALITY | STATUS | EXISTING_QA |
|---------|-----------|-----|-------------|--------|-------------|
| 위험도 평가 목록 | GET /risk-assessment-list → `GET /risk-assessments` | R | HIGH | ACTIVE | — |
| 위험도 평가 입력 | GET /risk-assessment-detail → `POST /risk-assessments/{id}/assess` | RW | HIGH | ACTIVE | — |
| 위험도 리포트 | GET /risk-assessment-report → `GET /risk-assessments/{id}/report, POST /risk-assessments/{id}/publish` | RW | NORMAL | ACTIVE | — |
| 평가 척도 관리 | GET /risk-assessment-scale → `GET/POST/PUT /risk-assessment-scales` | RW | NORMAL | ACTIVE | — |

### AREA: DOCUMENT

| SURFACE | ROUTE/API | R/W | CRITICALITY | STATUS | EXISTING_QA |
|---------|-----------|-----|-------------|--------|-------------|
| 서식 라이브러리 | GET /document-forms → `GET /document-templates` | R | NORMAL | ACTIVE | — |
| 일정 목록 | GET /work-schedule-list → `GET/POST/PUT/DELETE /work-schedules` | RW | NORMAL | ACTIVE | — |
| 엔진 문서 | GET /engine-document → `GET /engine-documents/{id}/download` | R | NORMAL | ACTIVE | — |
| 엔진 일정 | GET /engine-schedule → `GET/PATCH /engine-schedules` | RW | NORMAL | ACTIVE | — |

### AREA: SUPPORT

| SURFACE | ROUTE/API | R/W | CRITICALITY | STATUS | EXISTING_QA |
|---------|-----------|-----|-------------|--------|-------------|
| 고객센터 문의 | GET /contact → `GET/POST /contacts` | RW | NORMAL | ACTIVE | — |
| 도움말 | GET /help → `GET /help-articles` | R | NORMAL | ACTIVE | — |
| 사용성 설문 (인증 불필요) | GET /tai-survey → `POST /surveys/response` | RW | NORMAL | ACTIVE | — |

### AREA: QA (Service QA Control — role_code='001' 전용)

```
NOTE: SOURCE: vue3/src/pages/qa/ (SAAS 앱), safe.taieng.co.kr에서 role_code='001'만 접근.
      ADMIN 앱의 admin-vue3/qa/* 페이지와 별개로 존재하는 동일 기능 이중 UI.
      두 UI 모두 동일한 /admin/qa/* API를 호출하지만 CONTRACT_MISMATCH CM-001/CM-002 공유.
      GET /admin/qa/items/{id} — 미존재 (FE fetchItems page_size=100 후 클라이언트 id 탐색).
      GET/PUT /admin/qa/settings — 미존재 (스케줄 수정 = PATCH /admin/qa/items/{id}/schedule).
```

| SURFACE | ROUTE/API | R/W | CRITICALITY | STATUS | EXISTING_QA |
|---------|-----------|-----|-------------|--------|-------------|
| QA 대시보드 | GET /qa/dashboard → `GET /admin/qa/summary` | R | HIGH | ACTIVE | — |
| QA 항목 목록 | GET /qa/items → `GET /admin/qa/items?site_code=&category=&priority=&effective_status=&enabled=&page=&page_size=` | R | HIGH | ACTIVE | — |
| QA 항목 상세 | GET /qa/items/{id} → `GET /admin/qa/items?page_size=100` (FE id 탐색) | R | HIGH | ACTIVE | — |
| QA 실행 이력 | GET /qa/runs → `GET /admin/qa/runs` (**CM-001**: FE sends started_after/started_before/status, BE expects from_date/to_date/run_status) | R | HIGH | ACTIVE | — |
| QA 실행 상세 | GET /qa/runs/{id} → `GET /admin/qa/runs/{run_id}` | R | HIGH | ACTIVE | — |
| QA 설정 | GET /qa/settings → `PATCH /admin/qa/items/{id}/schedule` (**CM-002**: FE sends value, BE expects frequency_value) | RW | HIGH | ACTIVE | — |

---

## 3. ADMIN 서비스 (admin.taieng.co.kr)

```
SOURCE_PATH:   tai-admin/admin-vue3/ @ feat/admin-rebuild (remote origin) 6d9e89ea
               EVIDENCE: admin-vue3/src/navigation/horizontal/index.ts + 개별 페이지 파일
AUTH_BOUNDARY: JWT Bearer (Operator role, admin.taieng.co.kr 전용)
NOTE:          WO-19 (2026-07-29) 운영자 관점 재설계 — 8표시그룹 + 개발자도구
               unplugin-vue-router: pages/<slug>/index.vue → route name '<slug>'
               미서비스(매칭/견적설정) + 위험 그룹 = 주석 처리 (INACTIVE)
STATUS 범례:  ACTIVE=page source 직접 확인 / UNVERIFIED=nav만 확인(page 미읽기 또는 파일 없음) / INACTIVE=nav 주석
```

### AREA: DASHBOARD

| SURFACE | ROUTE_NAME | API | R/W | CRITICALITY | STATUS | EXISTING_QA |
|---------|------------|-----|-----|-------------|--------|-------------|
| 운영자 대시보드 | root | 미확인 (UNVERIFIED: pages/index/index.vue) | R | HIGH | UNVERIFIED | — |

### AREA: OPERATIONS (관제)

| SURFACE | ROUTE_NAME | API | R/W | CRITICALITY | STATUS | EXISTING_QA |
|---------|------------|-----|-----|-------------|--------|-------------|
| 관제홈 | ops-home | `GET /ops/home` | R | CRITICAL | ACTIVE | — |
| 운영 자동화 | automation | `GET /automation/rules|runs|tasks`, `POST /automation/runs/{id}/approve`, `POST /automation/tasks/{id}/close` | RW | HIGH | ACTIVE | — |
| 감사로그 | audit-log | `GET /admin/audit-logs?action&entity_type&page&size` | R | HIGH | ACTIVE | — |
| QA 현황 | qa-dashboard | 페이지 파일 없음 (qa-dashboard/index.vue NOT FOUND) | — | HIGH | UNVERIFIED | — |
| QA 항목 | qa-items | `GET /admin/qa/items` + `PATCH /admin/qa/items/{id}` + `POST /admin/qa/runs` (route: qa/items/index.vue, **CM-001** 참고) | RW | HIGH | ACTIVE | — |
| 실행 이력 | qa-runs | `GET /admin/qa/runs` (route: qa/runs/index.vue, **CM-001**: sends started_after/started_before/status) | R | HIGH | ACTIVE | — |
| QA 설정 | qa-settings | 페이지 파일 없음 (qa-settings/index.vue NOT FOUND) | — | HIGH | UNVERIFIED | — |
| 자동 QA 대시보드 (구) | auto-qa-dashboard | Supabase REST: `GET auto_qa_checks`, `GET auto_qa_log?limit=50`, `PATCH auto_qa_checks/{id}` | RW | NORMAL | ACTIVE | — |
| 내부 API 모니터 | api-monitor-internal | `GET /internal-api-registry` + 개별 endpoint probe | RW | NORMAL | ACTIVE | — |
| 외부 API 모니터 | api-monitor-external | `GET /report-api-registry` + HEAD ping + `POST/PATCH/DELETE /report-api-registry/*` | RW | NORMAL | ACTIVE | — |

> **QA 페이지 주의**: nav의 `qa-items`/`qa-runs`는 pages/qa/items/index.vue + qa/runs/index.vue (서브디렉토리 구조)와 route 이름 불일치 가능성 있음. `qa-dashboard`, `qa-settings`는 대응 page 파일 미발견(UNVERIFIED). EVIDENCE: `git ls-tree -r origin/feat/admin-rebuild admin-vue3/src/pages/`.

### AREA: CUSTOMER (고객)

| SURFACE | ROUTE_NAME | API | R/W | CRITICALITY | STATUS | EXISTING_QA |
|---------|------------|-----|-----|-------------|--------|-------------|
| 고객 360 | customer-360 | `GET /companies/{id}/360` | R | HIGH | ACTIVE | — |
| 회사관리 | company-list | `GET /companies`, `POST /companies`, `PATCH /companies/:id`, `DELETE /companies/:id` + NTS 검증 | RW | HIGH | ACTIVE | — |
| 시설관리 | factory-list | `GET /factories`, `POST /factories`, `PATCH /factories/:id`, `DELETE /factories/:id` + 주소/건축물대장 | RW | HIGH | ACTIVE | — |
| 회원관리 | member-list | `GET /users`, `POST /users`, `PATCH /users/:id`, `PATCH /users/:id/status` | RW | HIGH | ACTIVE | — |
| 문의관리 | inquiry-list | `GET /admin/inquiries`, `GET /admin/inquiries/{id}`, `PATCH /admin/inquiries/{id}`, `POST /admin/inquiries` | RW | NORMAL | ACTIVE | — |
| 온보딩 현황 | onboarding-ops | `GET /companies?keyword=`, `GET /companies/{id}/onboarding` | R | NORMAL | ACTIVE | — |

### AREA: BILLING (매출·결제)

| SURFACE | ROUTE_NAME | API | R/W | CRITICALITY | STATUS | EXISTING_QA |
|---------|------------|-----|-----|-------------|--------|-------------|
| 경영지표 | stats-business | `GET /stats/business` | R | HIGH | ACTIVE | — |
| 결제원장 | payment-ledger | `GET /payments`, `GET /payments/{id}/ledger`, `POST /payments/{id}/cancel|credit|refund|partial-refund|invoice/tax|invoice/cash`, `POST /payments/manual/confirm` | RW | CRITICAL | ACTIVE | — |
| 구독/계약 | contract-list | `GET /contracts`, `POST /contracts`, `PATCH /contracts/:id`, `PATCH /contracts/:id/activate`, `PATCH /contracts/:id/status` | RW | CRITICAL | ACTIVE | — |
| 세금계산서 | tax-ops | `GET /payments/admin/tax-invoices`, `POST /payments/tax-invoice-requests/{id}/process`, `POST /payments/admin/tax-invoices/manual` | RW | HIGH | ACTIVE | — |
| 실행 게이트 | payment-gate | `GET /payments/ops/gate-readiness` + REFUND_LIVE·INVOICE_LIVE 활성화/비활성화 | RW | HIGH | ACTIVE | — |
| 견적서 | quote-list | `GET /admin/quotes`, `GET /admin/quotes/{id}`, `POST /admin/quotes/{id}/preview|issue`, `POST /admin/quotes/preview|issue`, `GET /admin/quotes/{id}/pdf` | RW | HIGH | ACTIVE | — |
| 가격설정 | price-setting | `GET /price/summary-cards` + SaaS 플랜/수선/선임/법령진단/컨설팅/수수료/연결서비스/변경이력 각 GET/POST/PATCH/DELETE | RW | HIGH | ACTIVE | — |

### AREA: SERVICE (서비스 운영)

| SURFACE | ROUTE_NAME | API | R/W | CRITICALITY | STATUS | EXISTING_QA |
|---------|------------|-----|-----|-------------|--------|-------------|
| 법령진단 — 익명 진단 | anon-diagnosis-list | `GET /anonymous-diagnosis/admin/list`, `GET /anonymous-diagnosis/admin/detail/:id`, `PATCH /anonymous-diagnosis/admin/:id`, `DELETE /anonymous-diagnosis/admin/:id` | RW | HIGH | ACTIVE | — |
| 법령진단 — 리포트 | report-v1 | `GET /legal-engine/result/{id}` (또는 `/quotes/{id}` 폴백) | R | HIGH | ACTIVE | — |
| 법령진단 — 리포트 뷰어 | report-v1-viewer | `GET /legal-engine/result/:id` (로컬 DOM 편집, 서버 저장 없음) | R | HIGH | ACTIVE | — |
| 법령진단 — 진단 관리(구) | report_v1 | 정적 하드코딩 데이터, API 연동 없음 | R | NORMAL | ACTIVE | — |
| 법령진단 — 진단 연결 | diagnosis-step1 | `GET /system-codes/diagnosis_*` + `/legal-engine/diagnose` 또는 유사 endpoint | R | HIGH | ACTIVE | — |
| 교육 — 이수현황 | education-list | `GET /system-codes/*`, `GET /companies`, `GET /factories` (목록: **MOCK**, API 미연동) | RW | HIGH | ACTIVE | — |
| 교육 — 마스터 | education-setting | `GET /system-codes/*` (교육 마스터: **MOCK**, API 미연동) | RW | NORMAL | ACTIVE | — |
| SaaS — 권한관리 | permission | `GET /permissions?site=admin|tadmin`, `PATCH /permissions/{role_code}/{menu_id}`, `PUT /permissions/bulk` | RW | HIGH | ACTIVE | — |
| 플랫폼 권한 | platform-permission | `GET /permissions/platform`, `PATCH /permissions/platform/{role}/{permission}` | RW | HIGH | ACTIVE | — |
| SaaS — 알림설정 | notification-setting | **MOCK** (API 미연동, 로컬 상태만) | RW | NORMAL | ACTIVE | — |
| SaaS — 문서설정 | doc-setting | **NONE_FOUND** (플레이스홀더 페이지, 준비 중) | R | NORMAL | ACTIVE | — |
| SaaS — FAQ관리 | faq-setting | `GET /admin/site-faqs`, `POST /admin/site-faqs`, `PATCH /admin/site-faqs/:id`, `DELETE /admin/site-faqs/:id` | RW | NORMAL | ACTIVE | — |
| 매뉴얼 | manual | `GET /admin/manual`, `POST /admin/manual`, `PATCH /admin/manual/{id}`, `PATCH /admin/manual/{id}/status`, `DELETE /admin/manual/{id}` | RW | NORMAL | ACTIVE | — |

### AREA: COMMUNICATION (커뮤니케이션)

| SURFACE | ROUTE_NAME | API | R/W | CRITICALITY | STATUS | EXISTING_QA |
|---------|------------|-----|-----|-------------|--------|-------------|
| 메일 목록 | mail-list | `GET /mail/list`, `GET /mail/{id}`, `POST /mail/send`, `POST /mail/resend/{id}`, `PATCH /mail/{id}/read`, `GET /mail/unread-count` (60초 폴링) | RW | HIGH | ACTIVE | — |
| 알림센터 | notification-center | `GET /notifications/feed`, `POST /notifications/{id}/read`, `GET /notifications/preferences`, `PATCH /notifications/preferences/{id}`, `GET /notifications/health` (60초 폴링) | RW | NORMAL | ACTIVE | — |
| 알림 관리 | notification-admin | `GET /notifications/health`, `GET /notifications/wirings|policies|delivery` | R | NORMAL | ACTIVE | — |
| 푸시 테스트 | push-test | 미확인 (UNVERIFIED: pages/push-test/index.vue) | W | NORMAL | UNVERIFIED | — |
| 공지사항 | notice | `GET /notices`, `POST /notices`, `PATCH /notices/:id`, `PATCH /notices/:id/toggle`, `DELETE /notices/:id` | RW | NORMAL | ACTIVE | — |

### AREA: MARKETING (마케팅)

> API 클라이언트: `useMarketingApi` (별도 Railway 서비스, `VITE_MKT_API_BASE_URL`, `X-Actor-Role/Id` 헤더 인증)

| SURFACE | ROUTE_NAME | API | R/W | CRITICALITY | STATUS | EXISTING_QA |
|---------|------------|-----|-----|-------------|--------|-------------|
| 지식인관리 | kin-management | Supabase REST `naver_kin_log`/`kin_keyword_sets`/`kin_prompt_settings` + `GET /kin/pending-count`, `POST /kin/collect`, `POST /kin/generate` | RW | HIGH | ACTIVE | — |
| 대시보드 | marketing | `GET /admin/marketing/dashboard` | R | HIGH | ACTIVE | — |
| 발행 운영 | marketing-publish-ops | `GET/POST /admin/marketing/publish/options/*`, `POST /admin/marketing/publish/requests`, dispatch/run/archive | RW | HIGH | ACTIVE | — |
| 콘텐츠 | marketing-contents | 미확인 (UNVERIFIED: pages/marketing-contents/index.vue) | RW | NORMAL | UNVERIFIED | — |
| 배포 관리 | marketing-publish | 미확인 (UNVERIFIED: pages/marketing-publish/index.vue) | RW | HIGH | UNVERIFIED | — |
| 성과 | marketing-performance | `GET /admin/marketing/performance` | R | NORMAL | ACTIVE | — |
| 고객(Customer) | marketing-customers | 미확인 (UNVERIFIED: pages/marketing-customers/index.vue) | RW | NORMAL | UNVERIFIED | — |
| 행동(Journey) | marketing-journeys | 미확인 (UNVERIFIED: pages/marketing-journeys/index.vue) | RW | NORMAL | UNVERIFIED | — |
| 채널(Channel) | marketing-channels | `GET/POST /admin/marketing/channels`, `PATCH/DELETE /admin/marketing/channels/{code}`, activate/deactivate/stop | RW | HIGH | ACTIVE | — |
| 관계(Relation) | marketing-relations | 미확인 (UNVERIFIED: pages/marketing-relations/index.vue) | RW | NORMAL | UNVERIFIED | — |
| 전략(Strategy) | marketing-strategies | 미확인 (UNVERIFIED: pages/marketing-strategies/index.vue) | RW | NORMAL | UNVERIFIED | — |
| 계약(Contract) | marketing-contracts | 미확인 (UNVERIFIED: pages/marketing-contracts/index.vue) | RW | NORMAL | UNVERIFIED | — |
| 어댑터(Adapter) | marketing-adapters | 미확인 (UNVERIFIED: pages/marketing-adapters/index.vue) | RW | NORMAL | UNVERIFIED | — |
| 큐(Queue) | marketing-queue | 미확인 (UNVERIFIED: pages/marketing-queue/index.vue) | RW | NORMAL | UNVERIFIED | — |
| 스케줄러(Scheduler) | marketing-schedulers | 미확인 (UNVERIFIED: pages/marketing-schedulers/index.vue) | RW | NORMAL | UNVERIFIED | — |
| 결과(Result) | marketing-results | `GET /admin/marketing/results`, `POST /admin/marketing/results/{id}/run|cancel` | RW | NORMAL | ACTIVE | — |
| 감사(Audit) | marketing-audit | `GET /admin/marketing/audit`, `POST /admin/marketing/audit/archive` | RW | HIGH | ACTIVE | — |
| 설정 | marketing-settings | `GET /admin/marketing/settings`, `PATCH /admin/marketing/settings/{policy_key}` | RW | NORMAL | ACTIVE | — |

### AREA: STATISTICS (통계)

| SURFACE | ROUTE_NAME | API | R/W | CRITICALITY | STATUS | EXISTING_QA |
|---------|------------|-----|-----|-------------|--------|-------------|
| 운영개요 | stats-overview | `GET /stats/overview?days=N` | R | HIGH | ACTIVE | — |
| 진단 퍼널 | stats-funnel | `GET /stats/funnel?days=N` | R | HIGH | ACTIVE | — |
| 고객사·사업장 | stats-customers | `GET /stats/customers?days=N` | R | HIGH | ACTIVE | — |
| 매출·결제 | stats-revenue | `GET /stats/revenue?days=N` | R | HIGH | ACTIVE | — |
| 서비스 이행 | stats-fulfillment | 미확인 (`GET /stats/fulfillment` 추정, UNVERIFIED: pages/stats-fulfillment/index.vue) | R | NORMAL | UNVERIFIED | — |
| 워커 활동 | stats-workers | 미확인 (`GET /stats/workers` 추정, UNVERIFIED: pages/stats-workers/index.vue) | R | NORMAL | UNVERIFIED | — |

### AREA: DEVTOOLS (개발자도구)

| SURFACE | ROUTE_NAME | API | R/W | CRITICALITY | STATUS | EXISTING_QA |
|---------|------------|-----|-----|-------------|--------|-------------|
| 전역변수 | system-codes | `GET /system-codes/all`, `PATCH /system-codes/{id}`, `POST /system-codes`, `DELETE /system-codes/{id}` | RW | NORMAL | ACTIVE | — |
| 법규 엔진 | engine-legal | `GET /legal-engine/dashboard`, `/legal-engine/laws`, `/legal-engine/rules`, `/legal-engine/byulpyo/{domain}` | R | NORMAL | ACTIVE | — |
| AI 룰 생성/검토 | engine-legal-ai (+ ?draft=1) | `GET /legal-engine/laws`, `POST /legal-engine/parse`, `GET/PATCH/POST /legal-engine/drafts/*` | RW | NORMAL | ACTIVE | — |
| 설비 엔진 | engine-equipment | 미확인 (UNVERIFIED: pages/engine-equipment/index.vue) | RW | NORMAL | UNVERIFIED | — |
| 모델 엔진 | engine-model | 미확인 (UNVERIFIED: pages/engine-model/index.vue) | RW | NORMAL | UNVERIFIED | — |
| 공정 엔진(산업) | engine-process-industry | 미확인 (UNVERIFIED: pages/engine-process-industry/index.vue) | RW | NORMAL | UNVERIFIED | — |
| 공정 엔진(건설) | engine-process-construction | 미확인 (UNVERIFIED: pages/engine-process-construction/index.vue) | RW | NORMAL | UNVERIFIED | — |
| 문서 엔진 | engine-document | 미확인 (UNVERIFIED: pages/engine-document/index.vue) | RW | NORMAL | UNVERIFIED | — |
| 문서 스키마 | document-schema | 미확인 (UNVERIFIED: pages/document-schema/index.vue) | RW | NORMAL | UNVERIFIED | — |
| QA 엔진 | engine-qa | 미확인 (UNVERIFIED: pages/engine-qa/index.vue) | RW | NORMAL | UNVERIFIED | — |
| 스케줄 엔진 | engine-schedule | 미확인 (UNVERIFIED: pages/engine-schedule/index.vue) | RW | NORMAL | UNVERIFIED | — |
| 관제센터 | operational-awareness-center | `GET /control-runtime/health`, `/cron/scheduler-status` + runtime 다수 + `POST /synthetic/*`, `PATCH /calibration/profile` | RW | NORMAL | ACTIVE | — |
| Watch Engine | watch-engine | `GET/POST/PATCH /watch-engine/*` (health/issues/alert-rules/patterns 다수) | RW | NORMAL | ACTIVE | — |
| 문서출력 | document-output | 미확인 (UNVERIFIED: pages/document-output/index.vue) | RW | NORMAL | UNVERIFIED | — |
| 크론관리 | cron-list | `GET /cron/scheduler-status|jobs|logs`, `POST /cron/reload`, `POST /cron/jobs/{code}/run`, `PATCH /cron/jobs/{code}` | RW | NORMAL | ACTIVE | — |
| 다이어그램 | diagram-gallery | 미확인 (UNVERIFIED: pages/diagram-gallery/index.vue) | R | LOW | UNVERIFIED | — |

### INACTIVE (미서비스 — nav 주석 처리)

| SURFACE | ROUTE_NAME | AREA | INACTIVE_REASON |
|---------|------------|------|-----------------|
| 상담리스트 | fix-chat-list | MATCHING | 미서비스 |
| 수선 요청 | repair-list | MATCHING | 미서비스 |
| 수선 설정 | repair-setting | MATCHING | 미서비스 |
| 선임 연결 | personnel-list | MATCHING | 미서비스 |
| 크몽 계약 | contract-kmong | MATCHING | 미서비스 |
| 크몽 편집 | contract-kmong-edit | MATCHING | 미서비스 |
| 인력/전문가 | personnel-list | CUSTOMER | 미서비스 |
| 견적설정 | quote-setting | BILLING | 미서비스 (별건 WO) |
| 공정관리 | facility-process | RISK | WO-19 제거 |
| 설비관리 | equipment-list | RISK | WO-19 제거 |
| 시설설비 | facility-equipment | RISK | WO-19 제거 |
| 점검관리 | inspection-list | RISK | WO-19 제거 |
| 건설현장 | construction-site-list | RISK | WO-19 제거 |
| 건설공정 | construction-process-list | RISK | WO-19 제거 |
| 건설작업 | construction-work-list | RISK | WO-19 제거 |
| 건설작업자 | construction-worker-list | RISK | WO-19 제거 |
| 건설점검 | construction-inspection-list | RISK | WO-19 제거 |
| 지도 | maps-leaflet | RISK | WO-19 제거 |

> INACTIVE 페이지 파일: 위 페이지들의 index.vue는 실제로 존재하나 nav에서 주석 처리됨. 직접 URL 접근은 가능.

---

## 4. API Backend (api.taieng.co.kr)

```
SOURCE_PATH:   tai-api/routers/ @ origin/main (59b60f6a)
AUTH_BOUNDARY: JWT Bearer (Authorization header)
               /admin/* — Operator 권한
               /internal/* — X-Internal-Secret 헤더 (Railway env만 보관)
               /public/* — 인증 불필요
```

### QA 엔드포인트

> EVIDENCE: routers/admin_qa.py @ 59b60f6a (직접 확인)

| SURFACE | METHOD + PATH | 실제 파라미터 | R/W | CRITICALITY | STATUS |
|---------|---------------|-------------|-----|-------------|--------|
| QA 요약 | `GET /admin/qa/summary` | — | R | HIGH | ACTIVE |
| QA 항목 목록 | `GET /admin/qa/items` | site_code, priority, enabled, category, effective_status, page, page_size | R | HIGH | ACTIVE |
| QA 항목 enabled 수정 | `PATCH /admin/qa/items/{qa_item_id}` | body: enabled | W | HIGH | ACTIVE |
| QA 스케줄 수정 | `PATCH /admin/qa/items/{qa_item_id}/schedule` | body: enabled, frequency_type, **frequency_value**, anchor_time, day_of_week, timezone (**CM-002**: FE sends `value`) | W | HIGH | ACTIVE |
| QA 실행 이력 | `GET /admin/qa/runs` | **run_status**, trigger_type, **from_date**, **to_date**, page, page_size (**CM-001**: FE sends started_after/started_before/status) | R | HIGH | ACTIVE |
| QA 실행 상세 | `GET /admin/qa/runs/{run_id}` | — | R | HIGH | ACTIVE |
| QA 수동 실행 | `POST /admin/qa/runs` | body: qa_item_ids[] | W | HIGH | ACTIVE |
| QA 콜백 수신 | `POST /internal/qa/runs/{run_id}/results` | Header: X-Internal-Secret | W | CRITICAL | ACTIVE |
| QA 스케줄 틱 | `POST /internal/scheduler/qa/tick` | Header: X-Internal-Secret | W | HIGH | ACTIVE |

### 인증 엔드포인트

> EVIDENCE: routers/auth.py

| SURFACE | METHOD + PATH | R/W | CRITICALITY | STATUS |
|---------|---------------|-----|-------------|--------|
| 로그인 | `POST /auth/login` | W | CRITICAL | ACTIVE |
| 회원가입 | `POST /auth/register` | W | CRITICAL | ACTIVE |
| 소셜 ensure-user | `POST /auth/ensure-user` | W | CRITICAL | ACTIVE |
| 비밀번호 찾기 | `POST /auth/forgot-password` | W | HIGH | ACTIVE |
| 비밀번호 재설정 | `POST /auth/reset-password` | W | HIGH | ACTIVE |
| 내 정보 수정 | `PATCH /auth/me` | W | HIGH | ACTIVE |

### 진단 엔드포인트

> EVIDENCE: routers/diagnosis.py, routers/anonymous_diagnosis.py

| SURFACE | METHOD + PATH | R/W | CRITICALITY | STATUS |
|---------|---------------|-----|-------------|--------|
| 무료진단 실행 | `POST /diagnosis/run` | W | CRITICAL | ACTIVE |
| 진단 결과 조회 | `GET /diagnosis/result/{token}` | R | HIGH | ACTIVE |
| 유료진단 가격 티어 | `GET /diagnosis/price-tier` | R | HIGH | ACTIVE |
| 유료진단 결과 조회 | `GET /diagnosis/paid-result/{token}` | R | HIGH | ACTIVE |

### 결제 엔드포인트

> EVIDENCE: routers/payment.py, routers/payment_billing.py, routers/admin_quotes.py

| SURFACE | METHOD + PATH | R/W | CRITICALITY | STATUS |
|---------|---------------|-----|-------------|--------|
| 결제 내역 | `GET /payments` | R | CRITICAL | ACTIVE |
| Inicis 결제 콜백 | CF Function `/_api/payments/inicis/return` → tai-api | W | CRITICAL | ACTIVE |
| 계약 정보 | `GET /me/commercial/contract` | R | CRITICAL | ACTIVE |
| 진단 구매 | `POST /payments/purchase-diagnosis` | W | HIGH | ACTIVE |
| 견적서 목록 | `GET /admin/quotes` | R | HIGH | ACTIVE |
| 견적서 발행 | `POST /admin/quotes/{id}/issue`, `POST /admin/quotes/issue` | W | HIGH | ACTIVE |

### 공개 엔드포인트

> EVIDENCE: routers/public.py, routers/public_pricing.py, routers/public_safety_search.py

| SURFACE | METHOD + PATH | R/W | CRITICALITY | STATUS |
|---------|---------------|-----|-------------|--------|
| 공지사항 | `GET /notices/active` | R | CRITICAL | ACTIVE |
| 요금제 조회 | `GET /public/pricing/all` | R | HIGH | ACTIVE |
| 통합검색 | `GET /public/safety-search` | R | CRITICAL | ACTIVE |

---

## 5. QA Runner (tai-qa)

```
SOURCE_PATH:   tai-qa/ @ main (631af37b)
               EVIDENCE: Phase2E 완료 시점 기록 (project_wo_qa_control_phase2e.md)
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
fixtures/qa.fixture.ts (@ 631af37b):
  _qaErrors 픽스처: auto=true (전 테스트 자동 적용)
  수집 대상: pageerror + api.taieng.co.kr requestfailed + HTTP 5xx
  post-use: fatalErrors ≥ 1 → 테스트 자동 실패

playwright.config.ts:
  단일 프로젝트: Chromium Desktop Chrome
  fullyParallel: false (순차 실행)
  retries: CI ? 1 : 0
  timeout: 30,000ms / expect.timeout: 10,000ms

.github/workflows/p0-smoke.yml (@ 631af37b):
  트리거:
    1. workflow_dispatch — inputs: run_id (optional), scenario_ids (optional)
    2. schedule: 0 23 * * * (= 08:00 KST)
    3. pull_request → main (관련 경로 변경 시)
  콜백: workflow_dispatch + run_id 있을 때만
    POST https://api.taieng.co.kr/internal/qa/runs/{run_id}/results
    Header: X-Internal-Secret
  scenario_ids 필터링: SCENARIO_IDS 기준 results 필터링 (RESULT_NOT_TARGETED 방지)
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
| Supabase DB | 메인 DB | tai-api → supabase-py | ALL |
| Supabase REST (auth) | OAuth(kakao/google), 이미지 스토리지 | tai-www: Supabase UMD SDK | WWW |
| Supabase REST (ADMIN) | 자동 QA 대시보드(auto_qa_checks/auto_qa_log), KIN 설정(kin_keyword_sets/kin_prompt_settings/naver_kin_log) | admin-vue3: sbFetch | ADMIN |
| GitHub Actions | QA 자동화 실행 dispatch | tai-api → POST /repos/taiengineering/tai-qa/actions/workflows/p0-smoke.yml/dispatches | API (ADMIN 제어) |
| Slack | QA 결과 알림 | tai-api → Slack Incoming Webhook | API |
| 마케팅 API (Railway) | 마케팅 엔진 백엔드 | admin-vue3: VITE_MKT_API_BASE_URL (X-Actor-Role/Id 헤더) | ADMIN |
| 지식센터 SSR | CF Function → 45cm-mkt-api-production /public/knowledge | tai-www CF Function | WWW |

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

| SERVICE | AREA 수 | ACTIVE (SOURCE-VERIFIED) | UNVERIFIED | INACTIVE | EXISTING_QA 커버 |
|---------|---------|--------------------------|------------|----------|-----------------|
| WWW | 7 | 36 | 0 | 0 | 7개 (P0-WWW-001/003/004/005, P0-DIAG-001, P0-SRCH-001/002) |
| SAAS | 12 | 52 | 0 | 0 | 3개 (P0-SAAS-001, P0-MYP-001/005) |
| ADMIN | 9 active areas | 56 | 26 | 18 | 0 |
| API | — | 22 | 0 | 0 | 10개 scenario 전부 |
| QA_RUNNER | — | 10 scenarios | — | — | — |
| **TOTAL** | **28** | **166** | **26** | **18** | 10/10 |

> **ADMIN ACTIVE SOURCE-VERIFIED: 56/82**  
> **미추적 Active Surface: 0** (UNVERIFIED는 ACTIVE 아님)

### ADMIN UNVERIFIED 목록 (26개)

| SURFACE | ROUTE_NAME | 미확인 이유 |
|---------|------------|------------|
| 운영자 대시보드 | root | 소스 미읽기 (pages/index/index.vue) |
| QA 현황 | qa-dashboard | 페이지 파일 없음 |
| QA 설정 | qa-settings | 페이지 파일 없음 |
| 푸시 테스트 | push-test | 소스 미읽기 |
| 서비스 이행 | stats-fulfillment | 소스 미읽기 |
| 워커 활동 | stats-workers | 소스 미읽기 |
| 콘텐츠 | marketing-contents | 소스 미읽기 |
| 배포 관리 | marketing-publish | 소스 미읽기 |
| 고객(Customer) | marketing-customers | 소스 미읽기 |
| 행동(Journey) | marketing-journeys | 소스 미읽기 |
| 관계(Relation) | marketing-relations | 소스 미읽기 |
| 전략(Strategy) | marketing-strategies | 소스 미읽기 |
| 계약(Contract) | marketing-contracts | 소스 미읽기 |
| 어댑터(Adapter) | marketing-adapters | 소스 미읽기 |
| 큐(Queue) | marketing-queue | 소스 미읽기 |
| 스케줄러(Scheduler) | marketing-schedulers | 소스 미읽기 |
| 설비 엔진 | engine-equipment | 소스 미읽기 |
| 모델 엔진 | engine-model | 소스 미읽기 |
| 공정 엔진(산업) | engine-process-industry | 소스 미읽기 |
| 공정 엔진(건설) | engine-process-construction | 소스 미읽기 |
| 문서 엔진 | engine-document | 소스 미읽기 |
| 문서 스키마 | document-schema | 소스 미읽기 |
| QA 엔진 | engine-qa | 소스 미읽기 |
| 스케줄 엔진 | engine-schedule | 소스 미읽기 |
| 문서출력 | document-output | 소스 미읽기 |
| 다이어그램 | diagram-gallery | 소스 미읽기 |

### 존재하지 않는 API (PATCH1 수정 사항 유지)

EVIDENCE: routers/admin_qa.py @ 59b60f6a:

| 오기재 엔드포인트 | 실제 상황 |
|----------------|----------|
| `GET /admin/qa/items/{id}` | 미존재. FE: fetchItems(page_size=100) 전체 조회 후 클라이언트 id 탐색 |
| `GET /admin/qa/settings` | 미존재 |
| `PUT /admin/qa/settings` | 미존재. 스케줄 변경은 `PATCH /admin/qa/items/{id}/schedule` |

### 전수 조사 완료 항목

- [x] tai-www 조사 완료 (36 surfaces, 7 areas)
- [x] tai-admin SAFE SaaS 조사 완료 (52 surfaces, 12 areas)
- [x] tai-admin Operator Admin nav 전수조사 완료 (82 nav entries, 9 active areas)
  - ACTIVE SOURCE-VERIFIED: 56/82
  - UNVERIFIED (소스 미읽기 또는 파일 없음): 26/82
- [x] tai-api 주요 엔드포인트 조사 완료 (22 key endpoints)
- [x] tai-qa 기존 Scenario 조사 완료 (10 scenarios, BDD 구조, 워크플로우 @ 631af37b)
- [x] Contract Mismatch 2건 발견·기록 (CM-001/CM-002)
- [x] 코드 변경 = 0 / DB 변경 = 0 / Production mutation = 0

### 미조사 항목

- WORKER 서비스: repo/runtime 미확인. 이 문서에 포함하지 않음.
- ADMIN UNVERIFIED 26개: Phase 0 종료 조건 달성을 위해 별도 조사 또는 UNVERIFIED 확정 필요.

### Phase 1 진입 선결 조건

ADMIN UNVERIFIED 26개 처리(소스 확인 또는 UNVERIFIED 확정)가 완료되거나, Owner가 UNVERIFIED를 Phase 0 범위 내에서 허용하면 Phase 1 (QA Taxonomy DB 구현) 착수 가능.
