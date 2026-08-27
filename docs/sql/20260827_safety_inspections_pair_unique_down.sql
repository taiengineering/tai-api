-- WP-INSPECTION-OPS-01 / OBJ-01 INSPECTION RECORD / KNOT-3C2
-- SAFETY_INSPECTIONS SCHEDULE-PAIR UNIQUENESS - DOWN
--
-- Drops ONLY the pair UNIQUE INDEX. No data is touched; no other index, FK,
-- CHECK, or RPC is modified. The existing single-column
-- idx_safety_inspections_assignment is NOT dropped.

BEGIN;

DROP INDEX IF EXISTS public.uq_safety_inspections_assignment_factory;

COMMIT;
