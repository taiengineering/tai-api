---
class: records
type: report
scope: knowledge
project: risk
title: OBJ-RISK-04 REVIEW-003 W_MID leaf-family evidence
version: 1
status: active
owner: taiwang
---

# OBJ-RISK-04-REVIEW-003 — Freeze Batch002 GPT Review + Remaining W_MID 291 Evidence

This WO freezes GPT Batch002 semantic review (200 rows) as repo evidence and builds a remaining W_MID 291 evidence worksheet. Cursor does not fill MID kind, KEEP/MERGE/HOLD/REJECT, or leaf-family policy.

```text
WO-RISK-04-CHG1            = PASS / CLOSED
WO-RISK-04-REVIEW-002      = SEMANTIC REVIEW COMPLETE
RISK-04                    = IN REVIEW
PR                         = #366
previous HEAD              = d6ebab4d6357d34356568437ccb9830c93858b9e
WO-RISK-04-REVIEW-003      = EVIDENCE_READY
GPT REVIEW MANIFEST        ≠ OWNER APPROVED SEED MANIFEST
OWNER APPROVED SEEDS       = 0
RISK-04-APPROVE-001        = NOT OPENED
MERGE                      = NOT AUTHORIZED
GLOBAL AUTO CLASSIFIER     = NOT SAFE
```

---

## Batch002 GPT review frozen = 200

Frozen input SHA unchanged:

```text
RISK04_CICW_BATCH002_REVIEW_INPUT.tsv
SHA = 81377ba5e1f5b3e8f80d0c3d237843ccc563fbaece02cea9eb0d2cb4c83fd806
```

GPT review manifest (not approval):

```text
RISK04_CICW_BATCH002_GPT_REVIEW_v1.tsv
rows = 200
batch_no = 201..400
approval_state NOT_APPROVED = 200
MERGED = 0
APPROVED = 0
```

Batch002 semantic totals:

```text
PROCESS            = 129
TASK               = 23
METHOD             = 2
MATERIAL_COMPONENT = 13
FACILITY_EQUIPMENT = 16
CLASSIFICATION     = 16
AMBIGUOUS          = 1
TOTAL              = 200
```

Batch002 decision totals:

```text
KEEP_AS_DISTINCT = 143
MERGE_CANDIDATE  = 9
HOLD             = 1
REJECT           = 47
TOTAL            = 200
```

Nine MERGE_CANDIDATE rows use `merge_candidate_keys=UNRESOLVED`. Cursor did not confirm counterparts.

---

## CIC_W reviewed total = 250

These are semantic review results, not approved canonical or mapping counts.

```text
PROCESS            = 153
TASK               = 23
METHOD             = 2
MATERIAL_COMPONENT = 20
FACILITY_EQUIPMENT = 18
CLASSIFICATION     = 17
AMBIGUOUS          = 17
TOTAL              = 250
```

Decision totals:

```text
KEEP_AS_DISTINCT = 167
MERGE_CANDIDATE  = 9
HOLD             = 17
REJECT           = 57
TOTAL            = 250
```

Hierarchy coverage after Batch002 overlay:

```text
W_ROOT reviewed = 62 / 62
W_MID reviewed  = 82 / 373
W_MID remaining = 291
W_LEAF reviewed = 106 / 1287
W_LEAF remaining = 1181
W_LEAF semantic mutation = 0
```

---

## REVIEW003 rows = 291

Candidate pool = CIC_W + `source_node_type=W_MID` + not in Batch001 reviewed + not in Batch002 reviewed.

```text
RISK04_CICW_MID_REVIEW003_INPUT.tsv
rows = 291
batch_no = 401..691
source_id CIC_W = 291
source_node_type W_MID = 291
depth = 2
current_semantic_kind = AMBIGUOUS
current_review_decision = UNREVIEWED
gpt_semantic_kind = PENDING 291
gpt_review_decision = PENDING 291
gpt_leaf_family_policy = PENDING 291
merge_candidate_keys = EMPTY 291
gpt_reason = EMPTY 291
Batch001 overlap = 0
Batch002 overlap = 0
W_ROOT candidate = 0
W_LEAF candidate = 0
```

Root, sibling, and child overlays are evidence only. Root PROCESS does not assign MID PROCESS. Reviewed sibling kind is not copied. MID kind is not copied onto LEAF.

---

## Mechanical family state distribution

Cursor does not name families. Mechanical state only:

```text
NO_REVIEWED_CHILDREN         = 239
PARTIAL_REVIEW_SINGLE_KIND   = 37
PARTIAL_REVIEW_MULTI_KIND    = 2
ALL_REVIEWED_SINGLE_KIND     = 13
ALL_REVIEWED_MULTI_KIND      = 0
TOTAL                        = 291
```

```text
MID with zero reviewed children              = 239
MID with single reviewed child-kind evidence = 50
MID with multi-kind reviewed evidence        = 2
```

Single-kind evidence = PARTIAL_REVIEW_SINGLE_KIND + ALL_REVIEWED_SINGLE_KIND = 37 + 13 = 50. Multi-kind reviewed evidence = 2. This is not a HOMOGENEOUS_PROCESS_FAMILY label.

Future GPT `gpt_leaf_family_policy` values may be `SAFE_SINGLE_KIND_FAMILY`, `MIXED_FAMILY`, `INSUFFICIENT_EVIDENCE`, `NO_CHILDREN`. This WO leaves all 291 as PENDING.

---

## Child coverage

```text
MID with children                  = 245
MID child count min                = 0
MID child count max                = 6
MID child count avg                = 2.5601
MID reviewed-child coverage count  = 52
MID reviewed-child coverage pct    = 17.87
children_truncated                 = NO (all rows; max children 6)
direct children                    = W_LEAF only
```

Direct-child arithmetic: `reviewed_child_count + unreviewed_child_count = direct_child_count` on every row.

---

## W_MID coverage after this WO

```text
W_MID reviewed       = 82
W_MID evidence-ready = 291
W_MID total accounted = 373
CIC_W semantic reviewed = 250
remaining without semantic decision = 1472
```

291 remaining MIDs are EVIDENCE_READY only. Cursor final PROCESS/TASK/METHOD/MATERIAL_COMPONENT/FACILITY_EQUIPMENT/CLASSIFICATION/AMBIGUOUS decisions on this worksheet = 0.

---

## Source and production guards

```text
SOURCE PROPOSAL UNIVERSE = 3103
CIC_W total              = 1722
B path nodes             = 620
B identity               = HOLD
B occurrence             = 626
KOSHA semantic mutation  = 0
C tasks                  = 761
unique content           = 30696
occurrence               = 47559
KALIS semantic mutation  = 0
KALIS merge candidates   = 11 pairs (Batch001 frozen)
OWNER APPROVED SEEDS     = 0
CANONICAL UUID CREATED   = 0
ACTIVE CANONICALS        = 0
APPROVED DB MAPPINGS     = 0
mapping approval coverage = 0
NEW MIGRATION            = 0
production DB write      = 0
Graph / Legal / CHEM / SaaS mutation = 0
LLM / embedding / fuzzy  = 0
```

Frozen Batch001 artifacts are unchanged.

---

## Determinism

```text
BATCH002 MANIFEST SHA      = a5c124921c24a07168a587a33e874bb8760fd2519ed5cf798437ae2274e898bd
BATCH002 MANIFEST RUN1 SHA = a5c124921c24a07168a587a33e874bb8760fd2519ed5cf798437ae2274e898bd
BATCH002 MANIFEST RUN2 SHA = a5c124921c24a07168a587a33e874bb8760fd2519ed5cf798437ae2274e898bd
REVIEW003 RUN1 SHA         = 4fb7357d0fb6396ea9f63f03d49b6c5af9c62ac7fce6f2c9b510652c5e2ee72b
REVIEW003 RUN2 SHA         = 4fb7357d0fb6396ea9f63f03d49b6c5af9c62ac7fce6f2c9b510652c5e2ee72b
DETERMINISM                = PASS
```

---

## Next

```text
NEXT = GPT SEMANTIC REVIEW W_MID 291 + LEAF FAMILY POLICY DECISION
LEAF FAMILY POLICY = PENDING GPT
RISK-04-APPROVE-001 = NOT OPENED
MERGE = NOT AUTHORIZED
```
