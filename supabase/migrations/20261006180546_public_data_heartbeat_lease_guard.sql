-- WP-1C-B1: Add lease_until > p_now guard to fn_public_data_heartbeat_run.
--
-- The original function (20261006131519) omits a lease_until > p_now check,
-- which allows a heartbeat to revive an expired lease — defeating the stale-run
-- recovery mechanism in fn_public_data_claim_run.
-- This corrective migration replaces the function with the guarded version.

CREATE OR REPLACE FUNCTION public.fn_public_data_heartbeat_run(
    p_run_id        uuid,
    p_now           timestamptz,
    p_lease_seconds integer
)
RETURNS boolean
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
SET search_path = public, pg_temp
AS $fn$
DECLARE
    v_count integer;
BEGIN
    UPDATE public.public_data_sync_runs r
    SET heartbeat_at = p_now,
        lease_until  = p_now + (p_lease_seconds * interval '1 second')
    WHERE r.id            = p_run_id
      AND r.status        = 'RUNNING'
      AND r.lease_until   IS NOT NULL
      AND r.lease_until   > p_now
      AND EXISTS (
          SELECT 1 FROM public.public_data_source_runtime rt
          WHERE rt.source_id      = r.source_id
            AND rt.current_run_id = p_run_id
      );

    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count > 0;
END;
$fn$;

REVOKE ALL ON FUNCTION public.fn_public_data_heartbeat_run(uuid, timestamptz, integer)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_public_data_heartbeat_run(uuid, timestamptz, integer)
    TO service_role;
