-- WO-TAI-SLACK-RELAY-RECOVERY-GATE-001
-- Slack Relay Recovery 크론 등록 초안
--
-- STATUS: CODE_ONLY — DB 적용 미승인 / Owner 별도 Gate 필요
-- STOP=GPT_SLACK_RELAY_RECOVERY_SOURCE_IV
--
-- ■ 실행 차단 핵심
--   DbStore.refresh()는 cron_job_master.is_active=true 행만 실행 대상으로 선택한다.
--   is_enabled=false 만으로 안전하다고 판단하면 안 된다 — 실질적 차단은 is_active=false.
--
-- ■ 활성화 순서 (전부 Owner 별도 승인)
--   STEP-1: GATE-RECOVERY 코드 PR 병합 + Railway 배포 완료
--   STEP-2: Owner DB 등록 승인 → 이 SQL 실행 (is_active=false 상태로 등록)
--   STEP-3: test PENDING 이벤트 처리 검증 (POST /cron/jobs/slack_relay_recovery/run)
--   STEP-4: Owner 활성화 승인 → is_active=true / is_enabled=true 별도 UPDATE
--   STEP-5: 5분 주기 발화 1회 이상 cron_job_log.status=SUCCESS 확인

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
