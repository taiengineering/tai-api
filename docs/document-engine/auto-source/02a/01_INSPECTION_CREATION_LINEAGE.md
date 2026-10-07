---
title: Inspection Creation Lineage
status: FROZEN
version: 1
governed_by: WO-DOC-AUTO-SRC-02A
date: 2026-10-08
---

# Inspection Creation Lineage

## 1. Chain Overview

```
Legal Obligation Atoms (LEG DB)
        ↓  canonical_writer.py → materialize_canonical_inspection_sets()
inspection_sets (source=LEGAL_ENGINE)
        ↓  law_engine.py → run_generate_operation_schedules()
work_schedules (source_type=LEGAL)
        ↓  fn_create_worker_inspection_record (RPC)
safety_inspections
        ↓  fn_resolve_inspection_record(inspection_id)
Read Model (on-demand)
```

---

## 2. Stage 1: Legal Obligation Atom → inspection_sets

**Writer:** `services/inspection_sets_svc/canonical_writer.py` `build_canonical_set_payload()`

**Payload fields set at INSERT:**

| Field | Value |
|-------|-------|
| factory_id | caller arg |
| company_id | caller arg |
| source | "LEGAL_ENGINE" |
| legal_obligation_atom_id | atom.atom_id |
| legal_operation_presentation | map_operation_presentation(raw) |
| inspection_set_name | obligation_detail.what (action text) |
| law_name | raw.law_name |
| law_article | raw.law_article |
| obligation_type | enrichment.obligation_type (INSPECT/ACTION/etc.) — raw value, no normalization |
| obligation_summary | action text |
| description | action text |
| cycle_unit | NULL (CASE C explicit) |
| cycle_value | NULL |
| schedule_anchor_date | NULL |
| anchor_confirmed | false |
| assignee_user_id | NULL |
| status_code | "PENDING_ANCHOR" |
| is_active | true |

**Fields NOT set by canonical_writer (new rows or refresh):**
```
inspection_category        = NOT SET by canonical_writer
                             Production: 83/395 LEGAL_ENGINE rows have non-null value
                             Origin of existing values: LEGACY_ORIGIN_UNRESOLVED
                             (canonical_writer.py _REFRESH_FIELDS does not include inspection_category;
                             existing values are preserved on refresh, not overwritten)
inspection_category_code   = NOT SET
equipment_set_id           = NOT SET
site_equipment_set_id      = NOT SET
form_code                  = NOT SET (column does not exist on inspection_sets)
asset_id                   = NOT SET (column does not exist on inspection_sets)
```

**MANUAL path:** `services/inspection_sets_svc/queries.py` `create_manual_set()`
- `inspection_category` = body.inspection_category (user-provided via API)
- `source` = "MANUAL"
- `obligation_type` = NOT set by create_manual_set() INSERT
- Production MANUAL row has obligation_type=INSPECT (created 2026-03-31, updated 2026-04-15)
  → origin unresolved: may be legacy writer, direct DB update, or separate API path
  → current obligation_type writer for MANUAL rows = NOT CONFIRMED (LEGACY_ORIGIN_UNRESOLVED)

---

## 3. Stage 2: inspection_sets → work_schedules

**Writer:** `services/inspection_sets_svc/law_engine.py` `run_generate_operation_schedules()`

Uses `_build_operation_schedule_row(iset, planned, rule)` from `inspection_sets_helpers.py`:

**Fields carried from inspection_sets to work_schedules:**

| Field | Carried as |
|-------|-----------|
| factory_id | factory_id |
| company_id | company_id |
| id | inspection_set_id |
| planned_date | computed from OTR |
| inspection_category | → obligation_type in work_schedules (display only) |
| assignee_user_id | → assigned_user_id |

**Fields NOT carried:**
```
work_schedules.form_code    = NOT SET by any writer (0/68 populated)
work_schedules.asset_id     = NOT SET by any writer (0/68 populated)
inspection_category         = used only as obligation_type label for the schedule row
```

---

## 4. Stage 3: work_schedules → safety_inspections

**Writer:** DB Function `fn_create_worker_inspection_record()`

**INSERT statement (Step 8):**
```sql
INSERT INTO public.safety_inspections
    (id, assignment_id, inspector_id, inspection_date, status_code, factory_id)
VALUES
    (gen_random_uuid(), p_schedule_id, p_inspector_id, p_submitted_at, 'COMPLETED', p_factory_id);
```

**Fields NOT set:**
```
safety_inspections.asset_id = NOT SET by fn_create_worker_inspection_record
                              Column exists (nullable uuid), but writer never populates it.
                              safety_inspections.asset_id = 0/5 rows in production.
```

---

## 5. Field Ownership Summary

| Field | Table | Writer | Current Population |
|-------|-------|--------|--------------------|
| source | inspection_sets | canonical_writer / queries.py | 396/396 |
| obligation_type | inspection_sets | canonical_writer (from LEG enrichment) | 396/396 |
| inspection_category | inspection_sets | LEGACY_ORIGIN_UNRESOLVED (canonical_writer: NOT SET; existing values in 83 LEGAL_ENGINE rows from unknown prior write) | 84/396 (21.2%) |
| inspection_category_code | inspection_sets | NO WRITER | 0/396 |
| equipment_set_id | inspection_sets | NO WRITER | 0/396 |
| site_equipment_set_id | inspection_sets | NO WRITER | 0/396 |
| form_code | work_schedules | NO WRITER | 0/68 |
| asset_id | work_schedules | NO WRITER | 0/68 |
| asset_id | safety_inspections | NO WRITER (fn_create omits) | 0/5 |

---

## 6. Key Constraints

```
inspection_sets.inspection_category
  = NOT SET by canonical_writer (any source path)
  = NOT in canonical_writer refresh fields → existing values survive refresh
  = 83/395 LEGAL_ENGINE rows have non-null value (LEGACY_ORIGIN_UNRESOLVED)
  = 1/1 MANUAL row has non-null value (user-provided via API or legacy update)
  = NOT a projection_type selector today (no explicit canonical mapping contract)

work_schedules.form_code
  = column exists, schema nullable text
  = NO production writer
  = 0/68 populated
  = design note: present for future use but no current creation contract

safety_inspections.asset_id
  = column exists, schema nullable uuid
  = fn_create_worker_inspection_record does NOT include it in INSERT
  = 0/5 populated in production
  = EQUIP projection_detail path is broken at creation stage
```
