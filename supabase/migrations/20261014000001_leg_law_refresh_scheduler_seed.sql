-- WO-TAI-LEG-USED-LAW-REFRESH-001: LEG 법령 자동갱신 스케줄러 시드
-- is_active = false — 운영 활성화는 Owner 별도 승인 후 UPDATE로 전환
-- EXECUTION BLOCKED: Owner-authorized activation only

INSERT INTO public.cron_job_master
    (job_code, job_name, cron_expression, is_active, endpoint_url, http_method,
     category, schedule_desc, timeout_seconds, is_system)
VALUES
    ('leg_law_refresh',
     'LEG 사용 법령 별표·서식 갱신',
     '0 3 * * *',
     false,
     'direct://leg_law_refresh',
     'DIRECT',
     'LEG',
     '매일 03:00 KST — TAI 사용 법령의 별표·서식 신규분 수집 (licbyl search=2)',
     600,
     false)
ON CONFLICT (job_code) DO NOTHING;

INSERT INTO public.cron_schedule_config (job_id, job_code, cron_expression, is_enabled)
SELECT m.id, m.job_code, m.cron_expression, m.is_active
FROM public.cron_job_master m
WHERE m.job_code = 'leg_law_refresh'
  AND NOT EXISTS (
    SELECT 1 FROM public.cron_schedule_config c WHERE c.job_code = m.job_code
  );
