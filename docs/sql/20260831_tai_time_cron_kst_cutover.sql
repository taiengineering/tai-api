-- TAI TIME PHASE 2 STEP D artifact.
-- EXECUTE = 0. Do not run against TAI Supabase vwlahtguyggrhvslabax.
-- cron.alter_job(job_id, schedule, command, database, username, active)
-- NULL / omitted args preserve existing command, database, username, active.

-- schedule map (KST wall-clock after postmaster cron.timezone cutover)
SELECT cron.alter_job(1, '10 9 * * *');
SELECT cron.alter_job(2, '0 9 * * *');
SELECT cron.alter_job(5, '0 6 * * *');
SELECT cron.alter_job(6, '0 12 * * *');
SELECT cron.alter_job(7, '0 18 * * *');
SELECT cron.alter_job(8, '0 2 * * *');
SELECT cron.alter_job(9, '0 3 * * 1');
SELECT cron.alter_job(10, '0 12 * * *');
SELECT cron.alter_job(12, '27 3 * * *');

-- jobs 3, 4: schedule unchanged — no alter_job for schedule
-- job 11: schedule unchanged; command retention predicate:
--   started_at < now() - interval '30 days'  (localtimestamp removed)
-- Full existing command body is not in this repo; operator must substitute
-- the live cron.job.command with localtimestamp → now() in that predicate only.
-- SELECT cron.alter_job(11, command := '<existing command with now()-30 days>');

-- job 12 command unchanged: created_at < now() - interval '90 days'
-- active state EXACT preserved (not passed → unchanged)
