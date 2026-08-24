# WP-DATA-ARCH-04C · Work Assignment Factory Companion · STATIC VERIFICATION

```
UNIT   = WP-DATA-ARCH-04C  work_assignments.factory_id companion + writer cutover 준비
LEVEL  = A (backfill + writer cutover dependency)
MODE   = READ ONLY AUDIT + ARTIFACT AUTHORING · DB/DDL/DML/CODE/DEPLOY MUTATION = 0 · COMMIT = HOLD
SOURCE API = taiengineering/tai-api @ cfd87aff (code = e1506aa4 baseline, 04A/04B는 docs만)
CANONICAL PLAN = taiengineering/taieng @ 65f2e5590d6881577d31afd64af23787493df19a (S1-6 / B2-4 / WS-1·WS-2)
```

purpose: factory_id = work_schedules parent relation의 **companion** (신규 tenant authority 아님). 향후 HASH migration child FK 준비.

## 1. PRE-STATE (직독 @ vwlahtguyggrhvslabax)
```
work_assignments
  columns (12) = id(uuid,NN) · schedule_id(uuid) · asset_id(uuid) · assigned_user_id(uuid)
                 · scheduled_date(date) · status_code(text,'READY') · created_at(timestamp,now)
                 · inspection_set_id(uuid) · due_date(date) · overdue_level(smallint,NN,0)
                 · last_reminded_at(tz) · resolved_at(tz)
  PK  = work_assignments_pkey (id)
  FK  = schedule_id→work_schedules(id) · asset_id→equipment_assets(id) · assigned_user_id→users(id)
  UNIQUE/CHECK = 없음  (UNIQUE(schedule_id,scheduled_date) 미존재 = WA 전환 대상, 04C 범위 아님)
  indexes  = work_assignments_pkey · idx_wa_due_date · idx_wa_overdue_level
  policies = anon(select/insert/update/delete) · authenticated(ALL) · service_role_full (6)
  triggers = (none) · owner = postgres · RLS enabled = true
  factory_id column exists = 0  (safe to ADD)
  target FK-name/constraint collision = N/A (04C는 컬럼만; composite FK는 후행 HASH gate)
```

## 2. DETERMINISTIC BACKFILL PROOF (실측 count)
```
canonical source = wa.schedule_id → work_schedules.id → work_schedules.factory_id (유일)
total rows                         = 5991
schedule_id IS NULL                = 0
scheduled_date IS NULL             = 0
broken parent (schedule_id 있으나 ws 없음) = 0
parent work_schedules.factory_id NULL      = 0
한 row 다중 factory 후보              = 0
DETERMINISTIC resolvable            = 5991 / 5991  (100%)
UNRESOLVED                          = 0
판정 = FULLY DETERMINISTIC · fail-closed 대상 행 0 · 임의 factory 추론 불필요
```

## 3. UP — static design check
```
순서 = PRECHECK(fail-closed) → ADD COLUMN → deterministic UPDATE → POST VALIDATION(fail-closed)
PRECHECK  = schedule_id NULL 존재 → RAISE [★교정] / broken parent>0 → RAISE / parent factory NULL>0 → RAISE  (ADD/UPDATE 이전 중단)
ADD       = factory_id uuid NULL  (nullable, NOT NULL 아님 ✓)
BACKFILL  = UPDATE ... SET factory_id = ws.factory_id FROM work_schedules ws WHERE wa.schedule_id=ws.id AND wa.factory_id IS NULL
            (canonical parent source only ✓ · request/user/asset 추론 없음 ✓)
POST      = factory_id NULL 전량>0 → RAISE [★교정: schedule_id NULL은 PRECHECK 차단] / factory_id ≠ parent >0 → RAISE  (rollback)
atomicity = 단일 transaction (실패 시 전량 rollback, 부분성공 없음)
04C 미포함 = NOT NULL · composite FK · MATCH FULL · pair CHECK · HASH migration · tenant filter ✓
```

## 4. DOWN — static design check
```
statement = DROP COLUMN factory_id (단일)
ROLLBACK-A (writer deploy 전) = DOWN 단독 안전
ROLLBACK-B (writer deploy 후) = WRITE OFF → writer CODE ROLLBACK → DROP COLUMN → 검증 → WRITE ON
                                (code rollback 없이 컬럼부터 DROP 금지)
```

## 5. Compatibility (WP-03 matrix 상속)
```
factory_id nullable additive:
  OLD DB + OLD CODE = SAFE
  OLD DB + NEW CODE = BREAKS (스키마 先)
  NEW DB + OLD CODE = SAFE  (구 3 creator 미기입 → NULL. 단, backfill 후 구 writer가 계속 INSERT하면 새 NULL row 발생)
  NEW DB + NEW CODE = SAFE
RULE = SCHEMA FIRST, 그러나 backfill 무결성 유지 위해 production은 단순 schema-first 아님:
  WRITE CONTROL → SCHEMA → BACKFILL → PATCHED WRITER DEPLOY → VALIDATE → WRITE ON  (§CUTOVER)
```

## 6. WRITER INVENTORY (WP-03 확정 3 creator, 현 HEAD 본문 재확인)
```
W1 public.generate_daily_assignments() [DB func, live 직독]
   INSERT (id,schedule_id,asset_id,assigned_user_id,scheduled_date,status_code)
     SELECT gen_random_uuid(), ws.id, ws.asset_id, ws.assigned_user_id, current_date, 'READY'
     FROM work_schedules ws WHERE ws.active_yn=true
   factory source = ws.factory_id (동일 SELECT) · idempotency = 없음(plain) · auth = cron/no-auth
W2 routers/legal_engine_patch.py :: auto_assign_schedules  [blob 7f8f67b7]
   schedule 조회가 이미 factory_id select → assign_rows dict INSERT {schedule_id, assigned_user_id, scheduled_date, status_code, created_at}
   factory source = s["factory_id"] · idempotency = 없음(batch insert) · auth = 없음
W3 routers/work_schedules.py :: _apply_one_update  [blob 16b8d9c1]
   assign 변경 시: parent factory_id PRE-READ → NULL이면 schedule UPDATE 전 HTTP 409 → PASS 후 schedule UPDATE → 존재체크 후 신규 INSERT에 factory_id 주입
   factory source = UPDATE 직전 동일 schedule PRE-READ(부모 행) · 존재체크 가드(비원자) · auth = get_current_user+scope · 부분반영 없음
결론 = 3 creator 전부 factory_id 미기록. 전부 parent schedule에서 factory_id 획득(deterministic). request/user 신뢰 금지.
[★교정] parent factory_id NULL fail-closed 강제 = W1 RAISE EXCEPTION · W2 HTTP 409(side-effect 전) · W3 HTTP 409(schedule UPDATE 전 PRE-READ).
        (work_schedules.factory_id nullable=YES라 구조적 방어를 writer에 둠 — 오늘 NULL 0건이나 미래 방어)
W3 fail-closed 순서 = parent factory_id PRE-READ → NULL이면 schedule UPDATE 전 HTTP 409 → PASS 후 schedule UPDATE → assignment sync (부분반영 없음).
```

## 7. WA IDEMPOTENCY 경계 (준비만, deploy 아님)
```
현재 = generate_daily(plain) · auto_assign(plain batch) · _apply_one_update(존재가드 후 insert) — 3자 모두 ON CONFLICT 없음
04C  = factory_id write patch 준비(WA-0 artifact). ON CONFLICT(schedule_id,scheduled_date)는 UNIQUE arbiter 부재로 지금 deploy 불가.
PREPARED ≠ DEPLOYED. UNIQUE 적용은 별도 WA maintenance atomic transition(MIGRATION_DEPENDENCY §2). factory patch와 timing 분리.
```

## 8. STATUS / STOP GATE
```
PRE-STATE                = GROUNDED
BACKFILL DETERMINISM     = PROVEN (5991/5991, UNRESOLVED 0)
UP STATIC                = PASS
DOWN STATIC              = PASS
3 WRITER PATCH ARTIFACTS = COMPLETE (WRITER_PATCH_DRAFTS) · fail-closed 강제 [★교정] · W3 순서 PRE-READ 교정
CUTOVER RUNBOOK          = COMPLETE (WRITER_CUTOVER_PLAN) · W1 smoke=ROLLBACK-ONLY tx, W2/W3=non-mutating(자연발생 관찰) [★교정: production 실업무행 생성 금지]
COMPATIBILITY            = CLOSED
ROLLBACK                 = CLOSED (A/B)
DB/DML/CODE/DEPLOY MUTATION = 0 · COMMIT = HOLD
RESULT = READY FOR 04C EXECUTION
HOLD = production apply(ADD+backfill) · writer deploy · UNIQUE transition · HASH migration
```
