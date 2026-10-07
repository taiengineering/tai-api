---
title: ARCH-REC-02 Final Evidence
status: CLOSED / GPT PASS / 100%
version: 3
governed_by: WO-DOC-ARCHREC-002
date: 2026-10-08
---

# WO-DOC-ARCHREC-002 RESULT (CORR-001 APPLIED)

## A. GIT

```
main (base) = eba8fc90
branch = docs/doc-archrec-canonical-channels
before HEAD = 8b442d5e (initial commit)
after HEAD  = 509c8d52
changed files (CORR-001):
  docs/document-engine/architecture-reconciliation/01_CANONICAL_CHANNEL_CONTRACT.md
  docs/document-engine/architecture-reconciliation/03_RUNTIME_FETCHER_KEY_MATRIX.csv
  docs/document-engine/architecture-reconciliation/05_MANUAL_CHANNEL_REVIEW_QUEUE.csv
  docs/document-engine/architecture-reconciliation/06_TASK_GUIDE_SEARCH_CONTRACT.md
  docs/document-engine/architecture-reconciliation/07_C2C_SCOPE_RECLASSIFICATION.md
  docs/document-engine/architecture-reconciliation/08_ARCHREC_FINAL_EVIDENCE.md
```

---

## B. AUTO SOURCE

| Attribute | Value |
|-----------|-------|
| mapped existing fetcher doc count | 24 |
| INSP | 4 documents, fetcher=inspection, status=EXISTING |
| CHK | 2 documents, fetcher=inspection, status=EXISTING |
| EQUIP | 15 documents, fetcher=inspection, status=EXISTING |
| PPE | 1 document, fetcher=inspection, status=EXISTING |
| TBM | 2 documents, fetcher=tbm, status=EXISTING |
| auto render existing | YES (Fetcher→Template pipeline functional) |
| auto document list connection | NO (MISSING) |
| auto completion hook | NO (MISSING) |

InspectionFetcher output keys (22):
```
company_name, company_logo, factory_name, factory_address, manager_name,
doc_title, inspection_date, inspector_name, status_code, inspection_status,
result_summary, asset_name, asset_code, asset_location, items, total_count,
normal_count, issue_count, abnormal_count, hold_count, issue_items, has_issue
```

TbmFetcher output keys (13):
```
factory_name, work_date, work_location, conductor_name, work_description,
attendee_count, meeting_time, risk_items, safety_items, attendees,
conductor_signature, manager_name
```

---

## C. MANUAL

| Attribute | Value |
|-----------|-------|
| document_forms total | 260 |
| mapped (document_type_mapping EXISTS) | 30 |
| unmapped | 230 |
| AUTO_SOURCE_CANDIDATE (fetcher_status=EXISTING) | 24 |
| mapped but NOT AUTO_SOURCE (NO_SOURCE + NEW_NEEDED) | 6 |
| **MANUAL_REVIEW_REQUIRED total** | **236 (= 230 + 6)** |
| has_legal_form=true | 138 |
| has_legal_form=false | 122 |
| is_external_writer=true | 25 |
| is_external_writer=false | 235 |

Manual review breakdown:
```
unmapped                                    = 230
mapped but current fetcher unavailable      =   6
  APPT  (NO_SOURCE)  2 — DOC-OSH-062, DOC-OSH-063
  CONLOG (NEW_NEEDED) 1 — DOC-CON-006
  EDU   (NEW_NEEDED)  3 — DOC-OSH-006, DOC-OSH-037, DOC-SERA-006
─────────────────────────────────────────────────────────────────
MANUAL_REVIEW_REQUIRED total                = 236
```

Grade distribution (all 260):
```
A: 30
B: 75
C: 72
D: 37
X: 46
```

Grade distribution (236 manual review):
```
A:  6
B: 75
C: 72
D: 37
X: 46
```

NOTE: tai_auto != generation_mode
```
A grade documents with fetcher EXISTING = 24
A grade tai_auto = false (ALL 30 A-grade documents have tai_auto=false)
tai_auto reflects delivery/processing automation, NOT document generation mode
```

---

## D. RUNTIME

| Attribute | Value |
|-----------|-------|
| P0 runtime schemas total | 24 |
| P0 runtime fields total | 96 |
| runtime matrix rows (03_RUNTIME_FETCHER_KEY_MATRIX.csv) | 96 |
| fetcher exact key matches | 1 (EQUIP DOC-BLD-011 inspection_date↔inspection_date) |
| review_required matches | 95 — GPT semantic mapping 대기 |

Runtime matrix count breakdown:
```
CHK   2 schemas × 5 fields = 10
EQUIP 1 schema  × 4 fields =  4  (DOC-FAC-013 일상)
EQUIP 14 schemas             50  (정기 variants)
INSP  4 schemas × 5 fields = 20
PPE   1 schema  × 4 fields =  4
TBM   2 schemas × 4 fields =  8
─────────────────────────────────
Total                        96
```

Runtime schema field keys do NOT align with Fetcher output keys.
Connecting runtime schemas directly to AUTO_SOURCE is not supported without a mapping layer.

---

## E. TASK GUIDE

| Attribute | Value |
|-----------|-------|
| safe_help_content type allowed values | PAGE_GUIDE, TASK_GUIDE, FAQ |
| current TASK_GUIDE rows | 0 |
| Shared Search domain_name | KNOWLEDGE |
| Shared Search object_type | KNOWLEDGE |
| canonical enqueue | enqueue_search_index_sync called on upsert/status change |
| incremental job | shared_search_incremental ACTIVE |
| visibility | PUBLIC + SAAS + PAID |

NOT confirmed by this contract:
```
Google/Naver automatic SEO indexing — separate public route/crawl/sitemap verification needed
document_forms ↔ TASK_GUIDE automatic linking — no implementation; separate WO needed
```

---

## F. C2-C2

| Attribute | Value |
|-----------|-------|
| C2-C2 implementation | CLOSED / GPT PASS |
| production migration applied | NO |
| Production runtime schema status | CANDIDATE (24 schemas) |
| Production runtime field status | CANDIDATE (96 fields) |
| Production checklist status | APPROVED_BY_HUMAN (96 items) |
| Production evidence field status | CANDIDATE (12 fields) |

Production child state = pre-apply. "96 fields normalized" refers to implementation verification only, not production state.

---

## G. MUTATION

| Type | Count |
|------|-------|
| DB write | 0 |
| Storage write | 0 |
| Production migration | 0 |
| Code change | 0 |
| Schema promotion | 0 |

---

## H. FINAL

| Item | Status |
|------|--------|
| ARCH-REC-01 | CLOSED / GPT PASS |
| ARCH-REC-02 CORR-001 | PASSED |
| ARCH-REC-02 | CLOSED / GPT PASS / 100% |
| C2-C2 implementation | CLOSED / GPT PASS |
| C2-C2 production apply | NO |
| C2-C3 | BLOCKED (manual/fallback schema approval pending) |
| C2-C4 | BLOCKED |
| AUTO_SOURCE connection | MISSING — separate WO needed |
| TASK_GUIDE content | MISSING — separate WO needed |
| 236 manual channel classification | MANUAL_REVIEW_REQUIRED — GPT판정 대기 |
