---
class: records
type: report
scope: knowledge
project: risk
title: OBJ-RISK-04 REVIEW-002 CIC_W semantic scale-out
version: 1
status: active
owner: taiwang
---

# OBJ-RISK-04-REVIEW-002 — CIC_W Semantic Review Scale-Out / Batch 002 Evidence Pack

This WO selects a hierarchical 200-row CIC_W evidence pack from 1,672 unreviewed AMBIGUOUS nodes. Cursor does not fill semantic kind or KEEP/MERGE/HOLD/REJECT.

```text
WO-RISK-04-CHG1            = PASS / CLOSED
RISK-04                    = IN REVIEW
PR                         = #366
previous HEAD              = a20b53ef1cc68aa5122b90429c58c7e73adce274
WO-RISK-04-REVIEW-002      = EVIDENCE_READY
Batch002 semantic decisions= 0 / 200
CIC_W semantic reviewed    = 50
RISK-04-APPROVE-001        = NOT OPENED
MERGE                      = NOT AUTHORIZED
```

---

## CIC_W census

```text
CIC_W total     = 1722
reviewed        = 50
unreviewed      = 1672
unreviewed PROCESS = 0
unreviewed AMBIGUOUS = 1672
max depth       = 3
max child_count = 9
unique roots    = 62
unique parents  = 384
```

Hierarchy totals:

```text
W_ROOT = 62
W_MID  = 373
W_LEAF = 1287
```

Unreviewed 1,672:

```text
W_ROOT = 61
W_MID  = 361
W_LEAF = 1250
```

The one reviewed W_ROOT is Batch 001 `가구및집기`. Its unreviewed descendants still contribute to root coverage.

---

## Batch002 selection algorithm

Candidate pool = CIC_W + `semantic_kind=AMBIGUOUS` + `semantic_review_decision=UNREVIEWED` (1,672). Batch 001 keys excluded.

```text
PHASE A  all unreviewed W_ROOT, source_key ASC     = 61
PHASE B  W_MID cap 70, child_count DESC, source_key ASC = 70
PHASE C  remaining W_LEAF by root then parent round-robin = 69
TOTAL    200
batch_no 201..400
```

Leaf round-robin: `root_source_key ASC`, then within root `parent source_key ASC` / `leaf source_key ASC`. Name suffix heuristics are not used for selection. `lexical_cues` is review evidence only.

---

## Batch002 ROOT/MID/LEAF counts

```text
BATCH002 W_ROOT = 61
BATCH002 W_MID  = 70
BATCH002 W_LEAF = 69
CIC_W           = 200
KALIS           = 0
KOSHA           = 0
```

---

## Coverage metrics

```text
root_coverage_count       = 62
root_coverage_pct         = 100.00
parent_coverage_count     = 105
parent_coverage_pct       = 27.34
selected_leaf_parent_count= 69
MAX_ROOT_SHARE (full 200) = 0.035
leaf max root share       = 0.0290
leaf max parent share     = 0.0145
```

Leaf concentration guards PASS (`single root ≤ 25%`, `single parent ≤ 10%` of the leaf subset).

---

## Frozen evidence

```text
Batch001 overlap          = 0
Batch002 duplicates       = 0
Batch001 SHA unchanged    = 955b3c11f092b657b54d3d94f639270f767da4156c6a3710663deeeabbb4c4b8
Review Input SHA unchanged= c28fa67368ff3af3d05f7b771cebca455c6cf5cd94884bbff44dd1bd5087df1b
CHG1 KEEP/MERGE/HOLD/REJECT = 49/22/17/12 unchanged
```

---

## Batch002 SHA

```text
REVIEW INPUT = docs/knowledge/risk/RISK04_CICW_BATCH002_REVIEW_INPUT.tsv
RUN1 SHA     = 81377ba5e1f5b3e8f80d0c3d237843ccc563fbaece02cea9eb0d2cb4c83fd806
RUN2 SHA     = 81377ba5e1f5b3e8f80d0c3d237843ccc563fbaece02cea9eb0d2cb4c83fd806
DETERMINISM  = PASS
```

GPT columns on all 200 rows:

```text
current_semantic_kind    = AMBIGUOUS
current_review_decision  = UNREVIEWED
gpt_semantic_kind        = PENDING
gpt_review_decision      = PENDING
merge_candidate_keys     = EMPTY
gpt_reason               = EMPTY
KEEP_AS_DISTINCT         = 0
MERGE_CANDIDATE          = 0
HOLD                     = 0
REJECT                   = 0
```

Reviewed-anchor relations in this pack (reference only, not kind propagation): NONE 133, SAME_ROOT 45, CHILD 12, SIBLING 8, PARENT 2.

---

## Review coverage after this WO

```text
reviewed                     = 50
evidence_ready_not_reviewed  = 200
remaining_without_batch      = 1472
```

Local 1,672 dump is gitignored under `artifacts/risk04/review002/`.

---

## Guards

```text
SOURCE PROPOSAL UNIVERSE = 3103
KALIS semantic mutation  = 0
KOSHA B identity HOLD / 620 / 626 preserved
CIC_W unreviewed PROCESS = 0
mapping approval coverage= 0
OWNER APPROVED SEEDS     = 0
CANONICAL UUID CREATED   = 0
AUTO MERGED / AUTO APPROVED = 0
NEW MIGRATION            = 0
production / Graph / Legal / CHEM / LLM / fuzzy = 0
semantic_gate.py         = NO CHANGE
review_decisions.py      = NO CHANGE
```

---

## Next

GPT/Owner reads `RISK04_CICW_BATCH002_REVIEW_INPUT.tsv` and fills `gpt_semantic_kind` and `gpt_review_decision` for rows 201–400. After that review, GPT decides whether a safe family rule exists or Batch 003 is required. This WO does not create a classifier.

```text
NEXT = GPT SEMANTIC REVIEW BATCH002
MERGE = NOT AUTHORIZED
RISK-04-APPROVE-001 = NOT OPENED
```
