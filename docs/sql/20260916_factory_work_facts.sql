-- WO-E2E-OBS009-COMMON-WORK-SOURCE-IMPLEMENT-001
-- Common Work Source storage. Family-specific tables = 0.
-- PRODUCTION DB APPLY = 0. File is deploy-ready and idempotent.
-- STORAGE = NEW_GENERIC (construction_works / work_permits cannot hold the
--   work_type / work_subtype / equipment_ref / material_ref / location_ref /
--   attributes / active contract without treating display strings as legal
--   authority).

BEGIN;

CREATE TABLE IF NOT EXISTS public.factory_work_facts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  factory_id uuid NOT NULL REFERENCES public.factories(id),
  work_type text NOT NULL,
  work_subtype text,
  equipment_ref text,
  material_ref text,
  location_ref text,
  attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT factory_work_facts_work_type_chk CHECK (work_type <> ''),
  CONSTRAINT factory_work_facts_attributes_object_chk CHECK (jsonb_typeof(attributes) = 'object')
);

CREATE INDEX IF NOT EXISTS factory_work_facts_factory_id_idx
  ON public.factory_work_facts (factory_id);

CREATE INDEX IF NOT EXISTS factory_work_facts_factory_active_idx
  ON public.factory_work_facts (factory_id)
  WHERE active;

ALTER TABLE public.factory_work_facts ENABLE ROW LEVEL SECURITY;

COMMIT;
