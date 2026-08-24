-- =============================================================================
-- WP-DATA-ARCH-04D  Safety Inspection Factory Companion  (UP)
-- LEVEL-A · ADD COLUMN + DETERMINISTIC LINKED-SUBSET BACKFILL (fail-closed)
-- intended path   : tai-api/docs/sql/20260824_safety_inspections_factory_companion_up.sql
-- source API base : ad027e530f649df5dabb9d2ec0f6bddcbf806b7c   (04C deployed HEAD)
-- canonical plan  : taiengineering/taieng @ 65f2e5590d6881577d31afd64af23787493df19a (S1-4 / B2-1 / WS-3)
--
-- PRE-STATE ANCHOR [실측 @ vwlahtguyggrhvslabax]
--   safety_inspections : rows=2 · PK(id) · FK(assignment_id→work_schedules, asset_id→equipment_assets,
--                        inspector_id→users, submitted_by→users RESTRICT[04B]) · RLS enabled · triggers 0
--   factory_id column exists = 0  (safe to ADD)
--   ROW SPLIT:
--     schedule-backed (assignment_id NOT NULL) = 1   → DETERMINISTIC LINKED (backfill 대상)
--     legacy/standalone (assignment_id NULL)   = 1   → LEGACY NULL PAIR (factory_id NULL 유지, 실패 아님)
--   linked broken parent = 0 · linked parent factory_id NULL = 0 · deterministic linked resolvable = 1/1
--
-- factory_id = work_schedules parent relation COMPANION (신규 tenant authority 아님).
-- canonical source = si.assignment_id → work_schedules.id → work_schedules.factory_id  (ONLY)
--
-- ★ 성공조건은 "factory_id 전량 NULL=0"이 아님:
--     linked(assignment_id NOT NULL) → factory_id = parent (NULL/mismatch 0)
--     standalone(assignment_id NULL) → factory_id 는 NULL 로 유지 (임의 factory 추론 금지)
--
-- SCOPE (이번 04D): +1 nullable column + linked-subset backfill 만.
-- NOT IN 04D: NOT NULL · single/composite FK · MATCH FULL · pair CHECK · work_schedules PK 변경 · HASH · tenant filter.
-- 실행 규율: 단일 atomic transaction. PRECHECK/POST 위반 시 RAISE → 전체 rollback (fail-closed).
--            production 실행은 cutover runbook의 WRITE OFF 구간에서만.
-- =============================================================================

-- ── PRECHECK (fail-closed) ───────────────────────────────────────────────────
--   (A) assignment_id NOT NULL 인데 parent work_schedules 없음(broken) → FAIL
--   (B) assignment_id NOT NULL 인데 parent factory_id NULL → FAIL
--   assignment_id IS NULL 은 FAIL 아님 (LEGACY NULL PAIR 허용).
DO $$
BEGIN
  IF (SELECT count(*) FROM public.safety_inspections si
        WHERE si.assignment_id IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM public.work_schedules ws WHERE ws.id = si.assignment_id)) > 0 THEN
    RAISE EXCEPTION 'WP04D PRECHECK FAIL: linked broken schedule parent 존재 (backfill 불가)';
  END IF;
  IF (SELECT count(*) FROM public.safety_inspections si
        JOIN public.work_schedules ws ON ws.id = si.assignment_id
        WHERE ws.factory_id IS NULL) > 0 THEN
    RAISE EXCEPTION 'WP04D PRECHECK FAIL: linked parent work_schedules.factory_id NULL 존재 (backfill 불가)';
  END IF;
END $$;

-- ── (1) additive nullable column ─────────────────────────────────────────────
ALTER TABLE public.safety_inspections
    ADD COLUMN factory_id uuid NULL;

-- ── (2) deterministic LINKED-SUBSET backfill (standalone assignment_id NULL 은 미대상 → NULL 유지) ──
UPDATE public.safety_inspections si
   SET factory_id = ws.factory_id
  FROM public.work_schedules ws
 WHERE si.assignment_id = ws.id
   AND si.factory_id IS NULL;

-- ── POST VALIDATION (fail-closed) ────────────────────────────────────────────
DO $$
BEGIN
  -- linked(assignment_id NOT NULL) 행은 factory_id NULL 잔존 0
  IF (SELECT count(*) FROM public.safety_inspections
        WHERE assignment_id IS NOT NULL AND factory_id IS NULL) > 0 THEN
    RAISE EXCEPTION 'WP04D POST FAIL: linked row factory_id NULL 잔존';
  END IF;
  -- linked 값은 parent factory_id 와 100% 일치
  IF (SELECT count(*) FROM public.safety_inspections si
        JOIN public.work_schedules ws ON ws.id = si.assignment_id
        WHERE si.factory_id IS DISTINCT FROM ws.factory_id) > 0 THEN
    RAISE EXCEPTION 'WP04D POST FAIL: linked factory_id parent mismatch';
  END IF;
  -- standalone(assignment_id NULL) 행은 factory_id 반드시 NULL 유지 (임의 채움 금지)
  IF (SELECT count(*) FROM public.safety_inspections
        WHERE assignment_id IS NULL AND factory_id IS NOT NULL) > 0 THEN
    RAISE EXCEPTION 'WP04D POST FAIL: standalone row factory_id 비-NULL (추론 오염)';
  END IF;
END $$;
-- (row count 불변은 ADD/UPDATE 특성상 보장 — POST 실측으로 재확인)
