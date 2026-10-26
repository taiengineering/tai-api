-- setup_cw5.sql
-- WO-TAI-SEC-SEARCHPATH-REM97-CW5-C3-SOURCE-001
-- 독립 로컬 PostgreSQL 격리 DB 설정
-- 운영 OID와 격리 DB OID는 다를 수 있음 (정상, 기록함).
-- 함수 prosrc는 운영 본문과 동일하게 재현.

-- ── 0. 클린업 ─────────────────────────────────────────────
DROP TABLE IF EXISTS public.semantic_clause_fix CASCADE;
DROP TABLE IF EXISTS public.legal_sieve_rule    CASCADE;
DROP FUNCTION IF EXISTS public.sieve_executor(text);
DROP FUNCTION IF EXISTS public.diagnose_clauses_common();
DROP FUNCTION IF EXISTS public.run_common_sieve();

-- ── 1. 역할 (없으면 생성) ────────────────────────────────
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    CREATE ROLE anon NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    CREATE ROLE authenticated NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    CREATE ROLE service_role NOLOGIN BYPASSRLS;
  END IF;
END;
$$;

-- ── 2. legal_sieve_rule ──────────────────────────────────
CREATE TABLE public.legal_sieve_rule (
  id                    bigint      NOT NULL PRIMARY KEY,
  sieve_group           text        NOT NULL DEFAULT '',
  target_field          text        NOT NULL,
  match_type            text        NOT NULL,   -- exact / contains / regex
  pattern               text        NOT NULL,
  verdict               text        NOT NULL,   -- KEEP / DROP
  class_label           text        NOT NULL,
  priority              integer     NOT NULL,
  enabled               boolean     NOT NULL DEFAULT true,
  note                  text,
  created_at            timestamptz NOT NULL DEFAULT now(),
  applies_facility_sector text,
  stage                 text        NOT NULL,   -- common / common_value / ...
  field_kind            text,
  rule_kind             text,
  order_sensitive       boolean     NOT NULL DEFAULT false
);

REVOKE ALL ON public.legal_sieve_rule FROM PUBLIC;
GRANT SELECT ON public.legal_sieve_rule TO service_role;

-- ── 3. semantic_clause_fix ───────────────────────────────
CREATE TABLE public.semantic_clause_fix (
  id                    uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  source_part_id        uuid,
  source_article_id     uuid,
  clause_seq            integer,
  source_text           text,
  source_part_text      text,
  condition_text        text,
  executor_text         text,
  action_text           text,
  cycle_text            text,
  exception_text        text,
  form_token            text,
  content_type          text,
  sector                text,
  created_at            timestamptz DEFAULT now(),
  updated_at            timestamptz DEFAULT now()
);

REVOKE ALL ON public.semantic_clause_fix FROM PUBLIC;
GRANT SELECT ON public.semantic_clause_fix TO service_role;

-- ── 4. Fixture: legal_sieve_rule ─────────────────────────
-- R01: exact KEEP  '사업주'     priority=10
-- R02: exact DROP  '도급인'     priority=10
-- R03: contains KEEP '관리감독자' priority=20
-- R04: regex DROP  '^근로자'    priority=30
-- R05: exact KEEP  '우선순위주체' priority=5   (우선순위 낮은 번호 = 먼저 매칭)
-- R06: exact DROP  '우선순위주체' priority=15  (R05보다 낮은 우선순위)
-- R07: disabled    '비활성규칙'  enabled=false

INSERT INTO public.legal_sieve_rule
  (id, stage, target_field, match_type, pattern, verdict, class_label, priority, enabled)
VALUES
  (1,  'common',       'executor_text', 'exact',    '사업주',     'KEEP', '사업장_주체',   10, true),
  (2,  'common',       'executor_text', 'exact',    '도급인',     'DROP', '도급_주체',     10, true),
  (3,  'common',       'executor_text', 'contains', '관리감독자',  'KEEP', '관리감독_주체', 20, true),
  (4,  'common',       'executor_text', 'regex',    '^근로자',    'DROP', '근로자_주체',   30, true),
  (5,  'common',       'executor_text', 'exact',    '우선순위주체', 'KEEP', '우선_주체',    5,  true),
  (6,  'common',       'executor_text', 'exact',    '우선순위주체', 'DROP', '저순위_주체',  15, true),
  (7,  'common',       'executor_text', 'exact',    '비활성규칙',  'KEEP', '비활성_주체',  10, false),
  (8,  'section_only', 'executor_text', 'exact',    '사업주',     'DROP', '다른섹션',      10, true);
  -- R08: stage='section_only' → sieve_executor에서 'common','common_value'만 사용하므로 매칭 안 됨

-- ── 5. Fixture: semantic_clause_fix ─────────────────────
-- SCF_A: OBLIGATION, executor='사업주'     → KEEP
-- SCF_B: OBLIGATION, executor='도급인'     → DROP (diagnose_clauses_common에서 제외)
-- SCF_C: OBLIGATION, executor='현장대리인 관리감독자' → KEEP (contains 매칭)
-- SCF_D: OBLIGATION, executor='근로자 안전보건'     → DROP (regex '^근로자')
-- SCF_E: OBLIGATION, executor='매칭없는_주체'       → KEEP_REVIEW (미매칭)
-- SCF_F: OBLIGATION, executor=NULL                  → KEEP_REVIEW (NULL)
-- SCF_G: OBLIGATION, executor=''                    → KEEP_REVIEW (빈 문자열)
-- SCF_H: PROHIBITION, executor='사업주'             → KEEP
-- SCF_I: DEFINITION (제외 대상), executor='사업주'  → diagnose_clauses_common에서 제외

INSERT INTO public.semantic_clause_fix
  (id, source_article_id, executor_text, action_text, content_type, sector)
VALUES
  ('a0000000-0000-0000-0000-000000000001'::uuid,
   '00000000-0000-0000-0000-000000000001'::uuid,
   '사업주', '안전조치를 취한다', 'OBLIGATION', 'INDUSTRIAL'),

  ('a0000000-0000-0000-0000-000000000002'::uuid,
   '00000000-0000-0000-0000-000000000002'::uuid,
   '도급인', '안전보건조치', 'OBLIGATION', 'INDUSTRIAL'),

  ('a0000000-0000-0000-0000-000000000003'::uuid,
   '00000000-0000-0000-0000-000000000003'::uuid,
   '현장대리인 관리감독자', '작업 지시', 'OBLIGATION', 'CONSTRUCTION'),

  ('a0000000-0000-0000-0000-000000000004'::uuid,
   '00000000-0000-0000-0000-000000000004'::uuid,
   '근로자 안전보건', '교육 이수', 'OBLIGATION', 'INDUSTRIAL'),

  ('a0000000-0000-0000-0000-000000000005'::uuid,
   '00000000-0000-0000-0000-000000000005'::uuid,
   '매칭없는_주체', '의무 이행', 'OBLIGATION', 'INDUSTRIAL'),

  ('a0000000-0000-0000-0000-000000000006'::uuid,
   '00000000-0000-0000-0000-000000000006'::uuid,
   NULL, '의무 이행', 'OBLIGATION', 'INDUSTRIAL'),

  ('a0000000-0000-0000-0000-000000000007'::uuid,
   '00000000-0000-0000-0000-000000000007'::uuid,
   '', '의무 이행', 'OBLIGATION', 'INDUSTRIAL'),

  ('a0000000-0000-0000-0000-000000000008'::uuid,
   '00000000-0000-0000-0000-000000000008'::uuid,
   '사업주', '금지 의무', 'PROHIBITION', 'INDUSTRIAL'),

  ('a0000000-0000-0000-0000-000000000009'::uuid,
   '00000000-0000-0000-0000-000000000009'::uuid,
   '사업주', '정의 조항', 'DEFINITION', 'INDUSTRIAL');

-- ── 6. 함수 설치 (proconfig=NULL, prosrc = 운영 본문과 동일) ──

CREATE OR REPLACE FUNCTION public.sieve_executor(p_executor text)
  RETURNS TABLE(class_label text, decision text, rule_id bigint,
                matched_priority integer, match_kind text)
  LANGUAGE sql
  STABLE
AS $func$
  WITH ex AS (SELECT trim(coalesce(p_executor,'')) AS v)
  SELECT r.class_label,
         CASE WHEN r.verdict='KEEP' THEN 'KEEP' ELSE 'DROP' END AS decision,
         r.id, r.priority, r.match_type
  FROM legal_sieve_rule r, ex
  WHERE r.enabled = true
    AND r.stage IN ('common','common_value')
    AND r.target_field = 'executor_text'
    AND ex.v <> ''
    AND (
      (r.match_type='exact'    AND ex.v = r.pattern) OR
      (r.match_type='contains' AND ex.v LIKE '%'||r.pattern||'%') OR
      (r.match_type='regex'    AND ex.v ~ r.pattern)
    )
  ORDER BY r.priority,
           CASE r.match_type WHEN 'exact' THEN 0 WHEN 'contains' THEN 1 ELSE 2 END
  LIMIT 1;
$func$;

CREATE OR REPLACE FUNCTION public.diagnose_clauses_common()
  RETURNS TABLE(clause_id uuid, article_id uuid, executor_text text,
                action_text text, condition_text text, cycle_text text,
                content_type text, clause_sector text, sieve_class text,
                sieve_decision text, sieve_rule_id bigint)
  LANGUAGE sql
  STABLE
AS $func$
  SELECT
    s.id, s.source_article_id, s.executor_text, s.action_text,
    s.condition_text, s.cycle_text, s.content_type, s.sector,
    COALESCE(v.class_label, 'AMBIGUOUS') AS sieve_class,
    COALESCE(v.decision, 'KEEP_REVIEW')  AS sieve_decision,
    v.rule_id
  FROM semantic_clause_fix s
  LEFT JOIN LATERAL sieve_executor(s.executor_text) v ON true
  WHERE s.content_type IN ('OBLIGATION','PROHIBITION')
    AND COALESCE(v.decision, 'KEEP_REVIEW') <> 'DROP';  -- DROP 제외, KEEP+보류만
$func$;

CREATE OR REPLACE FUNCTION public.run_common_sieve()
  RETURNS TABLE(class_label text, decision text, cnt bigint, pct numeric)
  LANGUAGE sql
  STABLE
AS $func$
  WITH ob AS (
    SELECT executor_text
    FROM semantic_clause_fix
    WHERE content_type IN ('OBLIGATION','PROHIBITION')
      AND executor_text IS NOT NULL AND trim(executor_text) <> ''
  ),
  judged AS (
    SELECT COALESCE(s.class_label, '(보류)') AS cls,
           COALESCE(s.decision, 'KEEP_REVIEW') AS dec
    FROM ob
    LEFT JOIN LATERAL sieve_executor(ob.executor_text) s ON true
  )
  SELECT cls, dec, COUNT(*) AS cnt,
         ROUND(100.0*COUNT(*)/SUM(COUNT(*)) OVER(), 1) AS pct
  FROM judged
  GROUP BY cls, dec
  ORDER BY cnt DESC;
$func$;

-- ── 7. 권한 설정 ─────────────────────────────────────────
REVOKE ALL ON FUNCTION public.sieve_executor(text)         FROM PUBLIC;
REVOKE ALL ON FUNCTION public.diagnose_clauses_common()    FROM PUBLIC;
REVOKE ALL ON FUNCTION public.run_common_sieve()           FROM PUBLIC;

GRANT EXECUTE ON FUNCTION public.sieve_executor(text)      TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.diagnose_clauses_common() TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.run_common_sieve()        TO anon, authenticated, service_role;

-- PUBLIC grant: 운영 proacl 기준선(=X/postgres)과 격리 DB 일치
GRANT EXECUTE ON FUNCTION public.sieve_executor(text)      TO PUBLIC;
GRANT EXECUTE ON FUNCTION public.diagnose_clauses_common() TO PUBLIC;
GRANT EXECUTE ON FUNCTION public.run_common_sieve()        TO PUBLIC;

-- ── 8. 설정 확인 ─────────────────────────────────────────
DO $$
DECLARE
  v_cnt integer;
BEGIN
  SELECT COUNT(*) INTO v_cnt FROM public.legal_sieve_rule;
  RAISE NOTICE 'setup_cw5: legal_sieve_rule % rows', v_cnt;

  SELECT COUNT(*) INTO v_cnt FROM public.semantic_clause_fix;
  RAISE NOTICE 'setup_cw5: semantic_clause_fix % rows', v_cnt;

  SELECT COUNT(*) INTO v_cnt
  FROM pg_proc p
  JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public'
    AND p.proname IN ('sieve_executor','diagnose_clauses_common','run_common_sieve')
    AND p.proconfig IS NULL;
  RAISE NOTICE 'setup_cw5: % functions installed with proconfig=NULL (expected 3)', v_cnt;

  RAISE NOTICE 'setup_cw5 COMPLETE';
END;
$$;

-- ── 9. 본문 MD5 패리티 검증 (운영 기준선과 정확히 일치) ─────
DO $$
DECLARE
  v_md5 text;
  c20_expected text := '79c50e3985bf489f80b1b11ec516aac6';
  c19_expected text := 'f205550a5412f9111ac3a5449468ac7b';
  rc_expected  text := 'fbaf7f9a900d09f748ea02a1c6cc9bc6';
BEGIN
  SELECT md5(prosrc) INTO v_md5
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname='public' AND p.proname='sieve_executor';
  IF v_md5 <> c20_expected THEN
    RAISE EXCEPTION 'setup_cw5 MD5 PARITY FAIL: sieve_executor expected % got %', c20_expected, v_md5;
  END IF;

  SELECT md5(prosrc) INTO v_md5
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname='public' AND p.proname='diagnose_clauses_common';
  IF v_md5 <> c19_expected THEN
    RAISE EXCEPTION 'setup_cw5 MD5 PARITY FAIL: diagnose_clauses_common expected % got %', c19_expected, v_md5;
  END IF;

  SELECT md5(prosrc) INTO v_md5
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname='public' AND p.proname='run_common_sieve';
  IF v_md5 <> rc_expected THEN
    RAISE EXCEPTION 'setup_cw5 MD5 PARITY FAIL: run_common_sieve expected % got %', rc_expected, v_md5;
  END IF;

  RAISE NOTICE 'setup_cw5 MD5 PARITY: C20=% C19=% RC=% (3/3 match production baselines)',
    c20_expected, c19_expected, rc_expected;
END;
$$;
