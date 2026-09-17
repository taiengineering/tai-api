---
class: records
type: report
scope: knowledge
project: risk
title: WO-RISK-KOSHA-MAP-001A KOSHA source mapping review universe
version: 1
status: active
owner: taiwang
---

# WO-RISK-KOSHA-MAP-001A — KOSHA Source Mapping Review Universe

## THIS IS NOT MAPPING APPROVAL

```text
THIS IS NOT MAPPING APPROVAL
THIS IS NOT PRODUCTION MATERIALIZATION
THIS DOES NOT LIFT KOSHA IDENTITY HOLD
THIS DOES NOT CREATE CANONICAL NODES
THIS DOES NOT DECIDE NO_MATCH FOR ANY ROW
```

## Anchors

```text
CANONICAL MATERIALIZATION RECEIPT SHA = c8c4232bf924b52636c9dc33fb1891473d548e09ed15de35f33764fe18603f3c
SOURCE INGEST RECEIPT SHA             = 9493ff9f5515eec26daf0204589d1fa3dbb8128f2b58f3590f49244ebb4ecef4
```

## Review universe

```text
KOSHA_TOTAL_NODES = 787  # PROJECT_KIND + WORK_TYPE + DETAIL_PROCESS
PROJECT_KIND_CONTEXT_ONLY = 6  # not a mapping target
WORK_TYPE_CONTEXT_ONLY = 161  # not a mapping target
DETAIL_PROCESS_REVIEW_UNIVERSE = 620  # 620 review rows in this WO
RAW_LEAF_OCCURRENCES = 626  # must equal 626 (KOSHA raw source rows)
PATH_IDENTITIES = 620  # unique DETAIL_PROCESS identities preserved
IDENTITY_STATUS = HOLD  # frozen from RISK-02; not lifted by this WO
DUPLICATE_OCCURRENCE_GROUPS = 3  # leaf identities with occurrence_count > 1
DUPLICATE_RAW_EXTRAS = 6  # extra raw rows collapsed onto duplicate identities
EXACT_NAME_SOURCE_HITS = 12  # unique canonical TASK by name_normalized
NO_EXACT_NAME_ROWS = 608  # SEMANTIC_SEARCH_REQUIRED — NOT NO_MATCH
MULTI_TARGET_EXACT_NAME_AMBIGUITY = 0  # 0 by frozen production canonical anchor
SEMANTIC_DECISIONS = 0  # deferred to GPT semantic review WO
APPROVED_DECISIONS = 0  # no owner mapping approval yet
NO_MATCH_DECISIONS = 0  # cannot be assigned mechanically
PRODUCTION_KOSHA_MAPPINGS = 0  # no DB write in this WO
EXACT_NAME_FAMILIES = 발파=6;콘크리트양생=6  # candidate evidence only — same name != EXACT_EQUIVALENT
```

`EXACT_NAME_CANDIDATE` rows carry `recommended_mapping_type = POSSIBLE_RELATED`,
never `EXACT_EQUIVALENT`. `SEMANTIC_SEARCH_REQUIRED` rows carry a blank target
and are **not** `NO_MATCH`. Both classes require GPT semantic review before any
Owner mapping approval WO can be opened.

## Frozen SHAs

```text
RISK KOSHA MAP001 REVIEW UNIVERSE SHA = 30a2762eec244518fd73eb53fb0c3e53f56e6a41669569d94ee570175cd0e04a
RISK KOSHA MAP001 GPT REVIEW PACK SHA = 20bcdf3a7827a2446dae933a1d055463176478cccf86f7ad8c607c23fe29f9b5
```

## Verdict

```text
WO-RISK-KOSHA-MAP-001A = REVIEW_UNIVERSE_FROZEN / EVIDENCE_READY
KOSHA MAPPING APPROVAL = NOT OPENED
KOSHA PRODUCTION MAPPING = 0
CANONICAL = 1110 DRAFT / 0 ACTIVE (unchanged)
MERGE = NOT AUTHORIZED
NEXT = GPT KOSHA SEMANTIC REVIEW BATCH 01
STOP
```
