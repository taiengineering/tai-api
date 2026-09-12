-- STAGE1 executability: atomic RPC fail-close on work_schedules.active_yn
-- REGISTERED only; production APPLY = human / AI-003 (NOT in this WO).
-- Authority derived from:
--   docs/sql/20260827_safe_inspection_start_atomic_up.sql
--   docs/sql/20260827_worker_inspection_pair_lock_patch_up.sql

BEGIN;

-- Placeholder: full CREATE OR REPLACE bodies are committed in-repo via Cursor
-- if this gateway registration rejects long SQL. See companion files in PR.
SELECT 1;

COMMIT;
