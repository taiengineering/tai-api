# WP-DATA-ARCH-04E · HASH REWIRE CONTRACT  (READINESS ONLY · 04E 미실행)

```
UNIT  = WP-DATA-ARCH-04E  child composite FK readiness for work_schedules HASH migration
MODE  = CONTRACT / READINESS 문서 · DDL 실행 = 0 (HASH migration package 소유)
PG    = 17.6 (production)
```

목적: 04A~04E로 준비된 3 child 를 work_schedules HASH migration 후 composite FK 로 rewire하기 위한 계약 고정.
각 child의 companion factory_id·standalone 정책이 다르므로 FK 형태도 다르다.

## 1. work_schedules HASH 전제 (HASH package 소유, 04E 미실행)
```
HASH migration 이 work_schedules 에 (id, factory_id) UNIQUE/PK 를 부여해야
child 의 composite FK REFERENCES work_schedules(id, factory_id) 가 성립.
→ 아래 child rewire 는 전부 HASH migration 완료 이후에만 실행 가능 (04E는 계약만).
```

## 2. CHILD READINESS MATRIX
```
child                 companion col   standalone(부모 없음)   backfill    현재 상태     rewire target FK
--------------------  --------------  ----------------------  ----------  -----------   ---------------------------------------------
work_assignments      factory_id      불가(schedule_id NN 강제  5991 완결   04C LIVE      FK(schedule_id, factory_id)→ws(id,factory_id)
                      (=parent)        via writer fail-closed)  (전량)                    MATCH FULL + pair CHECK((schedule_id IS NULL)=(factory_id IS NULL))
                                                                                          (전량 non-NULL이라 pair CHECK 항상 충족)
safety_inspections    factory_id      허용(assignment_id NULL   linked만    04D LIVE      FK(assignment_id, factory_id)→ws(id,factory_id)
                      (=parent)        = legacy NULL pair)      (linked 1)                MATCH FULL + pair CHECK((assignment_id IS NULL)=(factory_id IS NULL))
                                                                                          legacy NULL pair 허용 · 신규 standalone=04D writer 금지 · partial NULL=DB 차단
equipment_checkins    factory_id      허용(schedule_id NULL     불요(rows0) 04E(writer)   FK(schedule_id, factory_id)→ws(id,factory_id)
                      (=ASSET)         = 현장 익명 스캔)                     hardening     MATCH SIMPLE · ON DELETE SET NULL (schedule_id)
```

## 3. equipment_checkins 전용 계약 (핵심 차이)
```
(a) factory authority = equipment_asset.factory_id (parent schedule 아님).
    → work_assignments/safety_inspections 는 factory=parent(schedule)지만, equipment_checkins 는 factory=ASSET.
    → composite FK 는 relation 존재 시 일관성만 강제하고, factory 출처는 asset 유지.
(b) standalone(schedule_id NULL) 허용 → MATCH SIMPLE 필수 (MATCH FULL 금지).
    MATCH SIMPLE: 참조 컬럼 중 하나라도 NULL 이면 FK 미검증 → schedule_id NULL 이면 factory_id(asset) 자유.
(c) ON DELETE SET NULL (schedule_id)  [PG15+ column-list]:
    schedule 삭제 시 schedule_id 만 NULL 로, factory_id(asset)는 보존.
    (단순 ON DELETE SET NULL 은 참조 컬럼 전체(schedule_id+factory_id)를 NULL → factory_id 소실이라 금지.)
(d) pair CHECK(schedule_id NULL ⇔ factory_id NULL) 적용 금지:
    equipment_checkins 는 schedule 없이도 factory 보유가 정상이므로 XNOR CHECK 부적합.
```

## 4. writer 선행 조건 + DIRECT PATH 경고 (04E가 채우는 것 / 못 채우는 것)
```
composite FK 는 cross-factory 행을 "거부"하지만, 현재 단일컬럼 FK 상태에서 cross-factory INSERT 가 들어오면
HASH rewire 시 FK 위반으로 마이그레이션이 실패한다.
→ 04E writer fail-closed(§WRITER_PATCH_DRAFT)로 API 경로 cross-factory checkin 을 사전 차단.
현재 rows=0 이므로 기존 위반 0.

★ 그러나 신규 위반 "완전 0 보장"은 아니다 (DB 실측):
  equipment_checkins 는 anon INSERT grant + RLS anon_insert WITH CHECK(true) 로
  API submit_checkin() 을 우회한 Supabase direct anon INSERT 가 가능하다.
  → API writer 경로의 신규 cross-factory = 배포 후 차단.
  → 단, direct anon INSERT 는 composite FK(DB-level) 적용 전까지 DB 가 pair 를 강제하지 않음 = OPEN.
  이 direct path 봉쇄는 04E 범위 밖(RLS/anon revoke 는 범위 확대). HASH maintenance Gate 소유.

★ 따라서 HASH maintenance Gate 는 반드시 아래 순서를 강제한다:
  WRITE OFF (equipment_checkins direct anon INSERT 포함 실제 write 차단 — API 정지만으로 불충분)
  → cross-factory precheck = 0 (wa/si/equipment_checkins 전 child)
  → composite FK 생성 (child별 MATCH: wa/si=FULL+CHECK, checkins=SIMPLE)
  → FK live 확인
  → WRITE ON
  (04D에서 쓴 DB-level INSERT 차단 트리거 방식이 direct anon 까지 막는 실제 WRITE OFF 수단)
```

## 5. HASH DRY-RUN 시 검증 항목 (04E 미실행, HASH package에서)
```
- work_schedules (id, factory_id) UNIQUE/PK 존재 여부 (composite FK 전제)
- ON DELETE SET NULL (schedule_id) column-list DDL 실행 가능성 (PG 17.6)
- 각 child cross-factory 위반 행 = 0 (wa/si/equipment_checkins) — FK 생성 전 필수 precheck
  (equipment_checkins 는 API 우회 direct anon INSERT 가능성 때문에 precheck 를 WRITE OFF 이후에 수행해야 신뢰 가능)
- MATCH child별 적용 (canonical WORK_SCHEDULES_PARTITION_DESIGN_FINAL_v1): wa=MATCH FULL+pair CHECK · si=MATCH FULL+pair CHECK · equipment_checkins=MATCH SIMPLE(pair CHECK 없음)
- si pair CHECK ((assignment_id IS NULL)=(factory_id IS NULL)) 실행가능성 + legacy NULL pair 1건 통과 확인
- 기존 단일컬럼 FK drop → composite FK add 원자성 · lock 창
```

## 6. 04E 경계
```
04E 완료(승인·배포 시) = equipment_checkins API writer pair fail-closed LIVE + child composite FK 계약 고정.
04E 미의미 = composite FK 실제 생성(아님) · work_schedules HASH 실행(아님) · (id,factory_id) UNIQUE 부여(아님)
           · direct anon INSERT 경로 봉쇄(아님 — RLS/anon revoke 는 04E 범위 밖).
DIRECT ANON DB WRITE PATH = OPEN / HASH GATE OWNED
  (composite FK live 전까지 direct anon path 로 cross-factory INSERT 가 물리적으로 가능; HASH WRITE OFF 가 봉쇄).
다음 = work_schedules HASH migration maintenance gate → §4 WRITE OFF 순서 강제 → 위 3 child composite FK rewire (본 계약대로).
```
