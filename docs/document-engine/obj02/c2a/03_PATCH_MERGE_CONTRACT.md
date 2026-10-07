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

### After (MERGE, CORR-03)
```python
existing_json = before.data.get("runtime_data_json") or {}
merged = {**existing_json, **runtime_data_json}
update["runtime_data_json"] = merged
```

## Rules (CORR-03)

| Incoming value | Effect |
|---------------|--------|
| New key with value | Added to existing JSON |
| Existing key with new value | Overwritten |
| Key not in incoming | Preserved unchanged |
| Key set to `null` / `None` | Preserved with null value (not deleted) |

## Validation Scope

`_validate_runtime_keys()` is called on the **incoming** `runtime_data_json` dict **before** merge, not on the merged result. This validates only the keys being sent in this request.

## Version Increment (CORR-04)

version NOT incremented on PATCH — the version increment line has been removed from `update_document()`. The `version` field is managed by the confirmation flow only.

## Tests

M1–M3 in `tests/test_doc_obj02c2a_runtime_state_contract.py`

M3 updated: null value preserved in stored state (not deleted)
