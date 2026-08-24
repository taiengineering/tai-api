# WP-DATA-ARCH-04C · WRITER CUTOVER PLAN (RUNBOOK)  — EXECUTION HOLD

```
UNIT = WP-DATA-ARCH-04C  work_assignments.factory_id companion + writer cutover
MODE = RUNBOOK ONLY · 이번 제출 실행 금지 · 각 단계 실행은 04C EXECUTION gate 승인 후
전제 = factory_id nullable · backfill FULLY DETERMINISTIC (5991/5991) · 3 writer patch = PREPARED
```

## WRITE CONTROL 대상 (WRITE OFF 시 정지/차단할 3 creator)
```
- public.generate_daily_assignments()      (cron/스케줄러 실행 차단)
- POST /work-schedules/auto-assign         (legal_engine_patch.auto_assign 차단)
- work_schedules assignment sync INSERT     (batch-update / bulk-assign / PATCH → _apply_one_update INSERT 경로 차단)
주의: _apply_one_update의 UPDATE(기존 assignment 담당자 변경)·CANCELLED 경로는 factory 무관. INSERT 신규생성만이 WRITE OFF 관심대상.
```

## 실행 순서 (승인 후)
```
1. FRESH HEAD / DB PRE-state 재확인
   - tai-api/main HEAD = (04C artifact commit 후 HEAD)
   - work_assignments.factory_id absent · backfill determinism 5991/5991 재확인 · lock/blocker NONE

2. WRITE OFF
   - 위 3 creator INSERT 경로 정지 (신규 assignment 유입 차단)
   - 검증: WRITE OFF 이후 신규 work_assignments row 증가 0

3. ADD factory_id nullable  (UP artifact PRECHECK 통과 후 ADD)

4. DETERMINISTIC BACKFILL  (UP artifact UPDATE)

5. POST-BACKFILL VALIDATION (fail-closed; 하나라도 실패 시 rollback)
   - factory_id NULL 전량 = 0
   - factory_id ≠ parent work_schedules.factory_id = 0
   - work_assignments row count = PRE 동일 (5991)

6. PATCHED 3 WRITERS DEPLOY  (WRITER_PATCH_DRAFTS: W1 함수교체 · W2/W3 코드 deploy)
   - schema-first 준수: 4·5 완료(NEW DB) 이후에만 deploy

7. WRITER SMOKE (production business row 임의 생성 금지)
   [W1] ROLLBACK-ONLY TRANSACTION (persistent 생성 금지 — active schedule 66개라 그냥 호출 시 실업무행 최대 66개 생성됨)
        BEGIN
          PRE work_assignments row count capture
          SELECT generate_daily_assignments();
          생성 test rows 내: factory_id IS NULL = 0 · factory_id ≠ parent factory_id = 0
          생성 예상/실제 row count 확인
        ROLLBACK
        FINAL: persistent work_assignments delta = 0
        ※ pg_cron job (schedule '10 0 * * *', SELECT generate_daily_assignments(), active=false) — cutover 때 active=false 재확인
   [W2/W3] production synthetic mutation smoke 금지
        PRE-DEPLOY : targeted unit/integration test (전용 fixture만; 04C용 신규 production test data 생성 금지)
        POST-DEPLOY: /health 200 · deployed SHA 확인 · route import/startup 정상 · static writer contract 확인
        WRITE ON 후: 최초 자연발생 assignment write를 즉시 관찰 → factory_id == parent factory_id 검증
   [공통] 기존 UPDATE(담당자 변경)·CANCELLED 경로 무회귀 · /health 200

8. WRITE ON
   - 3 creator 재개 · 이후 신규 row는 항상 factory_id 기록됨을 표본 확인
```

## ROLLBACK
```
ROLLBACK-A (6 이전, writer deploy 전)
  = DOWN(DROP COLUMN factory_id) 단독 → PRE schema 복원 (구 writer는 factory_id 미참조라 안전)

ROLLBACK-B (6 이후, patched writer deploy 후)
  = WRITE OFF
    → patched writer CODE ROLLBACK (W1 함수 원복 · W2/W3 git revert)
    → DOWN(DROP COLUMN factory_id)
    → old behavior 검증 (구 INSERT 정상)
    → WRITE ON
  ※ code rollback 없이 컬럼부터 DROP 금지.
```

## 경계 (04C가 의미하는 것 / 아닌 것)
```
04C 완료 = work_assignments child companion READY (+ writers live)
04C 미의미 = work_schedules HASH migration READY (아님)
후속 의존: 04C → 04D(safety_inspections.factory_id + writers) → equipment_checkins 재확인
          → WS HASH migration maintenance gate → child composite FK rewire
이번 04C는 UNIQUE(schedule_id,scheduled_date) / composite FK / NOT NULL / HASH 를 건드리지 않는다.
```
