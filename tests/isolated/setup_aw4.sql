-- setup_aw4.sql
-- WO-TAI-SEC-SEARCHPATH-REM97-AW4-C2-ISOLATED-TRIGGER-CONTRACT-001
-- 격리 테스트 환경 초기화: 최소 스키마 + 함수 원본 본문 재현 (proconfig=NULL)
-- PostgreSQL 15 격리 DB (aw4_test)
-- R1 보정: WO-TAI-SEC-SEARCHPATH-REM97-AW4-C3-ISOLATION-GUARD-R1-001
-- 운영 DB 오실행 방지 Fail-Closed Guard 추가 (Migration SQL 변경 불허)

\set ON_ERROR_STOP on

BEGIN;

-- ── ISOLATION GUARD (Fail-Closed) ────────────────────────────────────
-- Guard 실패 시 이 트랜잭션의 DROP·CREATE·ALTER 은 일절 커밋되지 않는다.
-- app.rem97_aw4_isolated 는 파일 내부에서 설정하지 않는다.
-- 실행 전 외부에서:
--   PGPASSWORD=... psql ... -c "SET app.rem97_aw4_isolated='approved'" -f setup_aw4.sql
-- 또는 psql -v 방식으로 전달한다.
DO $$
BEGIN
  IF current_database() IS DISTINCT FROM 'aw4_test'
     OR current_setting('app.rem97_aw4_isolated', true)
        IS DISTINCT FROM 'approved'
     OR to_regnamespace('auth') IS NOT NULL
     OR to_regnamespace('storage') IS NOT NULL
     OR to_regnamespace('supabase_migrations') IS NOT NULL
  THEN
    RAISE EXCEPTION
      'REM97 AW4 ISOLATION GUARD FAILED: unsafe database — '
      'db=% permit=% auth=% storage=% supabase_migrations=%',
      current_database(),
      current_setting('app.rem97_aw4_isolated', true),
      to_regnamespace('auth')::text,
      to_regnamespace('storage')::text,
      to_regnamespace('supabase_migrations')::text;
  END IF;
  RAISE NOTICE 'ISOLATION GUARD PASS: db=aw4_test permit=approved no_supabase_schemas';
END;
$$;

-- ── 0. 클린업 ─────────────────────────────────────────────
DROP TABLE IF EXISTS public.equipment_assets CASCADE;
DROP TABLE IF EXISTS public.companies        CASCADE;
DROP TABLE IF EXISTS public.factories        CASCADE;
DROP TABLE IF EXISTS public.teams            CASCADE;
DROP TABLE IF EXISTS public.users            CASCADE;

DROP SEQUENCE IF EXISTS public.seq_asset_code;
DROP SEQUENCE IF EXISTS public.seq_company_code;
DROP SEQUENCE IF EXISTS public.seq_site_code;
DROP SEQUENCE IF EXISTS public.seq_team_code;
DROP SEQUENCE IF EXISTS public.seq_user_code;

DROP FUNCTION IF EXISTS public.fn_generate_asset_code();
DROP FUNCTION IF EXISTS public.fn_generate_company_code();
DROP FUNCTION IF EXISTS public.fn_generate_site_code();
DROP FUNCTION IF EXISTS public.fn_generate_team_code();
DROP FUNCTION IF EXISTS public.fn_generate_user_code();

-- ── 1. 시퀀스 ─────────────────────────────────────────────
CREATE SEQUENCE public.seq_asset_code   START 1;
CREATE SEQUENCE public.seq_company_code START 1;
CREATE SEQUENCE public.seq_site_code    START 1;
CREATE SEQUENCE public.seq_team_code    START 1;
CREATE SEQUENCE public.seq_user_code    START 1;

-- ── 2. 최소 테이블 ────────────────────────────────────────
CREATE TABLE public.companies (
  id           uuid DEFAULT gen_random_uuid() NOT NULL PRIMARY KEY,
  company_code text NOT NULL DEFAULT '',    -- 트리거가 BEFORE에서 채우므로 DEFAULT '' 허용
  status_code  text DEFAULT 'TRIAL'
);

CREATE TABLE public.equipment_assets (
  id         uuid DEFAULT gen_random_uuid() NOT NULL PRIMARY KEY,
  asset_code text
);

CREATE TABLE public.factories (
  id          uuid DEFAULT gen_random_uuid() NOT NULL PRIMARY KEY,
  site_code   text,
  status_code text DEFAULT 'ACTIVE',
  company_id  uuid
);

CREATE TABLE public.teams (
  id        uuid DEFAULT gen_random_uuid() NOT NULL PRIMARY KEY,
  team_code text
);

CREATE TABLE public.users (
  id          uuid DEFAULT gen_random_uuid() NOT NULL PRIMARY KEY,
  user_code   text,
  status_code text DEFAULT 'ACTIVE',
  company_id  uuid
);

-- ── 3. 함수 설치 (proconfig=NULL — 운영 본문과 정확히 동일) ──

CREATE OR REPLACE FUNCTION public.fn_generate_asset_code()
  RETURNS trigger LANGUAGE plpgsql VOLATILE AS
$$
begin
  if new.asset_code is null or trim(new.asset_code) = '' then
    new.asset_code := 'AST' || lpad(nextval('seq_asset_code')::text, 6, '0');
  end if;
  return new;
end;
$$;

CREATE OR REPLACE FUNCTION public.fn_generate_company_code()
  RETURNS trigger LANGUAGE plpgsql VOLATILE AS
$$
begin
  if new.company_code is null or trim(new.company_code) = '' then
    new.company_code := 'COMP' || lpad(nextval('seq_company_code')::text, 5, '0');
  end if;
  return new;
end;
$$;

CREATE OR REPLACE FUNCTION public.fn_generate_site_code()
  RETURNS trigger LANGUAGE plpgsql VOLATILE AS
$$
declare
  v_site_seq bigint;
begin
  if new.site_code is null or trim(new.site_code) = '' then
    if new.status_code in ('ANON_TEMP','E2E_TEMP','REGA_TEMP','REGB_TEMP','E2E_TEST') then
      new.site_code := 'TMP-' || replace(gen_random_uuid()::text, '-', '');
    else
      v_site_seq := nextval('seq_site_code');
      new.site_code :=
        'SITE' ||
        lpad(
          v_site_seq::text,
          greatest(5, length(v_site_seq::text)),
          '0'
        );
    end if;
  end if;
  return new;
end;
$$;

CREATE OR REPLACE FUNCTION public.fn_generate_team_code()
  RETURNS trigger LANGUAGE plpgsql VOLATILE AS
$$
begin
  if new.team_code is null or trim(new.team_code) = '' then
    new.team_code := 'TEAM' || lpad(nextval('seq_team_code')::text, 5, '0');
  end if;
  return new;
end;
$$;

CREATE OR REPLACE FUNCTION public.fn_generate_user_code()
  RETURNS trigger LANGUAGE plpgsql VOLATILE AS
$$
begin
  if new.user_code is null or trim(new.user_code) = '' then
    new.user_code := 'USR' || lpad(nextval('seq_user_code')::text, 6, '0');
  end if;
  return new;
end;
$$;

-- ── 4. 트리거 설치 (BEFORE INSERT FOR EACH ROW) ────────────
CREATE TRIGGER trg_generate_asset_code
  BEFORE INSERT ON public.equipment_assets
  FOR EACH ROW EXECUTE FUNCTION public.fn_generate_asset_code();

CREATE TRIGGER trg_generate_company_code
  BEFORE INSERT ON public.companies
  FOR EACH ROW EXECUTE FUNCTION public.fn_generate_company_code();

CREATE TRIGGER trg_generate_site_code
  BEFORE INSERT ON public.factories
  FOR EACH ROW EXECUTE FUNCTION public.fn_generate_site_code();

CREATE TRIGGER trg_generate_team_code
  BEFORE INSERT ON public.teams
  FOR EACH ROW EXECUTE FUNCTION public.fn_generate_team_code();

CREATE TRIGGER trg_generate_user_code
  BEFORE INSERT ON public.users
  FOR EACH ROW EXECUTE FUNCTION public.fn_generate_user_code();

-- ── 5. 설치 확인 ─────────────────────────────────────────
DO $$
DECLARE
  v_fn   integer;
  v_trg  integer;
  v_seq  integer;
  v_md5_asset   text;
  v_md5_company text;
  v_md5_site    text;
  v_md5_team    text;
  v_md5_user    text;
  c_md5_asset   CONSTANT text := '716c1df59ef2b3e4a20d8d810598732f';
  c_md5_company CONSTANT text := 'ad17d81156ae5c1a66f9c2b6216c15d7';
  c_md5_site    CONSTANT text := '7bd5a931ad8963226f17847c3ca1a1a3';
  c_md5_team    CONSTANT text := '270ed9eb57d7718a8316e774a8257cf0';
  c_md5_user    CONSTANT text := 'df3a1f47e3516edc1030bd8590ad7dc2';
BEGIN
  SELECT COUNT(*) INTO v_fn   FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
    WHERE n.nspname='public' AND p.proname LIKE 'fn_generate%code' AND p.proconfig IS NULL;
  SELECT COUNT(*) INTO v_trg  FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
    JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname='public' AND t.tgname LIKE 'trg_generate%' AND NOT t.tgisinternal;
  SELECT COUNT(*) INTO v_seq  FROM pg_sequences WHERE schemaname='public' AND sequencename LIKE 'seq_%_code';

  SELECT md5(prosrc) INTO v_md5_asset   FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname='fn_generate_asset_code';
  SELECT md5(prosrc) INTO v_md5_company FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname='fn_generate_company_code';
  SELECT md5(prosrc) INTO v_md5_site    FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname='fn_generate_site_code';
  SELECT md5(prosrc) INTO v_md5_team    FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname='fn_generate_team_code';
  SELECT md5(prosrc) INTO v_md5_user    FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname='fn_generate_user_code';

  RAISE NOTICE 'SETUP: functions=% (expected 5) triggers=% (expected 5) sequences=% (expected 5)', v_fn, v_trg, v_seq;

  IF v_md5_asset   <> c_md5_asset   THEN RAISE EXCEPTION 'MD5 PARITY FAIL: fn_generate_asset_code'; END IF;
  IF v_md5_company <> c_md5_company THEN RAISE EXCEPTION 'MD5 PARITY FAIL: fn_generate_company_code'; END IF;
  IF v_md5_site    <> c_md5_site    THEN RAISE EXCEPTION 'MD5 PARITY FAIL: fn_generate_site_code'; END IF;
  IF v_md5_team    <> c_md5_team    THEN RAISE EXCEPTION 'MD5 PARITY FAIL: fn_generate_team_code'; END IF;
  IF v_md5_user    <> c_md5_user    THEN RAISE EXCEPTION 'MD5 PARITY FAIL: fn_generate_user_code'; END IF;

  IF v_fn <> 5 OR v_trg <> 5 OR v_seq <> 5 THEN
    RAISE EXCEPTION 'SETUP COUNT FAIL: fn=% trg=% seq=%', v_fn, v_trg, v_seq;
  END IF;

  RAISE NOTICE 'SETUP MD5 PARITY: 5/5 MATCH production baselines';
  RAISE NOTICE 'SETUP COMPLETE';
END;
$$;

COMMIT;
