-- TAI pg_cron retirement. EXECUTE = 0. DELETE/unschedule 금지. schedule/command 원문 보존.
-- cron.alter_job(job_id, schedule, command, database, username, active)
SELECT cron.alter_job(1, NULL, NULL, NULL, NULL, false);
SELECT cron.alter_job(2, NULL, NULL, NULL, NULL, false);
SELECT cron.alter_job(3, NULL, NULL, NULL, NULL, false);
SELECT cron.alter_job(4, NULL, NULL, NULL, NULL, false);
SELECT cron.alter_job(5, NULL, NULL, NULL, NULL, false);
SELECT cron.alter_job(6, NULL, NULL, NULL, NULL, false);
SELECT cron.alter_job(7, NULL, NULL, NULL, NULL, false);
SELECT cron.alter_job(8, NULL, NULL, NULL, NULL, false);
SELECT cron.alter_job(9, NULL, NULL, NULL, NULL, false);
SELECT cron.alter_job(10, NULL, NULL, NULL, NULL, false);
SELECT cron.alter_job(11, NULL, NULL, NULL, NULL, false);
SELECT cron.alter_job(12, NULL, NULL, NULL, NULL, false);
