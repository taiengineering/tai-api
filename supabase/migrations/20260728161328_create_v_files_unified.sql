-- WO-9: 파일·자산 통합뷰 (Goal G-ms4je4z3-33eada)
-- documents + company_files + generated_document(factory→company)를 company_id 기준 통합.
-- 읽기 전용. 공통 컬럼으로 정규화. 격리 자산(document_engine) 제외.
CREATE OR REPLACE VIEW public.v_files_unified AS
SELECT
    d.id::text            AS id,
    'documents'           AS source,
    d.company_id          AS company_id,
    d.factory_id          AS factory_id,
    d.file_name           AS file_name,
    COALESCE(d.storage_path, '') AS file_ref,
    d.category            AS category,
    CASE WHEN d.deleted_at IS NOT NULL THEN 'DELETED'
         WHEN d.is_active = false THEN 'INACTIVE'
         ELSE 'ACTIVE' END AS status,
    d.file_size           AS file_size,
    d.uploaded_at         AS created_at
FROM public.documents d

UNION ALL
SELECT
    cf.id::text,
    'company_files',
    cf.company_id,
    NULL::uuid,
    cf.file_name,
    COALESCE(cf.file_url, ''),
    cf.file_type,
    CASE WHEN cf.is_active = false THEN 'INACTIVE' ELSE 'ACTIVE' END,
    cf.file_size,
    cf.uploaded_at
FROM public.company_files cf

UNION ALL
SELECT
    gd.id::text,
    'generated_document',
    f.company_id,
    gd.factory_id,
    gd.document_name,
    COALESCE(gd.download_url, gd.storage_path, ''),
    gd.form_code,
    gd.status,
    NULL::bigint,
    gd.created_at
FROM public.generated_document gd
LEFT JOIN public.factories f ON f.id = gd.factory_id;

COMMENT ON VIEW public.v_files_unified IS 'WO-9 파일 통합뷰: documents+company_files+generated_document(factory→company). 읽기 전용, company_id 축.';