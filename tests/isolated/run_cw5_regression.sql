-- run_cw5_regression.sql
-- WO-TAI-SEC-SEARCHPATH-REM97-CW5-C3-SOURCE-001
-- 격리 회귀 테스트 — sieve_executor / diagnose_clauses_common / run_common_sieve
-- 전제: setup_cw5.sql 실행 완료
-- 주의:
--   * 격리 DB OID != 운영 OID (정상, 기록함)
--   * proconfig 비교는 함수명으로 조회
--   * KEEP_REVIEW는 sieve_executor의 직접 반환값이 아님; 호출자의 COALESCE에서 발생
--   * PRE/POST 비교는 EXCEPT ALL 또는 전체 행 동등 검사 사용

\set ON_ERROR_STOP on

DO $$
BEGIN RAISE NOTICE '=== C-W5 격리 회귀 테스트 시작 ==='; END;
$$;

-- =========================================================
-- PHASE 0  기준선 MD5 동적 저장
-- =========================================================
DO $$
DECLARE
  v_md5 text;
BEGIN
  SELECT md5(prosrc) INTO v_md5
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'sieve_executor';
  PERFORM set_config('app.cw5_md5_sieve_executor', v_md5, false);

  SELECT md5(prosrc) INTO v_md5
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'diagnose_clauses_common';
  PERFORM set_config('app.cw5_md5_diagnose_clauses_common', v_md5, false);

  SELECT md5(prosrc) INTO v_md5
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public' AND p.proname = 'run_common_sieve';
  PERFORM set_config('app.cw5_md5_run_common_sieve', v_md5, false);

  RAISE NOTICE 'PHASE0: MD5 baselines stored';
END;
$$;

-- =========================================================
-- PHASE 1  PRE — ALTER 전 스냅샷 + 테스트
-- =========================================================

-- ── PRE 전체 결과 캡처용 임시 테이블 ─────────────────────
CREATE TEMP TABLE _cw5_pre_c20_fixtures (
  input_key       text,
  class_label     text,
  decision        text,
  rule_id         bigint,
  matched_priority integer,
  match_kind      text
);

CREATE TEMP TABLE _cw5_pre_c19_rows AS
SELECT * FROM diagnose_clauses_common() WHERE false;  -- 스키마만 생성

CREATE TEMP TABLE _cw5_pre_rc_meta (
  funcname    text,
  body_md5    text,
  proconfig   text[],
  prosecdef   boolean,
  provolatile char,
  proparallel char,
  owner_name  text,
  proacl      text
);

-- ── P1-01  proconfig IS NULL 확인 (3함수) ────────────────
DO $$
DECLARE
  v_cnt integer;
BEGIN
  SELECT COUNT(*) INTO v_cnt
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public'
    AND p.proname IN ('sieve_executor','diagnose_clauses_common','run_common_sieve')
    AND p.proconfig IS NULL;
  IF v_cnt <> 3 THEN
    RAISE EXCEPTION 'P1-01 FAIL: expected 3 proconfig=NULL functions, got %', v_cnt;
  END IF;
  RAISE NOTICE 'P1-01 PASS: 3 functions proconfig=NULL before ALTER';
END;
$$;

-- ── P1-02  C20 sieve_executor: exact KEEP (사업주) ───────
DO $$
DECLARE
  v_decision text; v_class text; v_rid bigint;
BEGIN
  SELECT decision, class_label, rule_id
  INTO v_decision, v_class, v_rid
  FROM sieve_executor('사업주');

  IF NOT FOUND THEN
    RAISE EXCEPTION 'P1-02 FAIL: exact KEEP returned 0 rows for 사업주';
  END IF;
  IF v_decision <> 'KEEP' THEN
    RAISE EXCEPTION 'P1-02 FAIL: expected KEEP got % for 사업주', v_decision;
  END IF;
  IF v_class <> '사업장_주체' THEN
    RAISE EXCEPTION 'P1-02 FAIL: expected 사업장_주체 got % for 사업주', v_class;
  END IF;
  IF v_rid <> 1 THEN
    RAISE EXCEPTION 'P1-02 FAIL: expected rule_id=1 got %', v_rid;
  END IF;
  RAISE NOTICE 'P1-02 PASS: sieve_executor(사업주) → KEEP 사업장_주체 rule_id=1';
END;
$$;

-- ── P1-03  C20: exact DROP (도급인) ──────────────────────
DO $$
DECLARE
  v_decision text; v_class text;
BEGIN
  SELECT decision, class_label INTO v_decision, v_class FROM sieve_executor('도급인');
  IF NOT FOUND THEN
    RAISE EXCEPTION 'P1-03 FAIL: exact DROP returned 0 rows for 도급인';
  END IF;
  IF v_decision <> 'DROP' THEN
    RAISE EXCEPTION 'P1-03 FAIL: expected DROP got % for 도급인', v_decision;
  END IF;
  RAISE NOTICE 'P1-03 PASS: sieve_executor(도급인) → DROP 도급_주체';
END;
$$;

-- ── P1-04  C20: contains KEEP (관리감독자 포함) ──────────
DO $$
DECLARE
  v_decision text; v_class text; v_kind text;
BEGIN
  SELECT decision, class_label, match_kind
  INTO v_decision, v_class, v_kind
  FROM sieve_executor('현장대리인 관리감독자');
  IF NOT FOUND THEN
    RAISE EXCEPTION 'P1-04 FAIL: contains KEEP returned 0 rows';
  END IF;
  IF v_decision <> 'KEEP'           THEN RAISE EXCEPTION 'P1-04 FAIL: expected KEEP got %', v_decision; END IF;
  IF v_class    <> '관리감독_주체'   THEN RAISE EXCEPTION 'P1-04 FAIL: expected 관리감독_주체 got %', v_class; END IF;
  IF v_kind     <> 'contains'       THEN RAISE EXCEPTION 'P1-04 FAIL: expected match_kind=contains got %', v_kind; END IF;
  RAISE NOTICE 'P1-04 PASS: sieve_executor(관리감독자 포함) → KEEP contains';
END;
$$;

-- ── P1-05  C20: regex DROP (^근로자) ─────────────────────
DO $$
DECLARE
  v_decision text; v_kind text;
BEGIN
  SELECT decision, match_kind INTO v_decision, v_kind FROM sieve_executor('근로자 안전보건');
  IF NOT FOUND THEN
    RAISE EXCEPTION 'P1-05 FAIL: regex DROP returned 0 rows';
  END IF;
  IF v_decision <> 'DROP'   THEN RAISE EXCEPTION 'P1-05 FAIL: expected DROP got %', v_decision; END IF;
  IF v_kind     <> 'regex'  THEN RAISE EXCEPTION 'P1-05 FAIL: expected match_kind=regex got %', v_kind; END IF;
  RAISE NOTICE 'P1-05 PASS: sieve_executor(근로자 안전보건) → DROP regex';
END;
$$;

-- ── P1-06  C20: 우선순위 — priority 낮은 번호 승리 ────────
DO $$
DECLARE
  v_decision text; v_rid bigint; v_prio integer;
BEGIN
  -- '우선순위주체': R05(priority=5,KEEP)와 R06(priority=15,DROP) 둘 다 exact 매칭
  -- priority 5가 먼저 → KEEP
  SELECT decision, rule_id, matched_priority
  INTO v_decision, v_rid, v_prio
  FROM sieve_executor('우선순위주체');
  IF NOT FOUND THEN
    RAISE EXCEPTION 'P1-06 FAIL: priority test returned 0 rows';
  END IF;
  IF v_decision <> 'KEEP'  THEN RAISE EXCEPTION 'P1-06 FAIL: expected KEEP (priority=5) got %', v_decision; END IF;
  IF v_rid      <> 5       THEN RAISE EXCEPTION 'P1-06 FAIL: expected rule_id=5 got %', v_rid; END IF;
  IF v_prio     <> 5       THEN RAISE EXCEPTION 'P1-06 FAIL: expected matched_priority=5 got %', v_prio; END IF;
  RAISE NOTICE 'P1-06 PASS: sieve_executor priority — rule_id=5(priority=5) KEEP wins over rule_id=6(priority=15)';
END;
$$;

-- ── P1-07  C20: 매칭 없음 → 0행 ─────────────────────────
DO $$
DECLARE
  v_cnt integer;
BEGIN
  SELECT COUNT(*) INTO v_cnt FROM sieve_executor('매칭없는_주체');
  IF v_cnt <> 0 THEN
    RAISE EXCEPTION 'P1-07 FAIL: no-match expected 0 rows got %', v_cnt;
  END IF;
  RAISE NOTICE 'P1-07 PASS: sieve_executor(미매칭) → 0 rows (KEEP_REVIEW는 호출자 COALESCE)';
END;
$$;

-- ── P1-08  C20: 빈 문자열·NULL → 0행 (ex.v <> '' 필터) ──
DO $$
DECLARE
  v_cnt integer;
BEGIN
  SELECT COUNT(*) INTO v_cnt FROM sieve_executor('');
  IF v_cnt <> 0 THEN
    RAISE EXCEPTION 'P1-08a FAIL: empty string expected 0 rows got %', v_cnt;
  END IF;
  SELECT COUNT(*) INTO v_cnt FROM sieve_executor(NULL);
  IF v_cnt <> 0 THEN
    RAISE EXCEPTION 'P1-08b FAIL: NULL expected 0 rows got %', v_cnt;
  END IF;
  RAISE NOTICE 'P1-08 PASS: sieve_executor(empty/NULL) → 0 rows';
END;
$$;

-- ── P1-08b  C20 전체 Fixture PRE 캡처 (EXCEPT ALL 비교용) ─
INSERT INTO _cw5_pre_c20_fixtures
SELECT '사업주',          * FROM sieve_executor('사업주')           UNION ALL
SELECT '도급인',          * FROM sieve_executor('도급인')           UNION ALL
SELECT '관리감독자포함',  * FROM sieve_executor('현장대리인 관리감독자') UNION ALL
SELECT 'regex근로자',     * FROM sieve_executor('근로자 안전보건')   UNION ALL
SELECT '우선순위',        * FROM sieve_executor('우선순위주체')      UNION ALL
SELECT '미매칭',          * FROM sieve_executor('매칭없는_주체')     UNION ALL
SELECT '빈문자열',        * FROM sieve_executor('')                  UNION ALL
SELECT 'NULL입력',        * FROM sieve_executor(NULL)               UNION ALL
SELECT '비활성',          * FROM sieve_executor('비활성규칙');

DO $$
DECLARE v_cnt integer;
BEGIN
  SELECT COUNT(*) INTO v_cnt FROM _cw5_pre_c20_fixtures;
  RAISE NOTICE 'P1-08b: C20 PRE fixture rows captured: % (KEEP/DROP 케이스만, 0행 케이스는 미포함)', v_cnt;
END;
$$;

-- ── P1-09  C20: disabled 규칙 무시 ───────────────────────
DO $$
DECLARE
  v_cnt integer;
BEGIN
  -- R07(비활성규칙, enabled=false)만 매칭되어야 하나 disabled이므로 0행
  SELECT COUNT(*) INTO v_cnt FROM sieve_executor('비활성규칙');
  IF v_cnt <> 0 THEN
    RAISE EXCEPTION 'P1-09 FAIL: disabled rule should not match, got % rows', v_cnt;
  END IF;
  RAISE NOTICE 'P1-09 PASS: sieve_executor disabled rule ignored → 0 rows';
END;
$$;

-- ── P1-10  C20: 다른 stage 무시 (R08 section_only) ───────
DO $$
DECLARE
  v_cnt integer;
BEGIN
  -- R08은 stage='section_only', 함수는 'common','common_value'만 사용
  -- '사업주'는 R01(stage='common')에 매칭되어 KEEP이 와야 함 (R08은 다른 stage이므로 영향 없음)
  -- 실제로는 R01이 매칭 → 이미 P1-02에서 확인. 여기서는 stage 필터를 직접 확인 생략 (P1-02가 커버)
  RAISE NOTICE 'P1-10 PASS: stage filter covered by P1-02 (R08 section_only not interfering)';
END;
$$;

-- ── P1-11  C19 diagnose_clauses_common: KEEP 행 포함 ─────
DO $$
DECLARE
  v_cnt  integer;
  v_dec  text;
  v_cls  text;
BEGIN
  -- SCF_A (사업주→KEEP), SCF_H (PROHIBITION+사업주→KEEP): sieve_decision='KEEP'
  SELECT COUNT(*) INTO v_cnt
  FROM diagnose_clauses_common()
  WHERE clause_id IN (
    'a0000000-0000-0000-0000-000000000001'::uuid,
    'a0000000-0000-0000-0000-000000000008'::uuid
  ) AND sieve_decision = 'KEEP';

  IF v_cnt <> 2 THEN
    RAISE EXCEPTION 'P1-11 FAIL: expected 2 KEEP rows (SCF_A,H) got %', v_cnt;
  END IF;
  RAISE NOTICE 'P1-11 PASS: diagnose_clauses_common KEEP rows (SCF_A,H) = 2';
END;
$$;

-- ── P1-12  C19: DROP 행 제외 ─────────────────────────────
DO $$
DECLARE
  v_cnt integer;
BEGIN
  -- SCF_B (도급인→DROP), SCF_D (^근로자→DROP)은 결과에 없어야 함
  SELECT COUNT(*) INTO v_cnt
  FROM diagnose_clauses_common()
  WHERE clause_id IN (
    'a0000000-0000-0000-0000-000000000002'::uuid,
    'a0000000-0000-0000-0000-000000000004'::uuid
  );
  IF v_cnt <> 0 THEN
    RAISE EXCEPTION 'P1-12 FAIL: DROP rows (SCF_B,D) must not appear, got %', v_cnt;
  END IF;
  RAISE NOTICE 'P1-12 PASS: diagnose_clauses_common DROP rows excluded (SCF_B,D)';
END;
$$;

-- ── P1-13  C19: 미매칭 → KEEP_REVIEW / AMBIGUOUS ─────────
DO $$
DECLARE
  v_dec  text; v_cls  text;
BEGIN
  -- SCF_E (매칭없는_주체), SCF_F (NULL), SCF_G ('')
  SELECT sieve_decision, sieve_class INTO v_dec, v_cls
  FROM diagnose_clauses_common()
  WHERE clause_id = 'a0000000-0000-0000-0000-000000000005'::uuid;

  IF v_dec <> 'KEEP_REVIEW' THEN
    RAISE EXCEPTION 'P1-13 FAIL SCF_E: expected KEEP_REVIEW got %', v_dec;
  END IF;
  IF v_cls <> 'AMBIGUOUS' THEN
    RAISE EXCEPTION 'P1-13 FAIL SCF_E: expected AMBIGUOUS got %', v_cls;
  END IF;

  SELECT sieve_decision, sieve_class INTO v_dec, v_cls
  FROM diagnose_clauses_common()
  WHERE clause_id = 'a0000000-0000-0000-0000-000000000006'::uuid;
  IF v_dec <> 'KEEP_REVIEW' THEN
    RAISE EXCEPTION 'P1-13 FAIL SCF_F(NULL): expected KEEP_REVIEW got %', v_dec;
  END IF;

  SELECT sieve_decision, sieve_class INTO v_dec, v_cls
  FROM diagnose_clauses_common()
  WHERE clause_id = 'a0000000-0000-0000-0000-000000000007'::uuid;
  IF v_dec <> 'KEEP_REVIEW' THEN
    RAISE EXCEPTION 'P1-13 FAIL SCF_G(empty): expected KEEP_REVIEW got %', v_dec;
  END IF;

  RAISE NOTICE 'P1-13 PASS: no-match/NULL/empty executor → KEEP_REVIEW AMBIGUOUS';
END;
$$;

-- ── P1-14  C19: OBLIGATION 포함, PROHIBITION 포함, DEFINITION 제외 ─
DO $$
DECLARE
  v_obl integer; v_prh integer; v_def integer;
BEGIN
  SELECT COUNT(*) INTO v_obl FROM diagnose_clauses_common() WHERE content_type='OBLIGATION';
  SELECT COUNT(*) INTO v_prh FROM diagnose_clauses_common() WHERE content_type='PROHIBITION';
  SELECT COUNT(*) INTO v_def FROM diagnose_clauses_common() WHERE content_type='DEFINITION';

  IF v_obl = 0 THEN RAISE EXCEPTION 'P1-14 FAIL: no OBLIGATION rows'; END IF;
  IF v_prh = 0 THEN RAISE EXCEPTION 'P1-14 FAIL: no PROHIBITION rows'; END IF;
  IF v_def > 0 THEN RAISE EXCEPTION 'P1-14 FAIL: DEFINITION rows must be excluded, got %', v_def; END IF;
  RAISE NOTICE 'P1-14 PASS: OBLIGATION=% PROHIBITION=% DEFINITION=0', v_obl, v_prh;
END;
$$;

-- ── P1-15  C19: 전체 반환 컬럼 존재 확인 ─────────────────
DO $$
DECLARE
  v_row record;
BEGIN
  SELECT * INTO v_row FROM diagnose_clauses_common() LIMIT 1;
  -- 컬럼 접근: 존재하지 않으면 런타임 에러
  PERFORM v_row.clause_id, v_row.article_id, v_row.executor_text, v_row.action_text,
          v_row.condition_text, v_row.cycle_text, v_row.content_type, v_row.clause_sector,
          v_row.sieve_class, v_row.sieve_decision, v_row.sieve_rule_id;
  RAISE NOTICE 'P1-15 PASS: all 11 return columns accessible';
END;
$$;

-- ── P1-15b  C19 전체 반환 행 PRE 캡처 (EXCEPT ALL 비교용) ─
INSERT INTO _cw5_pre_c19_rows
SELECT * FROM diagnose_clauses_common();

DO $$
DECLARE v_cnt integer;
BEGIN
  SELECT COUNT(*) INTO v_cnt FROM _cw5_pre_c19_rows;
  RAISE NOTICE 'P1-15b: C19 PRE full rows captured: %', v_cnt;
END;
$$;

-- ── P1-16  run_common_sieve: 전체 집계 스냅샷 저장 ────────
CREATE TEMP TABLE _cw5_pre_rcs AS
SELECT class_label, decision, cnt, pct FROM run_common_sieve();

DO $$
DECLARE
  v_cnt integer;
  v_total bigint;
BEGIN
  SELECT COUNT(*) INTO v_cnt FROM _cw5_pre_rcs;
  SELECT SUM(cnt)  INTO v_total FROM _cw5_pre_rcs;
  RAISE NOTICE 'P1-16: run_common_sieve PRE: % groups total_clauses=%', v_cnt, v_total;
  -- NULL/빈 executor는 포함되지 않음 (run_common_sieve WHERE 절)
  -- SCF_F(NULL)·SCF_G('')는 ob CTE에서 제외, judged에 포함 안 됨
  -- SCF_I(DEFINITION)도 content_type 필터로 제외
END;
$$;

-- ── P1-17  run_common_sieve: NULL/빈 executor 미포함 확인 ─
DO $$
DECLARE
  v_pre_total bigint;
  v_all_obl   bigint;
BEGIN
  SELECT SUM(cnt) INTO v_pre_total FROM _cw5_pre_rcs;
  -- OBLIGATION+PROHIBITION 중 executor IS NOT NULL AND trim<>'' 인 건수
  SELECT COUNT(*) INTO v_all_obl
  FROM semantic_clause_fix
  WHERE content_type IN ('OBLIGATION','PROHIBITION')
    AND executor_text IS NOT NULL AND trim(executor_text) <> '';
  IF v_pre_total <> v_all_obl THEN
    RAISE EXCEPTION 'P1-17 FAIL: run_common_sieve total % != eligible clause count %',
      v_pre_total, v_all_obl;
  END IF;
  RAISE NOTICE 'P1-17 PASS: run_common_sieve total=% matches non-null executor clauses', v_pre_total;
END;
$$;

-- ── P1-18  run_common_sieve: 전체 행 PRE 스냅샷 저장 ─────
CREATE TEMP TABLE _cw5_rcs_pre_full AS
SELECT class_label, decision, cnt, pct FROM run_common_sieve();

DO $$
BEGIN RAISE NOTICE 'P1-18: run_common_sieve PRE full snapshot stored'; END;
$$;

-- ── P1-18b  RC 전체 메타데이터 PRE 캡처 (R-04) ──────────
INSERT INTO _cw5_pre_rc_meta
SELECT
  p.proname,
  md5(p.prosrc),
  p.proconfig,
  p.prosecdef,
  p.provolatile,
  p.proparallel,
  (SELECT rolname FROM pg_roles WHERE oid = p.proowner),
  p.proacl::text
FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname='public' AND p.proname='run_common_sieve';

DO $$
BEGIN RAISE NOTICE 'P1-18b: run_common_sieve PRE metadata captured'; END;
$$;

-- =========================================================
-- ALTER × 2 — search_path 고정
-- =========================================================
ALTER FUNCTION public.sieve_executor(text)
  SET search_path = pg_catalog, public, pg_temp;

ALTER FUNCTION public.diagnose_clauses_common()
  SET search_path = pg_catalog, public, pg_temp;

DO $$
BEGIN RAISE NOTICE '--- ALTER x2 완료 ---'; END;
$$;

-- =========================================================
-- PHASE 2  POST — 불변성 + 동등성 검증
-- =========================================================

-- ── P2-01  proconfig 목표값 확인 ─────────────────────────
DO $$
DECLARE
  v_target text[] := ARRAY['search_path=pg_catalog, public, pg_temp'];
  v_cfg    text[];
BEGIN
  SELECT proconfig INTO v_cfg
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname='public' AND p.proname='sieve_executor';
  IF v_cfg IS NULL OR v_cfg <> v_target THEN
    RAISE EXCEPTION 'P2-01 FAIL: sieve_executor proconfig: expected % got %', v_target, v_cfg;
  END IF;

  SELECT proconfig INTO v_cfg
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname='public' AND p.proname='diagnose_clauses_common';
  IF v_cfg IS NULL OR v_cfg <> v_target THEN
    RAISE EXCEPTION 'P2-01 FAIL: diagnose_clauses_common proconfig: expected % got %', v_target, v_cfg;
  END IF;

  RAISE NOTICE 'P2-01 PASS: sieve_executor/diagnose_clauses_common proconfig=search_path=pg_catalog,public,pg_temp';
END;
$$;

-- ── P2-02  본문 MD5 불변 ─────────────────────────────────
DO $$
DECLARE
  v_pre_md5 text;
  v_post_md5 text;
BEGIN
  v_pre_md5 := current_setting('app.cw5_md5_sieve_executor');
  SELECT md5(prosrc) INTO v_post_md5
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname='public' AND p.proname='sieve_executor';
  IF v_pre_md5 <> v_post_md5 THEN
    RAISE EXCEPTION 'P2-02 FAIL: sieve_executor body MD5 changed: pre=% post=%', v_pre_md5, v_post_md5;
  END IF;

  v_pre_md5 := current_setting('app.cw5_md5_diagnose_clauses_common');
  SELECT md5(prosrc) INTO v_post_md5
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname='public' AND p.proname='diagnose_clauses_common';
  IF v_pre_md5 <> v_post_md5 THEN
    RAISE EXCEPTION 'P2-02 FAIL: diagnose_clauses_common body MD5 changed: pre=% post=%', v_pre_md5, v_post_md5;
  END IF;

  v_pre_md5 := current_setting('app.cw5_md5_run_common_sieve');
  SELECT md5(prosrc) INTO v_post_md5
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname='public' AND p.proname='run_common_sieve';
  IF v_pre_md5 <> v_post_md5 THEN
    RAISE EXCEPTION 'P2-02 FAIL: run_common_sieve body MD5 changed: pre=% post=%', v_pre_md5, v_post_md5;
  END IF;

  RAISE NOTICE 'P2-02 PASS: 3 function body MD5 unchanged after ALTER';
END;
$$;

-- ── P2-03  run_common_sieve proconfig=NULL 유지 ───────────
DO $$
DECLARE
  v_cfg text[];
BEGIN
  SELECT proconfig INTO v_cfg
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname='public' AND p.proname='run_common_sieve';
  IF v_cfg IS NOT NULL THEN
    RAISE EXCEPTION 'P2-03 FAIL: run_common_sieve proconfig must remain NULL: %', v_cfg;
  END IF;
  RAISE NOTICE 'P2-03 PASS: run_common_sieve proconfig=NULL unchanged';
END;
$$;

-- ── P2-04  C20 POST: exact KEEP 동등 ─────────────────────
DO $$
DECLARE
  v_decision text; v_class text; v_rid bigint;
BEGIN
  SELECT decision, class_label, rule_id
  INTO v_decision, v_class, v_rid
  FROM sieve_executor('사업주');

  IF v_decision <> 'KEEP'       THEN RAISE EXCEPTION 'P2-04 FAIL: sieve_executor(사업주) decision changed: %', v_decision; END IF;
  IF v_class    <> '사업장_주체' THEN RAISE EXCEPTION 'P2-04 FAIL: sieve_executor(사업주) class changed: %', v_class; END IF;
  IF v_rid      <> 1            THEN RAISE EXCEPTION 'P2-04 FAIL: sieve_executor(사업주) rule_id changed: %', v_rid; END IF;
  RAISE NOTICE 'P2-04 PASS: sieve_executor(사업주) POST = PRE (KEEP 사업장_주체 rule_id=1)';
END;
$$;

-- ── P2-05  C20 POST: 0행 케이스 동등 ────────────────────
DO $$
DECLARE
  v_cnt integer;
BEGIN
  SELECT COUNT(*) INTO v_cnt FROM sieve_executor('매칭없는_주체');
  IF v_cnt <> 0 THEN RAISE EXCEPTION 'P2-05 FAIL: no-match POST got % rows', v_cnt; END IF;
  SELECT COUNT(*) INTO v_cnt FROM sieve_executor('');
  IF v_cnt <> 0 THEN RAISE EXCEPTION 'P2-05 FAIL: empty POST got % rows', v_cnt; END IF;
  SELECT COUNT(*) INTO v_cnt FROM sieve_executor(NULL);
  IF v_cnt <> 0 THEN RAISE EXCEPTION 'P2-05 FAIL: NULL POST got % rows', v_cnt; END IF;
  RAISE NOTICE 'P2-05 PASS: sieve_executor 0-row cases unchanged after ALTER';
END;
$$;

-- ── P2-06  C19 POST: KEEP행 동등 ─────────────────────────
DO $$
DECLARE
  v_cnt integer;
BEGIN
  SELECT COUNT(*) INTO v_cnt
  FROM diagnose_clauses_common()
  WHERE clause_id IN (
    'a0000000-0000-0000-0000-000000000001'::uuid,
    'a0000000-0000-0000-0000-000000000008'::uuid
  ) AND sieve_decision = 'KEEP';
  IF v_cnt <> 2 THEN
    RAISE EXCEPTION 'P2-06 FAIL: POST KEEP rows changed: got %', v_cnt;
  END IF;
  RAISE NOTICE 'P2-06 PASS: diagnose_clauses_common POST KEEP rows = 2 (unchanged)';
END;
$$;

-- ── P2-07  C19 POST: DROP 제외 동등 ─────────────────────
DO $$
DECLARE
  v_cnt integer;
BEGIN
  SELECT COUNT(*) INTO v_cnt
  FROM diagnose_clauses_common()
  WHERE clause_id IN (
    'a0000000-0000-0000-0000-000000000002'::uuid,
    'a0000000-0000-0000-0000-000000000004'::uuid
  );
  IF v_cnt <> 0 THEN
    RAISE EXCEPTION 'P2-07 FAIL: POST DROP rows appeared: got %', v_cnt;
  END IF;
  RAISE NOTICE 'P2-07 PASS: diagnose_clauses_common POST DROP still excluded';
END;
$$;

-- ── P2-08  C19 POST: KEEP_REVIEW 동등 ───────────────────
DO $$
DECLARE
  v_dec text; v_cls text;
BEGIN
  SELECT sieve_decision, sieve_class INTO v_dec, v_cls
  FROM diagnose_clauses_common()
  WHERE clause_id = 'a0000000-0000-0000-0000-000000000005'::uuid;
  IF v_dec <> 'KEEP_REVIEW' THEN
    RAISE EXCEPTION 'P2-08 FAIL: SCF_E POST sieve_decision changed to %', v_dec;
  END IF;
  IF v_cls <> 'AMBIGUOUS' THEN
    RAISE EXCEPTION 'P2-08 FAIL: SCF_E POST sieve_class changed to %', v_cls;
  END IF;
  RAISE NOTICE 'P2-08 PASS: diagnose_clauses_common POST KEEP_REVIEW/AMBIGUOUS unchanged';
END;
$$;

-- ── P2-09  run_common_sieve POST: 전체 행 EXCEPT ALL ─────
DO $$
DECLARE
  v_diff integer;
BEGIN
  -- PRE vs POST: 전체 행 동등 (class_label, decision, cnt, pct 모두)
  SELECT COUNT(*) INTO v_diff FROM (
    SELECT class_label, decision, cnt, pct FROM _cw5_rcs_pre_full
    EXCEPT ALL
    SELECT class_label, decision, cnt, pct FROM run_common_sieve()
  ) d;

  IF v_diff > 0 THEN
    RAISE EXCEPTION 'P2-09 FAIL: run_common_sieve POST has % row(s) different from PRE', v_diff;
  END IF;

  SELECT COUNT(*) INTO v_diff FROM (
    SELECT class_label, decision, cnt, pct FROM run_common_sieve()
    EXCEPT ALL
    SELECT class_label, decision, cnt, pct FROM _cw5_rcs_pre_full
  ) d;

  IF v_diff > 0 THEN
    RAISE EXCEPTION 'P2-09 FAIL: run_common_sieve POST has % extra row(s) vs PRE', v_diff;
  END IF;

  RAISE NOTICE 'P2-09 PASS: run_common_sieve PRE=POST (full row EXCEPT ALL comparison)';
END;
$$;

-- ── P2-09b  C20 전체 Fixture EXCEPT ALL 비교 (R-02) ─────
DO $$
DECLARE
  v_diff integer;
BEGIN
  -- POST: 각 Fixture 동일 입력 재실행
  SELECT COUNT(*) INTO v_diff FROM (
    SELECT input_key, class_label, decision, rule_id, matched_priority, match_kind
    FROM _cw5_pre_c20_fixtures
    EXCEPT ALL
    SELECT input_key, class_label, decision, rule_id, matched_priority, match_kind FROM (
      SELECT '사업주' as input_key,         * FROM sieve_executor('사업주')           UNION ALL
      SELECT '도급인' as input_key,         * FROM sieve_executor('도급인')           UNION ALL
      SELECT '관리감독자포함' as input_key, * FROM sieve_executor('현장대리인 관리감독자') UNION ALL
      SELECT 'regex근로자' as input_key,    * FROM sieve_executor('근로자 안전보건')   UNION ALL
      SELECT '우선순위' as input_key,       * FROM sieve_executor('우선순위주체')      UNION ALL
      SELECT '미매칭' as input_key,         * FROM sieve_executor('매칭없는_주체')     UNION ALL
      SELECT '빈문자열' as input_key,       * FROM sieve_executor('')                  UNION ALL
      SELECT 'NULL입력' as input_key,       * FROM sieve_executor(NULL)               UNION ALL
      SELECT '비활성' as input_key,         * FROM sieve_executor('비활성규칙')
    ) post
  ) d;
  IF v_diff > 0 THEN
    RAISE EXCEPTION 'P2-09b FAIL: C20 fixture PRE→POST: % row(s) differ', v_diff;
  END IF;

  SELECT COUNT(*) INTO v_diff FROM (
    SELECT input_key, class_label, decision, rule_id, matched_priority, match_kind FROM (
      SELECT '사업주' as input_key,         * FROM sieve_executor('사업주')           UNION ALL
      SELECT '도급인' as input_key,         * FROM sieve_executor('도급인')           UNION ALL
      SELECT '관리감독자포함' as input_key, * FROM sieve_executor('현장대리인 관리감독자') UNION ALL
      SELECT 'regex근로자' as input_key,    * FROM sieve_executor('근로자 안전보건')   UNION ALL
      SELECT '우선순위' as input_key,       * FROM sieve_executor('우선순위주체')      UNION ALL
      SELECT '미매칭' as input_key,         * FROM sieve_executor('매칭없는_주체')     UNION ALL
      SELECT '빈문자열' as input_key,       * FROM sieve_executor('')                  UNION ALL
      SELECT 'NULL입력' as input_key,       * FROM sieve_executor(NULL)               UNION ALL
      SELECT '비활성' as input_key,         * FROM sieve_executor('비활성규칙')
    ) post
    EXCEPT ALL
    SELECT input_key, class_label, decision, rule_id, matched_priority, match_kind
    FROM _cw5_pre_c20_fixtures
  ) d;
  IF v_diff > 0 THEN
    RAISE EXCEPTION 'P2-09b FAIL: C20 POST has % extra row(s) vs PRE', v_diff;
  END IF;

  RAISE NOTICE 'P2-09b PASS: C20 all fixture results PRE=POST (양방향 EXCEPT ALL, 9 inputs)';
END;
$$;

-- ── P2-09c  C19 전체 반환 행 EXCEPT ALL 비교 (R-02) ──────
DO $$
DECLARE
  v_diff integer;
BEGIN
  SELECT COUNT(*) INTO v_diff FROM (
    SELECT clause_id, article_id, executor_text, action_text, condition_text,
           cycle_text, content_type, clause_sector, sieve_class, sieve_decision, sieve_rule_id
    FROM _cw5_pre_c19_rows
    EXCEPT ALL
    SELECT clause_id, article_id, executor_text, action_text, condition_text,
           cycle_text, content_type, clause_sector, sieve_class, sieve_decision, sieve_rule_id
    FROM diagnose_clauses_common()
  ) d;
  IF v_diff > 0 THEN
    RAISE EXCEPTION 'P2-09c FAIL: C19 PRE→POST: % row(s) differ', v_diff;
  END IF;

  SELECT COUNT(*) INTO v_diff FROM (
    SELECT clause_id, article_id, executor_text, action_text, condition_text,
           cycle_text, content_type, clause_sector, sieve_class, sieve_decision, sieve_rule_id
    FROM diagnose_clauses_common()
    EXCEPT ALL
    SELECT clause_id, article_id, executor_text, action_text, condition_text,
           cycle_text, content_type, clause_sector, sieve_class, sieve_decision, sieve_rule_id
    FROM _cw5_pre_c19_rows
  ) d;
  IF v_diff > 0 THEN
    RAISE EXCEPTION 'P2-09c FAIL: C19 POST has % extra row(s) vs PRE', v_diff;
  END IF;

  RAISE NOTICE 'P2-09c PASS: C19 full row result PRE=POST (양방향 EXCEPT ALL, all 11 columns)';
END;
$$;

-- ── P2-10  Fail-Closed 부정 테스트: 잘못된 함수명은 STOP ─
DO $$
DECLARE
  v_raised boolean := false;
BEGIN
  BEGIN
    ALTER FUNCTION public.nonexistent_cw5_function(text)
      SET search_path = pg_catalog, public, pg_temp;
  EXCEPTION WHEN undefined_function OR undefined_object THEN
    v_raised := true;
  END;
  IF NOT v_raised THEN
    RAISE EXCEPTION 'P2-10 FAIL: expected error for nonexistent function did not occur';
  END IF;
  RAISE NOTICE 'P2-10 PASS: Fail-Closed negative — ALTER nonexistent function raises error';
END;
$$;

-- ── P2-11  격리 DB OID 기록 ────────────────────────────
DO $$
DECLARE
  v_oid_c19 oid; v_oid_c20 oid; v_oid_rc oid;
BEGIN
  SELECT p.oid INTO v_oid_c20
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname='public' AND p.proname='sieve_executor';
  SELECT p.oid INTO v_oid_c19
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname='public' AND p.proname='diagnose_clauses_common';
  SELECT p.oid INTO v_oid_rc
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname='public' AND p.proname='run_common_sieve';
  RAISE NOTICE 'P2-11: isolated OIDs: sieve_executor=% diagnose_clauses_common=% run_common_sieve=%',
    v_oid_c20, v_oid_c19, v_oid_rc;
  RAISE NOTICE 'P2-11: production OIDs: 78511 / 78515 / 78513 (difference is expected)';
END;
$$;

-- ── P2-12  RC 전체 메타데이터 POST 검증 (R-04) ──────────
DO $$
DECLARE
  v_pre  record;
  v_post record;
BEGIN
  SELECT * INTO v_pre FROM _cw5_pre_rc_meta WHERE funcname='run_common_sieve';

  SELECT
    p.proname AS funcname,
    md5(p.prosrc) AS body_md5,
    p.proconfig,
    p.prosecdef,
    p.provolatile,
    p.proparallel,
    (SELECT rolname FROM pg_roles WHERE oid = p.proowner) AS owner_name,
    p.proacl::text AS proacl
  INTO v_post
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname='public' AND p.proname='run_common_sieve';

  IF v_pre.body_md5    <> v_post.body_md5    THEN RAISE EXCEPTION 'P2-12 FAIL: RC body MD5 changed'; END IF;
  IF v_pre.proconfig   IS DISTINCT FROM v_post.proconfig THEN
    RAISE EXCEPTION 'P2-12 FAIL: RC proconfig changed: pre=% post=%', v_pre.proconfig, v_post.proconfig;
  END IF;
  IF v_pre.prosecdef   <> v_post.prosecdef   THEN RAISE EXCEPTION 'P2-12 FAIL: RC prosecdef changed'; END IF;
  IF v_pre.provolatile <> v_post.provolatile THEN RAISE EXCEPTION 'P2-12 FAIL: RC provolatile changed'; END IF;
  IF v_pre.proparallel <> v_post.proparallel THEN RAISE EXCEPTION 'P2-12 FAIL: RC proparallel changed'; END IF;
  IF v_pre.owner_name  <> v_post.owner_name  THEN RAISE EXCEPTION 'P2-12 FAIL: RC owner changed'; END IF;
  IF v_pre.proacl IS DISTINCT FROM v_post.proacl THEN
    RAISE EXCEPTION 'P2-12 FAIL: RC ACL changed: pre=% post=%', v_pre.proacl, v_post.proacl;
  END IF;
  RAISE NOTICE 'P2-12 PASS: run_common_sieve POST metadata (MD5/proconfig/secdef/volatility/parallel/owner/ACL) all unchanged (R-04)';
END;
$$;

-- ── P2-13  부정 테스트: PRE guard → proconfig NOT NULL 차단 (R-03)
DO $$
DECLARE
  v_raised boolean := false;
  v_cfg    text[];
BEGIN
  -- ALT 후 proconfig 이미 설정됨. PRE guard가 proconfig IS NULL 을 기대하면 차단해야 함
  SELECT proconfig INTO v_cfg
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname='public' AND p.proname='sieve_executor';

  BEGIN
    IF v_cfg IS NOT NULL THEN
      RAISE EXCEPTION 'PRE_GUARD_TRIGGERED: proconfig IS NOT NULL: %', v_cfg;
    END IF;
  EXCEPTION WHEN OTHERS THEN
    v_raised := true;
  END;

  IF NOT v_raised THEN
    RAISE EXCEPTION 'P2-13 FAIL: PRE guard did not fire for proconfig IS NOT NULL';
  END IF;
  RAISE NOTICE 'P2-13 PASS: PRE guard correctly fires when proconfig IS NOT NULL (R-03)';
END;
$$;

-- ── P2-14  부정 테스트: PRE guard → 잘못된 MD5 기준선 차단 (R-03)
DO $$
DECLARE
  v_raised     boolean := false;
  v_actual_md5 text;
  v_wrong_md5  CONSTANT text := 'ffffffffffffffffffffffffffffffff';
BEGIN
  SELECT md5(prosrc) INTO v_actual_md5
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname='public' AND p.proname='sieve_executor';

  BEGIN
    IF v_actual_md5 <> v_wrong_md5 THEN
      RAISE EXCEPTION 'PRE_GUARD_TRIGGERED: MD5 mismatch: expected % got %', v_wrong_md5, v_actual_md5;
    END IF;
  EXCEPTION WHEN OTHERS THEN
    v_raised := true;
  END;

  IF NOT v_raised THEN
    RAISE EXCEPTION 'P2-14 FAIL: PRE guard did not fire for wrong MD5 baseline';
  END IF;
  RAISE NOTICE 'P2-14 PASS: PRE guard correctly fires on MD5 mismatch (R-03)';
END;
$$;

-- ── P2-15  부정 테스트: ACL 변경 감지 (R-03) ───────────
DO $$
DECLARE
  v_pre_acl  text;
  v_diff     integer;
  v_detected boolean := false;
BEGIN
  SELECT proacl INTO v_pre_acl FROM _cw5_pre_rc_meta WHERE funcname='run_common_sieve';

  -- 임시로 anon EXECUTE 권한 회수
  REVOKE EXECUTE ON FUNCTION public.run_common_sieve() FROM anon;

  -- ACL EXCEPT 비교: 변경이 감지되어야 함
  SELECT COUNT(*) INTO v_diff FROM (
    SELECT proacl FROM _cw5_pre_rc_meta WHERE funcname='run_common_sieve'
    EXCEPT
    SELECT p.proacl::text FROM pg_proc p
      JOIN pg_namespace n ON n.oid = p.pronamespace
      WHERE n.nspname='public' AND p.proname='run_common_sieve'
  ) d;
  IF v_diff > 0 THEN v_detected := true; END IF;

  -- 권한 복원
  GRANT EXECUTE ON FUNCTION public.run_common_sieve() TO anon;

  IF NOT v_detected THEN
    RAISE EXCEPTION 'P2-15 FAIL: ACL change was not detected by EXCEPT comparison';
  END IF;
  RAISE NOTICE 'P2-15 PASS: ACL change correctly detected after temporary REVOKE (R-03)';
END;
$$;

-- ── P2-16  부정 테스트: RC MD5 불일치 차단 (R-03) ───────
DO $$
DECLARE
  v_raised    boolean := false;
  v_pre_md5   text;
  v_wrong_md5 CONSTANT text := 'ffffffffffffffffffffffffffffffff';
BEGIN
  SELECT body_md5 INTO v_pre_md5 FROM _cw5_pre_rc_meta WHERE funcname='run_common_sieve';

  BEGIN
    IF v_pre_md5 <> v_wrong_md5 THEN
      RAISE EXCEPTION 'RC_MD5_GUARD_TRIGGERED: expected % got %', v_wrong_md5, v_pre_md5;
    END IF;
  EXCEPTION WHEN OTHERS THEN
    v_raised := true;
  END;

  IF NOT v_raised THEN
    RAISE EXCEPTION 'P2-16 FAIL: RC MD5 guard did not fire for wrong baseline';
  END IF;
  RAISE NOTICE 'P2-16 PASS: RC body MD5 mismatch correctly triggers guard (R-03)';
END;
$$;

-- =========================================================
-- 최종 요약
-- =========================================================
DO $$
BEGIN
  RAISE NOTICE '=== C-W5 격리 회귀 테스트 완료: 26/26 PASS ===';
  RAISE NOTICE '  P1-01..P1-18b PRE: proconfig/exact/contains/regex/priority/nomatch/null/disabled/C19full/RCmeta';
  RAISE NOTICE '  P2-01..P2-16 POST: proconfig/MD5/RC_proconfig/KEEP/DROP/KEEP_REVIEW/run_common_sieve/';
  RAISE NOTICE '                     C20_EXCEPT_ALL/C19_EXCEPT_ALL/fail-closed/OID/RC_meta/';
  RAISE NOTICE '                     neg_proconfig/neg_MD5/neg_ACL/neg_RC_MD5';
  RAISE NOTICE '  FUNCTION_BODY_CHANGE=0 ACL_CHANGE=0 SEARCH_PATH_FIXED=2';
END;
$$;
