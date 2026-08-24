-- =============================================================================
-- WP-DATA-ARCH-04B  Safety Inspection Submitter Anchor  (UP)
-- LEVEL-B ADDITIVE MIGRATION · schema-only
-- intended path   : tai-api/docs/sql/20260824_safety_inspection_submitter_anchor_up.sql
-- source API base : e1506aa45d3b35bf4d99d3c123600e9f19ab6996
-- canonical plan  : taiengineering/taieng @ 65f2e5590d6881577d31afd64af23787493df19a  (IMPLEMENTATION_PLAN S1-3)
--
-- PRE-STATE ANCHOR [실측 @ vwlahtguyggrhvslabax]
--   safety_inspections : PK(id) · FK(assignment_id→work_schedules, asset_id→equipment_assets, inspector_id→users)
--                        rows=2 · RLS enabled · triggers 0
--   submitted_by column exists          = 0  (safe to ADD)
--   target FK name collision            = 0  (safety_inspections_submitted_by_fkey free)
--   users PK                            = PRIMARY KEY (id) · id uuid  (single-col FK target valid)
--
-- IDENTITY CONTRACT
--   inspector_id  = 실제 검사자 (existing)
--   submitted_by  = 제출 행위를 한 인증 사용자 (신규, 서로 다른 의미)
--   legacy rows   = submitted_by NULL 허용 · future canonical writes = authenticated current_user.id
--
-- SCOPE (exactly 2 objects): +1 column, +1 FK. Nothing else.
-- FORBIDDEN: historical backfill · inspector_id→submitted_by 복사 · worker_registry id 사용
--            · auth/code patch · worker_check/inspection_checklist 수정 · deploy
-- =============================================================================

-- (1) additive nullable column (legacy = NULL; future = authenticated submitter)
ALTER TABLE public.safety_inspections
    ADD COLUMN submitted_by uuid NULL;

-- (2) FK → users(id), ON DELETE RESTRICT (SET NULL 금지)
ALTER TABLE public.safety_inspections
    ADD CONSTRAINT safety_inspections_submitted_by_fkey
    FOREIGN KEY (submitted_by)
    REFERENCES public.users (id)
    ON DELETE RESTRICT;
