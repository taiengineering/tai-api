---
title: C2-C Scope Reclassification
status: FROZEN
version: 1
governed_by: WO-DOC-ARCHREC-002
date: 2026-10-08
---

# C2-C Scope Reclassification

## 1. Previous (Incorrect) C2-C3 Framing

> "24개 자동문서 Runtime Schema 승인"
> (Approve 24 AUTO_SOURCE Runtime Schemas)

This framing was incorrect because:
- The 24 P0 Runtime Schemas were treated as prerequisites for AUTO_SOURCE activation
- AUTO_SOURCE uses Fetcher → Template pipeline, NOT runtime_form_schema

## 2. Corrected C2-C3 Framing

> "24개 문서의 수동/보완 작성용 Schema 승인 여부 검증"
> (Verify whether the 24 document schemas should be approved for manual/fallback use)

The 24 P0 schemas are:
- `CANDIDATE` status
- Serve ASSISTED_MANUAL / MANUAL_FORM / fallback channels
- NOT activation prerequisites for AUTO_SOURCE

## 3. Runtime Field Key vs Fetcher Key Mismatch (Reason for Separation)

The 24 P0 runtime schemas cannot be directly connected to AUTO_SOURCE because their field keys do not match Fetcher output keys.

### INSP / CHK Runtime Schema Keys
```
inspection_done      ← NO FETCHER COUNTERPART
inspection_datetime  ← fetcher: inspection_date (name mismatch)
inspector            ← fetcher: inspector_name (name mismatch)
risk                 ← fetcher: items / issue_items (structural mismatch)
action               ← fetcher: issue_items[].note (structural mismatch)
```

### TBM Runtime Schema Keys
```
work_content   ← fetcher: work_description (name mismatch)
risk_share     ← fetcher: risk_items (name mismatch)
participants   ← fetcher: attendees (name mismatch)
signatures     ← fetcher: conductor_signature=None, attendees[].signature_url (structural mismatch)
```

### EQUIP Runtime Schema Keys (sample — 14 schema variants)
```
crane_check, brake, wire      ← schema-specific; no direct fetcher equivalent
gas_check, leak, pressure, valve
scaffold_check, binding, abnormal
(etc.)
```

**Conclusion: Runtime schema field keys and Fetcher output keys are architecturally misaligned. Connecting them directly is not supported.**

## 4. Status Summary

| Item | Status |
|------|--------|
| C2-C1 | CLOSED |
| C2-C2 | CLOSED (GPT PASS) — 96 fields normalized, CANDIDATE status |
| C2-C3 | HOLD — schema approval verification for manual/fallback use |
| C2-C4 | HOLD |
| C2-C3 as AUTO_SOURCE prerequisite | REMOVED (this reclassification) |

## 5. AUTO_SOURCE Implementation Path (Separate from C2-C)

AUTO_SOURCE document list connection requires:
1. Business completion hook (on inspection submit / TBM complete)
2. Document discovery query (list documents derived from source records)
3. On-demand render trigger (not schema promotion)

This is a separate WO from C2-C3.

## 6. C2-D Status

C2-D = BLOCKED (dependent on C2-C3 resolution, which is HOLD).
