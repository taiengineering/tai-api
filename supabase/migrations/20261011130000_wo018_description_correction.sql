-- =============================================================================
-- Migration: 20261011130000_wo018_description_correction.sql
-- WO-018 P0: Atomic description correction + approval hash re-sync
--
-- For each of 138 PUBLISHED forms (lang='ko'):
--   1. Archive old approval (is_current → false)
--   2. UPDATE reference_form_content.description (trigger auto-recomputes content_hash)
--   3. INSERT new APPROVED approval with new content_hash + same approved_file_hashes
--   4. UPDATE reference_form_sources.source_name
--   5. INSERT audit event
-- VERIFY: public_view COUNT = 138 before COMMIT
--
-- Actor: owner-approved-2026-10-11 / WO-018
-- =============================================================================

DO $$
DECLARE
    v_row            RECORD;
    v_new_desc       TEXT;
    v_new_hash       TEXT;
    v_count          INTEGER := 0;
    v_view_count     INTEGER;
    v_actor          CONSTANT TEXT := 'owner-approved-2026-10-11';
BEGIN
    FOR v_row IN
        SELECT
            rf.id            AS form_id,
            rfc.id           AS content_id,
            rfc.title,
            rfc.description  AS old_description,
            rfc.content_hash AS old_hash,
            ra.id            AS approval_id,
            ra.approved_file_hashes
        FROM public.reference_forms rf
        JOIN public.reference_form_content rfc
            ON rfc.form_id = rf.id AND rfc.lang = 'ko'
        JOIN public.reference_form_approvals ra
            ON ra.form_id = rf.id
           AND ra.is_current = true
           AND ra.approval_status = 'APPROVED'
        WHERE rf.status = 'PUBLISHED'
        ORDER BY rfc.canonical_slug
    LOOP
        -- Build canonical description
        v_new_desc := 'TAI 엔지니어링이 제작한 ''' || v_row.title
                      || ''' 참고서식입니다. 사업장 상황에 맞게 내용을 확인하고 수정하여 활용하세요.';

        -- Step 1: Archive old approval BEFORE description change
        --         (prevents duplicate on uq_approvals_current_approved)
        UPDATE public.reference_form_approvals
           SET is_current = false
         WHERE id = v_row.approval_id;

        -- Step 2: Update description; fn_reference_form_content_hash trigger fires here
        UPDATE public.reference_form_content
           SET description = v_new_desc,
               updated_at  = now()
         WHERE id = v_row.content_id;

        -- Step 3: Read new auto-computed content_hash
        SELECT content_hash INTO v_new_hash
          FROM public.reference_form_content
         WHERE id = v_row.content_id;

        -- Step 4: Insert new current APPROVED approval with updated hash
        INSERT INTO public.reference_form_approvals (
            form_id,
            approval_status,
            approved_content_hash,
            approved_file_hashes,
            is_current,
            approved_at,
            approved_by
        ) VALUES (
            v_row.form_id,
            'APPROVED',
            v_new_hash,
            v_row.approved_file_hashes,
            true,
            now(),
            v_actor
        );

        -- Step 5: Correct source_name on all active sources
        UPDATE public.reference_form_sources
           SET source_name = 'TAI 엔지니어링 (자체 제작)'
         WHERE form_id = v_row.form_id
           AND is_active = true;

        -- Step 6: Immutable audit event
        INSERT INTO public.reference_form_events (
            form_id,
            event_type,
            actor,
            payload
        ) VALUES (
            v_row.form_id,
            'DESCRIPTION_CORRECTED',
            v_actor,
            jsonb_build_object(
                'wo',                'WO-018',
                'old_hash',          v_row.old_hash,
                'new_hash',          v_new_hash,
                'old_desc_len',      length(COALESCE(v_row.old_description, '')),
                'owner_approved_at', '2026-10-11'
            )
        );

        v_count := v_count + 1;
    END LOOP;

    -- Gate A: processed count must be exactly 138
    IF v_count <> 138 THEN
        RAISE EXCEPTION
            'WO-018 P0 GATE_A FAILED: processed % forms, expected 138. ROLLBACK.',
            v_count;
    END IF;

    -- Gate B: public_view must still expose 138 rows (content_hash = approved_content_hash)
    SELECT COUNT(*) INTO v_view_count FROM public.reference_form_public_view;
    IF v_view_count <> 138 THEN
        RAISE EXCEPTION
            'WO-018 P0 GATE_B FAILED: public_view has % rows (expected 138). ROLLBACK.',
            v_view_count;
    END IF;

    RAISE NOTICE 'WO-018 P0 PASS: forms_updated=%, public_view=%. COMMIT.',
        v_count, v_view_count;
END;
$$;
