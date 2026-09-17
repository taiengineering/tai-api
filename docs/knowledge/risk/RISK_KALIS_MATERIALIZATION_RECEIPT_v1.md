---
class: records
type: report
scope: knowledge
project: risk
title: WO-RISK-KALIS-MATERIALIZE-001 KALIS production mapping materialization
version: 1
status: active
owner: taiwang
---

# WO-RISK-KALIS-MATERIALIZE-001 — KALIS Owner-Approved Source Mapping Materialization

Owner-approved KALIS source→canonical mapping package has been
materialized to production `risk_source_mappings`. 9 rows inserted
(all NARROWER_THAN → 발파굴착). 39 HOLD rows (POSSIBLE_RELATED:
용접작업 / 양생작업 / 인발작업) remained HOLD and were not written.
No canonical mutation, no sector write, no ACTIVE transition.

## Anchors

```text
owner approval id             = RISK-KALIS-MAP-APPROVE-001
owner approval date           = 2026-09-17
owner approval binding SHA    = ac75691caef78a44fa4036ab81435549f1f4d93f1a28a026c4b0f1602e34f03e
approved family               = 장약 및 발파작업
approved target               = 473d69ee-4433-487f-bc43-c35c1f2ea28f  발파굴착
```

## Production result

```text
mappings_before               = 1185
mappings_after                = 1194
CIC_W (unchanged)             = 1139
KOSHA (unchanged)             = 46
KALIS (new)                   = 9

KALIS NARROWER_THAN           = 9
KALIS mapping_status APPROVED = 9
KALIS mapping_method MANUAL   = 9
KALIS distinct canonical      = 1
HOLD leaked into production   = 0

canonical_nodes total         = 1110
canonical_nodes ACTIVE        = 0
risk_canonical_node_sectors   = 0
```

## Owner approval accounting

```text
APPROVED (input)              = 9
INSERTED                      = 9
HOLD (excluded)               = 39
REJECTED                      = 0

CANONICAL MUTATION            = 0
SECTOR WRITE                  = 0
ACTIVE TRANSITION             = 0
NEW CANONICAL                 = 0
```

## Receipt

```text
RISK KALIS MATERIALIZATION RECEIPT SHA = c8daa8f08b06d1ac7a72e9a9977d0cc3307063bb3ee2b2ea93cf5738296f912d
receipt file                            = docs/knowledge/risk/RISK_KALIS_MATERIALIZATION_RECEIPT_v1.tsv
```

## Reused frozen evidence (not reverified)

```text
PR #362 / #363 / #364 / #366 / #374 = MERGED
CIC_W production mappings           = 1139 (unchanged)
KOSHA production mappings           =   46 (unchanged)
```

## Verdict

```text
WO-RISK-KALIS-MATERIALIZE-001 = PASS / PRODUCTION_MATERIALIZED / GPT_MERGE_REVIEW_READY
MERGE = NOT AUTHORIZED (GPT verify first)
NEXT  = GPT DELTA-ONLY VERIFY → PR #376 MERGE
STOP
```
