# WP-DATA-ARCH-04B · Submitter Anchor · STATIC VERIFICATION + DRY-RUN

```
UNIT   = WP-DATA-ARCH-04B  Safety Inspection Submitter Anchor
LEVEL  = B (low-risk additive, schema-only)
SOURCE API BASE = e1506aa45d3b35bf4d99d3c123600e9f19ab6996
CANONICAL PLAN  = taiengineering/taieng @ 65f2e5590d6881577d31afd64af23787493df19a (IMPLEMENTATION_PLAN S1-3)
MUTATION (this artifact) = DB 0 / DDL 0 / DML 0 / CODE 0 / DEPLOY 0
ARTIFACTS = 20260824_safety_inspection_submitter_anchor_up.sql / _down.sql / (this file)
```

## 1. PRE-STATE (직독 고정 @ vwlahtguyggrhvslabax)
```
safety_inspections
  columns (6) = id(uuid,NN,gen_random_uuid) · assignment_id(uuid) · asset_id(uuid) · inspector_id(uuid)
                · inspection_date(timestamp,now()) · status_code(text)
  PK   = safety_inspections_pkey (id)
  FK   = assignment_id→work_schedules(id) · asset_id→equipment_assets(id) · inspector_id→users(id)
  indexes  = safety_inspections_pkey · idx_safety_inspections_assignment · idx_safety_inspections_status
  policies = anon(select/insert/update/delete) · authenticated(ALL) · service_role_full   (6)
  triggers = (none) · owner = postgres · RLS enabled = true
  row_count = 2
CONFLICT CHECKS
  submitted_by column exists        = 0  (expected 0 ✓)
  target FK name collision          = 0  (safety_inspections_submitted_by_fkey free ✓)
FK TARGET
  users PK = PRIMARY KEY (id) · id uuid  (single-col FK target valid ✓)
IDENTITY CONTRACT
  inspector_id = 실제 검사자 (existing) · submitted_by = 제출 인증 사용자 (신규, 다른 의미)
```

## 2. UP — static design check
```
statements = 2
  (1) ADD COLUMN submitted_by uuid NULL
  (2) ADD CONSTRAINT safety_inspections_submitted_by_fkey FK (submitted_by)→users(id) ON DELETE RESTRICT
creates exactly = 1 column + 1 FK              ✓  (UNIQUE 없음 — submitted_by는 유일키 아님)
column nullable = YES (NOT NULL 미사용)         ✓
FK delete       = ON DELETE RESTRICT (SET NULL 없음) ✓
forbidden ops   = NO backfill · NO inspector_id→submitted_by 복사 · NO worker_registry id
                  · NO auth/code patch · NO worker_check/inspection_checklist 수정 · NO deploy   ✓
```

## 3. DOWN — static design check
```
statements = 2 (UP 역순): DROP CONSTRAINT ...submitted_by_fkey → DROP COLUMN submitted_by
removes exactly = same 2 objects · other objects touched = 0 · restores PRE-STATE (§1)   ✓
```

## 4. Compatibility contract (WP-03 matrix 상속)
```
Change = safety_inspections.submitted_by (nullable additive, FK users)
  OLD DB + OLD CODE = SAFE
  OLD DB + NEW CODE = BREAKS (스키마 先배포 필요)
  NEW DB + OLD CODE = SAFE  (구 writer 미기입, nullable)
  NEW DB + NEW CODE = SAFE
DEPLOYMENT RULE = SCHEMA-FIRST · code(worker_check/inspection_checklist submitted_by write) = 본 unit 범위 아님(CD5-1)
```

## 5. TRANSACTIONAL DRY-RUN RESULT (PASS)
```
METHOD = 단일 DO 블록 원자 transaction 내 PRE→UP→POST-UP→DOWN→POST-DOWN 수집 후 RAISE 강제 ROLLBACK · 이후 read-only 재확인
PRE       col=0 · coll=0 · rows=2 · cons=4 · idx=3
POST-UP   col=1(uuid,nullable) · rows=2 · nonnull=0 · cons=5 · idx=3 · FK=[FOREIGN KEY (submitted_by) REFERENCES users(id) ON DELETE RESTRICT]
POST-DOWN col=0 · coll=0 · rows=2  (PRE-state 복원)
FINAL(rollback 후) col 부재=0 · fk 부재=0 · rows=2 · cons=4 · idx=3  (PRE 동일)
transaction status = ROLLED BACK · persistent schema diff = 0 · persistent data diff = 0
UP EXEC=PASS · POST-UP CONTRACT=PASS · DOWN EXEC=PASS · POST-DOWN RESTORATION=PASS
```

## 6. STATUS
```
STATIC DESIGN = PASS · TRANSACTIONAL DRY-RUN = PASS · PERSISTENT MUTATION = 0
SCOPE DIFF = EXACT (1 col + 1 FK ; DOWN 동일 2)
HOLD = ORCHESTRATION/writer(CD5-1) · REAL DOCUMENT CREATE · CONTROLLED FIRST CONFIRM
(ARTIFACT COMMIT + PROD APPLY = LEVEL-B single flow)
```
