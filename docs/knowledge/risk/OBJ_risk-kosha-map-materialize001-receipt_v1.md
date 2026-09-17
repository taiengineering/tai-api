---
class: records
type: report
scope: knowledge
project: risk
title: WO-RISK-KOSHA-MAP-MATERIALIZE-001 KOSHA production mapping materialization
version: 1
status: active
owner: taiwang
---

# WO-RISK-KOSHA-MAP-MATERIALIZE-001 — KOSHA Owner-Approved Source Mapping Materialization

Owner-approved KOSHA source→canonical mapping package has been
materialized to production `risk_source_mappings`. Row-level authority:
frozen owner approval binding. 46 rows inserted (6 EXACT + 40
NARROWER). 29 POSSIBLE_RELATED rows remained HOLD and were not written.
No canonical / sector / KALIS mutation. Existing CIC_W 1139 rows
untouched.

## Anchors

```text
owner approval id             = RISK-KOSHA-MAP-APPROVE-001
owner approval binding SHA    = 3c2f0a0f3558a7e0fd7a0d801ed22d18ba3d7fbed3f86a3ca54aa022f2e87a91
candidate SoT SHA             = 4952310fafda56d620f10a53a4c4faa765c73338157e1992c6d690428e4f869a
canonical task reference SHA  = a22f3a83f3cc2563554eb04b71ac8afc1faff44e3a6a594dd265ff04baafa2a6
canonical receipt SHA         = c8c4232bf924b52636c9dc33fb1891473d548e09ed15de35f33764fe18603f3c
source ingest receipt SHA     = 9493ff9f5515eec26daf0204589d1fa3dbb8128f2b58f3590f49244ebb4ecef4
```

## Production result

```text
mappings_before               = 1139
mappings_after                = 1185
CIC_W (unchanged)             = 1139
KOSHA (new)                   = 46
KALIS (unchanged)             = 0

KOSHA mapping_status APPROVED = 46
KOSHA mapping_method MANUAL   = 46
KOSHA EXACT_EQUIVALENT        = 6
KOSHA NARROWER_THAN           = 40
KOSHA POSSIBLE_RELATED        = 0
HOLD leaked into production   = 0

canonical_nodes total         = 1110
canonical_nodes ACTIVE        = 0
risk_canonical_node_sectors   = 0
```

## Owner approval accounting

```text
APPROVED (input)              = 46
INSERTED                      = 46
HOLD (excluded)               = 29
REJECTED                      = 0

EXACT_EQUIVALENT approved     = 6
NARROWER_THAN approved        = 40
POSSIBLE_RELATED HOLD         = 29

CANONICAL MUTATION            = 0
NEW CANONICAL                 = 0
```

## Receipt

```text
RISK KOSHA MATERIALIZATION RECEIPT SHA = 08dd77ceb0b5ecf500276bf2992457c6f6ac6e347f35e26efc8ce80d04b8c64e
receipt file                            = docs/knowledge/risk/RISK_KOSHA_MAP_MATERIALIZE001_RECEIPT_v1.tsv
```

## Verdict

```text
WO-RISK-KOSHA-MAP-MATERIALIZE-001 = PASS / PRODUCTION_MATERIALIZED / EVIDENCE_READY
MERGE = NOT AUTHORIZED
NEXT  = GPT LEAN MATERIALIZATION VERIFY
THEN  = PR #374 CLOSEOUT / MERGE GATE
STOP
```
