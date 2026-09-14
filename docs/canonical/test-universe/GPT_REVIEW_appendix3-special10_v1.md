---
wo: WO-E2E-OBS007-SPECIAL10-APPENDIX3-AUTHORITY-FREEZE-001
class: records
type: review
scope: canonical
project: test-universe
title: SPECIAL10 Appendix3 GPT synthetic fixture candidate classification
version: 1
status: approved
owner: taiwang
---

# GPT REVIEW — SPECIAL10 Appendix3 Explicit Classification Candidates

```text
PR = #349
STAGE_A_HEAD = 80a14fe633de99dc6a58d1b85ba44e058cca75bb
GPT_CLASSIFICATION_COMMENT =
https://github.com/taiengineering/tai-api/pull/349#issuecomment-5657077068

status = APPROVED_FOR_AUTHORITY_FREEZE
authority_type = OWNER_APPROVED_E2E_FIXTURE_FACT_CANDIDATE

Frozen112 mutation = 0
Production derivation rule = NONE
ksic_mapping = false
```

This file records GPT synthetic E2E fixture candidate classifications for the 7 CLASSIFIABLE SPECIAL10 profiles. It is not a production KSIC / sector / `facility_type` mapping rule.

Stage A Review Pack remains historical evidence and is not mutated:

```text
docs/canonical/test-universe/appendix3_special10_review_pack_v1.json
```

Candidate snapshot:

```text
docs/canonical/test-universe/appendix3_special10_gpt_candidate_v1.json
SHA256 = 9cb133e345227ab2fdfccf259f3829825fcd903c628a00774d816465561caaf9
```

---

## Counts

```text
GPT_CLASSIFIABLE = 7
GPT_NOT_JUDGABLE = 3
OWNER_RESOLVED = 3
TOTAL_RESOLVED = 10/10
NOT_JUDGABLE = 0
```

`is_real_estate_management` remains absent/null. None of the 10 rows is item 37.

---

## CLASSIFIABLE = 7

Catalog labels below are copied from the read-only Appendix3 1..49 snapshot. They are not a mapping rule.

| profile_id | raw industry | appendix3_item_no | catalog label |
|---|---|---:|---|
| PF-0037 | 연구소 | 39 | 연구개발업 |
| PF-0106 | 연구소 | 39 | 연구개발업 |
| PF-0110 | 연구소 | 39 | 연구개발업 |
| PF-0039 | 발전시설 | 26 | 발전업 |
| PF-0108 | 발전시설 | 26 | 발전업 |
| PF-0111 | 발전시설 | 26 | 발전업 |
| PF-0109 | 정수장 | 31 | 수도, 하수 및 폐기물 처리, 원료 재생업(제23호 및 제24호에 해당하는 사업은 제외한다) |

---

## NOT_JUDGABLE = 3 (historical)

GPT left these unnumbered. Owner then defined a synthetic business character for the exact profile IDs. They are no longer NOT_JUDGABLE.

```text
PF-0038 PF-0107 PF-0112
raw industry = 데이터센터
```

See `OWNER_DECISION_appendix3-special10_v1.md`.

---

## Governance

```text
AUTHORITY_FREEZE = THIS_WO
RUNNER_REVISE = BLOCKED
HTTP = 0
MEASUREMENT = BLOCKED
MERGE = BLOCKED
CRANE_MODIFY = 0
CRANE = PAUSED
```
