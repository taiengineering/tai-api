"""
WO-TAI-SEC-SEARCHPATH-P0A-001 정적 계약 테스트
SECURITY DEFINER 집계 함수 2건 search_path 고정 Migration 검증

대상 Migration:
  20261022100136_sec_searchpath_p0a_secdef_aggregate_functions.sql

테스트 목록:
  SP-SQL-01  Migration 파일 존재
  SP-SQL-02  BEGIN/COMMIT 트랜잭션 구조
  SP-SQL-03  ALTER FUNCTION 정확히 2건
  SP-SQL-04  refresh_dashboard_stats() 서명 일치
  SP-SQL-05  refresh_engine_equipment_summary() 서명 일치
  SP-SQL-06  search_path 값 정확히 일치 (pg_catalog, public, pg_temp)
  SP-SQL-07  pg_temp가 search_path 마지막
  SP-SQL-08  CREATE OR REPLACE FUNCTION 없음
  SP-SQL-09  함수 본문 재생성 없음 (AS $$ 없음)
  SP-SQL-10  REVOKE 없음
  SP-SQL-11  GRANT 없음
  SP-SQL-12  DROP FUNCTION 없음
  SP-SQL-13  테이블·View DDL 없음
  SP-SQL-14  DML 없음
  SP-SQL-15  PRE: F1 서명 검증 포함
  SP-SQL-16  PRE: F2 서명 검증 포함
  SP-SQL-17  PRE: SECURITY DEFINER 검증 포함
  SP-SQL-18  PRE: F1 정의 MD5 기준선 포함
  SP-SQL-19  PRE: F2 정의 MD5 기준선 포함
  SP-SQL-20  PRE: F1 본문 MD5 기준선 포함
  SP-SQL-21  PRE: F2 본문 MD5 기준선 포함
  SP-SQL-22  PRE: proconfig = NULL 검증 포함
  SP-SQL-23  PRE: anon/authenticated EXECUTE = FALSE 검증 포함
  SP-SQL-24  PRE: MatView 2개 존재 검증 포함
  SP-SQL-25  POST: search_path 설정 검증 포함
  SP-SQL-26  POST: 본문 MD5 불변 검증 포함
  SP-SQL-27  POST: SECURITY DEFINER 불변 검증 포함
  SP-SQL-28  POST: ACL 불변 검증 포함
  SP-SRC-01  이 Migration SHA256 고정
  SP-SRC-02  SEC-02-EX-001 Migration SHA256 불변
  SP-SRC-03  SEC-02-ADJ-P0 Migration SHA256 불변
  SP-SRC-04  HNU Migration SHA256 불변
"""

import hashlib
import pathlib
import re

import pytest

_MIGRATION_NAME = "20261022100136_sec_searchpath_p0a_secdef_aggregate_functions.sql"
_MIGRATIONS_DIR = pathlib.Path(__file__).parent.parent / "supabase" / "migrations"
_MIGRATION_PATH = _MIGRATIONS_DIR / _MIGRATION_NAME
_TARGET_SEARCH_PATH = "pg_catalog, public, pg_temp"


def _sql() -> str:
    return _MIGRATION_PATH.read_text(encoding="utf-8")


def _nc_upper() -> str:
    return _non_comment_lines(_sql())


def _non_comment_lines(sql: str) -> str:
    lines = []
    for line in sql.splitlines():
        if line.strip().startswith("--"):
            continue
        lines.append(line)
    return "\n".join(lines).upper()


# ── 파일 존재 ──────────────────────────────────────────────────────────────────

def test_sp_sql_01_migration_file_exists():
    """SP-SQL-01: Migration 파일 존재"""
    assert _MIGRATION_PATH.exists(), f"{_MIGRATION_NAME} 파일 없음"


# ── 트랜잭션 구조 ──────────────────────────────────────────────────────────────

def test_sp_sql_02_transaction_structure():
    """SP-SQL-02: BEGIN/COMMIT 트랜잭션 구조"""
    nc = _nc_upper()
    assert re.search(r"^\s*BEGIN\s*;", nc, re.MULTILINE), "BEGIN; 없음"
    assert re.search(r"^\s*COMMIT\s*;", nc, re.MULTILINE), "COMMIT; 없음"


# ── ALTER FUNCTION 대상 ────────────────────────────────────────────────────────

def test_sp_sql_03_alter_function_exactly_two():
    """SP-SQL-03: ALTER FUNCTION 정확히 2건"""
    nc = _nc_upper()
    matches = re.findall(r"\bALTER\s+FUNCTION\b", nc)
    assert len(matches) == 2, f"ALTER FUNCTION 횟수={len(matches)}, 기대=2"


def test_sp_sql_04_f1_signature():
    """SP-SQL-04: refresh_dashboard_stats() 서명 일치"""
    nc = _nc_upper()
    assert re.search(
        r"\bALTER\s+FUNCTION\s+PUBLIC\.REFRESH_DASHBOARD_STATS\s*\(\s*\)", nc
    ), "ALTER FUNCTION public.refresh_dashboard_stats() 없음"


def test_sp_sql_05_f2_signature():
    """SP-SQL-05: refresh_engine_equipment_summary() 서명 일치"""
    nc = _nc_upper()
    assert re.search(
        r"\bALTER\s+FUNCTION\s+PUBLIC\.REFRESH_ENGINE_EQUIPMENT_SUMMARY\s*\(\s*\)", nc
    ), "ALTER FUNCTION public.refresh_engine_equipment_summary() 없음"


# ── search_path 값 검증 ────────────────────────────────────────────────────────

def test_sp_sql_06_search_path_value():
    """SP-SQL-06: search_path 값 = pg_catalog, public, pg_temp"""
    sql = _sql()
    expected = _TARGET_SEARCH_PATH
    assert expected in sql, f"search_path '{expected}' 없음"
    count = sql.count(expected)
    assert count >= 2, f"search_path 값 등장 횟수={count}, 최소 2건(F1·F2) 기대"


def test_sp_sql_07_pg_temp_last():
    """SP-SQL-07: pg_temp가 search_path 마지막"""
    sql = _sql()
    for match in re.finditer(r"SET\s+search_path\s+TO\s+([^\n;]+)", sql, re.IGNORECASE):
        path_val = match.group(1).strip().rstrip(";").strip()
        parts = [p.strip() for p in path_val.split(",")]
        assert parts[-1].lower() == "pg_temp", f"pg_temp이 마지막 아님: {path_val}"


# ── 금지 패턴 ─────────────────────────────────────────────────────────────────

def test_sp_sql_08_no_create_or_replace_function():
    """SP-SQL-08: CREATE OR REPLACE FUNCTION 없음"""
    nc = _nc_upper()
    assert not re.search(r"\bCREATE\s+(OR\s+REPLACE\s+)?FUNCTION\b", nc), \
        "CREATE [OR REPLACE] FUNCTION 발견"


def test_sp_sql_09_no_function_body_rewrite():
    """SP-SQL-09: 함수 본문 재생성 없음 (AS $$ 없음)"""
    sql = _sql()
    assert "AS $$" not in sql and "AS $function$" not in sql, \
        "함수 본문 재생성 구문 발견"


def test_sp_sql_10_no_revoke():
    """SP-SQL-10: REVOKE 없음"""
    nc = _nc_upper()
    assert not re.search(r"\bREVOKE\b", nc), "REVOKE 발견"


def test_sp_sql_11_no_grant():
    """SP-SQL-11: GRANT 없음"""
    nc = _nc_upper()
    assert not re.search(r"\bGRANT\b", nc), "GRANT 발견"


def test_sp_sql_12_no_drop_function():
    """SP-SQL-12: DROP FUNCTION 없음"""
    nc = _nc_upper()
    assert not re.search(r"\bDROP\s+FUNCTION\b", nc), "DROP FUNCTION 발견"


def test_sp_sql_13_no_table_view_ddl():
    """SP-SQL-13: 테이블·View DDL 없음"""
    nc = _nc_upper()
    assert not re.search(r"\bCREATE\s+TABLE\b", nc), "CREATE TABLE 발견"
    assert not re.search(r"\bDROP\s+TABLE\b", nc), "DROP TABLE 발견"
    assert not re.search(r"\bALTER\s+TABLE\b", nc), "ALTER TABLE 발견"
    assert not re.search(r"\bCREATE\s+(MATERIALIZED\s+)?VIEW\b", nc), "CREATE VIEW 발견"
    assert not re.search(r"\bDROP\s+(MATERIALIZED\s+)?VIEW\b", nc), "DROP VIEW 발견"
    assert not re.search(r"\bREFRESH\s+MATERIALIZED\s+VIEW\b", nc), "REFRESH MATERIALIZED VIEW 발견"


def test_sp_sql_14_no_dml():
    """SP-SQL-14: DML 없음"""
    nc = _nc_upper()
    assert not re.search(r"\bINSERT\s+INTO\b", nc), "INSERT INTO 발견"
    assert not re.search(r"\bDELETE\s+FROM\b", nc), "DELETE FROM 발견"
    assert not re.search(r"\bTRUNCATE\b", nc), "TRUNCATE 발견"
    assert not re.search(r"\bUPDATE\b\s+\w+\s+SET\b", nc), "UPDATE … SET 발견"


# ── PRE 조건 ──────────────────────────────────────────────────────────────────

def test_sp_sql_15_pre_f1_signature():
    """SP-SQL-15: PRE — F1 서명 검증 포함"""
    nc = _nc_upper()
    assert re.search(r"REFRESH_DASHBOARD_STATS", nc), "refresh_dashboard_stats PRE 검증 없음"
    assert re.search(r"PRONARGS\s*=\s*0", nc), "pronargs=0 검증 없음"


def test_sp_sql_16_pre_f2_signature():
    """SP-SQL-16: PRE — F2 서명 검증 포함"""
    nc = _nc_upper()
    assert re.search(r"REFRESH_ENGINE_EQUIPMENT_SUMMARY", nc), \
        "refresh_engine_equipment_summary PRE 검증 없음"


def test_sp_sql_17_pre_security_definer():
    """SP-SQL-17: PRE — SECURITY DEFINER 검증 포함 (prosecdef)"""
    nc = _nc_upper()
    assert re.search(r"\bPROSECDEF\b", nc), "prosecdef 검증 없음"


def test_sp_sql_18_pre_f1_def_md5():
    """SP-SQL-18: PRE — F1 정의 MD5 기준선 포함"""
    sql = _sql()
    assert "f51bb1e3a717d44e91b97a2c1bd1232f" in sql, "F1 definition MD5 기준값 없음"


def test_sp_sql_19_pre_f2_def_md5():
    """SP-SQL-19: PRE — F2 정의 MD5 기준선 포함"""
    sql = _sql()
    assert "0b38f2bc5ed06d1cbadd60617525a8f2" in sql, "F2 definition MD5 기준값 없음"


def test_sp_sql_20_pre_f1_body_md5():
    """SP-SQL-20: PRE — F1 본문 MD5 기준선 포함"""
    sql = _sql()
    assert "8f9e939d25ceb118ea44ae97aa16f9f1" in sql, "F1 body MD5 기준값 없음"


def test_sp_sql_21_pre_f2_body_md5():
    """SP-SQL-21: PRE — F2 본문 MD5 기준선 포함"""
    sql = _sql()
    assert "9035dcba996c27b14c53c5483ae78e61" in sql, "F2 body MD5 기준값 없음"


def test_sp_sql_22_pre_proconfig_null():
    """SP-SQL-22: PRE — proconfig = NULL 검증 포함"""
    nc = _nc_upper()
    assert re.search(r"\bPROCONFIG\b", nc), "proconfig 검증 없음"


def test_sp_sql_23_pre_anon_auth_execute_false():
    """SP-SQL-23: PRE — anon/authenticated EXECUTE = FALSE 검증 포함"""
    nc = _nc_upper()
    assert re.search(r"HAS_FUNCTION_PRIVILEGE\s*\(\s*'ANON'", nc), "anon EXECUTE 검증 없음"
    assert re.search(r"HAS_FUNCTION_PRIVILEGE\s*\(\s*'AUTHENTICATED'", nc), \
        "authenticated EXECUTE 검증 없음"


def test_sp_sql_24_pre_matview_existence():
    """SP-SQL-24: PRE — MatView 2개 존재 검증 포함"""
    nc = _nc_upper()
    assert re.search(r"PG_MATVIEWS", nc), "pg_matviews 검증 없음"
    assert re.search(r"DASHBOARD_STATS", nc), "dashboard_stats MatView 검증 없음"
    assert re.search(r"ENGINE_EQUIPMENT_SUMMARY", nc), "engine_equipment_summary MatView 검증 없음"


# ── POST 조건 ─────────────────────────────────────────────────────────────────

def test_sp_sql_25_post_search_path_set():
    """SP-SQL-25: POST — search_path 설정 검증 포함"""
    nc = _nc_upper()
    assert re.search(r"POST.*FAIL|PROCONFIG.*IS\s+NULL|SEARCH_PATH.*NOT\s+SET", nc, re.IGNORECASE) \
        or re.search(r"SEARCH_PATH=PG_CATALOG", nc), "POST search_path 검증 없음"


def test_sp_sql_26_post_body_md5_unchanged():
    """SP-SQL-26: POST — 본문 MD5 불변 검증 포함"""
    nc = _nc_upper()
    # POST 블록에서 body MD5 재검증
    assert nc.count("8F9E939D25CEB118EA44AE97AA16F9F1") >= 2, \
        "F1 body MD5 POST 재검증 없음 (최소 2회 = PRE+POST)"
    assert nc.count("9035DCBA996C27B14C53C5483AE78E61") >= 2, \
        "F2 body MD5 POST 재검증 없음 (최소 2회 = PRE+POST)"


def test_sp_sql_27_post_security_definer_unchanged():
    """SP-SQL-27: POST — SECURITY DEFINER 불변 검증 포함"""
    nc = _nc_upper()
    assert nc.count("PROSECDEF") >= 2, "prosecdef POST 재검증 없음 (최소 2회 = PRE+POST)"


def test_sp_sql_28_post_acl_unchanged():
    """SP-SQL-28: POST — ACL 불변 검증 포함 (service_role EXECUTE 유지)"""
    nc = _nc_upper()
    assert re.search(r"HAS_FUNCTION_PRIVILEGE\s*\(\s*'SERVICE_ROLE'", nc), \
        "service_role EXECUTE POST 검증 없음"


# ── SHA256 불변 앵커 ──────────────────────────────────────────────────────────

def _sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_sp_src_01_this_migration_sha256():
    """SP-SRC-01: 이 Migration SHA256 고정"""
    expected = "b66a039b9df3ccbf089fecbf7c987347f1dc878fc9f1cfbb1624685b53c23412"
    actual = _sha256(_MIGRATION_PATH)
    assert actual == expected, f"Migration SHA256 변경: {actual}"


def test_sp_src_02_sec02_ex001_sha256():
    """SP-SRC-02: SEC-02-EX-001 Migration SHA256 불변"""
    path = _MIGRATIONS_DIR / "20261022020000_sec02_ex001_inspection_work_schedules_lockdown.sql"
    expected = "2e5d41e51b54b98d8ac1a3bc2ed971dfc62f51b900a77bdac572965db7742f2f"
    assert _sha256(path) == expected, "SEC-02-EX-001 Migration 변경 감지"


def test_sp_src_03_sec02_adj_p0_sha256():
    """SP-SRC-03: SEC-02-ADJ-P0 Migration SHA256 불변"""
    path = _MIGRATIONS_DIR / "20261022071824_sec02_adj_p0_work_assignments_generate_daily_lockdown.sql"
    expected = "417f9eb32612e041b3194583e64f4362234091164925bddedb6f0862d13e5714"
    assert _sha256(path) == expected, "SEC-02-ADJ-P0 Migration 변경 감지"


def test_sp_src_04_hnu_sha256():
    """SP-SRC-04: HNU Migration SHA256 불변"""
    path = _MIGRATIONS_DIR / "20261022083010_sec_residual_hnu001_drop_handle_new_user.sql"
    expected = "3739f850cfe839d11fcd07e3e2d1b6a7faf78405d6fe52a4dc617dc6f2f6b0ef"
    assert _sha256(path) == expected, "HNU Migration 변경 감지"
