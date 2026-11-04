-- WO-TAI-BIZINFO-LIFECYCLE-ATOMIC-001 / SQL R3
-- bizinfo_source_records 기존 1,585건 상태 초기화
--
-- STATUS: CODE_ONLY — DB 적용 미승인 / Owner DB Gate 필요
-- STOP=GPT_BIZINFO_LIFECYCLE_ATOMIC_SOURCE_IV
--
-- ■ 선행 조건
--   20261106_bizinfo_status_columns.sql (GATE-DB-SCHEMA) 완료 필수
--   fn_save_bizinfo_with_notification V2 (GATE-FN) 등록 전에 한 번만 실행
--
-- ■ 승인 범위 분리 근거
--   GATE-DB-SCHEMA  : DDL 변경 (ALTER TABLE, 제약, 인덱스) — 스키마 담당자 승인
--   GATE-DB-BACKFILL: DML 변경 (기존 행 UPDATE) — 데이터 담당자 승인
--   두 Gate 를 동일 파일에 두면 각각의 승인 범위가 불명확해진다.
--
-- ■ 실행 조건
--   GATE-DB-SCHEMA 완료 후
--   GATE-FN(V2 fn) 등록 전에 한 번만 실행한다.
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
