-- WO-TAI-SLACK-RELAY-RECOVERY-GATE-001
-- Slack Relay Recovery 크론 등록 초안
-- STATUS: CODE_ONLY — DB 적용 미승인 / Owner 별도 Gate 필요
-- is_active=false, is_enabled=false — 활성화는 Owner 승인 후
-- 실질적 차단은 is_active=false (DbStore.refresh()는 is_active=true만 선택)

INSERT INTO public.cron_job_master (
    job_code, job_name, job_description, category,
    endpoint_url, http_method,
    cron_expression, schedule_desc,
    timeout_seconds, notify_on_fail, is_active, is_system
) VALUES (
    'slack_relay_recovery',
    'Slack Relay 자동 복구',
    'PENDING/RETRY 상태 릴레이 이벤트를 재처리한다. run_relay_recovery_once() 호출.',
    'slack',
    'direct://slack_relay_recovery',
    'DIRECT',
    '*/5 * * * *',
    '5분마다',
    120, true, false, true
) ON CONFLICT (job_code) DO NOTHING;

INSERT INTO public.cron_schedule_config (job_id, job_code, cron_expression, is_enabled)
SELECT m.id, m.job_code, m.cron_expression, m.is_active
FROM public.cron_job_master m
WHERE m.job_code = 'slack_relay_recovery'
  AND NOT EXISTS (
    SELECT 1 FROM public.cron_schedule_config c WHERE c.job_code = m.job_code
  );
