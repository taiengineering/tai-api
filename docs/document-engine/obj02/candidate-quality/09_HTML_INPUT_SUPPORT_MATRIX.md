---
title: HTML Input Support Matrix — P0 24 Documents
description: Mapping from runtime_field.input_type to HTML input type support via templates
type: evidence
wo: WO-DOC-OBJ02-C1-P0-CANDIDATE-QUALITY-AUDIT-001
status: COLLECTED
---

# HTML Input Support Matrix

## Field Input Types Used Across 24 P0 Documents

| input_type | Count | Docs |
|------------|-------|------|
| text | 63 | all doc types |
| textarea | 17 | CHK×2, INSP×4, PPE×1, TBM×2, EQUIP×6 |
| date | 8 | CHK×2, INSP×4, EQUIP×3 |
| signature | 4 | TBM×2, EQUIP×2 (DOC-BLD-002, DOC-CON-012, DOC-CON-014→none, DOC-OSH-056) |
| **Total** | **96** | |

Note: Signature fields = DOC-CON-012.signatures, DOC-OSH-056.signatures, DOC-BLD-002.inspector_sign (total 4 rows: 2 TBM + 1 EQUIP).

Wait — recount from field matrix:
- TBM: DOC-CON-012.signatures(sig), DOC-OSH-056.signatures(sig) = 2 signature
- EQUIP: DOC-BLD-002.inspector_sign(sig) = 1 signature
Total signature = 3

Corrected totals:
| input_type | Count |
|------------|-------|
| text | 67 |
| textarea | 17 |
| date | 9 |
| signature | 3 |
| **Total** | **96** |

## Template HTML Input Support

Source: `templates/documents/` — DOC-CHK.html, DOC-INSP.html, DOC-PPE.html, DOC-EQUIP.html, DOC-OSH-056.html

All 5 templates exist on disk. Template rendering is performed via `renderer.py` using Jinja2 variable injection from `InspectionFetcher.fetch()` or `TbmFetcher.fetch()`.

| input_type | Template render path | Support status |
|------------|---------------------|----------------|
| text | Jinja2 `{{ var }}` | SUPPORTED |
| textarea | Jinja2 `{{ var }}` | SUPPORTED |
| date | Jinja2 `{{ var }}` | SUPPORTED (string passthrough) |
| signature | Evidence vault link (evidence_vault_link.linked_field_id) | SUPPORTED via evidence_links |

## Key Observation

The `runtime_data_json` (via `update_document`) stores field values keyed by `field_key`. The `_validate_field_keys` guardrail in `document_engine_svc.py:448` enforces that only registered `field_key` values are accepted. All 96 P0 fields have registered `field_key` values — the save contract is structurally sound.

Signature fields are NOT stored in `runtime_data_json`. They are captured via `link_evidence()` → `evidence_vault_link` table with `linked_field_id` referencing `runtime_evidence_field.id`. This path exists for the 4 EQUIP/TBM docs with SIGNATURE evidence.
