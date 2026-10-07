---
wo: WO-DOC-OBJ02-C2A-RUNTIME-STATE-CONTRACT-001
contract: CONTRACT_B_PATCH_MERGE
status: IMPLEMENTED
---

# PATCH Merge Contract (CONTRACT B)

## Behavior

`update_document()` changed from FULL_REPLACE to MERGE semantics.

### Before (FULL_REPLACE)
```python
update["runtime_data_json"] = runtime_data_json  # destroys untouched keys
```

### After (MERGE)
```python
existing_json = before.data.get("runtime_data_json") or {}
merged = {**existing_json, **runtime_data_json}
merged = {k: v for k, v in merged.items() if v is not None}
update["runtime_data_json"] = merged
```

## Rules

| Incoming value | Effect |
|---------------|--------|
| New key with value | Added to existing JSON |
| Existing key with new value | Overwritten |
| Key not in incoming | Preserved unchanged |
| Key set to `null` / `None` | Removed from stored JSON |

## Validation Scope

`_validate_runtime_keys()` is called on the **incoming** `runtime_data_json` dict **before** merge, not on the merged result. This validates only the keys being sent in this request.

## Version Increment

Each successful PATCH increments `version` by 1:
```python
update["version"] = (before.data.get("version") or 1) + 1
```

This is safe because `confirm_document_atomic()` checks `version >= 1` but does not check for a specific version number. See `06_CONFIRM_REGRESSION.md` for the safety analysis.

## Tests

M1–M3 in `tests/test_doc_obj02c2a_runtime_state_contract.py`
