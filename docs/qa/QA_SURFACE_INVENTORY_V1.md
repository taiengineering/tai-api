---
title: QA Surface Inventory v1
version: 1.0.0
work_order: WO-QA-UNIVERSE-PHASE0-SURFACE-INVENTORY-001
status: COMPLETE
surveyed_at: 2026-10-02
---

# QA Surface Inventory v1

조사 완료: 2026-10-02  
추측 항목: 0 (소스 미확인 항목 포함 금지)  
코드 변경: 0 / DB 변경: 0 / Production mutation: 0

---

## 조사 범위

| Repo | 서비스 | 도메인 | 조사 완료 |
|------|--------|--------|-----------|
| tai-www | WWW | taieng.co.kr | ✓ |
| tai-admin (SAFE) | SAAS | safe.taieng.co.kr + taieng.co.kr/mypage/* | ✓ |
| tai-admin (Operator) | ADMIN | admin.taieng.co.kr | ✓ |
| tai-api | API Backend | api.taieng.co.kr | ✓ |
| tai-qa | QA Runner | github.com/taiengineering/tai-qa | ✓ |
| WORKER | — | 미확인 | 미조사 (추측 없음) |

> WORKER 서비스: 실제 repo/runtime 미확인. 이 문서에 포함하지 않음.

---

## 1. WWW 서비스 (taieng.co.kr)

소스: tai-www (Astro 정적 사이트 + Cloudflare Functions)  
인증 방식: localStorage access_token (client-side guard)  
외부 연동: tai-api, Inicis(본인인증/결제), Supabase(OAuth/Storage), 마케팅 API

### AREA: LANDING

| SURFACE | ROUTE/API | ACTION | CRITICALITY |
|---------|-----------|--------|-------------|
| 메인 랜딩페이지 | GET / | CTA 클릭(무료진단/서비스/요금제), 공지사항 조회 `GET /notices/active?channel=MARKETING` | P0 |
| 요금제 페이지 | GET /pricing → `GET /public/pricing/all` | 탭전환(SaaS/진단), 연간/월간 토글, 섹터 선택(건물/산업/건설) | P1 |
| 서비스 소개 (SaaS) | GET /service/saas | CTA 클릭 | P2 |
| 서비스 소개 (진단) | GET /service/diagnosis | CTA 클릭 | P2 |
| 타겟 랜딩 (업주) | GET /for-business-owner | CTA 클릭 | P2 |
| 타겟 랜딩 (안전관리자) | GET /for-safety-manager | CTA 클릭 | P2 |
| 회사 소개 | GET /about | 정보 조회 | P2 |
| FAQ | GET /faq | 항목 아코디언 토글 | P2 |
| 개인정보처리방침 | GET /privacy | 문서 조회 | P2 |
| 이용약관 | GET /terms | 문서 조회 | P2 |

### AREA: AUTH

| SURFACE | ROUTE/API | ACTION | CRITICALITY |
|---------|-----------|--------|-------------|
| 로그인 | GET /log-in → `POST /auth/login` | 이메일/폰+비밀번호 입력(#login-id, #login-pw, #btn-login), 비밀번호 표시 토글 | P0 |
| 회원가입 | GET /log-in#register → `POST /auth/register` | 이름, 휴대폰 입력 + 본인인증(Inicis), 이메일, 비밀번호 확인, 약관 동의 | P1 |
| 소셜 로그인 (Kakao) | /log-in → Supabase OAuth → `POST /auth/ensure-user` | loginSocial('kakao') 클릭 | P1 |
| 소셜 로그인 (Google) | /log-in → Supabase OAuth → `POST /auth/ensure-user` | loginSocial('google') 클릭 | P1 |
| 초대 수락 | GET /invite?token={token} → `GET /user-invites/{token}/info` + `POST /user-invites/{token}/accept` | 초대 토큰 유효성 확인, 본인인증(Inicis), 4필드(이름/폰/비밀번호/mtx_id) 입력, PENDING 상태로 가입 완료 | P1 |

### AREA: FREE_DIAGNOSIS

| SURFACE | ROUTE/API | ACTION | CRITICALITY |
|---------|-----------|--------|-------------|
| 무료진단 마법사 (Step 1~4) | GET /free-diagnosis → `POST /diagnosis/run` | 섹터 선택(BUILDING/INDUSTRY/CONSTRUCTION), 입력패널(시설/공정/장비/인원), 본인인증(Inicis 팝업), 결과 조회 | P0 |
| 무료진단 결과 | GET /free-diagnosis-result → `GET /diagnosis/result/{token}` | 결과 표시, PDF 다운로드, 유료 업그레이드 CTA | P1 |
| 유료진단 안내 | GET /paid-diagnosis → `GET /diagnosis/price-tier` | 섹터 선택, 요금 자동 계산, 회원 필수 안내 | P1 |
| 유료진단 결과 조회 | GET /paid-diagnosis-result → `GET /diagnosis/paid-result/{token}` | 웹 결과, PDF/Excel 다운로드 | P1 |

### AREA: SEARCH

| SURFACE | ROUTE/API | ACTION | CRITICALITY |
|---------|-----------|--------|-------------|
| 통합검색 진입 | GET /safety-search | URL 직접 접속 (q 파라미터 없음) | P0 |
| 통합검색 결과 | GET /safety-search?q={term} | 섹터 노출 순서 검증 (knowledge→guide→law→accident→material→chem→precedent→kosha), .ss-error 없음 | P0 |
| 검색 상세 (지식) | GET /safety-search/knowledge/{id} | 지식 상세 조회 | P2 |
| 검색 상세 (법령) | GET /safety-search/legal/{id} | 법령 상세 조회 | P2 |
| 지식센터 허브 | GET /kb → CF Function → `GET /public/knowledge` (마케팅 API, 캐시 max-age=300) | 콘텐츠 목록 조회, 검색/필터 | P1 |
| 지식센터 상세 | GET /kb/{slug} → CF Function | 슬러그 기반 상세 조회 | P2 |

### AREA: HEADER

| SURFACE | ROUTE/API | ACTION | CRITICALITY |
|---------|-----------|--------|-------------|
| 비로그인 헤더 상태 | / (localStorage access_token 없음) | 로그인 버튼 노출, 마이페이지 링크 미노출 | P0 |
| 로그인 후 헤더 인증 상태 | / (localStorage access_token 있음) | 마이페이지 링크 노출, 로그아웃 버튼 노출 | P0 |
| 헤더 → 마이페이지 이동 | a[href*="mypage"] 클릭 → GET /mypage/ | 마이페이지 대시보드 진입 | P0 |

### AREA: CONTENT

| SURFACE | ROUTE/API | ACTION | CRITICALITY |
|---------|-----------|--------|-------------|
| 재해사례 목록 | GET /accident-cases → `GET /posts?category=accident` | 검색 입력(ac-search-wrap), 탭 필터(ac-tab), 카드 클릭 | P2 |
| 재해사례 상세 | GET /accident/{id} + /accident/csi/{uuid} | 상세 조회 | P2 |
| 판례 검색 | GET /precedent-search → `GET /posts?type=precedent` | 검색, 필터, 카드 클릭 | P2 |
| 안전뉴스 목록 | GET /safety-news → `GET /posts?category=SAFETY_NEWS` (CF Function) | 목록 조회, 상세 링크 | P2 |
| 법령개정 뉴스 | GET /law-updates → `GET /posts?category=LAW_UPDATE` | 목록 조회 | P2 |
| 동적 카테고리 | GET /safety/{subject}, /safety/accident/{type}, /safety/equipment/{value}, /safety/law/{law}, /safety/task/{task} | 카테고리 필터링 → 세부 콘텐츠 조회 | P2 |

### AREA: CONTACT

| SURFACE | ROUTE/API | ACTION | CRITICALITY |
|---------|-----------|--------|-------------|
| 도입 문의 | GET /contact → `POST /inquiries` | 분야 선택(5개), 이름/이메일/회사/내용 입력, 첨부파일, Summernote 에디터 | P2 |
| 전문가 매칭 | GET /fix-request → `POST /expert-matching/*` | 챗봇 인터페이스, 증상 설명, 전문가 자동 매칭, 연락처 수집 | P2 |

### WWW 인증 가드 요약

```
MEMBER 페이지 (/mypage/*) — client-side inline script:
  localStorage.getItem('access_token') 없음
  → location.replace('../../log-in.html?redirect=...')

서버사이드 가드: 없음 (Cloudflare Functions 미적용)
API 토큰 검증: tai-api Bearer token (서버에서 수행)
```

### WWW 외부 연동

| 연동 | 용도 | 사용 경로 |
|------|------|----------|
| tai-api (api.taieng.co.kr) | 메인 백엔드 (인증/진단/결제/콘텐츠) | 전 페이지 |
| Cloudflare Functions (`/_api/*` 프록시) | tai-api 프록시, SSR 캐시(kb), 결제 콜백 | /kb, /safety-news, `/_api/payments/inicis/return` |
| Inicis (KG) | 본인인증(svc_code='01') + 결제 (V023) | /log-in#register, /free-diagnosis, /mypage/checkout, /invite |
| Supabase (UMD SDK + Storage) | OAuth(kakao/google), 이미지 asset | /log-in, 전 페이지 이미지 |
| 마케팅 API (45cm-mkt-api-production) | `/public/knowledge` SSR | /kb |

---

## 2. SaaS 서비스 (SAFE / safe.taieng.co.kr + taieng.co.kr/mypage/*)

소스: tai-admin/vue3/ (Vue 3, vue-router/auto)  
로그인 후 role_code 기반 분기: 기타 role → safe.taieng.co.kr / role 001 → admin.taieng.co.kr  
API 통신: useTaiApi composable (Bearer token, demo 모드 시 POST/PUT/PATCH/DELETE 차단)  
인증 가드: `router.beforeEach()` → `useAuth().requireAuth()` (공개 경로: /login, /tai-survey, /forgot-password, /reset-password)

### AREA: AUTH

| SURFACE | ROUTE/API | ACTION | CRITICALITY |
|---------|-----------|--------|-------------|
| SaaS 로그인 | GET safe.taieng.co.kr/login → `POST /auth/login` | input[type="email"]/input[type="password"], button[type="submit"] 클릭, waitForURL(!includes('/login')) | P0 |
| SaaS 로그아웃 | 로그아웃 버튼 → localStorage 13개 키 제거 + /login 리다이렉트 | doLogout() 호출 | P1 |
| 비밀번호 찾기 | GET /forgot-password → `POST /auth/forgot-password` | 이메일 입력 | P2 |
| 비밀번호 재설정 | GET /reset-password → `POST /auth/reset-password` | 신규 비밀번호 입력 (Supabase 복구 토큰 해시 보존) | P2 |

### AREA: DASHBOARD

| SURFACE | ROUTE/API | ACTION | CRITICALITY |
|---------|-----------|--------|-------------|
| SaaS 대시보드 | GET /safety-dashboard → `GET /work-schedules, /overdue/summary, /weather` | 사업장 선택(role=combobox Vuetify VSelect), 통계카드(D-0/D-3/이번달/미배정), 14일 차트, 할일 테이블, 날씨위젯 | P0 |
| 알림 목록 | GET /alert-list → `GET /alerts?page=&size=` | 목록 조회, 페이지네이션 | P2 |
| 알림/공지 | GET /notification-list → `GET /notifications?page=&size=` | 읽음/미읽음 상태, 페이지네이션 | P2 |

### AREA: MYPAGE

| SURFACE | ROUTE/API | ACTION | CRITICALITY |
|---------|-----------|--------|-------------|
| 마이페이지 대시보드 | GET taieng.co.kr/mypage/ | 요약통계(계약/진단/결제), `TaiMypageState.load()`, 사이드바 메뉴(taiMypageRenderNav) | P0 |
| 결제내역 | GET taieng.co.kr/mypage/payments/ → `GET /payments` | 결제 목록 테이블, 세금계산서 모달, 연장기간 선택 모달. 403("소속 회사 정보를 확인할 수 없습니다") = 정상 허용 | P0 |
| 계약 목록 | GET taieng.co.kr/mypage/contracts | 계약 상태 조회, 다운로드 | P1 |
| 프로필 수정 | GET taieng.co.kr/mypage/profile → `PATCH /auth/me` | 사용자정보 수정, 휴대폰 변경(인증), 비밀번호 변경 | P1 |
| 회사정보 | GET taieng.co.kr/mypage/company → `GET/POST /factories` | 팩토리 조회/등록 | P1 |
| 온보딩 | GET taieng.co.kr/mypage/onboarding | 신규 회원 초기 설정(회사정보/팩토리/플랜 선택) | P1 |
| 결제 | GET taieng.co.kr/mypage/checkout → Inicis V023 → `/_api/payments/inicis/return` | 견적 로드, 결제정보 입력, Inicis 결제창, 승인 콜백 | P1 |
| 파트너 대시보드 | GET taieng.co.kr/mypage/partner/ → `GET /contracts?role=PARTNER` | 견적/계약/요청 관리 (role=PARTNER 필요) | P2 |

### AREA: INSPECTION

| SURFACE | ROUTE/API | ACTION | CRITICALITY |
|---------|-----------|--------|-------------|
| 내 점검 목록 | GET /my-inspection → `GET /inspection/status, /inspections` | 상태별 필터(D-0/D+N/완료율), 점검 개시 | P1 |
| 점검 작업대 | GET /inspection-workbench/{id} → `POST /inspection/result/{id}/items`, `POST /inspection/{id}/photos` | 항목별 결과 입력(O/X/숫자/텍스트), 필수항목 검증, 사진 업로드(multi), draft/final 저장 | P1 |
| 점검 상세 | GET /inspection-detail/{id} → `GET /inspection/{id}/view`, `POST /inspection/{id}/results/{result_id}/corrections` | 결과 조회(read-only), 정정 입력 모달 | P1 |
| 점검 달력 | GET /inspection-calendar → `GET /work-schedules`, `PATCH /work-schedules/{id}` | 달력 조회, 드래그 일정 변경 | P2 |
| 점검 세트 관리 | GET /inspection-custom → `GET/POST/PUT/DELETE /inspection-sets` | 사용자 정의 세트 CRUD | P2 |

### AREA: EDUCATION

| SURFACE | ROUTE/API | ACTION | CRITICALITY |
|---------|-----------|--------|-------------|
| 교육 과정 목록 | GET /education-list → `GET /educations`, `POST /educations/{id}/assign` | 배정, 완료현황 조회 | P1 |
| 교육 세팅 | GET /education-setting → `GET/POST/PUT/DELETE /education-templates` | 과정 CRUD (회사관리자) | P2 |
| TBM 목록 | GET /tbm-list → `GET /tbms` | 상태 조회, 페이지네이션 | P1 |
| TBM 작성 | GET /tbm-create → `POST /tbms` | 주제/참석자/내용 입력, 템플릿 선택 | P1 |
| TBM 세팅 | GET /tbm-setting → `GET/POST/PUT/DELETE /tbm-templates` | 템플릿 CRUD | P2 |
| 안전회의 기록 | GET /safety-meeting-list → `GET /safety-meetings` | 목록, 참석자 확인 | P2 |

### AREA: BILLING

| SURFACE | ROUTE/API | ACTION | CRITICALITY |
|---------|-----------|--------|-------------|
| 내 계약 | GET /my-contract → `GET /me/commercial/contract`, `GET /payments` | 계약정보/서비스범위 조회, 결제이력, 갱신 신청, 세금계산서 발급 | P1 |
| 진단 구매 | GET /diagnosis-purchase → `POST /payments/purchase-diagnosis` | 결제 연동 | P1 |
| 진단 결과 이력 | GET /diagnosis-result → `GET /diagnosis-results` | 과거 진단 결과, 리포트 다운로드 | P2 |

### AREA: SETTINGS

| SURFACE | ROUTE/API | ACTION | CRITICALITY |
|---------|-----------|--------|-------------|
| 내 프로필 | GET /my-profile → `GET/PUT /me`, `POST /me/password` | 프로필 조회/수정, 비밀번호 변경 | P1 |
| 회사 정보 | GET /my-company → `GET/PUT /companies/{id}`, `POST /companies/{id}/logo` | 회사정보/로고/라이선스, 주소검색, KSIC 검색, 담당자 CRUD | P1 |
| 사업장 관리 | GET /factory-list → `GET/POST/PUT/DELETE /factories` | 목록/등록/수정/삭제, 주소검색+건축물대장, 섹터별 조건필드, 법령현황 | P1 |
| 권한 관리 | GET /manager-permission → `GET/PUT /permissions` | 사용자 역할 설정 (회사관리자 전용) | P1 |
| 조직 설정 | GET /org-setting → `GET/PUT /org-settings` | 계층 구조 관리 | P2 |
| 설비 관리 | GET /my-equipment → `GET/POST/PUT /equipment-assets` | CRUD, 장비 유형 추천 | P2 |
| 설비 QR | GET /equipment-qr-manager → `GET/POST /equipment-assets/{id}/qr` | QR 생성, 출력, 관리 | P2 |

### AREA: CONSTRUCTION

| SURFACE | ROUTE/API | ACTION | CRITICALITY |
|---------|-----------|--------|-------------|
| 공사장 목록 | GET /construction-site-list → `GET/POST/PUT/DELETE /construction-sites` | CRUD, 담당자 관리 | P1 |
| 건설 Step1 | GET /construction-step1 → `POST /construction/step1` | 기본정보 입력 | P1 |
| 공정 목록 | GET /construction-process-list → `GET/POST/PUT /construction-processes` | CRUD | P1 |
| 작업 목록 | GET /construction-work-list → `GET/POST/PUT /construction-works` | 작업자 배정 | P1 |
| 인력 명부 | GET /construction-worker-list → `GET/POST/PUT /construction-workers` | 인원 배치 | P1 |
| 협력업체 | GET /construction-subcontractor-list → `GET/POST/PUT /construction-subcontractors` | 협력사 관리 | P2 |
| 공사 점검 | GET /construction-inspection-list → `GET /construction-inspections` | 점검 목록/상태 | P1 |
| 공정 추출 | GET /construction-extraction → `POST /construction-extraction` | 자동 분석 | P2 |

### AREA: RISK

| SURFACE | ROUTE/API | ACTION | CRITICALITY |
|---------|-----------|--------|-------------|
| 위험도 평가 목록 | GET /risk-assessment-list → `GET /risk-assessments` | 진행/완료/미작성 상태 필터 | P1 |
| 위험도 평가 입력 | GET /risk-assessment-detail → `POST /risk-assessments/{id}/assess` | MATRIX 입력, 점수 자동 계산 | P1 |
| 위험도 리포트 | GET /risk-assessment-report → `GET /risk-assessments/{id}/report`, `POST /risk-assessments/{id}/publish` | 리포트 생성/다운로드 | P2 |
| 평가 척도 관리 | GET /risk-assessment-scale → `GET/POST/PUT /risk-assessment-scales` | 평가기준 CRUD | P2 |

### AREA: DOCUMENT

| SURFACE | ROUTE/API | ACTION | CRITICALITY |
|---------|-----------|--------|-------------|
| 서식 라이브러리 | GET /document-forms → `GET /document-templates` | 서식 조회/다운로드, 사용자 정의 생성 | P2 |
| 일정 목록 | GET /work-schedule-list → `GET/POST/PUT/DELETE /work-schedules` | 캘린더/리스트 뷰, 담당자 배정 | P2 |
| 엔진 문서 | GET /engine-document → `GET /engine-documents/{id}/download` | 자동생성 문서 조회/PDF 다운로드 | P2 |
| 엔진 일정 | GET /engine-schedule → `GET/PATCH /engine-schedules` | 자동 일정 조회/설정 | P2 |

### AREA: SUPPORT

| SURFACE | ROUTE/API | ACTION | CRITICALITY |
|---------|-----------|--------|-------------|
| 고객센터 문의 | GET /contact → `GET/POST /contacts` | 문의 등록, 목록 조회, 답변 확인 | P2 |
| 도움말 | GET /help → `GET /help-articles` | FAQ, 가이드 문서 | P2 |
| 사용성 설문 (PUBLIC) | GET /tai-survey → `POST /surveys/response` | 로그인 없이 응답 | P2 |

### SaaS 네비게이션 게이트

```
role_code 기반 nav 필터링 (navigation/gate.ts):
  role 001 (platform admin) → 전체 메뉴 노출
  role 002 + company_id 없음 → admin.taieng.co.kr (legacy 리다이렉트)
  role 002 + company_id 있음 → SAFE (회사관리자), sector 게이트 적용
  기타 role → sector 게이트 적용

sector 정규화: BUILDING→FACILITY, INDUSTRY→INDUSTRIAL, CONSTRUCTION=동일
sector 미확정 → 실패-오픈 (전체 노출)
```

---

## 3. Admin 서비스 (Operator Admin Console)

소스: tai-admin/vue3/ (동일 애플리케이션, role_code='001' 전용 라우트)  
도메인: admin.taieng.co.kr (role 001 로그인 시 자동 리다이렉트)  
API prefix: `/admin/qa/*` (외부), `/internal/qa/*` (내부 콜백)  
접근 제한: `sectors: ['__QA_ADMIN__']` nav gate → role 001만 노출

### AREA: QA

| SURFACE | ROUTE/API | ACTION | CRITICALITY |
|---------|-----------|--------|-------------|
| QA 대시보드 | GET admin.taieng.co.kr/qa/dashboard → `GET /admin/qa/summary` | 현황 카드(전체/활성/PASS/FAIL/FLAKY/BLOCKED/SKIPPED/NEVER_RUN), 사이트별(WWW/SAFE/ADMIN) 결과, last_run_at/next_run_at | P0 |
| QA 항목 목록 | GET /qa/items → `GET /admin/qa/items?site_code=&category=&priority=&effective_status=&enabled=&page=&page_size=` | 필터(6종), 페이지네이션, 활성화 토글(PATCH), 스케줄 수정(모달), 수동 실행(POST) | P0 |
| QA 항목 상세 | GET /qa/items/{id} → `GET /admin/qa/items/{id}` | 메타정보(scenario_id/runner/priority), 스케줄 현황(next_run_at/frequency), 마지막 결과(status/error), 스케줄 편집, 지금 실행 | P0 |
| QA 실행 이력 | GET /qa/runs → `GET /admin/qa/runs?started_after=&started_before=&trigger_type=&status=&page=&page_size=` | 날짜범위/trigger_type/status 필터, 이력 테이블(run_id/시작시간/소요시간/상태/결과카운트) | P0 |
| QA 실행 상세 | GET /qa/runs/{id} → `GET /admin/qa/runs/{id}` | target별 결과(attempt#/status/duration_ms/error_summary/artifact_ref), GitHub run 링크 | P0 |
| QA 수동 실행 | POST /admin/qa/runs | body: `{ qa_item_ids: string[] }`, QUEUED→dispatch→RUNNING lifecycle | P0 |
| QA 스케줄 수정 | PATCH /admin/qa/items/{id}/schedule | body: `{ frequency_type, enabled, anchor_time, day_of_week, value, timezone }` | P0 |
| QA 활성화 토글 | PATCH /admin/qa/items/{id} | body: `{ enabled: boolean }` | P0 |
| QA 설정 | GET /qa/settings → `GET/PUT /admin/qa/settings` | 전역설정, Runner설정, 레포트 설정 | P1 |

### AREA: QA (tai-api 내부 엔드포인트)

| SURFACE | ROUTE/API | ACTION | CRITICALITY |
|---------|-----------|--------|-------------|
| QA 콜백 수신 | `POST /internal/qa/runs/{run_id}/results` | Header: X-Internal-Secret. tai-qa GitHub Actions → results 저장 → run_status COMPLETED/ERROR | P0 |
| QA 스케줄 틱 | `POST /internal/scheduler/qa/tick` | Header: X-Internal-Secret. cron_job_master(qa_scheduler_tick) → qa_schedules 조회 → qa_runs 생성 → GitHub dispatch | P0 |

### Admin 권한 검증

```
nav gate: sectors=['__QA_ADMIN__'] → role 001만 메뉴 노출
페이지 진입: const isAdmin = computed(() => localStorage.getItem('role_code') === '001')
이중 차단: router.beforeEach(requireAuth) + nav gate
```

---

## 4. 기존 QA Scenario 현황 (tai-qa)

소스: github.com/taiengineering/tai-qa  
구조: `features/**/*.feature` + `steps/**/*.steps.ts` + `fixtures/qa.fixture.ts`  
실행: `bddgen && playwright test --grep @p0`  
스케줄: `.github/workflows/p0-smoke.yml` — 매일 23:00 UTC (08:00 KST)

### 기존 10개 Scenario

| scenario_id | SERVICE | AREA | QA_TYPE (안) | 현재 설명 | 구현 파일 |
|-------------|---------|------|-------------|-----------|-----------|
| P0-WWW-001 | WWW | LANDING | AVAILABILITY | 마케팅 사이트 메인 정상 진입 | features/marketing/core.feature |
| P0-DIAG-001 | WWW | FREE_DIAGNOSIS | AVAILABILITY | 무료 법령진단 정상 진입 | features/diagnosis/core.feature |
| P0-SRCH-001 | WWW | SEARCH | AVAILABILITY | 통합검색 정상 진입 | features/search/core.feature |
| P0-SRCH-002 | WWW | SEARCH | FUNCTIONAL | 통합검색 결과 섹터 순서 유지 (8섹터 순서 검증) | features/search/core.feature |
| P0-MYP-001 | SAAS | MYPAGE | AVAILABILITY | 마이페이지 대시보드 정상 진입 | features/mypage/core.feature |
| P0-MYP-005 | SAAS | MYPAGE | FUNCTIONAL | 결제내역 정상 조회 (403 허용, 테이블 헤더 8개 검증) | features/mypage/core.feature |
| P0-SAAS-001 | SAAS | AUTH | E2E | SaaS 로그인 → /safety-dashboard 정상 진입 (Vuetify VSelect 확인) | features/saas/core.feature |
| P0-WWW-003 | WWW | AUTH | E2E | 회원 로그인 완료 (localStorage token 확인) | features/marketing/core.feature |
| P0-WWW-004 | WWW | HEADER | FUNCTIONAL | 로그인 후 헤더 인증 상태 유지 | features/marketing/core.feature |
| P0-WWW-005 | WWW | HEADER | FUNCTIONAL | 헤더에서 마이페이지 정상 이동 | features/marketing/core.feature |

### tai-qa 기술 설계

```
fixtures/qa.fixture.ts:
  - _qaErrors 픽스처 auto=true (전 테스트 자동 적용)
  - 수집 대상: pageerror + api.taieng.co.kr 도메인 requestfailed + HTTP 5xx
  - use() 이후 fatalErrors 1건 이상 → 테스트 자동 실패

playwright.config.ts:
  - 단일 프로젝트: Chromium Desktop Chrome
  - fullyParallel: false (순차 실행)
  - CI 환경만 retries: 1
  - timeout: 30,000ms / expect.timeout: 10,000ms

.github/workflows/p0-smoke.yml:
  트리거 3종:
    1. workflow_dispatch (run_id optional + scenario_ids optional)
    2. schedule: 0 23 * * * (= 08:00 KST)
    3. pull_request → main (관련 경로 변경 시)
  콜백: workflow_dispatch + run_id 있을 때만
    POST https://api.taieng.co.kr/internal/qa/runs/{run_id}/results
    Header: X-Internal-Secret

환경 변수 (GitHub Secrets):
  WWW_BASE_URL: https://taieng.co.kr
  SAAS_BASE_URL: https://safe.taieng.co.kr
  QA_WWW_LOGIN_ID / QA_WWW_PASSWORD
  QA_SAAS_LOGIN_ID / QA_SAAS_PASSWORD
  QA_FACTORY_ID / QA_DIAG_RESULT_URL
  QA_SEARCH_TERM: 지게차 (하드코딩)

Steps 인증 방식:
  WWW: #login-id, #login-pw, #btn-login (DOM 셀렉터)
  SaaS: input[type="email"], input[type="password"], button[type="submit"] (제네릭)
```

---

## 5. 외부 연동 현황

| 연동 서비스 | 용도 | 연동 경로 | 관련 SERVICE |
|------------|------|----------|-------------|
| Inicis (KG) | 본인인증 (svc_code='01'), 카드결제 (V023) | tai-www: /log-in, /free-diagnosis, /mypage/checkout, /invite | WWW, SAAS |
| Supabase | OAuth(kakao/google), 이미지 스토리지 | tai-www: Supabase UMD SDK | WWW |
| GitHub Actions | QA 자동화 실행 | tai-api → `POST /repos/taiengineering/tai-qa/actions/workflows/p0-smoke.yml/dispatches` | ADMIN |
| Slack | QA 결과 알림 | tai-api → Slack Incoming Webhook | ADMIN |
| 마케팅 API | 지식센터 SSR | tai-www CF Function → 45cm-mkt-api-production `/public/knowledge` | WWW |
| Supabase DB | 메인 DB | tai-api → supabase-py | ALL |

---

## 6. 운영 스케줄러 대상

| 대상 | 트리거 | 구현 위치 | 비고 |
|------|--------|----------|------|
| qa_scheduler_tick | cron `* * * * *` (매분) | tai-api: services/qa_scheduler_svc.py, cron_job_master | is_active=true로 운영 중 |
| P0-SAAS-001 DAILY 자동실행 | 매일 08:00 KST | qa_schedules: frequency_type=DAILY, anchor_time=08:00:00 | 활성 |
| p0-smoke.yml schedule | 매일 23:00 UTC (=08:00 KST) | tai-qa: .github/workflows/p0-smoke.yml | PR 변경 시도 트리거 |

---

## 7. 조사 결론

### 전수 조사 완료 항목

- [x] tai-www 조사 완료 (54 routes, 7 CF Functions, 4 외부 연동)
- [x] tai-admin SAFE SaaS 조사 완료 (58 routes, 9 업무 영역)
- [x] tai-admin Operator Admin QA Console 조사 완료 (7 routes, 9 API endpoints)
- [x] tai-api endpoint 조사 완료 (254 router files, 주요 QA/인증/결제 엔드포인트 확인)
- [x] tai-qa 기존 Scenario 조사 완료 (10 scenarios, BDD 구조, 워크플로우 전체)
- [x] 코드 변경 = 0 / DB 변경 = 0 / Production mutation = 0

### 미조사 항목

- WORKER 서비스: repo/runtime 미확인. 이 문서에 항목 포함하지 않음.

### Phase 1 진입 선결 조건

이 문서 = TAI Surface SoT. Phase 1 (QA Taxonomy 구현) 및 Phase 2 (QA Universe Catalog 작성) 착수 가능.
