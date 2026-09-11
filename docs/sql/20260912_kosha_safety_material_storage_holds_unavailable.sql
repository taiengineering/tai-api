-- WO-SAFETY-LIBRARY-001 WP-1C-5B PATCH-5B-BINARY-UNAVAILABLE
-- Additive CHECK allowlist only. Do not rewrite existing hold rows.
-- Do not recreate kosha_safety_material_storage_holds.

ALTER TABLE public.kosha_safety_material_storage_holds
    DROP CONSTRAINT IF EXISTS kosha_safety_material_storage_holds_reason_check;

ALTER TABLE public.kosha_safety_material_storage_holds
    ADD CONSTRAINT kosha_safety_material_storage_holds_reason_check
    CHECK (reason IN (
        'SOURCE_ASSET_FILENAME_MISMATCH',
        'SOURCE_ASSET_ZERO_MATCH',
        'SOURCE_ASSET_MULTI_MATCH',
        'SOURCE_ASSET_OVERSIZE_POLICY',
        'SOURCE_BINARY_UNAVAILABLE'
    ));
