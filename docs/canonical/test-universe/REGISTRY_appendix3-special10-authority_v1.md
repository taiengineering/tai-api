---
wo: WO-E2E-OBS007-SPECIAL10-APPENDIX3-OWNER-APPROVAL-RECEIPT-001
class: records
type: registry
scope: canonical
project: test-universe
title: SPECIAL10 Appendix3 Explicit Classification Authority v1 owner approval receipt
version: 1
status: approved
owner: taiwang
---

# REGISTRY — SPECIAL10 Appendix3 Explicit Classification Authority v1 (APPROVED)

```text
Authority Type =
OWNER_APPROVED_E2E_FIXTURE_FACT

AUTHORITY_CONTENT = FROZEN
OWNER_FINAL_SNAPSHOT_APPROVAL = APPROVED
Status = APPROVED
Coverage = SPECIAL10

Frozen Source =
~/45cm-test/profile_universe_v1.json

Frozen Profile SHA256 =
4818a63ab261c5a36c1432647b6b17e7636641071801d36fd1b85d1361af751b

Frozen Profile Count = 112
Frozen112 Mutation = 0

Approved Candidate =
appendix3_special10_gpt_candidate_v1.json

Approved Candidate SHA256 =
9cb133e345227ab2fdfccf259f3829825fcd903c628a00774d816465561caaf9

Authority =
appendix3_special10_explicit_classification_authority_v1.json

Authority Rows = 10

Production Derivation Rule = NONE
ksic_mapping = false

PRE_APPROVAL_AUTHORITY_JSON_SHA256 =
2c64ae58efa6b53137faf231dfbff2d7b572996087dfe739e9447a354d172893

FINAL_SPECIAL10_AUTHORITY_SHA256 =
c424c56fcbb619fde4cc5f77b5dbcea06b5ac281e488281fba554039e50725db

SEMANTIC_ROWS = SAME
GOVERNANCE_METADATA = OWNER_APPROVAL_RECEIPT
```

> These are exact synthetic E2E fixture facts, not production mapping rules.

Do not read this authority as:

- KSIC → Appendix3
- sector → Appendix3
- facility_type → Appendix3
- 데이터센터 → 항상 36
- 연구소 → 항상 39
- 발전시설 → 항상 26
- 정수장 → 항상 31

Model:

```text
Frozen Profile
+
Approved Companion Authority(profile_id exact)
→ Official DiagnosisRunBody
```

This companion does not replace the approved MFG+BUILDING 75.

```text
APPROVED_75_AUTHORITY =
docs/canonical/test-universe/appendix3_explicit_classification_authority_v1.json

APPROVED_75_SHA256 =
06b31f56d9d5eb92fcdebc48716494634c5f0ed189ab1304b7b430a6c7d64f46

APPROVED_75_AUTHORITY_DELTA = 0
```

Runner still loads only the 75-row file. SPECIAL10 injection remains BLOCKED until GPT verifies this receipt SHA, then a separate Runner REVISE PR.

---

## Owner / GPT Binding

```text
PR #349

STAGE_A_HEAD =
80a14fe633de99dc6a58d1b85ba44e058cca75bb

GPT classification comment =
https://github.com/taiengineering/tai-api/pull/349#issuecomment-5657077068

Owner decision comment =
https://github.com/taiengineering/tai-api/pull/349#issuecomment-5657083864

Owner Final Snapshot Approval comment =
https://github.com/taiengineering/tai-api/pull/349#issuecomment-5657188362

HEAD at Owner Final Snapshot Approval =
aa4613cee4162d5c9cbbb55a6ef6271cb67c3ead

Candidate SHA256 =
9cb133e345227ab2fdfccf259f3829825fcd903c628a00774d816465561caaf9
```

Authority content is projected from that candidate snapshot. No new legal classification was made.

Owner Final Snapshot Approval of this 10-row snapshot is APPROVED. Receipt metadata only was updated; row values were not changed.

---

## Counts

```text
AUTHORITY_ROWS = 10
UNIQUE_PROFILE_IDS = 10

SOURCE_SPECIAL_FACILITY = 10
REQUEST_BUILDING = 10

GPT_CLASSIFIABLE = 7
OWNER_RESOLVED = 3
TOTAL_RESOLVED = 10
NOT_JUDGABLE = 0

APPENDIX3_ITEM_NO_PRESENT = 10
NULL_ITEM = 0

ITEM26 = 3
ITEM31 = 1
ITEM36 = 3
ITEM39 = 3

ITEM37_ROWS = 0
NON37_SUBTYPE_KEY_PRESENT = 0
```

Exact IDs:

```text
PF-0037 PF-0038 PF-0039
PF-0106 PF-0107 PF-0108 PF-0109 PF-0110 PF-0111 PF-0112
```

---

## Owner Fact Resolved 3

```text
OWNER_FACT_RESOLVED = 3
PROFILE_ID = PF-0038 PF-0107 PF-0112

OWNER_DEFINED_BUSINESS =
통신업을 영위하는 데이터센터 사업장

appendix3_item_no = 36
```

This is an Owner-approved synthetic E2E fixture fact for these exact profile IDs only. It is not a general `데이터센터 -> 36호` rule.

---

## GPT Classified 7

```text
PF-0037 PF-0106 PF-0110 → 39 연구개발업
PF-0039 PF-0108 PF-0111 → 26 발전업
PF-0109 → 31 수도, 하수 및 폐기물 처리, 원료 재생업(제23호 및 제24호에 해당하는 사업은 제외한다)
```

---

## Files

| Item | Path |
|---|---|
| Authority | `docs/canonical/test-universe/appendix3_special10_explicit_classification_authority_v1.json` |
| This registry | `docs/canonical/test-universe/REGISTRY_appendix3-special10-authority_v1.md` |
| Approved candidate | `docs/canonical/test-universe/appendix3_special10_gpt_candidate_v1.json` |
| GPT review | `docs/canonical/test-universe/GPT_REVIEW_appendix3-special10_v1.md` |
| Owner decision | `docs/canonical/test-universe/OWNER_DECISION_appendix3-special10_v1.md` |

Stage A review pack is historical and unchanged.

```text
AUTHORITY_CONTENT = FROZEN
OWNER_FINAL_SNAPSHOT_APPROVAL = APPROVED
AUTHORITY_FREEZE_FINAL = PENDING_GPT_VERIFY
RUNNER_REVISE = BLOCKED
HTTP = 0
MEASUREMENT = BLOCKED
MERGE = BLOCKED
CRANE = PAUSED
CRANE_MODIFY = 0
```
