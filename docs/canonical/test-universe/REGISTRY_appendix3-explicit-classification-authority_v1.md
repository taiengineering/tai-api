---
wo: WO-E2E-APPENDIX3-FIXTURE-AUTHORITY-STAGE-B-FREEZE-001
class: records
type: registry
scope: canonical
project: test-universe
title: Frozen112 Appendix3 Explicit Classification Authority v1 (APPROVED)
version: 1
status: approved
owner: taiwang
---

# REGISTRY — Frozen112 Appendix3 Explicit Classification Authority v1 (APPROVED)

```text
Authority Type =
OWNER_APPROVED_E2E_FIXTURE_FACT

Status = APPROVED

Frozen Source =
~/45cm-test/profile_universe_v1.json

Frozen Profile SHA256 =
4818a63ab261c5a36c1432647b6b17e7636641071801d36fd1b85d1361af751b

Frozen Profile Count = 112
Frozen112 Mutation = 0

Approved Candidate =
appendix3_explicit_classification_gpt_candidate_v1.json

Approved Candidate SHA256 =
3d0e99704b423ba00af37cebfcb5e4383b45ac9071eea4aa9c6e55cd4b99e611

Authority =
appendix3_explicit_classification_authority_v1.json

Authority Rows = 75

Production Derivation Rule = NONE

AUTHORITY_JSON_SHA256 =
06b31f56d9d5eb92fcdebc48716494634c5f0ed189ab1304b7b430a6c7d64f46
```

> These are exact synthetic E2E fixture facts, not production mapping rules.

Do not read this authority as:

- KSIC → Appendix3
- sector → Appendix3
- building_use_type → Appendix3
- 아파트 → 항상 37
- 업무빌딩 → 항상 41

Model:

```text
Frozen Profile
+
Approved Companion Authority(profile_id exact)
→ Official DiagnosisRunBody
```

---

## Owner Final Snapshot Approval Binding

```text
OWNER FINAL SNAPSHOT APPROVAL =
APPROVED
```

Approved source:

```text
PR #345

HEAD at approval =
017ff4071d27c40658e861f4b9e27ada993300e4

Candidate SHA256 =
3d0e99704b423ba00af37cebfcb5e4383b45ac9071eea4aa9c6e55cd4b99e611
```

Stage B Authority is projected from that approved snapshot only. No new legal classification was made.

---

## Counts

```text
AUTHORITY_ROWS = 75
UNIQUE_PROFILE_IDS = 75
MANUFACTURING = 46
BUILDING = 29

APPENDIX3_ITEM_NO_PRESENT = 75
NULL_ITEM = 0
NOT_JUDGABLE = 0

ITEM37_ROWS = 3
ITEM37_WITH_EXPLICIT_BOOL = 3
ITEM41 = 9

NON37_ROWS = 72
NON37_SUBTYPE_KEY_PRESENT = 0
```

---

## Owner Fact Resolved 12

```text
OWNER_FACT_RESOLVED = 12
```

### Apartment

```text
PF-0022 PF-0082 PF-0089

OWNER_DEFINED_BUSINESS =
공동주택 관리사업장

appendix3_item_no = 37
is_real_estate_management = true
```

### Office Building

```text
PF-0025 PF-0049 PF-0050 PF-0051
PF-0062 PF-0063 PF-0064 PF-0085 PF-0093

OWNER_DEFINED_BUSINESS =
빌딩/시설 관리사업장

appendix3_item_no = 41
```

> These are exact synthetic E2E fixture facts, not production mapping rules.

---

## Files

| Item | Path |
|---|---|
| Authority | `docs/canonical/test-universe/appendix3_explicit_classification_authority_v1.json` |
| This registry | `docs/canonical/test-universe/REGISTRY_appendix3-explicit-classification-authority_v1.md` |
| Approved candidate (immutable this WO) | `docs/canonical/test-universe/appendix3_explicit_classification_gpt_candidate_v1.json` |

```text
STAGE_B = FROZEN_PENDING_GPT_VERIFY
MERGE = BLOCKED
RUNNER_BRIDGE = NOT_STARTED
MEASUREMENT_GATE = BLOCKED
CRANE = PAUSED
```
