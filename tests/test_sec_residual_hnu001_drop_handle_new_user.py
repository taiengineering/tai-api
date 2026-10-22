"""
WO-TAI-SEC-RESIDUAL-HNU-001 정적 계약 테스트
public.handle_new_user() 미사용 함수 제거 Migration 검증

대상 Migration:
  20261022083010_sec_residual_hnu001_drop_handle_new_user.sql

테스트 목록:
  SH-SQL-01  Migration 파일 존재
  SH-SQL-02  BEGIN/COMMIT 트랜잭션 구조
  SH-SQL-03  DROP FUNCTION public.handle_new_user() 정확히 1건
  SH-SQL-04  CASCADE 없음
  SH-SQL-05  DROP FUNCTION IF EXISTS 사용 안 함 (기준선 은폐 방지)
  SH-SQL-06  CREATE TRIGGER 없음
  SH-SQL-07  CREATE FUNCTION 없음
  SH-SQL-08  public.users DML 없음 (INSERT INTO/UPDATE SET/DELETE FROM/TRUNCATE)
  SH-SQL-09  auth.users 구조 변경 없음 (ALTER TABLE auth.users 없음)
  SH-SQL-10  RLS/Policy 변경 없음 (CREATE/DROP/ALTER POLICY 없음)
  SH-SQL-11  PRE: 함수 존재 검증 포함 (pronargs=0 + prorettype='trigger')
  SH-SQL-12  PRE: SECURITY DEFINER 검증 포함 (prosecdef)
  SH-SQL-13  PRE: 소유자 검증 포함 (proowner/postgres)
  SH-SQL-14  PRE: 함수 정의 MD5 기준선 포함
  SH-SQL-15  PRE: 함수 본문 MD5 기준선 포함
  SH-SQL-16  PRE: 연결 트리거 0건 검증 포함 (pg_trigger)
  SH-SQL-17  PRE: DB 종속 객체 0건 검증 포함 (pg_depend)
  SH-SQL-18  PRE: anon EXECUTE = FALSE 검증 포함
  SH-SQL-19  PRE: authenticated EXECUTE = FALSE 검증 포함
  SH-SQL-20  POST: 함수 부재 확인 포함
  SH-SQL-21  REVOKE 없음 (SEC-04 권한 회수 재현 없음)
  SH-SQL-22  다른 SQL DDL 없음 (ALTER TABLE/CREATE TABLE/DROP TABLE)
  SH-SRC-01  이 Migration SHA256 고정
  SH-SRC-02  SEC-02-EX-001 Migration SHA256 불변
  SH-SRC-03  SEC-02-ADJ-P0 Migration SHA256 불변
  SH-SRC-04  SEC-04 remaining6 Migration SHA256 불변
"""

import hashlib
import pathlib
import re

import pytest

_MIGRATION_NAME = "20261022083010_sec_residual_hnu001_drop_handle_new_user.sql"
_MIGRATIONS_DIR = pathlib.Path(__file__).parent.parent / "supabase" / "migrations"
_MIGRATION_PATH = _MIGRATIONS_DIR / _MIGRATION_NAME


def _sql() -> str:
    return _MIGRATION_PATH.read_text(encoding="utf-8")


def _nc_upper() -> str:
    """주석 제거 + 대문자 변환"""
    return _non_comment_lines(_sql())


def _non_comment_lines(sql: str) -> str:
    lines = []
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        lines.append(line)
    return "\n".join(lines).upper()


# ── 파일 존재 ──────────────────────────────────────────────────────────────────

def test_sh_sql_01_migration_file_exists():
    """SH-SQL-01: Migration 파일 존재"""
    assert _MIGRATION_PATH.exists(), f"{_MIGRATION_NAME} 파일 없음"


# ── 트랜잭션 구조 ──────────────────────────────────────────────────────────────

def test_sh_sql_02_transaction_structure():
    """SH-SQL-02: BEGIN/COMMIT 트랜잭션 구조"""
    nc = _nc_upper()
    assert re.search(r"^\s*BEGIN\s*;", nc, re.MULTILINE), "BEGIN; 없음"
    assert re.search(r"^\s*COMMIT\s*;", nc, re.MULTILINE), "COMMIT; 없음"


# ── DROP 대상 ──────────────────────────────────────────────────────────────────

def test_sh_sql_03_drop_function_exactly_one():
    """SH-SQL-03: DROP FUNCTION public.handle_new_user() 정확히 1건"""
    nc = _nc_upper()
    matches = re.findall(
        r"\bDROP\s+FUNCTION\s+PUBLIC\.HANDLE_NEW_USER\s*\(\s*\)", nc, re.IGNORECASE
    )
    assert len(matches) == 1, f"DROP FUNCTION public.handle_new_user() 횟수={len(matches)}, 기대=1"


def test_sh_sql_04_no_cascade():
    """SH-SQL-04: CASCADE 없음"""
    nc = _nc_upper()
    assert not re.search(r"\bCASCADE\b", nc), "CASCADE 발견 — 예상치 못한 종속 제거 위험"


def test_sh_sql_05_no_drop_if_exists():
    """SH-SQL-05: DROP FUNCTION IF EXISTS 사용 안 함 (기준선 은폐 방지)"""
    nc = _nc_upper()
    assert not re.search(r"\bDROP\s+FUNCTION\s+IF\s+EXISTS\b", nc), "DROP FUNCTION IF EXISTS 발견"


# ── 신규 객체 생성 없음 ────────────────────────────────────────────────────────

def test_sh_sql_06_no_create_trigger():
    """SH-SQL-06: CREATE TRIGGER 없음"""
    nc = _nc_upper()
    assert not re.search(r"\bCREATE\s+(OR\s+REPLACE\s+)?TRIGGER\b", nc), "CREATE TRIGGER 발견"


def test_sh_sql_07_no_create_function():
    """SH-SQL-07: CREATE FUNCTION 없음"""
    nc = _nc_upper()
    assert not re.search(r"\bCREATE\s+(OR\s+REPLACE\s+)?FUNCTION\b", nc), "CREATE FUNCTION 발견"


# ── 데이터 및 구조 변경 없음 ──────────────────────────────────────────────────

def test_sh_sql_08_no_public_users_dml():
    """SH-SQL-08: public.users DML 없음"""
    nc = _nc_upper()
    assert not re.search(r"\bINSERT\s+INTO\b", nc), "INSERT INTO 발견"
    assert not re.search(r"\bDELETE\s+FROM\b", nc), "DELETE FROM 발견"
    assert not re.search(r"\bTRUNCATE\b", nc), "TRUNCATE 발견"
    assert not re.search(r"\bUPDATE\b\s+\w+\s+SET\b", nc), "UPDATE … SET 발견"


def test_sh_sql_09_no_auth_users_alter():
    """SH-SQL-09: auth.users 구조 변경 없음"""
    nc = _nc_upper()
    assert not re.search(r"\bALTER\s+TABLE\s+AUTH\b", nc), "ALTER TABLE auth.* 발견"


def test_sh_sql_10_no_rls_policy_change():
    """SH-SQL-10: RLS/Policy 변경 없음"""
    nc = _nc_upper()
    assert not re.search(r"\bCREATE\s+POLICY\b", nc), "CREATE POLICY 발견"
    assert not re.search(r"\bDROP\s+POLICY\b", nc), "DROP POLICY 발견"
    assert not re.search(r"\bALTER\s+POLICY\b", nc), "ALTER POLICY 발견"


# ── PRE 조건 ──────────────────────────────────────────────────────────────────

def test_sh_sql_11_pre_function_signature():
    """SH-SQL-11: PRE — 함수 존재 및 반환형 trigger 검증"""
    nc = _nc_upper()
    assert re.search(r"\bHANDLE_NEW_USER\b", nc), "handle_new_user 참조 없음"
    assert re.search(r"PRORETTYPE", nc, re.IGNORECASE) or re.search(
        r"'TRIGGER'::REGTYPE", nc, re.IGNORECASE
    ), "prorettype/trigger 반환형 검증 없음"


def test_sh_sql_12_pre_security_definer():
    """SH-SQL-12: PRE — SECURITY DEFINER 검증 포함 (prosecdef)"""
    nc = _nc_upper()
    assert re.search(r"\bPROSECDEF\b", nc), "prosecdef 검증 없음"


def test_sh_sql_13_pre_owner_postgres():
    """SH-SQL-13: PRE — 소유자 postgres 검증 포함"""
    nc = _nc_upper()
    assert re.search(r"PROOWNER|PG_GET_USERBYID", nc, re.IGNORECASE), "소유자 검증 없음"
    assert re.search(r"'POSTGRES'", nc), "postgres 소유자 기준값 없음"


def test_sh_sql_14_pre_def_md5():
    """SH-SQL-14: PRE — 함수 정의 MD5 기준선 포함"""
    sql = _sql()
    assert "8e04ca79820d6f495fe808c9eef98756" in sql, "def MD5 기준값 없음"
    assert re.search(r"PG_GET_FUNCTIONDEF", sql, re.IGNORECASE), "pg_get_functiondef 없음"


def test_sh_sql_15_pre_body_md5():
    """SH-SQL-15: PRE — 함수 본문 MD5 기준선 포함"""
    sql = _sql()
    assert "f9ac19e4af493e7cba768d9ee76d5542" in sql, "body MD5 기준값 없음"
    assert re.search(r"\bPROSRC\b", sql, re.IGNORECASE), "prosrc 없음"


def test_sh_sql_16_pre_trigger_count():
    """SH-SQL-16: PRE — 연결 트리거 0건 검증 포함"""
    nc = _nc_upper()
    assert re.search(r"\bPG_TRIGGER\b", nc), "pg_trigger 검증 없음"


def test_sh_sql_17_pre_dep_count():
    """SH-SQL-17: PRE — DB 종속 객체 0건 검증 포함"""
    nc = _nc_upper()
    assert re.search(r"\bPG_DEPEND\b", nc), "pg_depend 검증 없음"


def test_sh_sql_18_pre_anon_execute_false():
    """SH-SQL-18: PRE — anon EXECUTE = FALSE 검증 포함"""
    nc = _nc_upper()
    assert re.search(r"HAS_FUNCTION_PRIVILEGE\s*\(\s*'ANON'", nc), "anon EXECUTE 검증 없음"


def test_sh_sql_19_pre_authenticated_execute_false():
    """SH-SQL-19: PRE — authenticated EXECUTE = FALSE 검증 포함"""
    nc = _nc_upper()
    assert re.search(r"HAS_FUNCTION_PRIVILEGE\s*\(\s*'AUTHENTICATED'", nc), "authenticated EXECUTE 검증 없음"


# ── POST 조건 ─────────────────────────────────────────────────────────────────

def test_sh_sql_20_post_function_absent():
    """SH-SQL-20: POST — 함수 부재 확인 포함"""
    nc = _nc_upper()
    # POST 조건 블록에서 handle_new_user를 조회하고 count=0을 확인
    assert re.search(r"POST.*FAIL|STILL\s+EXISTS|COUNT.*!=\s*0", nc, re.IGNORECASE), \
        "POST 함수 부재 검증 없음"


# ── 추가 안전 제약 ─────────────────────────────────────────────────────────────

def test_sh_sql_21_no_revoke():
    """SH-SQL-21: REVOKE 없음 (SEC-04 권한 회수 재현 없음)"""
    nc = _nc_upper()
    assert not re.search(r"\bREVOKE\b", nc), "REVOKE 발견 — SEC-04 범위 재현 금지"


def test_sh_sql_22_no_alter_create_drop_table():
    """SH-SQL-22: ALTER TABLE/CREATE TABLE/DROP TABLE 없음"""
    nc = _nc_upper()
    assert not re.search(r"\bALTER\s+TABLE\b", nc), "ALTER TABLE 발견"
    assert not re.search(r"\bCREATE\s+TABLE\b", nc), "CREATE TABLE 발견"
    assert not re.search(r"\bDROP\s+TABLE\b", nc), "DROP TABLE 발견"


# ── SHA256 불변 앵커 ──────────────────────────────────────────────────────────

def _sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_sh_src_01_this_migration_sha256():
    """SH-SRC-01: 이 Migration SHA256 고정"""
    expected = "3739f850cfe839d11fcd07e3e2d1b6a7faf78405d6fe52a4dc617dc6f2f6b0ef"
    actual = _sha256(_MIGRATION_PATH)
    assert actual == expected, f"Migration SHA256 변경: {actual}"


def test_sh_src_02_sec02_ex001_sha256():
    """SH-SRC-02: SEC-02-EX-001 Migration SHA256 불변"""
    path = _MIGRATIONS_DIR / "20261022020000_sec02_ex001_inspection_work_schedules_lockdown.sql"
    expected = "2e5d41e51b54b98d8ac1a3bc2ed971dfc62f51b900a77bdac572965db7742f2f"
    actual = _sha256(path)
    assert actual == expected, f"SEC-02-EX-001 Migration 변경 감지: {actual}"


def test_sh_src_03_sec02_adj_p0_sha256():
    """SH-SRC-03: SEC-02-ADJ-P0 Migration SHA256 불변"""
    path = _MIGRATIONS_DIR / "20261022071824_sec02_adj_p0_work_assignments_generate_daily_lockdown.sql"
    expected = "417f9eb32612e041b3194583e64f4362234091164925bddedb6f0862d13e5714"
    actual = _sha256(path)
    assert actual == expected, f"SEC-02-ADJ-P0 Migration 변경 감지: {actual}"


def test_sh_src_04_sec04_remaining6_sha256():
    """SH-SRC-04: SEC-04 remaining6 Migration SHA256 불변"""
    path = _MIGRATIONS_DIR / "20261022000003_sec04_remaining6_privilege_function_revoke.sql"
    expected = "06d89b0a2168592ac05845ba9c847601aa1468ff708556921a1acf5e6335b24e"
    actual = _sha256(path)
    assert actual == expected, f"SEC-04 remaining6 Migration 변경 감지: {actual}"
