-- WO-MSDS-04B-PATCH-001: Photo + OCR intake support (corrected)
-- Adds sequence_no, is_primary with DB-enforced contracts. No PHOTO_DERIVED type.
-- Derived PDF from photos uses artifact_type='PDF' / is_primary=true / sequence_no IS NULL.
-- TARGET DB: TAI SaaS (vwlahtguyggrhvslabax) — NOT leg-prod

ALTER TABLE public.msds_intake_artifacts
    ADD COLUMN IF NOT EXISTS sequence_no integer,
    ADD COLUMN IF NOT EXISTS is_primary boolean NOT NULL DEFAULT false;

-- sequence_no must be positive when present
ALTER TABLE public.msds_intake_artifacts
    ADD CONSTRAINT chk_mia_sequence_positive
        CHECK (sequence_no IS NULL OR sequence_no > 0);

-- PHOTO artifacts must have a sequence_no and must not be primary
ALTER TABLE public.msds_intake_artifacts
    ADD CONSTRAINT chk_mia_photo_contract
        CHECK (
            artifact_type != 'PHOTO'
            OR (sequence_no IS NOT NULL AND is_primary = false)
        );

-- PDF artifacts must NOT have a sequence_no
ALTER TABLE public.msds_intake_artifacts
    ADD CONSTRAINT chk_mia_pdf_contract
        CHECK (
            artifact_type != 'PDF'
            OR sequence_no IS NULL
        );

-- artifact_type stays PDF | PHOTO only (no PHOTO_DERIVED)
ALTER TABLE public.msds_intake_artifacts
    DROP CONSTRAINT IF EXISTS chk_mia_type;
ALTER TABLE public.msds_intake_artifacts
    ADD CONSTRAINT chk_mia_type CHECK (artifact_type IN ('PDF', 'PHOTO'));

-- Exactly one primary artifact per intake
CREATE UNIQUE INDEX IF NOT EXISTS uq_mia_one_primary
    ON public.msds_intake_artifacts (intake_id)
    WHERE is_primary = true;

-- PHOTO sequence_no unique per intake
CREATE UNIQUE INDEX IF NOT EXISTS uq_mia_photo_seq
    ON public.msds_intake_artifacts (intake_id, sequence_no)
    WHERE artifact_type = 'PHOTO' AND sequence_no IS NOT NULL;
