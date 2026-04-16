-- ============================================================
-- 롤백 스크립트: factory_diagnosis_results v2026.04 전환 취소
-- 작성일: 2026-04-16
-- 대상: 모든 schema_version='2026.04' 레코드
-- 내용: 사전 백업 테이블(diagnosis_results_backup_20260416)에서 전체 복원
-- ============================================================

-- 단계 1: 백업 테이블 존재 확인
DO $$
DECLARE v_backup_cnt int;
BEGIN
  SELECT COUNT(*) INTO v_backup_cnt FROM diagnosis_results_backup_20260416;
  IF v_backup_cnt < 43 THEN
    RAISE EXCEPTION '백업 테이블 이상: %건. 롤백 중단.', v_backup_cnt;
  END IF;
  RAISE NOTICE '백업 테이블 확인: %건', v_backup_cnt;
END$$;

-- 단계 2: 현재 테이블 전체 복원
-- (주의: 변환 후 생성된 신규 레코드는 복원되지 않음)
TRUNCATE TABLE factory_diagnosis_results;

INSERT INTO factory_diagnosis_results
SELECT * FROM diagnosis_results_backup_20260416;

-- 단계 3: 복원 후 확인
DO $$
DECLARE
  v_restored int;
  v_v2 int;
BEGIN
  SELECT COUNT(*) INTO v_restored FROM factory_diagnosis_results;
  SELECT COUNT(*) INTO v_v2 FROM factory_diagnosis_results WHERE schema_version = '2026.04';
  RAISE NOTICE '복원 완료: 전체 %건, 2026.04 버전 %건 (복원 후에는 legacy여야 정상)', v_restored, v_v2;
END$$;

-- 단계 4: 백업 테이블 삭제 (롤백 확인 후 수동 실행)
-- DROP TABLE IF EXISTS diagnosis_results_backup_20260416;
