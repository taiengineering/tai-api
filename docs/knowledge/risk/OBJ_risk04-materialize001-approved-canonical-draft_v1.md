---
class: records
type: report
scope: knowledge
project: risk
title: OBJ-RISK-04 MATERIALIZE-001 approved canonical draft
version: 1
status: active
owner: taiwang
---

# OBJ-RISK-04-MATERIALIZE-001 — Approved Canonical Draft Materialization

This pack rebuilds the Owner-approved exact 1110-row snapshot as a DRAFT canonical plan. OWNER APPROVAL ≠ ACTIVE. Cursor does not assign canonical_code, write mappings, write sectors, insert L-02, or invent a parent for L-02 children.

```text
OWNER APPROVAL = VERIFIED
OWNER PACKAGE SHA = 62c2c50e3c0becbe23a686735d1a7e50ed8bce2f3fa23c539d2250b68227c2d7
APPROVAL BINDING SHA = fc2537cb3ec72f204beda6a416f77ca7a3d1c5b55f976fe1bdfa93b6f87fcfa0
APPROVED SNAPSHOT = 1110
HOLD ROWS = 1
L-02 = HOLD / NOT MATERIALIZED
WRITE READY = BLOCKED / PARENT_POINTS_TO_HOLD_L02 246dba3003df34544b7b59939c89a1aae459a17b0d356ce70df1aca64c705e94
```

This is an explicit evidence pack, not a classifier.

---

## Plan Census

```text
MATERIALIZATION PLAN ROWS = 1110
UNIQUE REVIEW CONCEPT KEY = 1110
PROCESS = 556
TASK = 554
PROMOTED_FROM_SOURCE = 1082
MERGED_FROM_REVIEWED_SOURCES = 28
TAI_NATIVE = 0
empty canonical labels = 0
parent outside approved set = 1
parent pointing to HOLD L-02 = 1
L-02 child review_concept_key = 246dba3003df34544b7b59939c89a1aae459a17b0d356ce70df1aca64c705e94
L-02 child name = 의료시험및시운전공사실가스설비공사
self parent = 0
cycle = 0
status DRAFT = 1110
status ACTIVE = 0
canonical_code assigned = 0
mapping rows generated = 0
sector rows generated = 0
PLAN SHA = 48564af3da09cb659a6296ee36a6677faa05aef3f85b7aab2f1437baecd68056
SQL SHA = f0602b25b4d72197435fec68bec20377db648fbd37a0a4e509e367432f527995
```

---

## Expected Production Contract

```text
inserted risk_canonical_nodes = 0
DRAFT = 0
ACTIVE = 0
canonical_code assigned = 0
source mapping write = 0
sector write = 0
L-02 = HOLD / NOT MATERIALIZED
partial write = 0
UUID = gen_random_uuid at insert time
production SQL = GENERATED / NOT EXECUTED
```

The generated SQL keeps a parent-outside-approved-set RAISE EXCEPTION. It cannot complete while the L-02 child remains in the 1110 snapshot.

---

## Schema / Production

```text
SCHEMA PREFLIGHT = BLOCKED
schema blocker reason = RISK03_SCHEMA_NOT_APPLIED_OR_DRIFTED
production execution = NOT_EXECUTED
PRODUCTION WRITE = 0
MATERIALIZED = 0
canonical UUID = 0
MATERIALIZATION RECEIPT SHA = NONE
```

---

## Verdict

```text
WO-RISK-04-MATERIALIZE-001 = BLOCKED
REASON = PARENT_POINTS_TO_HOLD_L02
ALSO = RISK03_SCHEMA_NOT_APPLIED_OR_DRIFTED
OWNER APPROVAL = PRESERVED
OWNER PACKAGE SHA = 62c2c50e3c0becbe23a686735d1a7e50ed8bce2f3fa23c539d2250b68227c2d7
PRODUCTION WRITE = 0
MAPPING = NOT OPENED
ACTIVE TRANSITION = NOT OPENED
MERGE = NOT AUTHORIZED
NEXT = GPT INDEPENDENT VERIFY OF L-02 PARENT LEAK
THEN = SCHEMA APPLY WO
STOP
```
