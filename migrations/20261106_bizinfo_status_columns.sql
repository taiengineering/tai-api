-- WO-TAI-BIZINFO-LIFECYCLE-ATOMIC-001 / SQL R1
-- bizinfo_source_records 모집 상태 컬럼 추가
--
-- STATUS: CODE_ONLY — DB 적용 미승인 / Owner DB Gate 필요
-- STOP=GPT_BIZINFO_LIFECYCLE_ATOMIC_SOURCE_IV
--
-- ■ 설계 근거
--   기존 bizinfo_source_records에는 날짜 컬럼이 있으나
--   파생 상태 컬럼이 없어 매 조회 시마다 Python에서 재계산해야 한다.
--   상태를 비정규화 컬럼으로 보관해 "현재 모집 중인 IN_SCOPE 공고" 등
--   운영 조회를 단일 쿼리로 처리한다.
--
-- ■ 상태 컬럼 의미
--   recruitment_status : PROGRAM 모집 상태 (PROGRAM만 사용, EVENT는 NULL)
--     UPCOMING  - 접수 시작 전
--     OPEN      - 접수 중 (start <= today <= end, 양쪽 날짜 필수)
--     CLOSED    - 접수 마감 (today > end)
--     UNKNOWN   - 날짜 없음 / 한쪽 날짜 누락
--
--   reception_status : EVENT 접수 상태 (EVENT만 사용, PROGRAM은 NULL)
--     UPCOMING / OPEN / CLOSED / UNKNOWN (위와 동일 판정)
--
--   progress_status : EVENT 행사 진행 상태 (EVENT만 사용, PROGRAM은 NULL)
--     UPCOMING  - 행사 시작 전
--     ONGOING   - 행사 진행 중 (start <= today <= end, 양쪽 날짜 필수)
--     ENDED     - 행사 종료 (today > end)
--     UNKNOWN   - 날짜 없음 / 한쪽 날짜 누락
--
--   status_as_of : 상태 계산 기준 날짜 (fn_save_bizinfo_with_notification 실행 시각)
--
-- ■ 갱신 주체
--   fn_save_bizinfo_with_notification (20261106_bizinfo_notification_fn_v2.sql)
--   이 함수는 CURRENT_DATE 기준으로 상태를 자동 계산해 저장한다.
--   Python 계층에서 별도 파라미터로 전달하지 않는다.
--
-- ■ relevance_verdict 관계
--   recruitment_status = CLOSED 여도 relevance_verdict = IN_SCOPE 는 보존된다.
--   "안전 관련성"과 "모집 상태"는 독립적인 속성이다.
--
-- ■ 활성화 Gate
--   GATE-DB : Owner DB 승인 → ALTER TABLE 실행
--   GATE-FN : 20261106_bizinfo_notification_fn_v2.sql 등록 (동시 실행)
-- ────────────────────────────────────────────────────────────────────────────

ALTER TABLE public.bizinfo_source_records
    ADD COLUMN IF NOT EXISTS recruitment_status TEXT,
    ADD COLUMN IF NOT EXISTS reception_status   TEXT,
    ADD COLUMN IF NOT EXISTS progress_status    TEXT,
    ADD COLUMN IF NOT EXISTS status_as_of       DATE;

-- CHECK 제약: 허용 값 외 저장 차단
ALTER TABLE public.bizinfo_source_records
    ADD CONSTRAINT chk_bizinfo_recruitment_status
        CHECK (
            recruitment_status IS NULL
            OR recruitment_status IN ('UPCOMING', 'OPEN', 'CLOSED', 'UNKNOWN')
        ),
    ADD CONSTRAINT chk_bizinfo_reception_status
        CHECK (
            reception_status IS NULL
            OR reception_status IN ('UPCOMING', 'OPEN', 'CLOSED', 'UNKNOWN')
        ),
    ADD CONSTRAINT chk_bizinfo_progress_status
        CHECK (
            progress_status IS NULL
            OR progress_status IN ('UPCOMING', 'ONGOING', 'ENDED', 'UNKNOWN')
        );

-- 인덱스: "현재 모집 중인 IN_SCOPE 공고" 조회 최적화
CREATE INDEX IF NOT EXISTS idx_bizinfo_source_records_open_in_scope
    ON public.bizinfo_source_records (source_kind, relevance_verdict, recruitment_status)
    WHERE relevance_verdict = 'IN_SCOPE' AND recruitment_status IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_bizinfo_source_records_event_status
    ON public.bizinfo_source_records (source_kind, relevance_verdict, reception_status, progress_status)
    WHERE source_kind = 'EVENT' AND relevance_verdict = 'IN_SCOPE';

-- ────────────────────────────────────────────────────────────────────────────
-- 기존 1,585건 상태 초기화 (CODE_ONLY — 별도 Owner DB 승인 필요)
--
-- ■ 실행 조건
--   위 ALTER TABLE(GATE-DB) 완료 후
--   fn_save_bizinfo_with_notification V2(GATE-FN) 등록 전에 한 번만 실행한다.
--   V2 fn이 이후 모든 API 수집에서 상태를 자동 갱신하므로
--   이 UPDATE는 V2 fn 등록 이전 기존 행에 대한 일회성 초기화다.
--
-- ■ 갱신 범위
--   status_as_of IS NULL인 행만 대상 (이미 갱신된 행은 건드리지 않음)
--   relevance_verdict 변경 없음
--   retrieved_at(원천 수집일) 변경 없음 — API 재확인과 혼동 금지
--   status_as_of = 이 UPDATE 실행 시각의 KST 날짜 (저장된 날짜 기준 계산)
--
-- ■ 주의
--   이 UPDATE는 저장된 날짜(application_start/end 등)를 기준으로 상태를 계산한다.
--   실제 API 재확인 결과가 아니므로 retrieved_at은 변경하지 않는다.
-- ────────────────────────────────────────────────────────────────────────────

UPDATE public.bizinfo_source_records
SET
    recruitment_status = CASE
        WHEN source_kind = 'PROGRAM' THEN
            CASE
                WHEN application_start IS NULL AND application_end IS NULL   THEN 'UNKNOWN'
                WHEN application_end IS NOT NULL
                     AND (NOW() AT TIME ZONE 'Asia/Seoul')::date > application_end
                                                                             THEN 'CLOSED'
                WHEN application_start IS NOT NULL
                     AND (NOW() AT TIME ZONE 'Asia/Seoul')::date < application_start
                                                                             THEN 'UPCOMING'
                WHEN application_start IS NOT NULL
                     AND application_end IS NOT NULL
                     AND application_start <= (NOW() AT TIME ZONE 'Asia/Seoul')::date
                     AND (NOW() AT TIME ZONE 'Asia/Seoul')::date <= application_end
                                                                             THEN 'OPEN'
                ELSE 'UNKNOWN'
            END
        ELSE NULL
    END,
    reception_status = CASE
        WHEN source_kind = 'EVENT' THEN
            CASE
                WHEN reception_start IS NULL AND reception_end IS NULL       THEN 'UNKNOWN'
                WHEN reception_end IS NOT NULL
                     AND (NOW() AT TIME ZONE 'Asia/Seoul')::date > reception_end
                                                                             THEN 'CLOSED'
                WHEN reception_start IS NOT NULL
                     AND (NOW() AT TIME ZONE 'Asia/Seoul')::date < reception_start
                                                                             THEN 'UPCOMING'
                WHEN reception_start IS NOT NULL
                     AND reception_end IS NOT NULL
                     AND reception_start <= (NOW() AT TIME ZONE 'Asia/Seoul')::date
                     AND (NOW() AT TIME ZONE 'Asia/Seoul')::date <= reception_end
                                                                             THEN 'OPEN'
                ELSE 'UNKNOWN'
            END
        ELSE NULL
    END,
    progress_status = CASE
        WHEN source_kind = 'EVENT' THEN
            CASE
                WHEN event_start IS NULL AND event_end IS NULL               THEN 'UNKNOWN'
                WHEN event_end IS NOT NULL
                     AND (NOW() AT TIME ZONE 'Asia/Seoul')::date > event_end THEN 'ENDED'
                WHEN event_start IS NOT NULL
                     AND (NOW() AT TIME ZONE 'Asia/Seoul')::date < event_start
                                                                             THEN 'UPCOMING'
                WHEN event_start IS NOT NULL
                     AND event_end IS NOT NULL
                     AND event_start <= (NOW() AT TIME ZONE 'Asia/Seoul')::date
                     AND (NOW() AT TIME ZONE 'Asia/Seoul')::date <= event_end
                                                                             THEN 'ONGOING'
                ELSE 'UNKNOWN'
            END
        ELSE NULL
    END,
    status_as_of = (NOW() AT TIME ZONE 'Asia/Seoul')::date
WHERE status_as_of IS NULL;
