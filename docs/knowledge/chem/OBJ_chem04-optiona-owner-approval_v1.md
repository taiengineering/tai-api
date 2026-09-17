---
class: records
type: report
scope: knowledge
project: chem
title: WO-CHEM-04-OPTIONA-FREEZE-MERGE-001 Owner Option-A policy freeze
version: 1
status: active
owner: taiwang
---

# WO-CHEM-04-OPTIONA-FREEZE-MERGE-001 — Owner Option-A Policy Freeze

## Owner authority

```text
OWNER APPROVAL           = EXECUTED
OWNER APPROVAL DATE      = 2026-09-18 KST
```

## Decision

```text
POLICY                   = OPTION A
OPTION B                 = REJECTED
OPTION C                 = REJECTED / TECHNICAL GATE FAIL
```

### Meaning

```text
SECONDARY DATASET STATUS = NON_AUTHORITATIVE

secondary dataset        = research / comparison / bootstrap evidence only
secondary dataset       != current authoritative source
secondary dataset       != production authoritative MSDS
secondary dataset       != customer-facing official KOSHA MSDS

AUTHORITATIVE CONTENT SOURCE = KOSHA OFFICIAL
```

## Frozen evidence reused (not reverified this WO)

Merged, reused verbatim:

```text
PR #344 = CHEM-02 catalog/schema/adapter        MERGED
PR #346 = CHEM-03 enumeration/quota research    MERGED
PR #348 = CHEM enumeration gate                 MERGED
PR #350 = CHEM-04 identity census               MERGED
```

Frozen numbers:

```text
official current chemId  = 20,568
secondary identity rows  = 48,963
official ∩ secondary     = 18,478
SECONDARY_COMPLETE       =  9,124
SECONDARY_PARTIAL        =  9,354
SECONDARY_MISSING        =  2,090

STRICT_API_CALLS         = 329,088
STRUCTURAL_DELTA_CALLS   =  51,940
```

## Option-C live sample evidence (frozen, not reverified)

```text
sample                   = 256 / 256 successful
API_ERROR                = 0

EXACT                    = 227
NORMALIZED_EQUAL         =   0
CONTENT_DIFFERENT        =  29

SECTION FIDELITY         = 88.67%
CHEMICAL ALL_MATCH       =  3 / 16
CHEMICAL HAS_DIFFERENCE  = 13 / 16
```

Frozen SHAs (from
`OBJ_chem04-optionc-live-sample-resume_v1.md`):

```text
sample_manifest SHA      = b404725ade87b289e124abcca0652e91ec4bace1f5094d79f251860035af2351
preflight report SHA     = e2b92dafd5fb8195200d3ff863410facb85a045ed15d518375a00da1aedf6527
comparison.jsonl SHA     = e723c8ae9350f7acb7e66465f454e8633e03c253f4537b24e82785f494aa8b7e
live_sample_report SHA   = 3bc3117e6fd66e57b03433cdc6086367f8d92dc9c37dd4fd1fe4344f2a09f930
```

### Option-C rejection basis

```text
required fidelity        = >= 99%
actual fidelity          =    88.67%
CONTENT_DIFFERENT        =    29
explained differences    =     0 / 29
```

Section 11 (독성정보) dominates the diffs (12 / 29). Chem `134944`
alone accounts for 11 of the 29 CONTENT_DIFFERENT rows. Tool-side
`possible_cause` returned `UNKNOWN` for all 29 — no automatic
classification of "safe difference" was possible. The technical
gate for Option C therefore fails on both fidelity threshold and
un-explained divergence.

## Policy contract (frozen)

The following fields are Owner-locked at policy level. This WO
does NOT implement DB schema / code; it only fixes the intent.

```text
content_origin           = SECONDARY_BOOTSTRAP | KOSHA_OFFICIAL
current_verified         = false unless official verification exists
authoritative_verified   = false unless official verification exists
```

Under this contract:

```text
secondary row → current_verified        = FORBIDDEN auto-promotion
secondary row → authoritative_verified  = FORBIDDEN auto-promotion
secondary row → customer publication    = FORBIDDEN
```

## Scope closure

```text
PRODUCTION INGEST                        = 0
DB WRITE                                 = 0
FULL HYDRATION                           = NOT OPENED
CANONICAL MUTATION                       = 0
NEW CHEMICAL SCHEMA THIS WO              = 0
GRAPH / PAID / SAAS INTEGRATION THIS WO  = 0

official bulk hydration (329,088 calls)  = NOT EXECUTED
structural-delta hydration (51,940 calls) = NOT EXECUTED
```

## Anchors

```text
tai-api main HEAD (guard)                = 82744667ff06b6b4ce70cb5a094526b14bf8f203
PR                                       = #359
branch                                   = feature/chem04-content-local-audit
PR HEAD (pre-owner-receipt)              = 16d349158a269a352f0b1847db94b0affa8bbe87
CI run on that exact HEAD                = 35234370928 SUCCESS
```

## Verdict

```text
OWNER APPROVAL                           = EXECUTED / OPTION A
SECONDARY AUTHORITATIVE                  = NO
KOSHA OFFICIAL AUTHORITATIVE             = YES
OBJ-CHEM                                 = IN_PROGRESS  (NOT DONE)
FULL HYDRATION                           = NOT OPENED
NEXT                                     = GPT official hydration / quota execution design
STOP
```
