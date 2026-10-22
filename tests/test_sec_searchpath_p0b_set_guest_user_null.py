"""
WO-TAI-SEC-SEARCHPATH-P0B-IMPLEMENT-001 정적 계약 테스트
public.set_guest_user_null() search_path 고정 Migration 검증

대상 Migration:
  20261022131807_sec_searchpath_p0b_set_guest_user_null.sql

테스트 목록:
  SP2-SQL-01  Migration 파일 존재
  SP2-SQL-02  BEGIN/COMMIT 트랜잭션 구조
  SP2-SQL-03  ALTER FUNCTION 정확히 1건
  SP2-SQL-04  대상 서명 일치 (set_guest_user_null())
  SP2-SQL-05  목표 search_path 값 일치 (pg_catalog, public, pg_temp)
  SP2-SQL-06  pg_temp 마지막 위치
  SP2-SQL-07  CREATE OR REPLACE FUNCTION 없음 (함수 재작성 금지)
  SP2-SQL-08  DROP FUNCTION 없음
  SP2-SQL-09  트리거 DDL 없음 (CREATE/DROP/ALTER TRIGGER)
  SP2-SQL-10  payments 테이블 DDL 없음
  SP2-SQL-11  RLS 변경 없음 (CREATE/DROP/ALTER POLICY)
  SP2-SQL-12  GRANT 없음
  SP2-SQL-13  REVOKE 없음
  SP2-SQL-14  DML 없음 (INSERT/UPDATE/DELETE/TRUNCATE)
  SP2-SQL-15  PRE: 함수 서명 및 trigger 반환형 검증
  SP2-SQL-16  PRE: SECURITY DEFINER 검증 (prosecdef)
  SP2-SQL-17  PRE: 함수 정의 MD5 기준선 포함
  SP2-SQL-18  PRE: 함수 본문 MD5 기준선 포함
  SP2-SQL-19  PRE: proconfig NULL 검증 포함
  SP2-SQL-20  PRE: anon EXECUTE=FALSE 검증 포함
  SP2-SQL-21  PRE: authenticated EXECUTE=FALSE 검증 포함
  SP2-SQL-22  PRE: service_role EXECUTE=TRUE 검증 포함
  SP2-SQL-23  PRE: 트리거 1건 검증 포함 (pg_trigger)
  SP2-SQL-24  PRE: 트리거 MD5 기준선 포함
  SP2-SQL-25  PRE: payments RLS 검증 포함
  SP2-SQL-26  POST: search_path 설정 확인 포함
  SP2-SQL-27  POST: 함수 본문 MD5 불변 검증 포함
  SP2-SQL-28  POST: SECURITY DEFINER 불변 검증 포함
  SP2-SQL-29  POST: ACL 불변 검증 포함 (anon/auth/sr)
  SP2-SQL-30  POST: 트리거 MD5 불변 검증 포함
  SP2-SRC-01  이 Migration SHA256 고정
  SP2-SRC-02  P0A Migration SHA256 불변
  SP2-SRC-03  SEC-02-EX-001 Migration SHA256 불변
  SP2-SRC-04  HNU Migration SHA256 불변
"""

import hashlib
import pathlib
import re

import pytest

_MIGRATION_NAME = "20261022131807_sec_searchpath_p0b_set_guest_user_null.sql"
_MIGRATIONS_DIR = pathlib.Path(__file__).parent.parent / "supabase" / "migrations"
_MIGRATION_PATH = _MIGRATIONS_DIR / _MIGRATION_NAME


def _sql() -> str:
    return _MIGRATION_PATH.read_text(encoding="utf-8")


def _nc_upper() -> str:
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

def test_sp2_sql_01_migration_file_exists():
    """SP2-SQL-01: Migration 파일 존재"""
    assert _MIGRATION_PATH.exists(), f"{_MIGRATION_NAME} 파일 없음"


# ── 트랜잭션 구조 ──────────────────────────────────────────────────────────────

def test_sp2_sql_02_transaction_structure():
    """SP2-SQL-02: BEGIN/COMMIT 트랜잭션 구조"""
    nc = _nc_upper()
    assert re.search(r"^\s*BEGIN\s*;", nc, re.MULTILINE), "BEGIN; 없음"
    assert re.search(r"^\s*COMMIT\s*;", nc, re.MULTILINE), "COMMIT; 없음"


# ── ALTER FUNCTION 대상 ────────────────────────────────────────────────────────

def test_sp2_sql_03_alter_function_exactly_one():
    """SP2-SQL-03: ALTER FUNCTION 정확히 1건"""
    nc = _nc_upper()
    matches = re.findall(r"\bALTER\s+FUNCTION\b", nc)
    assert len(matches) == 1, f"ALTER FUNCTION 횟수={len(matches)}, 기대=1"


def test_sp2_sql_04_target_signature():
    """SP2-SQL-04: 대상 서명 set_guest_user_null() 일치"""
    nc = _nc_upper()
    assert re.search(
        r"\bALTER\s+FUNCTION\s+PUBLIC\.SET_GUEST_USER_NULL\s*\(\s*\)", nc
    ), "ALTER FUNCTION public.set_guest_user_null() 없음"


def test_sp2_sql_05_search_path_value():
    """SP2-SQL-05: 목표 search_path = pg_catalog, public, pg_temp"""
    sql = _sql()
    assert re.search(
        r"SET\s+search_path\s+TO\s+pg_catalog\s*,\s*public\s*,\s*pg_temp",
        sql, re.IGNORECASE
    ), "SET search_path TO pg_catalog, public, pg_temp 없음"


def test_sp2_sql_06_pg_temp_last():
    """SP2-SQL-06: pg_temp이 search_path 마지막"""
    sql = _sql()
    m = re.search(
        r"SET\s+search_path\s+TO\s+([\w\s,]+)", sql, re.IGNORECASE
    )
    assert m, "SET search_path TO ... 패턴 없음"
    parts = [p.strip().lower() for p in m.group(1).split(",")]
    assert parts[-1] == "pg_temp", f"pg_temp이 마지막이 아님: {parts}"


# ── 금지 DDL ──────────────────────────────────────────────────────────────────

def test_sp2_sql_07_no_create_or_replace_function():
    """SP2-SQL-07: CREATE OR REPLACE FUNCTION 없음"""
    nc = _nc_upper()
    assert not re.search(r"\bCREATE\s+(OR\s+REPLACE\s+)?FUNCTION\b", nc), \
        "CREATE FUNCTION 발견 — 본문 재작성 금지"


def test_sp2_sql_08_no_drop_function():
    """SP2-SQL-08: DROP FUNCTION 없음"""
    nc = _nc_upper()
    assert not re.search(r"\bDROP\s+FUNCTION\b", nc), "DROP FUNCTION 발견"


def test_sp2_sql_09_no_trigger_ddl():
    """SP2-SQL-09: 트리거 DDL 없음"""
    nc = _nc_upper()
    assert not re.search(r"\bCREATE\s+(OR\s+REPLACE\s+)?TRIGGER\b", nc), "CREATE TRIGGER 발견"
    assert not re.search(r"\bDROP\s+TRIGGER\b", nc), "DROP TRIGGER 발견"
    assert not re.search(r"\bALTER\s+TRIGGER\b", nc), "ALTER TRIGGER 발견"


def test_sp2_sql_10_no_payments_table_ddl():
    """SP2-SQL-10: payments 테이블 DDL 없음"""
    nc = _nc_upper()
    assert not re.search(r"\bALTER\s+TABLE\b", nc), "ALTER TABLE 발견"
    assert not re.search(r"\bCREATE\s+TABLE\b", nc), "CREATE TABLE 발견"
    assert not re.search(r"\bDROP\s+TABLE\b", nc), "DROP TABLE 발견"


def test_sp2_sql_11_no_rls_policy_change():
    """SP2-SQL-11: RLS/Policy 변경 없음"""
    nc = _nc_upper()
    assert not re.search(r"\bCREATE\s+POLICY\b", nc), "CREATE POLICY 발견"
    assert not re.search(r"\bDROP\s+POLICY\b", nc), "DROP POLICY 발견"
    assert not re.search(r"\bALTER\s+POLICY\b", nc), "ALTER POLICY 발견"


def test_sp2_sql_12_no_grant():
    """SP2-SQL-12: GRANT 없음"""
    nc = _nc_upper()
    assert not re.search(r"\bGRANT\b", nc), "GRANT 발견"


def test_sp2_sql_13_no_revoke():
    """SP2-SQL-13: REVOKE 없음"""
    nc = _nc_upper()
    assert not re.search(r"\bREVOKE\b", nc), "REVOKE 발견"


def test_sp2_sql_14_no_dml():
    """SP2-SQL-14: DML 없음"""
    nc = _nc_upper()
    assert not re.search(r"\bINSERT\s+INTO\b", nc), "INSERT INTO 발견"
    assert not re.search(r"\bDELETE\s+FROM\b", nc), "DELETE FROM 발견"
    assert not re.search(r"\bTRUNCATE\b", nc), "TRUNCATE 발견"
    assert not re.search(r"\bUPDATE\b\s+\w+\s+SET\b", nc), "UPDATE … SET 발견"


# ── PRE 조건 ──────────────────────────────────────────────────────────────────

def test_sp2_sql_15_pre_function_signature():
    """SP2-SQL-15: PRE — 함수 서명 및 trigger 반환형 검증"""
    nc = _nc_upper()
    assert re.search(r"\bSET_GUEST_USER_NULL\b", nc), "set_guest_user_null 참조 없음"
    assert re.search(r"PRORETTYPE|'TRIGGER'::REGTYPE", nc, re.IGNORECASE), \
        "trigger 반환형 검증 없음"


def test_sp2_sql_16_pre_security_definer():
    """SP2-SQL-16: PRE — SECURITY DEFINER 검증 (prosecdef)"""
    nc = _nc_upper()
    assert re.search(r"\bPROSECDEF\b", nc), "prosecdef 검증 없음"


def test_sp2_sql_17_pre_def_md5():
    """SP2-SQL-17: PRE — 함수 정의 MD5 기준선 포함"""
    sql = _sql()
    assert "ce566e4848a8ca47c794cbf3b48a826c" in sql, "def MD5 기준값 없음"
    assert re.search(r"PG_GET_FUNCTIONDEF", sql, re.IGNORECASE), "pg_get_functiondef 없음"


def test_sp2_sql_18_pre_body_md5():
    """SP2-SQL-18: PRE — 함수 본문 MD5 기준선 포함"""
    sql = _sql()
    assert "a879552fd1b918e717c633e7ace65a72" in sql, "body MD5 기준값 없음"
    assert re.search(r"\bPROSRC\b", sql, re.IGNORECASE), "prosrc 없음"


def test_sp2_sql_19_pre_proconfig_null():
    """SP2-SQL-19: PRE — proconfig NULL 검증 포함"""
    nc = _nc_upper()
    assert re.search(r"\bPROCONFIG\b", nc), "proconfig 검증 없음"
    assert re.search(r"PROCONFIG\s+IS\s+NOT\s+NULL|PROCONFIG\s+IS\s+NULL", nc, re.IGNORECASE), \
        "proconfig NULL 조건 검증 없음"


def test_sp2_sql_20_pre_anon_execute_false():
    """SP2-SQL-20: PRE — anon EXECUTE=FALSE 검증 포함"""
    nc = _nc_upper()
    assert re.search(r"HAS_FUNCTION_PRIVILEGE\s*\(\s*'ANON'", nc), "anon EXECUTE 검증 없음"


def test_sp2_sql_21_pre_authenticated_execute_false():
    """SP2-SQL-21: PRE — authenticated EXECUTE=FALSE 검증 포함"""
    nc = _nc_upper()
    assert re.search(r"HAS_FUNCTION_PRIVILEGE\s*\(\s*'AUTHENTICATED'", nc), \
        "authenticated EXECUTE 검증 없음"


def test_sp2_sql_22_pre_service_role_execute_true():
    """SP2-SQL-22: PRE — service_role EXECUTE=TRUE 검증 포함"""
    nc = _nc_upper()
    assert re.search(r"HAS_FUNCTION_PRIVILEGE\s*\(\s*'SERVICE_ROLE'", nc), \
        "service_role EXECUTE 검증 없음"


def test_sp2_sql_23_pre_trigger_count():
    """SP2-SQL-23: PRE — 트리거 1건 검증 포함"""
    nc = _nc_upper()
    assert re.search(r"\bPG_TRIGGER\b", nc), "pg_trigger 검증 없음"


def test_sp2_sql_24_pre_trigger_md5():
    """SP2-SQL-24: PRE — 트리거 MD5 기준선 포함"""
    sql = _sql()
    assert "5a22f8575250d9a458d39a93c90abbf2" in sql, "trigger MD5 기준값 없음"
    assert re.search(r"PG_GET_TRIGGERDEF", sql, re.IGNORECASE), "pg_get_triggerdef 없음"


def test_sp2_sql_25_pre_payments_rls():
    """SP2-SQL-25: PRE — payments RLS 검증 포함"""
    nc = _nc_upper()
    assert re.search(r"RELROWSECURITY", nc, re.IGNORECASE), "relrowsecurity 검증 없음"
    assert re.search(r"\bPAYMENTS\b", nc), "payments 참조 없음"


# ── POST 조건 ─────────────────────────────────────────────────────────────────

def test_sp2_sql_26_post_search_path_set():
    """SP2-SQL-26: POST — search_path 설정 확인 포함"""
    nc = _nc_upper()
    assert re.search(r"POST.*FAIL|PROCONFIG.*IS\s+NULL|SEARCH_PATH.*NOT\s+SET", nc, re.IGNORECASE), \
        "POST search_path 검증 없음"


def test_sp2_sql_27_post_body_md5_unchanged():
    """SP2-SQL-27: POST — 함수 본문 MD5 불변 검증 포함"""
    sql = _sql()
    # body MD5 a879552fd1b918e717c633e7ace65a72이 POST 블록에서도 참조되어야 함
    count = sql.count("a879552fd1b918e717c633e7ace65a72")
    assert count >= 2, f"body MD5 기준값이 PRE+POST에 각각 있어야 함: {count}건 발견"


def test_sp2_sql_28_post_security_definer_unchanged():
    """SP2-SQL-28: POST — SECURITY DEFINER 불변 검증 포함"""
    nc = _nc_upper()
    # prosecdef가 POST 블록에도 확인돼야 함 (PRE + POST 최소 2회)
    count = len(re.findall(r"\bPROSECDEF\b", nc))
    assert count >= 2, f"prosecdef 검증이 PRE·POST 양쪽에 있어야 함: {count}건"


def test_sp2_sql_29_post_acl_unchanged():
    """SP2-SQL-29: POST — ACL 불변 검증 포함 (anon/auth/sr)"""
    nc = _nc_upper()
    # has_function_privilege 가 anon, authenticated, service_role 각각 POST에도 포함
    assert len(re.findall(r"HAS_FUNCTION_PRIVILEGE", nc)) >= 6, \
        "has_function_privilege가 PRE+POST 양쪽 3役 각각 있어야 함"


def test_sp2_sql_30_post_trigger_md5_unchanged():
    """SP2-SQL-30: POST — 트리거 MD5 불변 검증 포함"""
    sql = _sql()
    count = sql.count("5a22f8575250d9a458d39a93c90abbf2")
    assert count >= 2, f"trigger MD5 기준값이 PRE+POST에 각각 있어야 함: {count}건 발견"


# ── SHA256 불변 앵커 ──────────────────────────────────────────────────────────

def _sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_sp2_src_01_this_migration_sha256():
    """SP2-SRC-01: 이 Migration SHA256 고정"""
    expected = "f201b27c88a3c8d2ee3ab408e0c65cc7ae64c7423eb92bacc80f5f6465f06f7c"
    actual = _sha256(_MIGRATION_PATH)
    assert actual == expected, f"Migration SHA256 변경: {actual}"


def test_sp2_src_02_p0a_sha256():
    """SP2-SRC-02: P0A Migration SHA256 불변"""
    path = _MIGRATIONS_DIR / "20261022100136_sec_searchpath_p0a_secdef_aggregate_functions.sql"
    expected = "b66a039b9df3ccbf089fecbf7c987347f1dc878fc9f1cfbb1624685b53c23412"
    actual = _sha256(path)
    assert actual == expected, f"P0A Migration 변경 감지: {actual}"


def test_sp2_src_03_sec02_ex001_sha256():
    """SP2-SRC-03: SEC-02-EX-001 Migration SHA256 불변"""
    path = _MIGRATIONS_DIR / "20261022020000_sec02_ex001_inspection_work_schedules_lockdown.sql"
    expected = "2e5d41e51b54b98d8ac1a3bc2ed971dfc62f51b900a77bdac572965db7742f2f"
    actual = _sha256(path)
    assert actual == expected, f"SEC-02-EX-001 Migration 변경 감지: {actual}"


def test_sp2_src_04_hnu_sha256():
    """SP2-SRC-04: HNU Migration SHA256 불변"""
    path = _MIGRATIONS_DIR / "20261022083010_sec_residual_hnu001_drop_handle_new_user.sql"
    expected = "3739f850cfe839d11fcd07e3e2d1b6a7faf78405d6fe52a4dc617dc6f2f6b0ef"
    actual = _sha256(path)
    assert actual == expected, f"HNU Migration 변경 감지: {actual}"
