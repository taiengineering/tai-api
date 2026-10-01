-- WO-COMM-V3-RECURRING-SCHEDULER-TRIGGER-001
-- UP: Register SaaS recurring billing scheduler job.
-- CRITICAL initial state: is_active=false, dry_run=true, cron disabled.
-- No Production apply in this WO. No pg_cron.
-- Artifact is idempotent via ON CONFLICT DO NOTHING.

INSERT INTO cron_job_master (
    job_code,
    job_name,
    category,
    endpoint_url,
    http_method,
    cron_expression,
    timeout_seconds,
    is_system,
    is_active,
    request_payload,
    cron_schedule_config,
    created_at,
    updated_at
)
VALUES (
    'SAAS_RECURRING_BILLING',
    'SaaS 정기결제 due 처리',
    'PAYMENT',
    'direct://saas_recurring_billing',
    'DIRECT',
    '0 * * * *',
    900,
    true,
    false,
    '{"dry_run": true, "limit": 20}'::jsonb,
    '{"is_enabled": false}'::jsonb,
    NOW(),
    NOW()
)
ON CONFLICT (job_code) DO NOTHING;
