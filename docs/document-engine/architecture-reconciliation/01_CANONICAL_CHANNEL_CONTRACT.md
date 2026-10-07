---
title: Canonical Document Channel Contract
status: FROZEN
version: 1
governed_by: WO-DOC-ARCHREC-002
date: 2026-10-08
---

# Canonical Document Channel Contract

## 1. Five Operational Document Channels

| Channel | Code | Definition |
|---------|------|------------|
| Auto Source | AUTO_SOURCE | Business execution is the document source. No separate copy needed. |
| Assisted Manual | ASSISTED_MANUAL | Company/factory/equipment auto-filled; user completes the rest. |
| Manual Form | MANUAL_FORM | User writes entirely. |
| Official Original | OFFICIAL_ORIGINAL | Government/public agency provides the canonical HWP/PDF original. |
| External Only | EXTERNAL_ONLY | External agency or specialist writes. TAI handles guidance and storage only. |

Classification of specific documents into channels 2–5 is REVIEW_REQUIRED (GPT판정 대기).
Claude Code does not assign channels beyond AUTO_SOURCE_CANDIDATE.

---

## 2. Separate Knowledge Channel

| Channel | Code | Definition |
|---------|------|------------|
| Task Guide | TASK_GUIDE | Safety-manager handbook content explaining how to write/manage documents. Not a document itself. |

`document_forms` = operational document/form catalog.
`safe_help_content TASK_GUIDE` = safety-manager handbook / how-to content.
These two must not be merged.

---

## 3. AUTO_SOURCE Contract

### 3.1 Core Principle

> Business execution itself is the document source.

When a user completes an inspection or TBM:
- The source record exists.
- The document exists as an on-demand projection.
- No separate `runtime_document_data` row is required at completion time.
- No PDF file is auto-generated at completion time.
- No Storage upload is triggered at completion time.

### 3.2 Render Path

```
Source Record (safety_inspections / tbm_meetings)
  → Fetcher (InspectionFetcher / TbmFetcher)
  → Template (DOC-INSP.html / DOC-OSH-056.html / ...)
  → On-demand HTML / PDF
```

### 3.3 Current AUTO_SOURCE Doc Types

| doc_type | Documents | Fetcher | Status |
|----------|-----------|---------|--------|
| INSP | 4 | inspection | EXISTING |
| CHK | 2 | inspection | EXISTING |
| EQUIP | 15 | inspection | EXISTING |
| PPE | 1 | inspection | EXISTING |
| TBM | 2 | tbm | EXISTING |

### 3.4 AUTO_SOURCE Candidate Rule (factual, no semantic inference)

```
AUTO_SOURCE_CANDIDATE =
  document_type_mapping EXISTS
  AND document_type_registry.fetcher_status = EXISTING
```

Remaining 230 documents without mapping = MANUAL_REVIEW_REQUIRED.

---

## 4. Auto Connection Gap (Current Fact)

```
AUTO DATA   = EXISTS   (safety_inspections, tbm_meetings populated on business completion)
AUTO RENDER = EXISTS   (Fetcher + Template pipeline functional)
AUTO DOCUMENT DISCOVERY / LIST = MISSING
```

Current flow after inspection complete:
```
safety_inspections.status updated
→ [NO DOCUMENT LIBRARY ENTRY CREATED]
```

Current flow after TBM complete:
```
tbm_meetings.status_code = COMPLETED
→ [NO DOCUMENT LIBRARY ENTRY CREATED]
```

Current document generation requires explicit caller:
```
POST /documents/{doc_type}/generate
  body: { "inspection_id": "...", "params": {...} }
```

Connecting business completion → document library is the next AUTO_SOURCE implementation target.

---

## 5. MANUAL / WORKING Document Engine

`runtime_form_schema`, `runtime_field`, `runtime_checklist_item`, `runtime_evidence_field`, `runtime_document_data` serve the ASSISTED_MANUAL and MANUAL_FORM channels.

These tables are **not** the SoT for AUTO_SOURCE business data.
AUTO_SOURCE does not copy its source data into runtime_document_data.

---

## 6. Confirmed State (Shared)

`runtime_document_archive` = immutable confirmed snapshot after explicit user confirmation.
All channels (AUTO_SOURCE and MANUAL) share the same canonical snapshot contract.

---

## 7. Architecture Diagram

```
                TAI Safe 업무
                     │
         ┌───────────┴───────────┐
         │                       │
    AUTO SOURCE                MANUAL
         │                       │
safety_inspections         document_forms
tbm_meetings               Runtime Schema
         │                       │
   Source Record          사용자 직접작성
         │                       │
         └───────────┬───────────┘
                     ↓
              Document View
                     ↓
              필요 시 Confirm
                     ↓
          Immutable Snapshot (runtime_document_archive)
                     ↓
               HTML / PDF


별도 Public Knowledge Layer

document_forms
      ↓
TASK_GUIDE (safe_help_content)
      ↓
Shared Search (KNOWLEDGE_CENTER domain)
      ↓
Google / Naver / 안전정보검색
      ↓
SaaS 유입
```

---

## 8. Governance

- CODE CHANGE = 0 (this document only)
- DB MUTATION = 0
- Channel assignments beyond AUTO_SOURCE_CANDIDATE = GPT 판정 대기
- C2-C3 schema promotion = BLOCKED (not a prerequisite for AUTO_SOURCE connection)
