---
title: AUTO-SRC-02A Final Evidence
status: CORR-001 COMPLETE — GPT VERIFY REQUIRED
version: 2
governed_by: WO-DOC-AUTO-SRC-02A
date: 2026-10-08
corr: CORR-001 — inspection_category LEGAL_ENGINE 83 non-null (LEGACY_ORIGIN_UNRESOLVED); MANUAL obligation_type origin unconfirmed; system_codes numeric master EXISTS (not MASTER_NOT_FOUND); document_type_mapping 30 rows (not 29); EQUIP earliest stage unfrozen
---

# WO-DOC-AUTO-SRC-02A RESULT

## A. GIT

```
base branch = docs/doc-auto-src-01-readmodel-design
base HEAD   = c35be3b5c19481a8623e1ba7b6af23061a2fc281

branch = docs/doc-auto-src-02a-projection-selector-discovery
HEAD   = (this commit)

changed files:
  docs/document-engine/auto-source/02a/01_INSPECTION_CREATION_LINEAGE.md
  docs/document-engine/auto-source/02a/02_PROJECTION_DISCRIMINATOR_MATRIX.csv
  docs/document-engine/auto-source/02a/03_OBLIGATION_TYPE_EVIDENCE.csv
  docs/document-engine/auto-source/02a/04_PPE_CHK_INSP_BOUNDARY.md
  docs/document-engine/auto-source/02a/05_EQUIPMENT_CODE_SOURCE_MATRIX.csv
  docs/document-engine/auto-source/02a/06_EQUIPMENT_DETAIL_MAPPING_CANDIDATES.csv
  docs/document-engine/auto-source/02a/07_EXISTING_MAPPING_CENSUS.md
  docs/document-engine/auto-source/02a/08_FORWARD_VS_LEGACY_SELECTOR_ANALYSIS.md
  docs/document-engine/auto-source/02a/09_AUTO_SRC02A_FINAL_EVIDENCE.md
```

---

## B. INSPECTION SOURCE

```
inspection_sets total           = 396
source populated                = 396/396
obligation_type populated       = 396/396
inspection_category populated   = 84/396 (21.2%)
  LEGAL_ENGINE non-null         = 83/395 (LEGACY_ORIGIN_UNRESOLVED — canonical_writer does NOT set inspection_category)
  MANUAL non-null               = 1/1 (FIRE — user-provided via API; obligation_type = INSPECT, LEGACY_ORIGIN_UNRESOLVED)
  LEGAL_ENGINE NULL             = 312/395
inspection_category_code        = 0/396 (all NULL)

equipment_set_id populated      = 0/396
site_equipment_set_id populated = 0/396

legal_rule_id populated         = 315/396
legal_obligation_atom_id        = 69/396

work_schedules total            = 68
form_code populated             = 0/68
asset_id populated              = 0/68
inspection_set_id populated     = 62/68

safety_inspections total        = 5
asset_id populated              = 0/5
assignment_id populated         = 4/5
```

---

## C. CREATION LINEAGE

```
inspection_set writer:
  LEGAL_ENGINE = canonical_writer.py → build_canonical_set_payload()
  MANUAL       = queries.py → create_manual_set()

schedule writer:
  law_engine.py → run_generate_operation_schedules()
  uses _build_operation_schedule_row() from inspection_sets_helpers.py

inspection writer:
  fn_create_worker_inspection_record() (DB function)
  INSERT: (id, assignment_id, inspector_id, inspection_date, status_code, factory_id)
  asset_id NOT included in INSERT

source field ownership:
  inspection_sets.source          = canonical_writer (LEGAL_ENGINE) / queries.py (MANUAL)
  inspection_sets.obligation_type = canonical_writer from LEG enrichment.obligation_type
                                    MANUAL row: obligation_type = INSPECT (LEGACY_ORIGIN_UNRESOLVED — create_manual_set() does NOT write obligation_type)
  inspection_sets.inspection_category = queries.py body (MANUAL — user-provided); NOT set by canonical_writer
                                         83/395 LEGAL_ENGINE rows have non-null value = LEGACY_ORIGIN_UNRESOLVED (prior write path; canonical_writer _REFRESH_FIELDS does not include inspection_category)

asset_id chain:
  inspection_sets.equipment_set_id  = 0/396 (no writer)
  work_schedules.asset_id           = 0/68 (no writer)
  safety_inspections.asset_id       = 0/5 (fn_create INSERT omits it)

work_schedules.form_code:
  = 0/68 populated
  = no current writer
  = column exists (nullable text) — no creation contract confirmed
```

---

## D. PROJECTION TYPE

```
INSP explicit discriminator     = NONE
CHK explicit discriminator      = NONE
PPE explicit discriminator      = NONE
EQUIP explicit discriminator    = PARTIAL (asset_id field exists; all writers broken)

CHK vs INSP:
  document_type_registry: "CHK = same source as INSP, render format only differs"
  NO source-level field distinguishes CHK from INSP

deterministic today             = NO (for all four: INSP/CHK/PPE/EQUIP)

forward deterministic possible:
  EQUIP  = YES if asset_id chain repaired (fn_create + law_engine + resolver table)
  INSP/CHK/PPE = YES if discriminator field added to LEG enrichment or inspection_sets at creation
  Earliest deterministic stage:
    INSP/CHK/PPE = Stage 2 (inspection_set creation)
    EQUIP        = Stage 4 (safety_inspection creation with asset_id)
```

---

## E. EQUIPMENT DETAIL

```
numeric code master (001-040):
  = EXPLICIT_MASTER EXISTS (CORR-001: previously stated MASTER_NOT_FOUND — error)
  = system_codes(category=equipment_type): 40 rows; 001=변압기, 008=전동기, 011=펌프, 013=열교환기,
    014=보일러, 021=크레인, 024=컨베이어, 025=승강기, 031=스프링클러, 038=압력용기, 040=기타 (full list)
  = 2,935 equipment_assets rows have numeric type_code joinable to system_codes
  = code → EQUIP doc_detail mapping: NOT FOUND (GAP-02B)

named code master (CRANE/PRESS/PRESSURE_VESSEL/CONVEYOR):
  = No formal master table; NOT in system_codes
  = equipment_assets.equipment_category populated for ~1,200 rows
  = categories (MACHINE/FIRE/ELECTRICAL/TRANSPORT) do NOT map to EQUIP doc_detail
  = Suspected test/seed data — category values inconsistent with EQUIP detail schema

lowercase user-entered codes (crane/boiler/forklift/etc.):
  = user-entered strings
  = no formal master; NOT in system_codes
  = different values from uppercase named codes and numeric codes

canonical equipment code source    = system_codes(category=equipment_type) for numeric codes
                                     UNRESOLVED_ORIGIN for named uppercase and lowercase codes
detail mapping table exists        = NO EXISTING CANONICAL MAPPING (code → EQUIP doc_detail)
mapping consumer exists            = NONE CONFIRMED

resolved detail candidates         = 0
ambiguous                          = all named + lowercase codes (UNRESOLVED_ORIGIN or INCONSISTENT_CATEGORY)
unresolved                         = all numeric codes (name known; doc_detail mapping NOT FOUND)
```

---

## F. LEGACY VS FORWARD

```
legacy rows deterministic           = NO
  inspection_category LEGAL_ENGINE NULL = 312/395 (83/395 LEGAL_ENGINE non-null = LEGACY_ORIGIN_UNRESOLVED)
  inspection_category MANUAL non-null   = 1/1 (FIRE; obligation_type origin = LEGACY_ORIGIN_UNRESOLVED)
  obligation_type does not map to projection_type
  asset_id = 0 across all tables in chain

future rows can be deterministic at:
  INSP/CHK/PPE = Stage 2 (inspection_set creation, with new discriminator field)
  EQUIP        = Stage 4 (safety_inspection creation, with asset_id chain)

backfill inference required         = YES (for legacy rows to be classified)
  Method: external rule definition (GPT판정) then explicit mapping — NOT name/keyword inference

LLM/name inference used = NO
```

---

## G. EXISTING MAPPING

```
inspection → projection_type mapping table = NO EXISTING CANONICAL MAPPING
equipment → detail mapping table           = NO EXISTING CANONICAL MAPPING

obligation_form_mapping:
  EXISTS (11 rows)
  Maps: obligation_code (ELEC_MGR_APPOINT/FIRE_MGR_REPORT/etc.) → form_code
  NOT a projection_type selector
  Not connected to INSP/CHK/EQUIP/PPE
  No active consumer code confirmed

document_type_registry:
  EXISTS (8 rows)
  Defines doc_type metadata + fetcher binding
  NOT a source→projection selector

document_type_mapping:
  EXISTS (30 rows) (CORR-001: previously stated 29)
  Maps doc_id → doc_type + doc_detail
  NOT a source_record→projection selector

system_codes(category=equipment_type):
  EXISTS (40 rows) (CORR-001: previously stated MASTER_NOT_FOUND)
  Maps numeric code (001-040) → Korean canonical name
  NOT a code→EQUIP doc_detail selector (GAP-02B)

existing writer for projection mapping = NONE
existing consumer for projection mapping = NONE
```

---

## H. MUTATION

```
DB write         = 0
Storage write    = 0
migration        = 0
code change      = 0
```

---

## I. FINAL

```
AUTO-SRC-02A = CORR-001 COMPLETE

GPT independent verify = REQUIRED

AUTO-SRC-02B (Selector Implementation) = BLOCKED
  Requires GPT판정:
    1. Projection type selector rule (INSP vs CHK vs PPE vs EQUIP)
    2. Forward write boundary (where to add discriminator field)
    3. Equipment detail resolver (numeric code → EQUIP detail mapping, GAP-02B)
    4. Legacy backfill policy (UNRESOLVED_TYPE or partial backfill)

AUTO-SRC-03 = BLOCKED (GAP-03)
```

---

## J. CORR-001 DELTA

```
version: 1 → 2
corr_id: CORR-001

ERROR-01 (inspection_category LEGAL_ENGINE population):
  v1 claim: "inspection_category NULL for all LEGAL_ENGINE rows" / "LEGAL_ENGINE = MANUAL only"
  CORR-001 fact: 83/395 LEGAL_ENGINE rows have non-null inspection_category
                 Origin = LEGACY_ORIGIN_UNRESOLVED (canonical_writer does NOT set this field;
                 existing values survive refresh; prior write path unknown)
  Files corrected: 01, 02, 04, 08, 09

ERROR-02 (MANUAL obligation_type writer):
  v1 claim: obligation_type set by create_manual_set()
  CORR-001 fact: create_manual_set() does NOT write obligation_type
                 MANUAL row has obligation_type = INSPECT (created 2026-03-31, updated 2026-04-15)
                 Origin = LEGACY_ORIGIN_UNRESOLVED
  Files corrected: 01, 09

ERROR-03 (numeric equipment code master):
  v1 claim: numeric 001-040 = MASTER_NOT_FOUND; no canonical lookup table in taieng DB
  CORR-001 fact: system_codes(category=equipment_type) EXISTS with 40 rows
                 Maps numeric codes 001-040 → Korean canonical names
                 2,935 equipment_assets joinable to system_codes
                 Remaining gap = code → EQUIP doc_detail mapping (GAP-02B; NOT FOUND)
  Files corrected: 05 (COMPLETE REWRITE), 06, 07, 08, 09

ERROR-04 (document_type_mapping count):
  v1 claim: 29 rows
  CORR-001 fact: 30 rows
  Files corrected: 07, 09

ERROR-05 (EQUIP earliest deterministic stage freeze):
  v1 claim: "EQUIP earliest deterministic stage = Stage 4" (frozen as fact)
  CORR-001 fact: This is a design decision requiring GPT판정; not a frozen factual finding
  Files corrected: 08, 09

DB write     = 0
Code change  = 0
Migration    = 0
```
