-- WO-SAFETY-LIBRARY-001 WP-1C-5A
-- Atomic current-version promotion. Additive function only.
-- Do not recreate kosha_safety_material_asset_versions.
-- Do not mutate existing rows. DDL only.

CREATE OR REPLACE FUNCTION public.promote_kosha_safety_material_asset_version(
  p_asset_id bigint,
  p_material_id text,
  p_source_asset_key text,
  p_content_checksum text,
  p_storage_provider text,
  p_storage_bucket text,
  p_storage_key text,
  p_source_file_name text,
  p_source_content_type text,
  p_source_file_size bigint,
  p_source_fetched_at timestamptz,
  p_is_derivative boolean,
  p_license_observed_at timestamptz,
  p_license_observed_type text,
  p_license_name text,
  p_license_source_url text,
  p_storage_basis text,
  p_source_med_seq text,
  p_source_url text,
  p_med_gonggongnuri_raw text,
  p_med_gonggongnuri_nm_raw text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $fn$
DECLARE
  v_current public.kosha_safety_material_asset_versions%ROWTYPE;
  v_prev public.kosha_safety_material_asset_versions%ROWTYPE;
  v_new_id bigint;
BEGIN
  IF p_is_derivative IS TRUE THEN
    RAISE EXCEPTION 'DERIVATIVE_FORBIDDEN';
  END IF;

  PERFORM pg_advisory_xact_lock(hashtextextended(p_source_asset_key, 0));

  SELECT * INTO v_current
  FROM public.kosha_safety_material_asset_versions
  WHERE source_asset_key = p_source_asset_key
    AND is_current_version = true
  FOR UPDATE;

  IF FOUND AND v_current.content_checksum = p_content_checksum THEN
    RETURN jsonb_build_object(
      'status', 'NO_CHANGE',
      'id', v_current.id,
      'dml', 0
    );
  END IF;

  SELECT * INTO v_prev
  FROM public.kosha_safety_material_asset_versions
  WHERE source_asset_key = p_source_asset_key
    AND content_checksum = p_content_checksum
  FOR UPDATE;

  IF FOUND THEN
    IF v_current.id IS NOT NULL THEN
      UPDATE public.kosha_safety_material_asset_versions
      SET is_current_version = false
      WHERE id = v_current.id;
    END IF;
    UPDATE public.kosha_safety_material_asset_versions
    SET is_current_version = true
    WHERE id = v_prev.id;
    RETURN jsonb_build_object(
      'status', 'PROMOTED_EXISTING_VERSION',
      'id', v_prev.id,
      'dml', CASE WHEN v_current.id IS NOT NULL THEN 2 ELSE 1 END
    );
  END IF;

  IF v_current.id IS NOT NULL THEN
    UPDATE public.kosha_safety_material_asset_versions
    SET is_current_version = false
    WHERE id = v_current.id;
  END IF;

  INSERT INTO public.kosha_safety_material_asset_versions (
    asset_id, material_id, source_asset_key, content_checksum,
    storage_provider, storage_bucket, storage_key,
    source_file_name, source_content_type, source_file_size,
    source_fetched_at, is_current_version, is_derivative,
    license_observed_at, license_observed_type, license_name, license_source_url,
    storage_basis, source_med_seq, source_url,
    med_gonggongnuri_raw, med_gonggongnuri_nm_raw
  ) VALUES (
    p_asset_id, p_material_id, p_source_asset_key, p_content_checksum,
    p_storage_provider, p_storage_bucket, p_storage_key,
    p_source_file_name, p_source_content_type, p_source_file_size,
    p_source_fetched_at, true, false,
    p_license_observed_at, p_license_observed_type, p_license_name, p_license_source_url,
    p_storage_basis, p_source_med_seq, p_source_url,
    p_med_gonggongnuri_raw, p_med_gonggongnuri_nm_raw
  )
  RETURNING id INTO v_new_id;

  RETURN jsonb_build_object(
    'status', 'NEW_VERSION',
    'id', v_new_id,
    'dml', CASE WHEN v_current.id IS NOT NULL THEN 2 ELSE 1 END
  );
END;
$fn$;

REVOKE ALL ON FUNCTION public.promote_kosha_safety_material_asset_version(
  bigint, text, text, text, text, text, text, text, text, bigint, timestamptz,
  boolean, timestamptz, text, text, text, text, text, text, text, text
) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.promote_kosha_safety_material_asset_version(
  bigint, text, text, text, text, text, text, text, text, bigint, timestamptz,
  boolean, timestamptz, text, text, text, text, text, text, text, text
) FROM anon;
REVOKE ALL ON FUNCTION public.promote_kosha_safety_material_asset_version(
  bigint, text, text, text, text, text, text, text, text, bigint, timestamptz,
  boolean, timestamptz, text, text, text, text, text, text, text, text
) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.promote_kosha_safety_material_asset_version(
  bigint, text, text, text, text, text, text, text, text, bigint, timestamptz,
  boolean, timestamptz, text, text, text, text, text, text, text, text
) TO postgres, service_role;
