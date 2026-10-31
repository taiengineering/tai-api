-- WO-TAI-QA-OPS-TIMED-TRIGGER-P0-005-R2
-- qa_cron_trigger 스케줄러 잡 등록
--
-- STATUS: CODE_ONLY — DB 적용 미승인
-- is_active=false: 기존 GitHub Actions schedule 유지, 운영 전환 절차 완료 후 활성화
--
-- R2-01 정정: KST 기반 스케줄러이므로 KST 시각으로 등록
--   '0 6,19 * * *' KST = 06:00 KST (= 21:00Z 전일) + 19:00 KST (= 10:00Z 당일)
--   구 SQL의 '0 21,10 * * *' = 21:00 KST + 10:00 KST → 오류

INSERT INTO public.cron_job_master
    (job_code, job_name, cron_expression, is_active, endpoint_url, http_method,
     category, schedule_desc, timeout_seconds, is_system)
VALUES
    ('qa_cron_trigger',
     'QA Twice-Daily Timed Trigger',
     '0 6,19 * * *',           -- KST: 06:00 + 19:00 (= UTC 21:00Z + 10:00Z)
     false,                     -- 운영 전환 Gate 완료 전 비활성 유지
     'direct://qa_cron_trigger',
     'DIRECT',
     'QA',
     '매일 06:00/19:00 KST — qa-twice-daily.yml workflow_dispatch (WO-005)',
     60,
     false)
ON CONFLICT (job_code) DO NOTHING;

INSERT INTO public.cron_schedule_config (job_id, job_code, cron_expression, is_enabled)
SELECT m.id, m.job_code, m.cron_expression, m.is_active
FROM public.cron_job_master m
WHERE m.job_code = 'qa_cron_trigger'
  AND NOT EXISTS (
    SELECT 1 FROM public.cron_schedule_config c WHERE c.job_code = m.job_code
  );

-- 운영 전환 절차 (별도 Owner 승인 필요):
--
--   Step 1: CODE_ONLY Migration 정정 + PR SOURCE IV PASS
--   Step 2: Owner 병합 승인
--   Step 3: is_active=false 상태로 운영 배포 (GitHub schedule 유지 — 중복 없음)
--   Step 4: Owner 운영 전환 승인 후 아래 두 경로 중 선택:
--
--     [공백 허용] (권장)
--       4a: tai-qa에서 schedule 구문 제거 (별도 PR, 배포 후 1~2개 슬롯 발화 공백 발생)
--       4b: qa_cron_trigger.is_active=true 업데이트
--
--     [공백 불허 — 중복 1회 허용]
--       4a: qa_cron_trigger.is_active=true 업데이트
--       4b: tai-qa schedule 구문 제거 (next slot까지 중복 1회 가능)
--
--   Step 5: 첫 정시 실행 cron_job_log.status=SUCCESS 확인
--   Step 6: 24h 모니터링 후 CLOSED
