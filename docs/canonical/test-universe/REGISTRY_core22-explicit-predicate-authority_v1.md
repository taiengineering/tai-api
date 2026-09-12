---
wo: WO-SM-E2E-CANONICAL-PREDICATE-FIXTURE-AUTHORITY-001
class: records
type: registry
scope: canonical
project: test-universe
title: CORE22 Explicit Predicate Authority v1 (APPROVED)
version: 1
status: approved
owner: taiwang
---

# REGISTRY — CORE22 Explicit Predicate Authority v1 (APPROVED)

> WO-SM-E2E-CANONICAL-PREDICATE-FIXTURE-AUTHORITY-001 Stage B.
> Frozen112 companion authority. Owner Approval binds to the exact JSON SHA256 below.
> **PRODUCTION DERIVATION RULE = NONE.** These values define synthetic E2E Profiles only.

## RAW CONTEXT IS NOT AUTHORITY

Raw `construction_type` / `construction_type_code` / `order_type` / worker counts
are review context only. They did **not** generate the approved booleans.

Do not read this table as:

- `sector=CONSTRUCTION` → `is_construction=true`
- `order_type=하도급` → `is_relationship_contractor=true`
- `construction_type_code=CIVIL` → `is_civil_construction=true`

## Binding

| Item | Value |
|---|---|
| Frozen source | `~/45cm-test/profile_universe_v1.json` (not copied; not mutated) |
| Frozen profile SHA256 | `4818a63ab261c5a36c1432647b6b17e7636641071801d36fd1b85d1361af751b` |
| Frozen profile count | 112 |
| Frozen112 mutation | 0 |
| Authority path | `docs/canonical/test-universe/core22_explicit_predicate_authority_v1.json` |
| authority_type | `OWNER_APPROVED_E2E_FIXTURE_FACT` |
| status | `APPROVED` |
| Authority JSON SHA256 | `21b32a48af95d604bb7e76a7c7543ab7359a9f3ee721c802824972f7437d0611` |
| Owner Approval | binds to that exact byte snapshot |
| Construction rows | 27 |
| Non-construction rows | 0 |
| Predicate cells | 81 bool |
| null | 0 |
| derivation | 0 |

## Construction Profile IDs (exact order)

PF-0028, PF-0029, PF-0030, PF-0031, PF-0032, PF-0033, PF-0034, PF-0035, PF-0036, PF-0052, PF-0053, PF-0054, PF-0055, PF-0056, PF-0057, PF-0094, PF-0095, PF-0096, PF-0097, PF-0098, PF-0099, PF-0100, PF-0101, PF-0102, PF-0103, PF-0104, PF-0105

## Owner-approved facts

is_construction = true for all 27 Construction profiles.

is_relationship_contractor = true only for PF-0033; false for the other 26.

is_civil_construction = true for PF-0030, PF-0031, PF-0036, PF-0095, PF-0096, PF-0101, PF-0103; false for the other 20.

Mandatory boundary (is_construction / is_relationship_contractor / is_civil_construction):

| Profile | Approved facts | contract_amount_eok |
|---|---|---:|
| PF-0052 | true / false / false | 49 |
| PF-0053 | true / false / false | 50 |
| PF-0054 | true / false / false | 51 |
| PF-0055 | true / false / false | 119 |
| PF-0056 | true / false / false | 120 |
| PF-0057 | true / false / false | 121 |

## Review pack (raw context is not authority)

| Profile | Amount | Raw construction_type_code | Raw order_type | is_construction | relationship | civil |
|---|---:|---|---|---|---|---|
| PF-0028 | 18 | BUILDING | 원도급 | true | false | false |
| PF-0029 | 6 | BUILDING | 원도급 | true | false | false |
| PF-0030 | 18 | CIVIL | 원도급 | true | false | true |
| PF-0031 | 18 | CIVIL | 원도급 | true | false | true |
| PF-0032 | 18 | COMMON | 원도급 | true | false | false |
| PF-0033 | 6 | BUILDING | 하도급 | true | true | false |
| PF-0034 | 1 | COMMON | 원도급 | true | false | false |
| PF-0035 | 6 | COMMON | 원도급 | true | false | false |
| PF-0036 | 18 | CIVIL | 원도급 | true | false | true |
| PF-0052 | 49 | BUILDING | 원도급 | true | false | false |
| PF-0053 | 50 | BUILDING | 원도급 | true | false | false |
| PF-0054 | 51 | BUILDING | 원도급 | true | false | false |
| PF-0055 | 119 | BUILDING | 원도급 | true | false | false |
| PF-0056 | 120 | BUILDING | 원도급 | true | false | false |
| PF-0057 | 121 | BUILDING | 원도급 | true | false | false |
| PF-0094 | 30 | BUILDING | 원도급 | true | false | false |
| PF-0095 | 6 | CIVIL | 원도급 | true | false | true |
| PF-0096 | 30 | CIVIL | 원도급 | true | false | true |
| PF-0097 | 50 | COMMON | 원도급 | true | false | false |
| PF-0098 | 1 | BUILDING | 원도급 | true | false | false |
| PF-0099 | 6 | COMMON | 원도급 | true | false | false |
| PF-0100 | 1 | COMMON | 원도급 | true | false | false |
| PF-0101 | 50 | CIVIL | 원도급 | true | false | true |
| PF-0102 | 18 | BUILDING | 원도급 | true | false | false |
| PF-0103 | 50 | CIVIL | 원도급 | true | false | true |
| PF-0104 | 18 | COMMON | 원도급 | true | false | false |
| PF-0105 | 6 | BUILDING | 원도급 | true | false | false |

## Dry projection (no HTTP)

```text
Profiles                 = 112
Projection success       = 112 / 112
Construction             = 27
Construction predicates  = 27 / 27
Non-construction inject  = 0
type(value) is bool      = 27 × 3
None                     = 0
HTTP                     = 0
quota change             = 0
Clean112                 = NOT RUN
```

Bridge:

Frozen Profile + Approved Authority(profile_id exact) → Official DiagnosisRunBody.

Missing row / null / non-bool → `E2E_FIXTURE_AUTHORITY_MISSING` before HTTP.

## Candidate SHA (superseded in this file, not a second version)

Stage A CANDIDATE SHA256 was `30ffa5301a851242a29fc9099073353f6447d5a1900d48d482a68ec87d9fe91b`.
This v1 file is now APPROVED. After this approval, do not overwrite values in place;
a later change requires a new version.
