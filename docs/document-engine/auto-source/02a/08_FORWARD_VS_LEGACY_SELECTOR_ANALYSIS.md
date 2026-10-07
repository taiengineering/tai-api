---
title: Forward vs Legacy Selector Analysis
status: FROZEN
version: 3
governed_by: WO-DOC-AUTO-SRC-02A
date: 2026-10-08
corr: CORR-002 — INSP/CHK/PPE earliest stage unfrozen (GPT DESIGN REQUIRED for ALL projections); Stage 2 freeze removed
---

# Forward vs Legacy Selector Analysis

## 1. Separation Principle

```
A. Legacy rows (existing 396 inspection_sets + 5 safety_inspections)
   = incomplete discriminator data
   = LEGACY_UNRESOLVED for projection_type

B. Future newly created rows
   = can be deterministic IF creation contract is extended
   = FORWARD_DETERMINISTIC_POSSIBLE for some paths
```

These two problems are analyzed separately.

---

## 2. Legacy Rows

### 2a. Projection Type

```
Total inspection_sets = 396
LEGAL_ENGINE rows     = 395 (inspection_category: 83 non-null = LEGACY_ORIGIN_UNRESOLVED; 312 = NULL)
MANUAL rows           = 1   (inspection_category = FIRE; obligation_type = INSPECT, LEGACY_ORIGIN_UNRESOLVED)

inspection_category populated = 84/396 = 21.2%
  83 are LEGAL_ENGINE rows with values like: FIRE, ELEC, SAFETY, BUILDING, HAZMAT, ENV, MACHINERY, WELFARE, INFRA, etc.
    Origin: canonical_writer.py does NOT set inspection_category (not in payload or _REFRESH_FIELDS)
    These values come from a prior write path — LEGACY_ORIGIN_UNRESOLVED
  1 is the MANUAL row (FIRE — user-provided via API)
  These values do NOT directly map to INSP/CHK/EQUIP/PPE without an explicit contract.

obligation_type populated = 396/396
  Values: BEFORE_WORK (188), INSPECT (137), ACTION (54), PROHIBIT (4), APPOINT (4), REPORT (4), NOTIFY (2), DOCUMENT (1), OTHER (1)
  MANUAL row obligation_type = INSPECT (created 2026-03-31, updated 2026-04-15; LEGACY_ORIGIN_UNRESOLVED — create_manual_set() does not write obligation_type)
  NO obligation_type value maps deterministically to INSP/CHK/EQUIP/PPE.
```

**Legacy verdict: LEGACY_UNRESOLVED**
All 396 existing inspection_sets cannot have their projection_type determined without backfill inference.

### 2b. EQUIP asset_id

```
safety_inspections.asset_id = 0/5 populated
work_schedules.asset_id     = 0/68 populated
```

**Legacy verdict: LEGACY_UNRESOLVED**
No existing safety_inspection is linkable to an equipment_asset for EQUIP projection.

---

## 3. Forward-Deterministic Analysis

### 3a. When can projection_type first be determined?

The creation lifecycle stages:

```
Stage 1: Legal obligation atom (LEG DB)
  enrichment.obligation_type = INSPECT/ACTION/etc. → carries to inspection_sets.obligation_type
  enrichment has NO projection_type (doc_type) field today
  → projection_type NOT deterministic at Stage 1 (no carrier field in LEG enrichment)

Stage 2: inspection_set creation (canonical_writer.py)
  payload does NOT include inspection_category or doc_projection_type
  → projection_type NOT deterministic at Stage 2 (no field to carry it)

Stage 3: work_schedule creation (law_engine.py)
  carries inspection_category as obligation_type label only
  work_schedules.form_code = NO WRITER
  → projection_type NOT deterministic at Stage 3

Stage 4: safety_inspection creation (fn_create_worker_inspection_record)
  INSERT does NOT include asset_id
  → EQUIP path not deterministic at Stage 4
```

### 3b. Earliest deterministic point per projection_type

All four projection types: **earliest write boundary = GPT DESIGN REQUIRED**

Factual basis only (Claude does NOT design or freeze):
```
Stage 1 (LEG enrichment):
  projection discriminator does not currently exist in enrichment.obligation_type
  POSSIBLE if LEG enrichment extended with explicit doc_projection_type field

Stage 2 (inspection_set creation):
  projection discriminator does not currently exist in inspection_sets
  POSSIBLE if inspection_sets.doc_projection_type column added at creation time

Stage 3 (work_schedules):
  form_code / asset linkage not currently populated
  POSSIBLE if carried from inspection_set

Stage 4 (safety_inspection creation):
  fn_create_worker_inspection_record does not currently persist asset_id
  POSSIBLE for EQUIP if asset_id chain repaired
```

The authoring boundary (which stage to add the discriminator) and the persistence boundary (where to carry/store it) are GPT DESIGN REQUIRED for all four projections.

| projection_type | Factual current state | Forward possible | Earliest write boundary |
|----------------|----------------------|-----------------|------------------------|
| INSP | no discriminator in any stage | YES — requires new field | GPT DESIGN REQUIRED |
| CHK | no discriminator in any stage | YES — requires new field | GPT DESIGN REQUIRED |
| PPE | no discriminator in any stage | YES — requires new field | GPT DESIGN REQUIRED |
| EQUIP | asset_id broken at all stages; numeric code master EXISTS; code→detail NOT FOUND (GAP-02C) | YES — requires asset_id chain + detail resolver | GPT DESIGN REQUIRED |

### 3c. EQUIP forward path (specific)

```
Required changes (Claude does NOT select these — evidence only):

1. fn_create_worker_inspection_record: add asset_id to INSERT
   Source: worker app must supply asset_id from work_schedule or direct input

2. work_schedules.asset_id: need a writer
   Source: law_engine materializer must carry asset_id from inspection_set.equipment_set_id
   OR caller supplies it at schedule creation time

3. equipment_assets.equipment_type_code → EQUIP doc_detail resolver
   Required: canonical mapping table (numeric codes + named codes → FIRE/ELEC/CRANE/etc.)
   Numeric code master: EXPLICIT_MASTER EXISTS (system_codes category=equipment_type; 40 rows; 001=변압기...040=기타)
   Named uppercase codes (CRANE/PRESS/PRESSURE_VESSEL/CONVEYOR): NOT in system_codes (UNRESOLVED_ORIGIN)
   Code → EQUIP doc_detail mapping: NOT FOUND (GAP-02C; GPT DESIGN REQUIRED)
```

### 3d. INSP/CHK/PPE forward path (specific)

```
Required paths are GPT DESIGN REQUIRED.

Factual constraints only (Claude does NOT design):

Option A (Stage 1): Extend LEG enrichment with doc_projection_type
  = POSSIBLE — carries earliest authoring boundary to LEG domain
  = requires LEG domain change

Option B (Stage 2): Add inspection_sets.doc_projection_type column
  = POSSIBLE — earliest within taieng scope
  = requires canonical_writer.py update + DB migration

Option C (Stage 2+): Post-creation classification service
  = POSSIBLE — decouples projection assignment from creation
  = requires classification rules from GPT판정 + separate implementation

Claude does not select between A/B/C.
Authoring boundary decision = GPT판정 (AUTO-SRC-02B).
```

---

## 4. Backfill Inference

```
backfill_inference_required = YES for legacy rows
  No existing source field allows deterministic projection_type assignment for legacy data.
  Classification requires external rule definition (GPT판정).

backfill_LLM_inference = PROHIBITED
  Only explicit canonical code / source field / master mapping permitted.
  name similarity / keyword matching = NOT PERMITTED.

backfill approach:
  LEGACY rows that cannot be deterministically resolved → UNRESOLVED_TYPE
  They remain invisible in AUTO document library (fail-closed per AUTO-SRC-01 contract).
```

---

## 5. Summary

```
Legacy rows (396 inspection_sets):
  projection_type deterministic  = NO (LEGACY_UNRESOLVED for all)
  EQUIP asset_id deterministic   = NO (LEGACY_UNRESOLVED)

Future rows:
  EQUIP projection_type deterministic  = FORWARD_DETERMINISTIC_POSSIBLE (requires asset_id chain + resolver)
  INSP/CHK/PPE projection_type         = FORWARD_DETERMINISTIC_POSSIBLE (requires discriminator field)
  Earliest deterministic stage         = GPT DESIGN REQUIRED (all four: INSP / CHK / PPE / EQUIP)

LLM/name inference used = NO
```
