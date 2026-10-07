---
title: AUTO-SRC-02A Final Evidence
status: CLOSED FINAL / GPT PASS / 100%
version: 4
governed_by: WO-DOC-AUTO-SRC-02A
date: 2026-10-08
closed: CORR-003 PASS — GAP numbering, lowercase wording, all projection boundaries GPT DESIGN REQUIRED
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
  EQUIP        = YES if asset_id chain repaired + code→doc_detail resolver (GAP-02C)
  INSP/CHK/PPE = YES if discriminator field added (LEG enrichment or inspection_sets)

  Earliest deterministic stage:
    INSP/CHK/PPE = GPT DESIGN REQUIRED (Stage 1/2/3 all possible depending on authoring boundary)
    EQUIP        = GPT DESIGN REQUIRED (asset_id chain stage + detail resolver design)
```

---

## E. EQUIPMENT DETAIL

```
numeric code master (001-040):
  = EXPLICIT_MASTER EXISTS (CORR-001: previously stated MASTER_NOT_FOUND — error)
  = system_codes(category=equipment_type): 40 rows; 001=변압기, 008=전동기, 011=펌프, 013=열교환기,
    014=보일러, 021=크레인, 024=컨베이어, 025=승강기, 031=스프링클러, 038=압력용기, 040=기타 (full list)
  = 2,935 equipment_assets rows have numeric type_code joinable to system_codes
  = code → EQUIP doc_detail mapping: NOT FOUND (GAP-02C)

named uppercase codes (CRANE/PRESS/PRESSURE_VESSEL/CONVEYOR):
  = EXPLICIT_LEGACY_ALIAS (CORR-002)
  = canonicalizer.py _ALIAS_TO_NUMERIC: CRANE→021 / CONVEYOR→024 / PRESS→023 / PRESSURE_VESSEL→038
  = validates through EQUIPMENT_AUTHORITY_CODES (store.py)
  = new writes: normalized to numeric before storage
  = legacy rows: may still have uppercase string in equipment_type_code
  = doc_detail: still NOT FOUND (GAP-02C)

lowercase/free-text legacy codes (crane/boiler/forklift/etc.):
  = LEGACY_OR_ALTERNATE_ORIGIN_UNRESOLVED (CORR-002: not "user-entered strings")
  = current canonical authority validation REJECTS these (EquipmentSourceValidationError)
  = origin of existing rows: prior write path — LEGACY_OR_ALTERNATE_ORIGIN_UNRESOLVED
  = NOT the same as the uppercase alias path

equipment code → boolean fact registry (services/equipment_source/registry.py):
  = ACTIVE CODE CONTRACT (010/014/023/024/038 → has_emergency_gen/has_boiler/has_press/has_conveyor/has_pressure_vessel)
  = maps code → LEG diagnosis boolean fact; NOT → AUTO EQUIP doc_detail

historical equipment_type_inspection_map SQL:
  = design artifact (docs/sql/20260331_... / 20260401_...)
  = maps type_code → inspection_master.equipment_std (NOT doc_detail)
  = production table = DOES NOT EXIST

canonical equipment code source    = system_codes(category=equipment_type) for numeric codes
                                     EXPLICIT_LEGACY_ALIAS for CRANE/PRESS/CONVEYOR/PRESSURE_VESSEL
                                     LEGACY_OR_ALTERNATE_ORIGIN_UNRESOLVED for lowercase/free-text
detail mapping table exists        = NO EXISTING CANONICAL MAPPING (code → EQUIP doc_detail)
mapping consumer exists            = NONE CONFIRMED

GAP-02 reclassified:
  GAP-02A (numeric code authority) = RESOLVED (system_codes 40 rows)
  GAP-02B (uppercase alias authority) = RESOLVED (canonicalizer EXPLICIT_LEGACY_ALIAS)
  GAP-02C (code → AUTO EQUIP doc_detail) = OPEN

resolved detail candidates         = 0
unresolved                         = all codes (doc_detail mapping NOT FOUND)
```

---

## F. LEGACY VS FORWARD

```
legacy rows deterministic           = NO
  inspection_category LEGAL_ENGINE NULL = 312/395 (83/395 LEGAL_ENGINE non-null = LEGACY_ORIGIN_UNRESOLVED)
  inspection_category MANUAL non-null   = 1/1 (FIRE; obligation_type origin = LEGACY_ORIGIN_UNRESOLVED)
  obligation_type does not map to projection_type
  asset_id = 0 across all tables in chain

future rows can be deterministic:
  INSP/CHK/PPE = YES — authoring/write boundary = GPT DESIGN REQUIRED
  EQUIP        = YES — asset_id chain repair + code→doc_detail resolver = GPT DESIGN REQUIRED

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
  NOT a code→EQUIP doc_detail selector (GAP-02C)

canonicalizer (services/equipment_source/canonicalizer.py):
  ACTIVE CODE CONTRACT
  CRANE→021 / CONVEYOR→024 / PRESS→023 / PRESSURE_VESSEL→038 (EXPLICIT_LEGACY_ALIAS)
  lowercase/free-text → rejected (LEGACY_OR_ALTERNATE_ORIGIN_UNRESOLVED)
  NOT a doc_detail selector

equipment_source registry (services/equipment_source/registry.py):
  ACTIVE CODE CONTRACT (5 codes → boolean facts)
  010/014/023/024/038 → has_emergency_gen/has_boiler/has_press/has_conveyor/has_pressure_vessel
  NOT a doc_detail selector

historical equipment_type_inspection_map SQL:
  Design artifact only — production table DOES NOT EXIST
  Maps type_code → inspection_master.equipment_std (NOT doc_detail)

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
AUTO-SRC-02A = CLOSED FINAL / GPT PASS / 100%

GPT independent verify = PASS (CORR-003)

AUTO-SRC-02B (Selector Implementation) = BLOCKED
  Requires GPT판정:
    1. Projection type selector rule (INSP vs CHK vs PPE vs EQUIP)
    2. Forward authoring/write boundary (all four projections = GPT DESIGN REQUIRED)
    3. Equipment detail resolver (code → AUTO EQUIP doc_detail mapping, GAP-02C)
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
                 Remaining gap = code → EQUIP doc_detail mapping (historical v2 naming: GAP-02B; current naming: GAP-02C; NOT FOUND)
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

---

## K. CORR-002 DELTA

```
version: 2 → 3
corr_id: CORR-002

FIND-01 (uppercase alias canonicalizer):
  v2 claim: CRANE/PRESS/CONVEYOR/PRESSURE_VESSEL = UNRESOLVED_ORIGIN
  CORR-002 fact: services/equipment_source/canonicalizer.py contains EXPLICIT_LEGACY_ALIAS contract
                 CRANE→021 / CONVEYOR→024 / PRESS→023 / PRESSURE_VESSEL→038
                 Status = ACTIVE CODE CONTRACT
  Files corrected: 02, 05, 06, 07, 09

FIND-02 (lowercase/free-text code origin):
  v2 claim: "user-entered strings" (implies normal API input)
  CORR-002 fact: current canonical authority validation REJECTS lowercase/free-text
                 store.py EQUIPMENT_AUTHORITY_CODES excludes lowercase
                 Status = LEGACY_OR_ALTERNATE_ORIGIN_UNRESOLVED
  Files corrected: 05, 06, 09

FIND-03 (equipment_source registry):
  NEW: services/equipment_source/registry.py ACTIVE CODE CONTRACT
  010→has_emergency_gen / 014→has_boiler / 023→has_press / 024→has_conveyor / 038→has_pressure_vessel
  Contracts: code → LEG boolean fact (NOT → AUTO doc_detail)
  Files added: 07, 09

FIND-04 (historical equipment_type_inspection_map SQL):
  NEW: docs/sql/20260331_... / 20260401_... design artifacts
  Maps type_code → inspection_master.equipment_std (NOT doc_detail)
  Production table = DOES NOT EXIST
  Files added: 07, 09

FIND-05 (numeric row count corrections):
  v2 claim (sum 2,929):
    007 = 54 / 019 = 0 / 027 = 0 / 033 = 28 / 040 = 800
  CORR-002 fact (sum 2,935; GPT independent verification snapshot 2026-10-08):
    007 = 55 / 019 = 1 / 027 = 1 / 033 = 29 / 040 = 802
  Note: production DB unreachable during CORR-002 (timeout); snapshot from GPT verify
  Files corrected: 05

FIND-06 (INSP/CHK/PPE earliest stage freeze):
  v2 claim: "INSP/CHK/PPE earliest = Stage 2 (inspection_set creation)"
  CORR-002 fact: This is a design decision; not a factual finding
                 LEG enrichment (Stage 1) is also a valid authoring boundary
                 All four projections = GPT DESIGN REQUIRED
  Files corrected: 08, 09

FIND-07 (GAP-02 reclassification):
  v2: GAP-02B = code→doc_detail mapping
  CORR-002: Split into:
    GAP-02A = numeric code authority = RESOLVED (system_codes)
    GAP-02B = uppercase alias authority = RESOLVED (canonicalizer)
    GAP-02C = code → AUTO EQUIP doc_detail = OPEN
  Files corrected: 09

DB write     = 0
Code change  = 0
Migration    = 0
```
