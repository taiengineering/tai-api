-- =============================================================================
-- Migration: 20261011120002_reference_forms_rpc.sql
-- Description: Reference Forms CMS — RPC functions and public view
-- All functions: SECURITY INVOKER, SET search_path = ''
-- All table references fully qualified (public.*) for empty search_path safety.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- fn_assert_slug_globally_unique
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.fn_assert_slug_globally_unique(
    p_slug      TEXT,
    p_form_id   UUID
)
RETURNS void
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    v_existing_form_id UUID;
BEGIN
    SELECT form_id INTO v_existing_form_id
    FROM public.reference_form_slug_registry
    WHERE slug = p_slug
    LIMIT 1;

    IF FOUND AND v_existing_form_id IS DISTINCT FROM p_form_id THEN
        RAISE EXCEPTION 'SLUG_CONFLICT: slug (%) registered by another form', p_slug;
    END IF;
END;
$$;

-- ---------------------------------------------------------------------------
-- rpc_publish_reference_form
-- p_skip_preview_gate: allows bypassing GATE-6 preview check.
-- Restricted to service_role callers via REVOKE below.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.rpc_publish_reference_form(
    p_form_id           UUID,
    p_actor             TEXT,
    p_payload           JSONB    DEFAULT '{}',
    p_skip_preview_gate BOOLEAN  DEFAULT false
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    v_form              record;
    v_content           record;
    v_approval          record;
    v_file              record;
    v_event_id          BIGINT;
    v_file_count        INT;
    v_preview_count     INT;
    v_approved_entry    JSONB;
    v_approved_sha256   TEXT;
    v_match_found       BOOLEAN;
    v_expected_fid      TEXT;
BEGIN
    -- GATE-1: form must exist and be DRAFT
    SELECT * INTO v_form
    FROM public.reference_forms
    WHERE id = p_form_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'FORM_NOT_FOUND: form % does not exist', p_form_id;
    END IF;

    IF v_form.status != 'DRAFT' THEN
        RAISE EXCEPTION 'GATE1_FAILED: form % status is %, expected DRAFT', p_form_id, v_form.status;
    END IF;

    -- GATE-2: must have a current APPROVED approval
    SELECT * INTO v_approval
    FROM public.reference_form_approvals
    WHERE form_id = p_form_id
      AND is_current = true
      AND approval_status = 'APPROVED'
    LIMIT 1;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'GATE2_FAILED: no current APPROVED approval for form %', p_form_id;
    END IF;

    -- GATE-3: content_hash must match approved_content_hash
    SELECT * INTO v_content
    FROM public.reference_form_content
    WHERE form_id = p_form_id
      AND lang = 'ko'
    LIMIT 1;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'GATE3_FAILED: no content found for form %', p_form_id;
    END IF;

    IF v_content.content_hash IS DISTINCT FROM v_approval.approved_content_hash THEN
        RAISE EXCEPTION 'GATE3_FAILED: content_hash mismatch for form %: current=% approved=%',
            p_form_id, v_content.content_hash, v_approval.approved_content_hash;
    END IF;

    -- GATE-7: must have at least 1 active file (check before GATE-4 loop)
    SELECT COUNT(*) INTO v_file_count
    FROM public.reference_form_files
    WHERE form_id = p_form_id AND is_active = true;

    IF v_file_count = 0 THEN
        RAISE EXCEPTION 'GATE7_FAILED: no active files for form %', p_form_id;
    END IF;

    -- GATE-4 part A: for each active file → qa_status='QA_PASS', approved_at IS NOT NULL,
    -- file is in approved_file_hashes (by file_id), sha256 matches
    FOR v_file IN
        SELECT * FROM public.reference_form_files
        WHERE form_id = p_form_id AND is_active = true
    LOOP
        IF v_file.qa_status != 'QA_PASS' THEN
            RAISE EXCEPTION 'GATE4_FAILED: file % qa_status is %, expected QA_PASS', v_file.id, v_file.qa_status;
        END IF;

        IF v_file.approved_at IS NULL THEN
            RAISE EXCEPTION 'GATE4_FAILED: file % has no approved_at', v_file.id;
        END IF;

        -- Find this file in approved_file_hashes
        v_match_found := false;
        FOR v_approved_entry IN
            SELECT jsonb_array_elements(v_approval.approved_file_hashes)
        LOOP
            IF (v_approved_entry->>'file_id') = v_file.id::text THEN
                v_match_found := true;
                v_approved_sha256 := v_approved_entry->>'sha256';
                EXIT;
            END IF;
        END LOOP;

        IF NOT v_match_found THEN
            RAISE EXCEPTION 'GATE4_FAILED: active file % not found in approved_file_hashes', v_file.id;
        END IF;

        IF v_approved_sha256 IS DISTINCT FROM v_file.sha256 THEN
            RAISE EXCEPTION 'GATE4_FAILED: sha256 mismatch for file %: current=% approved=%',
                v_file.id, v_file.sha256, v_approved_sha256;
        END IF;
    END LOOP;

    -- GATE-4 part B: for each entry in approved_file_hashes → corresponding active file must exist
    FOR v_approved_entry IN
        SELECT jsonb_array_elements(v_approval.approved_file_hashes)
    LOOP
        v_expected_fid := v_approved_entry->>'file_id';

        SELECT COUNT(*) INTO v_file_count
        FROM public.reference_form_files
        WHERE id = v_expected_fid::uuid
          AND form_id = p_form_id
          AND is_active = true;

        IF v_file_count = 0 THEN
            RAISE EXCEPTION 'GATE4_FAILED: approved file_id % is not an active file for form %',
                v_expected_fid, p_form_id;
        END IF;
    END LOOP;

    -- GATE-5: no source with rights_status IN ('REVIEW_REQUIRED','BLOCKED')
    PERFORM 1
    FROM public.reference_form_sources
    WHERE form_id = p_form_id
      AND is_active = true
      AND rights_status IN ('REVIEW_REQUIRED', 'BLOCKED')
    LIMIT 1;

    IF FOUND THEN
        RAISE EXCEPTION 'GATE5_FAILED: form % has sources with uncleared rights', p_form_id;
    END IF;

    -- GATE-6: at least 1 published QA_PASS preview artifact (if not skipped)
    IF NOT p_skip_preview_gate THEN
        SELECT COUNT(*) INTO v_preview_count
        FROM public.reference_form_preview_artifacts
        WHERE form_id = p_form_id
          AND is_published = true
          AND qa_status = 'QA_PASS';

        IF v_preview_count = 0 THEN
            RAISE EXCEPTION 'GATE6_FAILED: no published QA_PASS preview artifacts for form %', p_form_id;
        END IF;
    END IF;

    -- All gates passed — publish
    UPDATE public.reference_forms
    SET status            = 'PUBLISHED',
        published_at      = now(),
        owner_approved    = true,
        owner_approved_at = now()
    WHERE id = p_form_id;

    -- Insert event
    INSERT INTO public.reference_form_events (form_id, event_type, actor, payload)
    VALUES (p_form_id, 'PUBLISHED', p_actor, p_payload)
    RETURNING id INTO v_event_id;

    -- Enqueue search index sync
    PERFORM public.enqueue_search_index_sync(
        'REFERENCE_FORM',
        'REFERENCE_FORM',
        p_form_id::text,
        'reference_form:' || p_form_id::text || ':' || v_event_id::text,
        'PUBLISHED'
    );

    RETURN p_form_id;
END;
$$;

-- ---------------------------------------------------------------------------
-- rpc_unpublish_reference_form
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.rpc_unpublish_reference_form(
    p_form_id   UUID,
    p_actor     TEXT,
    p_reason    TEXT DEFAULT NULL
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    v_form      record;
    v_event_id  BIGINT;
BEGIN
    SELECT * INTO v_form
    FROM public.reference_forms
    WHERE id = p_form_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'FORM_NOT_FOUND: form % does not exist', p_form_id;
    END IF;

    IF v_form.status != 'PUBLISHED' THEN
        RAISE EXCEPTION 'UNPUBLISH_FAILED: form % status is %, expected PUBLISHED', p_form_id, v_form.status;
    END IF;

    UPDATE public.reference_forms
    SET status       = 'DRAFT',
        published_at = NULL
    WHERE id = p_form_id;

    INSERT INTO public.reference_form_events (form_id, event_type, actor, payload)
    VALUES (
        p_form_id,
        'UNPUBLISHED',
        p_actor,
        jsonb_build_object('reason', COALESCE(p_reason, ''))
    )
    RETURNING id INTO v_event_id;

    PERFORM public.enqueue_search_index_sync(
        'REFERENCE_FORM',
        'REFERENCE_FORM',
        p_form_id::text,
        'reference_form:' || p_form_id::text || ':' || v_event_id::text,
        'UNPUBLISHED'
    );

    RETURN p_form_id;
END;
$$;

-- ---------------------------------------------------------------------------
-- rpc_change_slug_reference_form
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.rpc_change_slug_reference_form(
    p_form_id   UUID,
    p_new_slug  TEXT,
    p_actor     TEXT
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    v_content       record;
    v_old_slug      TEXT;
    v_event_id      BIGINT;
    v_rows_inserted INT;
BEGIN
    -- 1. Lock content row and get current slug
    SELECT * INTO v_content
    FROM public.reference_form_content
    WHERE form_id = p_form_id AND lang = 'ko'
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'SLUG_CHANGE_FAILED: no content found for form %', p_form_id;
    END IF;

    v_old_slug := v_content.canonical_slug;

    -- 2a. Validate new slug is different
    IF v_old_slug = p_new_slug THEN
        RAISE EXCEPTION 'SLUG_CHANGE_FAILED: new slug is the same as current slug %', p_new_slug;
    END IF;

    -- 2b. Validate slug format (alphanumeric, hyphens, no leading/trailing hyphens)
    IF p_new_slug !~ '^[a-z0-9][a-z0-9\-]*[a-z0-9]$' AND p_new_slug !~ '^[a-z0-9]$' THEN
        RAISE EXCEPTION 'SLUG_CHANGE_FAILED: invalid slug format %', p_new_slug;
    END IF;

    -- 2c. Ensure new slug was never used by THIS form before (history check)
    PERFORM 1
    FROM public.reference_form_slug_registry
    WHERE slug = p_new_slug
      AND form_id = p_form_id
      AND slug_status = 'HISTORY';

    IF FOUND THEN
        RAISE EXCEPTION 'SLUG_CHANGE_FAILED: slug % was previously used by this form (no reuse)', p_new_slug;
    END IF;

    -- 2d. Ensure no conflict with other forms
    PERFORM public.fn_assert_slug_globally_unique(p_new_slug, p_form_id);

    -- 3. Update registry: old slug CANONICAL → HISTORY
    UPDATE public.reference_form_slug_registry
    SET slug_status = 'HISTORY'
    WHERE slug = v_old_slug AND form_id = p_form_id;

    -- 4. Insert new slug as CANONICAL
    INSERT INTO public.reference_form_slug_registry (slug, form_id, slug_status)
    VALUES (p_new_slug, p_form_id, 'CANONICAL')
    ON CONFLICT DO NOTHING;

    -- 5. Verify insert succeeded
    GET DIAGNOSTICS v_rows_inserted = ROW_COUNT;
    IF v_rows_inserted = 0 THEN
        RAISE EXCEPTION 'SLUG_CHANGE_FAILED: could not register new slug % (conflict)', p_new_slug;
    END IF;

    -- 6. Update reference_form_content (triggers hash recalc via trg_reference_form_content_hash)
    UPDATE public.reference_form_content
    SET canonical_slug = p_new_slug
    WHERE form_id = p_form_id AND lang = 'ko';

    -- 7. Insert slug_history
    INSERT INTO public.reference_form_slug_history (form_id, old_slug, new_slug)
    VALUES (p_form_id, v_old_slug, p_new_slug);

    -- 8. Insert event + enqueue
    INSERT INTO public.reference_form_events (form_id, event_type, actor, payload)
    VALUES (
        p_form_id,
        'SLUG_CHANGED',
        p_actor,
        jsonb_build_object('old_slug', v_old_slug, 'new_slug', p_new_slug)
    )
    RETURNING id INTO v_event_id;

    PERFORM public.enqueue_search_index_sync(
        'REFERENCE_FORM',
        'REFERENCE_FORM',
        p_form_id::text,
        'reference_form:' || p_form_id::text || ':' || v_event_id::text,
        'SLUG_CHANGED'
    );

    RETURN p_form_id;
END;
$$;

-- ---------------------------------------------------------------------------
-- reference_form_public_view
-- file_ref (storage path) is NOT exposed. Only file metadata (id, sha256).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW public.reference_form_public_view
WITH (security_invoker = true)
AS
SELECT
    rf.id,
    rfc.canonical_slug,
    rfc.title,
    rfc.description,
    rf.published_at,
    GREATEST(rf.updated_at, rfc.updated_at)                 AS updated_at,
    ra.id                                                    AS approval_id,
    (rfc.content_hash = ra.approved_content_hash)           AS content_approved,
    COALESCE(
        (
            SELECT jsonb_agg(
                jsonb_build_object(
                    'file_id',     f.id,
                    'sha256',      f.sha256,
                    'approved_at', f.approved_at
                )
                ORDER BY f.created_at
            )
            FROM public.reference_form_files f
            WHERE f.form_id = rf.id
              AND f.is_active = true
              AND f.qa_status = 'QA_PASS'
              AND f.approved_at IS NOT NULL
        ),
        '[]'::JSONB
    )                                                        AS qa_pass_files,
    COALESCE(
        (
            SELECT array_agg(DISTINCT lower(split_part(f2.file_ref, '.', -1))
                             ORDER BY lower(split_part(f2.file_ref, '.', -1)))
            FROM public.reference_form_files f2
            WHERE f2.form_id = rf.id
              AND f2.is_active = true
              AND f2.qa_status = 'QA_PASS'
        ),
        ARRAY[]::TEXT[]
    )                                                        AS formats,
    COALESCE(
        (
            SELECT array_agg(ll.legacy_code ORDER BY ll.legacy_code)
            FROM public.reference_form_legacy_links ll
            WHERE ll.form_id = rf.id
              AND ll.is_active = true
        ),
        ARRAY[]::TEXT[]
    )                                                        AS legacy_codes
FROM public.reference_forms rf
JOIN public.reference_form_content rfc
    ON rfc.form_id = rf.id AND rfc.lang = 'ko'
JOIN public.reference_form_approvals ra
    ON ra.form_id = rf.id
    AND ra.is_current = true
    AND ra.approval_status = 'APPROVED'
WHERE rf.status = 'PUBLISHED'
  AND rfc.content_hash = ra.approved_content_hash;

-- ---------------------------------------------------------------------------
-- REVOKE from untrusted roles (p_skip_preview_gate restricted to service_role)
-- Conditional: roles may not exist in non-Supabase environments.
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE EXECUTE ON FUNCTION public.rpc_publish_reference_form(UUID,TEXT,JSONB,BOOLEAN)   FROM anon;
        REVOKE EXECUTE ON FUNCTION public.rpc_unpublish_reference_form(UUID,TEXT,TEXT)          FROM anon;
        REVOKE EXECUTE ON FUNCTION public.rpc_change_slug_reference_form(UUID,TEXT,TEXT)        FROM anon;
        REVOKE EXECUTE ON FUNCTION public.fn_assert_slug_globally_unique(TEXT,UUID)             FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE EXECUTE ON FUNCTION public.rpc_publish_reference_form(UUID,TEXT,JSONB,BOOLEAN)   FROM authenticated;
        REVOKE EXECUTE ON FUNCTION public.rpc_unpublish_reference_form(UUID,TEXT,TEXT)          FROM authenticated;
        REVOKE EXECUTE ON FUNCTION public.rpc_change_slug_reference_form(UUID,TEXT,TEXT)        FROM authenticated;
        REVOKE EXECUTE ON FUNCTION public.fn_assert_slug_globally_unique(TEXT,UUID)             FROM authenticated;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
        GRANT EXECUTE ON FUNCTION public.rpc_publish_reference_form(UUID,TEXT,JSONB,BOOLEAN)    TO service_role;
        GRANT EXECUTE ON FUNCTION public.rpc_unpublish_reference_form(UUID,TEXT,TEXT)           TO service_role;
        GRANT EXECUTE ON FUNCTION public.rpc_change_slug_reference_form(UUID,TEXT,TEXT)         TO service_role;
        GRANT EXECUTE ON FUNCTION public.fn_assert_slug_globally_unique(TEXT,UUID)              TO service_role;
    END IF;
END;
$$;
