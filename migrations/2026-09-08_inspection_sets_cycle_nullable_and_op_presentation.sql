-- WO-SAAS-CANONICAL-INSPECTION-WRITER-001 / STEP 4B-3 REV-1 (A-GUARDED)
-- canonical INSPECT obligation → inspection_sets 미스케줄(operation) row 저장을 위한 스키마 준비.
--
-- 1) cycle_unit / cycle_value NOT NULL 완화(nullable).
--    canonical row 는 cycle_unit=NULL, cycle_value=NULL 로 저장 → legacy year/1 schedule fallback 차단.
--    scheduler(_meets_4_conditions)는 cycle_unit truthy 를 요구하므로 NULL row 는 자동 스케줄 대상 아님(fail-close).
--    ※ 코드측 anchor/schedule write 경계 guard(has_explicit_schedule_cycle)와 함께 배포해야 안전.
--    cycle_value DEFAULT 1 은 유지(legacy INSERT 생략 시 기존 동작 보존). canonical writer 는 명시 NULL 저장.
-- 2) legal_operation_presentation jsonb 추가 = map_operation_presentation(raw) EXACT snapshot(consumer read-model).
--    SoT 아님(SoT=full_result.obligations_raw[]). frontend 재조립 방지용.
--
-- ARTIFACT ONLY — DB APPLY = 0 (GPT 승인 후 별도 실행). idempotent.

ALTER TABLE public.inspection_sets
    ALTER COLUMN cycle_unit DROP NOT NULL;

ALTER TABLE public.inspection_sets
    ALTER COLUMN cycle_value DROP NOT NULL;

ALTER TABLE public.inspection_sets
    ADD COLUMN IF NOT EXISTS legal_operation_presentation jsonb;

COMMENT ON COLUMN public.inspection_sets.legal_operation_presentation IS
    'Derived snapshot = map_operation_presentation(full_result.obligations_raw[]) EXACT. consumer read-model(법령 SoT 아님). NULL=legacy/미링크.';
