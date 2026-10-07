---
title: AUTO-SRC-02B Asset ID Carry Contract
status: ACTIVE
version: 1
governed_by: WO-DOC-AUTO-SRC-02B
date: 2026-10-08
---

# Asset ID Carry Contract

## 1. Problem (from AUTO-SRC-02A)

```
safety_inspections.asset_id = 0/5 populated (AUTO-SRC-02A evidence)
work_schedules.asset_id     = 0/68 populated
inspection_sets.equipment_set_id = 0/396 populated

fn_create_worker_inspection_record Step 8 INSERT (v1.0):
  INSERT INTO public.safety_inspections
      (id, assignment_id, inspector_id, inspection_date, status_code, factory_id)
  VALUES (..., p_factory_id)
  — asset_id NOT included → always NULL after record creation
```

---

## 2. Fix (v1.1)

```
Step 8 INSERT (v1.1):
  INSERT INTO public.safety_inspections
      (id, assignment_id, inspector_id, inspection_date, status_code, factory_id, asset_id)
  VALUES (..., p_factory_id, v_sched.asset_id)

Source authority: v_sched (work_schedules row, locked FOR UPDATE in Step 3)
  = server-side authority; client cannot spoof asset_id
  = v_sched.asset_id carries NULL if the schedule is not asset-specific (LEGAL inspection)
  = carries the actual UUID if the schedule is asset-specific (EQUIP inspection)
```

---

## 3. Scope Boundary

```
fn_create_worker_inspection_record: CHANGED (asset_id added to INSERT)
fn_start_safe_inspection_record: NOT CHANGED (IN_PROGRESS header; asset carry not needed)
_build_schedules_for_repair(): NOT CHANGED (repair schedules; asset_id not forced on LEGAL schedules)

work_schedules.asset_id writer: NOT CHANGED in this WO
  — law_engine materializer for LEGAL schedules does not set asset_id (by design)
  — asset-specific schedules set asset_id at creation time (existing path)
```

---

## 4. Effect on RULE 2

```
Before v1.1:
  safety_inspections.asset_id = always NULL → RULE 2 never fires for new inspections
  EQUIP projection never deterministic

After v1.1:
  safety_inspections.asset_id = v_sched.asset_id
  For asset-specific work_schedules: asset_id populated → RULE 2 can fire
  For LEGAL work_schedules (no asset): asset_id = NULL → RULE 3 fires (INSP fallback)
```

---

## 5. Legacy Rows

```
Existing 5 safety_inspections: asset_id = 0/5 → LEGACY_UNRESOLVED (unchanged)
Backfill: NOT applied in this WO
Legacy rows: visible only via RULE 3 INSP fallback (if completed)
```
