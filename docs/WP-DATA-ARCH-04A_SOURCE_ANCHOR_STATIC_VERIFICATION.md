# WP-DATA-ARCH-04A · Source Anchor · STATIC VERIFICATION  (ARTIFACT AUTHORING ONLY)

```
UNIT   = WP-DATA-ARCH-04A  Inspection → Document Source Anchor
MODE   = ARTIFACT AUTHORING / NO EXECUTION
SOURCE API REPO  = taiengineering/tai-api
SOURCE API BASE  = e1506aa45d3b35bf4d99d3c123600e9f19ab6996
CANONICAL PLAN   = taiengineering/taieng @ 65f2e5590d6881577d31afd64af23787493df19a
MUTATION = DB 0 / DDL 0 / DML 0 / CODE 0 / DEPLOY 0 / REAL CONFIRM 0 · COMMIT = HOLD
ARTIFACTS = 20260824_inspection_document_source_anchor_up.sql
            20260824_inspection_document_source_anchor_down.sql
            (this file)
```

---

## 1. PRE-STATE (직독 고정, read-only introspection @ vwlahtguyggrhvslabax)

```
runtime_document_data
  columns (19)  = id(uuid,NN,default gen_random_uuid) · form_schema_id(uuid,NN) · factory_id(uuid) · company_id(uuid)
                  · runtime_data_json(jsonb,'{}') · evidence_links(jsonb,'[]') · created_by · updated_by
                  · status(text,NN,'DRAFT') · created_at(tz,NN,now) · updated_at(tz,NN,now) · submitted_at · submitted_by
                  · reviewed_at · reviewed_by · review_comment · archived_at · version(int,NN,1) · parent_document_id
  PK            = runtime_document_data_pkey (id)
  FK            = runtime_document_data_form_schema_id_fkey (form_schema_id → runtime_form_schema.id)
  CHECK         = chk_rdd_status · chk_rdd_approval_requires_reviewer
  UNIQUE        = (none besides PK)
  indexes       = pkey(id) · idx_rdd_factory(factory_id) · idx_rdd_schema(form_schema_id) · idx_rdd_status(status)
  owner         = postgres · RLS enabled=true · forced=false
  policies      = anon_select_runtime_document_data (SELECT, roles=anon, using true)
                  service_role_full (ALL, roles=service_role, using true, check true)
  grants        = postgres(ALL, grantable) · service_role(ALL, non-grantable)
  table comment = (null)
  triggers      = trg_rdd_seal_guard (BEFORE UPDATE, fn_rdd_seal_guard)
  row_count     = 1 · form_schema_id NULL = 0

CONFLICT CHECKS
  source_inspection_id column exists         = 0   (expected 0 ✓)
  same-name constraint collision             = 0   (runtime_document_data_source_inspection_id_fkey,
                                                     uq_rdd_source_inspection_form_schema — both free ✓)
  future UNIQUE(source_inspection_id, form_schema_id) violation candidate
                                             = 0   (col absent now; after add all-NULL → PG NULL distinct ✓)

FK TARGET
  safety_inspections PK = PRIMARY KEY (id) · id type = uuid   (single-col FK target valid ✓)
```

---

## 2. UP — static design check

```
statements                = 3
  (1) ADD COLUMN source_inspection_id uuid NULL
  (2) ADD CONSTRAINT ...fkey FOREIGN KEY (source_inspection_id) → safety_inspections(id) ON DELETE RESTRICT
  (3) ADD CONSTRAINT uq_rdd_source_inspection_form_schema UNIQUE (source_inspection_id, form_schema_id)
creates exactly            = 1 column + 1 FK + 1 UNIQUE                     ✓
column nullable            = YES (NOT NULL 미사용)                          ✓
FK delete semantic         = ON DELETE RESTRICT (RESTRICT/NO ACTION 계열)   ✓  (SET NULL 없음 ✓)
UNIQUE columns             = (source_inspection_id, form_schema_id) 복합    ✓  (source 단독 UNIQUE 없음 ✓)
forbidden ops present?     = NO backfill · NO source inference · NO status change · NO inspection data
                             · NO new table/trigger/function · NO auto-create   ✓
```

## 3. DOWN — static design check

```
statements                = 3 (UP 역순)
  DROP CONSTRAINT uq_rdd_source_inspection_form_schema
  DROP CONSTRAINT runtime_document_data_source_inspection_id_fkey
  DROP COLUMN source_inspection_id
removes exactly            = same 3 objects                                 ✓
other objects touched      = 0 (PK/기존FK/CHECK/index/policy/trigger 불변)  ✓
restores                   = PRE-STATE schema (§1)                          ✓
```

## 4. Compatibility contract (WP-03 matrix 상속)

```
Change = runtime_document_data.source_inspection_id (nullable additive) + composite UNIQUE
  OLD DB + OLD CODE = SAFE
  OLD DB + NEW CODE = BREAKS   (NEW code가 없는 컬럼에 write → 스키마 先배포 필요)
  NEW DB + OLD CODE = SAFE     (구 writer 미기입, nullable)
  NEW DB + NEW CODE = SAFE
DEPLOYMENT RULE = SCHEMA-FIRST
→ code artifact(CD5-2 orchestration)는 본 unit 범위 아님 (별도 unit).
```

## 5. Dry-run plan (NEXT step용 검증쿼리 — 이번엔 실행 안 함)

```
PRE (apply 전)
  column absent     : SELECT count(*) FROM information_schema.columns
                        WHERE table_schema='public' AND table_name='runtime_document_data'
                          AND column_name='source_inspection_id';                       -- expect 0
  constraint absent : SELECT count(*) FROM pg_constraint
                        WHERE conname IN ('runtime_document_data_source_inspection_id_fkey',
                                          'uq_rdd_source_inspection_form_schema');       -- expect 0

POST-UP
  column exists     : same as above column query                                        -- expect 1
                      + data_type='uuid' AND is_nullable='YES'
  FK exists         : SELECT pg_get_constraintdef(oid) FROM pg_constraint
                        WHERE conname='runtime_document_data_source_inspection_id_fkey';
                      -- expect FOREIGN KEY (source_inspection_id) REFERENCES safety_inspections(id) ON DELETE RESTRICT
  UNIQUE exists     : SELECT pg_get_constraintdef(oid) FROM pg_constraint
                        WHERE conname='uq_rdd_source_inspection_form_schema';
                      -- expect UNIQUE (source_inspection_id, form_schema_id)
  row count         : SELECT count(*) FROM public.runtime_document_data;                -- expect 1 (unchanged)
  all rows NULL     : SELECT count(*) FROM public.runtime_document_data
                        WHERE source_inspection_id IS NOT NULL;                          -- expect 0

POST-DOWN
  column absent     : PRE column query                                                  -- expect 0
  constraint absent : PRE constraint query                                              -- expect 0
  row count         : SELECT count(*) FROM public.runtime_document_data;                -- expect 1 (unchanged)

business-data mutation = 0   (schema-only; runtime_data_json/status/rows 불변)
```

## 6. TRANSACTIONAL DRY-RUN RESULT (WP-DATA-ARCH-04A-DRYRUN = PASS)

```
METHOD = 단일 DO 블록 원자 transaction 내 PRE→UP→POST-UP→DOWN→POST-DOWN 수집 후
         RAISE EXCEPTION 강제 ROLLBACK (persistence 0) · 이후 별도 read-only 영구상태 재확인
PRE        col=0 · coll=0 · rows=1 · fsnull=0
POST-UP    col=1(uuid,nullable) · FK=[... REFERENCES safety_inspections(id) ON DELETE RESTRICT] · UNIQUE=[(source_inspection_id, form_schema_id)] · rows=1 · nonnull=0
POST-DOWN  col=0 · coll=0 · rows=1  (PRE-state 복원)
FINAL(rollback 후) col 부재=0 · target 제약=0 · rows=1 · total constraints=4 · indexes=4 · triggers=1  (PRE 동일)
transaction status = ROLLED BACK · persistent schema diff = 0 · persistent data diff = 0
UP EXECUTION=PASS · POST-UP CONTRACT=PASS · DOWN EXECUTION=PASS · POST-DOWN RESTORATION=PASS
(상세 = WP-DATA-ARCH-04A-DRYRUN_RECEIPT)
```

## 7. STATUS / STOP GATE

```
STATIC DESIGN         = PASS
TRANSACTIONAL DRY-RUN = PASS
PERSISTENT MUTATION   = 0
UP STATIC DESIGN      = PASS
DOWN STATIC DESIGN    = PASS
PRE-STATE GROUNDED    = PASS  (§1 실측)
COMPATIBILITY         = PASS  (schema-first)
SCOPE DIFF            = EXACT (1 col + 1 FK + 1 UNIQUE ; DOWN 동일 3)
DB MUTATION           = 0
CODE MUTATION         = 0

HOLD = PRODUCTION APPLY / ORCHESTRATION CODE / REAL DOCUMENT CREATE / CONTROLLED FIRST CONFIRM
(ARTIFACT COMMIT = APPROVED — 본 문서 + UP/DOWN SQL 정본화)
```
