-- WP-INSPECTION-OPS-01 / OBJ-01 INSPECTION RECORD / KNOT-3C2
-- SAFETY_INSPECTIONS SCHEDULE-PAIR UNIQUENESS - UP
--
-- Installs the pair UNIQUE INDEX that enforces the locked schedule cardinality
-- 0..1 at the schema level:
--
--   CREATE UNIQUE INDEX uq_safety_inspections_assignment_factory
--   ON public.safety_inspections (assignment_id, factory_id)
--   WHERE assignment_id IS NOT NULL;
--
-- This is a PARTIAL UNIQUE INDEX, not a UNIQUE CONSTRAINT: PostgreSQL cannot
-- express "UNIQUE (assignment_id, factory_id) WHERE assignment_id IS NOT NULL"
-- as a table constraint, so the partial unique index is the canonical form.
--
-- The predicate is assignment_id IS NOT NULL (the locked "linked inspection"
-- subset). The DB pair CHECK already forces (assignment_id NULL <-> factory_id
-- NULL), so factory_id IS NOT NULL is implied and is not repeated in the
-- predicate. Standalone rows (assignment_id NULL AND factory_id NULL) remain
-- allowed and are intentionally outside the index.
--
-- This migration is fail-closed: it LOCKs the table briefly (SHARE MODE, blocks
-- writers only) and RAISEs before creating the index if any duplicate pair,
-- broken pair, or a same-named pre-existing index is found. It does NOT hide a
-- pre-existing (possibly wrong) index behind IF NOT EXISTS.
--
-- Out of scope (0 changes): base data INSERT/UPDATE/DELETE, backfill, NOT NULL
-- changes on assignment_id/factory_id, and DROP of the existing single-column
-- idx_safety_inspections_assignment.

BEGIN;

-- Block writers for the (tiny) duration of precheck + index build so no writer
-- can slip a duplicate pair in between the precheck and the index creation.
LOCK TABLE public.safety_inspections IN SHARE MODE;

DO $precheck$
DECLARE
    v_dup    integer;
    v_broken integer;
    v_idx    integer;
BEGIN
    -- PRECHECK 1 - linked pair duplicate groups must be zero
    SELECT count(*) INTO v_dup FROM (
        SELECT assignment_id, factory_id
        FROM public.safety_inspections
        WHERE assignment_id IS NOT NULL
        GROUP BY assignment_id, factory_id
        HAVING count(*) > 1
    ) d;
    IF v_dup > 0 THEN
        RAISE EXCEPTION 'KNOT-3C2 PRECHECK P1 FAILED: % linked (assignment_id, factory_id) duplicate group(s)', v_dup;
    END IF;

    -- PRECHECK 2 - broken assignment/factory pairs must be zero
    SELECT count(*) INTO v_broken
    FROM public.safety_inspections
    WHERE (assignment_id IS NULL AND factory_id IS NOT NULL)
       OR (assignment_id IS NOT NULL AND factory_id IS NULL);
    IF v_broken > 0 THEN
        RAISE EXCEPTION 'KNOT-3C2 PRECHECK P2 FAILED: % broken assignment/factory pair row(s)', v_broken;
    END IF;

    -- PRECHECK 3 - the target index name must not already exist (do NOT silently
    -- accept a same-named index that may carry a wrong definition)
    SELECT count(*) INTO v_idx
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relkind = 'i'
      AND n.nspname = 'public'
      AND c.relname = 'uq_safety_inspections_assignment_factory';
    IF v_idx > 0 THEN
        RAISE EXCEPTION 'KNOT-3C2 PRECHECK P3 FAILED: index public.uq_safety_inspections_assignment_factory already exists';
    END IF;
END
$precheck$;

-- No IF NOT EXISTS: pre-existence is handled explicitly by PRECHECK 3 above.
CREATE UNIQUE INDEX uq_safety_inspections_assignment_factory
ON public.safety_inspections (assignment_id, factory_id)
WHERE assignment_id IS NOT NULL;

COMMIT;
