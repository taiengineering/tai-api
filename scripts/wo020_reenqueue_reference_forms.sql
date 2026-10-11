-- WO-020: Re-enqueue 138 published reference forms after REFERENCE_FORM adapter registration.
--
-- Run via Supabase SQL editor (tai-api project) AFTER tai-api deploy completes.
-- ON CONFLICT (event_key) DO NOTHING — safe to re-run.

SELECT
    public.enqueue_search_index_sync(
        'REFERENCE_FORM',
        'REFERENCE_FORM',
        v.id::TEXT,
        'REFERENCE_FORM:' || v.id::TEXT || ':WO-020-ADAPTER-REGISTERED',
        'WO-020: REFERENCE_FORM adapter registered — initial index for ' || v.canonical_slug
    )
FROM public.reference_form_public_view v
ORDER BY v.id;
