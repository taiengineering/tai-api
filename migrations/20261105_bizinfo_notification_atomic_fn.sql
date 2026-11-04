-- WO-TAI-BIZINFO-NOTIFICATION-ATOMIC-GATE-001 / SQL R1
-- 기업마당 알림 원자적 등록 PG 함수 설계
--
-- STATUS: CODE_ONLY — DB 적용 미승인 / Owner DB Gate 필요
-- STOP=GPT_BIZINFO_NOTIFICATION_ATOMIC_SOURCE_IV
--
-- ■ 분석 결론
--   기존 테이블 충분 여부: YES (신규 테이블 불필요)
--   기존 Relay 코드 영향: NONE (accept_relay_event / process_relay_event 변경 없음)
--
-- ■ KNOWN_LIMITATION 해소 경로
--   현재 daily_sync.py 는 모든 레코드 저장 완료 후 Slack 알림을 등록한다.
--   "저장 성공 → 프로세스 중단 → 알림 등록 미실행" 구간에서 알림이 유실된다.
--   완전한 at-least-once 보장은 아래 두 단계가 모두 완료되어야 한다:
--
--   STEP-1 (Owner DB Gate): fn_bizinfo_register_notification 함수 등록
--   STEP-2 (Code Auth Gate): daily_sync.py 수정
--     _sync_kind 내에서 save_record 직후 각 신규 IN_SCOPE 항목에 대해
--     fn_bizinfo_register_notification RPC 호출 (항목별 알림, 단일 PG 트랜잭션)
--
-- ■ 운영 활성화 전 필수 Gate
--   GATE-DB : Owner DB 함수 등록 승인
--   GATE-CODE: daily_sync.py 수정 Code Auth 승인
--   GATE-SLACK: Slack 실 발송 Owner 승인 (기존 GATE-1과 동일)

-- ────────────────────────────────────────────────────────────────────────────
-- fn_bizinfo_register_notification
--
-- 목적:
--   신규 IN_SCOPE 공고에 대한 Slack 알림을 slack_relay_event_log에 PENDING으로 등록.
--   ON CONFLICT (event_id) DO NOTHING → 중복 등록 차단 (idempotent).
--
-- 반환:
--   TRUE  — 신규 등록 성공
--   FALSE — event_id 중복 (이미 등록됨)
--
-- 호출 위치 (설계):
--   services/bizinfo/daily_sync.py _sync_kind()
--   repo.save_record(normalized, change) 직후 호출하면
--   save_record와 동일한 HTTP 요청 범위 내에서 처리된다.
--   완전한 단일 PG 트랜잭션은 fn_save_bizinfo_with_notification (별도 Gate) 사용.
-- ────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public.fn_bizinfo_register_notification(
    p_event_id        TEXT,
    p_relay_channel   TEXT,
    p_target_channel  TEXT,
    p_message_text    TEXT,
    p_sender_id       TEXT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY INVOKER
AS $$
DECLARE
    v_inserted INTEGER;
BEGIN
    INSERT INTO public.slack_relay_event_log (
        event_id,
        relay_channel,
        target_channel,
        message_text,
        sender_id,
        source_message_ts,
        status
    ) VALUES (
        p_event_id,
        p_relay_channel,
        p_target_channel,
        SUBSTRING(p_message_text FROM 1 FOR 4000),
        p_sender_id,
        NULL,
        'PENDING'
    )
    ON CONFLICT (event_id) DO NOTHING;

    GET DIAGNOSTICS v_inserted = ROW_COUNT;
    RETURN v_inserted > 0;
END;
$$;

-- ────────────────────────────────────────────────────────────────────────────
-- (별도 Gate) fn_save_bizinfo_with_notification — 완전 원자성
--
-- save_record(bizinfo_source_records upsert) + 알림 등록을 단일 트랜잭션으로 묶는다.
-- 구현은 bizinfo_source_records 전체 컬럼 확정 후 별도 Owner DB Gate 승인 필요.
-- 아래는 설계 스케치이며 실행 불가 의사코드(pseudo-code)이다.
--
-- CREATE OR REPLACE FUNCTION public.fn_save_bizinfo_with_notification(
--     /* bizinfo_source_records upsert 파라미터 (전체 컬럼) */
--     p_source_kind       TEXT,
--     p_source_key        TEXT,
--     p_title             TEXT,
--     /* ... 기타 컬럼 ... */
--     /* 알림 파라미터 (NULL이면 알림 미등록) */
--     p_notif_event_id    TEXT DEFAULT NULL,
--     p_relay_channel     TEXT DEFAULT NULL,
--     p_target_channel    TEXT DEFAULT NULL,
--     p_message_text      TEXT DEFAULT NULL,
--     p_sender_id         TEXT DEFAULT NULL
-- ) RETURNS JSONB AS $$
-- BEGIN
--     /* 1. bizinfo_source_records upsert */
--     INSERT INTO public.bizinfo_source_records (source_kind, source_key, title, ...)
--     VALUES (p_source_kind, p_source_key, p_title, ...)
--     ON CONFLICT (source_kind, source_key) DO UPDATE SET ...;
--
--     /* 2. 알림 등록 (optional) */
--     IF p_notif_event_id IS NOT NULL THEN
--         INSERT INTO public.slack_relay_event_log (event_id, relay_channel, target_channel,
--                                                   message_text, sender_id, source_message_ts, status)
--         VALUES (p_notif_event_id, p_relay_channel, p_target_channel,
--                 SUBSTRING(p_message_text FROM 1 FOR 4000), p_sender_id, NULL, 'PENDING')
--         ON CONFLICT (event_id) DO NOTHING;
--     END IF;
--
--     RETURN jsonb_build_object('saved', true);
-- END;
-- $$ LANGUAGE plpgsql SECURITY INVOKER;
-- ────────────────────────────────────────────────────────────────────────────

-- ────────────────────────────────────────────────────────────────────────────
-- 활성화 절차 (모두 별도 Owner 승인 필요)
--
--   Step 1: SOURCE IV PASS (STOP=GPT_BIZINFO_NOTIFICATION_ATOMIC_SOURCE_IV)
--   Step 2: Owner DB Gate 승인 → fn_bizinfo_register_notification 등록
--   Step 3: Code Auth Gate → daily_sync.py 수정 승인
--   Step 4: 기존 GATE-1(Slack 실 발송) + GATE-2(Railway 배포) 연계 확인
--   Step 5: E2E 검증 후 CLOSED
-- ────────────────────────────────────────────────────────────────────────────
