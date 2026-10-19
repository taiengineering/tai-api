-- SEC-BATCH-P0T: WO-TAI-SUPABASE-SEC-BATCH-P0T-001
-- public 실제 테이블 362개 공통 TRUNCATE 권한 제거 + postgres 기본 권한 재발 방지
--
-- 배경:
--   Supabase 기본 템플릿이 모든 public 테이블에 anon/authenticated에
--   arwdDxtm (INSERT/SELECT/UPDATE/DELETE/TRUNCATE/REFERENCES/TRIGGER) 부여.
--   RLS로는 TRUNCATE를 통제할 수 없음 (PostgreSQL 공식 문서 명시).
--   P0 Migration에서 핵심 9개 객체의 anon/authenticated 전체 권한을 회수했으나
--   나머지 362개 테이블은 TRUNCATE 권한이 여전히 잔존.
--   모든 tai-api DB 접근은 service_role 전용.
--
-- 대상 (Manifest MD5 고정 검증):
--   public 실제 테이블 (relkind='r') + 파티셔닝 테이블 (relkind='p') 합계 362개
--   Manifest hash (relkind:relname, ORDER BY relkind,relname, newline join):
--   d6d190116b9b1579d8570b5cddb8a9fb
--
-- 변경 범위:
--   REVOKE TRUNCATE ON TABLE public.<name> FROM anon, authenticated  (362개)
--   SELECT / INSERT / UPDATE / DELETE 권한은 이번 범위에서 변경하지 않음
--   service_role 및 postgres 권한 유지
--
-- 기본 권한 (Default ACL):
--   postgres 소유: ALTER DEFAULT PRIVILEGES IN SCHEMA public
--                  REVOKE TRUNCATE ON TABLES FROM anon, authenticated
--   supabase_admin 소유: BLOCKED — supabase_admin 멤버십 없이 변경 불가
--                        (DEFAULT_ACL_GAP 유지, 별도 WO 필요)
--
-- 사전 조건:
--   1. TRUNCATE anon 권한 보유 테이블 수 = 362
--   2. Manifest MD5 = d6d190116b9b1579d8570b5cddb8a9fb
-- 불일치 시 전체 롤백.

BEGIN;

DO $$
DECLARE
  v_count         int;
  v_hash          text;
  v_manifest      text[];
  v_table_names   text[];
  v_name          text;
BEGIN

  -- ── STEP 1: 대상 수집 (manifest + table names 동시) ─────────────────

  SELECT
    array_agg(c.relkind::text || ':' || c.relname ORDER BY c.relkind, c.relname),
    array_agg(c.relname                            ORDER BY c.relkind, c.relname)
  INTO v_manifest, v_table_names
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public'
    AND c.relkind IN ('r', 'p')
    AND EXISTS (
      SELECT 1 FROM aclexplode(c.relacl) AS a
      WHERE a.grantee = (SELECT oid FROM pg_roles WHERE rolname = 'anon')
        AND a.privilege_type = 'TRUNCATE'
    );

  -- ── STEP 2: 수량 사전 조건 ────────────────────────────────────────

  v_count := coalesce(array_length(v_table_names, 1), 0);
  IF v_count != 362 THEN
    RAISE EXCEPTION
      'P0T-PRE FAILED: expected 362 TRUNCATE-capable tables, found %.', v_count;
  END IF;

  -- ── STEP 3: Manifest 해시 사전 조건 ──────────────────────────────

  v_hash := md5(array_to_string(v_manifest, E'\n'));
  IF v_hash != 'd6d190116b9b1579d8570b5cddb8a9fb' THEN
    RAISE EXCEPTION
      'P0T-PRE FAILED: manifest hash mismatch. Expected d6d190116b9b1579d8570b5cddb8a9fb, got %.', v_hash;
  END IF;

  RAISE NOTICE 'P0T: Pre-conditions PASS. 362 objects, hash verified.';

  -- ── STEP 4: REVOKE TRUNCATE (362개 루프) ──────────────────────────

  FOREACH v_name IN ARRAY v_table_names
  LOOP
    EXECUTE format(
      'REVOKE TRUNCATE ON TABLE public.%I FROM anon, authenticated',
      v_name
    );
  END LOOP;

  RAISE NOTICE 'P0T: REVOKE TRUNCATE complete on 362 tables.';

  -- ── STEP 5: 사후 조건 — anon TRUNCATE 권한 0 ────────────────────

  SELECT count(*) INTO v_count
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public'
    AND c.relkind IN ('r', 'p')
    AND EXISTS (
      SELECT 1 FROM aclexplode(c.relacl) AS a
      WHERE a.grantee = (SELECT oid FROM pg_roles WHERE rolname = 'anon')
        AND a.privilege_type = 'TRUNCATE'
    );
  IF v_count != 0 THEN
    RAISE EXCEPTION
      'P0T-POST FAILED: % public tables still have anon TRUNCATE.', v_count;
  END IF;

  -- ── STEP 6: 사후 조건 — authenticated TRUNCATE 권한 0 ───────────

  SELECT count(*) INTO v_count
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public'
    AND c.relkind IN ('r', 'p')
    AND EXISTS (
      SELECT 1 FROM aclexplode(c.relacl) AS a
      WHERE a.grantee = (SELECT oid FROM pg_roles WHERE rolname = 'authenticated')
        AND a.privilege_type = 'TRUNCATE'
    );
  IF v_count != 0 THEN
    RAISE EXCEPTION
      'P0T-POST FAILED: % public tables still have authenticated TRUNCATE.', v_count;
  END IF;

  RAISE NOTICE 'P0T-COMPLETE: TRUNCATE revoked from 362 public tables. anon=0, authenticated=0.';

END;
$$;

-- ── 기본 권한 재발 방지: postgres 소유 신규 테이블 ──────────────────
-- postgres가 public schema에 새 테이블 생성 시 anon/authenticated TRUNCATE 미부여
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  REVOKE TRUNCATE ON TABLES FROM anon, authenticated;

-- DEFAULT_ACL_GAP: supabase_admin 소유 테이블 기본 권한 (BLOCKED)
--   현재 상태: anon=arwdDxtm/supabase_admin, authenticated=arwdDxtm/supabase_admin
--   변경 필요 구문:
--     ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public
--       REVOKE TRUNCATE ON TABLES FROM anon, authenticated;
--   차단 사유: Migration 실행 역할(postgres)이 supabase_admin 멤버가 아님
--   처리: 별도 WO (권한 경로 검증 후 진행)

COMMIT;
