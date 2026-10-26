-- WO-027-C2-FINAL §2 D1 — evidence_field_candidate CHECK 확장
-- 목적: APPROVED_BY_HUMAN / REJECTED_BY_HUMAN 상태 추가
-- 적용 조건: Owner 별도 실행 승인 후 운영 DB 적용
-- !!! NOT EXECUTED — 별도 명시 승인 없이 실행 금지 !!!

DO $$
DECLARE
  v_conname text;
BEGIN
  -- 테이블 존재 확인
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_name = 'evidence_field_candidate'
  ) THEN
    RAISE EXCEPTION 'ABORT: evidence_field_candidate 테이블 없음';
  END IF;

  -- 기존 status CHECK 제약조건 이름 조회
  SELECT conname INTO v_conname
  FROM pg_constraint
  WHERE conrelid = 'evidence_field_candidate'::regclass
    AND contype = 'c'
    AND pg_get_constraintdef(oid) LIKE '%status%'
  LIMIT 1;

  IF v_conname IS NOT NULL THEN
    EXECUTE format('ALTER TABLE evidence_field_candidate DROP CONSTRAINT %I', v_conname);
    RAISE NOTICE 'D1: 기존 CHECK 제거: %', v_conname;
  END IF;

  -- 신규 CHECK 제약조건 (D1: APPROVED_BY_HUMAN / REJECTED_BY_HUMAN 추가)
  ALTER TABLE evidence_field_candidate
    ADD CONSTRAINT evidence_field_candidate_status_check
      CHECK (status IN (
        'CANDIDATE',
        'NEEDS_HUMAN_REVIEW',
        'AMBIGUOUS',
        'UNRESOLVED',
        'APPROVED_BY_HUMAN',
        'REJECTED_BY_HUMAN'
      ));

  RAISE NOTICE 'D1: evidence_field_candidate CHECK 확장 완료 (APPROVED_BY_HUMAN / REJECTED_BY_HUMAN 추가)';
END;
$$;
