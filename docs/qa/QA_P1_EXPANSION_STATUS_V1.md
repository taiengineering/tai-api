---
title: QA P1 Expansion Status v1
version: 1.1.0
work_order: WO-QA-P1-WAVE15-FINAL-LEDGER-CLOSEOUT-001
status: CLOSED_WITH_BLOCKERS
authored_at: 2026-10-04
code_change: 0
db_change: 0
production_mutation: 0
---

# QA P1 Expansion Status v1

P1 Universe 전체 139건 blocker 분류 대장. Wave15 최종 확정본 — NDR 26건 Wave14 소스 검증 반영.  
구현 코드 없음. Source 직접 조사 기반 분류.

---

## Anchors

| 항목 | 값 |
|------|-----|
| tai-api main | `8b485801` |
| tai-api PR branch | `docs/qa-p1-wave15-final-closeout` |
| tai-qa main | `9ab06f00` |
| 기준일 | 2026-10-04 |
| base catalog | `QA_UNIVERSE_CATALOG_V1.md` (8b485801) |

---

## Status 요약

| status | 건수 | 설명 |
|--------|------|------|
| COVERED | 38 | 자동화 완료 (tai-qa 수록) |
| BLOCKED_SOURCE_DRIFT | 47 | 소스 증거 기반 확정 (Wave6 GPT 7건 + MKT grep 14건 + route 미존재 1건 + Wave14 admin 페이지 미존재 22건 + Wave14 API 미존재 3건) |
| BLOCKED_TAXONOMY_COLLISION | 7 | ADMIN 시나리오와 중복 (SAAS/ADMIN 이중 UI) |
| BLOCKED_FIXTURE | 11 | 필수 테스트 픽스처 없음 |
| BLOCKED_SIDE_EFFECT | 33 | production DB write 발생 (거버넌스: 0 write) |
| MANUAL_ONLY | 2 | 자동화 불가 |
| PR_OPEN_HOLD_FIXTURE | 1 | tai-qa PR #9 OPEN/HOLD — fixture 미비 |
| NEEDS_DEEPER_REVIEW | 0 | Wave14 전량 분류 완료 (SD 25건 + BF 1건 흡수) |
| **합계** | **139** | |

Wave별 COVERED 이력: Wave1(16) + Wave2(14) + Wave3(3) + Wave5(2) + Wave8(1) + Wave11(2) = 38

P1 SAFE EXPANSION = CLOSED_WITH_BLOCKERS — 즉시 구현 가능한 P1 시나리오 소진 완료

---

## Wave3 COVERED 추가분

Wave3 (commit 6dcfaa0): P1-API-QA-API-002, P1-API-QA-API-004, P1-API-PAY-API-001  
Wave4 (commit 5870a8b): P1-API-DIAG-API-001 추가 — tai-qa PR #9 OPEN/HOLD (fixture 미비)

---

## P1 전체 목록

### WWW 서비스 (22건)

| scenario_id | service_code | qa_type | status | reason_code | note |
|-------------|-------------|---------|--------|-------------|------|
| P1-WWW-LANDING-FNC-001 | WWW | FUNCTIONAL | COVERED | WAVE1 | PR #4 |
| P1-WWW-LANDING-AVL-001 | WWW | AVAILABILITY | COVERED | WAVE1 | PR #4 |
| P1-WWW-LANDING-FNC-002 | WWW | FUNCTIONAL | COVERED | WAVE1 | PR #4 |
| P1-WWW-AUTH-FNC-001 | WWW | FUNCTIONAL | BLOCKED_SIDE_EFFECT | POST_REGISTER | POST /auth/register → user row INSERT |
| P1-WWW-AUTH-SEC-001 | WWW | SECURITY | COVERED | WAVE1 | PR #4 |
| P1-WWW-AUTH-INT-001 | WWW | INTEGRATION | BLOCKED_FIXTURE | OAUTH_KAKAO | Kakao OAuth 외부 provider — 자동화 sandbox 없음 |
| P1-WWW-AUTH-INT-002 | WWW | INTEGRATION | BLOCKED_FIXTURE | OAUTH_GOOGLE | Google OAuth 외부 provider — 자동화 sandbox 없음 |
| P1-WWW-AUTH-FNC-002 | WWW | FUNCTIONAL | BLOCKED_SIDE_EFFECT | POST_INVITE_ACCEPT | POST /user-invites/{token}/accept → invite accept DB write |
| P1-WWW-DIAG-FNC-001 | WWW | FUNCTIONAL | BLOCKED_SIDE_EFFECT | DIAG_RUN_MUTATION | POST /diagnosis/run: phone_auth + INSERT anonymous_diagnosis_results (Wave12 확정) |
| P1-WWW-DIAG-FNC-002 | WWW | FUNCTIONAL | BLOCKED_FIXTURE | DIAG_ANON_TOKEN | GET /free-diagnosis-result: 유효 anonymous_diagnosis token 필요 |
| P1-WWW-DIAG-AVL-001 | WWW | AVAILABILITY | COVERED | WAVE1 | PR #4 |
| P1-WWW-DIAG-FNC-003 | WWW | FUNCTIONAL | BLOCKED_FIXTURE | PAID_DIAG_TOKEN | GET /paid-diagnosis-result: 유료 진단 result token 필요 |
| P1-WWW-DIAG-API-001 | WWW | API | BLOCKED_SIDE_EFFECT | DIAG_RUN_MUTATION | POST /diagnosis/run SAFE=N (Wave12 source 확정) |
| P1-WWW-SEARCH-FNC-001 | WWW | FUNCTIONAL | COVERED | WAVE1 | PR #4 |
| P1-WWW-HEADER-FNC-001 | WWW | FUNCTIONAL | COVERED | WAVE1 | PR #4 |
| P1-WWW-HEADER-SEC-001 | WWW | SECURITY | COVERED | WAVE1 | PR #4 |
| P1-API-AUTH-API-001 | WWW | API | BLOCKED_SIDE_EFFECT | POST_REGISTER_API | POST /auth/register → user INSERT |
| P1-API-AUTH-API-002 | WWW | API | BLOCKED_FIXTURE | SUPABASE_JWT | POST /auth/ensure-user: Supabase OAuth JWT 필요 (Kakao/Google 외부 provider) |
| P1-API-DIAG-API-001 | WWW | API | PR_OPEN_HOLD_FIXTURE | DIAG_ANON_TOKEN | tai-qa PR #9 OPEN/HOLD (HEAD 5870a8b): fixture=유효 anonymous_diagnosis token 미비 |
| P1-API-DIAG-API-002 | WWW | API | COVERED | WAVE1 | PR #4 |
| P1-API-DIAG-API-003 | WWW | API | BLOCKED_FIXTURE | PAID_DIAG_TOKEN_API | GET /diagnosis/paid-result/{token}: 유료 진단 token 필요 |
| P1-API-PUB-API-001 | WWW | API | COVERED | WAVE1 | PR #4 |

### SAAS 서비스 (42건)

| scenario_id | service_code | qa_type | status | reason_code | note |
|-------------|-------------|---------|--------|-------------|------|
| P1-SAAS-AUTH-FNC-001 | SAAS | FUNCTIONAL | COVERED | WAVE8 | PR #11 |
| P1-SAAS-AUTH-SEC-001 | SAAS | SECURITY | COVERED | WAVE1 | PR #4 |
| P1-SAAS-DASH-AVL-001 | SAAS | AVAILABILITY | COVERED | WAVE2 | PR #5 |
| P1-SAAS-DASH-FNC-001 | SAAS | FUNCTIONAL | COVERED | WAVE2 | PR #5 |
| P1-SAAS-MYP-AVL-001 | SAAS | AVAILABILITY | COVERED | WAVE2 | PR #5 |
| P1-SAAS-MYP-FNC-001 | SAAS | FUNCTIONAL | BLOCKED_SIDE_EFFECT | PATCH_AUTH_ME | PATCH /auth/me → user profile UPDATE |
| P1-SAAS-MYP-FNC-002 | SAAS | FUNCTIONAL | BLOCKED_SIDE_EFFECT | POST_FACTORIES | POST /factories → factory INSERT |
| P1-SAAS-MYP-SEC-001 | SAAS | SECURITY | COVERED | WAVE1 | PR #4 |
| P1-SAAS-MYP-DATA-001 | SAAS | DATA | BLOCKED_FIXTURE | PAYMENT_HISTORY | GET /payments 화면 정합 — 결제 이력 fixture 없음 |
| P1-SAAS-MYP-AVL-002 | SAAS | AVAILABILITY | COVERED | WAVE2 | PR #5 |
| P1-SAAS-MYP-E2E-001 | SAAS | E2E | MANUAL_ONLY | INICIS_REAL_PAYMENT | Inicis PROD 결제 자동화 불가 (SAFE=N) |
| P1-SAAS-INSP-AVL-001 | SAAS | AVAILABILITY | COVERED | WAVE2 | PR #5 |
| P1-SAAS-INSP-FNC-001 | SAAS | FUNCTIONAL | BLOCKED_SIDE_EFFECT | POST_INSP_RESULT | POST /inspection/result/{id}/items → inspection result INSERT |
| P1-SAAS-INSP-FNC-002 | SAAS | FUNCTIONAL | BLOCKED_FIXTURE | INSP_RESULT_ID | 유효 inspection result ID fixture 없음 |
| P1-SAAS-EDU-AVL-001 | SAAS | AVAILABILITY | COVERED | WAVE2 | PR #5 |
| P1-SAAS-EDU-FNC-001 | SAAS | FUNCTIONAL | BLOCKED_SIDE_EFFECT | POST_EDU_ASSIGN | POST /educations/{id}/assign → assignment INSERT |
| P1-SAAS-EDU-AVL-002 | SAAS | AVAILABILITY | COVERED | WAVE2 | PR #5 |
| P1-SAAS-EDU-FNC-002 | SAAS | FUNCTIONAL | BLOCKED_SIDE_EFFECT | POST_TBM | POST /tbms → TBM record INSERT |
| P1-SAAS-BILL-AVL-001 | SAAS | AVAILABILITY | COVERED | WAVE2 | PR #5 |
| P1-SAAS-BILL-DATA-001 | SAAS | DATA | BLOCKED_FIXTURE | CONTRACT_FIXTURE | GET /me/commercial/contract 화면 정합 — active contract fixture 없음 |
| P1-SAAS-BILL-FNC-001 | SAAS | FUNCTIONAL | BLOCKED_SIDE_EFFECT | POST_PURCHASE_DIAG | POST /payments/purchase-diagnosis → payment + diagnosis INSERT |
| P1-SAAS-SET-FNC-001 | SAAS | FUNCTIONAL | BLOCKED_SIDE_EFFECT | PUT_ME | PUT /me → user profile UPDATE |
| P1-SAAS-SET-FNC-002 | SAAS | FUNCTIONAL | BLOCKED_SIDE_EFFECT | PUT_COMPANIES | PUT /companies/{id} → company UPDATE |
| P1-SAAS-SET-FNC-003 | SAAS | FUNCTIONAL | COVERED | WAVE2 | PR #5 |
| P1-SAAS-SET-FNC-004 | SAAS | FUNCTIONAL | BLOCKED_SIDE_EFFECT | PUT_PERMISSIONS | PUT /permissions → permission UPDATE |
| P1-SAAS-CON-AVL-001 | SAAS | AVAILABILITY | COVERED | WAVE2 | PR #5 |
| P1-SAAS-CON-FNC-001 | SAAS | FUNCTIONAL | BLOCKED_SIDE_EFFECT | POST_CONSTRUCTION | POST /construction/step1 → construction record INSERT |
| P1-SAAS-CON-AVL-002 | SAAS | AVAILABILITY | COVERED | WAVE2 | PR #5 |
| P1-SAAS-CON-AVL-003 | SAAS | AVAILABILITY | COVERED | WAVE2 | PR #5 |
| P1-SAAS-CON-AVL-004 | SAAS | AVAILABILITY | COVERED | WAVE2 | PR #5 |
| P1-SAAS-RISK-AVL-001 | SAAS | AVAILABILITY | COVERED | WAVE2 | PR #5 |
| P1-SAAS-RISK-FNC-001 | SAAS | FUNCTIONAL | BLOCKED_SIDE_EFFECT | POST_RISK_ASSESS | POST /risk-assessments/{id}/assess → assessment UPDATE |
| P1-SAAS-QA-AVL-001 | SAAS | AVAILABILITY | BLOCKED_TAXONOMY_COLLISION | ADMIN_DUPLICATE | P1-ADMIN-OPS-AVL-003와 동일 /admin/qa/summary (SAAS/ADMIN 이중 UI) |
| P1-SAAS-QA-FNC-001 | SAAS | FUNCTIONAL | BLOCKED_TAXONOMY_COLLISION | ADMIN_DUPLICATE | P1-ADMIN-OPS-FNC-001과 동일 /admin/qa/items GET |
| P1-SAAS-QA-FNC-002 | SAAS | FUNCTIONAL | BLOCKED_TAXONOMY_COLLISION | ADMIN_DUPLICATE | /admin/qa/items 상세 — ADMIN 경로 중복 |
| P1-SAAS-QA-FNC-003 | SAAS | FUNCTIONAL | BLOCKED_TAXONOMY_COLLISION | ADMIN_DUPLICATE | P1-ADMIN-OPS-FNC-004와 동일 /admin/qa/runs GET |
| P1-SAAS-QA-FNC-004 | SAAS | FUNCTIONAL | BLOCKED_TAXONOMY_COLLISION | ADMIN_DUPLICATE | POST /admin/qa/runs — P1-ADMIN-OPS-FNC-003 중복 |
| P1-SAAS-QA-SEC-001 | SAAS | SECURITY | BLOCKED_TAXONOMY_COLLISION | ADMIN_DUPLICATE | QA 페이지 접근 차단 — ADMIN AUTH_GUARD 중복 |
| P1-SAAS-QA-FNC-005 | SAAS | FUNCTIONAL | BLOCKED_TAXONOMY_COLLISION | ADMIN_DUPLICATE | PATCH /admin/qa/items/{id}/schedule — P1-ADMIN-OPS-FNC-006 중복 |
| P1-API-AUTH-API-003 | SAAS | API | BLOCKED_SIDE_EFFECT | PATCH_AUTH_ME_API | PATCH /auth/me → user profile UPDATE |
| P1-API-PAY-API-002 | SAAS | API | BLOCKED_SIDE_EFFECT | POST_PURCHASE_DIAG_API | POST /payments/purchase-diagnosis → payment INSERT |
| P1-API-PAY-SEC-001 | SAAS | SECURITY | BLOCKED_FIXTURE | TENANT_ISOLATION_FIXTURE | 다른 company_id 사용자 fixture 쌍 없음 |

### ADMIN 서비스 (75건)

| scenario_id | service_code | qa_type | status | reason_code | note |
|-------------|-------------|---------|--------|-------------|------|
| P1-ADMIN-DASH-AVL-001 | ADMIN | AVAILABILITY | BLOCKED_SOURCE_DRIFT | WAVE6_GPT_CONFIRMED | admin console 페이지 drift — Wave6 GPT 확정 |
| P1-ADMIN-DASH-FNC-001 | ADMIN | FUNCTIONAL | BLOCKED_SOURCE_DRIFT | ADMIN_PAGE_NOT_FOUND | Wave14 확정 — 다중 API 집계 대시보드 tai-admin 내부운영 콘솔 페이지 미존재 |
| P1-ADMIN-DASH-SEC-001 | ADMIN | SECURITY | COVERED | WAVE1 | PR #4 |
| P1-ADMIN-OPS-AVL-001 | ADMIN | AVAILABILITY | BLOCKED_SOURCE_DRIFT | WAVE6_GPT_CONFIRMED | GET /ops/home — admin console 페이지 drift Wave6 GPT 확정 |
| P1-ADMIN-OPS-AVL-002 | ADMIN | AVAILABILITY | BLOCKED_SOURCE_DRIFT | WAVE6_GPT_CONFIRMED | GET /admin/audit-logs — admin console 페이지 drift Wave6 GPT 확정 |
| P1-ADMIN-OPS-FNC-001 | ADMIN | FUNCTIONAL | COVERED | WAVE11 | PR #12 |
| P1-ADMIN-OPS-FNC-002 | ADMIN | FUNCTIONAL | BLOCKED_SIDE_EFFECT | PATCH_QA_ITEM | PATCH /admin/qa/items/{id} → qa_items UPDATE (Wave12 source 확정) |
| P1-ADMIN-OPS-FNC-003 | ADMIN | FUNCTIONAL | BLOCKED_SIDE_EFFECT | POST_QA_RUNS | POST /admin/qa/runs → qa_runs INSERT + GitHub Actions dispatch |
| P1-ADMIN-OPS-FNC-004 | ADMIN | FUNCTIONAL | COVERED | WAVE11 | PR #12 |
| P1-ADMIN-OPS-FNC-005 | ADMIN | FUNCTIONAL | BLOCKED_SIDE_EFFECT | POST_AUTO_APPROVE | POST /automation/runs/{id}/approve → real automation execution |
| P1-ADMIN-OPS-AVL-003 | ADMIN | AVAILABILITY | COVERED | WAVE5 | PR #10 |
| P1-ADMIN-OPS-AVL-004 | ADMIN | AVAILABILITY | COVERED | WAVE5 | PR #10 |
| P1-ADMIN-OPS-FNC-006 | ADMIN | FUNCTIONAL | BLOCKED_SIDE_EFFECT | PATCH_QA_SCHEDULE_WRITE | PATCH /admin/qa/items/{id}/schedule → qa_schedules UPDATE; CM-002 선결 미해결 병존 |
| P1-ADMIN-CUST-AVL-001 | ADMIN | AVAILABILITY | BLOCKED_SOURCE_DRIFT | ADMIN_PAGE_NOT_FOUND | Wave14 확정 — GET /companies/{id}/360 tai-admin 고객 상세 콘솔 페이지 미존재 |
| P1-ADMIN-CUST-FNC-001 | ADMIN | FUNCTIONAL | BLOCKED_SOURCE_DRIFT | WAVE6_GPT_CONFIRMED | GET /companies — admin console 페이지 drift Wave6 GPT 확정 |
| P1-ADMIN-CUST-FNC-002 | ADMIN | FUNCTIONAL | BLOCKED_SIDE_EFFECT | POST_COMPANIES | POST/PATCH /companies → company INSERT/UPDATE |
| P1-ADMIN-CUST-FNC-003 | ADMIN | FUNCTIONAL | BLOCKED_SOURCE_DRIFT | ADMIN_PAGE_NOT_FOUND | Wave14 확정 — GET /factories tai-admin 공장 목록 콘솔 페이지 미존재 |
| P1-ADMIN-CUST-FNC-004 | ADMIN | FUNCTIONAL | BLOCKED_SOURCE_DRIFT | ADMIN_PAGE_NOT_FOUND | Wave14 확정 — GET /users tai-admin 사용자 목록 콘솔 페이지 미존재 |
| P1-ADMIN-CUST-FNC-005 | ADMIN | FUNCTIONAL | BLOCKED_SOURCE_DRIFT | ADMIN_PAGE_NOT_FOUND | Wave14 확정 — GET /admin/inquiries tai-admin 문의 목록 콘솔 페이지 미존재 |
| P1-ADMIN-BILL-AVL-001 | ADMIN | AVAILABILITY | BLOCKED_SOURCE_DRIFT | ADMIN_PAGE_NOT_FOUND | Wave14 확정 — GET /stats/business tai-admin 결제 현황 콘솔 페이지 미존재 |
| P1-ADMIN-BILL-FNC-001 | ADMIN | FUNCTIONAL | BLOCKED_SOURCE_DRIFT | ADMIN_PAGE_NOT_FOUND | Wave14 확정 — GET /payments/{id}/ledger tai-admin 결제원장 상세 콘솔 페이지 미존재 |
| P1-ADMIN-BILL-FNC-002 | ADMIN | FUNCTIONAL | BLOCKED_SIDE_EFFECT | POST_CONTRACT_ACTIVATE | POST /contracts/{id}/activate → ACTIVE 전환 비가역 (Wave12 확정) |
| P1-ADMIN-BILL-FNC-003 | ADMIN | FUNCTIONAL | BLOCKED_SOURCE_DRIFT | ADMIN_PAGE_NOT_FOUND | Wave14 확정 — GET /payments/admin/tax-invoices tai-admin 세금계산서 콘솔 페이지 미존재 |
| P1-ADMIN-BILL-FNC-004 | ADMIN | FUNCTIONAL | BLOCKED_SOURCE_DRIFT | ADMIN_PAGE_NOT_FOUND | Wave14 확정 — GET /payments/ops/gate-readiness tai-admin 결제 게이트 콘솔 페이지 미존재 |
| P1-ADMIN-BILL-FNC-005 | ADMIN | FUNCTIONAL | BLOCKED_FIXTURE | QUOTE_COMPANY_CONTEXT_REQUIRED | Wave14 확정 — commercial-console 존재, API 존재, 그러나 company 선택 선행 필요; is_demo=true 계약사 GET /companies 제외로 QA-safe fixture 경로 없음 |
| P1-ADMIN-BILL-FNC-006 | ADMIN | FUNCTIONAL | BLOCKED_SIDE_EFFECT | POST_QUOTE_ISSUE | POST /admin/quotes/{id}/custom/issue → ISSUED 전환 비가역 (Wave12 확정) |
| P1-ADMIN-BILL-FNC-007 | ADMIN | FUNCTIONAL | BLOCKED_SOURCE_DRIFT | WAVE6_GPT_CONFIRMED | GET /price/summary-cards — admin console 페이지 drift Wave6 GPT 확정 |
| P1-ADMIN-BILL-SEC-001 | ADMIN | SECURITY | BLOCKED_SOURCE_DRIFT | PAYMENT_CANCEL_ROUTE_NOT_FOUND | Universe target POST /payments/{id}/cancel absent from current tai-api; /refund and /partial-refund exist instead |
| P1-ADMIN-BILL-DATA-001 | ADMIN | DATA | BLOCKED_SOURCE_DRIFT | ADMIN_PAGE_NOT_FOUND | Wave14 확정 — GET /payments 결제 목록 tai-admin 내부운영 콘솔 페이지 미존재 |
| P1-ADMIN-BILL-FNC-008 | ADMIN | FUNCTIONAL | MANUAL_ONLY | SAFE_N_REAL_REFUND | POST /payments/{id}/refund (SAFE=N) — 실환불 자동화 불가 |
| P1-ADMIN-SVC-AVL-001 | ADMIN | AVAILABILITY | BLOCKED_SOURCE_DRIFT | WAVE6_GPT_CONFIRMED | GET /anonymous-diagnosis/admin/list — admin console 페이지 drift Wave6 GPT 확정 |
| P1-ADMIN-SVC-AVL-002 | ADMIN | AVAILABILITY | BLOCKED_SOURCE_DRIFT | ADMIN_PAGE_NOT_FOUND | Wave14 확정 — GET /legal-engine/result/{factory_id} tai-api endpoint 존재; tai-admin 법령진단 결과 viewer 페이지 미존재 (compliance-report는 다른 semantic) |
| P1-ADMIN-SVC-FNC-001 | ADMIN | FUNCTIONAL | BLOCKED_SIDE_EFFECT | FORM_SUBMIT_WRITE | 진단 연결 처리 폼 제출 포함 → DB write 발생 |
| P1-ADMIN-SVC-AVL-003 | ADMIN | AVAILABILITY | BLOCKED_SOURCE_DRIFT | ADMIN_PAGE_NOT_FOUND | Wave14 확정 — GET /companies (MOCK 포함) tai-admin 고객사 목록 콘솔 페이지 미존재 |
| P1-ADMIN-SVC-FNC-002 | ADMIN | FUNCTIONAL | BLOCKED_SIDE_EFFECT | PATCH_PERMISSIONS | PATCH /permissions → permissions UPDATE |
| P1-ADMIN-SVC-FNC-003 | ADMIN | FUNCTIONAL | BLOCKED_SIDE_EFFECT | PATCH_PERMISSIONS_PLATFORM | PATCH /permissions/platform → permissions UPDATE |
| P1-ADMIN-SVC-FNC-004 | ADMIN | FUNCTIONAL | BLOCKED_SOURCE_DRIFT | ADMIN_PAGE_NOT_FOUND | Wave14 확정 — GET /admin/site-faqs tai-admin FAQ 콘솔 페이지 미존재 |
| P1-ADMIN-COMM-AVL-001 | ADMIN | AVAILABILITY | BLOCKED_SOURCE_DRIFT | ADMIN_PAGE_NOT_FOUND | Wave14 확정 — GET /mail/list tai-api 존재, tai-admin 메일 목록 콘솔 페이지 미존재 |
| P1-ADMIN-COMM-FNC-001 | ADMIN | FUNCTIONAL | BLOCKED_SOURCE_DRIFT | ADMIN_PAGE_NOT_FOUND | Wave14 확정 — GET /mail/{id} tai-api 존재, tai-admin 메일 상세 콘솔 페이지 미존재 |
| P1-ADMIN-COMM-AVL-002 | ADMIN | AVAILABILITY | BLOCKED_SOURCE_DRIFT | ADMIN_PAGE_NOT_FOUND | Wave14 확정 — GET /notices tai-admin 공지사항 목록 콘솔 페이지 미존재 |
| P1-ADMIN-COMM-FNC-002 | ADMIN | FUNCTIONAL | BLOCKED_SIDE_EFFECT | POST_NOTICES | POST /notices → notice INSERT |
| P1-ADMIN-MKT-AVL-001 | ADMIN | AVAILABILITY | BLOCKED_SOURCE_DRIFT | MKT_ROUTE_NOT_FOUND | GET /admin/marketing/dashboard — tai-api grep 미존재 확정 (Wave13) |
| P1-ADMIN-MKT-AVL-002 | ADMIN | AVAILABILITY | BLOCKED_SOURCE_DRIFT | MKT_ROUTE_NOT_FOUND | Supabase naver_kin_log — tai-api /admin/marketing/* 라우터 없음 |
| P1-ADMIN-MKT-FNC-001 | ADMIN | FUNCTIONAL | BLOCKED_SOURCE_DRIFT | MKT_ROUTE_NOT_FOUND | GET /admin/marketing/publish/options/* — 미존재 확정 |
| P1-ADMIN-MKT-AVL-003 | ADMIN | AVAILABILITY | BLOCKED_SOURCE_DRIFT | MKT_ROUTE_NOT_FOUND | GET /admin/marketing/contents — 미존재 확정 |
| P1-ADMIN-MKT-AVL-004 | ADMIN | AVAILABILITY | BLOCKED_SOURCE_DRIFT | MKT_ROUTE_NOT_FOUND | GET /admin/marketing/publish-jobs — 미존재 확정 |
| P1-ADMIN-MKT-AVL-005 | ADMIN | AVAILABILITY | BLOCKED_SOURCE_DRIFT | MKT_ROUTE_NOT_FOUND | GET /admin/marketing/performance — 미존재 확정 |
| P1-ADMIN-MKT-FNC-002 | ADMIN | FUNCTIONAL | BLOCKED_SOURCE_DRIFT | MKT_ROUTE_NOT_FOUND | POST /admin/marketing/channels/{code}/activate — 미존재 확정 |
| P1-ADMIN-MKT-AVL-006 | ADMIN | AVAILABILITY | BLOCKED_SOURCE_DRIFT | MKT_ROUTE_NOT_FOUND | GET /admin/marketing/customers — 미존재 확정 |
| P1-ADMIN-MKT-AVL-007 | ADMIN | AVAILABILITY | BLOCKED_SOURCE_DRIFT | MKT_ROUTE_NOT_FOUND | GET /admin/marketing/journeys — 미존재 확정 |
| P1-ADMIN-MKT-FNC-003 | ADMIN | FUNCTIONAL | BLOCKED_SOURCE_DRIFT | MKT_ROUTE_NOT_FOUND | POST /admin/marketing/strategies — 미존재 확정 |
| P1-ADMIN-MKT-FNC-004 | ADMIN | FUNCTIONAL | BLOCKED_SOURCE_DRIFT | MKT_ROUTE_NOT_FOUND | POST /admin/marketing/contracts/{code}/activate — 미존재 확정 |
| P1-ADMIN-MKT-AVL-008 | ADMIN | AVAILABILITY | BLOCKED_SOURCE_DRIFT | MKT_ROUTE_NOT_FOUND | GET /admin/marketing/queue — 미존재 확정 |
| P1-ADMIN-MKT-FNC-005 | ADMIN | FUNCTIONAL | BLOCKED_SOURCE_DRIFT | MKT_ROUTE_NOT_FOUND | POST /admin/marketing/scheduler/run-once — 미존재 확정 |
| P1-ADMIN-MKT-FNC-006 | ADMIN | FUNCTIONAL | BLOCKED_SOURCE_DRIFT | MKT_ROUTE_NOT_FOUND | GET /admin/marketing/audit — 미존재 확정 |
| P1-ADMIN-STAT-AVL-001 | ADMIN | AVAILABILITY | BLOCKED_SOURCE_DRIFT | WAVE6_GPT_CONFIRMED | GET /stats/overview — admin console 페이지 drift Wave6 GPT 확정 |
| P1-ADMIN-STAT-AVL-002 | ADMIN | AVAILABILITY | BLOCKED_SOURCE_DRIFT | ADMIN_PAGE_NOT_FOUND | Wave14 확정 — GET /stats/funnel tai-admin 통계 퍼널 콘솔 페이지 미존재 |
| P1-ADMIN-STAT-AVL-003 | ADMIN | AVAILABILITY | BLOCKED_SOURCE_DRIFT | ADMIN_PAGE_NOT_FOUND | Wave14 확정 — GET /stats/customers tai-admin 고객 통계 콘솔 페이지 미존재 |
| P1-ADMIN-STAT-AVL-004 | ADMIN | AVAILABILITY | BLOCKED_SOURCE_DRIFT | ADMIN_PAGE_NOT_FOUND | Wave14 확정 — GET /stats/revenue tai-admin 매출 통계 콘솔 페이지 미존재 |
| P1-ADMIN-STAT-AVL-005 | ADMIN | AVAILABILITY | BLOCKED_SOURCE_DRIFT | ADMIN_PAGE_NOT_FOUND | Wave14 확정 — GET /stats/fulfillment tai-admin 이행 통계 콘솔 페이지 미존재 |
| P1-ADMIN-STAT-AVL-006 | ADMIN | AVAILABILITY | BLOCKED_SOURCE_DRIFT | ADMIN_PAGE_NOT_FOUND | Wave14 확정 — GET /stats/workers tai-admin 작업자 통계 콘솔 페이지 미존재 |
| P1-ADMIN-STAT-DATA-001 | ADMIN | DATA | BLOCKED_SOURCE_DRIFT | ADMIN_PAGE_NOT_FOUND | Wave14 확정 — GET /stats/overview 화면 정합 tai-admin 통계 콘솔 페이지 미존재 |
| P1-ADMIN-DEV-FNC-001 | ADMIN | FUNCTIONAL | BLOCKED_SIDE_EFFECT | PATCH_SYSTEM_CODES | PATCH /system-codes → system_codes UPDATE |
| P1-ADMIN-DEV-AVL-001 | ADMIN | AVAILABILITY | BLOCKED_SOURCE_DRIFT | API_NOT_FOUND | Wave14 확정 — GET /legal-engine/dashboard tai-api 미존재 + tai-admin 콘솔 페이지 미존재 |
| P1-ADMIN-DEV-FNC-002 | ADMIN | FUNCTIONAL | BLOCKED_SIDE_EFFECT | POST_LEGAL_PARSE | POST /legal-engine/parse → AI rule draft INSERT |
| P1-ADMIN-DEV-AVL-002 | ADMIN | AVAILABILITY | BLOCKED_SOURCE_DRIFT | API_NOT_FOUND | Wave14 확정 — GET /control-runtime/health tai-api 미존재 + tai-admin 콘솔 페이지 미존재 |
| P1-ADMIN-DEV-FNC-003 | ADMIN | FUNCTIONAL | BLOCKED_SIDE_EFFECT | POST_CRON_RUN | POST /cron/jobs/{code}/run → cron action 실행 |
| P1-ADMIN-DEV-AVL-003 | ADMIN | AVAILABILITY | BLOCKED_SOURCE_DRIFT | API_NOT_FOUND | Wave14 확정 — GET /watch-engine/* tai-api 미존재 + tai-admin 콘솔 페이지 미존재 |
| P1-API-QA-API-001 | ADMIN | API | COVERED | WAVE1 | PR #4 |
| P1-API-QA-API-002 | ADMIN | API | COVERED | WAVE3 | commit 6dcfaa0 |
| P1-API-QA-API-003 | ADMIN | API | COVERED | WAVE1 | PR #4 |
| P1-API-QA-API-004 | ADMIN | API | COVERED | WAVE3 | commit 6dcfaa0 |
| P1-API-QA-API-005 | ADMIN | API | BLOCKED_SIDE_EFFECT | PATCH_QA_ITEM_API | PATCH /admin/qa/items/{id} → qa_items UPDATE |
| P1-API-QA-SEC-001 | ADMIN | SECURITY | COVERED | WAVE1 | PR #4 |
| P1-API-PAY-API-001 | ADMIN | API | COVERED | WAVE3 | commit 6dcfaa0 |

---

## 검증

```
COVERED                    =  38 (WWW:10 + SAAS:17 + ADMIN:11)
BLOCKED_SOURCE_DRIFT       =  47 (WAVE6_GPT_CONFIRMED:7 + MKT_ROUTE_NOT_FOUND:14 + PAYMENT_CANCEL_ROUTE_NOT_FOUND:1 + ADMIN_PAGE_NOT_FOUND:22 + API_NOT_FOUND:3)
NEEDS_DEEPER_REVIEW        =   0
BLOCKED_TAXONOMY_COLLISION =   7 (SAAS-QA-* 7건)
BLOCKED_FIXTURE            =  11 (WWW:6 + SAAS:4 + ADMIN:1)
BLOCKED_SIDE_EFFECT        =  33 (WWW:5 + SAAS:13 + ADMIN:15)
MANUAL_ONLY                =   2 (SAAS:1 + ADMIN:1)
PR_OPEN_HOLD_FIXTURE       =   1 (WWW:1 — tai-qa PR #9)
합계                       = 139 ✓
```

READY confirmed = 0  
NEEDS_DEEPER_REVIEW = 0 (Wave14 전량 분류 완료)  
P1 SAFE EXPANSION = CLOSED_WITH_BLOCKERS
