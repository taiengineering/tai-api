---
class: records
type: report
scope: knowledge
project: risk
title: OBJ-RISK-03 canonical process task mapping contract
version: 1
status: active
owner: taiwang
---

# OBJ-RISK-03 — TAI Canonical Process/Task Contract + Controlled Source Mapping

MODEL D remains APPROVED / FROZEN. This WO designs TAI canonical PROCESS/TASK identity and a controlled mapping layer. It does not copy A/B/C into a source master, does not seed production canonical rows, and does not open RISK-04.

```text
WO-RISK-01           = PASS / CLOSED
WO-RISK-02           = PASS / CLOSED
WO-RISK-02-MERGE-001 = PASS / CLOSED
base main HEAD       = 2855091d5edd0dbcc8e558e4cd0cbd24ef66589a
OBJ-RISK             = IN_PROGRESS
RISK-03              = IN_PROGRESS
RISK-04              = NOT OPENED
production mutation  = 0
Graph mutation       = 0
Legal Engine mutation= 0
CHEM API calls       = 0
LLM                  = 0
fuzzy auto-map       = 0
AUTO APPROVED        = 0
MERGE                = NOT AUTHORIZED
```

---

## Existing process/task schema inventory

Searched migrations, routers, services, and RISK-01/02 evidence. No `CREATE TABLE` for `tai_process`, `tai_task`, `process_master`, or `canonical_process`.

| Object | Class | Identity / scope | Canonical-ready? |
| --- | --- | --- | --- |
| `companies` | INSTANCE | tenant UUID | NO |
| `factories` | INSTANCE | `company_id` 사업장 | NO |
| `factory_process` | INSTANCE | `factory_id`; `process_id` from DB/MANUAL/KCSC | NO — customer factory registration |
| `construction_sites` | INSTANCE | `company_id` / `factory_id` | NO |
| `construction_site_processes` | INSTANCE | `site_id`; optional `kcsc_process_id` | NO |
| `construction_works` | INSTANCE | site PTW / work occurrence | NO |
| `inspection_sets` | INSTANCE | `factory_id` + `company_id` | NO |
| `work_schedules` | INSTANCE | `(id, factory_id)` schedule | NO |
| `runtime_task` | INSTANCE | `tenant_id` + `facility_id` obligation execution | NO |
| `task_candidate` | INSTANCE | `factory_id` legal compiler draft | NO |
| `risk_assessments` | INSTANCE | SaaS 위험성평가 document | NO |
| `ksic_process_map` | SECTOR_SOURCE_MASTER | KSIC manufacturing process path | NO — KSIC-bound, not MODEL D TAI |
| `kcsc_process_master` | SECTOR_SOURCE_MASTER | `kcs_code` | NO — KCSC-bound |
| `kcsc_work_master` | SECTOR_SOURCE_MASTER | FK to KCSC process | NO |
| `risk_source_nodes` | SOURCE_NATIVE | `(source_id, source_key)` A/B/C | NO — RISK-02 forbids promoting to TAI master |
| `risk_records` | SOURCE_CONTENT | KALIS content → C TASK | NO — not a task taxonomy |

`operation_cycle` is not a table; it mutates `inspection_sets` cycle fields.

`task_master` has ALTER-only KST evidence and is not a RISK taxonomy DDL.

---

## INSTANCE vs CANONICAL boundary

```text
INSTANCE
  = customer/factory/site/runtime record
  example: 고객 A 공장 → 도장공정 in factory_process

CANONICAL CONCEPT
  = TAI-owned process/task identity
  example: TAI canonical → 도장
```

```text
INSTANCE ≠ CANONICAL CONCEPT
SOURCE TAXONOMY ≠ TAI CANONICAL TAXONOMY
SOURCE MATCH ≠ CANONICAL APPROVAL
```

A factory `factory_process` row may later *reference* a canonical node. This WO does not migrate customer rows.

---

## Physical model decision

```text
PHYSICAL MODEL DECISION = NEW_RISK_CANONICAL
```

Not `REUSE_EXISTING`: no source-independent global TAI process/task master exists.

Not `EXTEND_EXISTING`: extending `ksic_process_map`, `kcsc_*`, or `risk_source_nodes` would violate frozen MODEL D roles (A reference, B bridge, C risk context).

Not `BLOCKED`: non-existence of a TAI master is explicit in RISK-01 Q5 and RISK-02 migration comments.

Physical tables (git-pinned, production apply = 0):

```text
supabase/migrations/20260916_risk_canonical_mapping.sql

risk_canonical_nodes
risk_canonical_node_sectors
risk_source_mappings
```

RISK-02 `20260915_risk_source_catalog.sql` is not modified.

---

## Canonical identity contract

```text
internal id     = UUID
canonical_code  = optional TAI-owned stable identifier, nullable unique
SOURCE-DERIVED IDENTITY = 0
```

Forbidden as TAI canonical identity:

```text
SHA256(A/B/C source path)
A W-code
B path hash
C task hash
row number / 번호
timestamp
name hash
```

Rename and reparent keep the same `id`. Source change does not change canonical `id`.

`origin_type` ∈ {TAI_NATIVE, PROMOTED_FROM_SOURCE, MERGED_FROM_REVIEWED_SOURCES}. Source promotion still creates DRAFT, not ACTIVE.

---

## Canonical hierarchy contract

```text
node_kind ∈ {PROCESS, TASK}
PROCESS
  └─ PROCESS (optional sub-process)
      └─ TASK
```

Minimum fields: `id`, `canonical_code`, `node_kind`, `parent_id`, `name`, `name_normalized`, `description`, `status`, `metadata`.

Status ∈ {DRAFT, ACTIVE, RETIRED}. New nodes default DRAFT. Auto ACTIVE is forbidden.

This WO does not mix FACILITY / EQUIPMENT / CHEMICAL / LEGAL_OBLIGATION / RISK_RECORD into `node_kind`.

---

## Sector extensibility

`risk_canonical_node_sectors` is optional many-to-many. `sector_code` is free text.

Examples: BUILDING, MANUFACTURING, CONSTRUCTION.

No exclusive CONSTRUCTION CHECK enum on canonical nodes. TAI process/task is not locked to 건설정보분류체계.

---

## Mapping table contract

```text
source node (risk_source_nodes)
        ↓
risk_source_mappings
        ↓
risk_canonical_nodes
```

Fields: `source_id`, `source_key`, `canonical_id`, `mapping_type`, `mapping_status`, `mapping_method`, `evidence`, `metadata`.

FK:

```text
(source_id, source_key) → risk_source_nodes (source_id, source_key)
canonical_id → risk_canonical_nodes (id)  (NULL allowed only for NO_MATCH)
```

Cardinality: 1:1, 1:N, N:1 via explicit mapping rows. Unique `(source_id, source_key, canonical_id, mapping_type)`.

NO_MATCH persistence:

```text
NO_MATCH =
source node에 대해 현재 승인 가능한 canonical target이 없다는
controlled mapping evidence.
canonical_id = NULL
mapping_status = HOLD 또는 REJECTED
consumer eligible = NO
```

DB CHECK:

```text
NO_MATCH → canonical_id NULL and status HOLD/REJECTED
non-NO_MATCH → canonical_id NOT NULL
```

Partial unique index: one `NO_MATCH` row per source node.

NO_MATCH + APPROVED, NO_MATCH + target, and POSSIBLE_RELATED/EXACT_EQUIVALENT/AMBIGUOUS + NULL are forbidden.

This WO does not insert production mapping rows:

```text
production NO_MATCH rows = 0
production mapping rows = 0
```

Partial unique index: one `APPROVED + EXACT_EQUIVALENT` per source node.

No confidence column. Confidence would not equal approval.

---

## Mapping type / status

Types (RISK-01 set, no new meanings):

```text
EXACT_EQUIVALENT
PARENT_CHILD
BROADER_THAN
NARROWER_THAN
POSSIBLE_RELATED
NO_MATCH
AMBIGUOUS
```

Status:

```text
PROPOSED / APPROVED / REJECTED / HOLD
PROPOSED ≠ APPROVED
```

Consumer-eligible status = APPROVED only.

Methods: EXACT_PATH, EXACT_NAME, MANUAL_REVIEW.

Exact name or exact path against fixtures creates `PROPOSED` + `POSSIBLE_RELATED`. Never auto `EXACT_EQUIVALENT`. Never auto APPROVED.

Same normalized name in multiple canonical contexts → `AMBIGUOUS` / `HOLD`.

---

## A mapping behavior

```text
source_id  = CIC_W
source_key = native W code
```

W code is mapping evidence, not TAI canonical identity.

Analyzed nodes = 1722 (all W roots/mids/leaves).

---

## B HOLD behavior

```text
B identity              = HOLD
B raw rows              = 626
B path identities       = 620
B leaf occurrence sum   = 626
mapping unit            = 620 DETAIL_PROCESS path nodes
```

No `번호` identity. No 626 row-level unique mappings. The three collision paths remain one node each, with occurrence 3 preserved in RISK-02 membership.

---

## C mapping behavior

```text
C TASK NODE → TAI canonical TASK candidate
C risk record → C TASK (RISK-02 FK) → later canonical via that task
```

30696 content rows and 47559 occurrences are not canonicalized.

C task nodes analyzed = 761.

---

## Candidate generator

Local deterministic tool: `PYTHONPATH=. python3 tools/risk03/candidates.py`

Input: RISK-02 source nodes + two synthetic DRAFT fixtures (`토공사` PROCESS, `터파기` TASK). Production seed = NO.

Candidate classes: EXACT_PATH_CANDIDATE, EXACT_NAME_CANDIDATE, AMBIGUOUS, UNMATCHED.

Local census vs fixtures (not approval coverage):

```text
A source nodes analyzed   = 1722
A exact-path candidates   = 1
A exact-name candidates   = 0
A ambiguous               = 0
A unmatched               = 1721

B source nodes analyzed   = 620
B identity                = HOLD
B exact-path candidates   = 0
B exact-name candidates   = 0
B ambiguous               = 0
B unmatched               = 620

C task nodes analyzed     = 761
C exact-path candidates   = 0
C exact-name candidates   = 0
C ambiguous               = 0
C unmatched               = 761

APPROVED MAPPINGS         = 0
APPROVED COVERAGE         = NOT YET MEASURED
```

The single A exact-path hit is CIC_W `21` / `토공사` matching the synthetic PROCESS fixture path. It remains PROPOSED / POSSIBLE_RELATED.

C has no source task named exactly `터파기` in the official 47559-row file, so the synthetic TASK fixture produces no name hit. That is expected: fixtures are contract samples, not a construction taxonomy dump.

---

## Ambiguity

Fixture: two DRAFT TASK nodes both named `터파기` under different PROCESS parents. Same source name → AMBIGUOUS / HOLD. Leaf-name-only approval is forbidden.

---

## Determinism

Two full local runs on the same artifacts:

```text
DETERMINISM RUN 1 SHA = fc5d84c941e01ea6a5c48e17c7edf8f97c3e8fcc6207d334e841fdf81e4ee769
DETERMINISM RUN 2 SHA = fc5d84c941e01ea6a5c48e17c7edf8f97c3e8fcc6207d334e841fdf81e4ee769
DETERMINISM           = PASS
```

Proposal key = SHA256(source_id + source_key + canonical_id + mapping_type). No timestamps.

---

## Forbidden auto-mapping rules

```text
LLM / embedding / rapidfuzz / Levenshtein auto-match / semantic auto-merge = 0
identical name → EXACT_EQUIVALENT APPROVED = forbidden
source node exists → canonical ACTIVE = forbidden
A/B/C copied into canonical tables = forbidden
```

---

## Open issues

```text
Owner-approved TAI canonical seed does not exist yet.
APPROVED mapping coverage is NOT YET MEASURED.
factory_process / construction_site_processes instance→canonical links are not designed here.
B HOLD identity remains HOLD; mapping does not invent suffixes.
C portal metadata drift remains YES / CAUSE UNKNOWN (RISK-02).
```

---

## Next decision

RISK-04 candidate (not opened): Canonical Seed Review + Controlled Mapping Approval + Source Ingest Readiness.

Do not auto-start RISK-04 after this PR.

---

## Tests

`tests/test_risk03_canonical_mapping.py` covers inventory decision, UUID stability, consumer status, exact-name/path not auto-equivalent, ambiguity HOLD, B path-only HOLD, C record exclusion, no LLM/fuzzy logic, and full census when `artifacts/risk01` exists.

CI: `pytest tests/test_risk03_canonical_mapping.py`. Full census is skip-if-missing on GitHub runners.
