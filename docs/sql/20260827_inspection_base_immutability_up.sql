-- WP-INSPECTION-OPS-02 / OBJ-01 INSPECTION RECORD / KNOT-3D
-- BASE LEDGER UPDATE/DELETE PHYSICAL IMMUTABILITY - UP
--
-- Makes the OBJ-01 base ledger physically append-only: once a row is INSERTed
-- into public.safety_inspections or public.safety_inspection_results it can never
-- be UPDATEd or DELETEd. Corrections/status changes/deactivations continue to flow
-- only through the already-designed journal/command path (which never mutates a
-- base row), so the normal writers are unaffected:
--   INSERT = allowed, SELECT = allowed, UPDATE = rejected, DELETE = rejected.
--
-- Fail-closed with NO bypass: the reject function is SECURITY INVOKER and raises
-- unconditionally for every row and every role (service_role/postgres included).
-- There is no role check, no session GUC, no reason/maintenance flag, no WHEN
-- clause. The triggers fire BEFORE UPDATE OR DELETE only (never INSERT, never
-- TRUNCATE).
--
-- This migration is deliberately narrow: it installs one trigger function and two
-- row triggers. It does NOT touch the pair UNIQUE index, RLS, GRANTs, FKs, the
-- journal/command objects, or any RPC, and it changes no base data.
--
-- CREATE FUNCTION / CREATE TRIGGER are used WITHOUT "OR REPLACE" / "IF NOT EXISTS"
-- so a pre-existing same-named object is surfaced by the prechecks and by the
-- create statements themselves, never silently overwritten.

BEGIN;

-- Briefly block writers on both base tables while we precheck and install.
LOCK TABLE public.safety_inspections, public.safety_inspection_results IN SHARE MODE;

DO $precheck$
DECLARE
    v_fn integer;
    v_t1 integer;
    v_t2 integer;
    v_uq integer;
BEGIN
    -- P1 - the reject function must not already exist
    SELECT count(*) INTO v_fn
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public' AND p.proname = 'fn_reject_inspection_base_mutation';
    IF v_fn > 0 THEN
        RAISE EXCEPTION 'KNOT-3D PRECHECK P1 FAILED: function public.fn_reject_inspection_base_mutation already exists';
    END IF;

    -- P2 - the header trigger must not already exist
    SELECT count(*) INTO v_t1
    FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relname = 'safety_inspections'
      AND t.tgname = 'trg_safety_inspections_immutable';
    IF v_t1 > 0 THEN
        RAISE EXCEPTION 'KNOT-3D PRECHECK P2 FAILED: trigger trg_safety_inspections_immutable already exists';
    END IF;

    -- P3 - the result trigger must not already exist
    SELECT count(*) INTO v_t2
    FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relname = 'safety_inspection_results'
      AND t.tgname = 'trg_safety_inspection_results_immutable';
    IF v_t2 > 0 THEN
        RAISE EXCEPTION 'KNOT-3D PRECHECK P3 FAILED: trigger trg_safety_inspection_results_immutable already exists';
    END IF;

    -- P4 - the KNOT-3C2 pair UNIQUE index must still exist, unique + partial + exact predicate
    SELECT count(*) INTO v_uq
    FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relname = 'uq_safety_inspections_assignment_factory'
      AND i.indisunique
      AND i.indpred IS NOT NULL
      AND pg_get_expr(i.indpred, i.indrelid) = '(assignment_id IS NOT NULL)';
    IF v_uq <> 1 THEN
        RAISE EXCEPTION 'KNOT-3D PRECHECK P4 FAILED: pair unique index uq_safety_inspections_assignment_factory missing or not (unique, partial, assignment_id IS NOT NULL)';
    END IF;
END
$precheck$;

CREATE FUNCTION public.fn_reject_inspection_base_mutation()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
AS $fn$
BEGIN
    RAISE EXCEPTION 'INSPECTION_BASE_IMMUTABLE: %.% does not allow %',
        TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_OP
        USING ERRCODE = '55000';
    RETURN NULL;
END
$fn$;

CREATE TRIGGER trg_safety_inspections_immutable
BEFORE UPDATE OR DELETE ON public.safety_inspections
FOR EACH ROW
EXECUTE FUNCTION public.fn_reject_inspection_base_mutation();

CREATE TRIGGER trg_safety_inspection_results_immutable
BEFORE UPDATE OR DELETE ON public.safety_inspection_results
FOR EACH ROW
EXECUTE FUNCTION public.fn_reject_inspection_base_mutation();

COMMIT;
