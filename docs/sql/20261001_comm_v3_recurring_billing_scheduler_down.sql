-- WO-COMM-V3-RECURRING-SCHEDULER-TRIGGER-001
-- DOWN: Remove SaaS recurring billing scheduler job.
-- Only removes the job registered by the UP migration.
-- Does not touch pg_cron. Idempotent.

DELETE FROM cron_job_master
WHERE job_code = 'SAAS_RECURRING_BILLING';
