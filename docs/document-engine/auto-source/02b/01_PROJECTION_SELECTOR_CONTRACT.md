---
title: AUTO-SRC-02B Projection Selector Contract
status: ACTIVE
version: 1
governed_by: WO-DOC-AUTO-SRC-02B
date: 2026-10-08
---

# AUTO-SRC-02B: Projection Selector Contract

## 1. Purpose

Define the deterministic rule set that maps an inspection_set record to one or
more projection_type values in the AUTO_SOURCE channel.

---

## 2. Rule Priority

Three rules evaluated in strict order. First matching rule wins.

```
RULE 1 (EXPLICIT BINDING)
  Source: inspection_set_projection_binding child table
  Condition: one or more active rows for this inspection_set_id
  Result: return all rows verbatim (multi-projection supported)
  Note: ASBESTOS/GUARD/SCAFFOLD must use this path; NOT via RULE 2

RULE 2 (ASSET-DERIVED EQUIP)
  Source: safety_inspections.asset_id + equipment_assets.equipment_type_code
          resolved via document_equipment_projection_map
  Condition: asset_id IS NOT NULL
  Sub-condition A: code → RESOLVED detail → yield EQUIP(detail)
  Sub-condition B: code → UNRESOLVED or unknown → fail-closed (empty list)
  Note: canonicalizer applied before lookup (CRANE→021, etc.)

RULE 3 (GENERIC INSP FALLBACK)
  Condition: no binding (RULE 1 empty), no asset_id (RULE 2 skipped), is_completed=True
  Result: yield INSP(detail=None)
  Note: applies to all standard INSP/CHK/PPE with no explicit specialization
```

---

## 3. Fail-Closed Policy

```
Legacy rows (396 existing inspection_sets):
  asset_id = 0/396 → RULE 2 never fires
  explicit_bindings = 0 (table empty for legacy rows) → RULE 1 never fires
  is_completed = varies → RULE 3 fires only for COMPLETED rows
  → Legacy INSP fallback: visible only if completed

UNRESOLVED equipment code (015/035/036/037/040):
  RULE 2 returns empty list → inspection invisible in AUTO library
  NOT backfilled by RULE 3 (asset_id is present → RULE 2 path taken)

Not-completed inspection:
  RULE 3 condition (is_completed=True) fails → empty list
```

---

## 4. Multi-Projection

```
Same inspection_set_id CAN have multiple projection_type rows in
inspection_set_projection_binding (e.g., CHK + PPE on the same record).
Unique constraint: (inspection_set_id, projection_type, COALESCE(projection_detail, '-'))
→ prevents duplicate (type, detail) pairs; allows CHK + PPE coexistence.
```

---

## 5. Implementation

```
Module: services/document_engine/auto_source_projection_selector.py
  Function: select_projections(explicit_bindings, asset_id, equipment_type_code, is_completed)
  Returns: List[ProjectionDecision]
  Dataclass: ProjectionDecision(projection_type, projection_detail, rule)

Module: services/document_engine/equipment_projection_resolver.py
  Function: resolve_equipment_detail(equipment_type_code)
  Returns: Optional[str] — EQUIP doc_detail or None
  Static map: _STATIC_MAP (40 entries; 35 RESOLVED + 5 UNRESOLVED)
```

---

## 6. DB Tables

```
inspection_set_projection_binding:
  - PK: id (uuid)
  - FK: inspection_set_id → inspection_sets(id) ON DELETE RESTRICT
  - Unique: (inspection_set_id, projection_type, COALESCE(projection_detail, '-'))
  - RLS: service_role only

document_equipment_projection_map:
  - PK: equipment_type_code (text)
  - Seed: 40 rows per WO-DOC-AUTO-SRC-02B v1 (35 RESOLVED + 5 UNRESOLVED)
  - RLS: service_role only
```

---

## 7. LLM/Name Inference

```
LLM/name inference used = NO
Projection determined by explicit rules only:
  - RULE 1: explicit DB binding
  - RULE 2: canonical code → map lookup (no name matching)
  - RULE 3: structural condition (is_completed, no asset)
```
