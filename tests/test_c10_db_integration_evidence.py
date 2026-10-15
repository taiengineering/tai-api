"""WO-E2E2000-C10-PR627-TEST-SAFETY-FINAL-003 — 실제 PostgreSQL 통합검증.

실행 조건:
  C10_TEST_DB_URL=postgresql://postgres:testpassword@localhost:PORT/c10_test
  C10_TEST_DB_AUTHORIZED=1
  pytest --run-db-int

CI에서는 C10_TEST_DB_AUTHORIZED 또는 C10_TEST_DB_URL 미설정 → 전체 자동 SKIP.

테스트 목록:
  DB-INT-01~04   anon    SELECT/INSERT/UPDATE/DELETE → DENY
  DB-INT-05~08   authenticated SELECT/INSERT/UPDATE/DELETE → DENY
  DB-INT-09~10   service_role SELECT/INSERT·UPDATE·DELETE → PASS
  DB-INT-11      PRE-CHECK Drift Guard: unknown 정책 삽입 시 DO $$ EXCEPTION (복사 SQL)
  DB-INT-12      트랜잭션 ROLLBACK → 정책 상태 원복 (단일 DROP)
  DB-INT-13      migration 재실행 idempotency
  DB-INT-14a~14d 잘못된 DB URL 또는 미승인 환경 → DROP 이전 차단 검증
  DB-INT-15      전체 마이그레이션 파일로 Drift Guard 실측 (unknown 정책 → 변경 없음)
  DB-INT-16      전체 마이그레이션 트랜잭션 ROLLBACK → 정책·GRANT 완전 원복

마이그레이션 파일:
  supabase/migrations/20261016000002_c10_rls_hardening_v2.sql
  SHA256: 3d50d021f5d67fd0e9d2e83a1c3ec6406cb32bdea38ab6fc4275e71d7a590bad
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import textwrap
from urllib.parse import urlparse

import psycopg2
import psycopg2.errors
import pytest

# ── 마이그레이션 파일 ────────────────────────────────────────────────────
_ROOT = pathlib.Path(__file__).resolve().parents[1]
_MIGRATION = _ROOT / "supabase" / "migrations" / "20261016000002_c10_rls_hardening_v2.sql"
_MIGRATION_SHA256 = "3d50d021f5d67fd0e9d2e83a1c3ec6406cb32bdea38ab6fc4275e71d7a590bad"

# ── 운영 과다 허용 정책 6개 재현 SQL ────────────────────────────────────
_SETUP_SQL = textwrap.dedent("""
    DO $$ BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
        CREATE ROLE anon NOLOGIN; END IF;
      IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
        CREATE ROLE authenticated NOLOGIN; END IF;
      IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='service_role') THEN
        CREATE ROLE service_role NOLOGIN BYPASSRLS; END IF;
    END $$;
    DROP TABLE IF EXISTS public.anonymous_diagnosis_results;
    CREATE TABLE public.anonymous_diagnosis_results (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      public_token TEXT, input_data JSONB,
      created_at TIMESTAMPTZ DEFAULT now(), expires_at TIMESTAMPTZ,
      claimed_user_id UUID, status TEXT DEFAULT 'ACTIVE',
      source_type TEXT, auth_log_id UUID
    );
    ALTER TABLE public.anonymous_diagnosis_results ENABLE ROW LEVEL SECURITY;
    ALTER TABLE public.anonymous_diagnosis_results FORCE ROW LEVEL SECURITY;
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
    GRANT SELECT, INSERT, UPDATE, DELETE
      ON public.anonymous_diagnosis_results TO anon;
    GRANT ALL ON public.anonymous_diagnosis_results TO authenticated;
    GRANT ALL ON public.anonymous_diagnosis_results TO service_role;
    INSERT INTO public.anonymous_diagnosis_results(status, source_type)
    VALUES ('ACTIVE','free_diag'), ('ACTIVE','site_free');
""")

_ORIGINAL_POLICIES = frozenset({
    "anon_delete_anonymous_diagnosis_results",
    "anon_insert_anonymous_diagnosis_results",
    "anon_select_anonymous_diagnosis_results",
    "anon_update_anonymous_diagnosis_results",
    "authenticated_all_anonymous_diagnosis_results",
    "service_role_full",
})


# ═══════════════════════════════════════════════════════════════════════
# 안전장치 — 운영 DB 접속 방지
# ═══════════════════════════════════════════════════════════════════════

def _assert_isolated_db(db_url: str) -> None:
    """DROP/REVOKE 실행 전 격리 DB임을 검증. 하나라도 실패하면 RuntimeError.

    규칙:
      1. C10_TEST_DB_AUTHORIZED=1 명시적 승인 환경변수 필요
      2. Supabase 운영 URL 패턴 차단 (*.supabase.co / *.supabase.com)
      3. 로컬 호스트(localhost / 127.0.0.1)만 허용
      4. DB 이름에 격리 식별자(test / iso / c10) 포함 필요
    접속 URL·비밀번호 원문은 오류 메시지에 포함하지 않는다.
    """
    if not os.environ.get("C10_TEST_DB_AUTHORIZED"):
        raise RuntimeError(
            "C10_TEST_DB_AUTHORIZED 환경변수가 없습니다. "
            "격리 테스트 DB임을 확인한 후 C10_TEST_DB_AUTHORIZED=1 로 설정하세요."
        )

    parsed = urlparse(db_url)
    host = (parsed.hostname or "").lower()
    dbname = (parsed.path or "").lstrip("/").lower()

    blocked = ["supabase.co", "supabase.com", ".supabase.io"]
    for pattern in blocked:
        if pattern in host:
            raise RuntimeError(
                f"운영 Supabase 호스트 패턴 감지 — 운영 DB 테스트 실행 금지. "
                f"(패턴: {pattern!r})"
            )

    allowed_hosts = {"localhost", "127.0.0.1", "0.0.0.0", ""}
    if host not in allowed_hosts:
        raise RuntimeError(
            f"비로컬 호스트 감지 — 통합 테스트는 localhost/127.0.0.1만 허용됩니다. "
            f"(호스트 클래스: {'로컬' if 'local' in host else '외부'})"
        )

    safe_name_tokens = ("test", "iso", "c10")
    if not any(t in dbname for t in safe_name_tokens):
        raise RuntimeError(
            f"DB 이름에 격리 식별자(test/iso/c10)가 없습니다. "
            f"운영 DB와 구분되는 격리 DB를 사용하세요."
        )


def _get_policies(cur) -> list[str]:
    cur.execute(
        "SELECT policyname FROM pg_policies "
        "WHERE tablename='anonymous_diagnosis_results' ORDER BY policyname;"
    )
    return [row[0] for row in cur.fetchall()]


def _get_grants(cur) -> list[tuple]:
    cur.execute(
        "SELECT grantee, privilege_type "
        "FROM information_schema.role_table_grants "
        "WHERE table_name='anonymous_diagnosis_results' "
        "ORDER BY grantee, privilege_type;"
    )
    return cur.fetchall()


# ═══════════════════════════════════════════════════════════════════════
# 픽스처
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def c10_db(request):
    """격리 DB: 6개 정책 재현 → migration 적용 → DB-INT-01~13용."""
    if not request.config.getoption("--run-db-int", default=False):
        pytest.skip("격리 DB 테스트 — --run-db-int 필요 (CI SKIP 정상)")

    db_url = os.environ.get("C10_TEST_DB_URL")
    if not db_url:
        pytest.skip("C10_TEST_DB_URL 미설정")

    _assert_isolated_db(db_url)

    # 마이그레이션 SHA256 검증
    actual_sha = hashlib.sha256(_MIGRATION.read_bytes()).hexdigest()
    assert actual_sha == _MIGRATION_SHA256, (
        f"마이그레이션 파일 SHA256 불일치: 예상={_MIGRATION_SHA256}, 실제={actual_sha}"
    )

    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("SELECT version();")
    db_version = cur.fetchone()[0]

    # 6개 정책 상태 설치
    cur.execute(_SETUP_SQL)

    # migration 적용
    cur.execute(_MIGRATION.read_text(encoding="utf-8"))

    yield {"conn": conn, "cur": cur, "db_version": db_version}
    cur.close()
    conn.close()


@pytest.fixture
def c10_fresh_6policy(request):
    """격리 DB를 6개 정책 원본 상태(migration 미적용)로 초기화하는 함수 스코프 픽스처."""
    if not request.config.getoption("--run-db-int", default=False):
        pytest.skip("격리 DB 테스트 — --run-db-int 필요")

    db_url = os.environ.get("C10_TEST_DB_URL")
    if not db_url:
        pytest.skip("C10_TEST_DB_URL 미설정")

    _assert_isolated_db(db_url)

    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(_SETUP_SQL)  # 6개 정책, migration 미적용

    yield {"conn": conn, "cur": cur, "db_url": db_url}
    cur.close()
    conn.close()


# ═══════════════════════════════════════════════════════════════════════
# DB-INT-01~04: anon 4개 DML → DENY
# ═══════════════════════════════════════════════════════════════════════

def _exec_as_role_expect_deny(conn, role: str, sql: str, test_id: str):
    with conn.cursor() as cur:
        cur.execute(f"SET ROLE {role};")
        try:
            cur.execute(sql)
            conn.rollback()
            pytest.fail(f"{test_id}: {role} {sql[:30]!r} 허용됨 — DENY 필요")
        except (psycopg2.errors.InsufficientPrivilege,
                psycopg2.errors.RaiseException):
            conn.rollback()
        finally:
            with conn.cursor() as r:
                r.execute("RESET ROLE;")


def test_DB_INT_01_anon_select_denied(c10_db):
    _exec_as_role_expect_deny(
        c10_db["conn"], "anon",
        "SELECT COUNT(*) FROM public.anonymous_diagnosis_results;",
        "DB-INT-01"
    )


def test_DB_INT_02_anon_insert_denied(c10_db):
    _exec_as_role_expect_deny(
        c10_db["conn"], "anon",
        "INSERT INTO public.anonymous_diagnosis_results(status) VALUES('X');",
        "DB-INT-02"
    )


def test_DB_INT_03_anon_update_denied(c10_db):
    _exec_as_role_expect_deny(
        c10_db["conn"], "anon",
        "UPDATE public.anonymous_diagnosis_results SET status='X';",
        "DB-INT-03"
    )


def test_DB_INT_04_anon_delete_denied(c10_db):
    _exec_as_role_expect_deny(
        c10_db["conn"], "anon",
        "DELETE FROM public.anonymous_diagnosis_results;",
        "DB-INT-04"
    )


# ═══════════════════════════════════════════════════════════════════════
# DB-INT-05~08: authenticated 4개 DML → DENY
# ═══════════════════════════════════════════════════════════════════════

def test_DB_INT_05_authenticated_select_denied(c10_db):
    _exec_as_role_expect_deny(
        c10_db["conn"], "authenticated",
        "SELECT COUNT(*) FROM public.anonymous_diagnosis_results;",
        "DB-INT-05"
    )


def test_DB_INT_06_authenticated_insert_denied(c10_db):
    _exec_as_role_expect_deny(
        c10_db["conn"], "authenticated",
        "INSERT INTO public.anonymous_diagnosis_results(status) VALUES('X');",
        "DB-INT-06"
    )


def test_DB_INT_07_authenticated_update_denied(c10_db):
    _exec_as_role_expect_deny(
        c10_db["conn"], "authenticated",
        "UPDATE public.anonymous_diagnosis_results SET status='X';",
        "DB-INT-07"
    )


def test_DB_INT_08_authenticated_delete_denied(c10_db):
    _exec_as_role_expect_deny(
        c10_db["conn"], "authenticated",
        "DELETE FROM public.anonymous_diagnosis_results;",
        "DB-INT-08"
    )


# ═══════════════════════════════════════════════════════════════════════
# DB-INT-09~10: service_role → PASS
# ═══════════════════════════════════════════════════════════════════════

def test_DB_INT_09_service_role_select_passes(c10_db):
    with c10_db["conn"].cursor() as cur:
        cur.execute("SET ROLE service_role;")
        cur.execute("SELECT COUNT(*) FROM public.anonymous_diagnosis_results;")
        count = cur.fetchone()[0]
        cur.execute("RESET ROLE;")
    assert isinstance(count, int) and count >= 0


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
    assert new_id is not None


# ═══════════════════════════════════════════════════════════════════════
# DB-INT-11: PRE-CHECK Drift Guard (DO $$ 복사본) — unknown 정책 → EXCEPTION
# ═══════════════════════════════════════════════════════════════════════

def test_DB_INT_11_pre_drift_guard_do_block(c10_db):
    cur = c10_db["cur"]
    conn = c10_db["conn"]

    cur.execute(
        "CREATE POLICY unknown_intruder ON public.anonymous_diagnosis_results "
        "FOR SELECT TO anon USING (true);"
    )
    assert "unknown_intruder" in _get_policies(cur)

    pre_check_sql = """
    DO $$
    DECLARE unknown_count INTEGER; unknown_names TEXT;
    BEGIN
        SELECT COUNT(*), string_agg(policyname, ', ')
        INTO unknown_count, unknown_names
        FROM pg_policies
        WHERE schemaname='public' AND tablename='anonymous_diagnosis_results'
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
    raised = False
    try:
        cur.execute(pre_check_sql)
    except psycopg2.errors.RaiseException as e:
        raised = True
        conn.rollback()
        assert "C10_PRE_DRIFT_GUARD_FAIL" in str(e)

    assert raised, "PRE-CHECK Drift Guard가 EXCEPTION을 발생시키지 않음"

    cur.execute(
        "DROP POLICY IF EXISTS unknown_intruder ON public.anonymous_diagnosis_results;"
    )


# ═══════════════════════════════════════════════════════════════════════
# DB-INT-12: 단일 DROP 트랜잭션 ROLLBACK → 정책 원복
# ═══════════════════════════════════════════════════════════════════════

def test_DB_INT_12_transaction_rollback_single_drop(c10_db):
    db_url = os.environ.get("C10_TEST_DB_URL")
    txn = psycopg2.connect(db_url)
    txn.autocommit = False
    try:
        with txn.cursor() as cur:
            cur.execute(
                "SELECT policyname FROM pg_policies "
                "WHERE tablename='anonymous_diagnosis_results' ORDER BY policyname;"
            )
            before = [r[0] for r in cur.fetchall()]
            cur.execute(
                "DROP POLICY IF EXISTS service_role_full "
                "ON public.anonymous_diagnosis_results;"
            )
            cur.execute(
                "SELECT policyname FROM pg_policies "
                "WHERE tablename='anonymous_diagnosis_results';"
            )
            mid = [r[0] for r in cur.fetchall()]
            assert "service_role_full" not in mid
            txn.rollback()
            cur.execute(
                "SELECT policyname FROM pg_policies "
                "WHERE tablename='anonymous_diagnosis_results' ORDER BY policyname;"
            )
            after = [r[0] for r in cur.fetchall()]
        assert before == after
    finally:
        txn.close()


# ═══════════════════════════════════════════════════════════════════════
# DB-INT-13: migration 재실행 idempotency
# ═══════════════════════════════════════════════════════════════════════

def test_DB_INT_13_migration_reapply_idempotent(c10_db):
    cur = c10_db["cur"]
    before = _get_policies(cur)

    cur.execute(_MIGRATION.read_text(encoding="utf-8"))

    after = _get_policies(cur)
    assert before == after
    assert after == ["service_role_full"]


# ═══════════════════════════════════════════════════════════════════════
# DB-INT-14a~14d: 잘못된 DB URL / 미승인 환경 → DROP 이전 차단
# ═══════════════════════════════════════════════════════════════════════

def test_DB_INT_14a_reject_without_authorized_env(request, monkeypatch):
    """C10_TEST_DB_AUTHORIZED 없으면 RuntimeError."""
    if not request.config.getoption("--run-db-int", default=False):
        pytest.skip("--run-db-int 필요")
    monkeypatch.delenv("C10_TEST_DB_AUTHORIZED", raising=False)
    with pytest.raises(RuntimeError, match="C10_TEST_DB_AUTHORIZED"):
        _assert_isolated_db("postgresql://u:p@localhost:15433/c10_test")


def test_DB_INT_14b_reject_supabase_url(request, monkeypatch):
    """Supabase 운영 도메인 → RuntimeError."""
    if not request.config.getoption("--run-db-int", default=False):
        pytest.skip("--run-db-int 필요")
    monkeypatch.setenv("C10_TEST_DB_AUTHORIZED", "1")
    with pytest.raises(RuntimeError, match="supabase"):
        _assert_isolated_db("postgresql://u:p@db.abcdef.supabase.co/postgres")


def test_DB_INT_14c_reject_nonlocal_host(request, monkeypatch):
    """외부 호스트 → RuntimeError."""
    if not request.config.getoption("--run-db-int", default=False):
        pytest.skip("--run-db-int 필요")
    monkeypatch.setenv("C10_TEST_DB_AUTHORIZED", "1")
    with pytest.raises(RuntimeError, match="비로컬"):
        _assert_isolated_db("postgresql://u:p@prod-db.example.com/c10_test")


def test_DB_INT_14d_reject_unsafe_dbname(request, monkeypatch):
    """DB 이름에 격리 식별자 없음 → RuntimeError."""
    if not request.config.getoption("--run-db-int", default=False):
        pytest.skip("--run-db-int 필요")
    monkeypatch.setenv("C10_TEST_DB_AUTHORIZED", "1")
    with pytest.raises(RuntimeError, match="격리 식별자"):
        _assert_isolated_db("postgresql://u:p@localhost:15433/production_db")


# ═══════════════════════════════════════════════════════════════════════
# DB-INT-15: 전체 마이그레이션 파일로 Drift Guard 실측
#   unknown 정책 존재 시 migration PRE-CHECK가 EXCEPTION 발생,
#   이후 DROP/REVOKE/CREATE 실행 없음 — 정책·GRANT 변경 없음
# ═══════════════════════════════════════════════════════════════════════

def test_DB_INT_15_full_migration_drift_guard(c10_fresh_6policy):
    """전체 migration 파일 실행 시 PRE-CHECK Drift Guard가 unknown 정책에서 차단."""
    conn = c10_fresh_6policy["conn"]
    cur = c10_fresh_6policy["cur"]
    db_url = c10_fresh_6policy["db_url"]

    # unknown 정책 추가
    cur.execute(
        "CREATE POLICY unknown_intruder ON public.anonymous_diagnosis_results "
        "FOR SELECT TO anon USING (true);"
    )
    policies_before = _get_policies(cur)
    grants_before = _get_grants(cur)
    assert "unknown_intruder" in policies_before
    assert len(policies_before) == 7  # 6 원본 + 1 unknown

    # 실제 migration 파일을 새 연결로 실행
    migration_sql = _MIGRATION.read_text(encoding="utf-8")
    migration_conn = psycopg2.connect(db_url)
    migration_conn.autocommit = True
    exception_raised = False
    exception_msg = ""
    try:
        with migration_conn.cursor() as mc:
            mc.execute(migration_sql)
    except psycopg2.errors.RaiseException as e:
        exception_raised = True
        exception_msg = str(e)
        migration_conn.rollback()
    finally:
        migration_conn.close()

    assert exception_raised, (
        "PRE-CHECK Drift Guard가 migration 전체 실행 시 EXCEPTION을 발생시키지 않음"
    )
    assert "C10_PRE_DRIFT_GUARD_FAIL" in exception_msg, (
        f"PRE-CHECK 식별자 누락: {exception_msg!r}"
    )

    # 정책·GRANT 변경 없음 확인 (PRE-CHECK에서 멈췄으므로 DROP 미실행)
    policies_after = _get_policies(cur)
    grants_after = _get_grants(cur)
    assert set(policies_after) == set(policies_before), (
        f"PRE-CHECK 이후 정책 변경 발생: 이전={policies_before}, 이후={policies_after}"
    )
    assert grants_after == grants_before, (
        f"PRE-CHECK 이후 GRANT 변경 발생"
    )


# ═══════════════════════════════════════════════════════════════════════
# DB-INT-16: 전체 마이그레이션 트랜잭션 ROLLBACK → 정책·GRANT 완전 원복
# ═══════════════════════════════════════════════════════════════════════

def test_DB_INT_16_full_migration_transaction_rollback(c10_fresh_6policy):
    """전체 migration을 트랜잭션에서 실행 후 ROLLBACK → 정책·GRANT 원복."""
    cur = c10_fresh_6policy["cur"]
    db_url = c10_fresh_6policy["db_url"]

    # migration 적용 전 상태 기록
    policies_before = _get_policies(cur)
    grants_before = _get_grants(cur)
    assert set(policies_before) == _ORIGINAL_POLICIES

    # autocommit=False 연결로 migration 실행 → 중간 상태 확인 → ROLLBACK
    txn_conn = psycopg2.connect(db_url)
    txn_conn.autocommit = False
    try:
        with txn_conn.cursor() as tc:
            migration_sql = _MIGRATION.read_text(encoding="utf-8")
            tc.execute(migration_sql)

            # 트랜잭션 내: migration 적용 상태 확인
            tc.execute(
                "SELECT policyname FROM pg_policies "
                "WHERE tablename='anonymous_diagnosis_results' ORDER BY policyname;"
            )
            policies_mid = [r[0] for r in tc.fetchall()]
            assert policies_mid == ["service_role_full"], (
                f"migration 적용 후(ROLLBACK 전) 예상과 다름: {policies_mid}"
            )

            tc.execute(
                "SELECT grantee, privilege_type "
                "FROM information_schema.role_table_grants "
                "WHERE table_name='anonymous_diagnosis_results' "
                "ORDER BY grantee, privilege_type;"
            )
            grants_mid = tc.fetchall()
            # migration 후 anon/authenticated GRANT 제거됨
            grantees_mid = {row[0] for row in grants_mid}
            assert "anon" not in grantees_mid, (
                "migration 후 anon GRANT가 남아있음"
            )

        txn_conn.rollback()

        # ROLLBACK 후 상태 확인 — 원복 여부 검증
        with txn_conn.cursor() as tc:
            tc.execute(
                "SELECT policyname FROM pg_policies "
                "WHERE tablename='anonymous_diagnosis_results' ORDER BY policyname;"
            )
            policies_after = [r[0] for r in tc.fetchall()]

            tc.execute(
                "SELECT grantee, privilege_type "
                "FROM information_schema.role_table_grants "
                "WHERE table_name='anonymous_diagnosis_results' "
                "ORDER BY grantee, privilege_type;"
            )
            grants_after = tc.fetchall()

    finally:
        txn_conn.close()

    assert set(policies_after) == _ORIGINAL_POLICIES, (
        f"ROLLBACK 후 정책 불일치: 이전={sorted(policies_before)}, 이후={sorted(policies_after)}"
    )
    assert grants_after == grants_before, (
        f"ROLLBACK 후 GRANT 불일치: 이전={grants_before}, 이후={grants_after}"
    )
