---
class: records
type: report
scope: knowledge
project: risk
title: OBJ-RISK-02 INGEST-001 production source core
version: 1
status: active
owner: taiwang
---

# OBJ-RISK-02-INGEST-001 — Production Source Core Ingest

This pack loads frozen A/B/C source snapshots, nodes, records, and memberships. Mapping is not opened. Canonical DRAFT rows stay unchanged. SOURCE FILE ACCEPTED ≠ IDENTITY HOLD 해제.

```text
CANONICAL MATERIALIZATION RECEIPT SHA = c8c4232bf924b52636c9dc33fb1891473d548e09ed15de35f33764fe18603f3c
RISK02 DETERMINISM SHA = 886d45cdaaf9478d066f22e2bfca3ee35128d5bfbda2eddfff664f87ffa7bbfa
A SHA = bef821019cd32ad9512f865d179852652d1f7aa9536be41b68c6e403fe0baa29
B SHA = 8e98fbb66d9e152a03425338d27fc738172cdf6dd5d46a36e7a5a06d80012b91
C SHA = 399dbe64dcf1b5d1445fd51e968070dd26e0a40583f8e0afc5e9219839c958c8
```

This is an explicit evidence pack, not a classifier.

---

## Planned Census

```text
A nodes = 1722
A identity = PASS
B raw rows = 626
B path identities = 620
B nodes = 787
B duplicate path groups = 3
B duplicate extras = 6
B leaf occurrence sum = 626
B identity = HOLD
C raw rows = 47559
C unique records = 30696
C nodes = 816
C task nodes = 761
C occurrence sum = 47559
planned memberships = 34021
```

---

## Production

```text
production execution = EXECUTED
ACCEPTED snapshots = 3
risk_source_nodes = 3325
risk_records = 30696
snapshot memberships = 34021
canonical DRAFT = 1110
canonical ACTIVE = 0
mapping write = 0
sector write = 0
SOURCE INGEST RECEIPT SHA = 9493ff9f5515eec26daf0204589d1fa3dbb8128f2b58f3590f49244ebb4ecef4
```

---

## Verdict

```text
WO-RISK-02-INGEST-001 = SOURCE_CORE_INGESTED / EVIDENCE_READY
MAPPING = NOT OPENED
ACTIVE TRANSITION = NOT OPENED
MERGE = NOT AUTHORIZED
NEXT = GPT INDEPENDENT VERIFY
THEN = SOURCE MAPPING GOVERNANCE
STOP
```


---

## Repair Evidence (RISK-02 W1)

```text
partial ingest anomaly           = 30 rows in initial 8010 (Cursor MCP path)
repair                           = 30 targeted rows in one transaction
authority                        = frozen local plan
RISK02 DETERMINISM SHA           = 886d45cdaaf9478d066f22e2bfca3ee35128d5bfbda2eddfff664f87ffa7bbfa
manifest                         = docs/knowledge/risk/RISK02_RECORD_REPAIR_DRYRUN_v1.tsv
concurrency guard                = 30 / 30 PASS
post-repair full exact scan      = 30696 / 30696 PASS
KOSHA identity_status            = HOLD / preserved through ACCEPTED
KOSHA DETAIL_PROCESS occurrence  = 626
KOSHA all-node occurrence sum    = 793
KALIS record occurrence sum      = 47559
```
