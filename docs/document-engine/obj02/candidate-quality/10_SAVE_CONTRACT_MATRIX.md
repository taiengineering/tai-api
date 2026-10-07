---
title: Save Contract Matrix — update_document() Guardrails
description: Evidence of save contract enforcement for P0 24 documents
type: evidence
wo: WO-DOC-OBJ02-C1-P0-CANDIDATE-QUALITY-AUDIT-001
status: COLLECTED
---

# Save Contract Matrix

## Source

`services/document_engine_svc.py` — `update_document()`, `_validate_field_keys()`, `_validate_evidence_links()`

## create_document() Fail-Close Guard

```python
# document_engine_svc.py:105
if schema.data["status"] != "APPROVED_FOR_RUNTIME_USE":
    raise ValueError(
        f"schema not approved for runtime use: {form_schema_id} "
        f"(status={schema.data['status']})"
    )
```

**Impact on P0 docs**: All 24 P0 schemas have `status=CANDIDATE`. `create_document()` will raise `ValueError` for all 24 P0 docs until schemas are promoted to `APPROVED_FOR_RUNTIME_USE`. This is the structural pre-condition for OBJ02-C2.

## update_document() Field Key Guardrail

```python
# document_engine_svc.py:448
def _validate_field_keys(sb, schema_id: str, data_json: dict):
    allowed = {r["field_key"] for r in (res.data or []) if r.get("field_key")}
    if not allowed:
        return  # field_key 없는 schema는 자유형 입력 허용
    unknown = set(data_json.keys()) - allowed
    if unknown:
        raise ValueError(f"unknown field_keys not in runtime_field: {sorted(unknown)}")
```

All 96 P0 fields have registered `field_key` values. Unknown key injection is blocked.

## update_document() Evidence Link Guardrail

```python
# document_engine_svc.py:468
def _validate_evidence_links(sb, schema_id: str, links: list):
    allowed = {str(r["id"]) for r in (res.data or [])}
    unknown = set(field_ids) - allowed
    if unknown:
        raise ValueError(f"unknown evidence field_ids not in runtime_evidence_field: ...")
```

Only `runtime_evidence_field.id` values registered for the schema are accepted in `evidence_links`. The 12 evidence rows across 13 P0 docs are structurally validated.

## Contract Status per Document

| doc_id | field_count | registered_keys | create_blocked_reason | evidence_linked |
|--------|-------------|-----------------|----------------------|-----------------|
| DOC-OSH-017 | 5 | inspection_done,inspection_datetime,inspector,risk,action | CANDIDATE schema | DATE:1 |
| DOC-OSH-055 | 5 | inspection_done,inspection_datetime,inspector,risk,action | CANDIDATE schema | DATE:1 |
| DOC-CON-007 | 5 | inspection_done,inspection_datetime,inspector,risk,action | CANDIDATE schema | DATE:1 |
| DOC-CON-LAW-014 | 5 | inspection_done,inspection_datetime,inspector,risk,action | CANDIDATE schema | DATE:1 |
| DOC-OSH-007 | 5 | inspection_done,inspection_datetime,inspector,risk,action | CANDIDATE schema | DATE:1 |
| DOC-OSH-038 | 5 | inspection_done,inspection_datetime,inspector,risk,action | CANDIDATE schema | DATE:1 |
| DOC-OSH-046 | 4 | ppe_check,worker,non_compliance,action | CANDIDATE schema | 0 |
| DOC-CON-012 | 4 | work_content,risk_share,participants,signatures | CANDIDATE schema | SIGNATURE:1 |
| DOC-OSH-056 | 4 | work_content,risk_share,participants,signatures | CANDIDATE schema | SIGNATURE:1 |
| DOC-BLD-002 | 5 | target,result,defect,action,inspector_sign | CANDIDATE schema | SIGNATURE:1 |
| DOC-BLD-009 | 3 | electrical_check,inspection_datetime,abnormal | CANDIDATE schema | DATE:1 |
| DOC-BLD-011 | 4 | inspection_date,inspection_content,result,action | CANDIDATE schema | DATE:1 |
| DOC-BLD-016 | 3 | asbestos_status,damage,result | CANDIDATE schema | 0 |
| DOC-CHEM-003 | 4 | facility_check,leak,storage,risk | CANDIDATE schema | 0 |
| DOC-CON-013 | 3 | equipment_check,equipment_name,status | CANDIDATE schema | 0 |
| DOC-CON-014 | 3 | scaffold_check,install_status,collapse_risk | CANDIDATE schema | 0 |
| DOC-CON-026 | 3 | scaffold_check,binding,abnormal | CANDIDATE schema | 0 |
| DOC-CON-032 | 3 | crane_check,brake,wire | CANDIDATE schema | 0 |
| DOC-CON-043 | 3 | guard_check,removed,status | CANDIDATE schema | 0 |
| DOC-FAC-002 | 4 | gas_check,leak,pressure,valve | CANDIDATE schema | 0 |
| DOC-FAC-008 | 4 | inspection_content,result,abnormal,action | CANDIDATE schema | 0 |
| DOC-FAC-013 | 4 | runtime,temperature,pressure,abnormal | CANDIDATE schema | 0 |
| DOC-FAC-016 | 3 | equipment_status,operation_condition,result | CANDIDATE schema | 0 |
| DOC-OSH-059 | 5 | equipment_check,inspection_datetime,equipment_name,abnormal,action | CANDIDATE schema | DATE:1 |

## Summary

- `create_document()`: BLOCKED for all 24 P0 docs — schema status=CANDIDATE (fail-close enforced)
- `update_document()` field guardrail: all 96 field_keys registered — PASS
- `update_document()` evidence guardrail: all 12 evidence UUIDs valid — PASS
- State machine ARCHIVED block: no P0 runtime documents exist yet (pre-approval) — N/A
