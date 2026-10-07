---
title: AUTO-SRC-02B Selector Test Matrix
status: ACTIVE
version: 1
governed_by: WO-DOC-AUTO-SRC-02B
date: 2026-10-08
---

# Selector Test Matrix

## Test File

```
tests/test_auto_src_02b_projection_selector.py
```

## F: Selector Rule Tests (27 total)

| ID | Rule | Input | Expected |
|----|------|-------|----------|
| F1 | RULE 1 | 1 explicit binding (CHK) | CHK / RULE_1_EXPLICIT |
| F2 | RULE 1 | 2 bindings (CHK + PPE) | [CHK, PPE] multi-projection |
| F3 | RULE 1 | binding with detail | detail preserved |
| F4 | RULE 1 wins | binding present + asset_id present | RULE_1_EXPLICIT (not RULE_2) |
| F5 | RULE 2 | no binding, asset_id=UUID, code=021 | EQUIP(CRANE) / RULE_2_ASSET_EQUIP |
| F6 | RULE 2 alias | code=CRANE (alias) | EQUIP(CRANE) via canonicalizer |
| F7 | RULE 2 unresolved | code=040 | [] fail-closed |
| F8 | RULE 2 unknown | code=UNKNOWN_CODE | [] fail-closed |
| F9 | RULE 2 null code | asset_id=UUID, code=None | [] fail-closed |
| F10 | RULE 3 | no binding, no asset, completed=True | INSP fallback |
| F11 | RULE 3 skip | no binding, no asset, completed=False | [] |
| F12 | RULE 2 lowercase | code=crane (lowercase) | [] fail-closed |

## M: Equipment Mapping Tests

| ID | Test |
|----|------|
| M1 | static map has exactly 40 rows |
| M2 | 35 RESOLVED + 5 UNRESOLVED(None) |
| M3 | UNRESOLVED codes = {015, 035, 036, 037, 040} |
| M4 | 001-010 all map to ELEC |
| M5 | 023/024/038 map to MACHINE |
| M6 | PRESSURE_VESSEL alias → MACHINE |
| M7 | code 040 → None (UNRESOLVED) |
| M8 | None input → None |

## A: Asset ID Carry Tests (SQL static)

| ID | Test |
|----|------|
| A1 | migration INSERT contains asset_id column |
| A2 | migration uses v_sched.asset_id as value |
| A3 | safety_inspections INSERT column list contains asset_id |

## R: fn_create_worker_inspection_record Regression Tests (SQL static)

| ID | Test |
|----|------|
| R1 | SECURITY DEFINER preserved |
| R2 | All 8 input parameters still present |
| R3 | SUBMISSION_ID_REUSE_CONFLICT guard preserved |
| R4 | WORK_SCHEDULE_NOT_EXECUTABLE guard preserved |

## Result

```
27/27 PASS (local run 2026-10-08)
DB write = 0
Code change = services/document_engine only (new files; no existing file modified)
Migration = 1 (20261007182044; production apply NOT executed in this WO)
```
