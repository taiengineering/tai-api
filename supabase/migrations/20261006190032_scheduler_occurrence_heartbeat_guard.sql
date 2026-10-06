-- WP-1C-B2-A: Scheduler occurrence heartbeat RPC + security hardening.
--
-- 1. New: tai_scheduler_heartbeat_occurrence — renew lease on a RUNNING occurrence.
--    Identity fence: log_id + job_code + scheduled_for + attempt_no + status=RUNNING
--    + lease_until IS NOT NULL AND > p_now.  Returns false on any mismatch.
-- 2. Harden tai_scheduler_claim_occurrence: SECURITY DEFINER → SECURITY INVOKER,
--    revoke PUBLIC/anon/authenticated.
-- 3. Harden tai_scheduler_complete_occurrence: same hardening.

-- ─── 1. New heartbeat RPC ────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public.tai_scheduler_heartbeat_occurrence(
    p_job_code      text,
    p_scheduled_for timestamptz,
    p_log_id        uuid,
    p_attempt_no    integer,
    p_now           timestamptz,
    p_lease         interval
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
    IF p_lease IS NULL OR p_lease <= interval '0' THEN
        RETURN false;
    END IF;

    UPDATE public.cron_job_log
    SET lease_until = p_now + p_lease
    WHERE id            = p_log_id
      AND job_code      = p_job_code
      AND scheduled_for = p_scheduled_for
      AND attempt_no    = p_attempt_no
      AND status        = 'RUNNING'
      AND lease_until   IS NOT NULL
      AND lease_until   > p_now;

    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count > 0;
END;
$fn$;

REVOKE ALL ON FUNCTION public.tai_scheduler_heartbeat_occurrence(text, timestamptz, uuid, integer, timestamptz, interval)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.tai_scheduler_heartbeat_occurrence(text, timestamptz, uuid, integer, timestamptz, interval)
    TO service_role;

-- ─── 2. Harden claim: SECURITY DEFINER → SECURITY INVOKER ───────────────────

CREATE OR REPLACE FUNCTION public.tai_scheduler_claim_occurrence(
    p_job_code      text,
    p_scheduled_for timestamptz,
    p_now           timestamptz,
    p_lease         interval,
    p_trace_id      text
)
RETURNS TABLE (log_id uuid, attempt_no integer, trace_id text)
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
SET search_path = public, pg_temp
AS $fn$
DECLARE
    v_id      uuid;
    v_attempt integer;
    v_trace   text;
BEGIN
    INSERT INTO public.cron_job_log (
        job_code,
        scheduled_for,
        status,
        attempt_no,
        lease_until,
        triggered_by,
        trace_id
    ) VALUES (
        p_job_code,
        p_scheduled_for,
        'RUNNING',
        1,
        p_now + p_lease,
        'SCHEDULE',
        p_trace_id
    )
    ON CONFLICT (job_code, scheduled_for) WHERE scheduled_for IS NOT NULL
    DO NOTHING
    RETURNING id, cron_job_log.attempt_no, cron_job_log.trace_id INTO v_id, v_attempt, v_trace;

    IF v_id IS NOT NULL THEN
        log_id     := v_id;
        attempt_no := v_attempt;
        trace_id   := v_trace;
        RETURN NEXT;
        RETURN;
    END IF;

    UPDATE public.cron_job_log
    SET
        attempt_no  = cron_job_log.attempt_no + 1,
        lease_until = p_now + p_lease,
        status      = 'RUNNING'
    WHERE job_code      = p_job_code
      AND scheduled_for = p_scheduled_for
      AND status        = 'RUNNING'
      AND lease_until   <= p_now
    RETURNING id, cron_job_log.attempt_no, cron_job_log.trace_id INTO v_id, v_attempt, v_trace;

    IF v_id IS NOT NULL THEN
        log_id     := v_id;
        attempt_no := v_attempt;
        trace_id   := v_trace;
        RETURN NEXT;
    END IF;
    RETURN;
END;
$fn$;

REVOKE ALL ON FUNCTION public.tai_scheduler_claim_occurrence(text, timestamptz, timestamptz, interval, text)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.tai_scheduler_claim_occurrence(text, timestamptz, timestamptz, interval, text)
    TO service_role;

-- ─── 3. Harden complete: SECURITY DEFINER → SECURITY INVOKER ────────────────

CREATE OR REPLACE FUNCTION public.tai_scheduler_complete_occurrence(
    p_job_code      text,
    p_scheduled_for timestamptz,
    p_log_id        uuid,
    p_attempt_no    integer,
    p_status        text,
    p_detail        jsonb,
    p_finished_at   timestamptz,
    p_next_run_at   timestamptz
)
RETURNS boolean
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
SET search_path = public, pg_temp
AS $fn$
DECLARE
    v_updated integer;
BEGIN
    UPDATE public.cron_job_log
    SET
        status        = p_status,
        finished_at   = p_finished_at,
        result_detail = p_detail
    WHERE id         = p_log_id
      AND attempt_no = p_attempt_no
      AND status     = 'RUNNING';

    GET DIAGNOSTICS v_updated = ROW_COUNT;
    IF v_updated = 0 THEN
        RETURN true;
    END IF;

    UPDATE public.cron_schedule_config
    SET
        next_run_at = p_next_run_at,
        last_run_at = p_finished_at,
        last_status = p_status
    WHERE job_code = p_job_code;

    RETURN false;
END;
$fn$;

REVOKE ALL ON FUNCTION public.tai_scheduler_complete_occurrence(text, timestamptz, uuid, integer, text, jsonb, timestamptz, timestamptz)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.tai_scheduler_complete_occurrence(text, timestamptz, uuid, integer, text, jsonb, timestamptz, timestamptz)
    TO service_role;
