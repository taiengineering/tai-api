# TAI 법령엔진 v3.0 — 전체 파이프라인 구축 세션 기록

## 작업일: 2026-05-11
## 버전: v5.40.0 (프로덕션 배포 완료)

---

## 1. 세션 개요

기존 LLM 기반 법령 판단 시스템을 **Deterministic Legal Constraint Compiler**로 전면 교체.
18개 파이프라인 프롬프트 실행 + 오염데이터 정리 + Admin UI + 진단/SaaS 분리 구현.

### 핵심 철학
- 의미 추론 금지
- Rule 생성 금지
- Candidate→Truth 승격 금지
- 단위 환산 금지
- UNKNOWN 유지
- 모든 출력 CANDIDATE 상태

---

## 2. 완료된 작업 (20개 프롬프트)

### 파이프라인 14단계

| # | 프롬프트 | 산출물 | DB 건수 |
|---|---|---|---|
| 1 | Constraint Graph Enrichment | Node/Edge | 284,579 / 54,122 |
| 2 | Subtype Classification | 14종 분류 | 100% |
| 3 | Numeric Constraint | 수치 추출 | 10,329 |
| 4 | Numeric Family | Family/Relation | 10,329 / 6,934 |
| 5 | Rule Candidate IR | Rule/Slot/Rel | 34,456 / 146,595 / 59,116 |
| 6 | Compatibility Validation | PASS/Issue | 12,748 / 757 |
| 7 | Executable Draft | Draft/Slot/Graph | 10,725 / 50,133 / 10,725 |
| 8 | Facility Applicability | 평가 | 25,920 (MATCH 3,045) |
| 9 | Task Candidate | Task/Relation | 3,388 / 15,456 |
| 10 | Schedule Candidate | Schedule | 1,159 |
| 11 | Compliance Package | Pkg/Queue/Audit | 30 / 1,737 / 20 |
| 12 | Law Versioning | Hash | 35,412 |
| 13 | Residual Coverage | Residual/Pattern | 111,142 / 10,020 |
| 14 | Penalty Candidate | Penalty/Rel | 3,129 / 7,511 |

### 시스템 레이어 4단계

| # | 프롬프트 | 산출물 |
|---|---|---|
| 15 | Residual Intelligence | 12 DB테이블 + 22 API + 12 서비스 |
| 16 | Legacy Migration & Compiler Core | 7 API + 아키텍처 문서 |
| 17 | Admin Review System | 4 DB테이블 + 12 API + 5 서비스 |
| 18 | 오염데이터 정리 | ~484K건 삭제 + Issue #67 |

### 진단/SaaS 분리

| # | 프롬프트 | 산출물 |
|---|---|---|
| 19 | 법령진단서비스 | 3 DB테이블 + 3 API |
| 20 | SaaS 반복설정 | 3 DB테이블 + 6 API |

---

## 3. 이슈 및 해결 내역

### Issue #67: LLM 오염 데이터 정리
https://github.com/taiengineering/tai-api/issues/67

**TRUNCATE (~484K건):**
- law_rule_drafts (87,099) — AI 판정룰 초안
- stage_1_clauses (151,751) — AI 의미절 분해
- stage_2_elements (151,751) — AI 역할 분해
- semantic_clause_iter1 (58,495) — AI 의미절 v1
- auto_qa_log (31,326) — 자동 QA
- legal_obligations, legal_applications 등

**Archive (_legacy_contaminated):**
- master_building_legal_rules (2,002)
- master_legal_rules_pending_review (1,454)
- master_legal_rules_preserved (321)
- law_parsing_result (469)

**DROP:** ~30개 backup/old/preswitch 테이블

### 배포 이슈

| 이슈 | 원인 | 해결 |
|---|---|---|
| Dockerfile playwright not found | requirements.txt에 playwright 누락 | 추가 |
| Healthcheck failure | law_collector.py에서 SMS_URL import 실패 | messaging.py 변수명 변경(EDGE_SMS_URL)으로 law_collector.py에 alias import 적용 |
| pw_reset.py SMS 실패 | 동일 import 문제 + async 호환 | _call_edge_function + async wrapper |
| dev→main 머지 충돌 | 브랜치 불일치 | GitHub API로 main에 직접 push |

---

## 4. 서비스 플로우

### 4-1. 전체 아키텍처

```
┌─────────────────────────────────────────────────────────┐
│              Legacy Runtime Layer (유지)                │
│  55+ 라우터: auth, factories, inspection_*,          │
│  education, tbm, notifications, payment 등          │
├─────────────────────────────────────────────────────────┤
│         Compiler Core API (7 엔드포인트)               │
│  POST /compiler/evaluate-facility (핵심)              │
│  GET  task/schedule/penalty/source-trace/coverage    │
├─────────────────────────────────────────────────────────┤
│      Deterministic Legal Compiler (14 파이프라인)     │
│  Evidence Token → Canonicalization → Family          │
│  → Constraint Graph → Numeric → Rule Candidate      │
│  → Executable Draft → Applicability → Task           │
│  → Schedule → Penalty → Compliance → Residual        │
├─────────────────────────────────────────────────────────┤
│       Human Review Layer (22+12 API)                 │
│  Residual Intelligence + Admin Review                │
│  Review Queue 229건 → 사람 검토 → Registry Update      │
├─────────────────────────────────────────────────────────┤
│       법령진단서비스 (3 API)                          │
│  POST /diagnosis-engine/evaluate                     │
│  → Candidate 결과 출력 (반복설정 등록 안 함)              │
├─────────────────────────────────────────────────────────┤
│       SaaS 반복설정 (6 API)                            │
│  POST /saas-setup/extract → approve → register      │
│  승인 후에만 Runtime 등록                                │
└─────────────────────────────────────────────────────────┘
```

### 4-2. 법령진단 플로우

```
사업장 입력 (업종/인원/설비/위험물 등)
↓
POST /api/v1/diagnosis-engine/evaluate
↓
Compiler Core 실행
  ├─ Applicability Candidate (25,920건 평가)
  ├─ Obligation Candidate (task_candidate 3,388건)
  ├─ Penalty Candidate (3,129건 연결)
  ├─ Schedule Hint (1,159건)
  └─ Residual / Missing Data
↓
결과 출력 (여기까지 진단서비스)
↓
POST /api/v1/saas-setup/extract/{session_id}
↓
반복관리 후보 추출 (점검/교육/신고/측정 등)
↓
POST /api/v1/saas-setup/approve/{id}  ← 사용자 승인 필수
↓
POST /api/v1/saas-setup/register/{id}  ← Runtime 등록
```

### 4-3. Admin 법령검토 플로우

```
Residual 111,142건
↓
Pattern Mining (12 패턴)
↓
Cluster Build (9 클러스터)
↓
Registry Gap Detect (11건)
↓
Admin Review Queue (229건)
  ├─ Cluster Review: 9건 (~10,000회 반복)
  ├─ Registry Gap: 11건 (~10,000회 반복)
  ├─ Penalty Mapping: 9건
  └─ Compatibility Conflict: 200건
↓
사람 검토 (10종 액션)
  ├─ ✅ 승인 / ❌ 거절
  ├─ 📁 Family 연결/생성
  ├─ 🆕 Token 추가
  ├─ ❓ UNKNOWN 유지
  └─ 📤 법무검토 / 추가데이터
↓
Registry Update + Versioning
↓
Reprocessing Queue
↓
Candidate 재생성
```

### 4-4. 오염 방지 플로우

```
기존 LLM 기반 시스템
  law_rule_generator (44KB) — AI rule 생성
  engine_legal, legal_engine* — AI 해석
  diagnosis_autofill — AI 자동채움
  schedule_engine — AI 스케줄
↓
오염 식별 → 교체 대상 25+ 라우터
↓
오염 데이터 ~484K건 정리 (Issue #67)
↓
Deterministic Compiler Core로 교체
  모든 출력: CANDIDATE
  사람 승인 전 registry 반영 금지
  Audit + Versioning + Rollback
```

---

## 5. DB 테이블 현황

### 신규 Compiler Core (54+ 테이블)

| 테이블 | 건수 | 역할 |
|---|---|---|
| constraint_node | 284,579 | Graph 노드 |
| constraint_edge | 54,122 | Graph 엣지 |
| numeric_constraint | 10,329 | 수치 제약 |
| numeric_family_candidate | 10,329 | 수치 Family |
| numeric_graph_relation | 6,934 | 수치 관계 |
| rule_candidate | 34,456 | Rule 후보 IR |
| rule_candidate_slot | 146,595 | Slot |
| rule_candidate_relation | 59,116 | Rule 관계 |
| compatibility_validation | 59,116 | 호환성 검증 |
| compatibility_issue | 757 | 충돌 이슈 |
| executable_draft | 10,725 | 실행 초안 |
| draft_slot | 50,133 | Draft Slot |
| draft_condition_graph | 10,725 | 조건 그래프 |
| facility_applicability | 25,920 | 시설 적용 |
| facility_applicability_detail | 36,390 | 적용 상세 |
| task_candidate | 3,388 | Task 후보 |
| task_candidate_relation | 15,456 | Task 관계 |
| schedule_candidate | 1,159 | 스케줄 후보 |
| compliance_package | 30 | 컴플라이언스 |
| compliance_review_queue | 1,737 | 검토 큐 |
| law_version_hash | 35,412 | 법령 해시 |
| residual_candidate | 111,142 | 잔여 |
| residual_abstract_pattern | 10,020 | 추상 패턴 |
| residual_coverage | 704 | 커버리지 |
| penalty_candidate | 3,129 | 처벌 후보 |
| penalty_numeric | 1,696 | 처벌 수치 |
| penalty_reference_link | 2,749 | 처벌 참조 |
| penalty_obligation_relation | 7,511 | 처벌↔의무 |

### Residual Intelligence (12 테이블)

| 테이블 | 건수 |
|---|---|
| residuals | 111,142 |
| residual_failed_reasons | 111,434 |
| residual_patterns | 12 |
| residual_clusters | 9 |
| registry_gaps | 11 |
| review_queue | 20 |

### Admin Review (4 테이블)

| 테이블 | 건수 |
|---|---|
| admin_review_queue | 229 |
| admin_audit_logs | 1 |
| registry_versions | 0 |
| admin_reprocessing_queue | 0 |

### 진단/SaaS (6 테이블)

| 테이블 | 역할 |
|---|---|
| diagnosis_session | 진단 세션 |
| diagnosis_candidate | 의무/금지/적용 후보 |
| diagnosis_penalty_link | 처벌 연결 |
| diagnosis_schedule_hint | 스케줄 힌트 |
| saas_setup_candidate | 반복설정 후보 |
| saas_registration_log | Runtime 등록 이력 |

---

## 6. API 엔드포인트 (50개 신규)

### Compiler Core (7)
prefix: `/api/v1/compiler`
- POST /evaluate-facility
- GET /task-candidates/{fid}
- GET /schedule-candidates/{fid}
- GET /penalty-map/{fid}
- GET /source-trace/{part_id}
- GET /coverage-summary
- GET /health

### Residual Intelligence (22)
prefix: `/api/v1/residual-intelligence`
- POST /patterns/mine
- POST /clusters/build
- POST /registry-gaps/detect
- GET /review-queue
- POST /review-queue/{id}/decision
- GET /dashboard
- ... (외 16개)

### Admin Review (12)
prefix: `/api/v1/admin`
- GET /review-queue
- GET /review-queue/{id}
- POST /review/{id}/approve (10종 액션)
- POST /review/{id}/reject
- POST /family/create
- POST /registry/add-token
- POST /reference/link
- POST /attachment/link
- POST /rule/approve
- POST /reprocessing/trigger
- POST /rollback
- GET /audit-logs

### 법령진단서비스 (3)
prefix: `/api/v1/diagnosis-engine`
- POST /evaluate
- GET /session/{id}
- GET /sessions

### SaaS 반복설정 (6)
prefix: `/api/v1/saas-setup`
- POST /extract/{session_id}
- GET /candidates
- POST /approve/{id}
- POST /reject/{id}
- POST /needs-data/{id}
- POST /register/{id}

---

## 7. 스크립트 목록

| 파일 | 용도 |
|---|---|
| scripts/run_constraint_enrich.py | Constraint Graph |
| scripts/run_constraint_subtype.py | Subtype |
| scripts/run_numeric_full.py | Numeric Constraint |
| scripts/run_numeric_family.py | Numeric Family |
| scripts/run_rule_candidate.py | Rule Candidate IR |
| scripts/run_compatibility_check.py | Compatibility |
| scripts/run_executable_draft.py | Executable Draft |
| scripts/run_facility_applicability.py | Facility Applicability |
| scripts/run_task_candidate.py | Task Candidate |
| scripts/run_schedule_candidate.py | Schedule Candidate |
| scripts/run_compliance_package.py | Compliance Package |
| scripts/run_law_versioning.py | Law Versioning |
| scripts/run_residual_coverage.py | Residual Coverage |
| scripts/run_penalty_candidate.py | Penalty Candidate |
| scripts/run_residual_intelligence_init.py | Residual Intelligence |
| scripts/run_legacy_migration.py | Legacy Migration |
| scripts/run_admin_review_init.py | Admin Review |

실행: `cd tai-api && railway run python3 scripts/[filename]`

---

## 8. Admin UI

**접속:** `admin.taieng.co.kr/html/horizontal-menu-template/engine-legal-review.html`

**메뉴 위치:** 엔진설정 > 📜 법령검토

**기능:**
- 대시보드 (총/신규/승인/거절 카운트)
- 필터 (유형 4종 × 상태 5종)
- 검토 목록 (229건)
- 상세 모달 (원문 + 10종 승인 액션)
- 엔진 상태 (Compiler Core 8테이블)
- 감사 로그

---

## 9. 핵심 문장

- 교체 대상은 Runtime이 아니다. 법령 의미판단 Core다.
- 애매함은 제거 대상이 아니라 관리 대상이다.
- 사람이 검토한 법령만 엔진에 추가된다.
- 법령진단은 결과 출력까지. SaaS는 승인 후 운영설정까지.
- 모든 결과는 Truth가 아니라 Candidate다.
