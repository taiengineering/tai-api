-- WO-QA-CONTROL-PHASE2E-AUTO-OPS-001 PATCH1
-- QA Scheduler Tick cron job 등록 (비활성 상태로 추가; 운영 전환 시 is_active=true)
-- Activation Authority: cron_job_master.is_active (not cron_schedule_config.is_enabled)

INSERT INTO public.cron_job_master
    (job_code, job_name, cron_expression, is_active, endpoint_url, http_method,
     category, schedule_desc, timeout_seconds, is_system)
VALUES
    ('qa_scheduler_tick',
     'QA Scheduler Tick',
     '* * * * *',
     false,
     'direct://qa_scheduler_tick',
     'DIRECT',
     'QA',
     '매분 QA schedule 점검 및 자동 run 생성',
     120,
     true)
ON CONFLICT (job_code) DO NOTHING;

INSERT INTO public.cron_schedule_config (job_id, job_code, cron_expression, is_enabled)
SELECT m.id, m.job_code, m.cron_expression, m.is_active
FROM public.cron_job_master m
WHERE m.job_code = 'qa_scheduler_tick'
  AND NOT EXISTS (
    SELECT 1 FROM public.cron_schedule_config c WHERE c.job_code = m.job_code
  );
