-- WO-E2E-OBS009-COMMON-MATERIAL-SOURCE-IMPLEMENT-001
-- Common Material Source storage. Family-specific tables = 0.
-- PRODUCTION DB APPLY = 0. File is deploy-ready and idempotent.
-- MATERIAL MASTER INSERT = 0. Authoritative rows stay in git manifests until a
-- later apply. factory_materials is reused as the factory ↔ master link object.

BEGIN;

CREATE TABLE IF NOT EXISTS public.material_legal_master (
  material_key text PRIMARY KEY,
  display_name text NOT NULL,
  cas_no text,
  source_system text NOT NULL,
  source_item_key text NOT NULL,
  source_ref text NOT NULL,
  source_version text,
  source_effective_date date,
  source_hash text,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT material_legal_master_key_chk CHECK (material_key <> ''),
  CONSTRAINT material_legal_master_source_system_chk CHECK (source_system <> '')
);

CREATE TABLE IF NOT EXISTS public.material_legal_classifications (
  material_key text NOT NULL
    REFERENCES public.material_legal_master(material_key),
  classification_code text NOT NULL,
  source_ref text NOT NULL,
  source_version text,
  source_hash text,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (material_key, classification_code),
  CONSTRAINT material_legal_classifications_code_chk CHECK (
    classification_code IN (
      'MANAGED_HAZARDOUS_SUBSTANCE',
      'PERMIT_REQUIRED_HAZARDOUS_SUBSTANCE',
      'SPECIAL_MANAGEMENT_SUBSTANCE'
    )
  )
);

CREATE INDEX IF NOT EXISTS material_legal_classifications_code_idx
  ON public.material_legal_classifications (classification_code)
  WHERE active;

ALTER TABLE public.factory_materials
  ADD COLUMN IF NOT EXISTS material_master_key text;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'factory_materials_material_master_key_fkey'
  ) THEN
    ALTER TABLE public.factory_materials
      ADD CONSTRAINT factory_materials_material_master_key_fkey
      FOREIGN KEY (material_master_key)
      REFERENCES public.material_legal_master(material_key);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS factory_materials_master_key_idx
  ON public.factory_materials (material_master_key)
  WHERE material_master_key IS NOT NULL;

COMMENT ON TABLE public.material_legal_master IS
  'OBS009 Common Material Source: source-identity master. material_key is not material_name.';
COMMENT ON TABLE public.material_legal_classifications IS
  'OBS009 Common Material Source: exact legal classifications from ingested law corpus only.';
COMMENT ON COLUMN public.factory_materials.material_master_key IS
  'Nullable reference to material_legal_master.material_key. Free-text material_name without this key is ABSENT classification, not false.';

ALTER TABLE public.material_legal_master ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.material_legal_classifications ENABLE ROW LEVEL SECURITY;

COMMIT;
