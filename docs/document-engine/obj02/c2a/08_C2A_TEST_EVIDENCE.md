---
wo: WO-DOC-OBJ02-C2A-RUNTIME-STATE-CONTRACT-001
contract: TEST_EVIDENCE
status: CORR-01~16 APPLIED
---

# C2A Test Evidence

## Test File

`tests/test_doc_obj02c2a_runtime_state_contract.py`

## Test Coverage

### K-tests: Runtime Key Contract

| Test | Description |
|------|-------------|
| K1 | known field_key accepted |
| K2 | known checklist UUID accepted |
| K3 | unknown non-UUID key rejected |
| K4 | mixed field + checklist accepted |
| K5 | PASS/FAIL/NA values accepted |
| K5b | null value accepted for checklist |
| K6 | invalid value "YES" rejected |
| K6b | lowercase "pass" rejected (case-sensitive) |
| K3b | unknown UUID-shaped key rejected |
| K7 | empty schema (0 fields) rejects arbitrary key (no bypass) — CORR-02 |

### M-tests: PATCH Merge Semantics

| Test | Description |
|------|-------------|
| M1 | existing {a:A, b:B} + incoming {a:A2} → {a:A2, b:B} |
| M2 | checklist UUID preserved on non-overlapping field update |
| M3 | incoming {key: null} → key present with null value (not deleted) — CORR-03 |

### R-tests: Render

| Test | Description |
|------|-------------|
| R1 | field value in rendered HTML |
| R2 | checklist UUID with "PASS" in rendered HTML |
| R3 | missing field shows "(미입력)" |
| R5 | same state → same HTML (deterministic) |
| R1b | render_document_html returns HTML with field value |
| Rnf | render raises ValueError for unknown doc_id |

### P-tests: Export Side-Effects

| Test | Description |
|------|-------------|
| P2 | InspectionFetcher NOT called during render |
| P3 | TbmFetcher NOT called during render |
| P4 | no generated_document INSERT during transient render |
| P6 | only HTML and PDF are supported export formats — CORR |

### A-tests: Catalog API

| Test | Description |
|------|-------------|
| A1 | approved schema → can_create=true, schema_id returned |
| A2 | candidate only → candidate schema detail returned, can_create=false — CORR-01 |
| A3 | doc not found → ValueError (→ 404) |
| A1b | approved schema → fields and checklists populated |
| A2b | candidate schema → fields and checklists returned (not empty) — CORR-01 |

### ES-tests: Edit-State Whitelist (CORR-05)

| Test | Description |
|------|-------------|
| ES-1 | DRAFT → edit allowed |
| ES-2 | IN_PROGRESS → edit allowed |
| ES-3 | RETURNED_FOR_EDIT → edit allowed |
| ES-4 | SUBMITTED_FOR_REVIEW → edit denied |
| ES-5 | REVIEW_PENDING → edit denied |
| ES-6 | APPROVED_BY_HUMAN → edit denied |
| ES-7 | REJECTED_BY_HUMAN → edit denied |
| ES-8 | ARCHIVED → edit denied |

### C-tests: Confirmed Reprint Fail-Close (CORR-06)

| Test | Description |
|------|-------------|
| C1 | APPROVED_BY_HUMAN + matching archive → archive rendered_body returned |
| C2 | APPROVED_BY_HUMAN → archive body used regardless of runtime_data_json changes |
| C3 | APPROVED_BY_HUMAN + no archive row → ValueError (fail-close, no fallback) |
| C4 | APPROVED_BY_HUMAN + archive exists but rendered_body is None → ValueError |
| C5 | version mismatch → ValueError |

### AR-tests: Archived Reprint (CORR-15)

| Test | Description |
|------|-------------|
| AR1 | APPROVED_BY_HUMAN → archive body (verify path) |
| AR2 | ARCHIVED → archive body returned (not fresh render) |
| AR3 | ARCHIVED + no archive row → ValueError (fail-close) |
| AR4 | ARCHIVED + archive exists but rendered_body None → ValueError |
| AR5 | ARCHIVED → output is archive body regardless of runtime_data_json changes |

### RT-tests: Router Integration (CORR-14)

| Test | Description |
|------|-------------|
| RT1 | no auth token → render endpoint returns 401 or 403 |
| RT2 | no auth token → generate endpoint returns 401 or 403 |
| RT3 | unsupported export_type → 422 |
| RT4 | PDF export → Content-Type application/pdf |
| RT5 | PDF export → non-empty bytes body |
| RT6 | HTML export → text/html content-type |

### SEC-tests: Tenant Authorization (CORR-14)

| Test | Description |
|------|-------------|
| SEC1 | same company document → render allowed (200) |
| SEC2 | different company document → render denied (404) |
| SEC3 | same company, different factory → render denied (404) |
| SEC4 | same company + own factory → render allowed (200) |
| SEC5 | no auth → PATCH denied (401/403) |
| SEC6 | different company → PATCH denied (404) |
| SEC7 | different company → GET evidence denied (404) |
| SEC8 | different company → PDF generation denied (404) |

## Regression Tests

B1 tests (existing): PASS (no regression)
