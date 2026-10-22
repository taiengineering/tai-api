"""
WO-TAI-SEC-SEARCHPATH-P0C-IMPLEMENT-001 정적 계약 테스트
DDL 헬퍼 함수 4개 search_path 고정 Migration 검증
R1: ACL PRE/POST · Owner POST · 정확한 서명 · 트리거 10건 · proconfig 동일성

대상 Migration:
  20261022152140_sec_searchpath_p0c_ddl_helper_functions.sql

테스트 목록:
  SP3-SQL-01  Migration 파일 존재
  SP3-SQL-02  BEGIN/COMMIT 트랜잭션 구조
  SP3-SQL-03  ALTER FUNCTION 정확히 4건
  SP3-SQL-04  F1 서명 일치 (tai_add_audit_columns(text))
  SP3-SQL-05  F2 서명 일치 (tai_comment_column(text,text,text))
  SP3-SQL-06  F3 서명 일치 (tai_comment_table(text,text))
  SP3-SQL-07  F4 서명 일치 (tai_create_update_trigger(text))
  SP3-SQL-08  search_path 값 정확히 일치 (pg_catalog, public, pg_temp)
  SP3-SQL-09  pg_temp이 search_path 마지막
  SP3-SQL-10  CREATE OR REPLACE FUNCTION 없음
  SP3-SQL-11  DROP FUNCTION 없음
  SP3-SQL-12  트리거 DDL 없음
  SP3-SQL-13  테이블 DDL 없음
  SP3-SQL-14  RLS/Policy 변경 없음
  SP3-SQL-15  GRANT 없음
  SP3-SQL-16  REVOKE 없음
  SP3-SQL-17  DML 없음
  SP3-SQL-18  PRE — SECURITY INVOKER 검증 (prosecdef=false)
  SP3-SQL-19  PRE — F1 본문 MD5 기준선 포함
  SP3-SQL-20  PRE — F2 본문 MD5 기준선 포함
  SP3-SQL-21  PRE — F3 본문 MD5 기준선 포함
  SP3-SQL-22  PRE — F4 본문 MD5 기준선 포함
  SP3-SQL-23  PRE — proconfig = NULL 검증 포함
  SP3-SQL-24  PRE — anon EXECUTE 검증 포함 (4개 함수)
  SP3-SQL-25  PRE — authenticated EXECUTE 검증 포함 (4개 함수)
  SP3-SQL-26  PRE — tai_set_updated_at 의존 함수 존재 검증 포함
  SP3-SQL-27  POST — proconfig array_length 동일성 검증 (R1)
  SP3-SQL-28  POST — 본문 MD5 불변 검증 포함 (PRE+POST 각 2회)
  SP3-SQL-29  POST — SECURITY INVOKER 불변 검증 포함 (PRE+POST 각 2회)
  SP3-SQL-30  PRE — 스키마 CREATE 권한 부재 검증 포함
  SP3-SQL-31  R1 — pg_get_function_identity_arguments 정확한 서명 검증 (≥16회)
  SP3-SQL-32  R1 — PRE ACL 기준선 상수 선언 및 4개 함수 PRE 불일치 검증
  SP3-SQL-33  R1 — POST ACL 불변 검증 (4개 함수 POST)
  SP3-SQL-34  R1 — Owner POST 불변 검증 (pg_get_userbyid PRE+POST 각 4회)
  SP3-SQL-35  R1 — 트리거 정확히 10건 PRE+POST (v_trig_count != 10 × 2)
  SP3-SRC-01  이 Migration SHA256 고정
  SP3-SRC-02  P0B Migration SHA256 불변
  SP3-SRC-03  P0A Migration SHA256 불변
  SP3-SRC-04  HNU Migration SHA256 불변
"""

import hashlib
import pathlib
import re

import pytest

_MIGRATION_NAME = "20261022152140_sec_searchpath_p0c_ddl_helper_functions.sql"
_MIGRATIONS_DIR = pathlib.Path(__file__).parent.parent / "supabase" / "migrations"
_MIGRATION_PATH = _MIGRATIONS_DIR / _MIGRATION_NAME
_TARGET_SEARCH_PATH = "pg_catalog, public, pg_temp"

_BODY_MD5_F1 = "363bbf0a50ac376c841225d564ad7809"  # tai_add_audit_columns(text)
_BODY_MD5_F2 = "418c8af3362682dff269df17872e4aa9"  # tai_comment_column(text,text,text)
_BODY_MD5_F3 = "7da885c26c03a436a209b7eb12070feb"  # tai_comment_table(text,text)
_BODY_MD5_F4 = "df68333c1155353f9c0395a59ad7bdf2"  # tai_create_update_trigger(text)


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

def test_sp3_sql_01_migration_file_exists():
    """SP3-SQL-01: Migration 파일 존재"""
    assert _MIGRATION_PATH.exists(), f"{_MIGRATION_NAME} 파일 없음"


# ── 트랜잭션 구조 ──────────────────────────────────────────────────────────────

def test_sp3_sql_02_transaction_structure():
    """SP3-SQL-02: BEGIN/COMMIT 트랜잭션 구조"""
    nc = _nc_upper()
    assert re.search(r"^\s*BEGIN\s*;", nc, re.MULTILINE), "BEGIN; 없음"
    assert re.search(r"^\s*COMMIT\s*;", nc, re.MULTILINE), "COMMIT; 없음"


# ── ALTER FUNCTION 대상 ────────────────────────────────────────────────────────

def test_sp3_sql_03_alter_function_exactly_four():
    """SP3-SQL-03: ALTER FUNCTION 정확히 4건"""
    nc = _nc_upper()
    matches = re.findall(r"\bALTER\s+FUNCTION\b", nc)
    assert len(matches) == 4, f"ALTER FUNCTION 횟수={len(matches)}, 기대=4"


def test_sp3_sql_04_f1_signature():
    """SP3-SQL-04: F1 서명 — tai_add_audit_columns(text)"""
    nc = _nc_upper()
    assert re.search(
        r"\bALTER\s+FUNCTION\s+PUBLIC\.TAI_ADD_AUDIT_COLUMNS\s*\(\s*TEXT\s*\)", nc
    ), "ALTER FUNCTION public.tai_add_audit_columns(text) 없음"


def test_sp3_sql_05_f2_signature():
    """SP3-SQL-05: F2 서명 — tai_comment_column(text,text,text)"""
    nc = _nc_upper()
    assert re.search(
        r"\bALTER\s+FUNCTION\s+PUBLIC\.TAI_COMMENT_COLUMN\s*\(\s*TEXT\s*,\s*TEXT\s*,\s*TEXT\s*\)", nc
    ), "ALTER FUNCTION public.tai_comment_column(text, text, text) 없음"


def test_sp3_sql_06_f3_signature():
    """SP3-SQL-06: F3 서명 — tai_comment_table(text,text)"""
    nc = _nc_upper()
    assert re.search(
        r"\bALTER\s+FUNCTION\s+PUBLIC\.TAI_COMMENT_TABLE\s*\(\s*TEXT\s*,\s*TEXT\s*\)", nc
    ), "ALTER FUNCTION public.tai_comment_table(text, text) 없음"


def test_sp3_sql_07_f4_signature():
    """SP3-SQL-07: F4 서명 — tai_create_update_trigger(text)"""
    nc = _nc_upper()
    assert re.search(
        r"\bALTER\s+FUNCTION\s+PUBLIC\.TAI_CREATE_UPDATE_TRIGGER\s*\(\s*TEXT\s*\)", nc
    ), "ALTER FUNCTION public.tai_create_update_trigger(text) 없음"


# ── search_path 값 검증 ────────────────────────────────────────────────────────

def test_sp3_sql_08_search_path_value():
    """SP3-SQL-08: search_path 값 = pg_catalog, public, pg_temp"""
    sql = _sql()
    assert _TARGET_SEARCH_PATH in sql, f"search_path '{_TARGET_SEARCH_PATH}' 없음"
    count = sql.count(_TARGET_SEARCH_PATH)
    assert count >= 4, f"search_path 등장 횟수={count}, 최소 4건(F1~F4) 기대"


def test_sp3_sql_09_pg_temp_last():
    """SP3-SQL-09: pg_temp이 search_path 마지막"""
    nc = _non_comment_lines(_sql())
    for match in re.finditer(r"SET\s+search_path\s+TO\s+([^\n;]+)", nc, re.IGNORECASE):
        path_val = match.group(1).strip().rstrip(";").strip()
        parts = [p.strip() for p in path_val.split(",")]
        assert parts[-1].lower() == "pg_temp", f"pg_temp이 마지막 아님: {path_val}"


# ── 금지 패턴 ─────────────────────────────────────────────────────────────────

def test_sp3_sql_10_no_create_or_replace_function():
    """SP3-SQL-10: CREATE OR REPLACE FUNCTION 없음"""
    nc = _nc_upper()
    assert not re.search(r"\bCREATE\s+(OR\s+REPLACE\s+)?FUNCTION\b", nc), \
        "CREATE [OR REPLACE] FUNCTION 발견 — 본문 재작성 금지"


def test_sp3_sql_11_no_drop_function():
    """SP3-SQL-11: DROP FUNCTION 없음"""
    nc = _nc_upper()
    assert not re.search(r"\bDROP\s+FUNCTION\b", nc), "DROP FUNCTION 발견"


def test_sp3_sql_12_no_trigger_ddl():
    """SP3-SQL-12: 트리거 DDL 없음"""
    nc = _nc_upper()
    assert not re.search(r"\bCREATE\s+(OR\s+REPLACE\s+)?TRIGGER\b", nc), "CREATE TRIGGER 발견"
    assert not re.search(r"\bDROP\s+TRIGGER\b", nc), "DROP TRIGGER 발견"
    assert not re.search(r"\bALTER\s+TRIGGER\b", nc), "ALTER TRIGGER 발견"


def test_sp3_sql_13_no_table_ddl():
    """SP3-SQL-13: 테이블 DDL 없음"""
    nc = _nc_upper()
    assert not re.search(r"\bALTER\s+TABLE\b", nc), "ALTER TABLE 발견"
    assert not re.search(r"\bCREATE\s+TABLE\b", nc), "CREATE TABLE 발견"
    assert not re.search(r"\bDROP\s+TABLE\b", nc), "DROP TABLE 발견"


def test_sp3_sql_14_no_rls_policy_change():
    """SP3-SQL-14: RLS/Policy 변경 없음"""
    nc = _nc_upper()
    assert not re.search(r"\bCREATE\s+POLICY\b", nc), "CREATE POLICY 발견"
    assert not re.search(r"\bDROP\s+POLICY\b", nc), "DROP POLICY 발견"
    assert not re.search(r"\bALTER\s+POLICY\b", nc), "ALTER POLICY 발견"


def test_sp3_sql_15_no_grant():
    """SP3-SQL-15: GRANT 없음"""
    nc = _nc_upper()
    assert not re.search(r"\bGRANT\b", nc), "GRANT 발견"


def test_sp3_sql_16_no_revoke():
    """SP3-SQL-16: REVOKE 없음"""
    nc = _nc_upper()
    assert not re.search(r"\bREVOKE\b", nc), "REVOKE 발견"


def test_sp3_sql_17_no_dml():
    """SP3-SQL-17: DML 없음"""
    nc = _nc_upper()
    assert not re.search(r"\bINSERT\s+INTO\b", nc), "INSERT INTO 발견"
    assert not re.search(r"\bDELETE\s+FROM\b", nc), "DELETE FROM 발견"
    assert not re.search(r"\bTRUNCATE\b", nc), "TRUNCATE 발견"
    assert not re.search(r"\bUPDATE\b\s+\w+\s+SET\b", nc), "UPDATE … SET 발견"


# ── PRE 조건 ──────────────────────────────────────────────────────────────────

def test_sp3_sql_18_pre_security_invoker():
    """SP3-SQL-18: PRE — SECURITY INVOKER 검증 (prosecdef=false)"""
    nc = _nc_upper()
    assert re.search(r"\bPROSECDEF\b", nc), "prosecdef 검증 없음"
    assert re.search(r"PROSECDEF\s*!=\s*FALSE|V_SECDEF\s*!=\s*FALSE", nc, re.IGNORECASE), \
        "prosecdef != false 검증 없음"


def test_sp3_sql_19_pre_f1_body_md5():
    """SP3-SQL-19: PRE — F1 본문 MD5 기준선 포함"""
    sql = _sql()
    assert _BODY_MD5_F1 in sql, f"tai_add_audit_columns body MD5 기준값 없음: {_BODY_MD5_F1}"
    assert re.search(r"\bPROSRC\b", sql, re.IGNORECASE), "prosrc 참조 없음"


def test_sp3_sql_20_pre_f2_body_md5():
    """SP3-SQL-20: PRE — F2 본문 MD5 기준선 포함"""
    sql = _sql()
    assert _BODY_MD5_F2 in sql, f"tai_comment_column body MD5 기준값 없음: {_BODY_MD5_F2}"


def test_sp3_sql_21_pre_f3_body_md5():
    """SP3-SQL-21: PRE — F3 본문 MD5 기준선 포함"""
    sql = _sql()
    assert _BODY_MD5_F3 in sql, f"tai_comment_table body MD5 기준값 없음: {_BODY_MD5_F3}"


def test_sp3_sql_22_pre_f4_body_md5():
    """SP3-SQL-22: PRE — F4 본문 MD5 기준선 포함"""
    sql = _sql()
    assert _BODY_MD5_F4 in sql, f"tai_create_update_trigger body MD5 기준값 없음: {_BODY_MD5_F4}"


def test_sp3_sql_23_pre_proconfig_null():
    """SP3-SQL-23: PRE — proconfig = NULL 검증 포함"""
    nc = _nc_upper()
    assert re.search(r"\bPROCONFIG\b", nc), "proconfig 검증 없음"
    assert re.search(r"PROCONFIG\s+IS\s+NOT\s+NULL|PROCONFIG\s+IS\s+NULL", nc, re.IGNORECASE), \
        "proconfig NULL 조건 검증 없음"


def test_sp3_sql_24_pre_anon_execute():
    """SP3-SQL-24: PRE — anon EXECUTE 검증 포함 (4개 함수)"""
    nc = _nc_upper()
    anon_matches = re.findall(r"HAS_FUNCTION_PRIVILEGE\s*\(\s*'ANON'", nc)
    assert len(anon_matches) >= 4, f"anon EXECUTE 검증이 4건 이상 있어야 함: {len(anon_matches)}건"


def test_sp3_sql_25_pre_authenticated_execute():
    """SP3-SQL-25: PRE — authenticated EXECUTE 검증 포함 (4개 함수)"""
    nc = _nc_upper()
    auth_matches = re.findall(r"HAS_FUNCTION_PRIVILEGE\s*\(\s*'AUTHENTICATED'", nc)
    assert len(auth_matches) >= 4, \
        f"authenticated EXECUTE 검증이 4건 이상 있어야 함: {len(auth_matches)}건"


def test_sp3_sql_26_pre_tai_set_updated_at():
    """SP3-SQL-26: PRE — tai_set_updated_at 의존 함수 존재 검증 포함"""
    nc = _nc_upper()
    assert re.search(r"\bTAI_SET_UPDATED_AT\b", nc), "tai_set_updated_at 검증 없음"


# ── POST 조건 ─────────────────────────────────────────────────────────────────

def test_sp3_sql_27_post_proconfig_set():
    """SP3-SQL-27: POST — proconfig array_length 동일성 검증 (R1)"""
    nc = _nc_upper()
    assert re.search(r"POST.*FAIL|PROCONFIG.*IS\s+NULL|SEARCH_PATH.*NOT\s+SET", nc, re.IGNORECASE), \
        "POST proconfig 검증 없음"
    # R1: array_length 동일성 검사 (ARRAY_LENGTH(V_PROCONFIG, 1) != 1)
    assert re.search(r"ARRAY_LENGTH\s*\(\s*V_PROCONFIG", nc, re.IGNORECASE), \
        "POST proconfig array_length 동일성 검사 없음"


def test_sp3_sql_28_post_body_md5_unchanged():
    """SP3-SQL-28: POST — 본문 MD5 불변 검증 포함 (PRE+POST 각 2회 이상)"""
    sql = _sql()
    for md5_val, name in [
        (_BODY_MD5_F1, "tai_add_audit_columns"),
        (_BODY_MD5_F2, "tai_comment_column"),
        (_BODY_MD5_F3, "tai_comment_table"),
        (_BODY_MD5_F4, "tai_create_update_trigger"),
    ]:
        count = sql.count(md5_val)
        assert count >= 2, \
            f"{name} body MD5 {md5_val}가 PRE+POST 양쪽에 있어야 함: {count}건 발견"


def test_sp3_sql_29_post_security_invoker_unchanged():
    """SP3-SQL-29: POST — SECURITY INVOKER 불변 검증 포함 (prosecdef PRE+POST)"""
    nc = _nc_upper()
    count = len(re.findall(r"\bPROSECDEF\b", nc))
    assert count >= 8, \
        f"prosecdef 검증이 PRE·POST 양쪽 4개 함수 각각 있어야 함(최소 8): {count}건"


def test_sp3_sql_30_pre_schema_create_privilege():
    """SP3-SQL-30: PRE — anon/authenticated 스키마 CREATE 권한 부재 검증 포함"""
    nc = _nc_upper()
    assert re.search(r"HAS_SCHEMA_PRIVILEGE\s*\(\s*'ANON'", nc), \
        "anon schema CREATE 검증 없음"
    assert re.search(r"HAS_SCHEMA_PRIVILEGE\s*\(\s*'AUTHENTICATED'", nc), \
        "authenticated schema CREATE 검증 없음"


# ── R1 강화 검증 ──────────────────────────────────────────────────────────────

def test_sp3_sql_31_r1_exact_signature_identity_args():
    """SP3-SQL-31: R1 — pg_get_function_identity_arguments 정확한 서명 검증 (≥16회)"""
    nc = _nc_upper()
    matches = re.findall(r"PG_GET_FUNCTION_IDENTITY_ARGUMENTS\s*\(", nc)
    assert len(matches) >= 16, \
        f"pg_get_function_identity_arguments 사용이 16건 이상이어야 함 (PRE×4×함수4): {len(matches)}건"


def test_sp3_sql_32_r1_acl_baseline_pre():
    """SP3-SQL-32: R1 — PRE ACL 기준선 상수 선언 및 4개 함수 PRE 불일치 검증"""
    sql = _sql()
    assert re.search(r"c_acl_baseline\s+CONSTANT\s+text", sql, re.IGNORECASE), \
        "c_acl_baseline CONSTANT text 선언 없음"
    nc = _nc_upper()
    pre_acl_matches = re.findall(r"PRE FAILED.*ACL|V_PROACL\s*!=\s*C_ACL_BASELINE", nc, re.IGNORECASE)
    assert len(pre_acl_matches) >= 4, \
        f"PRE ACL 불일치 검증이 4건 이상이어야 함: {len(pre_acl_matches)}건"


def test_sp3_sql_33_r1_acl_post_unchanged():
    """SP3-SQL-33: R1 — POST ACL 불변 검증 (4개 함수 POST)"""
    nc = _nc_upper()
    post_acl_matches = re.findall(r"POST FAILED.*ACL", nc, re.IGNORECASE)
    assert len(post_acl_matches) >= 4, \
        f"POST ACL 불변 검증이 4건 이상이어야 함: {len(post_acl_matches)}건"


def test_sp3_sql_34_r1_owner_post_unchanged():
    """SP3-SQL-34: R1 — Owner POST 불변 검증 (pg_get_userbyid PRE+POST 각 4회, 합계 ≥8)"""
    nc = _nc_upper()
    owner_matches = re.findall(r"PG_GET_USERBYID\s*\(", nc)
    assert len(owner_matches) >= 8, \
        f"pg_get_userbyid 사용이 PRE×4+POST×4=8건 이상이어야 함: {len(owner_matches)}건"
    post_owner_matches = re.findall(r"POST FAILED.*OWNER\s+CHANGED", nc, re.IGNORECASE)
    assert len(post_owner_matches) >= 4, \
        f"POST owner 불변 검증 RAISE가 4건 이상이어야 함: {len(post_owner_matches)}건"


def test_sp3_sql_35_r1_trigger_count_10_pre_post():
    """SP3-SQL-35: R1 — 트리거 정확히 10건 PRE+POST (v_trig_count != 10 × 2)"""
    nc = _nc_upper()
    trig_count_checks = re.findall(r"V_TRIG_COUNT\s*!=\s*10", nc)
    assert len(trig_count_checks) >= 2, \
        f"v_trig_count != 10 검증이 PRE+POST 각 1회=2건 이상이어야 함: {len(trig_count_checks)}건"


# ── SHA256 불변 앵커 ──────────────────────────────────────────────────────────

def _sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_sp3_src_01_this_migration_sha256():
    """SP3-SRC-01: 이 Migration SHA256 고정 (R1)"""
    expected = "e38dcd892da517c0f317bb9a2b23ab94bd844bb0a50aa091d5b1f025aa141571"
    actual = _sha256(_MIGRATION_PATH)
    assert actual == expected, f"Migration SHA256 변경: {actual}"


def test_sp3_src_02_p0b_sha256():
    """SP3-SRC-02: P0B Migration SHA256 불변"""
    path = _MIGRATIONS_DIR / "20261022131807_sec_searchpath_p0b_set_guest_user_null.sql"
    expected = "f201b27c88a3c8d2ee3ab408e0c65cc7ae64c7423eb92bacc80f5f6465f06f7c"
    actual = _sha256(path)
    assert actual == expected, f"P0B Migration 변경 감지: {actual}"


def test_sp3_src_03_p0a_sha256():
    """SP3-SRC-03: P0A Migration SHA256 불변"""
    path = _MIGRATIONS_DIR / "20261022100136_sec_searchpath_p0a_secdef_aggregate_functions.sql"
    expected = "b66a039b9df3ccbf089fecbf7c987347f1dc878fc9f1cfbb1624685b53c23412"
    actual = _sha256(path)
    assert actual == expected, f"P0A Migration 변경 감지: {actual}"


def test_sp3_src_04_hnu_sha256():
    """SP3-SRC-04: HNU Migration SHA256 불변"""
    path = _MIGRATIONS_DIR / "20261022083010_sec_residual_hnu001_drop_handle_new_user.sql"
    expected = "3739f850cfe839d11fcd07e3e2d1b6a7faf78405d6fe52a4dc617dc6f2f6b0ef"
    actual = _sha256(path)
    assert actual == expected, f"HNU Migration 변경 감지: {actual}"
