---
class: records
type: report
scope: knowledge
project: risk
title: OBJ-RISK-04 REVIEW-004 W_MID freeze and leaf routing
version: 1
status: active
owner: taiwang
---

# OBJ-RISK-04-REVIEW-004 — W_MID 291 GPT Freeze + W_LEAF Full Review Routing

This WO freezes GPT's completed W_MID 291 semantic review and builds six full-universe evidence batches for the remaining 1,181 W_LEAF nodes. Cursor does not fill LEAF kind, KEEP/MERGE/HOLD/REJECT, or propagate parent kind to child.

```text
WO-RISK-04-REVIEW-003      = EVIDENCE_READY
previous HEAD              = 9279e173af6538a9312d52e45e21da7eac219a82
PR                         = #366
WO-RISK-04-REVIEW-004      = EVIDENCE_READY
GPT REVIEW MANIFEST        ≠ OWNER APPROVED SEED MANIFEST
OWNER APPROVED SEEDS       = 0
RISK-04                    = IN REVIEW
RISK-04-APPROVE-001        = NOT OPENED
MERGE                      = NOT AUTHORIZED
GLOBAL AUTO CLASSIFIER     = NOT SAFE
```

The compact `default PROCESS` encoding for batch 401-691 is a completed GPT review of those 291 rows only. It is not a W_MID→PROCESS rule, not a depth=2 rule, and not a future source classifier.

---

## W_MID 291 GPT decisions

```text
RISK04_CICW_MID_REVIEW003_GPT_REVIEW_v1.tsv
rows = 291
batch_no = 401..691
approval_state NOT_APPROVED = 291
AMBIGUOUS = 0
MERGED = 0
APPROVED = 0
```

Frozen REVIEW003 input SHA unchanged:

```text
RISK04_CICW_MID_REVIEW003_INPUT.tsv
SHA = 4fb7357d0fb6396ea9f63f03d49b6c5af9c62ac7fce6f2c9b510652c5e2ee72b
```

Semantic totals:

```text
PROCESS            = 230
TASK               = 2
METHOD             = 2
MATERIAL_COMPONENT = 17
FACILITY_EQUIPMENT = 29
CLASSIFICATION     = 11
AMBIGUOUS          = 0
TOTAL              = 291
```

Decision totals:

```text
KEEP_AS_DISTINCT = 212
MERGE_CANDIDATE  = 20
HOLD             = 0
REJECT           = 59
TOTAL            = 291
```

Twenty MERGE_CANDIDATE rows record specified CIC_W counterpart `seed_proposal_key` values from the 3,103 proposal universe. MERGE_CANDIDATE is not MERGED and is not APPROVED.

---

## Family policy totals

GPT mapping of mechanical child-review state. Not child-kind assignment.

```text
SAFE_SINGLE_KIND_FAMILY = 13
MIXED_FAMILY            = 2
INSUFFICIENT_EVIDENCE   = 230
NO_CHILDREN             = 46
TOTAL                   = 291
```

`SAFE_SINGLE_KIND_FAMILY` does not assign LEAF kind. Families with unreviewed children remain INDIVIDUAL REVIEW. Remaining LEAF 1,181 are not family auto-classified.

Batch001/002 reviewed MID parents use `parent_leaf_family_policy=NOT_ASSESSED` on their remaining children.

---

## CIC_W reviewed 541

```text
PROCESS            = 383
TASK               = 25
METHOD             = 4
MATERIAL_COMPONENT = 37
FACILITY_EQUIPMENT = 47
CLASSIFICATION     = 28
AMBIGUOUS          = 17
TOTAL              = 541
```

Decision aggregate:

```text
KEEP_AS_DISTINCT = 379
MERGE_CANDIDATE  = 29
HOLD             = 17
REJECT           = 116
TOTAL            = 541
```

Hierarchy:

```text
W_ROOT reviewed = 62 / 62
W_MID reviewed  = 373 / 373
W_MID remaining = 0
W_LEAF reviewed = 106 / 1287
W_LEAF remaining = 1181
unreviewed PROCESS = 0
unreviewed AMBIGUOUS = 1181
W_LEAF semantic mutation = 0
```

---

## 6 evidence batches

Remaining W_LEAF universe = 1,181. Full review routing, not a sample. Order: `root_source_key ASC`, `parent_source_key ASC`, `source_key ASC`. `review_no` = 692..1872.

```text
RISK04_CICW_LEAF_BATCH004A_REVIEW_INPUT.tsv = 200
RISK04_CICW_LEAF_BATCH004B_REVIEW_INPUT.tsv = 200
RISK04_CICW_LEAF_BATCH004C_REVIEW_INPUT.tsv = 200
RISK04_CICW_LEAF_BATCH004D_REVIEW_INPUT.tsv = 200
RISK04_CICW_LEAF_BATCH004E_REVIEW_INPUT.tsv = 200
RISK04_CICW_LEAF_BATCH004F_REVIEW_INPUT.tsv = 181
TOTAL = 1181
pairwise intersection = 0
reviewed overlap = 0
gpt_semantic_kind PENDING = 1181
gpt_review_decision PENDING = 1181
```

Parent PROCESS/MATERIAL/`SAFE_SINGLE_KIND_FAMILY` is evidence only. Cursor did not copy those values onto LEAF GPT fields.

---

## Source and production guards

```text
SOURCE PROPOSAL UNIVERSE = 3103
CIC_W total              = 1722
B path nodes             = 620
B identity               = HOLD
B occurrence             = 626
KOSHA semantic mutation  = 0
C unique content         = 30696
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

---

## Determinism

```text
W_MID MANIFEST SHA      = 4acfce3392d6dd805a85f95fe19b8a72864f23c5c1e74f0f043ba8fa37ab3436
W_MID MANIFEST RUN1 SHA = 4acfce3392d6dd805a85f95fe19b8a72864f23c5c1e74f0f043ba8fa37ab3436
W_MID MANIFEST RUN2 SHA = 4acfce3392d6dd805a85f95fe19b8a72864f23c5c1e74f0f043ba8fa37ab3436
LEAF ROUTING SHA        = 5e1630916ad9004d9e854bbce82fce62061b4c181eec1eb4f5021a48d5c2a2fc
LEAF ROUTING RUN1 SHA   = 5e1630916ad9004d9e854bbce82fce62061b4c181eec1eb4f5021a48d5c2a2fc
LEAF ROUTING RUN2 SHA   = 5e1630916ad9004d9e854bbce82fce62061b4c181eec1eb4f5021a48d5c2a2fc
004A SHA = 23e15185bc004c62432f8044596995a1106759d2f1febe399bd76c6b9265c894
004B SHA = bfe98e52c4e6f812a09e44260b4f23bc7020bdbefa9a0c3eece281ab096b858c
004C SHA = 665a3c376c218315d4adceb32ff3d5a81da72af90eda76442d823fd6ac8e1f72
004D SHA = f0cdea5c724fb5c7d66104a3fe72aa3aceaa550c9239fb5fe065eb58d3cfa047
004E SHA = 2a2a973666b7144045272adbcd8a3456218e83e5f5c4c876fc94480c8c20ab64
004F SHA = c8ddb8b0e997005b3d6fe40f4b88ad1590e12012ba811f46c688773b2df3e100
DETERMINISM = PASS
```

---

## Next

```text
NEXT = GPT VERIFY → GPT SEMANTIC REVIEW LEAF BATCH004A
RISK-04-APPROVE-001 = NOT OPENED
MERGE = NOT AUTHORIZED
```
