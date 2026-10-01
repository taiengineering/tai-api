-- WO-COMM-V3-RECURRING-SCHEDULER-TRIGGER-PATCH-001 / PATCH-A
-- UP: Register SaaS recurring billing scheduler job (two-table registration).
-- cron_schedule_config is a SEPARATE TABLE — NOT a column in cron_job_master.
-- CRITICAL initial state: master.is_active=false, config.is_enabled=false.
-- Authoritative execution lock: cron_job_master.is_active (DbStore.refresh uses this).
-- No Production apply in this WO. Uses cron_job_master + cron_schedule_config only.
-- Idempotent via ON CONFLICT DO NOTHING on both tables.

-- Step 1: master row
INSERT INTO public.cron_job_master (
    job_code,
    job_name,
    job_description,
    category,
    endpoint_url,
    http_method,
    cron_expression,
    schedule_desc,
    request_payload,
    timeout_seconds,
    is_system,
    is_active,
    notify_on_fail
)
VALUES (
    'SAAS_RECURRING_BILLING',
    'SaaS 정기결제 due 처리',
    'SaaS 구독 next_billing_at <= now 도달 시 정기결제 실행 (DB-backed KST scheduler)',
    'PAYMENT',
    'direct://saas_recurring_billing',
    'DIRECT',
    '0 * * * *',
    '매시 정각',
    '{"dry_run": true, "limit": 20}'::jsonb,
    900,
    true,
    false,
    true
)
ON CONFLICT (job_code) DO NOTHING;

-- Step 2: schedule config row (job_id via SELECT — idempotent guard on job_code)
INSERT INTO public.cron_schedule_config (
    job_id,
    job_code,
    cron_expression,
    is_enabled,
    next_run_at
)
SELECT
    id,
    job_code,
    cron_expression,
    false,
    NULL
FROM public.cron_job_master
WHERE job_code = 'SAAS_RECURRING_BILLING'
ON CONFLICT (job_code) DO NOTHING;
