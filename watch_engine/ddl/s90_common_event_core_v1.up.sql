-- =====================================================================
-- §90 COMMON EVENT CORE v1 — business_event forward contract (UP)
-- =====================================================================
-- ARCHITECTURE: A+C (business_event forward-only additive evolution).
--
-- Properties (§20): additive · idempotent · forward-only · legacy-safe.
--   * Adds 6 nullable columns + 5 CHECK constraints.
--   * LEGACY rows (event_version IS NULL) are UNTOUCHED and remain valid.
--   * NO data backfill / rewrite. Expected legacy UPDATE = 0 rows.
--   * Existing be_actor_chk / be_result_chk / be_env_chk / be_connector_chk
--     are NOT modified (§5).
--
-- ARTIFACT ONLY: this file is authored for review. It is NOT auto-applied.
-- Production apply is authorized separately by GPT after STEP B review (§22).
-- =====================================================================

BEGIN;

-- ─── 3. NEW PHYSICAL COLUMNS (all nullable; legacy-safe, metadata-only) ───
ALTER TABLE public.business_event ADD COLUMN IF NOT EXISTS event_name    text;
ALTER TABLE public.business_event ADD COLUMN IF NOT EXISTS event_version integer;
ALTER TABLE public.business_event ADD COLUMN IF NOT EXISTS occurred_at   timestamptz;
ALTER TABLE public.business_event ADD COLUMN IF NOT EXISTS actor_kind    text;
ALTER TABLE public.business_event ADD COLUMN IF NOT EXISTS actor_ref     text;
ALTER TABLE public.business_event ADD COLUMN IF NOT EXISTS outcome       text;

-- ─── 5 + 6. CANONICAL CHECKS + CONTRACT ROW INVARIANT (idempotent guards) ───
DO $do$
BEGIN
  -- event_name: UPPER_SNAKE <DOMAIN>_<EVENT>, >= 2 segments, no leading/
  -- trailing/double underscore, no spaces. NULL allowed (legacy).
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'be_event_name_chk'
      AND conrelid = 'public.business_event'::regclass
  ) THEN
    ALTER TABLE public.business_event
      ADD CONSTRAINT be_event_name_chk
      CHECK (event_name IS NULL OR event_name ~ '^[A-Z][A-Z0-9]*(_[A-Z0-9]+)+$');
  END IF;

  -- event_version: positive integer when present.
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'be_event_version_chk'
      AND conrelid = 'public.business_event'::regclass
  ) THEN
    ALTER TABLE public.business_event
      ADD CONSTRAINT be_event_version_chk
      CHECK (event_version IS NULL OR event_version > 0);
  END IF;

  -- actor_kind: canonical §87 actor set. NULL allowed (legacy).
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'be_actor_kind_chk'
      AND conrelid = 'public.business_event'::regclass
  ) THEN
    ALTER TABLE public.business_event
      ADD CONSTRAINT be_actor_kind_chk
      CHECK (actor_kind IS NULL OR actor_kind = ANY (ARRAY[
        'USER','WORKER','SYSTEM','SERVICE','CRON','ENGINE','LLM','EXTERNAL'
      ]));
  END IF;

  -- outcome: canonical §87 outcome set. NULL allowed (optional, §6).
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'be_outcome_chk'
      AND conrelid = 'public.business_event'::regclass
  ) THEN
    ALTER TABLE public.business_event
      ADD CONSTRAINT be_outcome_chk
      CHECK (outcome IS NULL OR outcome = ANY (ARRAY[
        'SUCCESS','FAILURE','PARTIAL','DENIED','SKIPPED','NOOP'
      ]));
  END IF;

  -- CONTRACT ROW INVARIANT (§6): a versioned row must carry a complete,
  -- non-placeholder canonical core. LEGACY rows (event_version IS NULL) bypass
  -- the invariant entirely and are always accepted. trace_id/service_key/
  -- tenant_id/environment are already NOT NULL at the column level; restated
  -- here for explicitness. §15: placeholder trace cannot be a v1 event.
  -- outcome is OPTIONAL and intentionally excluded from the invariant.
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'be_contract_v1_chk'
      AND conrelid = 'public.business_event'::regclass
  ) THEN
    ALTER TABLE public.business_event
      ADD CONSTRAINT be_contract_v1_chk
      CHECK (
        event_version IS NULL
        OR (
          event_name  IS NOT NULL
          AND occurred_at IS NOT NULL
          AND actor_kind  IS NOT NULL
          AND actor_ref   IS NOT NULL
          AND trace_id    IS NOT NULL
          AND service_key IS NOT NULL
          AND tenant_id   IS NOT NULL
          AND environment IS NOT NULL
          AND trace_id NOT IN ('no_trace', 'unknown', '')
        )
      );
  END IF;
END
$do$;

COMMIT;

-- =====================================================================
-- POST-APPLY EXPECTATION (for STEP B verification):
--   * 6 columns present, all nullable.
--   * 5 new constraints present (be_event_name_chk, be_event_version_chk,
--     be_actor_kind_chk, be_outcome_chk, be_contract_v1_chk).
--   * All 24,768 existing rows have event_version IS NULL → invariant passes;
--     0 rows updated, 0 rows rejected.
--   * be_actor_chk / be_result_chk unchanged.
-- =====================================================================
