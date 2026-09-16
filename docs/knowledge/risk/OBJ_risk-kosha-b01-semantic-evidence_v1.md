---
class: records
type: report
scope: knowledge
project: risk
title: WO-RISK-KOSHA-B01-EVIDENCE-001 KOSHA B01 semantic review evidence
version: 1
status: active
owner: taiwang
---

# WO-RISK-KOSHA-B01-EVIDENCE-001 — KOSHA B01 Semantic Review Evidence

## THIS IS EVIDENCE ONLY

```text
THIS IS EVIDENCE ONLY
THIS IS NOT GPT SEMANTIC DECISION
THIS IS NOT MAPPING APPROVAL
THIS IS NOT PRODUCTION MATERIALIZATION
KOSHA IDENTITY HOLD IS PRESERVED
```

## Inputs (frozen repository evidence)

```text
GPT REVIEW PACK SHA               = 20bcdf3a7827a2446dae933a1d055463176478cccf86f7ad8c607c23fe29f9b5
KOSHA REVIEW UNIVERSE SHA         = 30a2762eec244518fd73eb53fb0c3e53f56e6a41669569d94ee570175cd0e04a
CANONICAL RECEIPT SHA             = c8c4232bf924b52636c9dc33fb1891473d548e09ed15de35f33764fe18603f3c
CIC_W PROPOSAL SHA                = 036d293c6e2fa506922c53ffcfdd44476ec903fdc639e2c12b73815d4401f026
MAP MATERIALIZATION RECEIPT SHA   = 8aa2efc056ac9873db108c07bce72ce691308badb7d413cc45cf306c110cc61b
```

No live-DB query. CIC_W provenance is reconstructed from the frozen
proposal, gated by the frozen materialization receipt so we only trust
proven-in-production provenance (1139 rows).

## B01 composition

```text
B01 rows                          = 100
EXACT_NAME_CANDIDATE              = 12
SEMANTIC_SEARCH_REQUIRED          = 88
rows with mechanical candidates   = 25
rows with zero mechanical candidates = 75
canonical TASK reference          = 554
```

## Mechanical scoring (WO §14)

```text
EXACT_NORMALIZED_NAME             = 1000
source in canonical (substring)   = 300
canonical in source (substring)   = 300
shared source-name token          = 50 each
shared work_type token in path    = 20 each
shared project_kind token in path = 10 each
top-N cap                         = 10
```

This score is a deterministic sort key, not a semantic confidence. Higher score
does **not** imply approval or equivalence. GPT semantic review must still pick
the mapping type + status.

### Tokenization

```text
normalization        = NFC + collapse whitespace + [\s/·ㆍ・,] normalizer
tokenization         = re.split(r'[^\w]+') with unicode flag
stopwords            = (none)
morphological analyzer = none (no Kiwi, no synonyms)
```

## SHAs

```text
RISK KOSHA B01 CANONICAL TASK REFERENCE SHA = a22f3a83f3cc2563554eb04b71ac8afc1faff44e3a6a594dd265ff04baafa2a6
RISK KOSHA B01 SEMANTIC EVIDENCE SHA        = bfa75ed7cb87368f9b0744188bd07ac87a495d641945e0e731565fda6517fde8
```

## Verdict

```text
WO-RISK-KOSHA-B01-EVIDENCE-001 = EVIDENCE_FROZEN / GPT_REVIEW_READY
B01 SEMANTIC DECISIONS = 0
KOSHA PRODUCTION MAPPINGS = 0
MERGE = NOT AUTHORIZED
NEXT = GPT KOSHA SEMANTIC REVIEW BATCH 01
STOP
```
