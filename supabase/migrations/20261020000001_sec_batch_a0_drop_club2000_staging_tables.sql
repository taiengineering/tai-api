-- SEC-BATCH-A0 R1: WO-TAI-SUPABASE-SEC-BATCH-A0-DISPOSAL-001
-- Club2000 스테이징 테이블 8개 폐기
--
-- 배경:
--   2026-06-10 일회성 ETL로 적재된 Club2000 외부 데이터.
--   테이블에 주민번호, 로그인PW, 보안PW, 계좌번호 등 민감 개인정보 포함.
--   RLS 비활성화 + anon 전 권한 상태로 잔존.
--   소스코드 참조 0건 (org:taiengineering GitHub 전수검색, incomplete_results=false).
--   View/FK/Trigger 의존성 0건 (DB 카탈로그 확인).
--   외부 원본 파일·백업 잔존 여부 UNVERIFIED — 이 Migration은 운영 DB만 대상.
--
-- 대상 테이블 (8개, OID: 76816/76822/76828/76834/76840/76846/76852/76858):
--   stg_club2000_정산세부조회_2026061    (52건)
--   stg_club2000_주문검색_20260610       (39건)
--   stg_club2000_지급마감현황_2           (11건)
--   stg_club2000_지급세부조회_20260610   (283건)
--   stg_club2000_코인현황_20260610       (549건)
--   stg_club2000_포인트조회_20260610     (226건)
--   stg_club2000_포인트현황_20260610     (105건)
--   stg_club2000_회원검색_20260610     (11,223건)
--   합계: 12,488건
--
-- 사전 조건 1: 접두어 'stg_club2000_' (13자 정확 매칭, LIKE 와일드카드 불사용)
--             으로 식별한 테이블이 정확히 8개.
-- 사전 조건 2: 테이블명 집합 MD5 = 2732e5919d43fb3bd90c11fb6a962522
--             (GPT 독립검증 기준값, relname을 ORDER BY 후 개행으로 연결)
-- 불일치 시 전체 롤백.

BEGIN;

DO $$
DECLARE
  v_names  text[];
  v_count  int;
  v_hash   text;
  v_name   text;
BEGIN
  -- STEP 1: 정확한 접두어로 테이블명 배열 수집
  --   left(relname, 13) = 'stg_club2000_' 으로 literal underscore를 포함한
  --   정확한 접두어 비교 (LIKE '_' 와일드카드 문제 제거)
  SELECT array_agg(c.relname ORDER BY c.relname) INTO v_names
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public'
    AND c.relkind = 'r'
    AND left(c.relname, 13) = 'stg_club2000_';

  -- STEP 2: 수량 검증 (8개 정확)
  v_count := coalesce(array_length(v_names, 1), 0);
  IF v_count != 8 THEN
    RAISE EXCEPTION
      'A0-R1 PRE-CONDITION FAILED: expected 8 stg_club2000_ tables, found %. Aborted.',
      v_count;
  END IF;

  -- STEP 3: 집합 무결성 검증 (MD5 — GPT 기준값 2732e5919d43fb3bd90c11fb6a962522)
  v_hash := md5(array_to_string(v_names, E'\n'));
  IF v_hash != '2732e5919d43fb3bd90c11fb6a962522' THEN
    RAISE EXCEPTION
      'A0-R1 INTEGRITY FAILED: table-name set MD5 mismatch. Expected 2732e5919d43fb3bd90c11fb6a962522, got %. Aborted.',
      v_hash;
  END IF;

  -- STEP 4: 검증된 배열로만 DROP — 조회를 다시 하지 않음
  --   format('%I.%I', 'public', v_name) 으로 식별자 안전 인용
  FOREACH v_name IN ARRAY v_names
  LOOP
    EXECUTE format('DROP TABLE %I.%I RESTRICT', 'public', v_name);
    RAISE NOTICE 'A0-R1: dropped public.%', v_name;
  END LOOP;

  -- STEP 5: 사후 검증 — 접두어 테이블 0개 잔존
  SELECT COUNT(*) INTO v_count
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public'
    AND c.relkind = 'r'
    AND left(c.relname, 13) = 'stg_club2000_';

  IF v_count != 0 THEN
    RAISE EXCEPTION
      'A0-R1 POST-CONDITION FAILED: % stg_club2000_ tables remain after drop.',
      v_count;
  END IF;

  RAISE NOTICE 'A0-R1 COMPLETE: 8 Club2000 staging tables removed (12,488 rows).';
END;
$$;

COMMIT;
