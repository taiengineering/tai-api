---
wo: WO-DOC-OBJ02-C2A-RUNTIME-STATE-CONTRACT-001
contract: CONFIRM_REGRESSION_ANALYSIS
status: SAFE
---

# Confirm Regression Analysis

## Question

Is the version increment in `update_document()` safe with `confirm_document_atomic()`?

## Evidence from `document_confirm_svc.py`

`confirm_document_atomic()` at line 160-163:
```python
version = locked.get("version")
if not isinstance(version, int) or isinstance(version, bool) or version < 1:
    raise ConfirmError(422, "document.version must be int >= 1")
```

**The confirm flow checks `version >= 1` only. It does NOT check for a specific version number.**

The archive stores `document_version = version` from the locked row. No unique constraint on `(runtime_document_id, document_version)` that would cause a conflict if the version has been incremented by multiple PATCHes before confirm.

(Note: `runtime_document_archive` has a `snapshot_hash` column with a uniqueness constraint. The hash depends on the runtime data content and `confirmed_at` timestamp, not solely on the version number.)

## Conclusion

Version increment on each PATCH is SAFE. Incrementing causes `confirm_document_atomic()` to archive a higher version number, which is the correct behavior — the version at archive time reflects how many times the document was edited.

## Implementation

```python
update["version"] = (before.data.get("version") or 1) + 1
```

This is placed in `update_document()` after the merge computation.
