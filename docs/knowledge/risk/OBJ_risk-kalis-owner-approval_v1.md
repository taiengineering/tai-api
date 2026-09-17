---
class: records
type: report
scope: knowledge
project: risk
title: WO-RISK-KALIS-MATERIALIZE-001 Owner approval binding
version: 1
status: active
owner: taiwang
---

# WO-RISK-KALIS-MATERIALIZE-001 — KALIS Owner Approval Binding (Frozen)

## Owner authority

```text
OWNER APPROVAL ID       = RISK-KALIS-MAP-APPROVE-001
OWNER APPROVAL DATE     = 2026-09-17
```

## Decision

```text
APPROVE                 = 9
HOLD                    = 39
REJECTED                = 0
TOTAL                   = 48
```

APPROVED family:

```text
장약 및 발파작업
  semantic         = NARROWER_THAN
  target_canonical = 473d69ee-4433-487f-bc43-c35c1f2ea28f
  target_name      = 발파굴착
  source rows      = 9
```

HOLD families:

```text
용접작업              = 29
양생작업              = 5
인발작업              = 5
```

## Contract

```text
FROZEN OWNER APPROVAL BINDING SHA = ac75691caef78a44fa4036ab81435549f1f4d93f1a28a026c4b0f1602e34f03e

CANONICAL CREATE        = 0
CANONICAL RENAME        = 0
SECTOR WRITE            = 0
ACTIVE TRANSITION       = 0
PRODUCTION MATERIALIZED = NOT EXECUTED (this artifact is authority only)

FROZEN EVIDENCE REVERIFIED = NO
```

## Verdict

```text
WO-RISK-KALIS-MATERIALIZE-001 owner binding = FROZEN
NEXT = kalis_materialize_approved --execute
STOP
```
