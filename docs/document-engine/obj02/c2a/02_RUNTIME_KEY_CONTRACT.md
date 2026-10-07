---
wo: WO-DOC-OBJ02-C2A-RUNTIME-STATE-CONTRACT-001
contract: CONTRACT_B_KEY_VALIDATION
status: IMPLEMENTED
---

# Runtime Key Contract (CONTRACT B)

## Function: `_validate_runtime_keys(sb, schema_id, data_json)`

Replaces `_validate_field_keys()` as the guardrail for `update_document()`.

## Allowed Key Types

| Key Type | Detection | Validation |
|----------|-----------|------------|
| `runtime_field.field_key` | Non-UUID string | Must exist in `runtime_field` for this `schema_id` |
| `runtime_checklist_item.id` | 36-char UUID format | Must exist in `runtime_checklist_item` for this `schema_id` |

## Checklist Value Enum

When the key is a registered checklist UUID, the value must be one of:
- `"PASS"` — item passed
- `"FAIL"` — item failed
- `"NA"` — not applicable
- `null` / `None` — no answer recorded

Any other value (including lowercase variants like `"pass"`) raises `ValueError`.

## Unknown Key Handling

- Non-UUID key not in `runtime_field` → `ValueError`
- UUID-shaped key not in `runtime_checklist_item` → `ValueError`
- Unknown UUID-like keys are never silently ignored

## Empty Schema Guard (CORR-02)

If `runtime_field` returns no rows (schema has 0 fields), non-UUID keys are still rejected. The empty allowed set causes `key not in allowed_field_keys` to be True for any key. This enforces strict validation — no bypass for empty schemas.

## Tests

K1–K7 in `tests/test_doc_obj02c2a_runtime_state_contract.py`

K7: schema with 0 fields → arbitrary non-UUID key still rejected (no bypass)
