---
title: Checklist Materialization Provenance — Gate C1
description: Trace of where 96 PASS_FAIL+APPROVED_BY_HUMAN runtime_checklist_item rows originated
type: evidence
wo: WO-DOC-OBJ02-C1-SUPPLEMENTAL-CONTRACT-VERIFY-002
status: COLLECTED
gate: C1
---

# Checklist Materialization Provenance — Gate C1

## Investigation Scope

Trace the INSERT path that created 96 `runtime_checklist_item` rows with:
- `input_type = PASS_FAIL`
- `status = APPROVED_BY_HUMAN`

for all 24 P0 candidate documents.

## Evidence Collected

### 1. Schema Compiler (`scripts/document_schema_compiler.py` v3.1.0)

`is_checklist()` function at line 195:

```python
CHECKLIST_RE = [
    re.compile(p) for p in [
        r'양호\s*/?\s*불량', r'적합\s*/?\s*부적합', r'정상\s*/?\s*이상',
        r'합격\s*/?\s*불합격', r'여부\s*(확인|점검)', r'이상\s*(없|유)',
        r'[□☐]\s*예\s*[□☐]\s*아니', r'해당\s*/?\s*비해당',
    ]
]
def is_checklist(text):
    return any(p.search(text) for p in CHECKLIST_RE)
```

**FINDING**: The compiler detects checklist items by matching yes/no binary patterns (양호/불량, 적합/부적합, etc.) — NOT by copying field labels 1:1. The compiler does NOT generate `input_type=PASS_FAIL`. The compiler output contains only `checklist_item_candidates` with `raw_text` and `status=CANDIDATE` — no `input_type` assigned.

**FINDING**: The schema compiler writes JSON files only (`form_originals_hwp/compiled/*.json`). It does NOT write to the DB.

### 2. Schema Registry Loader (`scripts/load_document_schema.py`)

Writes to `document_schema_registry` and `document_schema_section` tables.
Does NOT write to `runtime_form_schema`, `runtime_field`, or `runtime_checklist_item`.

### 3. Migration Files (`supabase/migrations/`)

Searched all `.sql` migration files for `runtime_checklist_item` or `PASS_FAIL`. Only match found:

- `docs/sql/20260825_WP_PERSISTENCE_02A_STEP4A_UP.sql` — covers GEN-INSPECT-RESULT-001 only (the one APPROVED_FOR_RUNTIME_USE schema). Does NOT cover any of the 24 P0 docs.
- `docs/sql/20260825_WP_PERSISTENCE_02A_STEP4D_UP.sql` — same scope.

No migration file INSERTs `runtime_checklist_item` rows for the 24 P0 documents.

### 4. Python Service Files

`services/document_engine_svc.py` — reads `runtime_checklist_item`, does NOT insert.
`services/document_engine/catalog_resolver.py` — reads `runtime_checklist_item`, does NOT insert.
`services/document_schema_renderer.py` — pure function, no DB access.

### 5. Git History

No commit found that inserts PASS_FAIL or APPROVED_BY_HUMAN checklist items for the 24 P0 docs. The P0 schemas (runtime_form_schema rows + fields + checklists) were created prior to OBJ02-B1 (commit 271428c8) by a path not tracked in the migration history.

## Conclusion

| Probe | Result |
|-------|--------|
| Compiler produces PASS_FAIL | NOT FOUND |
| Compiler does 1:1 field→checklist copy | NOT FOUND (pattern detection only) |
| Migration INSERTs runtime_checklist_item for P0 docs | NOT FOUND |
| Python script INSERTs PASS_FAIL checklist rows | NOT FOUND |
| Git commit traces P0 checklist INSERT | NOT FOUND |

**ROOT CAUSE STATUS: NOT_FOUND_IN_CODEBASE**

The 96 `input_type=PASS_FAIL` + `status=APPROVED_BY_HUMAN` checklist items for the 24 P0 documents were inserted through a path not traceable via current git history or codebase. The materialization was executed directly against the DB, outside the migration-tracked or script-tracked path, prior to OBJ02-B1.

This means:
1. The 96 PASS_FAIL assignments cannot be attributed to any automated compiler rule
2. The `APPROVED_BY_HUMAN` status on all 96 items implies manual or semi-manual DB promotion was performed
3. Reproducibility: the exact INSERT sequence cannot be replayed from git
