-- WO-TAI-DOC260-OBJ10-WAVE1-SAMPLE-AUTO-VERIFY-001
-- 목적: runtime_field CHECK 제약조건에 SOURCE_VERIFIED / REQUIRED_FROM_SOURCE 추가
-- 대상: chk_rf_status (status), chk_rf_required (required_status)
-- !!! NOT EXECUTED — Owner 별도 실행 승인 후 운영 DB 적용 !!!

DO $$
DECLARE
  v_status_con text;
  v_required_con text;
BEGIN
  -- 테이블 존재 확인
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_name = 'runtime_field'
  ) THEN
    RAISE EXCEPTION 'ABORT: runtime_field 테이블 없음';
  END IF;

  -- 기존 status CHECK 제약조건 이름 조회
  SELECT conname INTO v_status_con
  FROM pg_constraint
  WHERE conrelid = 'runtime_field'::regclass
    AND contype = 'c'
    AND pg_get_constraintdef(oid) LIKE '%status%'
    AND pg_get_constraintdef(oid) NOT LIKE '%required_status%'
  LIMIT 1;

  IF v_status_con IS NOT NULL THEN
    EXECUTE format('ALTER TABLE runtime_field DROP CONSTRAINT %I', v_status_con);
    RAISE NOTICE 'status CHECK 제거: %', v_status_con;
  END IF;

  -- 신규 status CHECK 제약조건 (SOURCE_VERIFIED 추가)
  ALTER TABLE runtime_field
    ADD CONSTRAINT chk_rf_status
      CHECK (status IN (
        'CANDIDATE',
        'NEEDS_HUMAN_REVIEW',
        'APPROVED_BY_HUMAN',
        'REJECTED_BY_HUMAN',
        'SOURCE_VERIFIED'
      ));

  RAISE NOTICE 'chk_rf_status 갱신 완료 (SOURCE_VERIFIED 추가)';

  -- 기존 required_status CHECK 제약조건 이름 조회
  SELECT conname INTO v_required_con
  FROM pg_constraint
  WHERE conrelid = 'runtime_field'::regclass
    AND contype = 'c'
    AND pg_get_constraintdef(oid) LIKE '%required_status%'
  LIMIT 1;

  IF v_required_con IS NOT NULL THEN
    EXECUTE format('ALTER TABLE runtime_field DROP CONSTRAINT %I', v_required_con);
    RAISE NOTICE 'required_status CHECK 제거: %', v_required_con;
  END IF;

  -- 신규 required_status CHECK 제약조건 (REQUIRED_FROM_SOURCE 추가)
  ALTER TABLE runtime_field
    ADD CONSTRAINT chk_rf_required
      CHECK (required_status IN (
        'CANDIDATE_ONLY',
        'NEEDS_HUMAN_REVIEW',
        'REQUIRED_BY_HUMAN',
        'NOT_REQUIRED',
        'REQUIRED_FROM_SOURCE'
      ));

  RAISE NOTICE 'chk_rf_required 갱신 완료 (REQUIRED_FROM_SOURCE 추가)';

  RAISE NOTICE 'WAVE1 CHECK 제약조건 확장 완료';
END;
$$;
