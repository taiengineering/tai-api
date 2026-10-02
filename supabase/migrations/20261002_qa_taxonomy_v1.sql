-- WO-QA-UNIVERSE-PHASE1-TAXONOMY-CANONICAL-001
-- Phase 1: qa_items 업무 분류 Canonical 3개 컬럼 추가 + 기존 10건 Backfill
--
-- 변경 대상:  qa_items (service_code, area_code, qa_type)
-- 변경 금지:  qa_schedules / qa_runs / qa_run_targets / qa_run_results
--             scenario_id / site_code / category / priority / runner_type / enabled
--
-- Source: WO-QA-UNIVERSE-PHASE0-SURFACE-INVENTORY-001 58134ae0
-- Idempotent: ADD COLUMN IF NOT EXISTS / constraint 존재 여부 확인

BEGIN;

-- ── Step 1: 컬럼 추가 (nullable — backfill 전까지) ────────────────────────────

ALTER TABLE public.qa_items
  ADD COLUMN IF NOT EXISTS service_code TEXT,
  ADD COLUMN IF NOT EXISTS area_code    TEXT,
  ADD COLUMN IF NOT EXISTS qa_type      TEXT;

-- ── Step 2: CHECK constraint 추가 (idempotent) ────────────────────────────────

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'qa_items_service_code_check'
      AND conrelid = 'public.qa_items'::regclass
  ) THEN
    ALTER TABLE public.qa_items
      ADD CONSTRAINT qa_items_service_code_check
        CHECK (service_code IN ('WWW', 'SAAS', 'ADMIN', 'WORKER'));
  END IF;
END
$$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'qa_items_qa_type_check'
      AND conrelid = 'public.qa_items'::regclass
  ) THEN
    ALTER TABLE public.qa_items
      ADD CONSTRAINT qa_items_qa_type_check
        CHECK (qa_type IN (
          'AVAILABILITY', 'FUNCTIONAL', 'INTEGRATION', 'E2E', 'API',
          'PERFORMANCE', 'SECURITY', 'DATA', 'ACCESSIBILITY', 'VISUAL'
        ));
  END IF;
END
$$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'qa_items_area_code_check'
      AND conrelid = 'public.qa_items'::regclass
  ) THEN
    ALTER TABLE public.qa_items
      ADD CONSTRAINT qa_items_area_code_check
        CHECK (area_code ~ '^[A-Z][A-Z0-9_]*$');
  END IF;
END
$$;

-- ── Step 3: 기존 10건 Backfill (scenario_id 기준 명시적 매핑) ────────────────

UPDATE public.qa_items SET service_code = 'WWW',  area_code = 'LANDING',        qa_type = 'AVAILABILITY' WHERE scenario_id = 'P0-WWW-001';
UPDATE public.qa_items SET service_code = 'WWW',  area_code = 'FREE_DIAGNOSIS',  qa_type = 'AVAILABILITY' WHERE scenario_id = 'P0-DIAG-001';
UPDATE public.qa_items SET service_code = 'WWW',  area_code = 'SEARCH',          qa_type = 'AVAILABILITY' WHERE scenario_id = 'P0-SRCH-001';
UPDATE public.qa_items SET service_code = 'WWW',  area_code = 'SEARCH',          qa_type = 'FUNCTIONAL'   WHERE scenario_id = 'P0-SRCH-002';
UPDATE public.qa_items SET service_code = 'SAAS', area_code = 'MYPAGE',          qa_type = 'AVAILABILITY' WHERE scenario_id = 'P0-MYP-001';
UPDATE public.qa_items SET service_code = 'SAAS', area_code = 'MYPAGE',          qa_type = 'FUNCTIONAL'   WHERE scenario_id = 'P0-MYP-005';
UPDATE public.qa_items SET service_code = 'SAAS', area_code = 'AUTH',            qa_type = 'E2E'          WHERE scenario_id = 'P0-SAAS-001';
UPDATE public.qa_items SET service_code = 'WWW',  area_code = 'AUTH',            qa_type = 'E2E'          WHERE scenario_id = 'P0-WWW-003';
UPDATE public.qa_items SET service_code = 'WWW',  area_code = 'HEADER',          qa_type = 'FUNCTIONAL'   WHERE scenario_id = 'P0-WWW-004';
UPDATE public.qa_items SET service_code = 'WWW',  area_code = 'HEADER',          qa_type = 'FUNCTIONAL'   WHERE scenario_id = 'P0-WWW-005';

-- ── Step 4: Fail-closed guard — NULL이 남으면 migration 실패 ─────────────────

DO $$
DECLARE
  null_count integer;
BEGIN
  SELECT COUNT(*) INTO null_count
  FROM public.qa_items
  WHERE service_code IS NULL
     OR area_code    IS NULL
     OR qa_type      IS NULL;

  IF null_count > 0 THEN
    RAISE EXCEPTION
      'TAXONOMY_BACKFILL_INCOMPLETE: % row(s) still have NULL taxonomy fields. '
      'Verify all qa_items have been classified before running this migration.',
      null_count;
  END IF;
END
$$;

-- ── Step 5: NOT NULL 적용 ─────────────────────────────────────────────────────

ALTER TABLE public.qa_items
  ALTER COLUMN service_code SET NOT NULL,
  ALTER COLUMN area_code    SET NOT NULL,
  ALTER COLUMN qa_type      SET NOT NULL;

-- ── Step 6: 인덱스 (선택적, 필터 성능) ──────────────────────────────────────

CREATE INDEX IF NOT EXISTS qa_items_service_code_idx ON public.qa_items (service_code);
CREATE INDEX IF NOT EXISTS qa_items_area_code_idx    ON public.qa_items (area_code);
CREATE INDEX IF NOT EXISTS qa_items_qa_type_idx      ON public.qa_items (qa_type);

COMMIT;
