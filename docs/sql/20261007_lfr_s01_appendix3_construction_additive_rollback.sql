-- WO-LFR-OBJ-S01-P3-EXEC-PREP-001 — ADDITIVE PHASE ROLLBACK
-- APPLY = 0. DO NOT EXECUTE unless additive phase was applied and must be undone.
-- DO NOT execute if final_cutover.sql has already been applied.
--
-- Reverses: 20261007_lfr_s01_appendix3_construction_additive.sql
-- Removes appendix3_item_no from CONSTRUCTION FREE/PAID.
-- Restores pre-additive state (is_construction active, no appendix3_item_no).

BEGIN;

-- ─── PRE-FLIGHT ──────────────────────────────────────────────────────────────

DO $$
DECLARE
  n_appendix3 int;
  n_cutover_applied int;
BEGIN
  -- Guard: appendix3_item_no must exist (additive was applied)
  SELECT count(*) INTO n_appendix3 FROM public.diagnosis_input_fields
   WHERE sector = 'CONSTRUCTION'
     AND field_code = 'appendix3_item_no'
     AND tier IN ('FREE', 'PAID');
  IF n_appendix3 = 0 THEN
    RAISE EXCEPTION 'appendix3_item_no not found for CONSTRUCTION — additive not applied, nothing to rollback';
  END IF;

  -- Guard: final cutover must NOT have been applied (is_construction must still be active)
  SELECT count(*) INTO n_cutover_applied FROM public.diagnosis_input_fields
   WHERE sector = 'CONSTRUCTION'
     AND field_code = 'is_construction'
     AND tier IN ('FREE', 'PAID')
     AND is_active = false;
  IF n_cutover_applied > 0 THEN
    RAISE EXCEPTION
      'final_cutover appears already applied (is_construction inactive, % rows) — use final_cutover_rollback.sql instead', n_cutover_applied;
  END IF;
END $$;

-- ─── REMOVE appendix3_item_no ─────────────────────────────────────────────────

DELETE FROM public.diagnosis_input_fields
 WHERE sector = 'CONSTRUCTION'
   AND field_code = 'appendix3_item_no'
   AND tier IN ('FREE', 'PAID');

-- ─── POST-FLIGHT ──────────────────────────────────────────────────────────────

DO $$
DECLARE
  n_appendix3 int;
  n_is_construction int;
BEGIN
  SELECT count(*) INTO n_appendix3 FROM public.diagnosis_input_fields
   WHERE sector = 'CONSTRUCTION'
     AND field_code = 'appendix3_item_no'
     AND tier IN ('FREE', 'PAID');
  IF n_appendix3 != 0 THEN
    RAISE EXCEPTION 'appendix3_item_no still present after rollback (% rows) — ROLLBACK', n_appendix3;
  END IF;

  SELECT count(*) INTO n_is_construction FROM public.diagnosis_input_fields
   WHERE sector = 'CONSTRUCTION'
     AND field_code = 'is_construction'
     AND tier IN ('FREE', 'PAID')
     AND is_active = true;
  IF n_is_construction != 2 THEN
    RAISE EXCEPTION
      'is_construction not active after additive rollback (% active rows, expected 2) — ROLLBACK', n_is_construction;
  END IF;
END $$;

COMMIT;
