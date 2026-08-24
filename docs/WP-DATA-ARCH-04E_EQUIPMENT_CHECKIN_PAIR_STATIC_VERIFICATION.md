# WP-DATA-ARCH-04E · Equipment Checkin Schedule/Factory Pair · STATIC VERIFICATION

```
UNIT   = WP-DATA-ARCH-04E  equipment_checkins schedule/factory pair readiness
LEVEL  = A (HASH-migration prerequisite; writer hardening only — NO DB migration)
MODE   = READ ONLY AUDIT + PATCH ARTIFACT AUTHORING · DB/DDL/DML/CODE/DEPLOY MUTATION = 0 · COMMIT = HOLD
SOURCE HEAD = 57da2266293b10024514e93ee8f5010cbb9c298c (04D deployed)
CANONICAL PLAN = taiengineering/taieng @ 65f2e5590d6881577d31afd64af23787493df19a
```

purpose: schedule_id 제공된 checkin에서 `equipment_asset.factory_id == work_schedule.factory_id` 를 writer 단계 fail-closed로 보장 → work_schedules composite FK rewire 준비.
04C/04D와 달리 **additive DB migration 없음**(schedule_id·factory_id 이미 존재). writer hardening only.

## 1. PRE-STATE (직독 @ vwlahtguyggrhvslabax · PG 17.6)
```
equipment_checkins  (rows = 0)
  columns (17) = id(uuid,NN) · equipment_asset_id(uuid,NN) · schedule_id(uuid,NULL) · factory_id(uuid,NULL)
                 · company_id(uuid,NULL) · worker_id · worker_name · checkin_items(jsonb) · overall_result(text,NN)
                 · note · signature_data · photo_urls(array) · scan_method('QR') · latitude · longitude
                 · checkin_at(tz,NN,now) · created_at(tz,now)
  PK  = equipment_checkins_pkey (id)
  FK  = equipment_asset_id→equipment_assets(id) ON DELETE CASCADE
        · schedule_id→work_schedules(id) ON DELETE SET NULL
        · factory_id→factories(id) ON DELETE SET NULL
        · company_id→companies(id) ON DELETE SET NULL
  indexes  = equipment_checkins_pkey · idx_checkins_checkin_at · idx_checkins_equipment_id · idx_checkins_factory_id
  policies = anon(select/insert/update/delete) · service_role_full (5)   ← anon INSERT = 현장 익명 스캔 계약
  triggers = (none) · owner = postgres · RLS enabled = true · forced = false
equipment_assets : total = 3299 · factory_id NULL = 0
```

## 2. CURRENT WRITER — EXACTLY ONE
```
routers/equipment_checkins.py :: submit_checkin  POST /equipment-checkins  [blob 6773b8a4]  (인증 불필요 — 익명 스캔)
  현재 흐름:
    asset = equipment_assets.select(id,asset_name,factory_id).eq(id, body.equipment_asset_id)
    factory_id = asset.factory_id           (server-derived)  ← ASSET = factory authority
    company_id = factories(factory_id).company_id
    INSERT equipment_checkins { equipment_asset_id, factory_id(=asset), schedule_id=body.schedule_id(있을 때만), ... }
    if body.schedule_id and overall_result=='OK' → work_schedules status_code='DONE'
    if overall_result in (NG,HOLD) and factory_id → notifications INSERT + FCM
  GAP = body.schedule_id(client) 와 asset.factory_id 사이 factory 일치 검증 없음
        → asset.factory=A, body.schedule_id→ws.factory=B 인 cross-factory pair도 단일컬럼 FK만 통과하면 INSERT 가능.
  현재 table rows = 0 → 기존 데이터 오염 0.
```

## 3. CANONICAL FACTORY CONTRACT
```
factory_id source = equipment_asset.factory_id (계속 유지). schedule factory로 asset factory overwrite 금지.
ASSET    = checkin 대상의 factory authority
SCHEDULE = optional relation → 존재 시 relation consistency(동일 factory)만 검증
```

## 4. STANDALONE POLICY (safety_inspections와 다름)
```
schedule_id = NULL 정상 허용 (QR/RFID 현장점검은 schedule 없이 존재 가능).
NEW STANDALONE CHECKIN = ALLOWED · factory_id = equipment_asset.factory_id.
→ equipment_checkins에는 MATCH FULL / pair CHECK(schedule_id NULL = factory_id NULL) 적용 금지.
```

## 5. TARGET WRITER CONTRACT (fail-closed, side-effect 전)
```
asset_factory_id = asset.factory_id
if body.schedule_id:
    parent = work_schedules.select(id, factory_id).eq(id, body.schedule_id).limit(1)
    parent 없음                       → fail-closed (409)
    parent.factory_id IS NULL          → fail-closed (409)
    asset_factory_id IS NULL           → fail-closed (409)
    parent.factory_id != asset_factory_id → fail-closed (409)
→ 통과 후에만 INSERT. INSERT.factory_id = asset_factory_id · schedule_id = body.schedule_id(있을 때만).
금지: request factory 추론 · schedule factory로 asset factory overwrite · mismatch INSERT 후 DB FK 위임 · company 임의 보정.
```

## 6. SIDE-EFFECT ORDER
```
PAIR VALIDATION → equipment_checkins INSERT → (schedule_id & OK 이면) work_schedules DONE → (NG/HOLD 이면) notification/FCM
cross-factory / missing schedule / parent factory NULL → equipment_checkins INSERT 0 · work_schedules UPDATE 0 · notification 0
(현재 코드 순서 INSERT→DONE→notify 는 유지; pair validation 을 그 앞에 삽입)
```

## 7. FUTURE COMPOSITE FK CONTRACT (04E 미실행 — HASH package 소유)
```
HASH child rewire target:
  FOREIGN KEY (schedule_id, factory_id) REFERENCES work_schedules(id, factory_id)
  MATCH SIMPLE (NOT MATCH FULL)  → schedule_id NULL(standalone)이면 FK 미검증 = 허용
  ON DELETE SET NULL (schedule_id)  ← PG15+ column-list; schedule 삭제 시 schedule_id만 NULL, factory_id(asset)는 보존
전제 = work_schedules 에 (id, factory_id) UNIQUE/PK (HASH migration이 부여) → 그 뒤에만 이 composite FK 생성 가능.
DDL 실행가능성(특히 ON DELETE SET NULL (schedule_id)) = HASH migration dry-run에서 검증 (PG 17.6).

canonical 3-child FK 계약 (봉인된 WORK_SCHEDULES_PARTITION_DESIGN_FINAL_v1 반영):
  work_assignments   = MATCH FULL + pair CHECK((schedule_id IS NULL)=(factory_id IS NULL))   [전량 non-NULL]
  safety_inspections = MATCH FULL + pair CHECK((assignment_id IS NULL)=(factory_id IS NULL))
       MATCH FULL = 둘 다 NULL 이면 허용 → 04D legacy NULL pair 통과 · 신규 standalone은 04D writer가 409 차단 · partial NULL은 DB CHECK 차단
  equipment_checkins = MATCH SIMPLE (pair CHECK 없음) · ON DELETE SET NULL (schedule_id)
       factory=asset authority · schedule optional standalone 허용이라 wa/si와 달리 MATCH FULL/pair CHECK 미적용
→ 이 canonical 계약 반영 확인 후에만 FUTURE FK CONTRACT = CLOSED.
```

## 8. COMPATIBILITY (04C/04D와 다름 — 선배포 가능)
```
writer patch 는 신규 DB column 요구 없음:
  OLD DB + OLD CODE = 현재 동작
  OLD DB + NEW CODE = SAFE (기존 columns + work_schedules.factory_id 만 사용)
  HASH NEW DB + NEW CODE = SAFE target
→ 이 writer hardening 은 HASH maintenance 이전에 미리 deploy 가능 (WRITE OFF/스키마 불요).
```

## 9. STATUS / STOP GATE
```
PRE-STATE GROUNDED   = PASS
CURRENT WRITER       = GROUNDED (creator 정확히 1개: submit_checkin)
PAIR MISMATCH RISK   = CLOSED (writer fail-closed 계약)
STANDALONE POLICY    = CLOSED (schedule NULL 허용 · MATCH FULL 금지)
PATCH DRAFT          = COMPLETE (WRITER_PATCH_DRAFT)
TEST PLAN            = COMPLETE (WRITER_PATCH_DRAFT §TESTS, T1–T10)
FUTURE FK CONTRACT   = CLOSED (HASH_REWIRE_CONTRACT · canonical MATCH 반영)
HASH READINESS MATRIX = COMPLETE (HASH_REWIRE_CONTRACT)
DB/CODE/DEPLOY MUTATION = 0 · COMMIT = HOLD
RESULT = READY FOR 04E EXECUTION REVIEW
```
