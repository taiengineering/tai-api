-- WP01-D: inspection_sets.scope_b_deactivation_date
-- 지정일 이후 반복 중단 계약을 위한 최소 스키마.
-- PENDING_MIGRATION_APPROVAL: Owner 승인 후 적용.
ALTER TABLE public.inspection_sets
    ADD COLUMN IF NOT EXISTS scope_b_deactivation_date DATE,
    ADD COLUMN IF NOT EXISTS scope_b_reason            TEXT;

COMMENT ON COLUMN public.inspection_sets.scope_b_deactivation_date IS
    'WP01-D Scope B: 반복 중단 적용일. 이 날짜 이후 신규 회차 생성 차단. NULL=예약 없음.';
COMMENT ON COLUMN public.inspection_sets.scope_b_reason IS
    'WP01-D Scope B: 중단 처리 사유.';
