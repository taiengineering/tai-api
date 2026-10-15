"""WO-E2E2000-C10-PR627-ISOLATION-GUARD-FIX-004 — 실제 PostgreSQL 통합검증.

실행 조건:
  1. 격리 컨테이너 준비 (postgres:17-alpine)
  2. 격리 마커 설치 (테스트 코드가 생성하지 않음 — 수동 설치):
       psql -c "CREATE TABLE _c10_test_isolation_marker(marker_value TEXT NOT NULL);
                INSERT INTO _c10_test_isolation_marker VALUES('C10_TEST_ISOLATION_CONFIRMED');"
  3. 환경변수 설정:
       C10_TEST_DB_URL=postgresql://postgres:testpassword@localhost:PORT/c10_test
       C10_TEST_DB_AUTHORIZED=1
  4. 실행:
       pytest --run-db-int

CI에서는 C10_TEST_DB_AUTHORIZED 또는 C10_TEST_DB_URL 미설정 → 전체 자동 SKIP.

테스트 목록:
  DB-INT-01~04   anon    SELECT/INSERT/UPDATE/DELETE → DENY
  DB-INT-05~08   authenticated SELECT/INSERT/UPDATE/DELETE → DENY
  DB-INT-09~10   service_role SELECT/INSERT·UPDATE·DELETE → PASS
  DB-INT-11      PRE-CHECK Drift Guard: unknown 정책 삽입 시 DO $$ EXCEPTION (복사 SQL)
  DB-INT-12      트랜잭션 ROLLBACK → 정책 상태 원복 (단일 DROP)
  DB-INT-13      migration 재실행 idempotency
  DB-INT-14a     C10_TEST_DB_AUTHORIZED 미설정 → 차단
  DB-INT-14b     Supabase 운영 URL → 차단
  DB-INT-14c     비로컬 호스트 → 차단
  DB-INT-14d     DB 이름 미승인 → 차단
  DB-INT-14e     C10_TEST_DB_AUTHORIZED=0 → 차단 (정확히 "1"만 허용)
  DB-INT-17      빈 호스트 → 차단
  DB-INT-18      0.0.0.0 호스트 → 차단
  DB-INT-19      격리 마커 테이블 없음 → 차단
  DB-INT-20      격리 마커 값 불일치 → 차단
  DB-INT-21      정상 격리 마커 → PASS (c10_db 픽스처에서 암묵적 검증)
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

# ── 격리 마커 상수 ────────────────────────────────────────────────────
_MARKER_TABLE = "_c10_test_isolation_marker"
_MARKER_VALUE = "C10_TEST_ISOLATION_CONFIRMED"

# ── 승인된 격리 DB 이름 목록 (env 재정의 가능) ──────────────────────────
def _approved_db_names() -> frozenset[str]:
    names = os.environ.get("C10_TEST_DB_NAMES", "c10_test")
    return frozenset(n.strip() for n in names.split(",") if n.strip())


# ═══════════════════════════════════════════════════════════════════════
# 안전장치 — 운영 DB 접속 방지
# ═══════════════════════════════════════════════════════════════════════

def _assert_isolated_db(db_url: str) -> None:
    """DROP/REVOKE 실행 전 격리 DB임을 검증. 하나라도 실패하면 RuntimeError.

    규칙:
      1. C10_TEST_DB_AUTHORIZED 값이 정확히 "1"이어야 함 (0 또는 미설정 거부)
      2. Supabase 운영 URL 패턴 차단 (*.supabase.co / *.supabase.com)
      3. localhost 또는 127.0.0.1만 허용 (0.0.0.0 및 빈 호스트 포함 거부)
      4. DB 이름이 승인 목록과 정확히 일치해야 함 (부분 문자열 불허)
    접속 URL·비밀번호 원문은 오류 메시지에 포함하지 않는다.
    """
    # 규칙 1: 정확히 "1"만 허용
    if os.environ.get("C10_TEST_DB_AUTHORIZED") != "1":
        raise RuntimeError(
            "C10_TEST_DB_AUTHORIZED 값이 정확히 '1'이어야 합니다. "
            "0 또는 미설정은 거부됩니다. 격리 테스트 DB임을 확인 후 설정하세요."
        )

    parsed = urlparse(db_url)
    host = (parsed.hostname or "").lower()
    dbname = (parsed.path or "").lstrip("/")

    # 규칙 2: Supabase 운영 URL 차단
    blocked = ["supabase.co", "supabase.com", ".supabase.io"]
    for pattern in blocked:
        if pattern in host:
            raise RuntimeError(
                f"운영 Supabase 호스트 패턴 감지 — 운영 DB 테스트 실행 금지. "
                f"(패턴: {pattern!r})"
            )

    # 규칙 3: localhost / 127.0.0.1만 허용 (0.0.0.0·빈 문자열 포함 거부)
    if host not in {"localhost", "127.0.0.1"}:
        raise RuntimeError(
            "허용되지 않는 호스트입니다. localhost 또는 127.0.0.1만 허용됩니다. "
            "0.0.0.0, 빈 호스트, 외부 주소는 모두 거부됩니다."
        )

    # 규칙 4: DB 이름 정확히 일치
    approved = _approved_db_names()
    if dbname not in approved:
        raise RuntimeError(
            f"DB 이름이 승인 목록에 없습니다. "
            f"승인 목록: {sorted(approved)}. 정확히 일치해야 합니다."
        )


def _assert_isolation_marker(conn) -> None:
    """DB 내부 격리 식별 마커 확인 (읽기 전용).

    테스트 코드는 마커를 생성하지 않는다. 마커는 격리 테스트 DB 준비 시
    수동으로 설치되어야 한다:
      CREATE TABLE _c10_test_isolation_marker(marker_value TEXT NOT NULL);
      INSERT INTO _c10_test_isolation_marker VALUES('C10_TEST_ISOLATION_CONFIRMED');

    마커 없음, 행 없음, 값 불일치 모두 RuntimeError 발생 → _SETUP_SQL 실행 차단.
    """
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT marker_value FROM {_MARKER_TABLE} LIMIT 1;"
            )
            row = cur.fetchone()
    except psycopg2.errors.UndefinedTable:
        try:
            conn.rollback()
        except Exception:
            pass
        raise RuntimeError(
            f"격리 식별 마커 테이블({_MARKER_TABLE})이 없습니다. "
            "격리 테스트 DB 준비 시 수동으로 설치하세요: "
            f"CREATE TABLE {_MARKER_TABLE}(marker_value TEXT NOT NULL); "
            f"INSERT INTO {_MARKER_TABLE} VALUES('{_MARKER_VALUE}');"
        )

    if not row:
        raise RuntimeError(
            f"격리 마커 행이 없습니다. "
            f"INSERT INTO {_MARKER_TABLE} VALUES('{_MARKER_VALUE}') 로 설치하세요."
        )

    if row[0] != _MARKER_VALUE:
        raise RuntimeError(
            f"격리 마커 값 불일치. 예상='{_MARKER_VALUE}', 실제='{row[0]!r}'. "
            "올바른 격리 DB를 사용하세요."
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

    # 격리 마커 확인 — _SETUP_SQL(DROP TABLE) 실행 전에 반드시 통과
    _assert_isolation_marker(conn)

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

    # 격리 마커 확인 — _SETUP_SQL(DROP TABLE) 실행 전에 반드시 통과
    _assert_isolation_marker(conn)

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
    with pytest.raises(RuntimeError, match="허용되지 않는 호스트"):
        _assert_isolated_db("postgresql://u:p@prod-db.example.com/c10_test")


def test_DB_INT_14d_reject_unsafe_dbname(request, monkeypatch):
    """DB 이름이 승인 목록에 없음 → RuntimeError."""
    if not request.config.getoption("--run-db-int", default=False):
        pytest.skip("--run-db-int 필요")
    monkeypatch.setenv("C10_TEST_DB_AUTHORIZED", "1")
    monkeypatch.setenv("C10_TEST_DB_NAMES", "c10_test")
    with pytest.raises(RuntimeError, match="승인 목록"):
        _assert_isolated_db("postgresql://u:p@localhost:15433/production_db")


def test_DB_INT_14e_reject_authorized_zero(request, monkeypatch):
    """C10_TEST_DB_AUTHORIZED=0 → RuntimeError (정확히 '1'만 허용)."""
    if not request.config.getoption("--run-db-int", default=False):
        pytest.skip("--run-db-int 필요")
    monkeypatch.setenv("C10_TEST_DB_AUTHORIZED", "0")
    with pytest.raises(RuntimeError, match="정확히 '1'"):
        _assert_isolated_db("postgresql://u:p@localhost:15433/c10_test")


# ═══════════════════════════════════════════════════════════════════════
# DB-INT-17~18: 0.0.0.0 / 빈 호스트 → 차단
# ═══════════════════════════════════════════════════════════════════════

def test_DB_INT_17_reject_empty_host(request, monkeypatch):
    """빈 호스트(socket 연결) → RuntimeError."""
    if not request.config.getoption("--run-db-int", default=False):
        pytest.skip("--run-db-int 필요")
    monkeypatch.setenv("C10_TEST_DB_AUTHORIZED", "1")
    with pytest.raises(RuntimeError, match="허용되지 않는 호스트"):
        _assert_isolated_db("postgresql:///c10_test")  # 호스트 없음


def test_DB_INT_18_reject_zero_zero_host(request, monkeypatch):
    """0.0.0.0 호스트 → RuntimeError."""
    if not request.config.getoption("--run-db-int", default=False):
        pytest.skip("--run-db-int 필요")
    monkeypatch.setenv("C10_TEST_DB_AUTHORIZED", "1")
    with pytest.raises(RuntimeError, match="허용되지 않는 호스트"):
        _assert_isolated_db("postgresql://u:p@0.0.0.0:15433/c10_test")


# ═══════════════════════════════════════════════════════════════════════
# DB-INT-19~21: 격리 마커 검증
# ═══════════════════════════════════════════════════════════════════════

class _MarkerCursor:
    """_assert_isolation_marker 단위 테스트용 최소 Mock 커서."""
    def __init__(self, behavior: str):
        self._behavior = behavior

    def execute(self, sql: str):
        if self._behavior == "no_table":
            raise psycopg2.errors.UndefinedTable("relation does not exist")

    def fetchone(self):
        if self._behavior == "no_row":
            return None
        if self._behavior == "wrong_value":
            return ("WRONG_VALUE_XYZ",)
        return (_MARKER_VALUE,)

    def __enter__(self): return self
    def __exit__(self, *a): pass


class _MarkerConn:
    """_assert_isolation_marker 단위 테스트용 최소 Mock 연결."""
    def __init__(self, behavior: str):
        self._behavior = behavior
        self._rolled_back = False

    def cursor(self):
        return _MarkerCursor(self._behavior)

    def rollback(self):
        self._rolled_back = True


def test_DB_INT_19_reject_missing_marker_table(request):
    """격리 마커 테이블 없음 → RuntimeError."""
    if not request.config.getoption("--run-db-int", default=False):
        pytest.skip("--run-db-int 필요")
    mock_conn = _MarkerConn("no_table")
    with pytest.raises(RuntimeError, match=_MARKER_TABLE):
        _assert_isolation_marker(mock_conn)
    assert mock_conn._rolled_back, "UndefinedTable 오류 후 rollback 호출 필요"


def test_DB_INT_20_reject_wrong_marker_value(request):
    """격리 마커 값 불일치 → RuntimeError."""
    if not request.config.getoption("--run-db-int", default=False):
        pytest.skip("--run-db-int 필요")
    mock_conn = _MarkerConn("wrong_value")
    with pytest.raises(RuntimeError, match="마커 값 불일치"):
        _assert_isolation_marker(mock_conn)


def test_DB_INT_21_correct_marker_passes(request):
    """정상 격리 마커 → RuntimeError 없음."""
    if not request.config.getoption("--run-db-int", default=False):
        pytest.skip("--run-db-int 필요")
    mock_conn = _MarkerConn("correct")
    _assert_isolation_marker(mock_conn)  # 예외 없으면 PASS


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
