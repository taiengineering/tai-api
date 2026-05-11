# TAI 법령엔진 v3.0 — 전체 파이프라인 구축 세션 기록

## 작업일: 2026-05-11
## 버전: v5.40.0 (프로덕션 배포 완료)

---

## 1. 세션 개요

기존 LLM 기반 법령 판단 시스템을 **Deterministic Legal Constraint Compiler**로 전면 교체.
20개 파이프라인 프롬프트 실행 + 오염데이터 정리 + Admin UI + 진단/SaaS 분리 구현.

### 핵심 철학
```
❌ 의미 추론 금지
❌ Rule 생성 금지
❌ Candidate→Truth 승격 금지
❌ 단위 환산 금지
✅ UNKNOWN 유지
✅ 모든 출력 CANDIDATE 상태
✅ 사람 검토 후에만 Registry 반영
```

---

## 2. 완료된 작업 (20개 프롬프트)

### Phase 1: Compiler 파이프라인 14단계

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

### Phase 2: 시스템 레이어 4단계

| # | 프롬프트 | 산출물 |
|---|---|---|
| 15 | Residual Intelligence | 12 DB테이블 + 22 API + 12 서비스 |
| 16 | Legacy Migration & Compiler Core | 7 API + 아키텍처 문서 |
| 17 | Admin Review System | 4 DB테이블 + 12 API + 5 서비스 |
| 18 | main.py 라우터 등록 + Admin UI | v5.39.0 + 법령검토 페이지 |

### Phase 3: 오염데이터 정리 + 진단/SaaS 분리

| # | 프롬프트 | 산출물 |
|---|---|---|
| - | 오염데이터 정리 (Issue #67) | ~484K건 삭제 + 아카이브 + DROP |
| 19 | 법령진단서비스 | 3 DB테이블 + 3 API |
| 20 | SaaS 반복설정 | 3 DB테이블 + 6 API |

---

## 3. 이슈 및 해결 내역

### 3-1. Issue #67: LLM 오염 데이터 정리
https://github.com/taiengineering/tai-api/issues/67

**문제:** LLM이 생성한 법령 데이터가 Deterministic 파이프라인과 혼재되면 오염 발생.

**TRUNCATE (~484K건):**
- law_rule_drafts (87,099) — AI 판정룰 초안
- stage_1_clauses (151,751) — AI 의미절 분해
- stage_2_elements (151,751) — AI 역할 분해
- semantic_clause_iter1 (58,495) — AI 의미절 v1
- auto_qa_log (31,326) — 자동 QA
- legal_obligations, legal_applications 등

**Archive → `_legacy_contaminated` 접미사 테이블:**
- master_building_legal_rules (2,002)
- master_legal_rules_pending_review (1,454)
- master_legal_rules_preserved (321)
- law_parsing_result (469)

**DROP:** ~30개 backup/old/preswitch 테이블

### 3-2. 배포 이슈 3건

| 이슈 | 원인 | 해결 |
|---|---|---|
| **playwright not found** | requirements.txt에 playwright 누락 | 추가 |
| **Healthcheck failure** | `law_collector.py`에서 `SMS_URL`, `_call_messageme` import 실패. `messaging.py`에서 `EDGE_SMS_URL`, `_call_edge_function`으로 리네임됨 | `law_collector.py`에 alias import 적용: `from routers.messaging import EDGE_SMS_URL as SMS_URL, _call_edge_function as _call_messageme` |
| **pw_reset.py SMS 실패** | 동일 import 문제 + `_call_edge_function`이 async | `_call_edge_function` + `asyncio` wrapper 적용 |

### 3-3. 브랜치 이슈

| 이슈 | 해결 |
|---|---|
| dev↔main diverged, `git merge` 충돌 | GitHub API로 main에 직접 push |
| 로컬에서 push rejected (non-fast-forward) | `git pull origin main` 후 재시도 또는 API 직접 push |

### 3-4. 229건 검토 영향 분석

229건 전부 처리 시 예상 변화:

| 지표 | 현재 | 처리 후 | 변화 |
|---|---|---|---|
| Residual | 111,142 | ~101,000 | -10,000 (-9%) |
| 커버리지 | 64.5% | ~73% | +8.5%p |
| Registry Token | 92 | ~103 | +11 |
| Rule Candidate | 34,456 | ~36,000 | +1,500 |

핵심 20건(Cluster 9 + Gap 11)이 영향 최대.
"대통령령으로 정하는" (5,866회) 같은 위임 조항은 KEEP_AS_UNKNOWN이 적절할 수 있음.

---

## 4. 서비스 플로우

### 4-1. 전체 아키텍처

```
┌───────────────────────────────────────────────────────────┐
│              Legacy Runtime Layer (유지)                  │
│  55+ 라우터: auth, factories, inspection,              │
│  education, tbm, notifications, payment 등            │
├───────────────────────────────────────────────────────────┤
│     ⬇ NEW: Deterministic Legal Compiler (14단계)       │
│                                                           │
│  law_master (768법령)                                    │
│    ↓                                                      │
│  Evidence Token → Canonicalization → Family              │
│    ↓                                                      │
│  Constraint Graph (284K node / 54K edge)                 │
│    ↓                                                      │
│  Numeric Constraint (10,329) → Family (6,934 rel)        │
│    ↓                                                      │
│  Rule Candidate IR (34,456 rule / 146K slot)              │
│    ↓                                                      │
│  Executable Draft (10,725) → Applicability (25,920)       │
│    ↓                                                      │
│  Task (3,388) → Schedule (1,159) → Penalty (3,129)       │
│    ↓                                                      │
│  Compliance Package (30) + Residual (111,142)             │
├───────────────────────────────────────────────────────────┤
│     ⬇ NEW: Compiler Core API (7 엔드포인트)              │
│  POST /compiler/evaluate-facility (핵심)                 │
│  GET  /compiler/health                                    │
│  GET  task/schedule/penalty/source-trace/coverage         │
├───────────────────────────────────────────────────────────┤
│     ⬇ NEW: Human Review Layer (22+12 API)                │
│                                                           │
│  Residual Intelligence (22 API)                           │
│    Pattern Mining → Cluster → Gap Detect → Dashboard     │
│                                                           │
│  Admin Review (12 API)                                    │
│    Review Queue 229건 → 10종 액션 → Audit/Versioning     │
│                                                           │
│  Admin UI: engine-legal-review.html                       │
├───────────────────────────────────────────────────────────┤
│     ⬇ NEW: 법령진단서비스 (3 API)                       │
│  POST /diagnosis-engine/evaluate                          │
│  → Candidate 결과 출력 (반복설정 등록 안 함)                 │
├───────────────────────────────────────────────────────────┤
│     ⬇ NEW: SaaS 반복설정 (6 API)                         │
│  POST /saas-setup/extract → approve → register           │
│  승인 후에만 Runtime 등록. rollback 가능.                   │
└───────────────────────────────────────────────────────────┘
```

### 4-2. 법령진단 → SaaS 플로우

```
사업장 입력 (업종/인원/설비/위험물/수변전용량 등)
    │
    ▼
POST /api/v1/diagnosis-engine/evaluate
    │
    ├── Applicability Candidate (25,920건 평가)
    ├── Obligation Candidate (3,388건 task)
    ├── Penalty Candidate (3,129건 연결)
    ├── Schedule Hint (1,159건)
    ├── Residual / Missing Data
    └── Human Review Queue
    │
    ▼  (여기까지 진단서비스. 아래부터 SaaS)
    │
POST /api/v1/saas-setup/extract/{session_id}
    │  반복관리 대상만 추출 (INSPECTION, EDUCATION, REPORT 등)
    │  UNKNOWN/AMBIGUOUS/NEEDS_HUMAN_REVIEW → 보류
    │  자동 등록 절대 금지
    │
    ▼
GET /api/v1/saas-setup/candidates
    │  사용자가 후보 목록 확인
    │
    ├── POST /approve/{id}      → APPROVED_FOR_SAAS_SETUP
    ├── POST /reject/{id}       → REJECTED_BY_USER
    └── POST /needs-data/{id}   → NEEDS_MORE_DATA
    │
    ▼  (승인된 것만)
    │
POST /api/v1/saas-setup/register/{id}
    │  Runtime에 등록 (recurring_task / event_based / deadline / record)
    │  source_trace 유지, audit_log 유지, rollback 가능
    ▼
운영 시스템
```

### 4-3. Admin 법령검토 플로우

```
Residual 111,142건
    │
    ▼
Pattern Mining (12 패턴 추출)
    │  "대통령령으로 정하는" 5,866회
    │  "필요한 경우" 1,199회
    │  "필요한 조치" 943회
    │  "기준에 적합" 814회 ...
    ▼
Cluster Build (9 클러스터)
    │  UNRESOLVED_REFERENCE / ABSTRACT_REQUIREMENT / BROAD_OBLIGATION
    ▼
Registry Gap Detect (11건)
    │  token_family_registry에 없는 토큰
    ▼
Admin Review Queue (229건)
    ├── CLUSTER_REVIEW: 9건 (occurrence ~10,005)
    ├── REGISTRY_EXPANSION_REVIEW: 11건 (occurrence ~10,019)
    ├── PENALTY_MAPPING_REVIEW: 9건
    └── RESIDUAL_REVIEW: 200건 (Compatibility 충돌)
    │
    ▼  (사람 검토 10종 액션)
    │
    ├─ APPROVE_RULE_CANDIDATE      → Rule 승인
    ├─ REJECT_NON_ACTIONABLE       → 거절
    ├─ KEEP_AS_UNKNOWN             → UNKNOWN 유지
    ├─ MAP_TO_EXISTING_FAMILY      → 기존 Family 연결
    ├─ CREATE_NEW_FAMILY           → 신규 Family 생성
    ├─ ADD_REGISTRY_TOKEN          → Registry 토큰 추가
    ├─ SPLIT_COMPOUND              → 복합 항목 분리
    ├─ ESCALATE_TO_LEGAL_EXPERT    → 법무 전문가 검토
    ├─ REQUEST_MORE_SOURCE         → 추가 데이터 요청
    └─ MERGE_WITH_EXISTING         → 기존 항목 병합
    │
    ▼
Registry Update + Versioning + Audit Log
    │
    ▼
Reprocessing Queue → Candidate 재생성
```

### 4-4. 오염 방지 플로우

```
기존 (v5.38.0 이전)
┌────────────────────────────────────┐
│ law_rule_generator (AI rule 생성)     │
│ legal_engine* (AI 해석)               │
│ schedule_engine (AI 스케줄)            │ → 오염 발생
│ stage_1/2 (AI 의미절 분해)             │
└────────────────────────────────────┘
             ↓
정리 (v5.39.0)
┌────────────────────────────────────┐
│ TRUNCATE ~484K AI 오염 데이터          │
│ Archive 4개 → _legacy_contaminated    │
│ DROP ~30개 backup 테이블               │
└────────────────────────────────────┘
             ↓
신규 (v5.40.0)
┌────────────────────────────────────┐
│ Deterministic Compiler (rule-based)   │
│ 모든 출력: CANDIDATE                   │ → 오염 원천 차단
│ 사람 승인 전 registry 반영 금지        │
│ Audit + Versioning + Rollback         │
└────────────────────────────────────┘
```

---

## 5. DB 테이블 현황 (76+ 신규)

### Compiler Core (54+)

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
| compatibility_issue | 757 | 충돌 |
| executable_draft | 10,725 | 실행 초안 |
| draft_slot | 50,133 | Draft Slot |
| draft_condition_graph | 10,725 | 조건 그래프 |
| facility_applicability | 25,920 | 시설 적용 |
| task_candidate | 3,388 | Task |
| task_candidate_relation | 15,456 | Task 관계 |
| schedule_candidate | 1,159 | 스케줄 |
| compliance_package | 30 | 컴플라이언스 |
| compliance_review_queue | 1,737 | 검토 |
| law_version_hash | 35,412 | 법령 해시 |
| residual_candidate | 111,142 | 잔여 |
| penalty_candidate | 3,129 | 처벌 |
| penalty_obligation_relation | 7,511 | 처벌↔의무 |

### Residual Intelligence (12)

| 테이블 | 건수 |
|---|---|
| residuals | 111,142 |
| residual_failed_reasons | 111,434 |
| residual_patterns | 12 |
| residual_clusters | 9 |
| registry_gaps | 11 |
| review_queue | 20 |

### Admin Review (4)

| 테이블 | 건수 |
|---|---|
| admin_review_queue | 229 |
| admin_audit_logs | 1 |
| registry_versions | 0 |
| admin_reprocessing_queue | 0 |

### 진단/SaaS (6)

| 테이블 | 역할 | 영역 |
|---|---|---|
| diagnosis_session | 진단 세션 | 진단서비스 |
| diagnosis_candidate | 의무/금지/적용 후보 | 진단서비스 |
| diagnosis_penalty_link | 처벌 연결 | 진단서비스 |
| diagnosis_schedule_hint | 스케줄 힌트 | 경계 |
| saas_setup_candidate | 반복설정 후보 | SaaS |
| saas_registration_log | Runtime 등록 이력 | SaaS |

---

## 6. API 엔드포인트 (50개 신규)

### Compiler Core (7) — `/api/v1/compiler`
| Method | Path | 용도 |
|---|---|---|
| POST | /evaluate-facility | 핵심: 시설 평가 |
| GET | /task-candidates/{fid} | Task 후보 |
| GET | /schedule-candidates/{fid} | Schedule 후보 |
| GET | /penalty-map/{fid} | Penalty 맵 |
| GET | /source-trace/{part_id} | 원문 추적 |
| GET | /coverage-summary | 커버리지 |
| GET | /health | 엔진 상태 |

### Residual Intelligence (22) — `/api/v1/residual-intelligence`
| Method | Path | 용도 |
|---|---|---|
| POST | /patterns/mine | 패턴 추출 |
| POST | /clusters/build | 클러스터 생성 |
| POST | /registry-gaps/detect | Gap 감지 |
| GET | /dashboard | 대시보드 |
| GET | /review-queue | 검토 큐 |
| POST | /review-queue/{id}/decision | 결정 |
| ... | ... | +16 API |

### Admin Review (12) — `/api/v1/admin`
| Method | Path | 용도 |
|---|---|---|
| GET | /review-queue | 검토 목록 |
| GET | /review-queue/{id} | 검토 상세 |
| POST | /review/{id}/approve | 승인 (10종 액션) |
| POST | /review/{id}/reject | 거절 |
| POST | /family/create | Family 생성 |
| POST | /registry/add-token | Token 추가 |
| POST | /reprocessing/trigger | 재처리 |
| POST | /rollback | 롤백 |
| GET | /audit-logs | 감사 로그 |
| ... | ... | +3 API |

### 법령진단서비스 (3) — `/api/v1/diagnosis-engine`
| Method | Path | 용도 |
|---|---|---|
| POST | /evaluate | 진단 실행 |
| GET | /session/{id} | 세션 상세 |
| GET | /sessions | 세션 목록 |

### SaaS 반복설정 (6) — `/api/v1/saas-setup`
| Method | Path | 용도 |
|---|---|---|
| POST | /extract/{session_id} | 후보 추출 |
| GET | /candidates | 후보 목록 |
| POST | /approve/{id} | 승인 |
| POST | /reject/{id} | 거절 |
| POST | /needs-data/{id} | 추가데이터 |
| POST | /register/{id} | Runtime 등록 |

---

## 7. Admin UI

**URL:** `admin.taieng.co.kr/html/horizontal-menu-template/engine-legal-review.html`

**메뉴:** 엔진설정 > 📜 법령검토

**기능:**
- 통계 카드 4개 (총/승인/신규/거절)
- 필터 (유형 4종 × 상태 5종)
- 검토 목록 테이블 (229건)
- 빠른 승인/거절 버튼
- 상세 모달 (원문 + 10종 액션 버튼)
- 엔진 상태 (Compiler Core 8테이블 건수)
- 감사 로그 모달

---

## 8. PENDING 작업

| 우선순위 | 작업 | 상태 |
|---|---|---|
| HIGH | Admin Review Queue 229건 사람 검토 실행 | 대기 |
| HIGH | 검토 완료 후 Reprocessing → Coverage 향상 확인 | 대기 |
| MED | `_legacy_contaminated` 4개 테이블 → 프론트엔드 참조 확인 후 DROP | 대기 |
| MED | Runtime 코드에서 삭제된 테이블 참조 제거 (25+ Legacy 라우터) | 대기 |
| LOW | dev↔main 브랜치 정리 (diverged 상태) | 대기 |

---

## 9. 핵심 문장

- 교체 대상은 Runtime이 아니다. 법령 의미판단 Core다.
- 애매함은 제거 대상이 아니라 관리 대상이다.
- 사람이 검토한 법령만 엔진에 추가된다.
- 법령진단은 결과 출력까지. SaaS는 승인 후 운영설정까지.
- 모든 결과는 Truth가 아니라 Candidate다.
