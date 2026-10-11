# REF-01 Observed Fields Apply — WO-049
Date: 2026-10-08
WO: WO-REF01-OBSERVED-FIELDS-CONTROLLED-APPLY-049
Investigator: Claude Code (apply + evidence)
Basis: REF01-SOURCE-SECTION-ERRATA-048.md, REF01-SOURCE-SECTION-MANIFEST-047.md, GPT WO-048 independent review (CONDITIONAL PASS, 4 approved / 2 HOLD)

---

## S0 BASELINE — PRE-MUTATION STATE

SQL: `SELECT research_id, source_title, source_document_access, source_document_checksum, jsonb_array_length(COALESCE(observed_fields,'[]'::jsonb)) AS field_count FROM public.ref_form_research_items WHERE research_id IN ('REF-C006','REF-C007','REF-C008','REF-C009','REF-C010','REF-C011') ORDER BY research_id`

| research_id | source_title | source_document_access | checksum | field_count |
|---|---|---|---|---|
| REF-C006 | 위험성평가표(빈도강도법) | ARTICLE_LOGIN_REQUIRED | NULL | 0 |
| REF-C007 | 안전보건예산 편성 서식 | ARTICLE_LOGIN_REQUIRED | NULL | 0 |
| REF-C008 | 안전보건 전문이력 평가 기준 및 평가표 | ARTICLE_LOGIN_REQUIRED | NULL | 0 |
| REF-C009 | 안전보건 전문인력 등 배치표 및 담당업무 | ARTICLE_LOGIN_REQUIRED | NULL | 0 |
| REF-C010 | 사고 발생 대응 시나리오(처리 흐름도) | ARTICLE_LOGIN_REQUIRED | NULL | 0 |
| REF-C011 | 도급·용역·위탁 업체 안전보건 수준 평가 | NOT_CHECKED | NULL | 0 |

Total rows: 189. observed_nonempty baseline: 10.
All 4 precondition rows confirmed observed_fields=[] before transaction.

---

## S1 TRANSACTION EXECUTION

Method: PostgreSQL DO $$ ... $$ block with row-level FOR UPDATE locks.
Preconditions enforced per ID:
1. `observed_fields = []` (empty) — RAISE EXCEPTION if not
2. `source_title` exact match — RAISE EXCEPTION if mismatch
3. `GET DIAGNOSTICS v_count = ROW_COUNT` after each UPDATE — RAISE EXCEPTION if not exactly 1

Transaction result: NO EXCEPTION. All 4 precondition checks PASSED. All 4 GET DIAGNOSTICS = 1.

RAISE NOTICE: `WO-049 COMPLETE: 4 rows updated (REF-C007/C008/C009/C011)`

Fields updated per approved ID:
- `observed_fields`: JSONB array (see S2 for exact arrays)
- `source_document_checksum`: `e94d8d8a271c148973111ff0c74b4d67ba2f9884aff59e87301e261b5794aefe`
- `source_document_access`: `OWNER_UPLOADED_HWP_TEXT_PARSED_PARTIAL`
- `source_observation_note`: APPEND `| WO-049 2026-10-08: ...` (existing note preserved)

Fields NOT updated (confirmed):
- `source_title` (unchanged for all — including C008 typo "이력" retained per WO-049)
- `proposed_fields`, `legal_required_fields`, `legal_sot_reference`
- `rights`, `license`, `review_status`, `owner_approval_status`, `publication_status`
- `canonical_candidate_id`, `relation_group`
- `source_url` (REF-C011 NULL preserved)
- REF-C006 and REF-C010: NOT TOUCHED (HOLD)

---

## S2 MUTATION RECEIPT — EXACT APPLIED ARRAYS

### REF-C007 — 21 fields (HWP-07, Para 1233–1290)
HWP heading: `안전보건 예산 편성항목 예시`
SoT title: `안전보건예산 편성 서식` (CLOSE_MATCH)

| # | label | label_type | para_ref | component |
|---|---|---|---|---|
| 1 | 구분 | COLUMN_HEADER | 1236 | null |
| 2 | 연도(예: 2021, 2022) | COLUMN_HEADER | 1237-1238 | null |
| 3 | 인력 및 시설분야 | CATEGORY_LABEL | 1239 | null |
| 4 | 위험시설 정비 및 개보수 | ROW_LABEL | 1240 | null |
| 5 | 안전검사 실시 | ROW_LABEL | 1243 | null |
| 6 | 안전시설 신규 설치 및 투자 | ROW_LABEL | 1246 | null |
| 7 | 안전보건조직 노무관리 | ROW_LABEL | 1249 | null |
| 8 | 안전분야 | CATEGORY_LABEL | 1252 | null |
| 9 | 안전인력 육성 및 교육 | ROW_LABEL | 1253 | null |
| 10 | 안전보건 진단 및 컨설팅 | ROW_LABEL | 1256 | null |
| 11 | 위험성평가 실시 | ROW_LABEL | 1259 | null |
| 12 | 안전보호구 구입 | ROW_LABEL | 1262 | null |
| 13 | 보건분야 | CATEGORY_LABEL | 1265 | null |
| 14 | 작업환경측정 실시 | ROW_LABEL | 1266 | null |
| 15 | 특수건강검진 실시 | ROW_LABEL | 1269 | null |
| 16 | 근골격계질환 예방 | ROW_LABEL | 1272 | null |
| 17 | 휴게·위생시설 관리 | ROW_LABEL | 1275 | null |
| 18 | 기타 | CATEGORY_LABEL | 1278 | null |
| 19 | 협력사 안전관리 역량 지원 | ROW_LABEL | 1279 | null |
| 20 | 안전보건 캠페인 추진 | ROW_LABEL | 1284 | null |
| 21 | 예비(예비비) | ROW_LABEL | 1287-1288 | null |

verification: NATIVE_PARAGRAPH_ONLY (all). requiredness: UNVERIFIED (all).

---

### REF-C008 — 10 fields (HWP-08, Para 1291–1404)
HWP heading: `안전보건 전문인력 평가 기준 및 평가표 예시`
SoT title: `안전보건 전문이력 평가 기준 및 평가표` (PROBABLE_MATCH + TYPO NOTE: "이력"→"인력" not corrected per WO-049)
Two components stored: A_평가기준, B_평가표

| # | label | label_type | para_ref | component |
|---|---|---|---|---|
| 1 | 양호 | EVALUATION_CRITERION | 1294 | A_평가기준 |
| 2 | 보통 | EVALUATION_CRITERION | 1296 | A_평가기준 |
| 3 | 미흡 | EVALUATION_CRITERION | 1298 | A_평가기준 |
| 4 | 직책 | COLUMN_HEADER | 1303 | B_평가표 |
| 5 | 성명 | COLUMN_HEADER | 1304 | B_평가표 |
| 6 | 담당업무 | COLUMN_HEADER | 1305 | B_평가표 |
| 7 | 평가 (미흡/보통/양호) | COLUMN_HEADER | 1306-1309 | B_평가표 |
| 8 | 안전보건관리 책임자 | ROW_LABEL | 1310-1312 | B_평가표 |
| 9 | 관리감독자 | ROW_LABEL | 1354-1355 | B_평가표 |
| 10 | 안전보건총괄책임자 | ROW_LABEL | 1382-1383 | B_평가표 |

verification: NATIVE_PARAGRAPH_ONLY (all). requiredness: UNVERIFIED (all).

---

### REF-C009 — 8 fields (HWP-09, Para 1405–1461)
HWP heading: `안전보건 전문인력 등 배치표 및 담당업무`
SoT title: `안전보건 전문인력 등 배치표 및 담당업무` (EXACT_MATCH)

| # | label | label_type | para_ref | component |
|---|---|---|---|---|
| 1 | 직책 | COLUMN_HEADER | 1407 | null |
| 2 | 성명 | COLUMN_HEADER | 1408 | null |
| 3 | 담당업무 | COLUMN_HEADER | 1409 | null |
| 4 | 비고 | COLUMN_HEADER | 1410 | null |
| 5 | 안전관리자 (산안법 제17조) | ROW_LABEL | 1411-1412 | null |
| 6 | 보건관리자 (산안법 제18조) | ROW_LABEL | 1425-1426 | null |
| 7 | 안전보건관리담당자 (산안법 제19조) | ROW_LABEL | 1443-1445 | null |
| 8 | 산업보건의 (산안법 제22조) | ROW_LABEL | 1454-1456 | null |

verification: NATIVE_PARAGRAPH_ONLY (all). requiredness: UNVERIFIED (all).

---

### REF-C011 — 17 fields (HWP-11, Para 1597–1645)
HWP heading: `도급·용역·위탁 업체 안전보건 수준 평가 예시`
SoT title: `도급·용역·위탁 업체 안전보건 수준 평가` (MATCH — 예시 = example annotation)
source_url: NULL (kept — download URL not independently verified)
Erratum basis: WO-048 (HWP-11 UNRESOLVED → MATCH)

| # | label | label_type | para_ref | component |
|---|---|---|---|---|
| 1 | 평가항목 | COLUMN_HEADER | 1599 | null |
| 2 | 평가기준 | COLUMN_HEADER | 1600 | null |
| 3 | 배점 | COLUMN_HEADER | 1601 | null |
| 4 | 점수 | COLUMN_HEADER | 1602 | null |
| 5 | I. 안전보건관리체계 | CATEGORY_LABEL | 1603 | null |
| 6 | 도급·용역·위탁받는 자의 안전보건관리 체계 구축 수준 | ROW_LABEL | 1604 | null |
| 7 | 리더십 | SUB_CATEGORY | 1607 | null |
| 8 | 경영방침, 인력·시설·장비 등 자원 배정의 적정성 등 | ROW_LABEL | 1608 | null |
| 9 | 근로자 참여 | SUB_CATEGORY | 1611 | null |
| 10 | 종사자 의견수렴 절차 및 이행 적정성 | ROW_LABEL | 1612 | null |
| 11 | 위험요인 파악 및 제거·대체·통제 | SUB_CATEGORY | 1615 | null |
| 12 | 비상조치계획 | SUB_CATEGORY | 1619 | null |
| 13 | II. 도급·용역·위탁 안전보건 관리계획 | CATEGORY_LABEL | 1623 | null |
| 14 | 위험요인 파악 및 제거·대체·통제 (도급) | SUB_CATEGORY | 1627-1628 | null |
| 15 | 자원 배정(시설·장비) | SUB_CATEGORY | 1631-1633 | null |
| 16 | 자원 배정(인력) | SUB_CATEGORY | 1636-1638 | null |
| 17 | 비상조치계획 (도급) | SUB_CATEGORY | 1641-1643 | null |

verification: NATIVE_PARAGRAPH_ONLY (all). requiredness: UNVERIFIED (all).
Note: S3 summary in WO-048 listed count=16 — actual applied array is 17 (detail section is ground truth; S3 had a counting error).

---

## S3 POST-MUTATION CHECK

SQL: `SELECT research_id, source_document_access, source_document_checksum, jsonb_array_length(observed_fields) AS field_count, owner_approval_status, publication_status, review_status, source_url FROM public.ref_form_research_items WHERE research_id IN ('REF-C006','REF-C007','REF-C008','REF-C009','REF-C010','REF-C011') ORDER BY research_id`

| research_id | source_document_access | checksum | field_count | owner_approval | publication | review | source_url |
|---|---|---|---|---|---|---|---|
| REF-C006 | ARTICLE_LOGIN_REQUIRED | NULL | 0 | NOT_REQUESTED | NOT_READY | IN_PROGRESS | KOSHA |
| REF-C007 | OWNER_UPLOADED_HWP_TEXT_PARSED_PARTIAL | e94d8d8a... | 21 | NOT_REQUESTED | NOT_READY | IN_PROGRESS | KOSHA |
| REF-C008 | OWNER_UPLOADED_HWP_TEXT_PARSED_PARTIAL | e94d8d8a... | 10 | NOT_REQUESTED | NOT_READY | IN_PROGRESS | KOSHA |
| REF-C009 | OWNER_UPLOADED_HWP_TEXT_PARSED_PARTIAL | e94d8d8a... | 8 | NOT_REQUESTED | NOT_READY | IN_PROGRESS | KOSHA |
| REF-C010 | ARTICLE_LOGIN_REQUIRED | NULL | 0 | NOT_REQUESTED | NOT_READY | IN_PROGRESS | KOSHA |
| REF-C011 | OWNER_UPLOADED_HWP_TEXT_PARSED_PARTIAL | e94d8d8a... | 17 | NOT_REQUESTED | NOT_READY | IN_PROGRESS | NULL |

Total count check:
```
total_rows: 189 ✓ (unchanged)
observed_nonempty_count: 14 ✓ (was 10 + 4 new = 14)
```

Gate verification:
| Gate | Expected | Observed | Result |
|---|---|---|---|
| Total rows | 189 | 189 | PASS |
| observed_nonempty | 14 | 14 | PASS |
| REF-C007 field_count | 21 | 21 | PASS |
| REF-C008 field_count | 10 | 10 | PASS |
| REF-C009 field_count | 8 | 8 | PASS |
| REF-C011 field_count | 17 | 17 | PASS |
| REF-C006 field_count | 0 (HOLD) | 0 | PASS |
| REF-C010 field_count | 0 (HOLD) | 0 | PASS |
| REF-C006 checksum | NULL (HOLD) | NULL | PASS |
| REF-C010 checksum | NULL (HOLD) | NULL | PASS |
| REF-C011 source_url | NULL | NULL | PASS |
| All owner_approval_status | NOT_REQUESTED | NOT_REQUESTED | PASS |
| All publication_status | NOT_READY | NOT_READY | PASS |
| All review_status | IN_PROGRESS | IN_PROGRESS | PASS |

ALL GATES PASS.

---

## S4 REDACTIONS AND UNRESOLVED

| Item | Status | Note |
|---|---|---|
| REF-C006 | HOLD | Title divergence: KRAS vs 빈도강도법 not resolved. No observed_fields written. |
| REF-C010 | HOLD | HWP-10a image-only (협착사고 흐름도). HWP-10b/10c 3-scenario ambiguity unresolved. No observed_fields written. |
| REF-C008 source_title typo | UNRESOLVED | SoT "이력" vs HWP "인력". source_title NOT corrected per WO-049 instruction. Requires separate GPT authorization. |
| REF-C011 S3 count discrepancy | NOTED | WO-048 S3 summary listed 16 fields; detail section has 17. Applied count = 17 (detail is ground truth). S3 summary had a counting error. |
| source_url for C007/C008/C009 | PRESERVED | KOSHA URL retained from prior research; download still requires login. source_document_access updated to OWNER_UPLOADED_HWP_TEXT_PARSED_PARTIAL to reflect actual access method (owner-supplied HWP). |

---

## S5 STOP — GPT INDEPENDENT VERIFY

WO-049 DB mutations: 4 rows.
Evidence file: docs/reference-forms/evidence/REF01-OBSERVED-FIELDS-APPLY-049.md (this file).
Branch: docs/tai-reference-forms-charter-obj-20261008.

FINAL: EXECUTED. STOP for GPT independent verification.
DO_NOT_EXPAND = TRUE
