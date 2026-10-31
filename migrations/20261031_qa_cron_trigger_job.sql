-- WO-TAI-QA-OPS-TIMED-TRIGGER-P0-005
-- qa_cron_trigger 스케줄러 잡 등록
--
-- STATUS: CODE_ONLY — DB 적용 미승인
-- is_active=false: 기존 GitHub Actions schedule 유지, 운영 검증 후 활성화
--
-- UTC 슬롯: 10:00Z (= KST 19:00), 21:00Z (= KST 06:00 익일)
-- KST 기준: 매일 06:00 / 19:00
--
-- 운영 전환 계획:
--   Step 1: is_active=false로 배포 (현행 GitHub schedule 유지)
--   Step 2: 1회 이상 정시 dispatch 확인 (cron_job_log SUCCESS)
--   Step 3: is_active=true로 업데이트
--   Step 4: tai-qa qa-twice-daily.yml의 GitHub schedule 구문 제거(별도 PR)
--   Step 5: 24h 모니터링 후 CLOSED

INSERT INTO cron_job_master (
    job_code,
    display_name,
    cron_expression,
    endpoint_url,
    is_active,
    timeout_seconds,
    request_payload
)
VALUES (
    'qa_cron_trigger',
    'QA Twice-Daily Timed Trigger (WO-005)',
    '0 21,10 * * *',          -- UTC: 21:00Z + 10:00Z
    'direct://qa_cron_trigger',
    false,                     -- 검증 전 비활성
    60,
    '{}'
)
ON CONFLICT (job_code) DO NOTHING;

INSERT INTO cron_schedule_config (job_code)
VALUES ('qa_cron_trigger')
ON CONFLICT (job_code) DO NOTHING;
