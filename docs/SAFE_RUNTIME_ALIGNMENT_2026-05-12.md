# SAFE ↔ Runtime Alignment Summary
## 2026-05-12

### 매핑 상태
- FULLY_MAPPED: 7개 (법령판정/점검항목/문서서식/문서 lifecycle/일정/법령진단/증빙)
- PARTIALLY_MAPPED: 4개 (점검수행/설비/알림/시정조치)
- LEGACY_ONLY: 9개 (사업장/교육/TBM/위험성평가/건설/결제/작업자앱/수선/관리자)
- RUNTIME_ONLY: 7개 (Activation/Conflict/Drift/Snapshot/ReEval/Simulation/Penalty)

### 즉시 전환 가능
1. 일정 관리 (기존 0건, Runtime schedule_instance)
2. 문서 관리 (기존 0건, Runtime document_data)
3. 법령 진단 (Runtime diagnosis_engine 배포 완료)

### 누락 CRITICAL
1. 실제 알림/Push 연동
2. 작업자 모바일 점검 UI

### 다음 백엔드 우선순위
1. inspection_sets ↔ runtime_checklist_item 매핑 API
2. Runtime event → notification_queue 브릿지
3. equipment_assets ↔ facility_equipment 동기화
4. generated_document PDF 실제 렌더링

### 다음 프론트 우선순위
1. Review Queue Console
2. 점검 수행 화면 Runtime 전환
3. Runtime Dashboard
4. 문서 작성 동적 폼
