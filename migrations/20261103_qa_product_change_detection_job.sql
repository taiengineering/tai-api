-- WO-TAI-QA-M5A-SCHEDULER-BRIDGE-001 / SQL R1
-- qa_product_change_detection 스케줄러 잡 등록
--
-- STATUS: CODE_ONLY — DB 적용 미승인 / is_active=false 고정
-- STOP=GPT_M5A_SCHEDULER_SQL_SOURCE_IV
--
-- 실행 주기: Owner 확정 2026-11-03
--   '15 6,19 * * *' KST 06:15 / 19:15 (= UTC 21:15Z 전일 + 10:15Z 당일)
--   기존 P0 발화(06:00/19:00) 직후 15분
--
-- ■ 운영 활성화 전 필수 해소 조건
--   CON-01: product-change-detection.yml Step 9 if:false 상태 유지 중.
--           정기 발화 시 처리 완료 HEAD가 갱신되지 않으므로 매 실행마다 동일 변경을
--           반복 감지하는 무한 루프 위험이 있다.
--           is_active=true 설정 전 반드시 다음 중 하나가 선행되어야 한다:
--             (a) Step 9 활성화 + 미처리 QA 56건 후속 처리 경로 확보 (별도 WO + Owner 승인)
--             (b) 동등한 HEAD 상태 관리 방안 확보

-- ────────────────────────────────────────────────────────────
-- Step 1: cron_job_master 등록
-- ────────────────────────────────────────────────────────────
INSERT INTO public.cron_job_master
    (job_code, job_name, cron_expression, is_active, endpoint_url, http_method,
     category, schedule_desc, timeout_seconds, is_system)
VALUES
    ('qa_product_change_detection',
     'QA Product Change Detection (M5-A)',
     '15 6,19 * * *',              -- KST 06:15 / 19:15 (Owner 확정 2026-11-03)
     false,                        -- CON-01 해소 전 비활성 고정
     'direct://qa_product_change_detection',
     'DIRECT',
     'QA',
     '매일 06:15/19:15 KST — product-change-detection.yml workflow_dispatch, PLAN_ONLY, force_run=false (M5-A, WO-TAI-QA-M5A-SCHEDULER-BRIDGE-001)',
     60,
     false)
ON CONFLICT (job_code) DO NOTHING;

-- ────────────────────────────────────────────────────────────
-- Step 2: cron_schedule_config 등록 (중복 없을 때만)
-- ────────────────────────────────────────────────────────────
-- is_enabled = m.is_active = false → 자동 실행 차단 상태로 등록
INSERT INTO public.cron_schedule_config (job_id, job_code, cron_expression, is_enabled)
SELECT m.id, m.job_code, m.cron_expression, m.is_active
FROM public.cron_job_master m
WHERE m.job_code = 'qa_product_change_detection'
  AND NOT EXISTS (
    SELECT 1 FROM public.cron_schedule_config c WHERE c.job_code = m.job_code
  );

-- ────────────────────────────────────────────────────────────
-- 운영 활성화 절차 (모두 별도 Owner 승인 필요)
--
--   Pre-gate (CON-01 해소):
--     G0: product-change-detection.yml Step 9 if:false 처리 + 미처리 QA 56건 경로 확보
--         (별도 WO + Owner 승인 선행 — 단순 if:false 제거 불가)
--
--   Step 1: SOURCE IV PASS (STOP=GPT_M5A_SCHEDULER_SQL_SOURCE_IV)
--   Step 2: Owner 병합 승인
--   Step 3: Owner DB 적용 승인 → is_active=false 상태로 등록
--   Step 4: CON-01 해소 완료 확인
--   Step 5: Owner 활성화 승인 → is_active=true / is_enabled=true 업데이트
--   Step 6: 정기 발화 1회 이상 cron_job_log.status=SUCCESS 확인
--   Step 7: 24h 모니터링 후 CLOSED
-- ────────────────────────────────────────────────────────────
