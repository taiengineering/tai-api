---
class: records
type: receipt
scope: knowledge
project: risk
title: WO-RISK-MAP-APPROVE-001 Owner mapping approval execution receipt
version: 1
status: active
owner: taiwang
---

# WO-RISK-MAP-APPROVE-001 — Owner Mapping Approval Execution Receipt

## Approval

```text
OWNER APPROVAL           = EXECUTED
APPROVAL ID              = RISK-MAP-APPROVE-001
APPROVAL STATE           = OWNER_APPROVED
APPROVAL TARGET          = EXACT MAPPING PACKAGE SNAPSHOT
PROPOSAL FILE            = RISK_MAP001_CICW_MAPPING_PROPOSAL_v1.tsv
PROPOSAL ROWS            = 1139
PROPOSAL SHA             = 036d293c6e2fa506922c53ffcfdd44476ec903fdc639e2c12b73815d4401f026
```

## Anchors

```text
CANONICAL RECEIPT SHA        = c8c4232bf924b52636c9dc33fb1891473d548e09ed15de35f33764fe18603f3c
SOURCE INGEST RECEIPT SHA    = 9493ff9f5515eec26daf0204589d1fa3dbb8128f2b58f3590f49244ebb4ecef4
CANONICAL OWNER PACKAGE SHA  = 62c2c50e3c0becbe23a686735d1a7e50ed8bce2f3fa23c539d2250b68227c2d7
```

## Binding identity

```text
RISK MAP APPROVAL BINDING SHA = 402b4004b987169e1cc5b9b0356061794218ef45ee473839b80b72a91cf1f9ed
BINDING TARGET               = PACKAGE_SHA_NOT_HEAD
```

Binding identity SHA is computed over the fields
`approval_id, approval_state, proposal_rows, proposal_sha256, canonical_receipt_sha, source_ingest_receipt_sha, canonical_owner_package_sha, mapping_type, mapping_method, scope_source_id, binding_target` — timestamp and HEAD are intentionally
excluded, so the same approved package yields the same binding identity across
re-executions.

## Scope

```text
scope_source_id          = CIC_W
mapping_type             = EXACT_EQUIVALENT (all 1139 rows)
mapping_method           = MANUAL_REVIEW (all 1139 rows)
KOSHA mapping            = 0
KALIS mapping            = 0
source 673 mapping       = 0  (HOLD_LABEL preserved)
```

## What this approval does NOT authorize

```text
OWNER MAPPING APPROVAL != PRODUCTION MAPPING MATERIALIZATION
OWNER MAPPING APPROVAL != CANONICAL ACTIVE TRANSITION

production_write_authorized  = NO
materialization_authorized   = NO
merge_authorized             = NO
```

Downstream materialization is a separate WO whose inputs are:

```text
RISK MAP001 PROPOSAL SHA        = 036d293c6e2fa506922c53ffcfdd44476ec903fdc639e2c12b73815d4401f026
RISK MAP APPROVAL BINDING SHA   = 402b4004b987169e1cc5b9b0356061794218ef45ee473839b80b72a91cf1f9ed
```

## Execution metadata (evidence-only, not in binding SHA)

```text
owner_approval_event_utc      = 2026-09-16T20:37:16Z
repository_head_at_execution  = e1c887d3345b873a884027e9a71977906b9d16be
```

## Verdict

```text
WO-RISK-MAP-APPROVE-001 = OWNER_APPROVAL_BOUND / EVIDENCE_READY
PRODUCTION MAPPING           = NOT MATERIALIZED
APPROVED PRODUCTION ROWS     = 0
MATERIALIZATION              = NOT OPENED
MERGE                        = NOT AUTHORIZED
NEXT                         = GPT INDEPENDENT VERIFY
STOP
```
