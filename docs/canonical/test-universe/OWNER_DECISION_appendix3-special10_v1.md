---
wo: WO-E2E-OBS007-SPECIAL10-APPENDIX3-AUTHORITY-FREEZE-001
class: records
type: decision
scope: canonical
project: test-universe
title: Owner fact decision for SPECIAL10 Appendix3 data-center fixtures
version: 1
status: approved
owner: taiwang
---

# OWNER DECISION — SPECIAL10 Appendix3 Data-Center Fixture Fact

```text
OWNER_DECISION = APPROVED
WO = WO-E2E-OBS007-SPECIAL10-APPENDIX3-AUTHORITY-FREEZE-001
PR = #349
OWNER_DECISION_COMMENT =
https://github.com/taiengineering/tai-api/pull/349#issuecomment-5657083864

FROZEN112_MUTATION = 0
PRODUCTION_DERIVATION_RULE = NONE
ksic_mapping = false
```

> This is a synthetic E2E fixture fact decision for the exact Frozen112 profile IDs only.
> It is not a production derivation or mapping rule.

Do not read this as:

- 데이터센터 → 항상 36
- facility_type → 36
- 특수정보시설 → 36
- sector → Appendix3
- KSIC → Appendix3

---

## Data-center group

```text
DATA_CENTER_PROFILE_COUNT = 3
PROFILE_ID = PF-0038 PF-0107 PF-0112
OWNER_DEFINED_BUSINESS = 통신업을 영위하는 데이터센터 사업장
APPENDIX3_ITEM_NO = 36
IS_REAL_ESTATE_MANAGEMENT = null
```

Owner fact (verbatim):

> 데이터센터를 “통신업을 영위하는 데이터센터 사업장”으로 정의

Catalog label for item 36 (existing snapshot, not a new interpretation): `우편 및 통신업`.

Item 36 is not 37, so `is_real_estate_management` stays absent on the authority row. Synthetic false is not written.

---

## Binding

```text
Frozen Profile exact profile_id
+
Owner-defined synthetic business character
→ GPT candidate row
→ Stage B companion authority row
```

Candidate file:

```text
docs/canonical/test-universe/appendix3_special10_gpt_candidate_v1.json
SHA256 = 9cb133e345227ab2fdfccf259f3829825fcd903c628a00774d816465561caaf9
```

This Owner fact applies only to PF-0038, PF-0107, and PF-0112.
