---
title: PPE / CHK / INSP Source Boundary Analysis
status: FROZEN
version: 1
governed_by: WO-DOC-AUTO-SRC-02A
date: 2026-10-08
---

# PPE / CHK / INSP Source Boundary Analysis

## 1. Shared Source Architecture

```
document_type_registry (production verified):

doc_type  | fetcher_key  | evidence_source
----------+--------------+---------------------------------------------
INSP      | inspection   | safety_inspections + safety_inspection_results
CHK       | inspection   | safety_inspections + safety_inspection_results
PPE       | inspection   | safety_inspections
EQUIP     | inspection   | safety_inspections + safety_inspection_results (asset_id→equipment_assets)

Note from registry:
  CHK: "INSP와 동일 소스, 렌더 형식만 상이" (same source as INSP, render format only differs)
  EQUIP: "asset type_code 정리 별건" (asset type_code cleanup is a separate task)
```

All four projection types share InspectionFetcher. The discriminator must come from source data.

---

## 2. INSP vs CHK: No Source Discriminator

```
INSP discriminator today = NONE
CHK discriminator today  = NONE
```

Evidence:
- `inspection_sets.inspection_category` is 78% NULL (LEGAL_ENGINE rows)
- The canonical_writer does NOT set inspection_category
- No source field distinguishes "안전점검일지 (INSP)" from "점검 체크리스트 (CHK)"
- document_type_registry explicitly notes CHK and INSP use the same source
- CHECK_TYPE_MAP in inspection_sets_helpers.py maps obligation_type → check_type (PASS_FAIL/CHECK/DATE)
  — this is a UI rendering hint only, NOT a projection_type selector

Verdict:
```
INSP vs CHK source discriminator = NO CURRENT SOURCE DISCRIMINATOR
```

---

## 3. PPE: No Source Discriminator

```
PPE candidate fields checked:
  - inspection_category: populated for 84/396 rows (MANUAL only); no PPE-specific value confirmed
  - obligation_type: no obligation_type value maps specifically to PPE
  - inspection set source: MANUAL or LEGAL_ENGINE — does not indicate PPE
  - legal atom metadata: LEG DB schema not visible from taieng; enrichment.obligation_type carries INSPECT/ACTION/etc.
  - schedule metadata: work_schedules carries obligation_type from inspection_category or "GENERAL"
  - inspection set/template metadata: inspection_set_name is free text (action from obligation_detail.what); keyword inference = PROHIBITED
  - inspection_sets.inspection_category populated values include: FIRE, ELEC, SAFETY, BUILDING, HAZMAT, ENV, MACHINERY, WELFARE, INFRA — no PPE value observed

PPE discriminator today = NONE (no explicit discriminator found in any source field)
```

---

## 4. EQUIP: Partial Path Exists, Broken at Creation

```
EQUIP detection logic (design intent):
  safety_inspections.asset_id → equipment_assets.equipment_type_code/equipment_category → EQUIP detail
```

Current state:
```
safety_inspections.asset_id = 0/5 populated (column exists, writer omits)
work_schedules.asset_id     = 0/68 populated (column exists, no writer)
inspection_sets.equipment_set_id = 0/396 populated
```

`fn_create_worker_inspection_record` INSERT step:
```sql
INSERT INTO safety_inspections (id, assignment_id, inspector_id, inspection_date, status_code, factory_id)
-- asset_id is NOT in the column list
```

Verdict: EQUIP detection path is architecturally defined but creation contract is broken at all three stages.

---

## 5. Summary Table

| Projection | Explicit Discriminator | Source Field | Status |
|------------|------------------------|--------------|--------|
| INSP | NONE | — | NO CURRENT SOURCE DISCRIMINATOR |
| CHK | NONE | — | NO CURRENT SOURCE DISCRIMINATOR |
| PPE | NONE | — | NO CURRENT SOURCE DISCRIMINATOR |
| EQUIP | PARTIAL (asset_id) | safety_inspections.asset_id | PARTIAL — field exists, writer broken |

---

## 6. Forward Path Assessment

For INSP/CHK/PPE to become deterministic, a discriminator must be introduced at one of:
- Legal obligation atom enrichment (LEG domain: add projection_type to enrichment)
- inspection_set creation (add explicit doc_projection_type column, set at creation time)
- No later stage is safe because the information is not derivable from completion data alone

For EQUIP to become deterministic:
- `fn_create_worker_inspection_record` must include `asset_id` from the work_schedule or a caller-supplied parameter
- `work_schedules.asset_id` must be set by the law_engine materializer from `inspection_sets.equipment_set_id` or a linked equipment asset

Claude does not select the resolution path.
