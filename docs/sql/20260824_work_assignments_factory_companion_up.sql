-- =============================================================================
-- WP-DATA-ARCH-04C  Work Assignment Factory Companion  (UP)
-- LEVEL-A · ADD COLUMN + DETERMINISTIC BACKFILL (fail-closed)
-- intended path   : tai-api/docs/sql/20260824_work_assignments_factory_companion_up.sql
-- source API base : e1506aa45d3b35bf4d99d3c123600e9f19ab6996  (HEAD cfd87aff, code 동일)
-- canonical plan  : taiengineering/taieng @ 65f2e5590d6881577d31afd64af23787493df19a (S1-6 / B2-4 / WS-1·WS-2)
--
-- PRE-STATE ANCHOR [실측 @ vwlahtguyggrhvslabax]
--   work_assignments : rows=5991 · PK(id) · FK(schedule_id→work_schedules, asset_id→equipment_assets, assigned_user_id→users)
--                      factory_id column exists = 0 · UNIQUE(schedule_id,scheduled_date) 없음
--   backfill determinism : schedule_id NULL=0 · broken parent=0 · parent factory_id NULL=0
--                          deterministic_resolvable = 5991/5991 (100%) · UNRESOLVED = 0
--
-- factory_id = work_schedules parent relation COMPANION (신규 tenant authority 아님).
-- canonical source = wa.schedule_id → work_schedules.id → work_schedules.factory_id (유일).
--
-- SCOPE (이번 04C): +1 nullable column + deterministic backfill 만.
-- NOT IN 04C: NOT NULL · composite FK · MATCH FULL · pair CHECK · HASH migration · tenant filter 전환.
-- 실행 규율: 아래는 단일 atomic transaction. PRECHECK/POST 위반 시 RAISE → 전체 rollback (fail-closed).
--            production 실행은 cutover runbook의 WRITE OFF 구간에서만.
-- =============================================================================

-- ── PRECHECK (fail-closed; 위반 시 ADD/UPDATE 전에 중단) ──────────────────────
DO $$
BEGIN
  -- (a) schedule_id NULL 행 = factory companion 결정 불가 → 즉시 중단
  --     (POST 검사는 schedule_id NOT NULL 만 보므로, 여기서 막지 않으면 unresolved NULL 잔존 가능)
  IF EXISTS (
      SELECT 1 FROM public.work_assignments WHERE schedule_id IS NULL
  ) THEN
    RAISE EXCEPTION 'WP04C PRECHECK FAIL: schedule_id NULL 존재 (factory companion 결정 불가)';
  END IF;
  -- (b) broken schedule parent
  IF (SELECT count(*) FROM public.work_assignments wa
        LEFT JOIN public.work_schedules ws ON wa.schedule_id = ws.id
        WHERE wa.schedule_id IS NOT NULL AND ws.id IS NULL) > 0 THEN
    RAISE EXCEPTION 'WP04C PRECHECK FAIL: broken schedule parent 존재 (backfill 불가)';
  END IF;
  IF (SELECT count(*) FROM public.work_assignments wa
        JOIN public.work_schedules ws ON wa.schedule_id = ws.id
        WHERE ws.factory_id IS NULL) > 0 THEN
    RAISE EXCEPTION 'WP04C PRECHECK FAIL: parent work_schedules.factory_id NULL 존재 (backfill 불가)';
  END IF;
END $$;

-- ── (1) additive nullable column ─────────────────────────────────────────────
ALTER TABLE public.work_assignments
    ADD COLUMN factory_id uuid NULL;

-- ── (2) deterministic backfill (canonical source = parent work_schedules.factory_id) ──
UPDATE public.work_assignments wa
   SET factory_id = ws.factory_id
  FROM public.work_schedules ws
 WHERE wa.schedule_id = ws.id
   AND wa.factory_id IS NULL;

-- ── POST VALIDATION (fail-closed; 위반 시 rollback) ──────────────────────────
DO $$
BEGIN
  -- 전량 factory_id NULL gap = 0 (schedule_id NULL 행은 PRECHECK에서 이미 차단 → 남아있으면 실패)
  IF (SELECT count(*) FROM public.work_assignments WHERE factory_id IS NULL) > 0 THEN
    RAISE EXCEPTION 'WP04C POST FAIL: factory_id NULL 잔존 (unresolved companion)';
  END IF;
  -- 채워진 값은 부모 factory_id와 100% 일치
  IF (SELECT count(*) FROM public.work_assignments wa
        JOIN public.work_schedules ws ON wa.schedule_id = ws.id
        WHERE wa.factory_id IS DISTINCT FROM ws.factory_id) > 0 THEN
    RAISE EXCEPTION 'WP04C POST FAIL: factory_id parent mismatch';
  END IF;
END $$;
-- (row count 불변은 ADD/UPDATE 특성상 보장 — POST 실측으로 재확인)
