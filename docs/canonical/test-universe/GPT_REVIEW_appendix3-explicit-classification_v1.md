---
wo: WO-E2E-APPENDIX3-FIXTURE-AUTHORITY-OWNER-FACT-RESOLUTION-001
class: records
type: review
scope: canonical
project: test-universe
title: Frozen112 Appendix3 GPT synthetic fixture candidate classification
version: 1
status: candidate
owner: taiwang
---

# GPT REVIEW — Frozen112 Appendix3 Explicit Classification Candidates

```text
PR = #345
STAGE_A_HEAD = 6f2d713e13e6a6081021b9f9dab8b3ebc126bbd9
GPT_REVIEW_HEAD = 31eb732e9f98e5bba39e6601f718abb1cc231db8

status = OWNER_FACT_RESOLUTION_COMPLETE_PENDING_FINAL_SNAPSHOT_APPROVAL
authority_type = OWNER_APPROVED_E2E_FIXTURE_FACT_CANDIDATE

Frozen112 mutation = 0
Production derivation rule = NONE
OWNER_FACT_RESOLUTION = COMPLETE
FINAL_OWNER_SNAPSHOT_APPROVAL = PENDING
STAGE_B = BLOCKED
MERGE = BLOCKED

CRANE = PAUSED
MEASUREMENT_GATE = BLOCKED_INPUT_SOURCE
```

This file records GPT synthetic E2E fixture candidate classifications for the 75 gated Frozen112 Profiles. It is not a production KSIC / sector / `building_use_type` mapping rule.

Stage A Review Pack remains historical evidence and is not mutated:

```text
docs/canonical/test-universe/appendix3_explicit_classification_review_pack_v1.json
```

Candidate snapshot:

```text
docs/canonical/test-universe/appendix3_explicit_classification_gpt_candidate_v1.json
```

Approved authority file `appendix3_explicit_classification_authority_v1.json` is not created in this WO.

---

## Counts

Historical before (GPT Review, HEAD `31eb732e`):

```text
GPT_CLASSIFIABLE = 63
NOT_JUDGABLE = 12
ASSIGNED_ITEM37 = 0
ASSIGNED_REAL_ESTATE_MANAGEMENT = 0
```

Current after Owner Fact Resolution:

```text
OWNER_FACT_RESOLUTION = COMPLETE

TOTAL = 75
RESOLVED = 75
NOT_JUDGABLE = 0

GPT_CLASSIFIED = 63
OWNER_FACT_RESOLVED = 12

ITEM37 = 3
ITEM41 = 9

FINAL_OWNER_SNAPSHOT_APPROVAL = PENDING
STAGE_B = BLOCKED
MERGE = BLOCKED
```

---

## Manufacturing 46 — CLASSIFIABLE

Each row is a Profile-ID-exact candidate. Mapping used Review Pack `ksic_name` against the existing Appendix3 catalog labels. It is not installed as production code or a table.

| ksic_name (copied from Review Pack) | appendix3_item_no | n |
|---|---:|---:|
| 식료품 제조업 | 2 | 4 |
| 섬유제품 제조업; 의복 제외 | 3 | 2 |
| 화학 물질 및 화학제품 제조업; 의약품 제외 | 7 | 5 |
| 고무 및 플라스틱제품 제조업 | 9 | 2 |
| 1차 금속 제조업 | 11 | 5 |
| 금속 가공제품 제조업; 기계 및 가구 제외 | 12 | 2 |
| 전자 부품, 컴퓨터, 영상, 음향 및 통신장비 제조업 | 13 | 3 |
| 전기장비 제조업 | 15 | 2 |
| 기타 기계 및 장비 제조업 | 16 | 12 |
| 자동차 및 트레일러 제조업 | 17 | 5 |
| 기타 운송장비 제조업 | 18 | 2 |
| 가구 제조업 | 19 | 2 |
| **Total** | | **46** |

`is_real_estate_management` remains null on all 46.

---

## Building 17 — CLASSIFIABLE

| industry (copied) | appendix3_item_no | catalog label | profiles |
|---|---:|---|---|
| 병원 | 43 | 보건업 | PF-0019 PF-0020 PF-0080 PF-0088 |
| 학교 | 48 | 교육서비스업 중 해당 교육기관 | PF-0021 PF-0081 PF-0091 |
| 물류센터 | 27 | 운수 및 창고업 | PF-0023 PF-0083 PF-0090 |
| 호텔 | 33 | 숙박 및 음식점업 | PF-0024 PF-0084 PF-0092 |
| 판매시설 | 32 | 도매 및 소매업 | PF-0026 PF-0086 |
| 폐기물처리 | 23 | 폐기물 수집, 운반, 처리 및 원료 재생업 | PF-0027 PF-0087 |

`is_real_estate_management` remains null on these 17 GPT-classified building rows. Item 37 is not used here.

---

## NOT_JUDGABLE — 12 (historical)

GPT Review left these 12 unnumbered. Owner then defined synthetic business character for the exact profile IDs. They are no longer NOT_JUDGABLE.

### Apartment 3 — OWNER_FACT_RESOLVED

```text
PF-0022 PF-0082 PF-0089
OWNER_DEFINED_BUSINESS = 공동주택 관리사업장
appendix3_item_no = 37
is_real_estate_management = true
```

### Office building 9 — OWNER_FACT_RESOLVED

```text
PF-0025 PF-0049 PF-0050 PF-0051 PF-0062 PF-0063 PF-0064 PF-0085 PF-0093
OWNER_DEFINED_BUSINESS = 빌딩/시설 관리사업장
appendix3_item_no = 41
is_real_estate_management = null
```

This is not a production rule that 아파트/공동주택 always maps to 37 or 업무빌딩 always maps to 41.

---

## Next (not this WO)

```text
GPT independent verification of this 75/75 candidate snapshot
  → Owner Final Snapshot Approval of exact SHA256
  → Stage B approved companion authority freeze
  → Runner bridge
  → Measurement Gate
  → crane CHG resume
```

Do not create Stage B authority. Do not merge. Do not resume crane.
