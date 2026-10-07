-- WO-LFR-OBJ-S01-P3-EXEC-PREP-001 — FINAL CUTOVER (Q2+Q3 ONLY)
-- ⚠️ PREPARE ONLY. SQL APPLY = 0.
-- DO NOT execute until ALL of the following:
--   1. Additive phase (construction_additive.sql) confirmed applied
--   2. LEG published correction (20261007_lfr_s01_core22_published_correction.sql) confirmed applied
--   3. TAI-API PR #543 deployed to production
--   4. is_construction active consumers = 0/22 in CORE22 runtime CONFIRMED
--   5. Owner approval for final cutover
--
-- Purpose:
--   CONSTRUCTION FREE/PAID FINAL CUTOVER (Q2+Q3 only — no INSERT):
--   Q2: Deactivate is_construction (is_active=false, is_required=false)
--   Q3: Update child visibility: is_construction=true → appendix3_item_no=49
--
-- Pre-conditions:
--   appendix3_item_no: PRESENT and active (additive phase applied)
--   is_construction: is_active=true, is_required=true (pre-cutover state)
--   is_relationship_contractor: visibility_condition field_code = is_construction
--   is_civil_construction: visibility_condition field_code = is_construction
--
-- APPLY = 0. DO NOT RUN.

BEGIN;

-- ─── PRE-FLIGHT ──────────────────────────────────────────────────────────────

DO $$
DECLARE
  n_appendix3 int;
  n_is_construction int;
  n_rel int;
  n_civil int;
BEGIN
  -- Guard: appendix3_item_no must already exist (additive applied)
  SELECT count(*) INTO n_appendix3 FROM public.diagnosis_input_fields
   WHERE sector = 'CONSTRUCTION'
     AND field_code = 'appendix3_item_no'
     AND tier IN ('FREE', 'PAID')
     AND is_active = true;
  IF n_appendix3 != 2 THEN
    RAISE EXCEPTION
      'appendix3_item_no not present for CONSTRUCTION (% active rows, expected 2) — additive phase not applied, abort', n_appendix3;
  END IF;

  -- Guard: is_construction must still be active (cutover not yet applied)
  SELECT count(*) INTO n_is_construction FROM public.diagnosis_input_fields
   WHERE sector = 'CONSTRUCTION'
     AND field_code = 'is_construction'
     AND tier IN ('FREE', 'PAID')
     AND is_active = true;
  IF n_is_construction != 2 THEN
    RAISE EXCEPTION
      'Expected 2 active is_construction rows for CONSTRUCTION, found % — abort', n_is_construction;
  END IF;

  -- Guard: is_relationship_contractor must have is_construction visibility condition
  SELECT count(*) INTO n_rel FROM public.diagnosis_input_fields
   WHERE sector = 'CONSTRUCTION'
     AND field_code = 'is_relationship_contractor'
     AND tier IN ('FREE', 'PAID')
     AND visibility_condition->>'field_code' = 'is_construction';
  IF n_rel != 2 THEN
    RAISE EXCEPTION
      'Expected 2 is_relationship_contractor rows with is_construction visibility, found % — abort', n_rel;
  END IF;

  -- Guard: is_civil_construction must have is_construction visibility condition
  SELECT count(*) INTO n_civil FROM public.diagnosis_input_fields
   WHERE sector = 'CONSTRUCTION'
     AND field_code = 'is_civil_construction'
     AND tier IN ('FREE', 'PAID')
     AND visibility_condition->>'field_code' = 'is_construction';
  IF n_civil != 2 THEN
    RAISE EXCEPTION
      'Expected 2 is_civil_construction rows with is_construction visibility, found % — abort', n_civil;
  END IF;
END $$;

-- ─── Q2: Deactivate is_construction ──────────────────────────────────────────

UPDATE public.diagnosis_input_fields
   SET is_active = false,
       is_required = false
 WHERE sector = 'CONSTRUCTION'
   AND field_code = 'is_construction'
   AND tier IN ('FREE', 'PAID')
   AND is_active = true;

-- ─── Q3: Update child visibility condition ────────────────────────────────────
-- OLD: {"field_code":"is_construction","op":"eq","value":true}
-- NEW: {"field_code":"appendix3_item_no","op":"eq","value":49}

UPDATE public.diagnosis_input_fields
   SET visibility_condition = '{"field_code":"appendix3_item_no","op":"eq","value":49}'::jsonb
 WHERE sector = 'CONSTRUCTION'
   AND field_code IN ('is_relationship_contractor', 'is_civil_construction')
   AND tier IN ('FREE', 'PAID')
   AND visibility_condition->>'field_code' = 'is_construction'
   AND visibility_condition->>'op' = 'eq'
   AND (visibility_condition->>'value')::boolean = true;

-- ─── POST-FLIGHT ──────────────────────────────────────────────────────────────

DO $$
DECLARE
  n_appendix3_active int;
  n_is_construction_active int;
  n_child_new_vis int;
BEGIN
  -- Assert appendix3_item_no still active
  SELECT count(*) INTO n_appendix3_active FROM public.diagnosis_input_fields
   WHERE sector = 'CONSTRUCTION'
     AND field_code = 'appendix3_item_no'
     AND tier IN ('FREE', 'PAID')
     AND is_active = true;
  IF n_appendix3_active != 2 THEN
    RAISE EXCEPTION
      'appendix3_item_no active rows = % (expected 2) — ROLLBACK', n_appendix3_active;
  END IF;

  -- Assert is_construction is now inactive
  SELECT count(*) INTO n_is_construction_active FROM public.diagnosis_input_fields
   WHERE sector = 'CONSTRUCTION'
     AND field_code = 'is_construction'
     AND tier IN ('FREE', 'PAID')
     AND is_active = true;
  IF n_is_construction_active != 0 THEN
    RAISE EXCEPTION
      'is_construction still active for CONSTRUCTION (% rows) — ROLLBACK', n_is_construction_active;
  END IF;

  -- Assert child visibility updated to appendix3_item_no=49
  SELECT count(*) INTO n_child_new_vis FROM public.diagnosis_input_fields
   WHERE sector = 'CONSTRUCTION'
     AND field_code IN ('is_relationship_contractor', 'is_civil_construction')
     AND tier IN ('FREE', 'PAID')
     AND visibility_condition->>'field_code' = 'appendix3_item_no'
     AND (visibility_condition->>'value')::int = 49;
  IF n_child_new_vis != 4 THEN
    RAISE EXCEPTION
      'Expected 4 child rows with appendix3_item_no=49 visibility, found % — ROLLBACK', n_child_new_vis;
  END IF;
END $$;

-- ─── READBACK QUERY ───────────────────────────────────────────────────────────

SELECT sector, tier, field_code, field_type, is_active, is_required,
       visibility_condition, sort_order
  FROM public.diagnosis_input_fields
 WHERE sector = 'CONSTRUCTION'
   AND field_code IN (
     'appendix3_item_no', 'is_construction',
     'is_relationship_contractor', 'is_civil_construction'
   )
 ORDER BY tier, sort_order;

COMMIT;
