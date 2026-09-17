---
class: records
type: report
scope: knowledge
project: risk
title: WO-RISK-KALIS-MAP-001-R1 KALIS mapping review evidence
version: 1
status: active
owner: taiwang
---

# WO-RISK-KALIS-MAP-001-R1 — KALIS TASK Review Evidence (Delta-Only)

## THIS IS EVIDENCE PREPARATION ONLY

```text
THIS IS NOT SEMANTIC DECISION
THIS IS NOT OWNER APPROVAL
THIS IS NOT PRODUCTION MAPPING
THIS DOES NOT LIFT KALIS IDENTITY HOLD

FAMILY IS REVIEW COMPRESSION AID
FAMILY IS NOT CANONICAL IDENTITY
```

## Inputs (frozen)

```text
KALIS source CSV               = artifacts/risk01/source_c/kalis_risk_profile.csv
canonical TASK reference SHA   = a22f3a83f3cc2563554eb04b71ac8afc1faff44e3a6a594dd265ff04baafa2a6
CIC_W mapping proposal         = RISK_MAP001_CICW_MAPPING_PROPOSAL_v1.tsv
KOSHA owner approval binding   = RISK_KOSHA_MAP_APPROVE001_OWNER_APPROVAL_BINDING_v1.tsv
```

Frozen production totals reused verbatim (not reverified this WO):

```text
CIC_W approved mappings   = 1139
KOSHA approved mappings   =   46
existing total mappings   = 1185
KALIS production mappings =    0
canonical                 = 1110 (DRAFT 1110 / ACTIVE 0)
sectors                   =    0
```

## KALIS census

```text
KALIS_RISK_PROFILE source nodes = 816
  WORK_BIG                       =   7
  WORK_MID                       =  48
  TASK                           = 761

distinct TASK name (normalized)  =  40
review families                  =  40
review rows                      = 761
unique review_key                = 761
unique source_key                = 761
```

## Candidate retrieval

Mechanical only — no LLM, no fuzzy, no embedding, no Kiwi, no
synonym expansion. Candidate cap = 10 / family.

Layer A : exact name_normalized against 554 TASK canonicals
Layer B : substring match on retrieval token (terminal '작업' dropped for retrieval only)
Layer C : token overlap ≥ 1

Per-candidate evidence attaches CIC_W + KOSHA APPROVED source_names
already mapped to that canonical target.

### Candidate distribution across 761 review rows

```text
  candidates = 0   rows = 309
  candidates = 1   rows = 81
  candidates = 2   rows = 55
  candidates = 3   rows = 2
  candidates = 4   rows = 25
  candidates = 5   rows = 50
  candidates = 6   rows = 23
  candidates = 7   rows = 18
  candidates = 8   rows = 18
  candidates = 10   rows = 180
```

## Frozen output SHAs

```text
RISK KALIS MAP001 REVIEW UNIVERSE SHA = 50446a5c9fa421f09beb1425ffe8d90649b29e50bafe93f46d8913a085ed497d
RISK KALIS MAP001 REVIEW SUMMARY SHA  = 96b5dc4403078e33c325e22265b316dc1ba970aef4ee347e2e9143caae2aa8a0
```

## Reused frozen evidence (not reverified)

```text
FROZEN EVIDENCE REUSED =
PR #362  (RISK-01)
PR #363  (RISK-02)
PR #364  (RISK-03)
PR #366  (CIC_W)
PR #374  (KOSHA)

FROZEN EVIDENCE REVERIFIED =
NO
```

## Verdict

```text
WO-RISK-KALIS-MAP-001-R1 = PASS / GPT_REVIEW_READY
KALIS TASK = 761 / 761
review families = 40
SEMANTIC DECISION = NOT EXECUTED
OWNER APPROVAL = NOT OPENED
KALIS PRODUCTION MAPPING = 0
CANONICAL MUTATION = 0
MAPPING WRITE = 0
MERGE = NOT AUTHORIZED
NEXT = GPT DELTA-ONLY VERIFY → GPT KALIS SEMANTIC REVIEW
STOP
```
