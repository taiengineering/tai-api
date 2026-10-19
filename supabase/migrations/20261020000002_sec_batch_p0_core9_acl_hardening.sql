-- SEC-BATCH-P0: WO-TAI-SUPABASE-SEC-BATCH-P0-IMPLEMENT-001
-- 개인정보·결제 핵심 9개 객체 일괄 보안 강화
--
-- 배경:
--   모든 대상 객체에 anon/authenticated 전 권한(arwdDxtm) 부여 상태.
--   소스코드 접근 경로: tai-api service_role 전용 (anon/authenticated 직접 접근 0건).
--   tai-admin / tai-www / tai-chemical 참조 0건 확인.
--
-- Group A — RLS 비활성 테이블 5개 (RLS 활성화 + 권한 회수):
--   refunds, worker_attendance, safety_committee_attendees,
--   work_permits, ra_participation
--
-- Group B — RLS 활성·무조건 허용 정책 테이블 3개 (정책 제거 + 권한 회수):
--   payments  : anon_*_payments × 4 + authenticated_all_payments 제거
--   users     : anon_*_users × 4 + authenticated_all_users 제거
--   companies : anon_*_companies × 4 + authenticated_all_companies 제거
--   service_role_full 정책 유지
--
-- Group C — View 1개 (anon/authenticated 권한 회수):
--   v_payments_list
--
-- 사전 조건:
--   1. Group A 5개 테이블 존재 확인
--   2. Group B 3개 테이블 존재 확인
--   3. v_payments_list View 존재 확인
--   4. Group B 각 테이블에 예상 외 정책 없음 확인
-- 불일치 시 전체 롤백.

BEGIN;

DO $$
DECLARE
  v_count              int;
  v_unexpected_names   text[];

  -- Group B: 제거할 정확한 정책 목록
  c_drop_payments  text[] := ARRAY[
    'anon_delete_payments', 'anon_insert_payments',
    'anon_select_payments', 'anon_update_payments',
    'authenticated_all_payments'
  ];
  c_drop_users     text[] := ARRAY[
    'anon_delete_users', 'anon_insert_users',
    'anon_select_users', 'anon_update_users',
    'authenticated_all_users'
  ];
  c_drop_companies text[] := ARRAY[
    'anon_delete_companies', 'anon_insert_companies',
    'anon_select_companies', 'anon_update_companies',
    'authenticated_all_companies'
  ];

BEGIN

  -- ── STEP 1: 사전 조건 검증 ──────────────────────────────────────

  -- Group A: 5개 테이블 존재
  SELECT count(*) INTO v_count
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public' AND c.relkind = 'r'
    AND c.relname IN (
      'refunds','worker_attendance','safety_committee_attendees',
      'work_permits','ra_participation'
    );
  IF v_count != 5 THEN
    RAISE EXCEPTION 'P0-PRE FAILED: Group-A expected 5 tables, found %.', v_count;
  END IF;

  -- Group B: 3개 테이블 존재
  SELECT count(*) INTO v_count
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public' AND c.relkind = 'r'
    AND c.relname IN ('payments','users','companies');
  IF v_count != 3 THEN
    RAISE EXCEPTION 'P0-PRE FAILED: Group-B expected 3 tables, found %.', v_count;
  END IF;

  -- Group C: View 존재
  SELECT count(*) INTO v_count
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public' AND c.relkind = 'v'
    AND c.relname = 'v_payments_list';
  IF v_count != 1 THEN
    RAISE EXCEPTION 'P0-PRE FAILED: v_payments_list view not found.';
  END IF;

  -- Group B: 예상 외 정책 차단 (payments)
  SELECT array_agg(policyname ORDER BY policyname) INTO v_unexpected_names
  FROM pg_policies
  WHERE schemaname = 'public' AND tablename = 'payments'
    AND policyname != 'service_role_full'
    AND NOT (policyname = ANY(c_drop_payments));
  IF v_unexpected_names IS NOT NULL AND array_length(v_unexpected_names, 1) > 0 THEN
    RAISE EXCEPTION 'P0-PRE FAILED: Unexpected policies on payments: %.', v_unexpected_names;
  END IF;

  -- Group B: 예상 외 정책 차단 (users)
  SELECT array_agg(policyname ORDER BY policyname) INTO v_unexpected_names
  FROM pg_policies
  WHERE schemaname = 'public' AND tablename = 'users'
    AND policyname != 'service_role_full'
    AND NOT (policyname = ANY(c_drop_users));
  IF v_unexpected_names IS NOT NULL AND array_length(v_unexpected_names, 1) > 0 THEN
    RAISE EXCEPTION 'P0-PRE FAILED: Unexpected policies on users: %.', v_unexpected_names;
  END IF;

  -- Group B: 예상 외 정책 차단 (companies)
  SELECT array_agg(policyname ORDER BY policyname) INTO v_unexpected_names
  FROM pg_policies
  WHERE schemaname = 'public' AND tablename = 'companies'
    AND policyname != 'service_role_full'
    AND NOT (policyname = ANY(c_drop_companies));
  IF v_unexpected_names IS NOT NULL AND array_length(v_unexpected_names, 1) > 0 THEN
    RAISE EXCEPTION 'P0-PRE FAILED: Unexpected policies on companies: %.', v_unexpected_names;
  END IF;

  RAISE NOTICE 'P0: Pre-conditions PASS.';

  -- ── STEP 2: Group A — RLS 활성화 + 권한 회수 ─────────────────────

  ALTER TABLE public.refunds                    ENABLE ROW LEVEL SECURITY;
  ALTER TABLE public.worker_attendance          ENABLE ROW LEVEL SECURITY;
  ALTER TABLE public.safety_committee_attendees ENABLE ROW LEVEL SECURITY;
  ALTER TABLE public.work_permits               ENABLE ROW LEVEL SECURITY;
  ALTER TABLE public.ra_participation           ENABLE ROW LEVEL SECURITY;

  REVOKE ALL PRIVILEGES ON TABLE public.refunds                    FROM PUBLIC, anon, authenticated;
  REVOKE ALL PRIVILEGES ON TABLE public.worker_attendance          FROM PUBLIC, anon, authenticated;
  REVOKE ALL PRIVILEGES ON TABLE public.safety_committee_attendees FROM PUBLIC, anon, authenticated;
  REVOKE ALL PRIVILEGES ON TABLE public.work_permits               FROM PUBLIC, anon, authenticated;
  REVOKE ALL PRIVILEGES ON TABLE public.ra_participation           FROM PUBLIC, anon, authenticated;

  RAISE NOTICE 'P0: Group-A (5 tables) RLS enabled + privileges revoked.';

  -- ── STEP 3: Group B — 무조건 허용 정책 제거 + 권한 회수 ───────────

  -- payments 정책 제거
  DROP POLICY anon_delete_payments        ON public.payments;
  DROP POLICY anon_insert_payments        ON public.payments;
  DROP POLICY anon_select_payments        ON public.payments;
  DROP POLICY anon_update_payments        ON public.payments;
  DROP POLICY authenticated_all_payments  ON public.payments;

  -- users 정책 제거
  DROP POLICY anon_delete_users           ON public.users;
  DROP POLICY anon_insert_users           ON public.users;
  DROP POLICY anon_select_users           ON public.users;
  DROP POLICY anon_update_users           ON public.users;
  DROP POLICY authenticated_all_users     ON public.users;

  -- companies 정책 제거
  DROP POLICY anon_delete_companies       ON public.companies;
  DROP POLICY anon_insert_companies       ON public.companies;
  DROP POLICY anon_select_companies       ON public.companies;
  DROP POLICY anon_update_companies       ON public.companies;
  DROP POLICY authenticated_all_companies ON public.companies;

  -- Group B 권한 회수
  REVOKE ALL PRIVILEGES ON TABLE public.payments  FROM PUBLIC, anon, authenticated;
  REVOKE ALL PRIVILEGES ON TABLE public.users     FROM PUBLIC, anon, authenticated;
  REVOKE ALL PRIVILEGES ON TABLE public.companies FROM PUBLIC, anon, authenticated;

  RAISE NOTICE 'P0: Group-B (3 tables) unsafe policies dropped + privileges revoked.';

  -- ── STEP 4: Group C — View 권한 회수 ─────────────────────────────

  REVOKE ALL PRIVILEGES ON TABLE public.v_payments_list FROM PUBLIC, anon, authenticated;

  RAISE NOTICE 'P0: Group-C (v_payments_list) privileges revoked.';

  -- ── STEP 5: 사후 조건 검증 ──────────────────────────────────────

  -- Group A: RLS 활성화 확인 (5개)
  SELECT count(*) INTO v_count
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public' AND c.relkind = 'r'
    AND c.relname IN (
      'refunds','worker_attendance','safety_committee_attendees',
      'work_permits','ra_participation'
    )
    AND c.relrowsecurity = true;
  IF v_count != 5 THEN
    RAISE EXCEPTION 'P0-POST FAILED: Expected 5 Group-A tables with RLS, found %.', v_count;
  END IF;

  -- Group B: service_role_full 정책 3개 유지 확인
  SELECT count(*) INTO v_count
  FROM pg_policies
  WHERE schemaname = 'public'
    AND tablename IN ('payments','users','companies')
    AND policyname = 'service_role_full';
  IF v_count != 3 THEN
    RAISE EXCEPTION 'P0-POST FAILED: Expected 3 service_role_full policies, found %.', v_count;
  END IF;

  -- Group B: 제거 대상 정책 잔존 없음
  SELECT count(*) INTO v_count
  FROM pg_policies
  WHERE schemaname = 'public'
    AND tablename IN ('payments','users','companies')
    AND policyname != 'service_role_full';
  IF v_count != 0 THEN
    RAISE EXCEPTION 'P0-POST FAILED: % non-service_role policies remain on Group-B.', v_count;
  END IF;

  -- 9개 객체에 anon / authenticated ACL 항목 없음
  SELECT count(*) INTO v_count
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public'
    AND c.relname IN (
      'refunds','worker_attendance','safety_committee_attendees',
      'work_permits','ra_participation',
      'payments','users','companies',
      'v_payments_list'
    )
    AND EXISTS (
      SELECT 1 FROM unnest(c.relacl) AS acl(entry)
      WHERE acl.entry::text ~ '^(anon|authenticated)='
    );
  IF v_count != 0 THEN
    RAISE EXCEPTION 'P0-POST FAILED: anon/authenticated ACL entries remain on % objects.', v_count;
  END IF;

  RAISE NOTICE 'P0-COMPLETE: 9 objects hardened. GroupA(5)+GroupB(3)+GroupC(1). service_role 접근 유지.';

END;
$$;

COMMIT;
