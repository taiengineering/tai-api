-- WO-TAI-BIZINFO-LIFECYCLE-ATOMIC-001 / SQL R1
-- fn_save_bizinfo_with_notification V2 — 상태 컬럼 자동 계산 추가
--
-- STATUS: CODE_ONLY — DB 적용 미승인 / Owner DB Gate 필요
-- STOP=GPT_BIZINFO_LIFECYCLE_ATOMIC_SOURCE_IV
--
-- ■ 선행 조건
--   20261106_bizinfo_status_columns.sql 먼저 실행 완료
--   (recruitment_status, reception_status, progress_status, status_as_of 컬럼 존재 필수)
--
-- ■ V1 대비 변경 사항
--   bizinfo_source_records UPSERT에 상태 컬럼 자동 계산·저장 추가.
--   Python 계층 파라미터 변경 없음 — 기존 p_ 파라미터 집합 그대로 유지.
--   상태는 KST(Asia/Seoul) 기준 날짜로 함수 내부에서 계산한다.
--
-- ■ 상태 계산 규칙 (services/bizinfo/status.py 의 _date_status 로직과 동일)
--   PROGRAM recruitment_status :
--     start IS NULL AND end IS NULL → UNKNOWN
--     today > end                   → CLOSED
--     today < start                 → UPCOMING
--     start <= today <= end         → OPEN (양쪽 날짜 모두 필수)
--     otherwise                     → UNKNOWN
--
--   EVENT reception_status : 위와 동일 (reception_start/end 사용)
--   EVENT progress_status  :
--     start IS NULL AND end IS NULL → UNKNOWN
--     today > end                   → ENDED
--     today < start                 → UPCOMING
--     start <= today <= end         → ONGOING (양쪽 날짜 모두 필수)
--     otherwise                     → UNKNOWN
--
-- ■ 활성화 Gate
--   GATE-DB : Owner DB 승인 → CREATE OR REPLACE FUNCTION 실행
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
    v_notif_inserted    INTEGER := 0;
    v_recruitment_status TEXT;
    v_reception_status   TEXT;
    v_progress_status    TEXT;
BEGIN
    -- ── 0. 상태 계산 (KST 한국시간 기준) ──────────────────────────────────
    --
    -- CURRENT_DATE는 세션 시간대에 의존하므로 명시적으로 Asia/Seoul 기준 날짜를 사용한다.
    -- recruitment_status (PROGRAM only)
    v_recruitment_status := CASE
        WHEN p_source_kind = 'PROGRAM' THEN
            CASE
                WHEN p_application_start IS NULL AND p_application_end IS NULL THEN 'UNKNOWN'
                WHEN p_application_end IS NOT NULL AND (NOW() AT TIME ZONE 'Asia/Seoul')::date > p_application_end THEN 'CLOSED'
                WHEN p_application_start IS NOT NULL AND (NOW() AT TIME ZONE 'Asia/Seoul')::date < p_application_start THEN 'UPCOMING'
                WHEN p_application_start IS NOT NULL
                     AND p_application_end IS NOT NULL
                     AND p_application_start <= (NOW() AT TIME ZONE 'Asia/Seoul')::date
                     AND (NOW() AT TIME ZONE 'Asia/Seoul')::date <= p_application_end THEN 'OPEN'
                ELSE 'UNKNOWN'
            END
        ELSE NULL
    END;

    -- reception_status (EVENT only)
    v_reception_status := CASE
        WHEN p_source_kind = 'EVENT' THEN
            CASE
                WHEN p_reception_start IS NULL AND p_reception_end IS NULL THEN 'UNKNOWN'
                WHEN p_reception_end IS NOT NULL AND (NOW() AT TIME ZONE 'Asia/Seoul')::date > p_reception_end THEN 'CLOSED'
                WHEN p_reception_start IS NOT NULL AND (NOW() AT TIME ZONE 'Asia/Seoul')::date < p_reception_start THEN 'UPCOMING'
                WHEN p_reception_start IS NOT NULL
                     AND p_reception_end IS NOT NULL
                     AND p_reception_start <= (NOW() AT TIME ZONE 'Asia/Seoul')::date
                     AND (NOW() AT TIME ZONE 'Asia/Seoul')::date <= p_reception_end THEN 'OPEN'
                ELSE 'UNKNOWN'
            END
        ELSE NULL
    END;

    -- progress_status (EVENT only) — OPEN 대신 ONGOING, CLOSED 대신 ENDED
    v_progress_status := CASE
        WHEN p_source_kind = 'EVENT' THEN
            CASE
                WHEN p_event_start IS NULL AND p_event_end IS NULL THEN 'UNKNOWN'
                WHEN p_event_end IS NOT NULL AND (NOW() AT TIME ZONE 'Asia/Seoul')::date > p_event_end THEN 'ENDED'
                WHEN p_event_start IS NOT NULL AND (NOW() AT TIME ZONE 'Asia/Seoul')::date < p_event_start THEN 'UPCOMING'
                WHEN p_event_start IS NOT NULL
                     AND p_event_end IS NOT NULL
                     AND p_event_start <= (NOW() AT TIME ZONE 'Asia/Seoul')::date
                     AND (NOW() AT TIME ZONE 'Asia/Seoul')::date <= p_event_end THEN 'ONGOING'
                ELSE 'UNKNOWN'
            END
        ELSE NULL
    END;

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
        recruitment_status,
        reception_status,
        progress_status,
        status_as_of,
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
        v_recruitment_status,
        v_reception_status,
        v_progress_status,
        (NOW() AT TIME ZONE 'Asia/Seoul')::date,
        p_relevance_verdict,
        p_change_verdict,
        COALESCE(p_changed_fields, '{}'),
        NOW()
    )
    ON CONFLICT (source_kind, source_key) DO UPDATE SET
        title               = EXCLUDED.title,
        source_org          = EXCLUDED.source_org,
        origin_url          = EXCLUDED.origin_url,
        bizinfo_url         = EXCLUDED.bizinfo_url,
        retrieved_at        = EXCLUDED.retrieved_at,
        source_updated_at   = EXCLUDED.source_updated_at,
        summary             = EXCLUDED.summary,
        support_target      = EXCLUDED.support_target,
        hashtags            = EXCLUDED.hashtags,
        parse_errors        = EXCLUDED.parse_errors,
        evidence_pending    = EXCLUDED.evidence_pending,
        application_start   = EXCLUDED.application_start,
        application_end     = EXCLUDED.application_end,
        event_start         = EXCLUDED.event_start,
        event_end           = EXCLUDED.event_end,
        reception_start     = EXCLUDED.reception_start,
        reception_end       = EXCLUDED.reception_end,
        -- 상태 컬럼: 항상 최신 값으로 갱신 (날짜 의존 파생값)
        recruitment_status  = EXCLUDED.recruitment_status,
        reception_status    = EXCLUDED.reception_status,
        progress_status     = EXCLUDED.progress_status,
        status_as_of        = EXCLUDED.status_as_of,
        -- relevance_verdict 보호: IN_SCOPE/OUT_OF_SCOPE는 덮어쓰지 않음
        relevance_verdict   = CASE
            WHEN p_relevance_verdict IS NULL
                THEN bizinfo_source_records.relevance_verdict
            WHEN bizinfo_source_records.relevance_verdict IN ('IN_SCOPE', 'OUT_OF_SCOPE')
                THEN bizinfo_source_records.relevance_verdict
            ELSE p_relevance_verdict
        END,
        change_verdict      = EXCLUDED.change_verdict,
        changed_fields      = EXCLUDED.changed_fields,
        updated_at          = NOW();

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
-- 보안: 함수 실행 권한 제한 (V1과 동일)
-- ────────────────────────────────────────────────────────────────────────────

REVOKE EXECUTE ON FUNCTION public.fn_save_bizinfo_with_notification
    FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.fn_save_bizinfo_with_notification
    TO service_role;
