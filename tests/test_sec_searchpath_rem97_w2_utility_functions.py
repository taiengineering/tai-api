"""
WO-TAI-SEC-SEARCHPATH-REM97-C3-W2-SOURCE-001 정적 계약 테스트
유틸리티 함수 4개 search_path 고정 Migration 검증

대상 Migration:
  20261023082048_sec_searchpath_rem97_w2_utility_functions.sql

테스트 목록:
  W2-SQL-01  Migration 파일 존재
  W2-SQL-02  BEGIN/COMMIT 트랜잭션 구조
  W2-SQL-03  ALTER FUNCTION 정확히 4건
  W2-SQL-04  generate_request_no() 서명 포함
  W2-SQL-05  help_blocks_valid(b jsonb) 서명 포함
  W2-SQL-06  help_doc_include_refs(b jsonb) 서명 포함
  W2-SQL-07  jsonb_to_text_array(j jsonb) 서명 포함
  W2-SQL-08  search_path 값 = pg_catalog, public, pg_temp (≥4건)
  W2-SQL-09  pg_temp이 search_path 마지막
  W2-SQL-10  CREATE [OR REPLACE] FUNCTION 없음
  W2-SQL-11  DROP FUNCTION 없음
  W2-SQL-12  트리거 DDL 없음 (CREATE/DROP TRIGGER)
  W2-SQL-13  테이블 DDL 없음 (CREATE/ALTER/DROP TABLE)
  W2-SQL-14  RLS/Policy 변경 없음
  W2-SQL-15  GRANT 없음
  W2-SQL-16  REVOKE 없음
  W2-SQL-17  DML 없음 (INSERT/UPDATE/DELETE/TRUNCATE)
  W2-SQL-18  PRE — SECURITY INVOKER 검증 포함 (IS DISTINCT FROM false)
  W2-SQL-19  PRE — 4개 함수 본문 MD5 기준선 포함
  W2-SQL-20  PRE — proconfig IS NULL 검증 포함
  W2-SQL-21  PRE — anon EXECUTE 검증 포함
  W2-SQL-22  PRE — authenticated EXECUTE 검증 포함
  W2-SQL-23  PRE — ACL 기준선 상수 선언 및 검증 포함
  W2-SQL-24  PRE — Volatility 기준선 검증 포함
  W2-SQL-25  PRE — help_doc_blocks_chk 제약조건 기준선 검증 포함
  W2-SQL-26  POST — proconfig 설정 검증 포함 (IS DISTINCT FROM)
  W2-SQL-27  POST — 본문 MD5 불변 검증 포함
  W2-SQL-28  POST — SECURITY INVOKER 불변 검증 포함
  W2-SQL-29  POST — ACL 불변 검증 포함
  W2-SQL-30  POST — Volatility 불변 검증 포함
  W2-SQL-31  POST — help_doc_blocks_chk 제약조건 불변 검증 포함
  W2-SQL-32  to_regprocedure() OID 기반 식별 (≥4회)
  W2-SQL-33  IS DISTINCT FROM null-safe 비교 사용 (≥5회)
  W2-SQL-34  W1/W3/W4/W5 범위 외 함수 미포함
  W2-SQL-35  OID 배열에 4개 OID 포함 (18565/246342/246455/18569)
  W2-SQL-36  Volatility 배열에 v/i/i/i 패턴 포함
  W2-BEH-01  generate_request_no 본문 MD5 기준선
  W2-BEH-02  help_blocks_valid 본문 MD5 기준선
  W2-BEH-03  help_doc_include_refs 본문 MD5 기준선
  W2-BEH-04  jsonb_to_text_array 본문 MD5 기준선
  W2-SRC-01  이 Migration SHA256 고정
  W2-SRC-02  W1 Migration SHA256 불변
"""

import hashlib
import pathlib
import re

import pytest

_MIGRATION_NAME = "20261023082048_sec_searchpath_rem97_w2_utility_functions.sql"
_W1_MIGRATION_NAME = "20261023012950_sec_searchpath_rem97_w1_timestamp_triggers.sql"
_MIGRATIONS_DIR = pathlib.Path(__file__).parent.parent / "supabase" / "migrations"
_MIGRATION_PATH = _MIGRATIONS_DIR / _MIGRATION_NAME
_W1_MIGRATION_PATH = _MIGRATIONS_DIR / _W1_MIGRATION_NAME
_TARGET_SEARCH_PATH = "pg_catalog, public, pg_temp"

# 운영 DB에서 확인된 함수 본문 MD5 기준선
_PROSRC_MD5 = {
    "generate_request_no":   "bc68b45992c6ae6918b7b7897968eb59",
    "help_blocks_valid":     "f8ab771e143a1f4bae50d8f4e834956c",
    "help_doc_include_refs": "f59b1a9e351738a420a554dbd3bf005e",
    "jsonb_to_text_array":   "8ffd61ed1e5f379f96de29d745138596",
}

# 운영 DB에서 확인된 OID
_OIDS = {
    "generate_request_no":   18565,
    "help_blocks_valid":     246342,
    "help_doc_include_refs": 246455,
    "jsonb_to_text_array":   18569,
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

def test_w2_sql_01_migration_file_exists():
    """W2-SQL-01: Migration 파일 존재"""
    assert _MIGRATION_PATH.exists(), f"{_MIGRATION_NAME} 파일 없음"


# ── 트랜잭션 구조 ──────────────────────────────────────────────────────────────

def test_w2_sql_02_transaction_structure():
    """W2-SQL-02: BEGIN/COMMIT 트랜잭션 구조"""
    nc = _nc()
    assert re.search(r"^\s*BEGIN\s*;", nc, re.MULTILINE), "BEGIN; 없음"
    assert re.search(r"^\s*COMMIT\s*;", nc, re.MULTILINE), "COMMIT; 없음"


# ── ALTER FUNCTION 대상 ────────────────────────────────────────────────────────

def test_w2_sql_03_alter_function_exactly_four():
    """W2-SQL-03: ALTER FUNCTION 정확히 4건"""
    nc = _nc()
    matches = re.findall(r"\bALTER\s+FUNCTION\b", nc)
    assert len(matches) == 4, f"ALTER FUNCTION 횟수={len(matches)}, 기대=4"


def test_w2_sql_04_generate_request_no():
    """W2-SQL-04: generate_request_no() 서명 포함"""
    nc = _nc()
    assert re.search(
        r"\bALTER\s+FUNCTION\s+PUBLIC\.GENERATE_REQUEST_NO\s*\(\s*\)", nc
    ), "ALTER FUNCTION public.generate_request_no() 없음"


def test_w2_sql_05_help_blocks_valid():
    """W2-SQL-05: help_blocks_valid(b jsonb) 서명 포함"""
    nc = _nc()
    assert re.search(
        r"\bALTER\s+FUNCTION\s+PUBLIC\.HELP_BLOCKS_VALID\s*\(\s*B\s+JSONB\s*\)", nc
    ), "ALTER FUNCTION public.help_blocks_valid(b jsonb) 없음"


def test_w2_sql_06_help_doc_include_refs():
    """W2-SQL-06: help_doc_include_refs(b jsonb) 서명 포함"""
    nc = _nc()
    assert re.search(
        r"\bALTER\s+FUNCTION\s+PUBLIC\.HELP_DOC_INCLUDE_REFS\s*\(\s*B\s+JSONB\s*\)", nc
    ), "ALTER FUNCTION public.help_doc_include_refs(b jsonb) 없음"


def test_w2_sql_07_jsonb_to_text_array():
    """W2-SQL-07: jsonb_to_text_array(j jsonb) 서명 포함"""
    nc = _nc()
    assert re.search(
        r"\bALTER\s+FUNCTION\s+PUBLIC\.JSONB_TO_TEXT_ARRAY\s*\(\s*J\s+JSONB\s*\)", nc
    ), "ALTER FUNCTION public.jsonb_to_text_array(j jsonb) 없음"


def test_w2_sql_08_search_path_value():
    """W2-SQL-08: search_path 값 = pg_catalog, public, pg_temp (≥4건)"""
    nc = _nc()
    matches = re.findall(r"SEARCH_PATH\s*=\s*PG_CATALOG\s*,\s*PUBLIC\s*,\s*PG_TEMP", nc)
    assert len(matches) >= 4, f"search_path 설정 횟수={len(matches)}, 기대≥4"


def test_w2_sql_09_pg_temp_last():
    """W2-SQL-09: pg_temp이 search_path 마지막"""
    nc_raw = "\n".join(
        ln for ln in _sql().splitlines() if not ln.strip().startswith("--")
    )
    for m in re.finditer(r"SET\s+search_path\s*(?:=|TO)\s*([^\n;]+)", nc_raw, re.IGNORECASE):
        path_val = m.group(1).strip().rstrip(";").strip()
        parts = [p.strip() for p in path_val.split(",")]
        assert parts[-1].lower() == "pg_temp", \
            f"pg_temp이 search_path 마지막 아님: {path_val!r}"


# ── 금지 패턴 ─────────────────────────────────────────────────────────────────

def test_w2_sql_10_no_create_or_replace_function():
    """W2-SQL-10: CREATE [OR REPLACE] FUNCTION 없음"""
    nc = _nc()
    assert not re.search(r"\bCREATE\s+(OR\s+REPLACE\s+)?FUNCTION\b", nc), \
        "CREATE FUNCTION 또는 CREATE OR REPLACE FUNCTION 발견"


def test_w2_sql_11_no_drop_function():
    """W2-SQL-11: DROP FUNCTION 없음"""
    nc = _nc()
    assert not re.search(r"\bDROP\s+FUNCTION\b", nc), "DROP FUNCTION 발견"


def test_w2_sql_12_no_trigger_ddl():
    """W2-SQL-12: 트리거 DDL 없음 (CREATE/DROP TRIGGER)"""
    nc = _nc()
    assert not re.search(r"\b(CREATE|DROP)\s+TRIGGER\b", nc), "TRIGGER DDL 발견"


def test_w2_sql_13_no_table_ddl():
    """W2-SQL-13: 테이블 DDL 없음 (CREATE/ALTER/DROP TABLE)"""
    nc = _nc()
    assert not re.search(r"\b(CREATE|ALTER|DROP)\s+TABLE\b", nc), "TABLE DDL 발견"


def test_w2_sql_14_no_rls_policy():
    """W2-SQL-14: RLS/Policy 변경 없음"""
    nc = _nc()
    assert not re.search(r"\b(ENABLE|DISABLE)\s+ROW\s+LEVEL\s+SECURITY\b", nc), \
        "ROW LEVEL SECURITY 변경 발견"
    assert not re.search(r"\bCREATE\s+POLICY\b", nc), "CREATE POLICY 발견"
    assert not re.search(r"\bDROP\s+POLICY\b", nc), "DROP POLICY 발견"


def test_w2_sql_15_no_grant():
    """W2-SQL-15: GRANT 없음"""
    nc = _nc()
    assert not re.search(r"^\s*GRANT\b", nc, re.MULTILINE), "GRANT 발견"


def test_w2_sql_16_no_revoke():
    """W2-SQL-16: REVOKE 없음"""
    nc = _nc()
    assert not re.search(r"^\s*REVOKE\b", nc, re.MULTILINE), "REVOKE 발견"


def test_w2_sql_17_no_dml():
    """W2-SQL-17: DML 없음 (INSERT/UPDATE/DELETE/TRUNCATE)"""
    nc = _nc()
    assert not re.search(r"^\s*(INSERT|UPDATE|DELETE|TRUNCATE)\b", nc, re.MULTILINE), \
        "DML 발견"


# ── PRE 조건 검증 패턴 ─────────────────────────────────────────────────────────

def test_w2_sql_18_pre_security_invoker():
    """W2-SQL-18: PRE — SECURITY INVOKER 검증 포함 (IS DISTINCT FROM false)"""
    nc = _nc()
    assert re.search(r"V_SECDEF\s+IS\s+DISTINCT\s+FROM\s+FALSE", nc), \
        "PRE v_secdef IS DISTINCT FROM false 없음"


def test_w2_sql_19_pre_body_md5_baselines():
    """W2-SQL-19: PRE — 4개 함수 본문 MD5 기준선 포함"""
    sql = _sql()
    for name, md5 in _PROSRC_MD5.items():
        assert md5 in sql, f"PRE body_md5 기준선 없음: {name} = {md5}"


def test_w2_sql_20_pre_proconfig_null():
    """W2-SQL-20: PRE — proconfig IS NULL 검증 포함"""
    nc = _nc()
    assert re.search(r"PROCONFIG\s+IS\s+NOT\s+NULL", nc), \
        "PRE proconfig IS NOT NULL 검증 없음"


def test_w2_sql_21_pre_anon_execute():
    """W2-SQL-21: PRE — anon EXECUTE 검증 포함"""
    nc = _nc()
    assert re.search(r"HAS_FUNCTION_PRIVILEGE\s*\(\s*'ANON'", nc), \
        "PRE anon EXECUTE 검증 없음"


def test_w2_sql_22_pre_authenticated_execute():
    """W2-SQL-22: PRE — authenticated EXECUTE 검증 포함"""
    nc = _nc()
    assert re.search(r"HAS_FUNCTION_PRIVILEGE\s*\(\s*'AUTHENTICATED'", nc), \
        "PRE authenticated EXECUTE 검증 없음"


def test_w2_sql_23_pre_acl_baseline():
    """W2-SQL-23: PRE — ACL 기준선 상수 선언 및 검증 포함"""
    sql = _sql()
    assert "c_acl_baseline" in sql, "c_acl_baseline 상수 없음"
    assert "{=X/postgres,postgres=X/postgres,anon=X/postgres,authenticated=X/postgres,service_role=X/postgres}" in sql, \
        "ACL 기준선 값 없음"


def test_w2_sql_24_pre_volatility_baseline():
    """W2-SQL-24: PRE — Volatility 기준선 검증 포함"""
    nc = _nc()
    assert re.search(r"V_VOLAT\s+IS\s+DISTINCT\s+FROM", nc), \
        "PRE v_volat IS DISTINCT FROM 검증 없음"
    assert "V_VOLATS" in nc, "v_volats 배열 없음"


def test_w2_sql_25_pre_constraint_check():
    """W2-SQL-25: PRE — help_doc_blocks_chk 제약조건 기준선 검증 포함"""
    sql = _sql()
    assert "help_doc_blocks_chk" in sql, "PRE help_doc_blocks_chk 제약조건 검증 없음"
    assert "CHECK (help_blocks_valid(blocks))" in sql, \
        "PRE help_doc_blocks_chk 정의 기준선 없음"


# ── POST 조건 검증 패턴 ────────────────────────────────────────────────────────

def test_w2_sql_26_post_proconfig_check():
    """W2-SQL-26: POST — proconfig 설정 검증 포함 (IS DISTINCT FROM)"""
    nc = _nc()
    assert re.search(
        r"V_PROCONFIG\s+IS\s+DISTINCT\s+FROM\s+ARRAY\[C_SEARCH_PATH\]", nc
    ), "POST proconfig IS DISTINCT FROM ARRAY[c_search_path] 검증 없음"
    assert "SEARCH_PATH=PG_CATALOG, PUBLIC, PG_TEMP" in nc, \
        "POST search_path 기대값 상수 없음"


def test_w2_sql_27_post_body_md5():
    """W2-SQL-27: POST — 본문 MD5 불변 검증 포함"""
    nc = _nc()
    assert re.search(r"V_BODY_MD5\s+IS\s+DISTINCT\s+FROM\s+V_MD5S", nc), \
        "POST body_md5 불변 검증 없음"


def test_w2_sql_28_post_security_invoker():
    """W2-SQL-28: POST — SECURITY INVOKER 불변 검증 포함"""
    nc = _nc()
    # PRE와 POST 모두 v_secdef IS DISTINCT FROM false 포함
    matches = re.findall(r"V_SECDEF\s+IS\s+DISTINCT\s+FROM\s+FALSE", nc)
    assert len(matches) >= 2, f"POST v_secdef 불변 검증 횟수={len(matches)}, 기대≥2"


def test_w2_sql_29_post_acl_unchanged():
    """W2-SQL-29: POST — ACL 불변 검증 포함"""
    nc = _nc()
    matches = re.findall(r"V_PROACL\s+IS\s+DISTINCT\s+FROM\s+C_ACL_BASELINE", nc)
    assert len(matches) >= 2, f"POST ACL 불변 검증 횟수={len(matches)}, 기대≥2"


def test_w2_sql_30_post_volatility_unchanged():
    """W2-SQL-30: POST — Volatility 불변 검증 포함"""
    nc = _nc()
    matches = re.findall(r"V_VOLAT\s+IS\s+DISTINCT\s+FROM", nc)
    assert len(matches) >= 2, f"POST v_volat 불변 검증 횟수={len(matches)}, 기대≥2"


def test_w2_sql_31_post_constraint_check():
    """W2-SQL-31: POST — help_doc_blocks_chk 제약조건 불변 검증 포함"""
    nc = _nc()
    # STEP 3B 블록에서도 help_doc_blocks_chk 검증이 있어야 함
    matches = [ln for ln in nc.splitlines() if "HELP_DOC_BLOCKS_CHK" in ln]
    assert len(matches) >= 2, \
        f"help_doc_blocks_chk 검증이 PRE+POST 양쪽에 없음 (발견={len(matches)})"


# ── 구현 패턴 ─────────────────────────────────────────────────────────────────

def test_w2_sql_32_to_regprocedure_oid():
    """W2-SQL-32: to_regprocedure() OID 기반 식별 (≥4회)"""
    nc = _nc()
    matches = re.findall(r"\bTO_REGPROCEDURE\b", nc)
    assert len(matches) >= 3, f"to_regprocedure 사용 횟수={len(matches)}, 기대≥3"


def test_w2_sql_33_is_distinct_from():
    """W2-SQL-33: IS DISTINCT FROM null-safe 비교 사용 (≥5회)"""
    nc = _nc()
    matches = re.findall(r"\bIS\s+DISTINCT\s+FROM\b", nc)
    assert len(matches) >= 5, f"IS DISTINCT FROM 횟수={len(matches)}, 기대≥5"


def test_w2_sql_34_no_out_of_scope_functions():
    """W2-SQL-34: W1/W3/W4/W5 범위 외 함수 미포함"""
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
        ), f"W1 함수 {fn} 가 W2 Migration에 포함됨"
    # W4 코드생성 함수들 (BLOCKED)
    w4_funcs = [
        "FN_GENERATE_ASSET_CODE", "FN_GENERATE_COMPANY_CODE",
        "FN_GENERATE_SITE_CODE", "FN_GENERATE_TEAM_CODE",
        "FN_GENERATE_USER_CODE",
    ]
    for fn in w4_funcs:
        assert not re.search(
            rf"\bALTER\s+FUNCTION\s+PUBLIC\.{fn}\b", nc
        ), f"W4 BLOCKED 함수 {fn} 가 W2 Migration에 포함됨"


def test_w2_sql_35_oid_array():
    """W2-SQL-35: OID 배열에 4개 OID 포함 (18565/246342/246455/18569)"""
    sql = _sql()
    for oid in [18565, 246342, 246455, 18569]:
        assert str(oid) in sql, f"OID {oid} 기준선 없음"


def test_w2_sql_36_volatility_array():
    """W2-SQL-36: Volatility 배열에 v/i/i/i 패턴 포함"""
    sql = _sql()
    # ARRAY['v', 'i', 'i', 'i'] 패턴
    assert re.search(r"ARRAY\s*\[\s*'v'\s*,\s*'i'\s*,\s*'i'\s*,\s*'i'\s*\]", sql), \
        "v_volats ARRAY['v','i','i','i'] 패턴 없음"


# ── 함수 본문 행동 계약 (MD5 기준선) ──────────────────────────────────────────

def test_w2_beh_01_generate_request_no_md5():
    """W2-BEH-01: generate_request_no 본문 MD5 기준선 — TAI-YYYYMMDD-XXXX 형식"""
    sql = _sql()
    assert _PROSRC_MD5["generate_request_no"] in sql, \
        "generate_request_no body_md5 기준선 없음 (TAI-날짜-랜덤 4자리 형식 계약)"


def test_w2_beh_02_help_blocks_valid_md5():
    """W2-BEH-02: help_blocks_valid 본문 MD5 기준선 — NULL·배열·type·block_id·중복 검증 계약"""
    sql = _sql()
    assert _PROSRC_MD5["help_blocks_valid"] in sql, \
        "help_blocks_valid body_md5 기준선 없음 (jsonb block 구조 검증 계약)"


def test_w2_beh_03_help_doc_include_refs_md5():
    """W2-BEH-03: help_doc_include_refs 본문 MD5 기준선 — type='include' doc_id 배열 반환 계약"""
    sql = _sql()
    assert _PROSRC_MD5["help_doc_include_refs"] in sql, \
        "help_doc_include_refs body_md5 기준선 없음 (include 참조 doc_id 수집 계약)"


def test_w2_beh_04_jsonb_to_text_array_md5():
    """W2-BEH-04: jsonb_to_text_array 본문 MD5 기준선 — jsonb 배열→text[] 변환 계약"""
    sql = _sql()
    assert _PROSRC_MD5["jsonb_to_text_array"] in sql, \
        "jsonb_to_text_array body_md5 기준선 없음 (jsonb→text[] 변환 계약)"


# ── 소스 SHA256 고정 ───────────────────────────────────────────────────────────

def test_w2_src_01_migration_sha256():
    """W2-SRC-01: W2 Migration SHA256 고정"""
    expected = "d181f4d2fb35e43f38a4501d17c117f65ccb6e07c56e11fe9fa045d63327262c"
    actual = _sha256(_MIGRATION_PATH)
    assert actual == expected, f"W2 Migration SHA256 불일치: {actual}"


def test_w2_src_02_w1_migration_sha256():
    """W2-SRC-02: W1 Migration SHA256 불변"""
    expected = "660ed59c767510b2e5c8f491ce4ffe60aa8bc6242eb3db60ef4a69a107dd8863"
    actual = _sha256(_W1_MIGRATION_PATH)
    assert actual == expected, f"W1 Migration SHA256 변경됨: {actual}"
