---
title: ARCH-REC-02 Final Evidence
status: COMPLETE — GPT VERIFY REQUIRED
version: 1
governed_by: WO-DOC-ARCHREC-002
date: 2026-10-08
---

# WO-DOC-ARCHREC-002 RESULT

## A. GIT

```
main (base) = pulled current (3 commits behind origin at start, now synced)
branch = docs/doc-archrec-canonical-channels
HEAD = [pending commit]
changed files:
  docs/document-engine/architecture-reconciliation/01_CANONICAL_CHANNEL_CONTRACT.md
  docs/document-engine/architecture-reconciliation/02_AUTO_SOURCE_CURRENT_MATRIX.csv
  docs/document-engine/architecture-reconciliation/03_RUNTIME_FETCHER_KEY_MATRIX.csv
  docs/document-engine/architecture-reconciliation/04_DOCUMENT_260_CHANNEL_FACTS.csv
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
| has_legal_form=true | 138 |
| has_legal_form=false | 122 |
| is_external_writer=true | 25 |
| is_external_writer=false | 235 |

Grade distribution:
```
A: 30
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
| P0 runtime fields total | 96 (post C2-C2 correction, status=CANDIDATE) |
| fetcher exact key matches | 1 (EQUIP inspection_date↔inspection_date) |
| review_required matches | all remaining — GPT semantic mapping 대기 |

Runtime schema field keys do NOT align with Fetcher output keys.
Connecting runtime schemas directly to AUTO_SOURCE is not supported without a mapping layer.

---

## E. TASK GUIDE

| Attribute | Value |
|-----------|-------|
| safe_help_content type allowed values | PAGE_GUIDE, TASK_GUIDE, FAQ |
| current TASK_GUIDE rows | 0 |
| Shared Search domain | KNOWLEDGE_CENTER |
| visibility | PUBLIC + SAAS + PAID |

---

## F. MUTATION

| Type | Count |
|------|-------|
| DB write | 0 |
| Storage write | 0 |
| Production migration | 0 |
| Code change | 0 |
| Schema promotion | 0 |

---

## G. FINAL

| Item | Status |
|------|--------|
| ARCH-REC-01 | CLOSED / GPT PASS |
| ARCH-REC-02 | COMPLETE — GPT VERIFY REQUIRED |
| C2-C3 | BLOCKED (not prerequisite for AUTO_SOURCE; manual/fallback schema approval pending) |
| C2-C4 | BLOCKED |
| AUTO_SOURCE connection | MISSING — separate WO needed |
| TASK_GUIDE content | MISSING — separate WO needed |
| 230 manual channel classification | MANUAL_REVIEW_REQUIRED — GPT판정 대기 |
