# TAI Phase 2 — Obligation Management Runtimeization
## 2026-05-12 | Session Handoff

---

## 완료 항목

### 신규 DB 테이블 (7개)
| 테이블 | 목적 | CHECK 제약 |
|--------|------|------------|
| runtime_obligation_execution_type | 의무 실행 유형 10종 | execution_type 10값 제한 |
| runtime_obligation_registry | Runtime 의무 Registry | activation_status 5값, execution_type 10값, AUTO_ACTIVE/AUTO_APPROVED/FINAL 금지, source_trace 금지 패턴 |
| runtime_obligation_assignment | 의무별 담당자 지정 | review_status 3값, source_trace 금지 패턴 |
| runtime_obligation_schedule_policy | 의무별 반복주기 정책 | schedule_type 3값, repeat_unit 5값, RECURRING→cycle 필수, source_trace 금지 패턴 |
| runtime_operational_work_order | 작업자 앱 Operational Work | work_status 8값, execution_type 10값, AUTO 금지, source_trace 금지 패턴 |
| runtime_work_order_resource_link | Work Order ↔ Runtime 자원 연결 | resource_type 4값, link_status 3값 |
| runtime_work_order_review | Review Queue 감사 이력 | review_action 4값, new_status 5값, AUTO 금지 |

### 트리거/함수 (2개)
| 함수 | 목적 |
|------|------|
| fn_validate_work_order_prerequisites | assignment(APPROVED) + schedule_policy 존재 + execution_type 일치 검증 |
| fn_validate_reviewer_not_assignee | reviewer ≠ assigned_user 검증 + work_order status 자동 갱신 |

### FK 연결
- runtime_obligation_registry → rule_candidate, task_candidate
- runtime_obligation_assignment → runtime_obligation_registry
- runtime_obligation_schedule_policy → runtime_obligation_registry
- runtime_operational_work_order → registry, assignment, schedule_policy, document_data
- runtime_work_order_resource_link → work_order
- runtime_work_order_review → work_order

### Bridge API (routers/obligation_bridge.py)
- GET /bridge/obligations
- GET /bridge/obligations/{id}
- GET/POST /bridge/obligation-assignments
- GET/POST /bridge/obligation-schedule-policies
- GET /bridge/work-orders
- GET /bridge/my-work-orders
- GET /bridge/obligation-status

### CHECK 제약조건 총 88개

### 무결성 검증
- forbidden patterns (DB): **전체 0건**
- forbidden patterns (code): 실행 로직 **0건**
- operational integrity audit: **7항목 전부 PASS**

---

## Runtime Workflow Flow

```
rule_candidate
  ↓ (FK)
task_candidate
  ↓ (FK)
runtime_obligation_registry (activation_status: CANDIDATE → NEEDS_REVIEW → ACTIVE)
  ↓
runtime_obligation_assignment (안전관리자 직접 지정, PENDING → APPROVED)
  ↓
runtime_obligation_schedule_policy (RECURRING/ONE_TIME/EVENT_DRIVEN)
  ↓ (트리거: assignment APPROVED + schedule 존재 검증)
runtime_operational_work_order (GENERATED → ASSIGNED → IN_PROGRESS → SUBMITTED → REVIEW_PENDING → APPROVED)
  ↓
runtime_work_order_review (APPROVE/REJECT/REOPEN/ESCALATE, 자기승인 차단)
```

---

## PENDING 작업 (다음 세션)

### Phase 3 백엔드
- [ ] legal_engine write freeze
- [ ] Runtime event → notification_queue bridge
- [ ] equipment_assets ↔ facility_equipment 동기화
- [ ] generated_document Gotenberg PDF 렌더링

### 프론트엔드 Runtime 전환
- [ ] Review Queue Console (runtime_work_order_review 기반)
- [ ] 점검 수행 화면 (runtime_operational_work_order + checklist_item)
- [ ] Runtime Dashboard (obligation_registry 통계)
- [ ] 문서 작성 동적 폼 (runtime_form_schema 기반)
- [ ] 일정 캘린더 (schedule_policy 기반)

### 데이터 시딩
- [ ] obligation_form_mapping 11건 → runtime_obligation_registry 매핑
- [ ] task_candidate 3,388건 → obligation_registry 연결
- [ ] execution_type 분류 (INSPECTION/TRAINING/REPORTING 등)

### 번외
- [ ] Supabase Storage 이전 (diagrams 버킷)
- [ ] Railway → Google 서울 검토
