"""
WO-TAI-SEC-SEARCHPATH-REM97-C3-W5-SOURCE-001 정적 계약 테스트
검색 인덱스 갱신 함수 search_path 고정 Migration 검증

대상 Migration:
  20261024021404_sec_searchpath_rem97_w5_reindex_help.sql

테스트 목록:
  W5-SQL-01  Migration 파일 존재
  W5-SQL-02  BEGIN/COMMIT 트랜잭션 구조
  W5-SQL-03  ALTER FUNCTION 정확히 1건
  W5-SQL-04  reindex_help(uuid, text) 서명 포함
  W5-SQL-05  search_path 값 = pg_catalog, public, pg_temp (≥1건)
  W5-SQL-06  pg_temp이 search_path 마지막
  W5-SQL-07  CREATE [OR REPLACE] FUNCTION 없음
  W5-SQL-08  DROP FUNCTION 없음
  W5-SQL-09  트리거 DDL 없음 (CREATE/DROP TRIGGER)
  W5-SQL-10  테이블 DDL 없음 (CREATE/ALTER/DROP TABLE)
  W5-SQL-11  RLS/Policy 변경 없음
  W5-SQL-12  GRANT 없음
  W5-SQL-13  REVOKE 없음
  W5-SQL-14  DML 없음 (INSERT/UPDATE/DELETE/TRUNCATE)
  W5-SQL-15  PRE — OID 기준선 포함 (243820)
  W5-SQL-16  PRE — 함수 본문 MD5 기준선 포함
  W5-SQL-17  PRE — proconfig IS NULL 검증 포함
  W5-SQL-18  PRE — SECURITY INVOKER 검증 포함
  W5-SQL-19  PRE — ACL 기준선 상수 포함
  W5-SQL-20  PRE — anon EXECUTE 검증 포함
  W5-SQL-21  PRE — authenticated EXECUTE 검증 포함
  W5-SQL-22  PRE — Volatility 기준선 검증 포함 (v = VOLATILE)
  W5-SQL-23  PRE — Parallel 기준선 검증 포함 (u = UNSAFE)
  W5-SQL-24  PRE — safe_help_content 테이블 존재 확인 포함
  W5-SQL-25  PRE — 필수 컬럼 (id/search_tsv/updated_at) 확인 포함
  W5-SQL-26  PRE — search_tsv 타입 tsvector 확인 포함
  W5-SQL-27  PRE — text search config 'simple' 확인 포함
  W5-SQL-28  POST — proconfig 설정 검증 포함 (IS DISTINCT FROM)
  W5-SQL-29  POST — 본문 MD5 불변 검증 포함
  W5-SQL-30  POST — SECURITY INVOKER 불변 검증 포함
  W5-SQL-31  POST — ACL 불변 검증 포함
  W5-SQL-32  POST — Volatility 불변 검증 포함
  W5-SQL-33  POST — Parallel 불변 검증 포함
  W5-SQL-34  POST — safe_help_content 테이블 불변 검증 포함
  W5-SQL-35  POST — text search config 'simple' 불변 검증 포함
  W5-SQL-36  to_regprocedure() OID 기반 식별 (≥2회)
  W5-SQL-37  IS DISTINCT FROM null-safe 비교 사용 (≥5회)
  W5-SQL-38  W1·W2·W3·W4 범위 외 함수 미포함
  W5-SRC-01  이 Migration SHA256 고정
  W5-SRC-02  W3 Migration SHA256 불변
"""

import hashlib
import pathlib
import re

_MIGRATION_NAME = "20261024021404_sec_searchpath_rem97_w5_reindex_help.sql"
_W3_MIGRATION_NAME = "20261023124050_sec_searchpath_rem97_w3_cycle_guard_functions.sql"
_MIGRATIONS_DIR = pathlib.Path(__file__).parent.parent / "supabase" / "migrations"
_MIGRATION_PATH = _MIGRATIONS_DIR / _MIGRATION_NAME
_W3_MIGRATION_PATH = _MIGRATIONS_DIR / _W3_MIGRATION_NAME

_PROSRC_MD5 = "5e69750107f8361914662d0609233d7a"
_OID = 243820


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

def test_w5_sql_01_migration_file_exists():
    """W5-SQL-01: Migration 파일 존재"""
    assert _MIGRATION_PATH.exists(), f"{_MIGRATION_NAME} 파일 없음"


# ── 트랜잭션 구조 ──────────────────────────────────────────────────────────────

def test_w5_sql_02_transaction_structure():
    """W5-SQL-02: BEGIN/COMMIT 트랜잭션 구조"""
    nc = _nc()
    assert re.search(r"^\s*BEGIN\s*;", nc, re.MULTILINE), "BEGIN; 없음"
    assert re.search(r"^\s*COMMIT\s*;", nc, re.MULTILINE), "COMMIT; 없음"


# ── ALTER FUNCTION 대상 ────────────────────────────────────────────────────────

def test_w5_sql_03_alter_function_exactly_one():
    """W5-SQL-03: ALTER FUNCTION 정확히 1건"""
    nc = _nc()
    matches = re.findall(r"\bALTER\s+FUNCTION\b", nc)
    assert len(matches) == 1, f"ALTER FUNCTION 횟수={len(matches)}, 기대=1"


def test_w5_sql_04_reindex_help_signature():
    """W5-SQL-04: reindex_help(uuid, text) 서명 포함"""
    nc = _nc()
    assert re.search(
        r"\bALTER\s+FUNCTION\s+PUBLIC\.REINDEX_HELP\s*\(\s*UUID\s*,\s*TEXT\s*\)", nc
    ), "ALTER FUNCTION public.reindex_help(uuid, text) 없음"


def test_w5_sql_05_search_path_value():
    """W5-SQL-05: search_path 값 = pg_catalog, public, pg_temp (≥1건)"""
    nc = _nc()
    matches = re.findall(r"SEARCH_PATH\s*=\s*PG_CATALOG\s*,\s*PUBLIC\s*,\s*PG_TEMP", nc)
    assert len(matches) >= 1, f"search_path 설정 횟수={len(matches)}, 기대≥1"


def test_w5_sql_06_pg_temp_last():
    """W5-SQL-06: pg_temp이 search_path 마지막"""
    nc_raw = "\n".join(
        ln for ln in _sql().splitlines() if not ln.strip().startswith("--")
    )
    for m in re.finditer(r"SET\s+search_path\s*(?:=|TO)\s*([^\n;]+)", nc_raw, re.IGNORECASE):
        path_val = m.group(1).strip().rstrip(";").strip()
        parts = [p.strip() for p in path_val.split(",")]
        assert parts[-1].lower() == "pg_temp", \
            f"pg_temp이 search_path 마지막 아님: {path_val!r}"


# ── 금지 패턴 ─────────────────────────────────────────────────────────────────

def test_w5_sql_07_no_create_or_replace_function():
    """W5-SQL-07: CREATE [OR REPLACE] FUNCTION 없음"""
    nc = _nc()
    assert not re.search(r"\bCREATE\s+(OR\s+REPLACE\s+)?FUNCTION\b", nc), \
        "CREATE FUNCTION 또는 CREATE OR REPLACE FUNCTION 발견"


def test_w5_sql_08_no_drop_function():
    """W5-SQL-08: DROP FUNCTION 없음"""
    nc = _nc()
    assert not re.search(r"\bDROP\s+FUNCTION\b", nc), "DROP FUNCTION 발견"


def test_w5_sql_09_no_trigger_ddl():
    """W5-SQL-09: 트리거 DDL 없음"""
    nc = _nc()
    assert not re.search(r"\b(CREATE|DROP)\s+TRIGGER\b", nc), "TRIGGER DDL 발견"


def test_w5_sql_10_no_table_ddl():
    """W5-SQL-10: 테이블 DDL 없음"""
    nc = _nc()
    assert not re.search(r"\b(CREATE|ALTER|DROP)\s+TABLE\b", nc), "TABLE DDL 발견"


def test_w5_sql_11_no_rls_policy():
    """W5-SQL-11: RLS/Policy 변경 없음"""
    nc = _nc()
    assert not re.search(r"\b(ENABLE|DISABLE)\s+ROW\s+LEVEL\s+SECURITY\b", nc), \
        "ROW LEVEL SECURITY 변경 발견"
    assert not re.search(r"\bCREATE\s+POLICY\b", nc), "CREATE POLICY 발견"
    assert not re.search(r"\bDROP\s+POLICY\b", nc), "DROP POLICY 발견"


def test_w5_sql_12_no_grant():
    """W5-SQL-12: GRANT 없음"""
    nc = _nc()
    assert not re.search(r"^\s*GRANT\b", nc, re.MULTILINE), "GRANT 발견"


def test_w5_sql_13_no_revoke():
    """W5-SQL-13: REVOKE 없음"""
    nc = _nc()
    assert not re.search(r"^\s*REVOKE\b", nc, re.MULTILINE), "REVOKE 발견"


def test_w5_sql_14_no_dml():
    """W5-SQL-14: DML 없음 (INSERT/UPDATE/DELETE/TRUNCATE)"""
    nc = _nc()
    assert not re.search(r"^\s*(INSERT|UPDATE|DELETE|TRUNCATE)\b", nc, re.MULTILINE), \
        "DML 발견"


# ── PRE 조건 검증 패턴 ─────────────────────────────────────────────────────────

def test_w5_sql_15_pre_oid_baseline():
    """W5-SQL-15: PRE — OID 기준선 포함 (243820)"""
    sql = _sql()
    assert str(_OID) in sql, f"OID {_OID} 기준선 없음"


def test_w5_sql_16_pre_body_md5_baseline():
    """W5-SQL-16: PRE — 함수 본문 MD5 기준선 포함"""
    sql = _sql()
    assert _PROSRC_MD5 in sql, f"PRE body_md5 기준선 없음: {_PROSRC_MD5}"


def test_w5_sql_17_pre_proconfig_null():
    """W5-SQL-17: PRE — proconfig IS NULL 검증 포함"""
    nc = _nc()
    assert re.search(r"PROCONFIG\s+IS\s+NOT\s+NULL", nc), \
        "PRE proconfig IS NOT NULL 검증 없음"


def test_w5_sql_18_pre_security_invoker():
    """W5-SQL-18: PRE — SECURITY INVOKER 검증 포함"""
    nc = _nc()
    assert re.search(r"V_SECDEF\s+IS\s+DISTINCT\s+FROM\s+FALSE", nc), \
        "PRE v_secdef IS DISTINCT FROM false 없음"


def test_w5_sql_19_pre_acl_baseline():
    """W5-SQL-19: PRE — ACL 기준선 상수 포함"""
    sql = _sql()
    assert "c_acl_baseline" in sql, "c_acl_baseline 상수 없음"
    assert "{=X/postgres,postgres=X/postgres,anon=X/postgres,authenticated=X/postgres,service_role=X/postgres}" in sql, \
        "ACL 기준선 값 없음"


def test_w5_sql_20_pre_anon_execute():
    """W5-SQL-20: PRE — anon EXECUTE 검증 포함"""
    nc = _nc()
    assert re.search(r"HAS_FUNCTION_PRIVILEGE\s*\(\s*'ANON'", nc), \
        "PRE anon EXECUTE 검증 없음"


def test_w5_sql_21_pre_authenticated_execute():
    """W5-SQL-21: PRE — authenticated EXECUTE 검증 포함"""
    nc = _nc()
    assert re.search(r"HAS_FUNCTION_PRIVILEGE\s*\(\s*'AUTHENTICATED'", nc), \
        "PRE authenticated EXECUTE 검증 없음"


def test_w5_sql_22_pre_volatility_baseline():
    """W5-SQL-22: PRE — Volatility 기준선 검증 포함 (v = VOLATILE)"""
    nc = _nc()
    assert re.search(r"V_VOLAT\s+IS\s+DISTINCT\s+FROM\s+'V'", nc), \
        "PRE v_volat IS DISTINCT FROM 'v' 없음"


def test_w5_sql_23_pre_parallel_baseline():
    """W5-SQL-23: PRE — Parallel 기준선 검증 포함 (u = UNSAFE)"""
    nc = _nc()
    assert re.search(r"V_PARALLEL\s+IS\s+DISTINCT\s+FROM\s+'U'", nc), \
        "PRE v_parallel IS DISTINCT FROM 'u' 없음"


def test_w5_sql_24_pre_safe_help_content_table():
    """W5-SQL-24: PRE — safe_help_content 테이블 존재 확인 포함"""
    sql = _sql()
    assert "safe_help_content" in sql, "safe_help_content 테이블 확인 없음"
    assert "relname = 'safe_help_content'" in sql or \
           "table_name = 'safe_help_content'" in sql, \
        "safe_help_content 테이블 확인 조건 없음"


def test_w5_sql_25_pre_required_columns():
    """W5-SQL-25: PRE — 필수 컬럼 (id/search_tsv/updated_at) 확인 포함"""
    sql = _sql()
    assert "'id'" in sql, "PRE 컬럼 'id' 확인 없음"
    assert "'search_tsv'" in sql, "PRE 컬럼 'search_tsv' 확인 없음"
    assert "'updated_at'" in sql, "PRE 컬럼 'updated_at' 확인 없음"


def test_w5_sql_26_pre_search_tsv_type():
    """W5-SQL-26: PRE — search_tsv 타입 tsvector 확인 포함"""
    sql = _sql()
    assert "tsvector" in sql, "PRE search_tsv tsvector 타입 확인 없음"


def test_w5_sql_27_pre_simple_config():
    """W5-SQL-27: PRE — text search config 'simple' 확인 포함"""
    sql = _sql()
    assert "pg_ts_config" in sql, "PRE pg_ts_config 조회 없음"
    assert "'simple'" in sql or "simple" in sql, "PRE 'simple' config 확인 없음"


# ── POST 조건 검증 패턴 ────────────────────────────────────────────────────────

def test_w5_sql_28_post_proconfig_check():
    """W5-SQL-28: POST — proconfig 설정 검증 포함"""
    nc = _nc()
    assert re.search(
        r"V_PROCONFIG\s+IS\s+DISTINCT\s+FROM\s+ARRAY\[C_SEARCH_PATH\]", nc
    ), "POST proconfig IS DISTINCT FROM ARRAY[c_search_path] 없음"
    assert "SEARCH_PATH=PG_CATALOG, PUBLIC, PG_TEMP" in nc, \
        "POST search_path 기대값 상수 없음"


def test_w5_sql_29_post_body_md5():
    """W5-SQL-29: POST — 본문 MD5 불변 검증 포함"""
    nc = _nc()
    assert re.search(r"V_BODY_MD5\s+IS\s+DISTINCT\s+FROM\s+C_EXPECTED_MD5", nc), \
        "POST body_md5 불변 검증 없음"


def test_w5_sql_30_post_security_invoker():
    """W5-SQL-30: POST — SECURITY INVOKER 불변 검증 포함"""
    nc = _nc()
    matches = re.findall(r"V_SECDEF\s+IS\s+DISTINCT\s+FROM\s+FALSE", nc)
    assert len(matches) >= 2, f"POST v_secdef 불변 검증 횟수={len(matches)}, 기대≥2"


def test_w5_sql_31_post_acl_unchanged():
    """W5-SQL-31: POST — ACL 불변 검증 포함"""
    nc = _nc()
    assert re.search(r"V_PROACL\s+IS\s+DISTINCT\s+FROM\s+C_ACL_BASELINE", nc), \
        "POST ACL 불변 검증 없음"


def test_w5_sql_32_post_volatility_unchanged():
    """W5-SQL-32: POST — Volatility 불변 검증 포함"""
    nc = _nc()
    matches = re.findall(r"V_VOLAT\s+IS\s+DISTINCT\s+FROM\s+'V'", nc)
    assert len(matches) >= 2, f"POST v_volat 불변 검증 횟수={len(matches)}, 기대≥2"


def test_w5_sql_33_post_parallel_unchanged():
    """W5-SQL-33: POST — Parallel 불변 검증 포함"""
    nc = _nc()
    matches = re.findall(r"V_PARALLEL\s+IS\s+DISTINCT\s+FROM\s+'U'", nc)
    assert len(matches) >= 2, f"POST v_parallel 불변 검증 횟수={len(matches)}, 기대≥2"


def test_w5_sql_34_post_table_unchanged():
    """W5-SQL-34: POST — safe_help_content 테이블 불변 검증 포함"""
    nc = _nc()
    matches = [ln for ln in nc.splitlines() if "SAFE_HELP_CONTENT" in ln]
    assert len(matches) >= 4, \
        f"safe_help_content 검증이 PRE+POST 양쪽에 없음 (발견={len(matches)})"


def test_w5_sql_35_post_simple_config_unchanged():
    """W5-SQL-35: POST — text search config 'simple' 불변 검증 포함"""
    nc = _nc()
    matches = [ln for ln in nc.splitlines() if "PG_TS_CONFIG" in ln]
    assert len(matches) >= 2, \
        f"pg_ts_config 검증이 PRE+POST 양쪽에 없음 (발견={len(matches)})"


# ── 구현 패턴 ─────────────────────────────────────────────────────────────────

def test_w5_sql_36_to_regprocedure_oid():
    """W5-SQL-36: to_regprocedure() OID 기반 식별 (≥2회)"""
    nc = _nc()
    matches = re.findall(r"\bTO_REGPROCEDURE\b", nc)
    assert len(matches) >= 2, f"to_regprocedure 사용 횟수={len(matches)}, 기대≥2"


def test_w5_sql_37_is_distinct_from():
    """W5-SQL-37: IS DISTINCT FROM null-safe 비교 사용 (≥5회)"""
    nc = _nc()
    matches = re.findall(r"\bIS\s+DISTINCT\s+FROM\b", nc)
    assert len(matches) >= 5, f"IS DISTINCT FROM 횟수={len(matches)}, 기대≥5"


def test_w5_sql_38_no_out_of_scope_functions():
    """W5-SQL-38: W1·W2·W3·W4 범위 외 함수 미포함"""
    nc = _nc()
    out_of_scope = [
        # W1
        "FN_SET_UPDATED_AT", "SET_UPDATED_AT", "HELP_TOUCH_UPDATED_AT",
        "UPDATE_CMC_UPDATED_AT", "UPDATE_DOCUMENTS_TIMESTAMP",
        "UPDATE_TIMESTAMP", "UPDATE_UPDATED_AT_COLUMN", "TG_KOSHA_GUIDE_BODY_TOUCH",
        # W2
        "GENERATE_REQUEST_NO", "HELP_BLOCKS_VALID",
        "HELP_DOC_INCLUDE_REFS", "JSONB_TO_TEXT_ARRAY",
        # W3
        "HELP_NODE_NO_CYCLE", "HELP_DOC_NO_INCLUDE_CYCLE",
        # W4 BLOCKED
        "FN_GENERATE_ASSET_CODE", "FN_GENERATE_COMPANY_CODE",
        "FN_GENERATE_SITE_CODE", "FN_GENERATE_TEAM_CODE", "FN_GENERATE_USER_CODE",
    ]
    for fn in out_of_scope:
        assert not re.search(
            rf"\bALTER\s+FUNCTION\s+PUBLIC\.{fn}\b", nc
        ), f"범위 외 함수 {fn} 가 W5 Migration에 포함됨"


# ── 소스 SHA256 고정 ───────────────────────────────────────────────────────────

def test_w5_src_01_migration_sha256():
    """W5-SRC-01: W5 Migration SHA256 고정"""
    expected = "4b24b31b204971ed9ce174356491451695aeede302c0e5b093e03f0ff6c5487a"
    actual = _sha256(_MIGRATION_PATH)
    assert actual == expected, f"W5 Migration SHA256 불일치: {actual}"


def test_w5_src_02_w3_migration_sha256():
    """W5-SRC-02: W3 Migration SHA256 불변"""
    expected = "100848064eea49218ce1d4b1b8f38671532fabd7660cf00d436a185e9d7442c5"
    actual = _sha256(_W3_MIGRATION_PATH)
    assert actual == expected, f"W3 Migration SHA256 변경됨: {actual}"
