"""SEC-02-EX-001 inspection_sets / work_schedules 직접 접근 차단 (Option A).
WO-TAI-SEC02-EX001-P0-OPTION-A-IMPLEMENT-001 소스 계약 테스트.

마이그레이션: supabase/migrations/20261022020000_sec02_ex001_inspection_work_schedules_lockdown.sql

검증 방식: 정적 SQL 파일 분석 (파일 기반).
격리 DB 실측(DB_INT)은 RUNTIME_UNVERIFIED.

SOURCE GATE 기준:
  - 대상 테이블 정확히 2개 (inspection_sets, work_schedules)
  - DROP POLICY 정확히 10건 (테이블당 5개)
  - REVOKE 대상 테이블 정확히 2개
  - PUBLIC / anon / authenticated 모두 포함
  - service_role REVOKE 없음
  - postgres 권한 변경 없음
  - service_role_full DROP 없음
  - RLS DISABLE 없음 (DROP TABLE, ALTER TABLE SET 변경 없음)
  - 테이블 구조 변경 없음 (CREATE/ALTER/DROP TABLE 없음)
  - 데이터 DML 없음 (INSERT/UPDATE/DELETE/TRUNCATE 없음)
  - 함수 본문 변경 없음 (CREATE/ALTER/DROP FUNCTION 없음)
  - 트리거 변경 없음 (CREATE/ALTER/DROP TRIGGER 없음)
  - 사전·사후조건 검증 블록 존재
  - SEC-04 기존 Migration 불변

테스트 목록:
  S2-SQL-01  Migration 파일 존재
  S2-SQL-02  대상 테이블 inspection_sets 명시
  S2-SQL-03  대상 테이블 work_schedules 명시
  S2-SQL-04  DROP POLICY 정확히 10건
  S2-SQL-05  inspection_sets 5개 정책 명시
  S2-SQL-06  work_schedules 5개 정책 명시
  S2-SQL-07  service_role_full DROP 없음
  S2-SQL-08  REVOKE ALL PRIVILEGES 2건
  S2-SQL-09  PUBLIC 포함
  S2-SQL-10  anon 포함
  S2-SQL-11  authenticated 포함
  S2-SQL-12  service_role REVOKE 없음
  S2-SQL-13  postgres REVOKE 없음
  S2-SQL-14  RLS DISABLE 없음
  S2-SQL-15  테이블 구조 변경 없음 (CREATE/ALTER/DROP TABLE 없음)
  S2-SQL-16  데이터 DML 없음
  S2-SQL-17  함수 변경 없음
  S2-SQL-18  트리거 변경 없음
  S2-SQL-19  사전조건 검증 블록 존재 (PRE FAILED 패턴)
  S2-SQL-20  사후조건 검증 블록 존재 (POST FAILED 패턴)
  S2-SRC-01  SEC-04 CSI4 Migration 불변
  S2-SRC-02  SEC-04 UDL7 Migration 불변
  S2-SRC-03  SEC-04 Remaining6 Migration 불변
  S2-SRC-04  SEC-04 current_user_id Migration 불변
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
    / "20261022020000_sec02_ex001_inspection_work_schedules_lockdown.sql"
)

# SEC-04 기존 Migration 해시 (불변 기준)
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

_INSPECTION_SETS_POLICIES = [
    "anon_select_inspection_sets",
    "anon_insert_inspection_sets",
    "anon_update_inspection_sets",
    "anon_delete_inspection_sets",
    "authenticated_all_inspection_sets",
]
_WORK_SCHEDULES_POLICIES = [
    "anon_select_work_schedules",
    "anon_insert_work_schedules",
    "anon_update_work_schedules",
    "anon_delete_work_schedules",
    "authenticated_all_work_schedules",
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


# ── S2-SQL ────────────────────────────────────────────────────────────────────


def test_s2_sql_01_migration_file_exists():
    """S2-SQL-01: Migration 파일 존재"""
    assert _MIGRATION.exists(), f"Migration 파일 없음: {_MIGRATION}"


def test_s2_sql_02_inspection_sets_mentioned():
    """S2-SQL-02: 대상 테이블 inspection_sets 명시"""
    assert "inspection_sets" in _sql(), "inspection_sets 테이블명 없음"


def test_s2_sql_03_work_schedules_mentioned():
    """S2-SQL-03: 대상 테이블 work_schedules 명시"""
    assert "work_schedules" in _sql(), "work_schedules 테이블명 없음"


def test_s2_sql_04_drop_policy_count():
    """S2-SQL-04: DROP POLICY 정확히 10건"""
    count = len(re.findall(r"\bDROP\s+POLICY\b", _nc_upper()))
    assert count == 10, f"DROP POLICY 문 수가 10이어야 합니다. 실제: {count}"


def test_s2_sql_05_inspection_sets_five_policies():
    """S2-SQL-05: inspection_sets 대상 5개 정책 명시"""
    sql = _sql()
    for policy in _INSPECTION_SETS_POLICIES:
        assert policy in sql, f"inspection_sets 정책 없음: {policy}"


def test_s2_sql_06_work_schedules_five_policies():
    """S2-SQL-06: work_schedules 대상 5개 정책 명시"""
    sql = _sql()
    for policy in _WORK_SCHEDULES_POLICIES:
        assert policy in sql, f"work_schedules 정책 없음: {policy}"


def test_s2_sql_07_service_role_full_not_dropped():
    """S2-SQL-07: service_role_full DROP 없음"""
    nc = _non_comment_lines(_sql())
    drops = re.findall(r"DROP\s+POLICY\s+\S+", nc, re.IGNORECASE)
    for d in drops:
        assert "service_role_full" not in d.lower(), (
            f"service_role_full 정책이 DROP 대상에 포함됨: {d}"
        )


def test_s2_sql_08_revoke_all_privileges_count():
    """S2-SQL-08: REVOKE ALL PRIVILEGES ON TABLE 정확히 2건"""
    count = len(re.findall(r"\bREVOKE\s+ALL\s+PRIVILEGES\s+ON\s+TABLE\b", _nc_upper()))
    assert count == 2, f"REVOKE ALL PRIVILEGES ON TABLE 수가 2이어야 합니다. 실제: {count}"


def test_s2_sql_09_public_included():
    """S2-SQL-09: REVOKE FROM 절에 PUBLIC 포함"""
    nc = _nc_upper()
    revoke_blocks = re.findall(r"REVOKE\s+ALL\s+PRIVILEGES\s+ON\s+TABLE[^;]+;", nc, re.DOTALL)
    assert len(revoke_blocks) == 2, f"REVOKE 블록 수: {len(revoke_blocks)}"
    for block in revoke_blocks:
        assert "PUBLIC" in block, f"REVOKE FROM 절에 PUBLIC 없음: {block}"


def test_s2_sql_10_anon_included():
    """S2-SQL-10: REVOKE FROM 절에 anon 포함"""
    nc = _nc_upper()
    revoke_blocks = re.findall(r"REVOKE\s+ALL\s+PRIVILEGES\s+ON\s+TABLE[^;]+;", nc, re.DOTALL)
    assert len(revoke_blocks) == 2
    for block in revoke_blocks:
        assert "ANON" in block, f"REVOKE FROM 절에 anon 없음: {block}"


def test_s2_sql_11_authenticated_included():
    """S2-SQL-11: REVOKE FROM 절에 authenticated 포함"""
    nc = _nc_upper()
    revoke_blocks = re.findall(r"REVOKE\s+ALL\s+PRIVILEGES\s+ON\s+TABLE[^;]+;", nc, re.DOTALL)
    assert len(revoke_blocks) == 2
    for block in revoke_blocks:
        assert "AUTHENTICATED" in block, f"REVOKE FROM 절에 authenticated 없음: {block}"


def test_s2_sql_12_no_service_role_revoke():
    """S2-SQL-12: service_role REVOKE 없음"""
    nc = _nc_upper()
    sr_revokes = re.findall(r"REVOKE[^;]*SERVICE_ROLE", nc)
    assert not sr_revokes, f"service_role REVOKE 발견: {sr_revokes}"


def test_s2_sql_13_no_postgres_revoke():
    """S2-SQL-13: postgres 권한 변경 없음"""
    nc = _nc_upper()
    pg_revokes = re.findall(r"REVOKE[^;]*\bPOSTGRES\b", nc)
    assert not pg_revokes, f"postgres REVOKE 발견: {pg_revokes}"


def test_s2_sql_14_no_rls_disable():
    """S2-SQL-14: RLS DISABLE 없음"""
    sql_u = _sql_upper()
    assert "DISABLE ROW" not in sql_u, "DISABLE ROW LEVEL SECURITY 발견"
    nc = _nc_upper()
    assert "DISABLE ROW" not in nc, "DISABLE ROW LEVEL SECURITY (비주석) 발견"


def test_s2_sql_15_no_table_ddl():
    """S2-SQL-15: 테이블 구조 변경 없음 (CREATE/ALTER/DROP TABLE 없음)"""
    nc = _nc_upper()
    assert not re.search(r"\bCREATE\s+TABLE\b", nc), "CREATE TABLE 발견"
    assert not re.search(r"\bALTER\s+TABLE\b", nc), "ALTER TABLE 발견"
    assert not re.search(r"\bDROP\s+TABLE\b", nc), "DROP TABLE 발견"


def test_s2_sql_16_no_data_mutation():
    """S2-SQL-16: 데이터 DML 없음 (INSERT/UPDATE/DELETE/TRUNCATE 없음)"""
    nc = _nc_upper()
    assert not re.search(r"\bINSERT\b", nc), "INSERT 발견"
    assert not re.search(r"\bUPDATE\b", nc), "UPDATE 발견"
    assert not re.search(r"\bDELETE\b", nc), "DELETE 발견"
    assert not re.search(r"\bTRUNCATE\b", nc), "TRUNCATE 발견"


def test_s2_sql_17_no_function_ddl():
    """S2-SQL-17: 함수 변경 없음 (CREATE/ALTER/DROP FUNCTION 없음)"""
    sql_u = _sql_upper()
    assert "CREATE OR REPLACE FUNCTION" not in sql_u, "CREATE OR REPLACE FUNCTION 발견"
    assert "CREATE FUNCTION" not in sql_u, "CREATE FUNCTION 발견"
    assert "ALTER FUNCTION" not in sql_u, "ALTER FUNCTION 발견"
    assert "DROP FUNCTION" not in sql_u, "DROP FUNCTION 발견"


def test_s2_sql_18_no_trigger_ddl():
    """S2-SQL-18: 트리거 변경 없음 (CREATE/ALTER/DROP TRIGGER 없음)"""
    sql_u = _sql_upper()
    assert "CREATE TRIGGER" not in sql_u, "CREATE TRIGGER 발견"
    assert "ALTER TRIGGER" not in sql_u, "ALTER TRIGGER 발견"
    assert "DROP TRIGGER" not in sql_u, "DROP TRIGGER 발견"


def test_s2_sql_19_precondition_block_exists():
    """S2-SQL-19: 사전조건 검증 블록 존재 (PRE FAILED 패턴)"""
    assert "PRE FAILED" in _sql(), "사전조건 검증 패턴 'PRE FAILED' 없음"
    nc = _non_comment_lines(_sql())
    assert "PRE FAILED" in nc, "비주석 영역에 사전조건 검증 없음"


def test_s2_sql_20_postcondition_block_exists():
    """S2-SQL-20: 사후조건 검증 블록 존재 (POST FAILED 패턴)"""
    assert "POST FAILED" in _sql(), "사후조건 검증 패턴 'POST FAILED' 없음"
    nc = _non_comment_lines(_sql())
    assert "POST FAILED" in nc, "비주석 영역에 사후조건 검증 없음"


# ── S2-SRC — SEC-04 기존 Migration 불변 ──────────────────────────────────────


def test_s2_src_01_sec04_csi4_migration_unchanged():
    """S2-SRC-01: SEC-04 CSI4 Migration 불변"""
    assert _CSI4_MIGRATION.exists(), f"CSI4 Migration 없음: {_CSI4_MIGRATION}"
    sha256 = hashlib.sha256(_CSI4_MIGRATION.read_bytes()).hexdigest()
    expected = "55cc93031d178022a59f958e0e04376d55db028c9da5ace972dd6afe1fccccf1"
    assert sha256 == expected, (
        f"CSI4 Migration 변경.\n  기대: {expected}\n  실제: {sha256}"
    )


def test_s2_src_02_sec04_udl7_migration_unchanged():
    """S2-SRC-02: SEC-04 UDL7 Migration 불변"""
    assert _UDL7_MIGRATION.exists(), f"UDL7 Migration 없음: {_UDL7_MIGRATION}"
    sha256 = hashlib.sha256(_UDL7_MIGRATION.read_bytes()).hexdigest()
    expected = "daa604b86b2ae479c8d594f47f298c3b271c2fe347fcddac9bc86c9d7f45e28c"
    assert sha256 == expected, (
        f"UDL7 Migration 변경.\n  기대: {expected}\n  실제: {sha256}"
    )


def test_s2_src_03_sec04_remaining6_migration_unchanged():
    """S2-SRC-03: SEC-04 Remaining6 Migration 불변"""
    assert _REMAINING6_MIGRATION.exists(), f"Remaining6 Migration 없음: {_REMAINING6_MIGRATION}"
    sha256 = hashlib.sha256(_REMAINING6_MIGRATION.read_bytes()).hexdigest()
    expected = "06d89b0a2168592ac05845ba9c847601aa1468ff708556921a1acf5e6335b24e"
    assert sha256 == expected, (
        f"Remaining6 Migration 변경.\n  기대: {expected}\n  실제: {sha256}"
    )


def test_s2_src_04_sec04_current_user_id_migration_unchanged():
    """S2-SRC-04: SEC-04 current_user_id Migration 불변"""
    assert _CURRENT_USER_ID_MIGRATION.exists(), (
        f"current_user_id Migration 없음: {_CURRENT_USER_ID_MIGRATION}"
    )
    sha256 = hashlib.sha256(_CURRENT_USER_ID_MIGRATION.read_bytes()).hexdigest()
    expected = "6edd6486ae66de6516d7cef85d952606325a50fd20b576cf442ae1a920d29f70"
    assert sha256 == expected, (
        f"current_user_id Migration 변경.\n  기대: {expected}\n  실제: {sha256}"
    )
