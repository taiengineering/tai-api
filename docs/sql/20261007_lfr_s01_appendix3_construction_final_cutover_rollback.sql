-- WO-LFR-OBJ-S01-P3-EXEC-PREP-001 — FINAL CUTOVER ROLLBACK
-- APPLY = 0. DO NOT EXECUTE unless final cutover was applied and must be undone.
-- CRITICAL: Restores is_construction=active and child visibility. Does NOT remove appendix3_item_no.
-- To also remove appendix3_item_no, run additive_rollback.sql AFTER this rollback.

BEGIN;

-- ─── PRE-FLIGHT ──────────────────────────────────────────────────────────────

DO $$
DECLARE
  n_is_construction_inactive int;
  n_child_new_vis int;
BEGIN
  -- Guard: is_construction must be inactive (cutover applied)
  SELECT count(*) INTO n_is_construction_inactive FROM public.diagnosis_input_fields
   WHERE sector = 'CONSTRUCTION'
     AND field_code = 'is_construction'
     AND tier IN ('FREE', 'PAID')
     AND is_active = false;
  IF n_is_construction_inactive = 0 THEN
    RAISE EXCEPTION 'is_construction is still active — final cutover not applied, nothing to rollback';
  END IF;

  -- Guard: child visibility must be in post-cutover state
  SELECT count(*) INTO n_child_new_vis FROM public.diagnosis_input_fields
   WHERE sector = 'CONSTRUCTION'
     AND field_code IN ('is_relationship_contractor', 'is_civil_construction')
     AND tier IN ('FREE', 'PAID')
     AND visibility_condition->>'field_code' = 'appendix3_item_no';
  IF n_child_new_vis = 0 THEN
    RAISE EXCEPTION 'child visibility not in post-cutover state — nothing to rollback';
  END IF;
END $$;

-- ─── RESTORE Q2: Re-activate is_construction ─────────────────────────────────

UPDATE public.diagnosis_input_fields
   SET is_active = true,
       is_required = true
 WHERE sector = 'CONSTRUCTION'
   AND field_code = 'is_construction'
   AND tier IN ('FREE', 'PAID');

-- ─── RESTORE Q3: Revert child visibility to is_construction ──────────────────

UPDATE public.diagnosis_input_fields
   SET visibility_condition = '{"field_code":"is_construction","op":"eq","value":true}'::jsonb
 WHERE sector = 'CONSTRUCTION'
   AND field_code IN ('is_relationship_contractor', 'is_civil_construction')
   AND tier IN ('FREE', 'PAID')
   AND visibility_condition->>'field_code' = 'appendix3_item_no'
   AND (visibility_condition->>'value')::int = 49;

-- ─── POST-FLIGHT ──────────────────────────────────────────────────────────────

DO $$
DECLARE
  n_is_construction_active int;
  n_child_old_vis int;
BEGIN
  SELECT count(*) INTO n_is_construction_active FROM public.diagnosis_input_fields
   WHERE sector = 'CONSTRUCTION'
     AND field_code = 'is_construction'
     AND tier IN ('FREE', 'PAID')
     AND is_active = true;
  IF n_is_construction_active != 2 THEN
    RAISE EXCEPTION
      'is_construction active rows = % after rollback (expected 2) — ROLLBACK', n_is_construction_active;
  END IF;

  SELECT count(*) INTO n_child_old_vis FROM public.diagnosis_input_fields
   WHERE sector = 'CONSTRUCTION'
     AND field_code IN ('is_relationship_contractor', 'is_civil_construction')
     AND tier IN ('FREE', 'PAID')
     AND visibility_condition->>'field_code' = 'is_construction';
  IF n_child_old_vis != 4 THEN
    RAISE EXCEPTION
      'Expected 4 child rows with is_construction visibility after rollback, found % — ROLLBACK', n_child_old_vis;
  END IF;
END $$;

COMMIT;
