---
title: AUTO_SOURCE Confirm Boundary Analysis
status: FROZEN
version: 1
governed_by: WO-DOC-AUTO-SRC-01
date: 2026-10-08
---

# AUTO_SOURCE Confirm Boundary Analysis

## 1. Current Confirm Contract (MANUAL path)

```
runtime_document_data (working state)
  → user explicit confirm action
  → runtime_document_archive (immutable snapshot)
```

This path assumes a materialized `runtime_document_data` row exists.

## 2. AUTO_SOURCE Does Not Create runtime_document_data

By design, AUTO_SOURCE documents are listed from source records without inserting:
- runtime_document_data
- generated_document
- PDF or Storage

Therefore the current confirm path CANNOT be applied directly to AUTO_SOURCE logical documents.

## 3. Evidence: source_inspection_id Column

`runtime_document_data` has:
```
source_inspection_id uuid (nullable)
UNIQUE (source_inspection_id, form_schema_id)
```

This column was created to link a MANUAL working-state document back to an inspection source.
It does NOT represent AUTO_SOURCE listing or auto-creation.
Re-activating it as the AUTO confirm trigger is explicitly out of scope until AUTO-SRC-06.

## 4. Confirm Option Analysis (Design Candidates — GPT판정 대기)

### Option A: Lazy Materialization on Explicit Edit/Confirm

```
User opens AUTO document
→ if user edits or explicitly confirms:
  → create runtime_document_data with source_inspection_id
  → confirm → runtime_document_archive
```

Advantage: no upfront cost
Risk: conceptual split between "auto" and "edited manual" state

### Option B: Source-Direct Confirmed Snapshot Path

```
User confirms AUTO document
→ Fetcher fetches current source state
→ Directly creates runtime_document_archive
→ No intermediate runtime_document_data row
```

Advantage: architecturally clean
Risk: confirm contract requires redesign

### Option C: Common Canonical Intermediate State

```
Introduce a new intermediate layer:
  auto_document_confirmed_snapshot
  → separate from runtime_document_data
  → references source_id directly
```

Advantage: avoids runtime_document_data contamination
Risk: new table/contract

## 5. Decision Status

```
AUTO confirm path = DEFERRED to AUTO-SRC-06
No implementation in AUTO-SRC-01
```

Claude does not select an option. GPT판정 대기.

## 6. Governance

- CODE CHANGE = 0
- DB MUTATION = 0
