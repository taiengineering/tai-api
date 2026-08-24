-- =============================================================================
-- WP-DATA-ARCH-04D  Safety Inspection Factory Companion  (DOWN)
-- intended path   : tai-api/docs/sql/20260824_safety_inspections_factory_companion_down.sql
-- source API base : ad027e530f649df5dabb9d2ec0f6bddcbf806b7c
-- canonical plan  : taiengineering/taieng @ 65f2e5590d6881577d31afd64af23787493df19a
--
-- Removes the single object added by UP. No other object touched.
--
-- ★ ROLLBACK 조건:
--   ROLLBACK-A (patched writer DEPLOY 전) = 이 DOWN 단독 실행으로 안전
--       (구 writer 2개(worker_check/inspection_checklist)는 factory_id 미참조 → nullable 컬럼 제거 무해).
--   ROLLBACK-B (patched writer DEPLOY 후) = column DROP 단독 금지.
--       순서 = WRITE OFF → patched writer CODE ROLLBACK(worker_check.py · inspection_checklist.py git revert)
--              → 이 DOWN(DROP COLUMN) → old behavior 검증 → WRITE ON.
--   즉 writer가 factory_id 를 쓰기 시작한 뒤에는 code rollback 없이 컬럼부터 DROP 금지.
--
-- 주의: 이 DOWN 은 legacy/standalone(assignment_id NULL) 행이나 그 어떤 business data 도 변경하지 않는다(스키마만).
-- =============================================================================

ALTER TABLE public.safety_inspections
    DROP COLUMN factory_id;
