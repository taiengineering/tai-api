-- WO-TAI-BIZINFO-DAILY-SYNC-SLACK-001 / SQL R1
-- 기업마당 일일 동기화 스케줄러 잡 등록
--
-- STATUS: CODE_ONLY — DB 적용 미승인 / is_active=false 고정
-- STOP=GPT_BIZINFO_DAILY_SYNC_SOURCE_IV
--
-- 실행 주기: 매일 KST 13:00 (= UTC 04:00)
--   '0 4 * * *'
--
-- ■ 운영 활성화 전 필수 해소 조건
--   GATE-1: Slack 실 발송 Owner 승인
--           현재 _SLACK_CHANNEL = C0CCQKVQCQP 고정, 실 메시지 발송 차단 상태.
--           is_active=true 설정 전 Owner 명시 승인 필수.
--   GATE-2: 운영 배포(Railway) 완료
--           핸들러 코드가 운영 환경에 미배포 상태.
--   GATE-3: BIZINFO_STORAGE_ENABLED=1 환경변수 활성화
--           현재 비활성 — SupabaseBizinfoRepository 미작동.

-- ────────────────────────────────────────────────────────────
-- Step 1: cron_job_master 등록
-- ────────────────────────────────────────────────────────────
INSERT INTO public.cron_job_master
    (job_code, job_name, cron_expression, is_active, endpoint_url, http_method,
     category, schedule_desc, timeout_seconds, is_system)
VALUES
    ('bizinfo_daily_safety_sync',
     '기업마당 안전 관련 일일 동기화',
     '0 4 * * *',                   -- KST 13:00 (= UTC 04:00)
     false,                         -- GATE-1/2/3 해소 전 비활성 고정
     'direct://bizinfo_daily_safety_sync',
     'DIRECT',
     'BIZINFO',
     '매일 13:00 KST — 기업마당 수집·상태갱신·Slack 알림',
     300,
     false)
ON CONFLICT (job_code) DO NOTHING;

-- ────────────────────────────────────────────────────────────
-- Step 2: cron_schedule_config 등록 (중복 없을 때만)
-- ────────────────────────────────────────────────────────────
-- is_enabled = m.is_active = false → 자동 실행 차단 상태로 등록
INSERT INTO public.cron_schedule_config (job_id, job_code, cron_expression, is_enabled)
SELECT m.id, m.job_code, m.cron_expression, m.is_active
FROM public.cron_job_master m
WHERE m.job_code = 'bizinfo_daily_safety_sync'
  AND NOT EXISTS (
    SELECT 1 FROM public.cron_schedule_config c WHERE c.job_code = m.job_code
  );

-- ────────────────────────────────────────────────────────────
-- 운영 활성화 절차 (모두 별도 Owner 승인 필요)
--
--   Step 1: SOURCE IV PASS (STOP=GPT_BIZINFO_DAILY_SYNC_SOURCE_IV)
--   Step 2: Owner 병합 승인
--   Step 3: Owner DB 적용 승인 → is_active=false 상태로 등록
--   Step 4: GATE-3(BIZINFO_STORAGE_ENABLED=1) 환경변수 활성화
--   Step 5: Owner GATE-1(Slack 실 발송) 승인
--   Step 6: Owner GATE-2(Railway 배포) 완료 확인
--   Step 7: Owner 활성화 승인 → is_active=true / is_enabled=true 업데이트
--   Step 8: 정기 발화 1회 이상 cron_job_log.status=SUCCESS 확인
--   Step 9: 24h 모니터링 후 CLOSED
-- ────────────────────────────────────────────────────────────
