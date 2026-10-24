"""
WO-TAI-SEC-SEARCHPATH-REM97-C3-W3-SOURCE-001 정적 계약 테스트
도움말 순환 방지 트리거 함수 2개 search_path 고정 Migration 검증

대상 Migration:
  20261023124050_sec_searchpath_rem97_w3_cycle_guard_functions.sql

테스트 목록:
  W3-SQL-01  Migration 파일 존재
  W3-SQL-02  BEGIN/COMMIT 트랜잭션 구조
  W3-SQL-03  ALTER FUNCTION 정확히 2건
  W3-SQL-04  help_doc_no_include_cycle() 서명 포함
  W3-SQL-05  help_node_no_cycle() 서명 포함
  W3-SQL-06  search_path 값 = pg_catalog, public, pg_temp (≥2건)
  W3-SQL-07  pg_temp이 search_path 마지막
  W3-SQL-08  CREATE [OR REPLACE] FUNCTION 없음
  W3-SQL-09  DROP FUNCTION 없음
  W3-SQL-10  트리거 DDL 없음 (CREATE/DROP TRIGGER)
  W3-SQL-11  테이블 DDL 없음 (CREATE/ALTER/DROP TABLE)
  W3-SQL-12  RLS/Policy 변경 없음
  W3-SQL-13  GRANT 없음
  W3-SQL-14  REVOKE 없음
  W3-SQL-15  DML 없음 (INSERT/UPDATE/DELETE/TRUNCATE)
  W3-SQL-16  PRE — SECURITY INVOKER 검증 포함
  W3-SQL-17  PRE — 2개 함수 본문 MD5 기준선 포함
  W3-SQL-18  PRE — proconfig IS NULL 검증 포함
  W3-SQL-19  PRE — anon EXECUTE 검증 포함
  W3-SQL-20  PRE — authenticated EXECUTE 검증 포함
  W3-SQL-21  PRE — ACL 기준선 상수 선언 및 검증 포함
  W3-SQL-22  PRE — Volatility 기준선 검증 포함 (v = VOLATILE)
  W3-SQL-23  PRE — Parallel 기준선 검증 포함 (u = UNSAFE)
  W3-SQL-24  PRE — 트리거 2개 기준선 검증 포함
  W3-SQL-25  PRE — W2 의존 함수 설정 유지 확인 포함
  W3-SQL-26  POST — proconfig 설정 검증 포함 (IS DISTINCT FROM)
  W3-SQL-27  POST — 본문 MD5 불변 검증 포함
  W3-SQL-28  POST — SECURITY INVOKER 불변 검증 포함
  W3-SQL-29  POST — ACL 불변 검증 포함
  W3-SQL-30  POST — Volatility 불변 검증 포함
  W3-SQL-31  POST — Parallel 불변 검증 포함
  W3-SQL-32  POST — 트리거 불변 검증 포함
  W3-SQL-33  to_regprocedure() OID 기반 식별 (≥3회)
  W3-SQL-34  IS DISTINCT FROM null-safe 비교 사용 (≥5회)
  W3-SQL-35  W1·W2·W4 범위 외 함수 미포함
  W3-SQL-36  OID 배열에 2개 OID 포함 (246456/246423)
  W3-SQL-37  Volatility는 모두 'v' (VOLATILE) 고정
  W3-SRC-01  이 Migration SHA256 고정
  W3-SRC-02  W2 Migration SHA256 불변
"""

import hashlib
import pathlib
import re

import pytest

_MIGRATION_NAME = "20261023124050_sec_searchpath_rem97_w3_cycle_guard_functions.sql"
_W2_MIGRATION_NAME = "20261023082048_sec_searchpath_rem97_w2_utility_functions.sql"
_MIGRATIONS_DIR = pathlib.Path(__file__).parent.parent / "supabase" / "migrations"
_MIGRATION_PATH = _MIGRATIONS_DIR / _MIGRATION_NAME
_W2_MIGRATION_PATH = _MIGRATIONS_DIR / _W2_MIGRATION_NAME
_TARGET_SEARCH_PATH = "pg_catalog, public, pg_temp"

# 운영 DB에서 확인된 함수 본문 MD5 기준선
_PROSRC_MD5 = {
    "help_doc_no_include_cycle": "e4707fa3c5fcd447c9b900e29a9b55e3",
    "help_node_no_cycle":        "9f0f34ca03105dd05ace9815bbbafc8b",
}

# 운영 DB에서 확인된 OID
_OIDS = {
    "help_doc_no_include_cycle": 246456,
    "help_node_no_cycle":        246423,
}

# 트리거 기준선
_TRIGGER_MD5 = {
    "help_doc_no_include_cycle_trg": "5dfd34dce1196d9dc124d2e60eeb7afc",
    "help_node_no_cycle_trg":        "78df84a85f863bdd1e44a7bef2e98c8a",
}


def _sql() -> str:
    return _MIGRATION_PATH.read_text(encoding="utf-8")


def _nc(sql: str | None = None) -> str:
    """비-주석 라인만 추출 후 대문자 반환."""
    src = sql if sql is not None else _sql()
    lines = [ln for ln in src.splitlines() if not ln.strip().startswith("--")]
    return "\n".join(lines).upper()


def _sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ── 파일 존재 ──────────────────────────────────────────────────────────────────

def test_w3_sql_01_migration_file_exists():
    """W3-SQL-01: Migration 파일 존재"""
    assert _MIGRATION_PATH.exists(), f"{_MIGRATION_NAME} 파일 없음"


# ── 트랜잭션 구조 ──────────────────────────────────────────────────────────────

def test_w3_sql_02_transaction_structure():
    """W3-SQL-02: BEGIN/COMMIT 트랜잭션 구조"""
    nc = _nc()
    assert re.search(r"^\s*BEGIN\s*;", nc, re.MULTILINE), "BEGIN; 없음"
    assert re.search(r"^\s*COMMIT\s*;", nc, re.MULTILINE), "COMMIT; 없음"


# ── ALTER FUNCTION 대상 ────────────────────────────────────────────────────────

def test_w3_sql_03_alter_function_exactly_two():
    """W3-SQL-03: ALTER FUNCTION 정확히 2건"""
    nc = _nc()
    matches = re.findall(r"\bALTER\s+FUNCTION\b", nc)
    assert len(matches) == 2, f"ALTER FUNCTION 횟수={len(matches)}, 기대=2"


def test_w3_sql_04_help_doc_no_include_cycle():
    """W3-SQL-04: help_doc_no_include_cycle() 서명 포함"""
    nc = _nc()
    assert re.search(
        r"\bALTER\s+FUNCTION\s+PUBLIC\.HELP_DOC_NO_INCLUDE_CYCLE\s*\(\s*\)", nc
    ), "ALTER FUNCTION public.help_doc_no_include_cycle() 없음"


def test_w3_sql_05_help_node_no_cycle():
    """W3-SQL-05: help_node_no_cycle() 서명 포함"""
    nc = _nc()
    assert re.search(
        r"\bALTER\s+FUNCTION\s+PUBLIC\.HELP_NODE_NO_CYCLE\s*\(\s*\)", nc
    ), "ALTER FUNCTION public.help_node_no_cycle() 없음"


def test_w3_sql_06_search_path_value():
    """W3-SQL-06: search_path 값 = pg_catalog, public, pg_temp (≥2건)"""
    nc = _nc()
    matches = re.findall(r"SEARCH_PATH\s*=\s*PG_CATALOG\s*,\s*PUBLIC\s*,\s*PG_TEMP", nc)
    assert len(matches) >= 2, f"search_path 설정 횟수={len(matches)}, 기대≥2"


def test_w3_sql_07_pg_temp_last():
    """W3-SQL-07: pg_temp이 search_path 마지막"""
    nc_raw = "\n".join(
        ln for ln in _sql().splitlines() if not ln.strip().startswith("--")
    )
    for m in re.finditer(r"SET\s+search_path\s*(?:=|TO)\s*([^\n;]+)", nc_raw, re.IGNORECASE):
        path_val = m.group(1).strip().rstrip(";").strip()
        parts = [p.strip() for p in path_val.split(",")]
        assert parts[-1].lower() == "pg_temp", \
            f"pg_temp이 search_path 마지막 아님: {path_val!r}"


# ── 금지 패턴 ─────────────────────────────────────────────────────────────────

def test_w3_sql_08_no_create_or_replace_function():
    """W3-SQL-08: CREATE [OR REPLACE] FUNCTION 없음"""
    nc = _nc()
    assert not re.search(r"\bCREATE\s+(OR\s+REPLACE\s+)?FUNCTION\b", nc), \
        "CREATE FUNCTION 또는 CREATE OR REPLACE FUNCTION 발견"


def test_w3_sql_09_no_drop_function():
    """W3-SQL-09: DROP FUNCTION 없음"""
    nc = _nc()
    assert not re.search(r"\bDROP\s+FUNCTION\b", nc), "DROP FUNCTION 발견"


def test_w3_sql_10_no_trigger_ddl():
    """W3-SQL-10: 트리거 DDL 없음 (CREATE/DROP TRIGGER)"""
    nc = _nc()
    assert not re.search(r"\b(CREATE|DROP)\s+TRIGGER\b", nc), "TRIGGER DDL 발견"


def test_w3_sql_11_no_table_ddl():
    """W3-SQL-11: 테이블 DDL 없음 (CREATE/ALTER/DROP TABLE)"""
    nc = _nc()
    assert not re.search(r"\b(CREATE|ALTER|DROP)\s+TABLE\b", nc), "TABLE DDL 발견"


def test_w3_sql_12_no_rls_policy():
    """W3-SQL-12: RLS/Policy 변경 없음"""
    nc = _nc()
    assert not re.search(r"\b(ENABLE|DISABLE)\s+ROW\s+LEVEL\s+SECURITY\b", nc), \
        "ROW LEVEL SECURITY 변경 발견"
    assert not re.search(r"\bCREATE\s+POLICY\b", nc), "CREATE POLICY 발견"
    assert not re.search(r"\bDROP\s+POLICY\b", nc), "DROP POLICY 발견"


def test_w3_sql_13_no_grant():
    """W3-SQL-13: GRANT 없음"""
    nc = _nc()
    assert not re.search(r"^\s*GRANT\b", nc, re.MULTILINE), "GRANT 발견"


def test_w3_sql_14_no_revoke():
    """W3-SQL-14: REVOKE 없음"""
    nc = _nc()
    assert not re.search(r"^\s*REVOKE\b", nc, re.MULTILINE), "REVOKE 발견"


def test_w3_sql_15_no_dml():
    """W3-SQL-15: DML 없음 (INSERT/UPDATE/DELETE/TRUNCATE)"""
    nc = _nc()
    assert not re.search(r"^\s*(INSERT|UPDATE|DELETE|TRUNCATE)\b", nc, re.MULTILINE), \
        "DML 발견"


# ── PRE 조건 검증 패턴 ─────────────────────────────────────────────────────────

def test_w3_sql_16_pre_security_invoker():
    """W3-SQL-16: PRE — SECURITY INVOKER 검증 포함"""
    nc = _nc()
    assert re.search(r"V_SECDEF\s+IS\s+DISTINCT\s+FROM\s+FALSE", nc), \
        "PRE v_secdef IS DISTINCT FROM false 없음"


def test_w3_sql_17_pre_body_md5_baselines():
    """W3-SQL-17: PRE — 2개 함수 본문 MD5 기준선 포함"""
    sql = _sql()
    for name, md5 in _PROSRC_MD5.items():
        assert md5 in sql, f"PRE body_md5 기준선 없음: {name} = {md5}"


def test_w3_sql_18_pre_proconfig_null():
    """W3-SQL-18: PRE — proconfig IS NULL 검증 포함"""
    nc = _nc()
    assert re.search(r"PROCONFIG\s+IS\s+NOT\s+NULL", nc), \
        "PRE proconfig IS NOT NULL 검증 없음"


def test_w3_sql_19_pre_anon_execute():
    """W3-SQL-19: PRE — anon EXECUTE 검증 포함"""
    nc = _nc()
    assert re.search(r"HAS_FUNCTION_PRIVILEGE\s*\(\s*'ANON'", nc), \
        "PRE anon EXECUTE 검증 없음"


def test_w3_sql_20_pre_authenticated_execute():
    """W3-SQL-20: PRE — authenticated EXECUTE 검증 포함"""
    nc = _nc()
    assert re.search(r"HAS_FUNCTION_PRIVILEGE\s*\(\s*'AUTHENTICATED'", nc), \
        "PRE authenticated EXECUTE 검증 없음"


def test_w3_sql_21_pre_acl_baseline():
    """W3-SQL-21: PRE — ACL 기준선 상수 선언 및 검증 포함"""
    sql = _sql()
    assert "c_acl_baseline" in sql, "c_acl_baseline 상수 없음"
    assert "{=X/postgres,postgres=X/postgres,anon=X/postgres,authenticated=X/postgres,service_role=X/postgres}" in sql, \
        "ACL 기준선 값 없음"


def test_w3_sql_22_pre_volatility_baseline():
    """W3-SQL-22: PRE — Volatility 기준선 검증 포함 (v = VOLATILE)"""
    nc = _nc()
    assert re.search(r"V_VOLAT\s+IS\s+DISTINCT\s+FROM\s+'V'", nc), \
        "PRE v_volat IS DISTINCT FROM 'v' 검증 없음"


def test_w3_sql_23_pre_parallel_baseline():
    """W3-SQL-23: PRE — Parallel 기준선 검증 포함 (u = UNSAFE)"""
    nc = _nc()
    assert re.search(r"V_PARALLEL\s+IS\s+DISTINCT\s+FROM\s+'U'", nc), \
        "PRE v_parallel IS DISTINCT FROM 'u' 검증 없음"


def test_w3_sql_24_pre_trigger_baselines():
    """W3-SQL-24: PRE — 트리거 2개 기준선 검증 포함"""
    sql = _sql()
    for tg_name, tg_md5 in _TRIGGER_MD5.items():
        assert tg_name in sql, f"PRE 트리거 기준선 없음: {tg_name}"
        assert tg_md5 in sql, f"PRE 트리거 MD5 기준선 없음: {tg_name} = {tg_md5}"


def test_w3_sql_25_pre_w2_dependency_check():
    """W3-SQL-25: PRE — W2 의존 함수 설정 유지 확인 포함"""
    sql = _sql()
    assert "help_doc_include_refs(jsonb)" in sql, \
        "PRE W2 의존 함수 help_doc_include_refs 확인 없음"
    assert "help_doc_include_refs proconfig" in sql.lower() or \
           "w2 help_doc_include_refs" in sql.lower(), \
        "PRE W2 help_doc_include_refs proconfig 유지 확인 없음"


# ── POST 조건 검증 패턴 ────────────────────────────────────────────────────────

def test_w3_sql_26_post_proconfig_check():
    """W3-SQL-26: POST — proconfig 설정 검증 포함 (IS DISTINCT FROM)"""
    nc = _nc()
    assert re.search(
        r"V_PROCONFIG\s+IS\s+DISTINCT\s+FROM\s+ARRAY\[C_SEARCH_PATH\]", nc
    ), "POST proconfig IS DISTINCT FROM ARRAY[c_search_path] 검증 없음"
    assert "SEARCH_PATH=PG_CATALOG, PUBLIC, PG_TEMP" in nc, \
        "POST search_path 기대값 상수 없음"


def test_w3_sql_27_post_body_md5():
    """W3-SQL-27: POST — 본문 MD5 불변 검증 포함"""
    nc = _nc()
    assert re.search(r"V_BODY_MD5\s+IS\s+DISTINCT\s+FROM\s+V_MD5S", nc), \
        "POST body_md5 불변 검증 없음"


def test_w3_sql_28_post_security_invoker():
    """W3-SQL-28: POST — SECURITY INVOKER 불변 검증 포함"""
    nc = _nc()
    matches = re.findall(r"V_SECDEF\s+IS\s+DISTINCT\s+FROM\s+FALSE", nc)
    assert len(matches) >= 2, f"POST v_secdef 불변 검증 횟수={len(matches)}, 기대≥2"


def test_w3_sql_29_post_acl_unchanged():
    """W3-SQL-29: POST — ACL 불변 검증 포함"""
    nc = _nc()
    matches = re.findall(r"V_PROACL\s+IS\s+DISTINCT\s+FROM\s+C_ACL_BASELINE", nc)
    assert len(matches) >= 2, f"POST ACL 불변 검증 횟수={len(matches)}, 기대≥2"


def test_w3_sql_30_post_volatility_unchanged():
    """W3-SQL-30: POST — Volatility 불변 검증 포함"""
    nc = _nc()
    matches = re.findall(r"V_VOLAT\s+IS\s+DISTINCT\s+FROM\s+'V'", nc)
    assert len(matches) >= 2, f"POST v_volat 불변 검증 횟수={len(matches)}, 기대≥2"


def test_w3_sql_31_post_parallel_unchanged():
    """W3-SQL-31: POST — Parallel 불변 검증 포함"""
    nc = _nc()
    matches = re.findall(r"V_PARALLEL\s+IS\s+DISTINCT\s+FROM\s+'U'", nc)
    assert len(matches) >= 2, f"POST v_parallel 불변 검증 횟수={len(matches)}, 기대≥2"


def test_w3_sql_32_post_trigger_unchanged():
    """W3-SQL-32: POST — 트리거 불변 검증 포함"""
    nc = _nc()
    matches = [ln for ln in nc.splitlines() if "HELP_DOC_NO_INCLUDE_CYCLE_TRG" in ln or
               "HELP_NODE_NO_CYCLE_TRG" in ln]
    assert len(matches) >= 4, \
        f"트리거 불변 검증이 PRE+POST 양쪽에 없음 (발견={len(matches)})"


# ── 구현 패턴 ─────────────────────────────────────────────────────────────────

def test_w3_sql_33_to_regprocedure_oid():
    """W3-SQL-33: to_regprocedure() OID 기반 식별 (≥3회)"""
    nc = _nc()
    matches = re.findall(r"\bTO_REGPROCEDURE\b", nc)
    assert len(matches) >= 3, f"to_regprocedure 사용 횟수={len(matches)}, 기대≥3"


def test_w3_sql_34_is_distinct_from():
    """W3-SQL-34: IS DISTINCT FROM null-safe 비교 사용 (≥5회)"""
    nc = _nc()
    matches = re.findall(r"\bIS\s+DISTINCT\s+FROM\b", nc)
    assert len(matches) >= 5, f"IS DISTINCT FROM 횟수={len(matches)}, 기대≥5"


def test_w3_sql_35_no_out_of_scope_functions():
    """W3-SQL-35: W1·W2·W4 범위 외 함수 미포함"""
    nc = _nc()
    # W1 함수들
    w1_funcs = [
        "FN_SET_UPDATED_AT", "SET_UPDATED_AT", "HELP_TOUCH_UPDATED_AT",
        "UPDATE_CMC_UPDATED_AT", "UPDATE_DOCUMENTS_TIMESTAMP",
        "UPDATE_TIMESTAMP", "UPDATE_UPDATED_AT_COLUMN", "TG_KOSHA_GUIDE_BODY_TOUCH",
    ]
    for fn in w1_funcs:
        assert not re.search(
            rf"\bALTER\s+FUNCTION\s+PUBLIC\.{fn}\b", nc
        ), f"W1 함수 {fn} 가 W3 Migration에 포함됨"
    # W2 함수들
    w2_funcs = [
        "GENERATE_REQUEST_NO", "HELP_BLOCKS_VALID",
        "HELP_DOC_INCLUDE_REFS", "JSONB_TO_TEXT_ARRAY",
    ]
    for fn in w2_funcs:
        assert not re.search(
            rf"\bALTER\s+FUNCTION\s+PUBLIC\.{fn}\b", nc
        ), f"W2 함수 {fn} 가 W3 Migration에 포함됨"
    # W4 BLOCKED 함수들
    w4_funcs = [
        "FN_GENERATE_ASSET_CODE", "FN_GENERATE_COMPANY_CODE",
        "FN_GENERATE_SITE_CODE", "FN_GENERATE_TEAM_CODE",
        "FN_GENERATE_USER_CODE",
    ]
    for fn in w4_funcs:
        assert not re.search(
            rf"\bALTER\s+FUNCTION\s+PUBLIC\.{fn}\b", nc
        ), f"W4 BLOCKED 함수 {fn} 가 W3 Migration에 포함됨"


def test_w3_sql_36_oid_array():
    """W3-SQL-36: OID 배열에 2개 OID 포함 (246456/246423)"""
    sql = _sql()
    for oid in [246456, 246423]:
        assert str(oid) in sql, f"OID {oid} 기준선 없음"


def test_w3_sql_37_volatility_all_volatile():
    """W3-SQL-37: Volatility는 모두 'v' (VOLATILE) 고정"""
    sql = _sql()
    assert re.search(r"IS\s+DISTINCT\s+FROM\s+'v'", sql), \
        "Volatility 'v' 기준선 없음"
    assert not re.search(r"ARRAY\s*\[.*'i'.*\]", sql), \
        "Volatility 배열에 IMMUTABLE('i') 포함됨 — W3은 모두 VOLATILE"


# ── 소스 SHA256 고정 ───────────────────────────────────────────────────────────

def test_w3_src_01_migration_sha256():
    """W3-SRC-01: W3 Migration SHA256 고정"""
    expected = "100848064eea49218ce1d4b1b8f38671532fabd7660cf00d436a185e9d7442c5"
    actual = _sha256(_MIGRATION_PATH)
    assert actual == expected, f"W3 Migration SHA256 불일치: {actual}"


def test_w3_src_02_w2_migration_sha256():
    """W3-SRC-02: W2 Migration SHA256 불변"""
    expected = "8b4fd42a0ac8c675c4f26c7e70da51474a734f26e66eb455454c0fb6f06f3cec"
    actual = _sha256(_W2_MIGRATION_PATH)
    assert actual == expected, f"W2 Migration SHA256 변경됨: {actual}"
