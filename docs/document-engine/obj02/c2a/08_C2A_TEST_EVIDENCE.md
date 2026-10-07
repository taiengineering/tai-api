---
wo: WO-DOC-OBJ02-C2A-RUNTIME-STATE-CONTRACT-001
contract: TEST_EVIDENCE
status: 26/26 PASS
---

# C2A Test Evidence

## Test File

`tests/test_doc_obj02c2a_runtime_state_contract.py`

## Results

```
26 passed in 0.08s
```

## Test Coverage

### K-tests: Runtime Key Contract

| Test | Description | Result |
|------|-------------|--------|
| K1 | known field_key accepted | PASS |
| K2 | known checklist UUID accepted | PASS |
| K3 | unknown non-UUID key rejected | PASS |
| K4 | mixed field + checklist accepted | PASS |
| K5 | PASS/FAIL/NA values accepted | PASS |
| K5b | null value accepted for checklist | PASS |
| K6 | invalid value "YES" rejected | PASS |
| K6b | lowercase "pass" rejected (case-sensitive) | PASS |
| K3b | unknown UUID-shaped key rejected | PASS |

### M-tests: PATCH Merge Semantics

| Test | Description | Result |
|------|-------------|--------|
| M1 | existing {a:A, b:B} + incoming {a:A2} → {a:A2, b:B} | PASS |
| M2 | checklist UUID preserved on non-overlapping field update | PASS |
| M3 | incoming {key: null} → key removed | PASS |

### R-tests: Render

| Test | Description | Result |
|------|-------------|--------|
| R1 | field value in rendered HTML | PASS |
| R2 | checklist UUID with "PASS" in rendered HTML | PASS |
| R3 | missing field shows "(미입력)" | PASS |
| R5 | same state → same HTML (deterministic) | PASS |
| R1b | render_document_html returns HTML with field value | PASS |
| Rnf | render raises ValueError for unknown doc_id | PASS |

### P-tests: Export Side-Effects

| Test | Description | Result |
|------|-------------|--------|
| P2 | InspectionFetcher NOT called during render | PASS |
| P3 | TbmFetcher NOT called during render | PASS |
| P4 | no generated_document INSERT during transient render | PASS |

### A-tests: Catalog API

| Test | Description | Result |
|------|-------------|--------|
| A1 | approved schema → can_create=true, schema_id returned | PASS |
| A2 | candidate only → can_create=false | PASS |
| A3 | doc not found → ValueError (→ 404) | PASS |
| A1b | approved schema → fields and checklists populated | PASS |
| A2b | candidate schema → fields and checklists empty | PASS |

## Regression Tests

B1 tests (existing): 26/26 PASS (no regression)
