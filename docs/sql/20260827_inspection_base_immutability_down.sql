-- WP-INSPECTION-OPS-02 / OBJ-01 INSPECTION RECORD / KNOT-3D
-- BASE LEDGER UPDATE/DELETE PHYSICAL IMMUTABILITY - DOWN
--
-- Removes the immutability triggers first, then the reject function. Nothing else
-- is touched: the pair UNIQUE index, journal/receipt objects, RPCs, and all base
-- data are left exactly as they are.

BEGIN;

DROP TRIGGER IF EXISTS trg_safety_inspections_immutable
    ON public.safety_inspections;

DROP TRIGGER IF EXISTS trg_safety_inspection_results_immutable
    ON public.safety_inspection_results;

DROP FUNCTION IF EXISTS public.fn_reject_inspection_base_mutation();

COMMIT;
