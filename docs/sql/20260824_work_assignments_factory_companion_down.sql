-- =============================================================================
-- WP-DATA-ARCH-04C  Work Assignment Factory Companion  (DOWN)
-- intended path   : tai-api/docs/sql/20260824_work_assignments_factory_companion_down.sql
-- source API base : e1506aa45d3b35bf4d99d3c123600e9f19ab6996
-- canonical plan  : taiengineering/taieng @ 65f2e5590d6881577d31afd64af23787493df19a
--
-- Removes the single object added by UP. No other object touched.
--
-- ★ ROLLBACK 조건 (중요):
--   ROLLBACK-A (patched writer DEPLOY 전) = 이 DOWN 단독 실행으로 안전 (구 writer는 factory_id 미참조).
--   ROLLBACK-B (patched writer DEPLOY 후) = column DROP 단독 금지.
--       순서 = WRITE OFF → patched writer CODE ROLLBACK → 이 DOWN(DROP COLUMN) → old behavior 검증 → WRITE ON.
--   즉 writer가 factory_id 를 쓰기 시작한 뒤에는 code rollback 없이 컬럼부터 DROP 금지.
-- =============================================================================

ALTER TABLE public.work_assignments
    DROP COLUMN factory_id;
