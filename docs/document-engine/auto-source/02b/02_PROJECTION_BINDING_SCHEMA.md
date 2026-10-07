---
title: AUTO-SRC-02B Projection Binding Schema
status: ACTIVE
version: 1
governed_by: WO-DOC-AUTO-SRC-02B
date: 2026-10-08
---

# Projection Binding Schema

## 1. inspection_set_projection_binding

```
Table: public.inspection_set_projection_binding
Migration: 20261007182044_doc_auto_src_02b_projection_selector.sql

Columns:
  id                  uuid        PK DEFAULT gen_random_uuid()
  inspection_set_id   uuid        NOT NULL FK → inspection_sets(id) ON DELETE RESTRICT
  projection_type     text        NOT NULL  (INSP/CHK/PPE/EQUIP/ASBESTOS/GUARD/SCAFFOLD)
  projection_detail   text        NULL      (EQUIP detail: ELEC/MACHINE/BOILER/etc.; NULL for INSP/CHK/PPE)
  binding_source      text        NOT NULL  (e.g., LEGAL_ENGINE / MANUAL / SYSTEM)
  is_active           boolean     NOT NULL DEFAULT true
  created_at          timestamptz NOT NULL DEFAULT now()
  updated_at          timestamptz NOT NULL DEFAULT now()

Indexes:
  PK: id
  UNIQUE: (inspection_set_id, projection_type, COALESCE(projection_detail, '-'))
  INDEX: inspection_set_id

RLS: ENABLE ROW LEVEL SECURITY
  REVOKE ALL FROM anon, authenticated, service_role
  GRANT SELECT/INSERT/UPDATE/DELETE TO service_role
```

---

## 2. document_equipment_projection_map

```
Table: public.document_equipment_projection_map
Migration: 20261007182044_doc_auto_src_02b_projection_selector.sql

Columns:
  equipment_type_code text        PK  (numeric 001-040; no uppercase aliases stored)
  projection_detail   text        NULL (ELEC/MACHINE/BOILER/REFRIG/CRANE/ELEV/GAS/HAZMAT/FIRE; NULL = UNRESOLVED)
  mapping_status      text        NOT NULL (RESOLVED / UNRESOLVED)
  mapping_basis       text        NOT NULL (WO reference)
  note                text        NULL (Korean canonical name from system_codes)
  is_active           boolean     NOT NULL DEFAULT true
  created_at          timestamptz NOT NULL DEFAULT now()
  updated_at          timestamptz NOT NULL DEFAULT now()

Seed: 40 rows (v1; frozen per WO-DOC-AUTO-SRC-02B)
  35 RESOLVED + 5 UNRESOLVED (015/035/036/037/040)

RLS: ENABLE ROW LEVEL SECURITY
  REVOKE ALL FROM anon, authenticated, service_role
  GRANT SELECT/INSERT/UPDATE/DELETE TO service_role
```

---

## 3. GAP-02C Resolution Status

```
GAP-02C (canonical equipment code → AUTO EQUIP doc_detail):
  Status: RESOLVED by this migration (40-row seed)
  Authority: WO-DOC-AUTO-SRC-02B v1 mapping
  Remaining UNRESOLVED: 015/035/036/037/040 (no canonical AUTO doc_detail)
  Next upgrade: extend mapping via new WO + migration delta (ON CONFLICT DO NOTHING pattern)
```
