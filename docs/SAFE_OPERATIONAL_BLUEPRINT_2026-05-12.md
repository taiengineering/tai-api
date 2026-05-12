# SAFE Operational Blueprint Summary
## 2026-05-12

### Migration Phase
1. Phase 1: 일정+문서+법령진단 즉시 전환 (기존 0건, LOW risk)
2. Phase 2: 점검항목 매핑 (inspection_sets↔checklist)
3. Phase 3: 점검수행 Runtime 전환 + Review Queue UI
4. Phase 4: 알림 연동 + 작업자앱 wrapper
5. Phase 5: Legacy AI 엔진 비활성화

### Hidden Logic CRITICAL
- legal_engine.py (AI 판정) → compiler_core로 교체
- diagnosis_autofill.py (AI 자동채움) → 제거
- schedule_engine.py (AI 일정) → schedule_instance로 교체

### Backend 우선순위
1. inspection_sets ↔ runtime_checklist_item 매핑
2. Runtime event → notification_queue bridge
3. equipment ↔ facility_equipment 동기화
4. PDF Gotenberg 렌더링

### Frontend 우선순위
1. Review Queue Console (신규 필수)
2. 점검 수행 Runtime 전환
3. Runtime Dashboard (신규)
4. 문서 작성 동적 폼
5. 일정 캘린더
