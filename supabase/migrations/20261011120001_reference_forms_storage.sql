-- =============================================================================
-- Migration: 20261011120001_reference_forms_storage.sql
-- Reference Forms CMS — Supabase Storage bucket definitions.
--
-- The DO block self-skips on plain PostgreSQL (storage.buckets absent).
-- On Supabase, storage.buckets exists and the INSERT executes.
-- Apply after OBJ-REF-08 QA + Owner authorization.
--
-- Buckets:
--   reference-forms         private, 20 MB, PDF/DOCX/XLSX/HWP/HWPX
--   reference-forms-preview private, 10 MB, PNG/JPEG/WEBP/PDF
-- =============================================================================

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'storage' AND table_name = 'buckets'
    ) THEN
        INSERT INTO storage.buckets
            (id, name, public, file_size_limit, allowed_mime_types)
        VALUES
            (
                'reference-forms',
                'reference-forms',
                false,
                20971520,
                ARRAY[
                    'application/pdf',
                    'application/msword',
                    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    'application/vnd.ms-excel',
                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    'application/x-hwp',
                    'application/haansofthwp',
                    'application/haansofthwpx'
                ]
            ),
            (
                'reference-forms-preview',
                'reference-forms-preview',
                false,
                10485760,
                ARRAY[
                    'image/png',
                    'image/jpeg',
                    'image/webp',
                    'application/pdf'
                ]
            )
        ON CONFLICT (id) DO NOTHING;
    END IF;
END;
$$;
