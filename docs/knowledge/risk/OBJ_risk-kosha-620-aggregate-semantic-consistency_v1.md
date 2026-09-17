---
class: records
type: report
scope: knowledge
project: risk
title: WO-RISK-KOSHA-AGGREGATE-001 KOSHA 620 aggregate semantic consistency
version: 1
status: active
owner: taiwang
---

# WO-RISK-KOSHA-AGGREGATE-001 — KOSHA 620 Aggregate Semantic Consistency

## THIS IS AGGREGATION ONLY

```text
THIS IS NOT OWNER APPROVAL
THIS IS NOT CANONICAL CREATION
THIS IS NOT PRODUCTION MATERIALIZATION
THIS DOES NOT LIFT KOSHA IDENTITY HOLD
```

Claude did not re-decide any semantic outcome. Every row is the verbatim
GPT decision from the B01-B07 frozen review artifacts, joined with the
frozen normalized label from the corresponding evidence TSV.

## Aggregate counts

```text
TOTAL                        = 620
MAPPING CANDIDATES           = 75
  EXACT_EQUIVALENT           = 6
  NARROWER_THAN              = 40
  POSSIBLE_RELATED           = 29
AMBIGUOUS                    = 78
CANONICAL_GAP                = 196
NO_MATCH                     = 271

Non-mapping (78 + 196 + 271) = 545
```

## Consistency exceptions

```text
group key                        = (work_type, source_name_normalized)
consistency exception groups     = 4
```

Each exception group has ≥2 distinct decision signatures across
review rows sharing the same normalized label + work_type. These are
candidates for GPT semantic exception review — Claude classified them
mechanically but did not resolve them.

## Canonical GAP groups (label + work_type context)

```text
group key                        = (work_type, source_name_normalized)
distinct GAP context groups      = 66
```

## NO_MATCH groups (label + work_type context)

```text
group key                        = (work_type, source_name_normalized)
distinct NO_MATCH context groups = 53
```

## Frozen inputs

Per-batch GPT review SHAs (locked, WO §2):

```text
B01 = 4b39776f3404f100a182fa23727c74f5cb239036b78ac25d99c82b46662f8bfd
B02 = 59dbdf26645b536aac2cd16b3cdaac477de29be793aa3d0a2c209b210e20b787
B03 = 4dda24f4d3c930249e23c36f3062117cde3063f5182a7fa7a08d1d9fa1e69885
B04 = 5d76544dae6c2f509a842baf8f8d394db339d62ffb3f9b6789091f637856815b
B05 = feb52cb79c36abb1f1fad96f4b7f61d3b04d57e9550696d17d85b69f6b37cda2
B06 = 2d4015cf8f5c8e38d55e7fecaae48b0f07b088a23199363e332ac8b717def581
B07 = a2d64c551c1104eb304859773a0a74417560410c3d58f5cf3112d4c6abb2d5ba

CANONICAL TASK REFERENCE = a22f3a83f3cc2563554eb04b71ac8afc1faff44e3a6a594dd265ff04baafa2a6
```

## Frozen output SHAs

```text
RISK KOSHA 620 AGGREGATE SHA                       = 7e99b73204876cfef6c85a198430d14adfd8582b17cc2c7162a0729063aea67d
RISK KOSHA 620 MAPPING CANDIDATES SHA              = 4952310fafda56d620f10a53a4c4faa765c73338157e1992c6d690428e4f869a
RISK KOSHA 620 AMBIGUOUS SHA                       = 4769525cc441028c21f1326f71752479702179462b6560975d6596e8e6403fba
RISK KOSHA 620 CANONICAL_GAP SHA                   = 7e0147924851517bb805e1844e6801ffea9b48e2f1da97b5aa3251496d862c66
RISK KOSHA 620 NO_MATCH SHA                        = adbd594a9ffd5abed1d46d00d25d4883665591aba584ebef4a826ae6824654a0
RISK KOSHA 620 CONSISTENCY EXCEPTIONS SHA          = 59236636c9169b28ad920be5f10a7faf31bd2e43a58ff4278bd5a245fa2fbc97
RISK KOSHA 620 CANONICAL_GAP GROUPS SHA            = e506fb08f4959f77ad43fa4d5c93d79739f9035b7bc27b0c0e50f7296ec3f268
RISK KOSHA 620 NO_MATCH GROUPS SHA                 = e688c9a0cecd5ac0e007f24ba99d4f07d5e9aedd485d90ea8c4ad9d7230ec66e
```

## Verdict

```text
WO-RISK-KOSHA-AGGREGATE-001 = AGGREGATE_FROZEN / GPT_EXCEPTION_REVIEW_READY
TOTAL KOSHA REVIEWED = 620 / 620
OWNER APPROVAL = NOT OPENED
KOSHA MAPPING APPROVAL = NOT OPENED
KOSHA PRODUCTION MAPPING = 0
MERGE = NOT AUTHORIZED
NEXT = GPT AGGREGATE EXCEPTION REVIEW + CANONICAL GAP CONSOLIDATION
STOP
```
