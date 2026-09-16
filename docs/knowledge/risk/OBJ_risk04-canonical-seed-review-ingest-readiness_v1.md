---
class: records
type: report
scope: knowledge
project: risk
title: OBJ-RISK-04 canonical seed review and ingest readiness
version: 1
status: active
owner: taiwang
---

# OBJ-RISK-04 — Canonical Seed Review + Controlled Mapping Approval Readiness + Source Ingest Readiness

This WO builds the full seed-proposal universe and a 100-row Owner/GPT review pack. It does not materialize TAI canonical UUIDs, does not write `APPROVED` mappings, and does not apply production ingest.

```text
WO-RISK-01             = PASS / CLOSED
WO-RISK-02             = PASS / CLOSED
WO-RISK-03             = PASS / CLOSED
WO-RISK-03-MERGE-002   = PASS / CLOSED
base main HEAD         = db024b57d9b81802f5dd18b18c69872735e3c3da
PHYSICAL MODEL         = NEW_RISK_CANONICAL
MODEL D                = APPROVED / FROZEN
B identity             = HOLD
AUTO APPROVED          = 0
APPROVED MAPPINGS      = 0
production DB write    = 0
production migration   = 0
OBJ-RISK               = IN_PROGRESS
RISK-04                = REVIEW_READY
RISK-04-APPROVE-001    = NOT OPENED
MERGE                  = NOT AUTHORIZED
```

---

## RISK-04 objective

```text
1. TAI canonical seed candidate universe
2. Owner/GPT review pack (full local artifacts + Batch 001)
3. RISK source ingest dry-run to the step before production write
```

```text
SOURCE NODE → SEED PROPOSAL
SOURCE NODE ↛ CANONICAL AUTO CREATE
REVIEW_READY ≠ APPROVED
```

---

## Seed proposal vs canonical identity

```text
SEED PROPOSAL IDENTITY ≠ TAI CANONICAL IDENTITY
```

Local proposal key is deterministic SHA256 of `source_id + source_key + proposed_node_kind` via the RISK-02 `sha256_parts` contract. It is not a UUID, timestamp, row number, or runtime order.

Actual `risk_canonical_nodes.id = UUID` is created only after Owner approval, in a later materialization WO. This WO:

```text
CANONICAL UUID CREATED = 0
OWNER APPROVED SEEDS   = 0
ACTIVE CANONICALS      = 0
APPROVED DB MAPPINGS   = 0
```

---

## Source schema

Existing RISK-02/03 tables were confirmed. No new migration.

```text
NEW MIGRATION = 0
SOURCE SCHEMA = PASS
CANONICAL SCHEMA = PASS
MIGRATION APPLY = 0
```

```text
risk_sources
risk_snapshots
risk_source_nodes
risk_records
risk_snapshot_memberships
risk_canonical_nodes
risk_canonical_node_sectors
risk_source_mappings
```

SQL files remain:

```text
supabase/migrations/20260915_risk_source_catalog.sql
supabase/migrations/20260916_risk_canonical_mapping.sql
```

FK-safe source ingest order (dry-run only):

```text
1 risk_sources
2 risk_snapshots
3 risk_source_nodes
4 risk_records
5 risk_snapshot_memberships
```

Canonical ingest order is documented, not executed:

```text
1 risk_canonical_nodes
2 risk_canonical_node_sectors
3 risk_source_mappings
CANONICAL INGEST = NOT AUTHORIZED
MAPPING INGEST   = NOT AUTHORIZED
```

---

## Proposal universe metrics

Eligible source-node universe reused RISK-03 kind mapping. Final proposal kinds are PROCESS and TASK only.

```text
A eligible W nodes              = 1722 → PROCESS
B DETAIL_PROCESS path nodes     = 620  → TASK
C TASK nodes                    = 761  → TASK
SEED UNIVERSE TOTAL             = 3103
PROCESS PROPOSALS               = 1722
TASK PROPOSALS                  = 1381
A ORIGIN PROPOSALS              = 1722
B ORIGIN PROPOSALS              = 620
C ORIGIN PROPOSALS              = 761
```

Frozen source metrics preserved:

```text
A nodes                 = 1722
B raw rows              = 626
B path identities       = 620
B leaf occurrence sum   = 626
B identity              = HOLD
C task nodes            = 761
C unique content        = 30696
C occurrence sum        = 47559
C sha256                = 399dbe64dcf1b5d1445fd51e968070dd26e0a40583f8e0afc5e9219839c958c8
```

B collision paths remain one proposal each, occurrence 3, no `-1/-2` split:

```text
빌딩 > 조적 > 미장 및 견출작업
아파트 > 조적 > 미장 및 견출작업
지하철 > 조적 > 미장 및 견출작업
```

C path is `risk record → C TASK → canonical proposal` only. 30696 unique content rows and 47559 occurrences are not proposals.

---

## Multi-source support metrics

Exact evidence only: normalized exact name, normalized exact path, compatible node kind, parent-context equality. No fuzzy, embedding, language-model, or semantic merge.

```text
MULTI-SOURCE SUPPORTED (same kind + exact name) = 0
AUTO MERGED                                     = 0
```

Six names exist across sources with **incompatible** kind (A PROCESS vs B/C TASK): `타워크레인`, `리프트`, `윈치`, `발파`, `콘크리트타설`, `콘크리트양생`. They stay separate proposals. Compatible-kind exact-name support is zero in this official snapshot; that is a review fact, not a merge.

`support_count` / `exact_name_support_count` / `exact_path_support_count` / `risk_content_support` are review-priority evidence only.

```text
priority order ≠ confidence ≠ approval
```

---

## Ambiguity / HOLD counts

Minimum HOLD when the same normalized name appears under incompatible parent context.

```text
AMBIGUOUS / HOLD universe = 1410
REVIEW_READY universe     = 1693
REJECT_CANDIDATE          = 0
ACTIVE                    = 0
APPROVED                  = 0
```

HOLD by origin:

```text
CIC_W                        = 62
KOSHA_CONSTRUCTION_PROCESS   = 587
KALIS_RISK_PROFILE           = 761
```

All 761 C TASK proposals are HOLD because each name also appears under another parent path in C. Generator statuses are only `UNREVIEWED` / `REVIEW_READY` / `HOLD` / `REJECT_CANDIDATE`. This run emits `REVIEW_READY` or `HOLD`.

---

## Review Batch 001

Repo evidence is the 100-row TSV. Full JSONL stays local under `artifacts/risk04/` and is gitignored.

TSV path is `docs/knowledge/risk/RISK04_BATCH001.tsv` (WO suggested `docs/knowledge/risk/review/`; that third directory segment is omitted so the file stays at `docs/<scope>/<project>/<file>`).

```text
REVIEW BATCH 001 count          = 100
PROCESS                         = 50
TASK                            = 50
HOLD                            = 50
REVIEW_READY                    = 50
SHA256                          = 955b3c11f092b657b54d3d94f639270f767da4156c6a3710663deeeabbb4c4b8
source-origin CIC_W             = 50
source-origin KALIS_RISK_PROFILE= 50
source-origin KOSHA             = 0
```

Batch composition follows the documented sort (exact-path support, exact-name support, risk-content support, occurrence, kind, name, source_id, source_key), then PROCESS cap 50 + TASK cap 50. C TASK rows outrank B on risk-content support, so Batch 001 TASK slots are KALIS HOLD rows such as `굴착작업` / `설치작업` under different parents. Same-name different-parent rows are kept, not deleted.

---

## Mapping approval readiness

No production canonical UUID exists, so DB `mapping_status = APPROVED` is structurally forbidden.

```text
APPROVED DB MAPPINGS        = 0
PENDING MAPPING CANDIDATES  = 3103
NO_MATCH CANDIDATES         = 0
```

Every eligible source node has a local seed proposal, so universe mappings recommend `POSSIBLE_RELATED` to `target_seed_proposal_key` (not `canonical_id`). Maximum auto recommendation is `POSSIBLE_RELATED`. `EXACT_EQUIVALENT` and `APPROVED` are not generated.

`NO_MATCH` contract (null `target_seed_proposal_key`, `HOLD`) is implemented for source nodes with no proposal; the full eligible universe does not need it.

Owner approval still requires a later `approved_seed_manifest` / `approved_mapping_manifest`.

```text
MAPPING INGEST = NOT AUTHORIZED
```

---

## Source ingest readiness

RISK-02 pipeline dry-run on local official artifacts: parse → normalize → identity → snapshot → membership → integrity → ingest plan. No production write.

```text
SOURCE INGEST              = READY_WITH_HOLD
source node orphan         = 0
snapshot orphan            = 0
membership orphan          = 0
C record→task orphan       = 0
duplicate source key unexpected = 0
B 620 path identities      = PASS
B 626 occurrence           = PASS
B collision evidence       = retained
row-number identity        = 0
```

B identity HOLD is not an ingest blocker under those occurrence/path gates.

C metadata drift is preserved, not forced to match:

```text
official file rows = 47559
portal row field   = 41239
current prose      = approximately 47000
metadata_drift     = true
cause              = UNKNOWN
```

---

## Canonical ingest authorization state

```text
CANONICAL INGEST = NOT AUTHORIZED
```

Expected. Owner-approved seed manifest does not exist.

---

## Mapping ingest authorization state

```text
MAPPING INGEST = NOT AUTHORIZED
```

Expected. Canonical UUIDs do not exist.

---

## Migration readiness

Static only. Dependency order `20260915` then `20260916` is FK-safe. Production apply = 0. Production schema probe is not required.

---

## Determinism

Two full local runs, identical source input:

```text
SEED RUN1 SHA      = b9cd97ffdb917b6a43c7214d706fe04b42d889e0ae9de172b18e16ac0a56872b
SEED RUN2 SHA      = b9cd97ffdb917b6a43c7214d706fe04b42d889e0ae9de172b18e16ac0a56872b
MAPPING RUN1 SHA   = 6f4d49d4d8e55a53c9f0a6a7d8a9c2bb233200756501acc4493d500d67012f15
MAPPING RUN2 SHA   = 6f4d49d4d8e55a53c9f0a6a7d8a9c2bb233200756501acc4493d500d67012f15
READINESS RUN1 SHA = 7769888d35f0556fb66eff7d1da7c359abe4e4e44e347b6c496625471aa5b9ea
READINESS RUN2 SHA = 7769888d35f0556fb66eff7d1da7c359abe4e4e44e347b6c496625471aa5b9ea
BATCH 001 SHA      = 955b3c11f092b657b54d3d94f639270f767da4156c6a3710663deeeabbb4c4b8
DETERMINISM        = PASS
```

---

## Protected areas

```text
new external source calls = 0
CHEM API calls            = 0
CHEM-04 / PR #359         = untouched
Graph mutation            = 0
Legal Engine mutation     = 0
new SaaS API              = 0
UI mutation               = 0
customer process mutation = 0
factory_process mutation  = 0
LLM calls                 = 0
embedding                 = 0
fuzzy matching            = 0
semantic auto-merge       = 0
customer INSTANCE data    = 0
production DB write       = 0
production migration      = 0
```

Canonical PROCESS/TASK proposals are not Legal applicability evidence.

---

## Owner review gate

Cursor did not emit `APPROVED` or `ACTIVE`. Output is a REVIEW PACK.

Owner/GPT starts with Batch 001 (100 rows). Full 3103-row universe is local-only for later batches. Same-name different-parent HOLD rows in Batch 001 are merge/split decisions for humans, not generator auto-merge.

---

## Next decision

```text
RECOMMENDATION         = CHG_REQUIRED then CHG1 PASS CANDIDATE
OWNER REVIEW           = REQUIRED
RISK-04-APPROVE-001    = NOT OPENED
WO-RISK-04-CHG1        = PASS CANDIDATE
MERGE                  = NOT AUTHORIZED
NEXT                   = GPT VERIFY CHG1
```

After GPT/Owner verify the review pack, a separate WO may convert approved proposals into an `approved_seed_manifest` and only then mint canonical UUIDs.

---

## PRE-CHG1 / POST-CHG1

PRE-CHG1 (frozen Batch 001 / REVIEW-001 evidence; numbers not deleted):

```text
PROCESS PROPOSALS (source-kind) = 1722
TASK PROPOSALS (source-kind)    = 1381
CIC_W → PROCESS ALL             = in force
KALIS same-name multi-parent    = auto HOLD
PENDING MAPPING CANDIDATES      = 3103  (review-wait relation universe)
```

POST-CHG1 (`WO-RISK-04-CHG1`):

```text
SOURCE PROPOSAL UNIVERSE              = 3103
semantic PROCESS                      = 24
semantic TASK                         = 1381
semantic AMBIGUOUS                    = 1688
CIC_W unreviewed PROCESS              = 0
CIC_W unreviewed AMBIGUOUS            = 1672
KALIS same-name multi-parent auto HOLD = 0
SOURCE RELATION REVIEW UNIVERSE       = 3103
mapping approval coverage             = 0
```

See `OBJ_risk04-chg1-semantic-kind-gate_v1.md`.

---

## Tests

`tests/test_risk04_seed_review.py` covers deterministic proposal keys, no canonical UUID generation, KALIS same-name different-parent as mechanical flag (not auto HOLD), no cross-source auto-merge, no auto `APPROVED`, B collision occurrence preservation, C record exclusion, `NO_MATCH` null target, Batch 001 cap/determinism, committed TSV shape, and full census when `artifacts/risk01` exists.

CI: `pytest tests/test_risk04_seed_review.py`. Full census is skip-if-missing on GitHub runners.
