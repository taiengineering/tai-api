---
class: records
type: report
scope: knowledge
project: risk
title: WO-RISK-MAP-001 CIC_W approved-provenance source mapping governance
version: 1
status: active
owner: taiwang
---

# WO-RISK-MAP-001 — CIC_W Source Mapping Governance (Plan / Evidence Freeze)

Owner-approved TAI canonical concepts (1110) are the semantic authority. This
package converts approved concept membership into an immutable source →
canonical mapping proposal. No search identity, no fuzzy, no LLM. Production
mapping write = 0.

## Anchors

```text
CANONICAL RECEIPT SHA        = c8c4232bf924b52636c9dc33fb1891473d548e09ed15de35f33764fe18603f3c
SOURCE INGEST RECEIPT SHA    = 9493ff9f5515eec26daf0204589d1fa3dbb8128f2b58f3590f49244ebb4ecef4
OWNER PACKAGE SHA            = 62c2c50e3c0becbe23a686735d1a7e50ed8bce2f3fa23c539d2250b68227c2d7
OWNER APPROVAL ID            = RISK-04-APPROVE-001
```

Owner approval of canonical concept membership is NOT approval of the mapping
package. Mapping approval is a separate future WO.

## Scope

```text
source_id in scope           = CIC_W (only)
KOSHA mapping                = 0
KALIS mapping                = 0
```

## Census

```text
approved concepts            = 1110
expanded CIC_W source members = 1139
unique source keys           = 1139
canonical targets covered    = 1110 / 1110

PROMOTED targets             = 1082
PROMOTED mapping rows        = 1082
MERGED targets               = 28
MERGED mapping rows          = 57

mapping_type                 = EXACT_EQUIVALENT (all 1139 rows)
mapping_status               = PROPOSED (all 1139 rows)
mapping_method               = MANUAL_REVIEW (all 1139 rows)

HOLD source (source_key=673) = present in HOLD package, NOT in mapping proposal
semantic exclusions          = 582
CIC_W total accounting       = 1139 + 1 + 582 = 1722
```

## Evidence basis

Every proposal row's `evidence_basis = OWNER_APPROVED_CONCEPT_MEMBERSHIP`. The
provenance is the semantic review + Owner package approval, not name or path
similarity.

## Package SHA

```text
RISK MAP001 PROPOSAL SHA     = 036d293c6e2fa506922c53ffcfdd44476ec903fdc639e2c12b73815d4401f026
```

This SHA is the anchor for the subsequent SOURCE MAPPING APPROVAL WO. It does
not by itself grant mapping approval.

## Guardrails

```text
production risk_source_mappings write = 0
canonical unchanged (1110 DRAFT / 0 ACTIVE / 0 canonical_code assigned)
mapping_status APPROVED               = 0
NO_MATCH / AMBIGUOUS / REJECTED rows  = 0
LLM / fuzzy / embedding used          = 0
```

## Verdict

```text
WO-RISK-MAP-001 = MAPPING_PROPOSAL_FROZEN / EVIDENCE_READY
PRODUCTION MAPPING = NOT MATERIALIZED
APPROVED MAPPING = 0
NEXT = GPT INDEPENDENT VERIFY
THEN = OWNER MAPPING APPROVAL
MERGE = NOT AUTHORIZED
STOP
```
