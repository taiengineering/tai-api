-- WO-TAI-BIZINFO-NOTIFICATION-ATOMIC-GATE-001 / SQL R1
-- 기업마당 공고 저장 + 알림 등록 단일 트랜잭션 PG 함수
--
-- STATUS: CODE_ONLY — DB 적용 미승인 / Owner DB Gate 필요
-- STOP=GPT_BIZINFO_NOTIFICATION_ATOMIC_SOURCE_IV
--
-- ■ 설계 근거 (R1 보정)
--   기존 fn_bizinfo_register_notification(알림만 등록)은
--   save_record()와 별도 REST 요청으로 실행돼 원자성 미확보.
--   이 함수는 bizinfo_source_records 저장 + slack_relay_event_log 등록을
--   단일 PG 트랜잭션으로 묶어 중단 시 양쪽이 함께 롤백된다.
--
-- ■ 적용 대상
--   1. 신규 IN_SCOPE 공고 저장 + 알림 등록 (p_relevance_verdict='IN_SCOPE')
--   2. 기존 IN_SCOPE 공고 상태 변경 저장 + 변경 알림 등록
--   3. 기타 공고 (알림 없음): p_notif_event_id=NULL → 알림 등록 생략
--
-- ■ 릴레이 복구 경로 (MANUAL_ONLY 주의)
--   현재 run_relay_recovery_once()는 POST /internal/slack-relay/recover
--   수동 엔드포인트로만 접근 가능하다.
--   정기 자동 복구는 별도 Owner 승인으로 cron_job_master에 등록해야 한다.
--   (GATE-RECOVERY: relay_recovery cron 등록 승인)
--
-- ■ 운영 활성화 Gate
--   GATE-DB    : Owner DB 함수 등록 승인
--   GATE-CODE  : daily_sync.py 연결 Code Auth 승인
--   GATE-SLACK : Slack 실 발송 Owner 승인 (기존 GATE-1과 동일)
--   GATE-RECOVERY: relay_recovery cron 등록 (별도 Owner 승인)
--   GATE-DEPLOY: Railway 배포 완료 (기존 GATE-2와 동일)

-- ────────────────────────────────────────────────────────────────────────────
-- fn_save_bizinfo_with_notification
--
-- 목적:
--   bizinfo_source_records upsert + slack_relay_event_log 알림 등록을
--   단일 PG 트랜잭션으로 수행한다.
--
-- 파라미터 (p_ = 공고 필드, p_relevance_verdict = 판정, p_n* = 알림):
--   p_notif_event_id NULL → 알림 등록 생략 (저장만 수행)
--
-- 반환:
--   JSONB { "saved": true, "notif_registered": bool }
--
-- relevance_verdict 보호 정책 (ON CONFLICT DO UPDATE):
--   p_relevance_verdict NULL → 기존 값 보존
--   기존 값 IN_SCOPE / OUT_OF_SCOPE → 덮어쓰지 않음
--   기존 값 REVIEW_REQUIRED 또는 NULL → p_relevance_verdict로 갱신
--
-- 동시성 보호:
--   ON CONFLICT (source_kind, source_key) DO UPDATE → PG 행 잠금 사용.
--   ON CONFLICT (event_id) DO NOTHING → 중복 알림 차단 (idempotent).
-- ────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public.fn_save_bizinfo_with_notification(
    -- bizinfo_source_records 필드
    p_source_kind           TEXT,
    p_source_key            TEXT,
    p_title                 TEXT,
    p_source_org            TEXT        DEFAULT NULL,
    p_origin_url            TEXT        DEFAULT NULL,
    p_bizinfo_url           TEXT        DEFAULT NULL,
    p_retrieved_at          TIMESTAMPTZ DEFAULT NULL,
    p_source_updated_at     TIMESTAMPTZ DEFAULT NULL,
    p_summary               TEXT        DEFAULT NULL,
    p_support_target        TEXT        DEFAULT NULL,
    p_hashtags              TEXT[]      DEFAULT '{}',
    p_parse_errors          TEXT[]      DEFAULT '{}',
    p_evidence_pending      TEXT[]      DEFAULT '{}',
    p_application_start     DATE        DEFAULT NULL,
    p_application_end       DATE        DEFAULT NULL,
    p_event_start           DATE        DEFAULT NULL,
    p_event_end             DATE        DEFAULT NULL,
    p_reception_start       DATE        DEFAULT NULL,
    p_reception_end         DATE        DEFAULT NULL,
    p_change_verdict        TEXT        DEFAULT NULL,
    p_changed_fields        TEXT[]      DEFAULT '{}',
    -- 판정 (IN_SCOPE/OUT_OF_SCOPE/REVIEW_REQUIRED): NULL이면 보존
    p_relevance_verdict     TEXT        DEFAULT NULL,
    -- 알림 파라미터 (모두 NULL이면 알림 등록 생략)
    p_notif_event_id        TEXT        DEFAULT NULL,
    p_relay_channel         TEXT        DEFAULT NULL,
    p_target_channel        TEXT        DEFAULT NULL,
    p_message_text          TEXT        DEFAULT NULL,
    p_sender_id             TEXT        DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY INVOKER
AS $$
DECLARE
    v_notif_inserted INTEGER := 0;
BEGIN
    -- ── 1. bizinfo_source_records upsert ─────────────────────────────────
    INSERT INTO public.bizinfo_source_records (
        source_kind,
        source_key,
        title,
        source_org,
        origin_url,
        bizinfo_url,
        retrieved_at,
        source_updated_at,
        summary,
        support_target,
        hashtags,
        parse_errors,
        evidence_pending,
        application_start,
        application_end,
        event_start,
        event_end,
        reception_start,
        reception_end,
        relevance_verdict,
        change_verdict,
        changed_fields,
        updated_at
    ) VALUES (
        p_source_kind,
        p_source_key,
        p_title,
        p_source_org,
        p_origin_url,
        p_bizinfo_url,
        COALESCE(p_retrieved_at, NOW()),
        p_source_updated_at,
        p_summary,
        p_support_target,
        COALESCE(p_hashtags, '{}'),
        COALESCE(p_parse_errors, '{}'),
        COALESCE(p_evidence_pending, '{}'),
        p_application_start,
        p_application_end,
        p_event_start,
        p_event_end,
        p_reception_start,
        p_reception_end,
        p_relevance_verdict,
        p_change_verdict,
        COALESCE(p_changed_fields, '{}'),
        NOW()
    )
    ON CONFLICT (source_kind, source_key) DO UPDATE SET
        title             = EXCLUDED.title,
        source_org        = EXCLUDED.source_org,
        origin_url        = EXCLUDED.origin_url,
        bizinfo_url       = EXCLUDED.bizinfo_url,
        retrieved_at      = EXCLUDED.retrieved_at,
        source_updated_at = EXCLUDED.source_updated_at,
        summary           = EXCLUDED.summary,
        support_target    = EXCLUDED.support_target,
        hashtags          = EXCLUDED.hashtags,
        parse_errors      = EXCLUDED.parse_errors,
        evidence_pending  = EXCLUDED.evidence_pending,
        application_start = EXCLUDED.application_start,
        application_end   = EXCLUDED.application_end,
        event_start       = EXCLUDED.event_start,
        event_end         = EXCLUDED.event_end,
        reception_start   = EXCLUDED.reception_start,
        reception_end     = EXCLUDED.reception_end,
        -- relevance_verdict 보호: IN_SCOPE/OUT_OF_SCOPE는 덮어쓰지 않음
        relevance_verdict = CASE
            WHEN p_relevance_verdict IS NULL
                THEN bizinfo_source_records.relevance_verdict
            WHEN bizinfo_source_records.relevance_verdict IN ('IN_SCOPE', 'OUT_OF_SCOPE')
                THEN bizinfo_source_records.relevance_verdict
            ELSE p_relevance_verdict
        END,
        change_verdict    = EXCLUDED.change_verdict,
        changed_fields    = EXCLUDED.changed_fields,
        updated_at        = NOW();

    -- ── 2. slack_relay_event_log 알림 등록 (optional, idempotent) ─────────
    IF p_notif_event_id IS NOT NULL THEN
        INSERT INTO public.slack_relay_event_log (
            event_id,
            relay_channel,
            target_channel,
            message_text,
            sender_id,
            source_message_ts,
            status
        ) VALUES (
            p_notif_event_id,
            p_relay_channel,
            p_target_channel,
            SUBSTRING(COALESCE(p_message_text, ''), 1, 4000),
            p_sender_id,
            NULL,
            'PENDING'
        )
        ON CONFLICT (event_id) DO NOTHING;

        GET DIAGNOSTICS v_notif_inserted = ROW_COUNT;
    END IF;

    RETURN jsonb_build_object(
        'saved',            true,
        'notif_registered', v_notif_inserted > 0
    );
END;
$$;

-- ────────────────────────────────────────────────────────────────────────────
-- 보안: 함수 실행 권한 제한
-- PUBLIC 기본 부여 취소 → service_role만 실행 가능
-- ────────────────────────────────────────────────────────────────────────────

REVOKE EXECUTE ON FUNCTION public.fn_save_bizinfo_with_notification
    FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.fn_save_bizinfo_with_notification
    TO service_role;

-- ────────────────────────────────────────────────────────────────────────────
-- 연결 설계 요약 (CODE_ONLY — Code Auth Gate HOLD)
--
-- services/bizinfo/repository.py
--   BizinfoRepository.save_record_with_notification(record, change, *,
--     relevance_verdict=None, notif_event_id=None, ...) -> bool
--   InMemoryBizinfoRepository.save_record_with_notification(...)
--
-- services/bizinfo/supabase_repository.py
--   SupabaseBizinfoRepository.save_record_with_notification(...)
--     → sb.rpc("fn_save_bizinfo_with_notification", params).execute()
--
-- services/bizinfo/daily_sync.py _sync_kind() 연결 지점:
--   신규 IN_SCOPE:
--     repo.save_record_with_notification(normalized, change,
--       relevance_verdict="IN_SCOPE",
--       notif_event_id=f"bizinfo_new_{source_kind.lower()}_{key}_{today}",
--       message_text=_build_per_item_message(normalized, decision),
--       ...)
--   기존 IN_SCOPE 상태 변경:
--     repo.save_record_with_notification(normalized, change,
--       notif_event_id=f"bizinfo_status_{source_kind.lower()}_{key}_{today}",
--       message_text=_build_status_change_message(status_ev),
--       ...)
--   기타 공고 (알림 없음):
--     repo.save_record(normalized, change)  — 기존 경로 유지
-- ────────────────────────────────────────────────────────────────────────────

-- ────────────────────────────────────────────────────────────────────────────
-- 활성화 절차 (모두 별도 Owner 승인 필요)
--
--   Step 1: SOURCE IV PASS (STOP=GPT_BIZINFO_NOTIFICATION_ATOMIC_SOURCE_IV)
--   Step 2: Owner GATE-DB 승인 → fn_save_bizinfo_with_notification 등록
--   Step 3: Owner GATE-CODE 승인 → daily_sync.py 연결 구현
--   Step 4: Owner GATE-RECOVERY 승인 → relay_recovery cron_job_master 등록
--   Step 5: 기존 GATE-1(Slack 실 발송) + GATE-2(Railway 배포) 연계
--   Step 6: E2E 검증 후 CLOSED
-- ────────────────────────────────────────────────────────────────────────────
