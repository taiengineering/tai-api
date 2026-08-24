# WP-DATA-ARCH-04D · Safety Inspection Factory Companion · STATIC VERIFICATION

```
UNIT   = WP-DATA-ARCH-04D  safety_inspections.factory_id companion + writer preparation
LEVEL  = A (subset backfill + writer cutover dependency)
MODE   = READ ONLY AUDIT + ARTIFACT AUTHORING · DB/DDL/DML/CODE/DEPLOY MUTATION = 0 · COMMIT = HOLD
SOURCE API = taiengineering/tai-api @ ad027e53 (04C deployed HEAD)
CANONICAL PLAN = taiengineering/taieng @ 65f2e5590d6881577d31afd64af23787493df19a (S1-4 / B2-1 / WS-3)
```

purpose: factory_id = work_schedules parent relation의 **companion** (신규 tenant authority 아님). 향후 HASH migration child FK 준비.
04C(work_assignments)와 달리 **부분 결정적** — linked 행만 backfill, standalone(legacy) 행은 NULL 유지.

## 1. PRE-STATE (직독 @ vwlahtguyggrhvslabax)
```
safety_inspections
  columns (7) = id(uuid,NN,gen_random_uuid) · assignment_id(uuid) · asset_id(uuid) · inspector_id(uuid)
                · inspection_date(timestamp,now) · status_code(text) · submitted_by(uuid)[04B live]
  PK  = safety_inspections_pkey (id)
  FK  = assignment_id→work_schedules(id) · asset_id→equipment_assets(id) · inspector_id→users(id)
        · submitted_by→users(id) ON DELETE RESTRICT [04B]
  indexes  = safety_inspections_pkey · idx_safety_inspections_assignment · idx_safety_inspections_status
  policies = anon(select/insert/update/delete) · authenticated(ALL) · service_role_full (6)
  triggers = (none) · owner = postgres · RLS enabled = true · forced = false
  factory_id column exists = 0  (safe to ADD)
```

## 2. ROW SPLIT + BACKFILL DETERMINISM (실측 count)
```
canonical source = si.assignment_id → work_schedules.id → work_schedules.factory_id (유일)
total rows                                  = 2
schedule-backed (assignment_id NOT NULL)    = 1   → DETERMINISTIC LINKED (backfill 대상)
legacy/standalone (assignment_id NULL)      = 1   → LEGACY NULL PAIR (factory_id NULL 유지; 실패 아님)
linked broken parent (assignment 있으나 ws 없음) = 0
linked parent work_schedules.factory_id NULL    = 0
deterministic linked resolvable             = 1 / 1  (linked 100%)
판정 = LINKED FULLY DETERMINISTIC · STANDALONE UNRESOLVED-BY-DESIGN(NULL 유지) · 임의 factory 추론 0
```

## 3. UP — static design check
```
순서 = PRECHECK(fail-closed) → ADD COLUMN → LINKED-SUBSET UPDATE → POST VALIDATION(fail-closed)
PRECHECK  = (A) assignment_id NOT NULL & parent 없음 → RAISE
            (B) assignment_id NOT NULL & parent factory_id NULL → RAISE
            (assignment_id NULL 은 FAIL 아님 — LEGACY NULL PAIR 허용)
ADD       = factory_id uuid NULL  (nullable, NOT NULL 아님 ✓)
BACKFILL  = UPDATE ... SET factory_id = ws.factory_id FROM work_schedules ws
            WHERE si.assignment_id = ws.id AND si.factory_id IS NULL
            (linked subset only ✓ · standalone assignment_id NULL 미대상 → NULL 유지 ✓ · request/user/asset 추론 없음 ✓)
POST      = linked factory NULL 잔존>0 → RAISE / linked mismatch>0 → RAISE
            / standalone(assignment NULL) factory NOT NULL>0 → RAISE  (추론 오염 차단)
atomicity = 단일 transaction (실패 시 전량 rollback, 부분성공 없음)
성공조건  = linked-pair 완결 + standalone-pair NULL 유지 (전량 NULL=0 아님)
04D 미포함 = NOT NULL · single/composite FK · MATCH FULL · pair CHECK · work_schedules PK 변경 · HASH · tenant filter ✓
```

## 4. DOWN — static design check
```
statement = DROP COLUMN factory_id (단일) · business data(legacy 포함) 무변경
ROLLBACK-A (writer deploy 전) = DOWN 단독 안전 (구 writer 2개 factory_id 미참조)
ROLLBACK-B (writer deploy 후) = WRITE OFF → writer CODE ROLLBACK(worker_check/inspection_checklist) → DROP COLUMN → 검증 → WRITE ON
```

## 5. Compatibility (WP-03 matrix 상속)
```
factory_id nullable additive:
  OLD DB + OLD CODE = SAFE
  OLD DB + NEW CODE = BREAKS (스키마 先)
  NEW DB + OLD CODE = SAFE  (구 2 writer 미기입 → linked면 NULL 유입 가능(재조정) / standalone도 NULL)
  NEW DB + NEW CODE = SAFE
RULE = SCHEMA FIRST, backfill 무결성 위해 production은:
  WRITE OFF → SCHEMA → LINKED SUBSET BACKFILL → POST-BACKFILL VERIFY → PATCHED WRITER DEPLOY
  → RECONCILIATION(linked only) → POST-RECONCILIATION VERIFY → WRITE ON → NATURAL WRITE OBSERVATION
  (★ reconciliation 으로 linked NULL=0/mismatch=0/standalone NULL 확정 이후에만 WRITE ON — window gap 닫기 전 재개 금지)
```

## 6. WRITER INVENTORY (safety_inspections INSERT creator 2개, 현 HEAD 본문 재확인)
```
W1 routers/worker_check.py :: POST /worker-check/submit  [blob 503cf84a]
   현재 INSERT {inspector_id, inspection_date, status_code, assignment_id=schedule_ref}
     schedule_ref = body.schedule_id OR (body.assignment_id → work_assignments.schedule_id)
   CheckSubmitBody.factory_id 존재하나 **사용 금지**(request 신뢰 금지).
   04D patch = schedule_ref 확정 후 parent work_schedules.select(id,factory_id).eq(id,schedule_ref)
               → 없거나 factory_id NULL → 409(fail-closed) · INSERT factory_id=parent
   STANDALONE = schedule_ref 미확정(None) → 409(신규 standalone 생성 금지) · 기존 legacy assignment_id=NULL 행은 미변경.
   [경계·비수정] inspector_id = users.id OR worker_registry.id fallback(FK-break 위험) = 별도 dependency/HOLD.
                04D에서 고치지 않음. 단 factory 테스트가 이 위험을 가리지 않도록 inspector_id 로직 불변 유지.
W2 routers/inspection_checklist.py :: POST /inspection/start/{work_schedule_id}  [blob 3907ba49]
   auth+ownership 이미 보유(_ensure_ws_own). work_schedule_id = parent id.
   현재 INSERT {assignment_id=work_schedule_id, inspection_date, status_code='in_progress'} (factory_id 없음)
   04D patch = side-effect(work_schedules UPDATE) 전에 parent factory_id PRE-READ
               → NULL/미존재면 409(fail-closed) → INSERT factory_id=parent
결론 = 2 creator 모두 factory source = parent work_schedules. request factory 금지. NULL fallback 후 계속 금지(fail-closed 강제).
추가 INSERT creator 탐색 = safety_inspections INSERT 는 위 2곳뿐(직독). (신규 발견 시 STOP+보고 — 해당 없음)
```

## 7. 경계 (04D 미혼입)
```
submitted_by writer(worker_check/inspection_checklist가 submitted_by 기록) = 별도 CD5-1 dependency. 04D에서 손대지 않음.
worker_check identity risk(roster fallback→inspector_id, FK는 users) = 별도 HOLD. 04D에서 수정 안 하되 factory 테스트가 이를 가리지 않게 함.
```

## 8. STATUS / STOP GATE
```
PRE-STATE GROUNDED        = PASS
LINKED BACKFILL DETERMINISTIC = PROVEN (linked 1/1)
LEGACY NULL POLICY        = CLOSED (standalone assignment_id NULL → factory_id NULL 유지, POST에서 강제)
UP STATIC                 = PASS
DOWN STATIC               = PASS
W1/W2 PATCH DRAFTS        = COMPLETE (WRITER_PATCH_DRAFTS · fail-closed 강제)
TARGETED TEST PLAN        = COMPLETE (CUTOVER_PLAN §TESTS)
CUTOVER RUNBOOK           = COMPLETE (WRITER_CUTOVER_PLAN · 순서: deploy→smoke→reconciliation→post-verify→WRITE ON→natural)
ROLLBACK                  = CLOSED (A/B)
HASH BOUNDARY             = CLOSED (04D = si companion READY; composite FK/HASH 아님)
DB/DML/CODE/DEPLOY MUTATION = 0 · COMMIT = HOLD
RESULT = READY FOR 04D EXECUTION
```
