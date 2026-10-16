-- WO-E2E2000-WP01-A-C10-FOUNDATION-001 B-1
-- anonymous_diagnosis_results 에 inspection_materialization_status 컬럼 추가.
--
-- 목적: SaaS LEG 결과 저장 후 canonical inspection_sets 반영 결과를 기록.
--   PENDING            — C10 INSERT 직후 기본값 (writer 미실행 or 진행 중)
--   MATERIALIZED       — canonical_writer 실행 성공
--   FAILED             — canonical_writer 예외 발생
--   BLOCKED_LEGACY_ROWS — legacy null-atom row 존재로 writer 미실행
--
-- 기존 행: NULL 유지 (backfill 0). NULL = 확정 미완료 취급 (WP01-A 기준 조건 외).
-- 기존 RLS 정책·GRANT·status 컬럼·full_result 무변경.

ALTER TABLE public.anonymous_diagnosis_results
  ADD COLUMN IF NOT EXISTS inspection_materialization_status TEXT NULL;
