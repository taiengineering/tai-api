# WP-PARTITION-02B-R1 · Work Schedules HASH Migration · CURRENT-STATE REBASE STATIC VERIFICATION

```
UNIT   = WP-PARTITION-02B-R1  work_schedules HASH migration package current-state rebase
LEVEL  = A (HASH-migration execution readiness; rebase of 20260822 REV-3)
MODE   = READ ONLY AUDIT + ARTIFACT AUTHORING · DB/DDL/DML/CODE/DEPLOY MUTATION = 0 · COMMIT = HOLD
SOURCE API HEAD = 6874bb85f5a9519d0f3c052f31492873a1a388bd (04E deployed)
CANONICAL PHYSICAL DESIGN = WORK_SCHEDULES_PARTITION_DESIGN_FINAL_v1 (설계 재검토 금지)
OLD PACKAGE = docs/sql/20260822_work_schedules_partition_up.sql / _down.sql (DESIGN SOURCE ONLY · DO NOT EXECUTE AS-IS)
```

목적: HASH 물리설계는 불변. 2026-08-22 package 를 04C/04D/04E LIVE 현재 상태에 rebase 하여 실제 실행 가능한 최종 package 생성.

## 1. CURRENT PRE-STATE (직독 @ vwlahtguyggrhvslabax · PG 17.6 · 2026-08-24 fresh)
```
work_schedules
  rows=66 · columns=37 · factory_id NULL=0 · distinct factory=4 · duplicate target(set,planned,factory)=0
  set/factory mismatch=0 · constraints=7 · CHECK=0 · indexes=12 · policies=6 · user triggers=0
  owner=postgres · RLS enabled=true forced=false · relkind='r'(regular) · comments=26
  PK=work_schedules_pkey(id) · UNIQUE idx=uq_work_schedules_inspection_set_planned_date
work_assignments
  rows=5991 · factory companion LIVE(04C) · linked factory NULL=0 · mismatch=0 · schedule NULL=0
  factory_id: uuid · nullable · comment=NULL
  단일 FK: work_assignments_schedule_id_fkey (schedule_id→work_schedules.id)
safety_inspections
  rows=2 · linked(assignment NOT NULL)=1 · legacy standalone(assignment NULL)=1
  linked factory NULL=0 · linked mismatch=0 · partial pair(한쪽만 NULL)=0 · factory companion LIVE(04D)
  factory_id: uuid · nullable · comment=NULL
  단일 FK: safety_inspections_assignment_id_fkey (assignment_id→work_schedules.id)
equipment_checkins
  rows=0 · cross-factory=0 · factory companion 이미 존재(04E writer LIVE)
  direct anon INSERT path=OPEN (composite FK 가 봉쇄; LOCK 이후 precheck authoritative)
  단일 FK: equipment_checkins_schedule_id_fkey (schedule_id→work_schedules.id ON DELETE SET NULL)
clean start: work_schedules_old / _new / _mig_* 부재
DEPENDENT MATVIEW (실측): public.dashboard_stats — owner postgres · populated=true · work_schedules dependency 3건
  · 정의 내 work_schedules 참조 12회(completed/overdue/upcoming 서브쿼리) · unique idx idx_dashboard_stats_singleton((1))
  · comment NULL · role grants 없음(owner-only) · refresh_dashboard_stats()(SECURITY DEFINER, 이름기반 REFRESH ... CONCURRENTLY→fallback)
DEFAULT ACL (실측): work_schedules 에 anon/authenticated/service_role = arwdDxt 전권(전부 grantable=NO) ·
  policies anon INSERT/SELECT/UPDATE/DELETE=true · authenticated ALL=true · service_role ALL=true
  → 신규 public table(스냅샷/파티션) 및 rename 된 old 가 동일 노출을 상속할 위험.
판정 = 데이터 전부 clean. blocker 는 데이터가 아니라 (1) OLD package 낡은 rollback 기준점 (2) matview OID 고착 (3) anchor 변조 가능성.
```

## 2. OLD PACKAGE DRIFT (직독 근거)
```
OLD UP §10:
  ALTER TABLE work_assignments   ADD COLUMN IF NOT EXISTS factory_id ...   ← 04C 가 이미 LIVE
  ALTER TABLE safety_inspections ADD COLUMN IF NOT EXISTS factory_id ...   ← 04D 가 이미 LIVE
  + companion COMMENT 부여 + UPDATE backfill
  → HASH 소유로 취급. 현재 상태와 충돌(이미 존재, comment=NULL).
OLD DOWN §6 (★치명적):
  ALTER TABLE work_assignments   DROP COLUMN IF EXISTS factory_id;
  ALTER TABLE safety_inspections DROP COLUMN IF EXISTS factory_id;
  → HASH rollback 이 04C/04D LIVE 자산을 삭제.
OLD DOWN §9-(8):
  factory_id 잔존 시 'DOWN FAIL' → 제거를 성공조건으로 강제 (반전 필요).
결론 = 설계 결함 아님. rollback 기준점이 04C/04D 이전이라 stale. → current-state rebase 필요.
```

## 3. REBASE 변경점 (물리설계 불변 · 3건)
```
REBASE-1 (UP §10 제거→PRECHECK):
  wa/si factory_id 를 ADD 하지 않는다. 존재/타입(uuid)/nullable/linked null 0/mismatch 0 을 §1 PRECHECK 로 assertion.
  companion COMMENT 도 새로 넣지 않는다(현재 NULL · 04C/04D-owned metadata 불변).
  backfill(UPDATE) 제거 — 이미 채워졌고 mismatch=0.
REBASE-2 (DOWN §6 제거→PRESERVE):
  wa/si factory_id DROP COLUMN 완전 제거. HASH rollback ≠ 04C/04D rollback. 컬럼+값 보존.
REBASE-3 (DOWN §9 반전):
  POSTCHECK 를 "factory_id 존재+보존+linked null 0" 성공조건으로 반전. 단일 FK 복원 + pair CHECK/composite FK 부재 확인.
불변(OLD 설계 그대로): PARTITION BY HASH(factory_id) MODULUS 16 · PK(id,factory_id) ·
  UNIQUE(inspection_set_id,planned_date,factory_id) · shadow→copy→37col full-row equality→FK rewire→swap ·
  16 partitions · outbound FK · comments/grants/policies/owner/RLS exact 재생성 · old table rollback anchor.

REV-2 CRITICAL 추가 (물리설계 불변 · execution correctness/security):
  CRITICAL-1 (matview OID rebind): dashboard_stats 는 relation OID 로 dependency 를 잡으므로 rename 만으로는 old 고착.
    UP §14-B 에서 swap 후 같은 tx 로 DROP→스냅샷 definition 재생성(NEW canonical 결합)+owner/index/comment/grants/WITH DATA 복원.
    DOWN §5 에서 partitioned DROP 전 matview DROP → old rename → restored 에 재결합. POSTCHECK 로 NEW OID 결합 검증.
  CRITICAL-2 (rollback anchor lockdown): _mig_* 전부 + work_schedules_old + p00~p15 에 대해
    REVOKE ALL FROM PUBLIC/anon/authenticated/service_role (생성/ rename 직후, 같은 tx). 특히 _mig_ws_data_snapshot(RLS 없는 전량 스냅샷)
    과 old anchor 의 direct write surface 차단. DOWN 은 old→canonical 후 _mig_ws_grants 스냅샷으로 PRE grants EXACT 재생성.
```

## 4. CHILD REWIRE TARGET (FIXED · canonical)
```
A. work_assignments   FK(schedule_id, factory_id)→ws(id,factory_id) MATCH FULL
                      CHECK((schedule_id IS NULL)=(factory_id IS NULL))   [전량 non-NULL → 항상 통과]
B. safety_inspections FK(assignment_id, factory_id)→ws(id,factory_id) MATCH FULL
                      CHECK((assignment_id IS NULL)=(factory_id IS NULL)) [legacy NULL pair 1건 통과]
C. equipment_checkins FK(schedule_id, factory_id)→ws(id,factory_id) MATCH SIMPLE
                      pair CHECK 없음 · ON DELETE SET NULL(schedule_id) [factory=asset authority 보존]
```

## 5. WRITE OFF MODEL (04D와 다름 — code deploy window 없음)
```
04C/04D/04E writer 전부 LIVE · HASH UP 은 신규 code deploy 동반 안 함(companion 이미 존재).
단일 transaction 안에서 4개 테이블 ACCESS EXCLUSIVE LOCK → composite FK 까지 생성 후 COMMIT.
  → equipment_checkins direct anon INSERT 도 migration 중 lock 대기 → COMMIT 후엔 composite FK LIVE
    = DB pair 검증 우회 window 없음.
전제 = UP 전체가 진짜 단일 transaction. executor 가 atomicity 보장 못하면 STOP.
운영상 application maintenance 병행. CODE DEPLOY=0 · Railway deployed SHA 전후 동일 expected.
```

## 6. PRECHECK (LOCK 이후 수행 — direct anon path 때문)
```
work_schedules: factory NULL 0 · set/factory mismatch 0 · target UNIQUE dup 0
work_assignments: broken parent 0 · linked factory NULL 0 · mismatch 0
safety_inspections: broken linked parent 0 · linked factory NULL 0 · linked mismatch 0 · partial pair 0
   legacy(assignment NULL & factory NULL) 허용
equipment_checkins: broken parent 0 · parent factory NULL 0 · cross-factory 0 (LOCK 이후 값만 authoritative)
+ (REBASE) wa/si factory_id 존재/uuid/nullable assertion (ADD 아님)
```

## 7. DOWN ROLLBACK TARGET
```
target = 2026-08-22 상태 아님. HASH 실행 직전(=04C/04D/04E 완료) 현재 상태.
work_schedules = regular table · PK(id) · uq_work_schedules_inspection_set_planned_date 복원 · 37col reconciled · 메타 exact
work_assignments   factory_id EXISTS/값 보존 · 단일 FK(schedule_id→ws.id) 복원 · pair CHECK 없음
safety_inspections factory_id EXISTS/값 보존 · 단일 FK(assignment_id→ws.id) 복원 · pair CHECK 없음 · legacy NULL pair 보존
equipment_checkins factory_id 불변 · 단일 FK(schedule_id→ws.id) ON DELETE SET NULL 복원
writers = 6874bb85 그대로. 04C/04D writer code rollback = 금지/불필요.
```

## 8. FAST-PATH ROLLBACK
```
work_schedules_old = DROP 금지 (cutover 후 cleanup 승인 전까지 보존).
DOWN: WRITE OFF/lock → composite FK drop → pair CHECK drop → new→old reconciliation →
  full-row equality → partitioned parent 제거 → old rename back → 단일 FK 복원 →
  04C/04D companion PRESERVE → exact POSTCHECK → WRITE ON.
```

## 9. STATUS / STOP GATE
```
CURRENT PRE-STATE       = GROUNDED (fresh 직독)
OLD PACKAGE DRIFT       = DOCUMENTED (§2)
UP REBASE               = COMPLETE (§10 ADD/backfill/comment 제거 → PRECHECK assertion)
DOWN REBASE             = COMPLETE (§6 DROP 제거 → PRESERVE · §9 POSTCHECK 반전)
04C/04D PRESERVATION    = PROVEN (UP §1/§15 assertion · DOWN §6 무DROP · §9-(8) 존재+보존 강제)
04E DIRECT PATH GATE    = CLOSED BY EXECUTION MODEL (§5 단일 tx LOCK → composite FK, 우회 window 0)
CHILD REWIRE            = CLOSED (§4 · wa/si MATCH FULL+CHECK, ec MATCH SIMPLE+SET NULL(schedule_id))
MATVIEW DEPENDENCY      = dashboard_stats 1 · REBIND CLOSED (UP §14-B DROP/재생성→NEW OID · DOWN §5 재결합 · POSTCHECK 검증)
ROLLBACK ANCHOR ACCESS  = PRIVATE (_mig_* + work_schedules_old REVOKE ALL from anon/authenticated/service_role · POSTCHECK 검증)
PHYSICAL PARTITION DIRECT ACCESS = CLOSED (p00~p15 REVOKE · logical parent 경유만 · POSTCHECK 검증)
ROLLBACK TARGET         = CURRENT PRE-HASH STATE (§7)
DRY-RUN PLAN            = COMPLETE (별도 DRYRUN_PLAN)
EXECUTION RUNBOOK       = COMPLETE (별도 EXECUTION_RUNBOOK)
DB/CODE/DEPLOY MUTATION = 0 · COMMIT = HOLD
RESULT = READY FOR HASH PACKAGE REVIEW
```
