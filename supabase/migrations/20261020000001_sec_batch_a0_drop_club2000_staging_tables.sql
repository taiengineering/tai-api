-- SEC-BATCH-A0: WO-TAI-SUPABASE-SEC-BATCH-A0-DISPOSAL-001
-- Club2000 스테이징 테이블 8개 폐기
--
-- 배경:
--   2026-06-10 일회성 ETL로 적재된 Club2000 외부 데이터.
--   테이블에 주민번호, 로그인PW, 보안PW, 계좌번호 등 민감 개인정보 포함.
--   RLS 비활성화 + anon 전 권한 상태로 잔존.
--   소스코드 참조 0건 (org:taiengineering GitHub 전수검색, incomplete_results=false).
--   View/FK/Trigger 의존성 0건 (DB 카탈로그 확인).
--   더 이상 사용되지 않는 임시 데이터로 폐기 결정.
--
-- 대상 테이블 (8개, OID 기준 확인: 76816~76858):
--   stg_club2000_정산세부조회_2026061
--   stg_club2000_주문검색_20260610
--   stg_club2000_지급마감현황_2
--   stg_club2000_지급세부조회_20260610
--   stg_club2000_코인현황_20260610
--   stg_club2000_포인트조회_20260610
--   stg_club2000_포인트현황_20260610
--   stg_club2000_회원검색_20260610
--
-- 사전 조건: public 스키마에 stg_club2000% 테이블이 정확히 8개 존재해야 실행.
-- 하나라도 불일치 시 전체 롤백.

BEGIN;

DO $$
DECLARE
  v_count int;
  v_tbl   record;
BEGIN
  -- 사전 조건 검증: 정확히 8개만 존재해야 함
  SELECT COUNT(*) INTO v_count
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public'
    AND c.relkind = 'r'
    AND c.relname LIKE 'stg_club2000%';

  IF v_count != 8 THEN
    RAISE EXCEPTION
      'A0-DISPOSAL PRE-CONDITION FAILED: expected 8 stg_club2000 tables, found %. Migration aborted.',
      v_count;
  END IF;

  -- 테이블별 DROP (RESTRICT — CASCADE 사용 금지)
  FOR v_tbl IN
    SELECT c.relname
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relkind = 'r'
      AND c.relname LIKE 'stg_club2000%'
    ORDER BY c.relname
  LOOP
    EXECUTE format('DROP TABLE public.%I RESTRICT', v_tbl.relname);
    RAISE NOTICE 'A0-DISPOSAL: dropped %', v_tbl.relname;
  END LOOP;

  -- 사후 검증: stg_club2000% 테이블이 0개여야 함
  SELECT COUNT(*) INTO v_count
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public'
    AND c.relkind = 'r'
    AND c.relname LIKE 'stg_club2000%';

  IF v_count != 0 THEN
    RAISE EXCEPTION
      'A0-DISPOSAL POST-CONDITION FAILED: % stg_club2000 tables remain after drop.',
      v_count;
  END IF;

  RAISE NOTICE 'A0-DISPOSAL COMPLETE: 8 Club2000 staging tables removed.';
END;
$$;

COMMIT;
