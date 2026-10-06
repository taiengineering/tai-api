---
title: Frontend Edit Contract — tai-admin Document Forms UI
description: Gate H1 — actual input_type→UI component mapping in document-forms/index.vue
type: evidence
wo: WO-DOC-OBJ02-C1-SUPPLEMENTAL-CONTRACT-VERIFY-002
status: COLLECTED
gate: H1
---

# Frontend Edit Contract — Gate H1

## Source

`tai-admin/vue3/src/pages/document-forms/index.vue`

## INPUT_TYPES Constant (line 33)

```typescript
const INPUT_TYPES = new Set(['text', 'number', 'date', 'email', 'tel'])
```

## Component Dispatch Logic (lines 239–266)

```vue
<VTextarea
  v-if="f.type === 'textarea'"
  v-model="list.dynamicFormValues[f.key]"
  ...
/>
<VSelect
  v-else-if="f.type === 'select'"
  v-model="list.dynamicFormValues[f.key]"
  ...
/>
<VTextField
  v-else
  v-model="list.dynamicFormValues[f.key]"
  :type="INPUT_TYPES.has(f.type) ? f.type : 'text'"
  ...
/>
```

## Input Type → Component Mapping

| input_type | Component | HTML type attr | Notes |
|------------|-----------|----------------|-------|
| text | VTextField | text | SUPPORTED |
| number | VTextField | number | SUPPORTED |
| date | VTextField | date | SUPPORTED (browser date picker) |
| email | VTextField | email | SUPPORTED |
| tel | VTextField | tel | SUPPORTED |
| textarea | VTextarea | — | SUPPORTED |
| select | VSelect | — | SUPPORTED |
| signature | VTextField | text | FALLBACK — no signature pad. User types text. |
| PASS_FAIL | VTextField | text | FALLBACK — no boolean/pass-fail component. User types text. |

## Impact on P0 Documents

| Finding | Affected docs | Affected fields |
|---------|---------------|-----------------|
| Signature fields render as text inputs | DOC-BLD-002, DOC-CON-012, DOC-OSH-056 | 3 signature fields |
| PASS_FAIL checklist items have no dedicated UI | all 24 | 96 checklist items (no checklist UI component at all) |

## Critical Gap: No Checklist UI

The document-forms page (`index.vue`) renders `list.dynamicFields.value` — which comes from `normalizeFields()` in `document-formsFormat.ts`. This function reads `fields || form_fields || field_schema || form_json || required_fields` from the API response. There is no path to render `checklists` (runtime_checklist_item rows) in the UI — the checklist data is not passed to any component.

**Result**: Even if signature fields were supported, the 96 checklist items (PASS_FAIL × 96) have no render path in the current frontend. The UI only renders runtime_field rows, not runtime_checklist_item rows.

## Conclusion

| Gate H1 Check | Result |
|---------------|--------|
| signature input type supported | NOT SUPPORTED (falls back to text) |
| PASS_FAIL checklist input type supported | NOT SUPPORTED (no checklist UI component) |
| textarea supported | SUPPORTED |
| date supported | SUPPORTED (browser date picker via VTextField type=date) |
| text supported | SUPPORTED |
