-- =============================================================================
-- Migration: 20261011120001_reference_forms_storage.sql
-- Supabase Storage bucket definitions for Reference Forms CMS.
--
-- NOT applied in isolated PostgreSQL tests (storage.buckets is Supabase-only).
-- Apply separately in Supabase dashboard / supabase db push after
-- OBJ-REF-08 QA + Owner authorization.
--
-- Buckets:
--   reference-forms         private, 20 MB, PDF/DOCX/XLSX/HWP/HWPX
--   reference-forms-preview private, 10 MB, PNG/JPEG/WEBP/PDF
-- =============================================================================

/*
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
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
*/
