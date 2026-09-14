---
class: records
type: report
scope: knowledge
project: risk
title: OBJ-RISK-04 CHG1 semantic kind gate
version: 1
status: active
owner: taiwang
---

# OBJ-RISK-04-CHG1 — Semantic Kind Gate + KALIS Multi-Parent Rule Correction

This WO inserts a pre-canonical semantic-kind gate between source nodes and PROCESS/TASK seed candidacy. It does not approve seeds, mint canonical UUIDs, or merge proposals.

```text
WO-RISK-04                 = CHG_REQUIRED / IN REVIEW
WO-RISK-04-REVIEW-001      = SEMANTIC REVIEW COMPLETE
WO-RISK-04-CHG1            = PASS CANDIDATE
PR                         = #366
previous HEAD              = f87446eca5ebb92b967e110d6ae5747e9d715ee7
NEW MIGRATION              = 0
RISK-04-APPROVE-001        = NOT OPENED
MERGE                      = NOT AUTHORIZED
```

---

## CHG_REQUIRED cause

GPT/Owner Batch 001 review found two systemic generator errors:

```text
CIC_W 1722 → PROCESS ALL          = REJECTED
same-name + different-parent
  → HOLD ALL (KALIS)              = REJECTED
SYSTEMIC_KIND_RULE_ISSUE          = YES
```

Batch 001 CIC_W 50 mixed process-like nodes with material/component, facility/equipment, classification, and method/task-like items. KALIS same-name different-parent mixed true merge-review pairs with distinct operational tasks.

---

## CIC_W → PROCESS ALL rejection

Unreviewed CIC_W no longer defaults to PROCESS.

```text
CIC_W nodes              = 1722
CIC_W reviewed           = 50
CIC_W unreviewed         = 1672
CIC_W unreviewed PROCESS = 0
CIC_W unreviewed AMBIGUOUS = 1672
```

Reviewed 50 (explicit GPT override only):

```text
PROCESS             = 24
AMBIGUOUS           = 16
MATERIAL_COMPONENT  = 7
FACILITY_EQUIPMENT  = 2
CLASSIFICATION      = 1
TASK                = 0
METHOD              = 0
```

`METHOD = 0` in this sample because method-like HOLD rows stayed AMBIGUOUS. It does not mean CIC_W has no methods.

The 24 PROCESS rows are seed-candidate-possible only:

```text
OWNER APPROVED SEEDS = 0
```

---

## Semantic kind gate contract

```text
SOURCE NODE
  → SEMANTIC KIND GATE
  → PROCESS / TASK ?
  → YES → CANONICAL SEED CANDIDATE
```

Enum:

```text
PROCESS
TASK
METHOD
MATERIAL_COMPONENT   (= MATERIAL · COMPONENT)
FACILITY_EQUIPMENT   (= FACILITY · EQUIPMENT)
CLASSIFICATION
AMBIGUOUS
```

Name-suffix heuristics (`공사`/`작업`/`공법`/`설비`/`재`) are not a gate. Kind is `EXPLICIT_REVIEW_OVERRIDE` or `AMBIGUOUS` / source-kind default.

---

## DB node_kind vs semantic_kind

```text
risk_canonical_nodes.node_kind = PROCESS / TASK
```

is unchanged. `METHOD`, `MATERIAL_COMPONENT`, `FACILITY_EQUIPMENT`, `CLASSIFICATION`, `AMBIGUOUS` cannot be canonical nodes. Mapping to those kinds as `POSSIBLE_RELATED` self-targets is forbidden. `AMBIGUOUS ≠ NO_MATCH`.

---

## GPT reviewed 100 decisions

Manifest: `docs/knowledge/risk/RISK04_BATCH001_GPT_REVIEW_v1.tsv`  
Result overlay: `docs/knowledge/risk/RISK04_BATCH001_CHG1_RESULT.tsv`

```text
KEEP_AS_DISTINCT = 49
MERGE_CANDIDATE  = 22
HOLD             = 17
REJECT           = 12
approval_state   = NOT_APPROVED × 100
```

KALIS 1–50: KEEP 25 / MERGE 22 / HOLD 1 (`#31`) / REJECT 2 (`#32`, `#39`).  
CIC_W 51–100: KEEP PROCESS 24 / HOLD AMBIGUOUS 16 / REJECT 10.

Frozen evidence unchanged:

```text
Batch001 SHA     = 955b3c11f092b657b54d3d94f639270f767da4156c6a3710663deeeabbb4c4b8
Review Input SHA = c28fa67368ff3af3d05f7b771cebca455c6cf5cd94884bbff44dd1bd5087df1b
```

---

## 11 merge candidate pairs

```text
1↔5   2↔4   3↔10  6↔11  7↔22  8↔47
13↔14 15↔24 16↔26 20↔30 29↔37
```

```text
MERGE_CANDIDATE ≠ MERGED ≠ APPROVED
canonical merge = 0
proposal merge  = 0
proposal delete = 0
```

---

## CIC_W reviewed-kind distribution

See counts above. REJECT kinds:

```text
MATERIAL_COMPONENT : ALC블록, ALC판넬, FRP판넬, RC말뚝, SheetPile, 가공유리, 가공재
FACILITY_EQUIPMENT : PC옹벽, PC형틀및생산시설
CLASSIFICATION     : 가구및집기
```

---

## CIC_W unreviewed default AMBIGUOUS

```text
semantic_kind        = AMBIGUOUS
seed_candidate_state = PENDING_SEMANTIC_REVIEW
```

Totals after gate:

```text
semantic PROCESS        = 24
semantic TASK           = 1381
semantic AMBIGUOUS      = 1688
semantic NON-CANONICAL  = 1698
SOURCE PROPOSAL UNIVERSE = 3103
```

`3103 ≠ canonical seed count`.

---

## KALIS multi-parent mechanical flag rule

```text
SAME_NAME_MULTI_PARENT ≠ HOLD ≠ MERGE_CANDIDATE ≠ KEEP_AS_DISTINCT
KALIS same-name multi-parent auto HOLD = 0
```

Unreviewed C TASK (711): `semantic_kind = TASK`, `semantic_review_decision = UNREVIEWED`, `generator_review_status = REVIEW_READY`. Batch 001 overlay keeps GPT decisions plus the mechanical flag.

---

## Source relation universe interpretation

```text
SOURCE RELATION REVIEW UNIVERSE = 3103
mapping approval coverage       = 0
APPROVED DB MAPPINGS            = 0
```

This is not mapping quality coverage. Non-canonical / pending / merge-review / reject rows use `UNRESOLVED` with `target_seed_proposal_key = NULL`. They are not auto `NO_MATCH`.

---

## Production mutation

```text
production DB write / migration / canonical / mapping = 0
Graph / Legal / CHEM / SaaS / customer / LLM / fuzzy  = 0
AUTO MERGED / AUTO APPROVED / canonical UUID / ACTIVE = 0
B path 620 / identity HOLD / occurrence 626 preserved
C unique 30696 / occurrence 47559 preserved
```

---

## Determinism

```text
SEMANTIC RUN1 SHA = 918b966db802f36299897a10b03cc5b4d7844103487cb43362111ff1b389ab39
SEMANTIC RUN2 SHA = 918b966db802f36299897a10b03cc5b4d7844103487cb43362111ff1b389ab39
RELATION RUN1 SHA = 1d32d36cb953856a5213266d1f2f87eb98479428f63725b6195847ba806388d5
RELATION RUN2 SHA = 1d32d36cb953856a5213266d1f2f87eb98479428f63725b6195847ba806388d5
DETERMINISM       = PASS
```

---

## Next gate

```text
WO-RISK-04-CHG1        = PASS CANDIDATE
RISK-04                = IN REVIEW
RISK-04-APPROVE-001    = NOT OPENED
NEXT                   = GPT VERIFY
MERGE                  = NOT AUTHORIZED
```

GPT independently verifies this HEAD, the 100-row manifest, and the 1722 CIC_W gate before any approve WO.
