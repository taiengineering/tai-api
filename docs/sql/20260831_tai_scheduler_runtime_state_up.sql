-- TAI scheduler runtime state. EXECUTE = 0. Do not run against TAI Supabase.
-- next_run_at persistence + 1 config per master job + holiday/pgcron master rows + DOW names.

ALTER TABLE public.cron_schedule_config ADD COLUMN IF NOT EXISTS next_run_at timestamptz;
ALTER TABLE public.cron_schedule_config ADD COLUMN IF NOT EXISTS last_run_at timestamptz;
ALTER TABLE public.cron_schedule_config ADD COLUMN IF NOT EXISTS last_status text;
ALTER TABLE public.cron_job_log ADD COLUMN IF NOT EXISTS scheduled_for timestamptz;
ALTER TABLE public.cron_job_log ADD COLUMN IF NOT EXISTS attempt_no integer NOT NULL DEFAULT 1;
ALTER TABLE public.cron_job_log ADD COLUMN IF NOT EXISTS lease_until timestamptz;
ALTER TABLE public.cron_job_log ADD COLUMN IF NOT EXISTS trace_id text;
CREATE UNIQUE INDEX IF NOT EXISTS cron_job_log_occurrence_uidx
  ON public.cron_job_log (job_code, scheduled_for)
  WHERE scheduled_for IS NOT NULL;

-- every existing master job gets a config row (21 currently missing)
INSERT INTO public.cron_schedule_config (job_id, job_code, cron_expression, is_enabled)
SELECT m.id, m.job_code, m.cron_expression, m.is_active
FROM public.cron_job_master m
WHERE NOT EXISTS (SELECT 1 FROM public.cron_schedule_config c WHERE c.job_code = m.job_code);

-- numeric weekday → name (6)
UPDATE public.cron_job_master SET cron_expression = '0 7 * * mon' WHERE job_code = 'SCHEDULE_GENERATE_ALL';
UPDATE public.cron_schedule_config SET cron_expression = '0 7 * * mon' WHERE job_code = 'SCHEDULE_GENERATE_ALL';
UPDATE public.cron_job_master SET cron_expression = '0 5 * * mon' WHERE job_code = 'PRECEDENT_COLLECT_WEEKLY';
UPDATE public.cron_schedule_config SET cron_expression = '0 5 * * mon' WHERE job_code = 'PRECEDENT_COLLECT_WEEKLY';
UPDATE public.cron_job_master SET cron_expression = '0 4 * * mon' WHERE job_code = 'AUTO_PARSE_NEW';
UPDATE public.cron_schedule_config SET cron_expression = '0 4 * * mon' WHERE job_code = 'AUTO_PARSE_NEW';
UPDATE public.cron_job_master SET cron_expression = '0 4 * * sun' WHERE job_code = 'LAW_COLLECT_MISSING';
UPDATE public.cron_schedule_config SET cron_expression = '0 4 * * sun' WHERE job_code = 'LAW_COLLECT_MISSING';
UPDATE public.cron_job_master SET cron_expression = '0 4 * * wed' WHERE job_code = 'RULE_REPARSE';
UPDATE public.cron_schedule_config SET cron_expression = '0 4 * * wed' WHERE job_code = 'RULE_REPARSE';
UPDATE public.cron_job_master SET cron_expression = '0 6 * * fri' WHERE job_code = 'VALIDATE_MASTER';
UPDATE public.cron_schedule_config SET cron_expression = '0 6 * * fri' WHERE job_code = 'VALIDATE_MASTER';

-- code-only holiday → master
INSERT INTO public.cron_job_master (job_code, job_name, cron_expression, is_active, endpoint_url, http_method, category, schedule_desc, timeout_seconds, is_system)
VALUES
  ('holiday_sync_annual', '공휴일 연간 동기화', '10 3 1 12 *', true, 'direct://holiday_sync', 'DIRECT', 'SYSTEM', '매년 12/1 03:10', 120, true),
  ('holiday_sync_quarterly', '공휴일 분기 동기화', '10 3 1 1,4,7,10 *', true, 'direct://holiday_sync', 'DIRECT', 'SYSTEM', '1/4/7/10월 1일 03:10', 120, true)
ON CONFLICT (job_code) DO NOTHING;

-- pg_cron 12 → master 1:1 (KST schedule, active_old preserved)
INSERT INTO public.cron_job_master (job_code, job_name, cron_expression, is_active, endpoint_url, http_method, category, schedule_desc, timeout_seconds, is_system)
VALUES
  ('daily_assignments', 'daily_assignments', '10 9 * * *', false, 'direct://generate_daily_assignments', 'DIRECT', 'SYSTEM', 'DB_FUNCTION', 300, true),
  ('daily_health', 'daily_health', '0 9 * * *', true, 'direct://daily_health_check', 'DIRECT', 'SYSTEM', 'DB_FUNCTION', 300, true),
  ('qa_send', 'qa_send', '0,30 * * * *', false, 'direct://send_auto_qa_requests', 'DIRECT', 'SYSTEM', 'DB_FUNCTION', 300, true),
  ('qa_collect', 'qa_collect', '2,32 * * * *', false, 'direct://collect_auto_qa_results', 'DIRECT', 'SYSTEM', 'DB_FUNCTION', 300, true),
  ('kosha_construction_21', 'kosha_construction_21', '0 6 * * *', true, 'direct://kosha_construction_safety_light', 'DIRECT', 'SYSTEM', 'HTTP', 300, true),
  ('kosha_construction_03', 'kosha_construction_03', '0 12 * * *', true, 'direct://kosha_construction_safety_light', 'DIRECT', 'SYSTEM', 'HTTP', 300, true),
  ('kosha_construction_09', 'kosha_construction_09', '0 18 * * *', true, 'direct://kosha_construction_safety_light', 'DIRECT', 'SYSTEM', 'HTTP', 300, true),
  ('kosha_accidents', 'kosha_accidents', '0 2 * * *', true, 'direct://kosha_accident_cases', 'DIRECT', 'SYSTEM', 'HTTP', 300, true),
  ('kosha_weekly', 'kosha_weekly', '0 3 * * mon', true, 'direct://kosha_safety_materials', 'DIRECT', 'SYSTEM', 'HTTP', 300, true),
  ('health_cleanup', 'health_cleanup', '0 12 * * *', true, 'direct://health_cleanup', 'DIRECT', 'SYSTEM', 'CLEANUP', 300, true),
  ('cron_job_log_retention', 'cron_job_log_retention', '17 * * * *', true, 'direct://cron_job_log_retention', 'DIRECT', 'SYSTEM', 'CLEANUP', 300, true),
  ('business_event_retention', 'business_event_retention', '27 3 * * *', true, 'direct://business_event_retention', 'DIRECT', 'SYSTEM', 'CLEANUP', 300, true)
ON CONFLICT (job_code) DO NOTHING;

INSERT INTO public.cron_schedule_config (job_id, job_code, cron_expression, is_enabled)
SELECT m.id, m.job_code, m.cron_expression, m.is_active
FROM public.cron_job_master m
WHERE NOT EXISTS (SELECT 1 FROM public.cron_schedule_config c WHERE c.job_code = m.job_code);

