# WP-DATA-ARCH-04D · WRITER CUTOVER PLAN (RUNBOOK)  — EXECUTION HOLD

```
UNIT = WP-DATA-ARCH-04D  safety_inspections.factory_id companion + writer cutover
MODE = RUNBOOK ONLY · 이번 제출 실행 금지 · 각 단계 실행은 04D EXECUTION gate 승인 후
전제 = factory_id nullable · linked backfill DETERMINISTIC(1/1) · standalone NULL 유지 · 2 writer patch = PREPARED
```

## WRITE CONTROL 대상 (WRITE OFF 시 정지/차단할 safety_inspections INSERT creator)
```
- POST /worker-check/submit           (worker_check.submit_check INSERT 차단)
- POST /inspection/start/{ws_id}      (inspection_checklist.start_inspection INSERT 차단)
주의: /inspection/result/{id}/items · /complete 는 safety_inspections INSERT 아님(UPDATE/results) → WRITE OFF 관심 밖.
       기존 legacy standalone(assignment_id NULL) 행은 어떤 단계에서도 수정/삭제/backfill 금지.
```

## 실행 순서 (승인 후)
```
1. FRESH HEAD / DB PRE-state 재확인
   - tai-api/main HEAD = (04D artifact commit 후 HEAD)
   - safety_inspections.factory_id absent · row split(linked 1 / standalone 1) · linked determinism 1/1 재확인 · lock/blocker NONE
2. WRITE OFF  (위 2 creator INSERT 경로 정지; 신규 inspection 유입 차단)
   - 검증: WRITE OFF 이후 신규 safety_inspections row 증가 0
3. ADD factory_id nullable  (UP artifact PRECHECK 통과 후 ADD)
4. LINKED-SUBSET BACKFILL   (UP artifact UPDATE; standalone 미대상)
5. POST-BACKFILL VALIDATION (fail-closed; 하나라도 실패 시 rollback)
   - linked(assignment NOT NULL) factory NULL = 0
   - linked mismatch(factory != parent) = 0
   - standalone(assignment NULL) factory NOT NULL = 0   (NULL 유지 강제)
   - safety_inspections row count = PRE 동일 (2)
6. PATCHED 2 WRITERS DEPLOY  (WRITER_PATCH_DRAFTS: worker_check.py · inspection_checklist.py)
   - schema-first 준수: 4·5 완료(NEW DB) 이후에만 deploy
7. WRITER SMOKE (non-mutating; production business row 임의 생성 금지)
   - production synthetic mutation smoke 금지.
   - PRE-DEPLOY : targeted unit/integration test (전용 fixture만; 04D용 신규 production 데이터 생성 금지)
   - POST-DEPLOY: /health 200 · deployed SHA == expected · route import/startup 정상 · static writer contract 확인
8. RECONCILIATION (DB owner, linked only) — deploy 성공 후 1회
   fail-closed PRECHECK: linked broken parent=0 · linked parent factory NULL=0 (>0 이면 UPDATE 금지/STOP)
   UPDATE public.safety_inspections si SET factory_id = ws.factory_id
     FROM public.work_schedules ws
    WHERE si.assignment_id = ws.id AND si.factory_id IS NULL;
   -- OLD writer window 에서 생긴 LINKED NULL companion 만 보정.
   -- standalone(assignment_id NULL)은 WHERE(si.assignment_id=ws.id) 미매칭 → 영구 NULL 유지(정상). 추론 금지.
9. POST-RECONCILIATION VERIFY (fail-closed)
   - linked(assignment NOT NULL) factory NULL = 0
   - linked mismatch(factory != parent) = 0
   - standalone(assignment NULL) factory NOT NULL = 0
   - safety_inspections row count = PRE 동일 (2) · W1(04C) cron active=false
10. WRITE ON  (2 creator 재개)
    - 이유: OLD writer window 의 linked NULL gap 을 8·9 에서 먼저 닫은 뒤에만 writer 재개 (reconciliation 전 WRITE ON 금지)
11. NATURAL WRITE OBSERVATION
    - WRITE ON 후 최초 자연발생 신규 inspection write 관찰 → factory_id == parent(assignment_id의 ws.factory_id) 검증
    - 즉시 자연 write 없으면 production synthetic 업무행 만들지 않음
```

## RECONCILIATION 상세 (실행순서 §8·§9와 동일 — 참조용)
```
= 위 실행순서 8·9 로 통합됨 (deploy → smoke/health → RECONCILIATION → POST-RECONCILIATION VERIFY → WRITE ON → natural).
= reconciliation 은 linked only. standalone(assignment_id NULL)은 영구 NULL 유지.
```

## ROLLBACK
```
ROLLBACK-A (6 이전, writer deploy 전) = DOWN(DROP COLUMN factory_id) 단독 → PRE schema 복원 (구 writer factory_id 미참조라 안전)
ROLLBACK-B (6 이후, patched writer deploy 후) = WRITE OFF → writer CODE ROLLBACK(worker_check/inspection_checklist git revert)
                                              → DOWN(DROP COLUMN) → old behavior 검증 → WRITE ON
  ※ code rollback 없이 컬럼부터 DROP 금지.
```

## TARGETED TESTS (pytest, 결과 원문 제출 — Cursor/CI)
```
W1 worker_check.submit_check:
  T1  schedule_id 직접 → INSERT payload factory_id == parent(schedule) factory_id
  T2  assignment_id → work_assignments→schedule_id 해소 → INSERT factory_id == parent
  T3  parent work_schedules 없음 → HTTP 409 · safety_inspections INSERT 호출 = 0
  T4  parent factory_id NULL → HTTP 409 · INSERT 호출 = 0
  T5  body.factory_id 가 parent와 다른 값 → 무시(parent 값 사용), payload factory_id == parent
  T6  schedule_ref 미확정(schedule_id/assignment_id 모두 없음/해소불가) → HTTP 409 · standalone 생성 안 함
W2 inspection_checklist.start_inspection:
  T7  정상 → safety_inspections INSERT payload {assignment_id=ws_id, factory_id == parent}
  T8  parent factory_id NULL → HTTP 409 · work_schedules status UPDATE 호출 = 0 · safety_inspections INSERT = 0
  T9  auth/ownership(_ensure_ws_own) 무회귀 (타사 ws → 404)
  T10 정상 start 흐름 무회귀 (status in_progress 전이)
전용 fixture만 사용. production test data 신규 생성 금지.
```

## 경계 (04D가 의미하는 것 / 아닌 것)
```
04D 완료 = safety_inspections child companion READY (+ 2 writer live, standalone NULL 정책 유지)
04D 미의미 = composite FK ready(아님) · work_schedules HASH executed(아님)
후속: 04C(wa)+04D(si) + equipment_checkins 재확인 → WS HASH migration maintenance gate → child composite FK rewire.
이번 04D는 NOT NULL · single/composite FK · MATCH FULL · pair CHECK · HASH · tenant filter 를 건드리지 않는다.
submitted_by writer(CD5-1) · worker_check inspector_id roster 위험 = 별도 dependency (04D 미포함).
```
