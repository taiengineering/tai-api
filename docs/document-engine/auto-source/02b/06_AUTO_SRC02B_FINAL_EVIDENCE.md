---
title: AUTO-SRC-02B Final Evidence
status: IMPLEMENTATION COMPLETE / GPT VERIFY PENDING
version: 1
governed_by: WO-DOC-AUTO-SRC-02B
date: 2026-10-08
---

# WO-DOC-AUTO-SRC-02B RESULT

## A. GIT

```
base branch = docs/doc-auto-src-02a-projection-selector-discovery
base HEAD   = 1e30a03574f50368568450a7febdfda3e49a876b

branch = feat/doc-auto-src-02b-projection-selector
HEAD   = (this commit)

changed files (new):
  supabase/migrations/20261007182044_doc_auto_src_02b_projection_selector.sql
  services/document_engine/equipment_projection_resolver.py
  services/document_engine/auto_source_projection_selector.py
  tests/test_auto_src_02b_projection_selector.py
  docs/document-engine/auto-source/02b/01_PROJECTION_SELECTOR_CONTRACT.md
  docs/document-engine/auto-source/02b/02_PROJECTION_BINDING_SCHEMA.md
  docs/document-engine/auto-source/02b/03_EQUIPMENT_DETAIL_MAPPING_V1.csv
  docs/document-engine/auto-source/02b/04_ASSET_ID_CARRY_CONTRACT.md
  docs/document-engine/auto-source/02b/05_SELECTOR_TEST_MATRIX.md
  docs/document-engine/auto-source/02b/06_AUTO_SRC02B_FINAL_EVIDENCE.md
```

---

## B. MIGRATION

```
file: supabase/migrations/20261007182044_doc_auto_src_02b_projection_selector.sql
production apply: NOT EXECUTED (pending GPT verify + operator gate)

Tables created:
  inspection_set_projection_binding
    — id (uuid PK)
    — inspection_set_id FK → inspection_sets(id) ON DELETE RESTRICT
    — projection_type (text NOT NULL)
    — projection_detail (text NULL)
    — binding_source (text NOT NULL)
    — is_active (boolean NOT NULL DEFAULT true)
    — UNIQUE (inspection_set_id, projection_type, COALESCE(projection_detail, '-'))
    — RLS: service_role only

  document_equipment_projection_map
    — equipment_type_code (text PK)
    — projection_detail (text NULL)
    — mapping_status (text NOT NULL: RESOLVED / UNRESOLVED)
    — mapping_basis (text NOT NULL)
    — note (text NULL)
    — is_active (boolean NOT NULL DEFAULT true)
    — RLS: service_role only
    — SEED: 40 rows (35 RESOLVED + 5 UNRESOLVED)

Function replaced:
  fn_create_worker_inspection_record v1.1
    — Step 8 INSERT: added asset_id = v_sched.asset_id
    — All other steps: UNCHANGED (idempotency / replay guards preserved)
    — SECURITY DEFINER: preserved
    — GRANT EXECUTE TO service_role only: preserved
```

---

## C. PYTHON

```
services/document_engine/equipment_projection_resolver.py
  resolve_equipment_detail(equipment_type_code) → Optional[str]
  _STATIC_MAP: dict[str, Optional[str]] — 40 entries (35 RESOLVED + 5 None)
  Uses canonicalizer.normalize_equipment_type_code() for alias normalization

services/document_engine/auto_source_projection_selector.py
  select_projections(explicit_bindings, asset_id, equipment_type_code, is_completed)
    → List[ProjectionDecision]
  ProjectionDecision(projection_type, projection_detail, rule)
  RULE_1_EXPLICIT / RULE_2_ASSET_EQUIP / RULE_3_INSP_FALLBACK
```

---

## D. TESTS

```
tests/test_auto_src_02b_projection_selector.py
  27 tests: F1-F12 (selector) + M1-M8 (mapping) + A1-A3 (SQL carry) + R1-R4 (regression)
  27/27 PASS (local, 2026-10-08)
  DB write = 0 (pure Python + SQL static text tests)
```

---

## E. GAP RESOLUTION

```
GAP-02C (equipment code → AUTO EQUIP doc_detail):
  Status: RESOLVED (40-row seed in document_equipment_projection_map)
  35 RESOLVED: ELEC/MACHINE/BOILER/REFRIG/CRANE/ELEV/GAS/HAZMAT/FIRE
  5 UNRESOLVED: 015/035/036/037/040 (fail-closed; invisible in AUTO library)

Asset-id chain:
  fn_create_worker_inspection_record: FIXED (v_sched.asset_id now propagated)
  work_schedules.asset_id writer: NOT CHANGED (law_engine LEGAL path = NULL by design)
  legacy safety_inspections (5 rows): UNCHANGED (no backfill)
```

---

## F. PROJECTION SELECTOR RULES

```
RULE 1 (explicit binding): inspection_set_projection_binding rows → returned verbatim
RULE 2 (asset EQUIP): asset_id + resolved code → EQUIP(detail)
  UNRESOLVED code: fail-closed (empty list, not INSP fallback)
RULE 3 (INSP fallback): no binding, no asset, completed → INSP(detail=None)

Fail-closed policy:
  UNRESOLVED equipment (015/035/036/037/040) → invisible in AUTO library
  Not-completed inspection → invisible
  Unknown code → invisible
```

---

## G. MUTATION

```
DB write         = 0 (production apply NOT EXECUTED)
Code change      = 3 new files (resolver + selector + tests)
Migration        = 1 (local only; production gate PENDING)
Existing files modified = 0
```

---

## H. FINAL

```
AUTO-SRC-02B = IMPLEMENTATION COMPLETE / GPT VERIFY PENDING

GPT independent verify = PENDING

Production apply gate:
  Requires operator approval
  migration: 20261007182044_doc_auto_src_02b_projection_selector.sql
  command: supabase db push --linked (NOT MCP apply_migration)

Next:
  AUTO-SRC-02C (if applicable) or AUTO-SRC-03 (unblock from GAP-03 catalog)
```
