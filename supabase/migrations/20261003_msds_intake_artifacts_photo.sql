-- WO-MSDS-04B-IMPLEMENTATION-001: Photo + OCR intake support
-- Add sequence_no, is_primary to msds_intake_artifacts; expand artifact_type
-- TARGET DB: TAI SaaS (vwlahtguyggrhvslabax) — NOT leg-prod

ALTER TABLE public.msds_intake_artifacts
    ADD COLUMN IF NOT EXISTS sequence_no integer,
    ADD COLUMN IF NOT EXISTS is_primary boolean NOT NULL DEFAULT false;

-- Expand artifact_type to include PHOTO_DERIVED (derived PDF from ordered photos)
ALTER TABLE public.msds_intake_artifacts
    DROP CONSTRAINT IF EXISTS chk_mia_type;
ALTER TABLE public.msds_intake_artifacts
    ADD CONSTRAINT chk_mia_type CHECK (artifact_type IN ('PDF','PHOTO','PHOTO_DERIVED'));
