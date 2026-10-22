"""SEC-02 인접 P0: work_assignments / generate_daily_assignments() 접근 차단 (Option A).
WO-TAI-SEC02-ADJ-P0-OPTION-A-IMPLEMENT-001 소스 계약 테스트.

마이그레이션: supabase/migrations/20261022071824_sec02_adj_p0_work_assignments_generate_daily_lockdown.sql

검증 방식: 정적 SQL 파일 분석 (파일 기반).
격리 DB 실측(DB_INT)은 RUNTIME_UNVERIFIED.

SOURCE GATE 기준:
  - 대상 객체 정확히 2개 (work_assignments, generate_daily_assignments())
  - DROP POLICY 정확히 5건 (work_assignments 사용자 정책)
  - REVOKE ALL PRIVILEGES ON TABLE 정확히 1건
  - REVOKE EXECUTE ON FUNCTION 정확히 1건
  - PUBLIC / anon / authenticated 모두 포함
  - service_role REVOKE 없음
  - postgres REVOKE 없음
  - service_role_full DROP 없음
  - RLS DISABLE 없음
  - 테이블 구조 변경 없음 (CREATE/ALTER/DROP TABLE 없음)
  - 데이터 DML 없음
  - 함수 정의 변경 없음 (CREATE/ALTER/DROP FUNCTION 없음)
  - RPC 서명 정확히 일치 (generate_daily_assignments())
  - 사전·사후조건 검증 블록 존재 (PRE FAILED / POST FAILED)
  - 기존 SEC-02-EX-001 및 SEC-04 Migration 불변

테스트 목록:
  SA-SQL-01  Migration 파일 존재
  SA-SQL-02  work_assignments 명시
  SA-SQL-03  generate_daily_assignments 명시
  SA-SQL-04  DROP POLICY 정확히 5건
  SA-SQL-05  work_assignments 5개 정책 명시
  SA-SQL-06  service_role_full DROP 없음
  SA-SQL-07  REVOKE ALL PRIVILEGES ON TABLE 정확히 1건
  SA-SQL-08  REVOKE EXECUTE ON FUNCTION 정확히 1건
  SA-SQL-09  PUBLIC 포함 (테이블 REVOKE)
  SA-SQL-10  anon 포함 (테이블 REVOKE)
  SA-SQL-11  authenticated 포함 (테이블 REVOKE)
  SA-SQL-12  PUBLIC 포함 (함수 REVOKE)
  SA-SQL-13  anon 포함 (함수 REVOKE)
  SA-SQL-14  authenticated 포함 (함수 REVOKE)
  SA-SQL-15  service_role REVOKE 없음
  SA-SQL-16  postgres REVOKE 없음
  SA-SQL-17  RLS DISABLE 없음
  SA-SQL-18  테이블 구조 변경 없음 (CREATE/ALTER/DROP TABLE 없음)
  SA-SQL-19  데이터 DML 없음
  SA-SQL-20  함수 정의 변경 없음 (CREATE/ALTER/DROP FUNCTION 없음)
  SA-SQL-21  RPC 서명 정확히 일치 (generate_daily_assignments())
  SA-SQL-22  사전조건 검증 블록 존재 (PRE FAILED 패턴)
  SA-SQL-23  사후조건 검증 블록 존재 (POST FAILED 패턴)
  SA-SQL-24  has_table_privilege 유효 권한 검사 존재
  SA-SQL-25  has_function_privilege 유효 권한 검사 존재
  SA-SQL-26  service_role 보존 검사 존재
  SA-SQL-27  postgres 보존 검사 존재
  SA-SQL-28  SECURITY INVOKER 유지 확인 (prosecdef)
  SA-SRC-01  SEC-02-EX-001 Migration 불변
  SA-SRC-02  SEC-04 CSI4 Migration 불변
  SA-SRC-03  SEC-04 UDL7 Migration 불변
  SA-SRC-04  SEC-04 Remaining6 Migration 불변
  SA-SRC-05  SEC-04 current_user_id Migration 불변
"""
from __future__ import annotations

import hashlib
import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_MIGRATION = (
    _ROOT
    / "supabase"
    / "migrations"
    / "20261022071824_sec02_adj_p0_work_assignments_generate_daily_lockdown.sql"
)

# 기존 Migration 불변 기준 (SHA256)
_SEC02_EX001_MIGRATION = (
    _ROOT / "supabase" / "migrations"
    / "20261022020000_sec02_ex001_inspection_work_schedules_lockdown.sql"
)
_CSI4_MIGRATION = (
    _ROOT / "supabase" / "migrations"
    / "20261022000001_sec04_csi_privilege_function_revoke.sql"
)
_UDL7_MIGRATION = (
    _ROOT / "supabase" / "migrations"
    / "20261022000002_sec04_udl7_privilege_function_revoke.sql"
)
_REMAINING6_MIGRATION = (
    _ROOT / "supabase" / "migrations"
    / "20261022000003_sec04_remaining6_privilege_function_revoke.sql"
)
_CURRENT_USER_ID_MIGRATION = (
    _ROOT / "supabase" / "migrations"
    / "20261022010122_sec04_current_user_id_privilege_function_revoke.sql"
)

_WORK_ASSIGNMENTS_POLICIES = [
    "anon_select_work_assignments",
    "anon_insert_work_assignments",
    "anon_update_work_assignments",
    "anon_delete_work_assignments",
    "authenticated_all_work_assignments",
]


def _sql() -> str:
    return _MIGRATION.read_text(encoding="utf-8")


def _sql_upper() -> str:
    return _sql().upper()


def _non_comment_lines(sql: str) -> str:
    lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    return "\n".join(lines)


def _nc_upper() -> str:
    return _non_comment_lines(_sql()).upper()


# ── SA-SQL ────────────────────────────────────────────────────────────────────


def test_sa_sql_01_migration_file_exists():
    """SA-SQL-01: Migration 파일 존재"""
    assert _MIGRATION.exists(), f"Migration 파일 없음: {_MIGRATION}"


def test_sa_sql_02_work_assignments_mentioned():
    """SA-SQL-02: work_assignments 명시"""
    assert "work_assignments" in _sql(), "work_assignments 없음"


def test_sa_sql_03_generate_daily_assignments_mentioned():
    """SA-SQL-03: generate_daily_assignments 명시"""
    assert "generate_daily_assignments" in _sql(), "generate_daily_assignments 없음"


def test_sa_sql_04_drop_policy_count():
    """SA-SQL-04: DROP POLICY 정확히 5건"""
    count = len(re.findall(r"\bDROP\s+POLICY\b", _nc_upper()))
    assert count == 5, f"DROP POLICY 수가 5이어야 합니다. 실제: {count}"


def test_sa_sql_05_work_assignments_five_policies():
    """SA-SQL-05: work_assignments 5개 정책 명시"""
    sql = _sql()
    for policy in _WORK_ASSIGNMENTS_POLICIES:
        assert policy in sql, f"work_assignments 정책 없음: {policy}"


def test_sa_sql_06_service_role_full_not_dropped():
    """SA-SQL-06: service_role_full DROP 없음"""
    nc = _non_comment_lines(_sql())
    drops = re.findall(r"DROP\s+POLICY\s+\S+", nc, re.IGNORECASE)
    for d in drops:
        assert "service_role_full" not in d.lower(), (
            f"service_role_full 정책이 DROP 대상에 포함됨: {d}"
        )


def test_sa_sql_07_revoke_all_privileges_table_count():
    """SA-SQL-07: REVOKE ALL PRIVILEGES ON TABLE 정확히 1건"""
    count = len(re.findall(r"\bREVOKE\s+ALL\s+PRIVILEGES\s+ON\s+TABLE\b", _nc_upper()))
    assert count == 1, f"REVOKE ALL PRIVILEGES ON TABLE 수가 1이어야 합니다. 실제: {count}"


def test_sa_sql_08_revoke_execute_function_count():
    """SA-SQL-08: REVOKE EXECUTE ON FUNCTION 정확히 1건"""
    count = len(re.findall(r"\bREVOKE\s+EXECUTE\s+ON\s+FUNCTION\b", _nc_upper()))
    assert count == 1, f"REVOKE EXECUTE ON FUNCTION 수가 1이어야 합니다. 실제: {count}"


def test_sa_sql_09_public_in_table_revoke():
    """SA-SQL-09: 테이블 REVOKE FROM 절에 PUBLIC 포함"""
    nc = _nc_upper()
    blocks = re.findall(r"REVOKE\s+ALL\s+PRIVILEGES\s+ON\s+TABLE[^;]+;", nc, re.DOTALL)
    assert len(blocks) == 1, f"REVOKE ALL PRIVILEGES ON TABLE 블록 수: {len(blocks)}"
    assert "PUBLIC" in blocks[0], "테이블 REVOKE FROM 절에 PUBLIC 없음"


def test_sa_sql_10_anon_in_table_revoke():
    """SA-SQL-10: 테이블 REVOKE FROM 절에 anon 포함"""
    nc = _nc_upper()
    blocks = re.findall(r"REVOKE\s+ALL\s+PRIVILEGES\s+ON\s+TABLE[^;]+;", nc, re.DOTALL)
    assert len(blocks) == 1
    assert "ANON" in blocks[0], "테이블 REVOKE FROM 절에 anon 없음"


def test_sa_sql_11_authenticated_in_table_revoke():
    """SA-SQL-11: 테이블 REVOKE FROM 절에 authenticated 포함"""
    nc = _nc_upper()
    blocks = re.findall(r"REVOKE\s+ALL\s+PRIVILEGES\s+ON\s+TABLE[^;]+;", nc, re.DOTALL)
    assert len(blocks) == 1
    assert "AUTHENTICATED" in blocks[0], "테이블 REVOKE FROM 절에 authenticated 없음"


def test_sa_sql_12_public_in_function_revoke():
    """SA-SQL-12: 함수 REVOKE FROM 절에 PUBLIC 포함"""
    nc = _nc_upper()
    blocks = re.findall(r"REVOKE\s+EXECUTE\s+ON\s+FUNCTION[^;]+;", nc, re.DOTALL)
    assert len(blocks) == 1, f"REVOKE EXECUTE ON FUNCTION 블록 수: {len(blocks)}"
    assert "PUBLIC" in blocks[0], "함수 REVOKE FROM 절에 PUBLIC 없음"


def test_sa_sql_13_anon_in_function_revoke():
    """SA-SQL-13: 함수 REVOKE FROM 절에 anon 포함"""
    nc = _nc_upper()
    blocks = re.findall(r"REVOKE\s+EXECUTE\s+ON\s+FUNCTION[^;]+;", nc, re.DOTALL)
    assert len(blocks) == 1
    assert "ANON" in blocks[0], "함수 REVOKE FROM 절에 anon 없음"


def test_sa_sql_14_authenticated_in_function_revoke():
    """SA-SQL-14: 함수 REVOKE FROM 절에 authenticated 포함"""
    nc = _nc_upper()
    blocks = re.findall(r"REVOKE\s+EXECUTE\s+ON\s+FUNCTION[^;]+;", nc, re.DOTALL)
    assert len(blocks) == 1
    assert "AUTHENTICATED" in blocks[0], "함수 REVOKE FROM 절에 authenticated 없음"


def test_sa_sql_15_no_service_role_revoke():
    """SA-SQL-15: service_role REVOKE 없음"""
    nc = _nc_upper()
    sr_revokes = re.findall(r"REVOKE[^;]*SERVICE_ROLE", nc)
    assert not sr_revokes, f"service_role REVOKE 발견: {sr_revokes}"


def test_sa_sql_16_no_postgres_revoke():
    """SA-SQL-16: postgres REVOKE 없음"""
    nc = _nc_upper()
    pg_revokes = re.findall(r"REVOKE[^;]*\bPOSTGRES\b", nc)
    assert not pg_revokes, f"postgres REVOKE 발견: {pg_revokes}"


def test_sa_sql_17_no_rls_disable():
    """SA-SQL-17: RLS DISABLE 없음"""
    sql_u = _sql_upper()
    assert "DISABLE ROW" not in sql_u, "DISABLE ROW LEVEL SECURITY 발견"
    nc = _nc_upper()
    assert "DISABLE ROW" not in nc, "DISABLE ROW LEVEL SECURITY (비주석) 발견"


def test_sa_sql_18_no_table_ddl():
    """SA-SQL-18: 테이블 구조 변경 없음 (CREATE/ALTER/DROP TABLE 없음)"""
    nc = _nc_upper()
    assert not re.search(r"\bCREATE\s+TABLE\b", nc), "CREATE TABLE 발견"
    assert not re.search(r"\bALTER\s+TABLE\b", nc), "ALTER TABLE 발견"
    assert not re.search(r"\bDROP\s+TABLE\b", nc), "DROP TABLE 발견"


def test_sa_sql_19_no_data_mutation():
    """SA-SQL-19: 데이터 DML 없음 (INSERT INTO/DELETE FROM/UPDATE…SET/TRUNCATE 없음)"""
    nc = _nc_upper()
    # INSERT/UPDATE/DELETE 는 has_table_privilege/RAISE 메시지에 합법 등장.
    # 실제 DML 구문 패턴으로 한정 검사.
    assert not re.search(r"\bINSERT\s+INTO\b", nc), "INSERT INTO 발견"
    assert not re.search(r"\bDELETE\s+FROM\b", nc), "DELETE FROM 발견"
    assert not re.search(r"\bTRUNCATE\b", nc), "TRUNCATE 발견"
    assert not re.search(r"\bUPDATE\b\s+\w+\s+SET\b", nc), "UPDATE … SET 발견"


def test_sa_sql_20_no_function_ddl():
    """SA-SQL-20: 함수 정의 변경 없음 (CREATE/ALTER/DROP FUNCTION 없음)"""
    sql_u = _sql_upper()
    assert "CREATE OR REPLACE FUNCTION" not in sql_u, "CREATE OR REPLACE FUNCTION 발견"
    assert "CREATE FUNCTION" not in sql_u, "CREATE FUNCTION 발견"
    assert "ALTER FUNCTION" not in sql_u, "ALTER FUNCTION 발견"
    assert "DROP FUNCTION" not in sql_u, "DROP FUNCTION 발견"


def test_sa_sql_21_rpc_signature_correct():
    """SA-SQL-21: RPC 서명 정확히 generate_daily_assignments() (빈 인수)"""
    assert re.search(
        r"generate_daily_assignments\s*\(\s*\)", _sql(), re.IGNORECASE
    ), "generate_daily_assignments() 서명 없음"


def test_sa_sql_22_precondition_block_exists():
    """SA-SQL-22: 사전조건 검증 블록 존재 (PRE FAILED 패턴)"""
    assert "PRE FAILED" in _sql(), "PRE FAILED 패턴 없음"
    nc = _non_comment_lines(_sql())
    assert "PRE FAILED" in nc, "비주석 영역에 PRE FAILED 없음"


def test_sa_sql_23_postcondition_block_exists():
    """SA-SQL-23: 사후조건 검증 블록 존재 (POST FAILED 패턴)"""
    assert "POST FAILED" in _sql(), "POST FAILED 패턴 없음"
    nc = _non_comment_lines(_sql())
    assert "POST FAILED" in nc, "비주석 영역에 POST FAILED 없음"


def test_sa_sql_24_has_table_privilege_check():
    """SA-SQL-24: has_table_privilege 유효 권한 검사 존재"""
    nc = _non_comment_lines(_sql())
    assert re.search(r"\bhas_table_privilege\b", nc, re.IGNORECASE), (
        "has_table_privilege 검사 없음"
    )


def test_sa_sql_25_has_function_privilege_check():
    """SA-SQL-25: has_function_privilege 유효 권한 검사 존재"""
    nc = _non_comment_lines(_sql())
    assert re.search(r"\bhas_function_privilege\b", nc, re.IGNORECASE), (
        "has_function_privilege 검사 없음"
    )


def test_sa_sql_26_service_role_preserved_check():
    """SA-SQL-26: service_role 보존 검사 존재 (테이블 + 함수)"""
    nc = _non_comment_lines(_sql())
    assert re.search(
        r"has_table_privilege\s*\(\s*'service_role'", nc, re.IGNORECASE
    ), "has_table_privilege('service_role'...) 없음"
    assert re.search(
        r"has_function_privilege\s*\(\s*'service_role'", nc, re.IGNORECASE
    ), "has_function_privilege('service_role'...) 없음"


def test_sa_sql_27_postgres_preserved_check():
    """SA-SQL-27: postgres 보존 검사 존재 (함수 EXECUTE)"""
    nc = _non_comment_lines(_sql())
    assert re.search(
        r"has_function_privilege\s*\(\s*'postgres'", nc, re.IGNORECASE
    ), "has_function_privilege('postgres'...) 없음"


def test_sa_sql_28_security_invoker_check():
    """SA-SQL-28: SECURITY INVOKER 유지 확인 (prosecdef 검사 존재)"""
    nc = _non_comment_lines(_sql())
    assert re.search(r"\bprosecdef\b", nc, re.IGNORECASE), (
        "prosecdef 검사 없음 — SECURITY INVOKER 유지 미확인"
    )


# ── SA-SRC — 기존 Migration 불변 ─────────────────────────────────────────────


def test_sa_src_01_sec02_ex001_migration_unchanged():
    """SA-SRC-01: SEC-02-EX-001 Migration 불변"""
    assert _SEC02_EX001_MIGRATION.exists(), (
        f"SEC-02-EX-001 Migration 없음: {_SEC02_EX001_MIGRATION}"
    )
    sha256 = hashlib.sha256(_SEC02_EX001_MIGRATION.read_bytes()).hexdigest()
    expected = "2e5d41e51b54b98d8ac1a3bc2ed971dfc62f51b900a77bdac572965db7742f2f"
    assert sha256 == expected, (
        f"SEC-02-EX-001 Migration 변경.\n  기대: {expected}\n  실제: {sha256}"
    )


def test_sa_src_02_sec04_csi4_migration_unchanged():
    """SA-SRC-02: SEC-04 CSI4 Migration 불변"""
    assert _CSI4_MIGRATION.exists(), f"CSI4 Migration 없음: {_CSI4_MIGRATION}"
    sha256 = hashlib.sha256(_CSI4_MIGRATION.read_bytes()).hexdigest()
    expected = "55cc93031d178022a59f958e0e04376d55db028c9da5ace972dd6afe1fccccf1"
    assert sha256 == expected, (
        f"CSI4 Migration 변경.\n  기대: {expected}\n  실제: {sha256}"
    )


def test_sa_src_03_sec04_udl7_migration_unchanged():
    """SA-SRC-03: SEC-04 UDL7 Migration 불변"""
    assert _UDL7_MIGRATION.exists(), f"UDL7 Migration 없음: {_UDL7_MIGRATION}"
    sha256 = hashlib.sha256(_UDL7_MIGRATION.read_bytes()).hexdigest()
    expected = "daa604b86b2ae479c8d594f47f298c3b271c2fe347fcddac9bc86c9d7f45e28c"
    assert sha256 == expected, (
        f"UDL7 Migration 변경.\n  기대: {expected}\n  실제: {sha256}"
    )


def test_sa_src_04_sec04_remaining6_migration_unchanged():
    """SA-SRC-04: SEC-04 Remaining6 Migration 불변"""
    assert _REMAINING6_MIGRATION.exists(), (
        f"Remaining6 Migration 없음: {_REMAINING6_MIGRATION}"
    )
    sha256 = hashlib.sha256(_REMAINING6_MIGRATION.read_bytes()).hexdigest()
    expected = "06d89b0a2168592ac05845ba9c847601aa1468ff708556921a1acf5e6335b24e"
    assert sha256 == expected, (
        f"Remaining6 Migration 변경.\n  기대: {expected}\n  실제: {sha256}"
    )


def test_sa_src_05_sec04_current_user_id_migration_unchanged():
    """SA-SRC-05: SEC-04 current_user_id Migration 불변"""
    assert _CURRENT_USER_ID_MIGRATION.exists(), (
        f"current_user_id Migration 없음: {_CURRENT_USER_ID_MIGRATION}"
    )
    sha256 = hashlib.sha256(_CURRENT_USER_ID_MIGRATION.read_bytes()).hexdigest()
    expected = "6edd6486ae66de6516d7cef85d952606325a50fd20b576cf442ae1a920d29f70"
    assert sha256 == expected, (
        f"current_user_id Migration 변경.\n  기대: {expected}\n  실제: {sha256}"
    )
