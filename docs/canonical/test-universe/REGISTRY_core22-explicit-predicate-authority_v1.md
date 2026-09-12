---
wo: WO-SM-E2E-CANONICAL-PREDICATE-FIXTURE-AUTHORITY-001
class: records
type: registry
scope: canonical
project: test-universe
title: CORE22 Explicit Predicate Authority v1 (CANDIDATE)
version: 1
status: candidate
owner: taiwang
---

# REGISTRY — CORE22 Explicit Predicate Authority v1 (CANDIDATE)

> WO-SM-E2E-CANONICAL-PREDICATE-FIXTURE-AUTHORITY-001 Stage A.
> Frozen112 companion authority. Frozen profile SHA / Profile ID / existing layer values are not modified.
> This file is **not** a production derivation rule. Candidate cells are Owner-review UNSET facts only.

## RAW CONTEXT IS NOT AUTHORITY

The Construction-layer fields below (`construction_type`, `construction_type_code`, `order_type`, `contract_amount_eok`, worker counts, `boundary_note`) are **review context only**.

They MUST NOT be used to auto-compute:

- `sector=CONSTRUCTION` → `is_construction`
- `construction_type_code=CIVIL` → `is_civil_construction`
- `construction_type="토목"` → `is_civil_construction`
- `order_type=하도급` / `원도급` → `is_relationship_contractor`
- `subcon_workers` / PF-number patterns

Authority is only `OWNER_APPROVED_E2E_FIXTURE_FACT` after Owner Approval of exact boolean facts.

CANDIDATE generation ≠ semantic assignment. Cursor did not fill true/false.

## Stage A stop

```text
FINAL
= CORE22_E2E_PREDICATE_FIXTURE_AUTHORITY_CANDIDATE_READY

Stage B
= BLOCKED until Owner + GPT approve 27 × 3 exact bools

bridge change
= 0

quota change
= 0

HTTP run
= 0

Clean112
= NOT RUN
```

## Frozen112 binding

| Item | Value |
|---|---|
| Frozen source | `~/45cm-test/profile_universe_v1.json` (not copied; not mutated) |
| Frozen profile SHA256 | `4818a63ab261c5a36c1432647b6b17e7636641071801d36fd1b85d1361af751b` |
| Frozen profile count | 112 |
| Construction profile count | 27 |
| Duplicate Construction IDs | 0 |
| Missing Construction IDs | 0 |
| Extra non-construction rows in this authority | 0 |
| Frozen112 mutation | 0 |

## Candidate authority file

| Item | Value |
|---|---|
| Path | `docs/canonical/test-universe/core22_explicit_predicate_authority_v1.json` |
| authority_type | `OWNER_APPROVED_E2E_FIXTURE_FACT` |
| status | `CANDIDATE` |
| Candidate JSON SHA256 | `30ffa5301a851242a29fc9099073353f6447d5a1900d48d482a68ec87d9fe91b` |
| Construction rows | 27 |
| Predicate cells | 27 × 3 = 81 |
| UNSET / JSON `null` | 81 |
| true | 0 |
| false | 0 |
| Non-construction rows | 0 |

Owner Approval, when it happens, binds to this exact candidate file SHA256 **or** to a later vN file. Do not overwrite approved v1 values in place.

## Construction Profile IDs (Frozen112 order)

PF-0028, PF-0029, PF-0030, PF-0031, PF-0032, PF-0033, PF-0034, PF-0035, PF-0036, PF-0052, PF-0053, PF-0054, PF-0055, PF-0056, PF-0057, PF-0094, PF-0095, PF-0096, PF-0097, PF-0098, PF-0099, PF-0100, PF-0101, PF-0102, PF-0103, PF-0104, PF-0105

## Full inventory (raw context + UNSET facts)

| profile_id | boundary_note | contract_amount_eok | construction_type | construction_type_code | order_type | direct_workers | subcon_workers | is_construction | is_relationship_contractor | is_civil_construction |
|---|---|---:|---|---|---|---:|---:|---|---|---|
| PF-0028 |  | 18 | 건축 | BUILDING | 원도급 | 300 | 150 | UNSET | UNSET | UNSET |
| PF-0029 |  | 6 | 건축 | BUILDING | 원도급 | 50 | 25 | UNSET | UNSET | UNSET |
| PF-0030 |  | 18 | 토목 | CIVIL | 원도급 | 300 | 150 | UNSET | UNSET | UNSET |
| PF-0031 |  | 18 | 토목 | CIVIL | 원도급 | 300 | 150 | UNSET | UNSET | UNSET |
| PF-0032 |  | 18 | 공통 | COMMON | 원도급 | 300 | 150 | UNSET | UNSET | UNSET |
| PF-0033 |  | 6 | 건축 | BUILDING | 하도급 | 50 | 25 | UNSET | UNSET | UNSET |
| PF-0034 |  | 1 | 공통 | COMMON | 원도급 | 15 | 7 | UNSET | UNSET | UNSET |
| PF-0035 |  | 6 | 공통 | COMMON | 원도급 | 50 | 25 | UNSET | UNSET | UNSET |
| PF-0036 |  | 18 | 토목 | CIVIL | 원도급 | 300 | 150 | UNSET | UNSET | UNSET |
| PF-0052 | contract_amount_eok=49.0 (공사금액 50억 경계) | 49 | 건축 | BUILDING | 원도급 | 50 | 0 | UNSET | UNSET | UNSET |
| PF-0053 | contract_amount_eok=50.0 (공사금액 50억 경계) | 50 | 건축 | BUILDING | 원도급 | 50 | 0 | UNSET | UNSET | UNSET |
| PF-0054 | contract_amount_eok=51.0 (공사금액 50억 경계) | 51 | 건축 | BUILDING | 원도급 | 50 | 0 | UNSET | UNSET | UNSET |
| PF-0055 | contract_amount_eok=119.0 (120억 경계) | 119 | 건축 | BUILDING | 원도급 | 50 | 0 | UNSET | UNSET | UNSET |
| PF-0056 | contract_amount_eok=120.0 (120억 경계) | 120 | 건축 | BUILDING | 원도급 | 50 | 0 | UNSET | UNSET | UNSET |
| PF-0057 | contract_amount_eok=121.0 (120억 경계) | 121 | 건축 | BUILDING | 원도급 | 50 | 0 | UNSET | UNSET | UNSET |
| PF-0094 |  | 30 | 건축 | BUILDING | 원도급 | 300 | 150 | UNSET | UNSET | UNSET |
| PF-0095 |  | 6 | 토목 | CIVIL | 원도급 | 50 | 25 | UNSET | UNSET | UNSET |
| PF-0096 |  | 30 | 토목 | CIVIL | 원도급 | 300 | 150 | UNSET | UNSET | UNSET |
| PF-0097 |  | 50 | 공통 | COMMON | 원도급 | 300 | 150 | UNSET | UNSET | UNSET |
| PF-0098 |  | 1 | 건축 | BUILDING | 원도급 | 15 | 7 | UNSET | UNSET | UNSET |
| PF-0099 |  | 6 | 공통 | COMMON | 원도급 | 50 | 25 | UNSET | UNSET | UNSET |
| PF-0100 |  | 1 | 공통 | COMMON | 원도급 | 15 | 7 | UNSET | UNSET | UNSET |
| PF-0101 |  | 50 | 토목 | CIVIL | 원도급 | 300 | 150 | UNSET | UNSET | UNSET |
| PF-0102 |  | 18 | 건축 | BUILDING | 원도급 | 50 | 25 | UNSET | UNSET | UNSET |
| PF-0103 |  | 50 | 토목 | CIVIL | 원도급 | 300 | 150 | UNSET | UNSET | UNSET |
| PF-0104 |  | 18 | 공통 | COMMON | 원도급 | 50 | 25 | UNSET | UNSET | UNSET |
| PF-0105 |  | 6 | 건축 | BUILDING | 원도급 | 50 | 25 | UNSET | UNSET | UNSET |

## Owner / GPT review pack

**RAW CONTEXT IS NOT AUTHORITY.**

| Profile | Amount | Raw construction_type_code | Raw order_type | is_construction | relationship | civil |
|---|---:|---|---|---|---|---|
| PF-0028 | 18 | BUILDING | 원도급 | UNSET | UNSET | UNSET |
| PF-0029 | 6 | BUILDING | 원도급 | UNSET | UNSET | UNSET |
| PF-0030 | 18 | CIVIL | 원도급 | UNSET | UNSET | UNSET |
| PF-0031 | 18 | CIVIL | 원도급 | UNSET | UNSET | UNSET |
| PF-0032 | 18 | COMMON | 원도급 | UNSET | UNSET | UNSET |
| PF-0033 | 6 | BUILDING | 하도급 | UNSET | UNSET | UNSET |
| PF-0034 | 1 | COMMON | 원도급 | UNSET | UNSET | UNSET |
| PF-0035 | 6 | COMMON | 원도급 | UNSET | UNSET | UNSET |
| PF-0036 | 18 | CIVIL | 원도급 | UNSET | UNSET | UNSET |
| PF-0052 | 49 | BUILDING | 원도급 | UNSET | UNSET | UNSET |
| PF-0053 | 50 | BUILDING | 원도급 | UNSET | UNSET | UNSET |
| PF-0054 | 51 | BUILDING | 원도급 | UNSET | UNSET | UNSET |
| PF-0055 | 119 | BUILDING | 원도급 | UNSET | UNSET | UNSET |
| PF-0056 | 120 | BUILDING | 원도급 | UNSET | UNSET | UNSET |
| PF-0057 | 121 | BUILDING | 원도급 | UNSET | UNSET | UNSET |
| PF-0094 | 30 | BUILDING | 원도급 | UNSET | UNSET | UNSET |
| PF-0095 | 6 | CIVIL | 원도급 | UNSET | UNSET | UNSET |
| PF-0096 | 30 | CIVIL | 원도급 | UNSET | UNSET | UNSET |
| PF-0097 | 50 | COMMON | 원도급 | UNSET | UNSET | UNSET |
| PF-0098 | 1 | BUILDING | 원도급 | UNSET | UNSET | UNSET |
| PF-0099 | 6 | COMMON | 원도급 | UNSET | UNSET | UNSET |
| PF-0100 | 1 | COMMON | 원도급 | UNSET | UNSET | UNSET |
| PF-0101 | 50 | CIVIL | 원도급 | UNSET | UNSET | UNSET |
| PF-0102 | 18 | BUILDING | 원도급 | UNSET | UNSET | UNSET |
| PF-0103 | 50 | CIVIL | 원도급 | UNSET | UNSET | UNSET |
| PF-0104 | 18 | COMMON | 원도급 | UNSET | UNSET | UNSET |
| PF-0105 | 6 | BUILDING | 원도급 | UNSET | UNSET | UNSET |

## Candidate JSON contract

Each Construction row is:

```json
{
  "profile_id": "PF-....",
  "is_construction": null,
  "is_relationship_contractor": null,
  "is_civil_construction": null
}
```

CANDIDATE allows `null`. Final APPROVED authority requires every cell to be JSON boolean `true` or `false`. `null` = 0 after approval.

Meaning of an approved value is **not** a production rule. Example: Owner setting `is_relationship_contractor=false` means only that this synthetic E2E Profile's test fact is defined as 관계수급인 아님. It does **not** create `order_type=원도급 → false`.

## Authority gap

If any of the 27 Profiles cannot receive an explicit legal fact, do not force `false`. That Profile is a Clean112 blocker (`CORE22_E2E_PREDICATE_FIXTURE_AUTHORITY_GAP`).

## Out of Stage A

- No Stage B bridge / request projection
- No E2E loader tests T8–T18
- No status CANDIDATE → APPROVED
- No quota 523 → 747
- No POST /diagnosis/run-leg
- No RuntimeMatchingEngine
- No Clean112
