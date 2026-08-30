-- =====================================================================
-- §90 COMMON EVENT CORE v1 — DOWN (documented teardown only)
-- =====================================================================
-- WARNING (§20): this is NOT a production auto-rollback.
--
-- Preferred rollback = CODE rollback (emitter stops writing v1); the new
-- columns REMAIN. Dropping the columns AFTER any event_version=1 row exists is
-- DATA LOSS. Do NOT run this in production once v1 rows have been written.
--
-- Provided only for local/dev teardown of a clean (v1-free) table.
-- =====================================================================

BEGIN;

ALTER TABLE public.business_event DROP CONSTRAINT IF EXISTS be_contract_v1_chk;
ALTER TABLE public.business_event DROP CONSTRAINT IF EXISTS be_outcome_chk;
ALTER TABLE public.business_event DROP CONSTRAINT IF EXISTS be_actor_kind_chk;
ALTER TABLE public.business_event DROP CONSTRAINT IF EXISTS be_event_version_chk;
ALTER TABLE public.business_event DROP CONSTRAINT IF EXISTS be_event_name_chk;

ALTER TABLE public.business_event DROP COLUMN IF EXISTS outcome;
ALTER TABLE public.business_event DROP COLUMN IF EXISTS actor_ref;
ALTER TABLE public.business_event DROP COLUMN IF EXISTS actor_kind;
ALTER TABLE public.business_event DROP COLUMN IF EXISTS occurred_at;
ALTER TABLE public.business_event DROP COLUMN IF EXISTS event_version;
ALTER TABLE public.business_event DROP COLUMN IF EXISTS event_name;

COMMIT;
