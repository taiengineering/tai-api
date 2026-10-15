"""WO-E2E2000-C10-PR626-SECURITY-GATE-CORRECTION-001 — DB PR SQL 계약 테스트.

마이그레이션: supabase/migrations/20261016000002_c10_rls_hardening_v2.sql

주의: 이 파일은 SQL 내용 정적 검사(파일 기반)다.
  실제 PostgreSQL pg_policies / 역할별 접근 차단 검증은
  격리 테스트 DB 환경이 필요하며 (DB_INTEGRATION_TEST = REQUIRES_TEST_DB),
  여기서는 마이그레이션 파일의 계약 의도를 정적으로 보장한다.

  DB_INT_01~DB_INT_08 (anon/auth DENY, service_role PASS 실측) =
    TEST_DB_ENVIRONMENT_REQUIRED / BLOCKED until provisioned.

SQL 계약 테스트 목록:
  DB-SQL-01  마이그레이션 파일 존재
  DB-SQL-02  실제 운영 RLS 정책 이름 6개 모두 DROP
  DB-SQL-03  소스 DDL 구형 정책 이름 DROP 포함
  DB-SQL-04  anon REVOKE 존재
  DB-SQL-05  authenticated REVOKE 존재
  DB-SQL-06  PUBLIC REVOKE 존재
  DB-SQL-07  service_role_full 단일 CREATE POLICY만 존재
  DB-SQL-08  anon에 USING(true) 정책 재생성 없음
  DB-SQL-09  authenticated에 USING(true) 정책 재생성 없음
  DB-SQL-10  anon SELECT 조건부(status/expires) 정책 재생성 없음
  DB-SQL-11  authenticated UPDATE/SELECT claim 정책 재생성 없음
  DB-SQL-12  DRIFT GUARD DO $$ 블록 존재
"""
from __future__ import annotations

import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_MIGRATION = _ROOT / "supabase" / "migrations" / "20261016000002_c10_rls_hardening_v2.sql"


def _sql() -> str:
    return _MIGRATION.read_text(encoding="utf-8")


def _sql_upper() -> str:
    return _sql().upper()


# ── 운영 DB 실측 정책 이름 ──────────────────────────────────────────────
LIVE_POLICY_NAMES = [
    "anon_delete_anonymous_diagnosis_results",
    "anon_insert_anonymous_diagnosis_results",
    "anon_select_anonymous_diagnosis_results",
    "anon_update_anonymous_diagnosis_results",
    "authenticated_all_anonymous_diagnosis_results",
    "service_role_full",
]

# ── 소스 DDL 구형 정책 이름 ────────────────────────────────────────────
SOURCE_POLICY_NAMES = [
    "anon_diag_insert_open",
    "anon_diag_select_by_token",
    "anon_diag_select_claimed",
    "anon_diag_update_claim",
    "anon_diag_admin_all",
    "anon_diag_service_role",
]


def _create_policy_blocks(sql: str) -> list[str]:
    """CREATE POLICY 블록 분리 (명령어 단위, 세미콜론 기준)."""
    blocks = re.split(r"(?i)CREATE\s+POLICY", sql)
    return blocks[1:]  # 선두 비정책 부분 제외


# ═══════════════════════════════════════════════════════════════════════
# DB-SQL-01: 파일 존재
# ═══════════════════════════════════════════════════════════════════════

def test_DB_SQL_01_migration_file_exists():
    assert _MIGRATION.exists(), f"마이그레이션 파일 없음: {_MIGRATION}"


# ═══════════════════════════════════════════════════════════════════════
# DB-SQL-02: 운영 RLS 정책 이름 6개 모두 DROP
# ═══════════════════════════════════════════════════════════════════════

def test_DB_SQL_02_live_policy_names_all_dropped():
    sql_u = _sql_upper()
    missing = []
    for name in LIVE_POLICY_NAMES:
        pattern = rf"DROP\s+POLICY\s+IF\s+EXISTS\s+{name.upper()}"
        if not re.search(pattern, sql_u):
            missing.append(name)
    assert not missing, (
        f"운영 DB 실측 정책 이름 DROP 누락: {missing}\n"
        "GPT가 확인한 실제 정책 이름이 마이그레이션에서 삭제되지 않으면 USING(true) 정책이 남습니다."
    )


# ═══════════════════════════════════════════════════════════════════════
# DB-SQL-03: 소스 DDL 구형 정책 이름 DROP 포함
# ═══════════════════════════════════════════════════════════════════════

def test_DB_SQL_03_source_dDL_policy_names_dropped():
    sql_u = _sql_upper()
    missing = []
    for name in SOURCE_POLICY_NAMES:
        pattern = rf"DROP\s+POLICY\s+IF\s+EXISTS\s+{name.upper()}"
        if not re.search(pattern, sql_u):
            missing.append(name)
    assert not missing, f"소스 DDL 구형 정책 이름 DROP 누락: {missing}"


# ═══════════════════════════════════════════════════════════════════════
# DB-SQL-04~06: REVOKE 구문 존재
# ═══════════════════════════════════════════════════════════════════════

def test_DB_SQL_04_revoke_from_anon():
    sql_u = _sql_upper()
    assert re.search(
        r"REVOKE\s+ALL\s+PRIVILEGES\s+ON\s+PUBLIC\.ANONYMOUS_DIAGNOSIS_RESULTS\s+FROM\s+ANON",
        sql_u,
    ), "REVOKE ALL FROM anon 구문 없음 — 테이블 GRANT 회수 필요"


def test_DB_SQL_05_revoke_from_authenticated():
    sql_u = _sql_upper()
    assert re.search(
        r"REVOKE\s+ALL\s+PRIVILEGES\s+ON\s+PUBLIC\.ANONYMOUS_DIAGNOSIS_RESULTS\s+FROM\s+AUTHENTICATED",
        sql_u,
    ), "REVOKE ALL FROM authenticated 구문 없음"


def test_DB_SQL_06_revoke_from_public():
    sql_u = _sql_upper()
    assert re.search(
        r"REVOKE\s+ALL\s+PRIVILEGES\s+ON\s+PUBLIC\.ANONYMOUS_DIAGNOSIS_RESULTS\s+FROM\s+PUBLIC",
        sql_u,
    ), "REVOKE ALL FROM PUBLIC 구문 없음 — PUBLIC 경유 권한 차단 필요"


# ═══════════════════════════════════════════════════════════════════════
# DB-SQL-07: service_role_full 단일 CREATE POLICY
# ═══════════════════════════════════════════════════════════════════════

def test_DB_SQL_07_only_service_role_full_created():
    sql = _sql()
    blocks = _create_policy_blocks(sql)
    assert len(blocks) == 1, (
        f"CREATE POLICY 블록이 {len(blocks)}개 — service_role_full 1개만 허용"
    )
    block = blocks[0]
    assert re.search(r"\bservice_role_full\b", block, re.IGNORECASE), (
        "유일한 CREATE POLICY가 service_role_full이 아님"
    )
    assert re.search(r"\bTO\s+service_role\b", block, re.IGNORECASE), (
        "service_role_full 정책에 TO service_role 없음"
    )


# ═══════════════════════════════════════════════════════════════════════
# DB-SQL-08~09: anon/authenticated에 USING(true) 재생성 없음
# ═══════════════════════════════════════════════════════════════════════

def test_DB_SQL_08_no_anon_using_true_policy():
    sql = _sql()
    for block in _create_policy_blocks(sql):
        has_anon = bool(re.search(r"\bTO\s+anon\b", block, re.IGNORECASE))
        has_using_true = bool(re.search(r"USING\s*\(\s*true\s*\)", block, re.IGNORECASE))
        assert not (has_anon and has_using_true), (
            f"anon USING(true) 정책 재생성 발견: ...{block[:200]}..."
        )


def test_DB_SQL_09_no_authenticated_using_true_policy():
    sql = _sql()
    for block in _create_policy_blocks(sql):
        has_auth = bool(re.search(r"\bTO\s+authenticated\b", block, re.IGNORECASE))
        has_using_true = bool(re.search(r"USING\s*\(\s*true\s*\)", block, re.IGNORECASE))
        assert not (has_auth and has_using_true), (
            f"authenticated USING(true) 정책 재생성 발견: ...{block[:200]}..."
        )


# ═══════════════════════════════════════════════════════════════════════
# DB-SQL-10: anon SELECT(status/expires 조건부) 정책 재생성 없음
# ═══════════════════════════════════════════════════════════════════════

def test_DB_SQL_10_no_anon_select_policy_recreated():
    """status/expires 조건부 SELECT도 소유권 미검증으로 최소 권한 원칙 위반.
    재생성하지 않는다.
    """
    sql = _sql()
    for block in _create_policy_blocks(sql):
        has_anon = bool(re.search(r"\bTO\s+anon\b", block, re.IGNORECASE))
        has_select = bool(re.search(r"\bFOR\s+SELECT\b", block, re.IGNORECASE))
        assert not (has_anon and has_select), (
            f"anon SELECT 정책이 재생성됨 — 소유권 미검증으로 차단 대상: ...{block[:200]}..."
        )


# ═══════════════════════════════════════════════════════════════════════
# DB-SQL-11: authenticated UPDATE/SELECT/ALL 정책 재생성 없음
# ═══════════════════════════════════════════════════════════════════════

def test_DB_SQL_11_no_authenticated_dml_policy_recreated():
    sql = _sql()
    for block in _create_policy_blocks(sql):
        has_auth = bool(re.search(r"\bTO\s+authenticated\b", block, re.IGNORECASE))
        assert not has_auth, (
            f"authenticated 정책이 재생성됨 — 직접 접근 전면 차단 위반: ...{block[:200]}..."
        )


# ═══════════════════════════════════════════════════════════════════════
# DB-SQL-12: DRIFT GUARD DO $$ 블록 존재
# ═══════════════════════════════════════════════════════════════════════

def test_DB_SQL_12_drift_guard_do_block_exists():
    """사후 Drift Guard: DROP 이후 예상치 못한 정책이 남아 있으면 EXCEPTION."""
    sql_u = _sql_upper()
    assert "DRIFT_GUARD" in sql_u or "DRIFT GUARD" in sql_u, (
        "Drift Guard 블록 없음 — 예상치 못한 과다 허용 정책 차단 보장 필요"
    )
    assert re.search(r"\bDO\s+\$\$", sql_u) or re.search(r"\bDO\s+\$", sql_u), (
        "Drift Guard DO $$ 블록 없음"
    )
    assert "RAISE EXCEPTION" in sql_u, (
        "Drift Guard RAISE EXCEPTION 없음 — 예상치 못한 정책 발견 시 적용 중단 필요"
    )


# ═══════════════════════════════════════════════════════════════════════
# DB-SQL-13: PRE-CHECK DRIFT GUARD DO $$ 블록 존재 (DROP 이전 중단)
# ═══════════════════════════════════════════════════════════════════════

def test_DB_SQL_13_pre_check_drift_guard_exists():
    """사전 Drift Guard: DROP 이전에 알 수 없는 정책 발견 시 EXCEPTION으로 중단.

    C10_PRE_DRIFT_GUARD_FAIL 식별자 포함 + DROP POLICY 이전 위치에 있어야 함.
    """
    sql = _sql()
    sql_u = sql.upper()

    assert "C10_PRE_DRIFT_GUARD_FAIL" in sql_u, (
        "PRE-CHECK Drift Guard(C10_PRE_DRIFT_GUARD_FAIL) 블록 없음 — "
        "DROP 이전에 알 수 없는 정책 탐지 후 중단 필요"
    )

    # PRE-CHECK가 DROP POLICY 이전에 위치하는지 확인
    pre_check_pos = sql_u.find("C10_PRE_DRIFT_GUARD_FAIL")
    first_drop_pos = sql_u.find("DROP POLICY")
    assert pre_check_pos < first_drop_pos, (
        f"PRE-CHECK Drift Guard(pos={pre_check_pos})가 첫 DROP POLICY(pos={first_drop_pos}) 이후에 위치함. "
        "DROP 이전에 선행 검사가 실행되어야 합니다."
    )

    # NOT IN 절에 운영 DB 실측 이름이 포함되는지 확인
    for name in LIVE_POLICY_NAMES:
        assert name.upper() in sql_u, (
            f"PRE-CHECK NOT IN 절에 운영 정책 이름 누락: {name}"
        )
