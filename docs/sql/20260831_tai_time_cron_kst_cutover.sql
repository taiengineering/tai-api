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
-- job 11 schedule unchanged. Full live command body was not attached to Cursor.
-- Required predicate after cutover (localtimestamp removed):
--   started_at < now() - interval '30 days'
SELECT cron.alter_job(11, NULL, NULL, NULL, NULL, true);
-- job 12 schedule KST 03:27; command unchanged:
--   created_at < now() - interval '90 days'
SELECT cron.alter_job(12, '27 3 * * *', NULL, NULL, NULL, true);
