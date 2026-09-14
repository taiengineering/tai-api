---
class: records
type: report
scope: knowledge
project: risk
title: OBJ-RISK-02 source catalog snapshot and identity core
version: 1
status: active
owner: taiwang
---

# OBJ-RISK-02 — Source Catalog / Snapshot / Identity Core

MODEL D remains APPROVED / FROZEN. This WO does not create TAI canonical process/task or A↔B↔C mapping.

```text
WO-RISK-01           = PASS / CLOSED
WO-RISK-02-CHG1      = LOCAL PASS / PR OPEN
base main HEAD       = ed2c4ac810ce02025c1bfedb618b5e9c24c7270f
previous RISK-02 HEAD= d9777b7ee81a0d8a23e295fdc5f7640a764ae9f6
OBJ-RISK             = IN_PROGRESS
RISK-02              = PASS CANDIDATE
RISK-03              = NOT OPENED
production mutation  = 0
Graph mutation       = 0
Legal Engine mutation= 0
CHEM API calls       = 0
LLM                  = 0
fuzzy                = 0
MERGE                = NOT AUTHORIZED
```

---

## Existing schema inventory

Searched migrations/models for knowledge, taxonomy, catalog, snapshot, source, content, graph, risk.

| Existing object | Reuse? | Reason |
| --- | --- | --- |
| `csi_accident_cases` / `_snapshots` / `_snapshot_items` | PATTERN ONLY | Catalog + snapshot + membership. Membership PK uses `row_number`, which RISK-02 forbids as stable identity. Different object. |
| `kosha_msds_chemicals` / `_snapshots` / `_snapshot_items` | NO | CHEM HOLD. `source_key=chemId`. Do not open CHEM-04. |
| `kosha_guide_snapshots` | PATTERN ONLY | Current = latest COMPLETED. GUIDE catalog is a different source. |
| `knowledge_relation_runs/edges/evidence` | NO | Graph. RISK-02 Graph mutation = 0. |
| `menu_catalog` | NO | UI menu, not knowledge source. |
| `risk_*` tables | NONE EXISTED | New family required. |

UUID convention in existing catalogs: internal PK `gen_random_uuid()`, source identity is `source_id` + `source_key` / `content_id`. JSONB used for lossless payloads (`raw_json`, `payload_json`).

```text
EXISTING SCHEMA REUSE = PARTIAL
chosen family         = risk_*
```

---

## Chosen physical schema

Git-pinned (not production-applied):

```text
supabase/migrations/20260915_risk_source_catalog.sql
```

| Logical entity | Table |
| --- | --- |
| SOURCE CATALOG | `risk_sources` |
| SOURCE SNAPSHOT | `risk_snapshots` |
| SOURCE NODE | `risk_source_nodes` |
| SOURCE RECORD | `risk_records` (KALIS content only) |
| SNAPSHOT MEMBERSHIP | `risk_snapshot_memberships` |

Current pointer: view `risk_accepted_snapshots` = latest ACCEPTED per `source_id` by `published_or_modified_date`, then `source_sha256`. No `PUBLISHED` status.

Internal UUID is PK only. `source_key` / `content_key` are identities.

No `created_at` / `downloaded_at` columns. Snapshot dates are official calendar dates from RISK-01 evidence, not a runtime clock.

---

## Source catalog contract

| source_id | source_role | rights_status | display | redistribution |
| --- | --- | --- | --- | --- |
| CIC_W | REFERENCE_CLASSIFICATION | CONDITIONAL | CONDITIONAL | CONDITIONAL |
| KOSHA_CONSTRUCTION_PROCESS | USEFUL_BRIDGE | CLEAR | CONDITIONAL | CONDITIONAL |
| KALIS_RISK_PROFILE | RISK_CONTEXT_SOURCE | CLEAR | CONDITIONAL | CONDITIONAL |

Attribution required = true for all three.

Hierarchies stored separately:

```text
A: W_ROOT → W_MID → W_LEAF
B: PROJECT_KIND → WORK_TYPE → DETAIL_PROCESS
C: WORK_BIG → WORK_MID → TASK
```

No cross-source merge.

---

## Snapshot contract

```text
status ∈ {STAGED, VALIDATED, ACCEPTED, REJECTED}
identity of a file version = source_id + source_sha256
C metadata preserves simultaneously:
  official file rows     = 47559
  portal row field       = 41239
  legacy prose count     = 55546
  current prose          = approximately 47000
  metadata_drift         = true
  cause                  = UNKNOWN
```

Local dry-run DB WRITE = 0. Planner only.

---

## A identity

```text
source_id     = CIC_W
source_key    = native W code
native_code   = same as source_key
nodes         = 1722
roots         = 62
leaves        = 1287
duplicate source_key = 0
null source_key      = 0
orphan parent        = 0
nonnull / unique / hierarchical / parent resolvable = PASS
identity      = PASS
SHA256        = bef821019cd32ad9512f865d179852652d1f7aa9536be41b68c6e403fe0baa29
```

---

## B identity

`번호` is excluded from identity.

Normalized path = `공사종류 > 공종명 > 세부공정명`.

```text
rows                  = 626
path identities       = 620
duplicate path groups = 3
rows in duplicate paths = 9
null component count  = 0
orphan parent         = 0
identity              = HOLD
```

Exact collisions (번호 listed only as collision evidence, not as identity):

```text
빌딩 > 조적 > 미장 및 견출작업     n=3  번호 148,149,150
아파트 > 조적 > 미장 및 견출작업   n=3  번호 36,37,38
지하철 > 조적 > 미장 및 견출작업   n=3  번호 455,456,457
```

No `-1` / `-2` / row-number suffix was added. Leaf nodes stored = 620 unique paths, not 626 fake keys.

Occurrence is preserved separately from identity:

```text
B raw rows                  = 626
B leaf membership rows      = 620
B leaf occurrence sum       = 626
B duplicate extras          = 6
B occurrence preservation   = PASS
B identity                  = HOLD
```

`DETAIL_PROCESS` membership uses normalized full-path source row count. The three collision paths have `occurrence_count=3`. Unique paths have `occurrence_count=1`. `PROJECT_KIND` / `WORK_TYPE` stay taxonomy nodes with `occurrence_count=1` and are not inflated to source row counts.

KOSHA catalog metadata records HOLD so consumers do not treat B as PASS identity:

```json
{
  "identity_status": "HOLD",
  "duplicate_path_groups": 3,
  "rows_in_duplicate_paths": 9
}
```

---

## C identity

```text
source_id              = KALIS_RISK_PROFILE
content_key            = SHA256(canonical 19-field tuple, U+241F join)
raw rows               = 47559
unique content         = 30696
duplicate groups       = 5730
duplicate extras       = 16863
membership rows        = 30696
occurrence sum         = 47559
raw 19 fields preserved= YES
orphan task link       = 0
content identity       = PASS
SHA256                 = 399dbe64dcf1b5d1445fd51e968070dd26e0a40583f8e0afc5e9219839c958c8
```

Lossless gate:

```text
SUM(occurrence_count) = 47559
unique membership     = 30696
```

Duplicates are CONTENT DEDUP + SOURCE OCCURRENCE PRESERVATION. Not data loss.

`risk_records.task_source_key` points at native C TASK nodes. That is not TAI canonical mapping.

H/M/L stored as source-native `사고가능성` / `사고심각성` strings.

---

## Dry-run metrics

Command: `PYTHONPATH=. python3 tools/risk02/plan_source_core.py`

```text
A nodes                 = 1722
B rows                  = 626
B path identities       = 620
B leaf membership rows  = 620
B leaf occurrence sum   = 626
B duplicate extras      = 6
B identity              = HOLD
B occurrence preservation = PASS
C raw rows              = 47559
C content entities      = 30696
C duplicate groups      = 5730
C duplicate extras      = 16863
C occurrence sum        = 47559
DB WRITE                = 0
```

---

## Referential integrity

```text
A orphan parent              = 0
B orphan parent              = 0
C orphan task link           = 0
A duplicate source_key       = 0
B/C null keys                = 0
snapshot membership orphan   = 0
record without snapshot      = 0
```

DB constraints (git-pinned, production apply = 0):

```text
risk_snapshots UNIQUE (id, source_id)
risk_snapshot_memberships
  FOREIGN KEY (snapshot_id, source_id)
  REFERENCES risk_snapshots (id, source_id)
risk_records
  FOREIGN KEY (source_id, task_source_key)
  REFERENCES risk_source_nodes (source_id, source_key)
```

Cross-source membership (CIC_W snapshot + KALIS member) is prohibited by the snapshot/source composite FK.

Polymorphic `member_key` (NODE vs RECORD) has no new trigger. Member target existence remains the planner gate `snapshot membership orphan = 0`.

B path collisions are identity HOLD, not hidden orphans. HOLD identity and PASS occurrence preservation are separate.

---

## Determinism

Two full dry-runs on the same artifacts after CHG1:

```text
DETERMINISM RUN 1 SHA = 886d45cdaaf9478d066f22e2bfca3ee35128d5bfbda2eddfff664f87ffa7bbfa
DETERMINISM RUN 2 SHA = 886d45cdaaf9478d066f22e2bfca3ee35128d5bfbda2eddfff664f87ffa7bbfa
DETERMINISM           = PASS
```

Previous RISK-02 SHA `fd19e4d329682285abbfab4d2602e6a74bbbd8aca6a827acec1d4705fa082e0a` changed because B leaf occurrence entered the payload. The gate is RUN1 == RUN2.

Hash inputs exclude timestamps, UUIDs, row numbers, `downloaded_at`.

---

## Rights metadata

Stored on `risk_sources` as catalog columns. Values frozen from RISK-01. Not rewritten.

---

## Open issues

```text
B IDENTITY HOLD
  3 normalized path groups collide (9 rows, 6 extras).
  Occurrence on those paths is preserved (leaf occurrence sum = 626).
  Do not invent suffixes in RISK-02.

C portal metadata drift remains YES / CAUSE UNKNOWN.

TAI canonical process/task is not designed here.
Source mapping A↔B↔C is not designed here.
```

---

## Tests

`tests/test_risk02_source_core.py` covers native A codes, B path collisions, B leaf occurrence preservation, C 19-field hash, occurrence preservation, raw payload, forbidden hash inputs, MODEL D separation, snapshot/source and record/task composite FKs, and full census when `artifacts/risk01` exists.

CI: `pytest tests/test_risk02_source_core.py`. Full 47,559 census is skip-if-missing on GitHub runners. Local full census is the 47,559-row evidence.
