---
wo: WO-E2E-APPENDIX3-FIXTURE-AUTHORITY-OWNER-FACT-RESOLUTION-001
class: records
type: decision
scope: canonical
project: test-universe
title: Owner fact decision for Frozen112 Appendix3 unresolved 12
version: 1
status: recorded
owner: taiwang
---

# OWNER DECISION — Frozen112 Appendix3 Explicit Classification

```text
OWNER_DECISION = EXECUTED
WO = WO-E2E-APPENDIX3-FIXTURE-AUTHORITY-OWNER-FACT-RESOLUTION-001
PR = #345

FROZEN112_MUTATION = 0
PRODUCTION_DERIVATION_RULE = NONE
FINAL_OWNER_SNAPSHOT_APPROVAL = PENDING
STAGE_B = BLOCKED
MERGE = BLOCKED
```

> This is a synthetic E2E fixture fact decision for the exact Frozen112 profile IDs only.
> It is not a production derivation or mapping rule.

Do not read this as:

- 아파트 → 항상 37
- 공동주택 → 항상 37
- 업무빌딩 → 항상 41
- 업무시설 → 항상 41
- 판매시설 → 항상 41

---

## Apartment group

```text
APARTMENT_PROFILE_COUNT = 3
PROFILE_ID = PF-0022 PF-0082 PF-0089
OWNER_DEFINED_BUSINESS = 공동주택 관리사업장
APPENDIX3_ITEM_NO = 37
IS_REAL_ESTATE_MANAGEMENT = true
```

Catalog label for item 37 (existing snapshot, not a new interpretation): `부동산업`.

---

## Office building group

```text
OFFICE_BUILDING_PROFILE_COUNT = 9
PROFILE_ID = PF-0025 PF-0049 PF-0050 PF-0051 PF-0062 PF-0063 PF-0064 PF-0085 PF-0093
OWNER_DEFINED_BUSINESS = 빌딩/시설 관리사업장
APPENDIX3_ITEM_NO = 41
IS_REAL_ESTATE_MANAGEMENT = null
```

Catalog label for item 41 (existing snapshot): `사업시설 관리 및 조경 서비스업`.

Item 41 is not 37, so `is_real_estate_management` stays null. Synthetic false is not written.

---

## Binding

```text
Frozen Profile exact profile_id
+
Owner-defined synthetic business character
→ GPT candidate row
```

Candidate file to verify:

```text
docs/canonical/test-universe/appendix3_explicit_classification_gpt_candidate_v1.json
```

Owner Final Snapshot Approval binds to that file's SHA256 after GPT independent verification. This receipt records the business-character decision only. It does not auto-approve the byte snapshot.

Stage B file `appendix3_explicit_classification_authority_v1.json` is not created here.
