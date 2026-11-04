-- WO-TAI-BIZINFO-DB-APPLY-SQL-FIX-001
-- bizinfo_source_records relevance_verdict 보정 — R2 선별기 기준 적용
--
-- 대상: REVIEW_REQUIRED 17건 → Group A 8건(IN_SCOPE) / Group B 9건(OUT_OF_SCOPE)
-- 조건: source_kind, source_key, relevance_verdict 3-way 일치 — 오적용 방지
-- 보호: PERFORM ... FOR UPDATE 행 잠금 → GET DIAGNOSTICS 건수 검증 → 불일치 시 RAISE EXCEPTION 전체 롤백
-- 실행 전 조건: BIZINFO_STORAGE_ENABLED=1 미활성 (파이프라인 비실행 상태)
-- Owner 승인 후 Supabase SQL 에디터에서 단독 실행

DO $$
DECLARE
  v_pre_check  INTEGER := 0;
  v_rows_a     INTEGER := 0;
  v_rows_b     INTEGER := 0;
BEGIN
  -- ① 사전 검사: 17건 전부 존재 + 기존 판정 확인 (트랜잭션 내, FOR UPDATE 행 잠금)
  --    PERFORM 1 ... FOR UPDATE 로 행을 잠근 뒤 GET DIAGNOSTICS 로 잠긴 행 수를 확인한다.
  --    (SELECT COUNT(*) ... FOR UPDATE 는 PostgreSQL에서 허용되지 않는다)
  PERFORM 1
  FROM bizinfo_source_records
  WHERE (source_kind, source_key, relevance_verdict) IN (
    ('EVENT',   'EVEN_000000000068790', 'REVIEW_REQUIRED'),
    ('EVENT',   'EVEN_000000000069262', 'REVIEW_REQUIRED'),
    ('PROGRAM', 'PBLN_000000000124459', 'REVIEW_REQUIRED'),
    ('PROGRAM', 'PBLN_000000000125095', 'REVIEW_REQUIRED'),
    ('PROGRAM', 'PBLN_000000000126712', 'REVIEW_REQUIRED'),
    ('PROGRAM', 'PBLN_000000000127340', 'REVIEW_REQUIRED'),
    ('PROGRAM', 'PBLN_000000000127526', 'REVIEW_REQUIRED'),
    ('PROGRAM', 'PBLN_000000000127690', 'REVIEW_REQUIRED'),
    ('EVENT',   'EVEN_000000000069758', 'REVIEW_REQUIRED'),
    ('PROGRAM', 'PBLN_000000000117433', 'REVIEW_REQUIRED'),
    ('PROGRAM', 'PBLN_000000000120340', 'REVIEW_REQUIRED'),
    ('PROGRAM', 'PBLN_000000000121165', 'REVIEW_REQUIRED'),
    ('PROGRAM', 'PBLN_000000000121288', 'REVIEW_REQUIRED'),
    ('PROGRAM', 'PBLN_000000000122104', 'REVIEW_REQUIRED'),
    ('PROGRAM', 'PBLN_000000000122516', 'REVIEW_REQUIRED'),
    ('PROGRAM', 'PBLN_000000000123966', 'REVIEW_REQUIRED'),
    ('PROGRAM', 'PBLN_000000000124676', 'REVIEW_REQUIRED')
  )
  FOR UPDATE;
  GET DIAGNOSTICS v_pre_check = ROW_COUNT;

  IF v_pre_check != 17 THEN
    RAISE EXCEPTION
      'Preflight 실패: 17건 중 %건만 존재하거나 기존 판정 불일치 — 실행 중단',
      v_pre_check;
  END IF;

  -- ② Group A: 8건 → IN_SCOPE
  --    안전관리 전문인력 양성, 스마트 안전솔루션, 안전관리시스템 등 직접 안전기술 대상
  UPDATE bizinfo_source_records
    SET relevance_verdict = 'IN_SCOPE',
        updated_at        = now()
  WHERE (source_kind, source_key, relevance_verdict) IN (
    ('EVENT',   'EVEN_000000000068790', 'REVIEW_REQUIRED'),
    ('EVENT',   'EVEN_000000000069262', 'REVIEW_REQUIRED'),
    ('PROGRAM', 'PBLN_000000000124459', 'REVIEW_REQUIRED'),
    ('PROGRAM', 'PBLN_000000000125095', 'REVIEW_REQUIRED'),
    ('PROGRAM', 'PBLN_000000000126712', 'REVIEW_REQUIRED'),
    ('PROGRAM', 'PBLN_000000000127340', 'REVIEW_REQUIRED'),
    ('PROGRAM', 'PBLN_000000000127526', 'REVIEW_REQUIRED'),
    ('PROGRAM', 'PBLN_000000000127690', 'REVIEW_REQUIRED')
  );
  GET DIAGNOSTICS v_rows_a = ROW_COUNT;

  IF v_rows_a != 8 THEN
    RAISE EXCEPTION
      'Group A 실패: 8건 기대, 실제 %건 — 전체 롤백', v_rows_a;
  END IF;

  -- ③ Group B: 9건 → OUT_OF_SCOPE
  --    비안전 목적 명확 (창업지원·금융·마케팅·법률 등), R1 전수검토 후 확정
  UPDATE bizinfo_source_records
    SET relevance_verdict = 'OUT_OF_SCOPE',
        updated_at        = now()
  WHERE (source_kind, source_key, relevance_verdict) IN (
    ('EVENT',   'EVEN_000000000069758', 'REVIEW_REQUIRED'),
    ('PROGRAM', 'PBLN_000000000117433', 'REVIEW_REQUIRED'),
    ('PROGRAM', 'PBLN_000000000120340', 'REVIEW_REQUIRED'),
    ('PROGRAM', 'PBLN_000000000121165', 'REVIEW_REQUIRED'),
    ('PROGRAM', 'PBLN_000000000121288', 'REVIEW_REQUIRED'),
    ('PROGRAM', 'PBLN_000000000122104', 'REVIEW_REQUIRED'),
    ('PROGRAM', 'PBLN_000000000122516', 'REVIEW_REQUIRED'),
    ('PROGRAM', 'PBLN_000000000123966', 'REVIEW_REQUIRED'),
    ('PROGRAM', 'PBLN_000000000124676', 'REVIEW_REQUIRED')
  );
  GET DIAGNOSTICS v_rows_b = ROW_COUNT;

  IF v_rows_b != 9 THEN
    RAISE EXCEPTION
      'Group B 실패: 9건 기대, 실제 %건 — 전체 롤백', v_rows_b;
  END IF;

  RAISE NOTICE 'DB 반영 완료: Group A=% (IN_SCOPE), Group B=% (OUT_OF_SCOPE)',
    v_rows_a, v_rows_b;
END;
$$;

-- ④ 반영 후 검증 쿼리 (DO 블록 커밋 후 별도 실행)
-- 기대 결과: IN_SCOPE 8건, OUT_OF_SCOPE 9건
SELECT
  relevance_verdict,
  COUNT(*) AS cnt
FROM bizinfo_source_records
WHERE (source_kind, source_key) IN (
  ('EVENT',   'EVEN_000000000068790'), ('EVENT',   'EVEN_000000000069262'),
  ('PROGRAM', 'PBLN_000000000124459'), ('PROGRAM', 'PBLN_000000000125095'),
  ('PROGRAM', 'PBLN_000000000126712'), ('PROGRAM', 'PBLN_000000000127340'),
  ('PROGRAM', 'PBLN_000000000127526'), ('PROGRAM', 'PBLN_000000000127690'),
  ('EVENT',   'EVEN_000000000069758'),
  ('PROGRAM', 'PBLN_000000000117433'), ('PROGRAM', 'PBLN_000000000120340'),
  ('PROGRAM', 'PBLN_000000000121165'), ('PROGRAM', 'PBLN_000000000121288'),
  ('PROGRAM', 'PBLN_000000000122104'), ('PROGRAM', 'PBLN_000000000122516'),
  ('PROGRAM', 'PBLN_000000000123966'), ('PROGRAM', 'PBLN_000000000124676')
)
GROUP BY relevance_verdict
ORDER BY relevance_verdict;
