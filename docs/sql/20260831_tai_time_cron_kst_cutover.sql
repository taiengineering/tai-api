-- TAI TIME PHASE 2 STEP D artifact.
-- EXECUTE = 0. Do not run against TAI Supabase vwlahtguyggrhvslabax.
-- cron.alter_job(job_id, schedule, command, database, username, active)
-- NULL args preserve the existing value. jobid 1–12 each once.
-- active EXACT preserved: jobs 1, 3, 4 inactive; others active.

SELECT cron.alter_job(1, '10 9 * * *', NULL, NULL, NULL, false);
SELECT cron.alter_job(2, '0 9 * * *', NULL, NULL, NULL, true);
SELECT cron.alter_job(3, NULL, NULL, NULL, NULL, false);
SELECT cron.alter_job(4, NULL, NULL, NULL, NULL, false);
SELECT cron.alter_job(5, '0 6 * * *', NULL, NULL, NULL, true);
SELECT cron.alter_job(6, '0 12 * * *', NULL, NULL, NULL, true);
SELECT cron.alter_job(7, '0 18 * * *', NULL, NULL, NULL, true);
SELECT cron.alter_job(8, '0 2 * * *', NULL, NULL, NULL, true);
SELECT cron.alter_job(9, '0 3 * * 1', NULL, NULL, NULL, true);
SELECT cron.alter_job(10, '0 12 * * *', NULL, NULL, NULL, true);
-- job 11: schedule unchanged; command localtimestamp → now()
SELECT cron.alter_job(11, NULL, $job11$WITH victims AS MATERIALIZED (SELECT id FROM public.cron_job_log WHERE started_at < now() - interval '30 days' ORDER BY started_at ASC, id ASC LIMIT 5000) DELETE FROM public.cron_job_log AS l USING victims AS v WHERE l.id = v.id;$job11$, NULL, NULL, true);
-- job 12: schedule KST 03:27; command unchanged
SELECT cron.alter_job(12, '27 3 * * *', $job12$WITH victims AS MATERIALIZED (SELECT id FROM public.business_event WHERE created_at < now() - interval '90 days' ORDER BY created_at ASC, id ASC LIMIT 5000) DELETE FROM public.business_event AS b USING victims AS v WHERE b.id = v.id;$job12$, NULL, NULL, true);
