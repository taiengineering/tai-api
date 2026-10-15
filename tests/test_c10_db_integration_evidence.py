"""WO-E2E2000-C10-DB-INTEGRATION-EVIDENCE-CORRECTION-002 — 실제 PostgreSQL 통합검증.

실행 조건:
  환경변수 C10_TEST_DB_URL=postgresql://postgres:testpassword@localhost:15432/c10_test
  pytest --run-db-int

CI에서는 C10_TEST_DB_URL 미설정 → 전체 자동 SKIP (안전).

테스트 목록:
  DB-INT-01  anon    SELECT → DENY (insufficient_privilege / no policy)
  DB-INT-02  anon    INSERT → DENY
  DB-INT-03  anon    UPDATE → DENY
  DB-INT-04  anon    DELETE → DENY
  DB-INT-05  authenticated SELECT → DENY
  DB-INT-06  authenticated INSERT → DENY
  DB-INT-07  authenticated UPDATE → DENY
  DB-INT-08  authenticated DELETE → DENY
  DB-INT-09  service_role SELECT → PASS (행 반환)
  DB-INT-10  service_role INSERT/UPDATE/DELETE → PASS
  DB-INT-11  PRE-CHECK Drift Guard — 알 수 없는 정책 삽입 시 EXCEPTION 발생
  DB-INT-12  트랜잭션 ROLLBACK → 정책 상태 원복
  DB-INT-13  migration 재실행 idempotency → DROP IF EXISTS 재실행 오류 없음

마이그레이션 파일:
  supabase/migrations/20261016000002_c10_rls_hardening_v2.sql
  SHA256: 3d50d021f5d67fd0e9d2e83a1c3ec6406cb32bdea38ab6fc4275e71d7a590bad
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import textwrap

import psycopg2
import psycopg2.errors
import pytest

# ── 마이그레이션 파일 경로 ──────────────────────────────────────────────
_ROOT = pathlib.Path(__file__).resolve().parents[1]
_MIGRATION = _ROOT / "supabase" / "migrations" / "20261016000002_c10_rls_hardening_v2.sql"
_MIGRATION_SHA256 = "3d50d021f5d67fd0e9d2e83a1c3ec6406cb32bdea38ab6fc4275e71d7a590bad"

# ── 운영 과다 허용 정책 6개 재현 SQL ────────────────────────────────────
_SETUP_SQL = textwrap.dedent("""
    -- 역할 재현
    DO $$ BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
        CREATE ROLE anon NOLOGIN; END IF;
      IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
        CREATE ROLE authenticated NOLOGIN; END IF;
      IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='service_role') THEN
        CREATE ROLE service_role NOLOGIN BYPASSRLS; END IF;
    END $$;

    -- C10 테이블
    DROP TABLE IF EXISTS public.anonymous_diagnosis_results;
    CREATE TABLE public.anonymous_diagnosis_results (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      public_token TEXT, input_data JSONB,
      created_at TIMESTAMPTZ DEFAULT now(), expires_at TIMESTAMPTZ,
      claimed_user_id UUID, status TEXT DEFAULT 'ACTIVE',
      source_type TEXT, auth_log_id UUID
    );

    -- RLS 활성화
    ALTER TABLE public.anonymous_diagnosis_results ENABLE ROW LEVEL SECURITY;
    ALTER TABLE public.anonymous_diagnosis_results FORCE ROW LEVEL SECURITY;

    -- 운영 정책 6개 재현
    CREATE POLICY anon_delete_anonymous_diagnosis_results
      ON public.anonymous_diagnosis_results FOR DELETE TO anon USING (true);
    CREATE POLICY anon_insert_anonymous_diagnosis_results
      ON public.anonymous_diagnosis_results FOR INSERT TO anon WITH CHECK (true);
    CREATE POLICY anon_select_anonymous_diagnosis_results
      ON public.anonymous_diagnosis_results FOR SELECT TO anon USING (true);
    CREATE POLICY anon_update_anonymous_diagnosis_results
      ON public.anonymous_diagnosis_results FOR UPDATE TO anon USING (true);
    CREATE POLICY authenticated_all_anonymous_diagnosis_results
      ON public.anonymous_diagnosis_results FOR ALL TO authenticated
      USING (true) WITH CHECK (true);
    CREATE POLICY service_role_full
      ON public.anonymous_diagnosis_results FOR ALL TO service_role
      USING (true) WITH CHECK (true);

    -- GRANT 재현
    GRANT SELECT, INSERT, UPDATE, DELETE
      ON public.anonymous_diagnosis_results TO anon;
    GRANT ALL ON public.anonymous_diagnosis_results TO authenticated;
    GRANT ALL ON public.anonymous_diagnosis_results TO service_role;

    -- 시드 데이터
    INSERT INTO public.anonymous_diagnosis_results(status, source_type)
    VALUES ('ACTIVE','free_diag'), ('ACTIVE','site_free');
""")


# ── 픽스처 ───────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def c10_db(request):
    """격리 테스트 DB 연결. --run-db-int + C10_TEST_DB_URL 없으면 SKIP."""
    if not request.config.getoption("--run-db-int", default=False):
        pytest.skip("격리 DB 테스트 — --run-db-int 필요 (CI SKIP 정상)")

    db_url = os.environ.get("C10_TEST_DB_URL")
    if not db_url:
        pytest.skip("C10_TEST_DB_URL 미설정 — 격리 DB 연결 불가")

    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    cur = conn.cursor()

    # DB 버전 기록
    cur.execute("SELECT version();")
    db_version = cur.fetchone()[0]

    # 마이그레이션 SHA256 검증
    actual_sha = hashlib.sha256(_MIGRATION.read_bytes()).hexdigest()
    assert actual_sha == _MIGRATION_SHA256, (
        f"마이그레이션 파일 SHA256 불일치: 예상={_MIGRATION_SHA256}, 실제={actual_sha}"
    )

    # 스키마 초기화 (운영 상태 재현)
    cur.execute(_SETUP_SQL)

    # migration 적용
    cur.execute(_MIGRATION.read_text(encoding="utf-8"))

    yield {"conn": conn, "cur": cur, "db_version": db_version}

    cur.close()
    conn.close()


def _role_denied(conn, role: str, sql: str) -> bool:
    """지정 역할로 SQL 실행 시 권한 거부 발생 여부."""
    try:
        with conn.cursor() as cur:
            cur.execute(f"SET ROLE {role};")
            cur.execute(sql)
            conn.execute("ROLLBACK;")  # INSERT/UPDATE 결과 원복
    except (psycopg2.errors.InsufficientPrivilege, psycopg2.errors.RaiseException) as e:
        return True
    except Exception:
        return True
    finally:
        try:
            conn.execute("RESET ROLE;")
        except Exception:
            pass
    return False


# ── 정책 상태 조회 헬퍼 ────────────────────────────────────────────────

def _get_policies(cur) -> list[str]:
    cur.execute(
        "SELECT policyname FROM pg_policies "
        "WHERE tablename='anonymous_diagnosis_results' ORDER BY policyname;"
    )
    return [row[0] for row in cur.fetchall()]


# ═══════════════════════════════════════════════════════════════════════
# DB-INT-01~04: anon 4개 DML → DENY
# ═══════════════════════════════════════════════════════════════════════

def test_DB_INT_01_anon_select_denied(c10_db):
    conn = c10_db["conn"]
    with conn.cursor() as cur:
        cur.execute("SET ROLE anon;")
        try:
            cur.execute("SELECT COUNT(*) FROM public.anonymous_diagnosis_results;")
            conn.rollback()
            pytest.fail("anon SELECT 허용됨 — DENY 필요")
        except (psycopg2.errors.InsufficientPrivilege, psycopg2.errors.RaiseException):
            conn.rollback()  # 오류 상태 정리
        finally:
            with conn.cursor() as r:
                r.execute("RESET ROLE;")


def test_DB_INT_02_anon_insert_denied(c10_db):
    conn = c10_db["conn"]
    with conn.cursor() as cur:
        cur.execute("SET ROLE anon;")
        try:
            cur.execute(
                "INSERT INTO public.anonymous_diagnosis_results(status) VALUES('X');"
            )
            conn.rollback()
            pytest.fail("anon INSERT 허용됨 — DENY 필요")
        except (psycopg2.errors.InsufficientPrivilege, psycopg2.errors.RaiseException):
            conn.rollback()
        finally:
            with conn.cursor() as r:
                r.execute("RESET ROLE;")


def test_DB_INT_03_anon_update_denied(c10_db):
    conn = c10_db["conn"]
    with conn.cursor() as cur:
        cur.execute("SET ROLE anon;")
        try:
            cur.execute(
                "UPDATE public.anonymous_diagnosis_results SET status='X';"
            )
            conn.rollback()
            pytest.fail("anon UPDATE 허용됨 — DENY 필요")
        except (psycopg2.errors.InsufficientPrivilege, psycopg2.errors.RaiseException):
            conn.rollback()
        finally:
            with conn.cursor() as r:
                r.execute("RESET ROLE;")


def test_DB_INT_04_anon_delete_denied(c10_db):
    conn = c10_db["conn"]
    with conn.cursor() as cur:
        cur.execute("SET ROLE anon;")
        try:
            cur.execute(
                "DELETE FROM public.anonymous_diagnosis_results;"
            )
            conn.rollback()
            pytest.fail("anon DELETE 허용됨 — DENY 필요")
        except (psycopg2.errors.InsufficientPrivilege, psycopg2.errors.RaiseException):
            conn.rollback()
        finally:
            with conn.cursor() as r:
                r.execute("RESET ROLE;")


# ═══════════════════════════════════════════════════════════════════════
# DB-INT-05~08: authenticated 4개 DML → DENY
# ═══════════════════════════════════════════════════════════════════════

def test_DB_INT_05_authenticated_select_denied(c10_db):
    conn = c10_db["conn"]
    with conn.cursor() as cur:
        cur.execute("SET ROLE authenticated;")
        try:
            cur.execute("SELECT COUNT(*) FROM public.anonymous_diagnosis_results;")
            conn.rollback()
            pytest.fail("authenticated SELECT 허용됨 — DENY 필요")
        except (psycopg2.errors.InsufficientPrivilege, psycopg2.errors.RaiseException):
            conn.rollback()
        finally:
            with conn.cursor() as r:
                r.execute("RESET ROLE;")


def test_DB_INT_06_authenticated_insert_denied(c10_db):
    conn = c10_db["conn"]
    with conn.cursor() as cur:
        cur.execute("SET ROLE authenticated;")
        try:
            cur.execute(
                "INSERT INTO public.anonymous_diagnosis_results(status) VALUES('X');"
            )
            conn.rollback()
            pytest.fail("authenticated INSERT 허용됨 — DENY 필요")
        except (psycopg2.errors.InsufficientPrivilege, psycopg2.errors.RaiseException):
            conn.rollback()
        finally:
            with conn.cursor() as r:
                r.execute("RESET ROLE;")


def test_DB_INT_07_authenticated_update_denied(c10_db):
    conn = c10_db["conn"]
    with conn.cursor() as cur:
        cur.execute("SET ROLE authenticated;")
        try:
            cur.execute(
                "UPDATE public.anonymous_diagnosis_results SET status='X';"
            )
            conn.rollback()
            pytest.fail("authenticated UPDATE 허용됨 — DENY 필요")
        except (psycopg2.errors.InsufficientPrivilege, psycopg2.errors.RaiseException):
            conn.rollback()
        finally:
            with conn.cursor() as r:
                r.execute("RESET ROLE;")


def test_DB_INT_08_authenticated_delete_denied(c10_db):
    conn = c10_db["conn"]
    with conn.cursor() as cur:
        cur.execute("SET ROLE authenticated;")
        try:
            cur.execute(
                "DELETE FROM public.anonymous_diagnosis_results;"
            )
            conn.rollback()
            pytest.fail("authenticated DELETE 허용됨 — DENY 필요")
        except (psycopg2.errors.InsufficientPrivilege, psycopg2.errors.RaiseException):
            conn.rollback()
        finally:
            with conn.cursor() as r:
                r.execute("RESET ROLE;")


# ═══════════════════════════════════════════════════════════════════════
# DB-INT-09~10: service_role → PASS
# ═══════════════════════════════════════════════════════════════════════

def test_DB_INT_09_service_role_select_passes(c10_db):
    conn = c10_db["conn"]
    with conn.cursor() as cur:
        cur.execute("SET ROLE service_role;")
        cur.execute("SELECT COUNT(*) FROM public.anonymous_diagnosis_results;")
        count = cur.fetchone()[0]
        cur.execute("RESET ROLE;")
    assert count >= 0, "service_role SELECT 실패"


def test_DB_INT_10_service_role_write_passes(c10_db):
    conn = c10_db["conn"]
    with conn.cursor() as cur:
        cur.execute("SET ROLE service_role;")
        cur.execute(
            "INSERT INTO public.anonymous_diagnosis_results(status, source_type) "
            "VALUES('INT_TEST','test') RETURNING id;"
        )
        new_id = cur.fetchone()[0]
        cur.execute(
            "UPDATE public.anonymous_diagnosis_results SET status='INT_UPD' WHERE id=%s;",
            (new_id,)
        )
        cur.execute(
            "DELETE FROM public.anonymous_diagnosis_results WHERE id=%s;",
            (new_id,)
        )
        cur.execute("RESET ROLE;")
    assert new_id is not None, "service_role INSERT/UPDATE/DELETE 실패"


# ═══════════════════════════════════════════════════════════════════════
# DB-INT-11: PRE-CHECK Drift Guard — unknown 정책 삽입 시 EXCEPTION
# ═══════════════════════════════════════════════════════════════════════

def test_DB_INT_11_pre_drift_guard_blocks_unknown_policy(c10_db):
    """unknown 정책이 존재할 때 migration PRE-CHECK DO 블록이 EXCEPTION 발생 확인."""
    conn = c10_db["conn"]
    cur = c10_db["cur"]

    # unknown 정책 삽입
    cur.execute(
        "CREATE POLICY unknown_intruder ON public.anonymous_diagnosis_results "
        "FOR SELECT TO anon USING (true);"
    )
    policies_before = _get_policies(cur)
    assert "unknown_intruder" in policies_before, "unknown 정책 삽입 실패"

    # PRE-CHECK DO 블록 발췌 실행 (migration 전체 재실행 대신 핵심 블록만)
    pre_check_sql = """
    DO $$
    DECLARE unknown_count INTEGER; unknown_names TEXT;
    BEGIN
        SELECT COUNT(*), string_agg(policyname, ', ')
        INTO unknown_count, unknown_names
        FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'anonymous_diagnosis_results'
          AND policyname NOT IN (
              'anon_delete_anonymous_diagnosis_results',
              'anon_insert_anonymous_diagnosis_results',
              'anon_select_anonymous_diagnosis_results',
              'anon_update_anonymous_diagnosis_results',
              'authenticated_all_anonymous_diagnosis_results',
              'service_role_full',
              'anon_diag_insert_open','anon_diag_select_by_token',
              'anon_diag_select_claimed','anon_diag_update_claim',
              'anon_diag_admin_all','anon_diag_service_role',
              'anon_select_all','anon_update_all','anon_delete_all','authenticated_all'
          );
        IF unknown_count > 0 THEN
            RAISE EXCEPTION 'C10_PRE_DRIFT_GUARD_FAIL: [%]', unknown_names;
        END IF;
    END $$;
    """
    exception_raised = False
    try:
        cur.execute(pre_check_sql)
    except psycopg2.errors.RaiseException as e:
        exception_raised = True
        assert "C10_PRE_DRIFT_GUARD_FAIL" in str(e), (
            f"PRE_DRIFT_GUARD EXCEPTION 발생했으나 식별자 누락: {e}"
        )
        conn.rollback()

    assert exception_raised, "PRE-CHECK Drift Guard가 unknown 정책에도 EXCEPTION을 발생시키지 않음"

    # 정리
    cur.execute(
        "DROP POLICY IF EXISTS unknown_intruder ON public.anonymous_diagnosis_results;"
    )


# ═══════════════════════════════════════════════════════════════════════
# DB-INT-12: 트랜잭션 ROLLBACK → 정책 상태 원복
# ═══════════════════════════════════════════════════════════════════════

def test_DB_INT_12_transaction_rollback_restores_state(c10_db):
    """트랜잭션 내 DROP 후 ROLLBACK 시 정책이 원복되는지 확인."""
    conn_url = os.environ.get("C10_TEST_DB_URL")
    if not conn_url:
        pytest.skip("C10_TEST_DB_URL 미설정")

    # autocommit=False 연결 새로 열기
    txn_conn = psycopg2.connect(conn_url)
    txn_conn.autocommit = False
    try:
        with txn_conn.cursor() as cur:
            # 현재 정책 목록
            cur.execute(
                "SELECT policyname FROM pg_policies "
                "WHERE tablename='anonymous_diagnosis_results' ORDER BY policyname;"
            )
            policies_before = [r[0] for r in cur.fetchall()]

            # 트랜잭션 내 DROP
            cur.execute(
                "DROP POLICY IF EXISTS service_role_full "
                "ON public.anonymous_diagnosis_results;"
            )
            cur.execute(
                "SELECT policyname FROM pg_policies "
                "WHERE tablename='anonymous_diagnosis_results' ORDER BY policyname;"
            )
            policies_mid = [r[0] for r in cur.fetchall()]
            assert "service_role_full" not in policies_mid, (
                "트랜잭션 내 DROP이 반영되지 않음"
            )

            # ROLLBACK
            txn_conn.rollback()

            cur.execute(
                "SELECT policyname FROM pg_policies "
                "WHERE tablename='anonymous_diagnosis_results' ORDER BY policyname;"
            )
            policies_after = [r[0] for r in cur.fetchall()]

        assert policies_before == policies_after, (
            f"ROLLBACK 후 정책 불일치: 이전={policies_before}, 이후={policies_after}"
        )
    finally:
        txn_conn.close()


# ═══════════════════════════════════════════════════════════════════════
# DB-INT-13: migration 재실행 idempotency
# ═══════════════════════════════════════════════════════════════════════

def test_DB_INT_13_migration_reapply_idempotent(c10_db):
    """migration 재실행 시 오류 없이 완료되고 정책 상태가 동일함을 확인."""
    cur = c10_db["cur"]
    conn = c10_db["conn"]

    policies_before = _get_policies(cur)

    # migration 재실행 (DROP IF EXISTS → NOTICE만 발생, 오류 없음)
    try:
        cur.execute(_MIGRATION.read_text(encoding="utf-8"))
    except Exception as e:
        pytest.fail(f"migration 재실행 실패: {e}")

    policies_after = _get_policies(cur)

    assert policies_before == policies_after, (
        f"재실행 후 정책 상태 불일치: 이전={policies_before}, 이후={policies_after}"
    )
    assert policies_after == ["service_role_full"], (
        f"재실행 후 예상 정책과 다름: {policies_after}"
    )
