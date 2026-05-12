# Runtime Ownership Transition Blueprint
## 2026-05-12

### Ownership 분류
- **Runtime 소유 10개:** rule/task/schedule/document/review/archive/evidence/conflict/penalty/diagnosis
- **Legacy 유지 4개:** 교육/TBM/위험성평가/결제
- **Bridge 2개:** 작업자앱/알림
- **Hybrid 1개:** 관리자통계

### Legacy Mutation Freeze 순서
- Phase 1: schedule_engine + diagnosis_autofill + work_schedules + documents
- Phase 2: legal_engine + inspection_recommendation
- Phase 3: risk_score_engine + law_rule_generator

### Bridge 전략
- inspection_sets → RUNTIME_ONLY_WRITE
- worker_app → SINGLE_DIRECTION_SYNC (작업자→Runtime)
- notification → SINGLE_DIRECTION_SYNC (Runtime→알림)

### Phase 1 즉시 실행 가능
- work_schedules 0건, documents 0건 (리스크 LOW)
- Runtime API 이미 배포 완료 (v5.40～v5.44)
- Legacy 3개 비활성화 + Frontend 3개 전환 대기

### 핵심 원잙
- UI는 유지. 내부 엔진만 Runtime으로 치환
- Runtime 도메인에서 Legacy는 읽기만 허용, 쓰기 절대 금지
- 모든 승인: Runtime lifecycle 경유 필수
