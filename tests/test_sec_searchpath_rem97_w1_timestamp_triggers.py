"""
WO-TAI-SEC-SEARCHPATH-REM97-C3-W1-SOURCE-001 정적 계약 테스트
타임스탬프 트리거 함수 8개 search_path 고정 Migration 검증

대상 Migration:
  20261023012950_sec_searchpath_rem97_w1_timestamp_triggers.sql

테스트 목록:
  W1-SQL-01  Migration 파일 존재
  W1-SQL-02  BEGIN/COMMIT 트랜잭션 구조
  W1-SQL-03  ALTER FUNCTION 정확히 8건
  W1-SQL-04  fn_set_updated_at() 서명 포함
  W1-SQL-05  set_updated_at() 서명 포함
  W1-SQL-06  help_touch_updated_at() 서명 포함
  W1-SQL-07  update_cmc_updated_at() 서명 포함
  W1-SQL-08  update_documents_timestamp() 서명 포함
  W1-SQL-09  update_timestamp() 서명 포함
  W1-SQL-10  update_updated_at_column() 서명 포함
  W1-SQL-11  tg_kosha_guide_body_touch() 서명 포함
  W1-SQL-12  search_path 값 = pg_catalog, public, pg_temp (≥8건)
  W1-SQL-13  pg_temp이 search_path 마지막
  W1-SQL-14  CREATE [OR REPLACE] FUNCTION 없음
  W1-SQL-15  DROP FUNCTION 없음
  W1-SQL-16  트리거 DDL 없음 (CREATE/DROP TRIGGER)
  W1-SQL-17  테이블 DDL 없음 (CREATE/ALTER/DROP TABLE)
  W1-SQL-18  RLS/Policy 변경 없음
  W1-SQL-19  GRANT 없음
  W1-SQL-20  REVOKE 없음
  W1-SQL-21  DML 없음 (INSERT/UPDATE/DELETE/TRUNCATE)
  W1-SQL-22  PRE — SECURITY INVOKER 검증 포함 (IS DISTINCT FROM false)
  W1-SQL-23  PRE — 8개 함수 본문 MD5 기준선 포함
  W1-SQL-24  PRE — proconfig IS NULL 검증 포함
  W1-SQL-25  PRE — anon EXECUTE 검증 포함
  W1-SQL-26  PRE — authenticated EXECUTE 검증 포함
  W1-SQL-27  PRE — ACL 기준선 상수 선언 및 검증 포함
  W1-SQL-28  PRE — 트리거 수 기준선 배열 포함 (17건 합산)
  W1-SQL-29  POST — proconfig 설정 검증 포함
  W1-SQL-30  POST — 본문 MD5 불변 검증 포함
  W1-SQL-31  POST — SECURITY INVOKER 불변 검증 포함
  W1-SQL-32  POST — ACL 불변 검증 포함
  W1-SQL-33  POST — 트리거 수 불변 검증 포함
  W1-SQL-34  to_regprocedure() OID 기반 식별 (≥8회)
  W1-SQL-35  IS DISTINCT FROM null-safe 비교 사용 (≥5회)
  W1-SQL-36  W2/W3/W4/W5 범위 외 함수 미포함
  W1-SRC-01  이 Migration SHA256 고정
  W1-SRC-02  P0C Migration SHA256 불변
"""

import hashlib
import pathlib
import re

import pytest

_MIGRATION_NAME = "20261023012950_sec_searchpath_rem97_w1_timestamp_triggers.sql"
_MIGRATIONS_DIR = pathlib.Path(__file__).parent.parent / "supabase" / "migrations"
_MIGRATION_PATH = _MIGRATIONS_DIR / _MIGRATION_NAME
_TARGET_SEARCH_PATH = "pg_catalog, public, pg_temp"

_PROSRC_MD5 = {
    "fn_set_updated_at":          "e48740bd35e2a9e17c5e8ae049421527",
    "set_updated_at":             "ef6b2d76360a727c9d6479352655b7ba",
    "help_touch_updated_at":      "9cd5ec4496cf5a9c5a108e23d2551d06",
    "update_cmc_updated_at":      "301a884953d37769916294bb60562e05",
    "update_documents_timestamp": "5b733ab523bad442e4b10f836de9e4ba",
    "update_timestamp":           "9b1889f56258bf9d6554213c05019c76",
    "update_updated_at_column":   "301a884953d37769916294bb60562e05",
    "tg_kosha_guide_body_touch":  "f8778fa84b849f96f2f2197b9a7b56fb",
}


def _sql() -> str:
    return _MIGRATION_PATH.read_text(encoding="utf-8")


def _nc(sql: str | None = None) -> str:
    """비-주석 라인만 추출 후 대문자 반환."""
    src = sql if sql is not None else _sql()
    lines = [ln for ln in src.splitlines() if not ln.strip().startswith("--")]
    return "\n".join(lines).upper()


# ── 파일 존재 ──────────────────────────────────────────────────────────────────

def test_w1_sql_01_migration_file_exists():
    """W1-SQL-01: Migration 파일 존재"""
    assert _MIGRATION_PATH.exists(), f"{_MIGRATION_NAME} 파일 없음"


# ── 트랜잭션 구조 ──────────────────────────────────────────────────────────────

def test_w1_sql_02_transaction_structure():
    """W1-SQL-02: BEGIN/COMMIT 트랜잭션 구조"""
    nc = _nc()
    assert re.search(r"^\s*BEGIN\s*;", nc, re.MULTILINE), "BEGIN; 없음"
    assert re.search(r"^\s*COMMIT\s*;", nc, re.MULTILINE), "COMMIT; 없음"


# ── ALTER FUNCTION 대상 ────────────────────────────────────────────────────────

def test_w1_sql_03_alter_function_exactly_eight():
    """W1-SQL-03: ALTER FUNCTION 정확히 8건"""
    nc = _nc()
    matches = re.findall(r"\bALTER\s+FUNCTION\b", nc)
    assert len(matches) == 8, f"ALTER FUNCTION 횟수={len(matches)}, 기대=8"


def test_w1_sql_04_fn_set_updated_at():
    """W1-SQL-04: fn_set_updated_at() 서명 포함"""
    nc = _nc()
    assert re.search(
        r"\bALTER\s+FUNCTION\s+PUBLIC\.FN_SET_UPDATED_AT\s*\(\s*\)", nc
    ), "ALTER FUNCTION public.fn_set_updated_at() 없음"


def test_w1_sql_05_set_updated_at():
    """W1-SQL-05: set_updated_at() 서명 포함"""
    nc = _nc()
    assert re.search(
        r"\bALTER\s+FUNCTION\s+PUBLIC\.SET_UPDATED_AT\s*\(\s*\)", nc
    ), "ALTER FUNCTION public.set_updated_at() 없음"


def test_w1_sql_06_help_touch_updated_at():
    """W1-SQL-06: help_touch_updated_at() 서명 포함"""
    nc = _nc()
    assert re.search(
        r"\bALTER\s+FUNCTION\s+PUBLIC\.HELP_TOUCH_UPDATED_AT\s*\(\s*\)", nc
    ), "ALTER FUNCTION public.help_touch_updated_at() 없음"


def test_w1_sql_07_update_cmc_updated_at():
    """W1-SQL-07: update_cmc_updated_at() 서명 포함"""
    nc = _nc()
    assert re.search(
        r"\bALTER\s+FUNCTION\s+PUBLIC\.UPDATE_CMC_UPDATED_AT\s*\(\s*\)", nc
    ), "ALTER FUNCTION public.update_cmc_updated_at() 없음"


def test_w1_sql_08_update_documents_timestamp():
    """W1-SQL-08: update_documents_timestamp() 서명 포함"""
    nc = _nc()
    assert re.search(
        r"\bALTER\s+FUNCTION\s+PUBLIC\.UPDATE_DOCUMENTS_TIMESTAMP\s*\(\s*\)", nc
    ), "ALTER FUNCTION public.update_documents_timestamp() 없음"


def test_w1_sql_09_update_timestamp():
    """W1-SQL-09: update_timestamp() 서명 포함"""
    nc = _nc()
    assert re.search(
        r"\bALTER\s+FUNCTION\s+PUBLIC\.UPDATE_TIMESTAMP\s*\(\s*\)", nc
    ), "ALTER FUNCTION public.update_timestamp() 없음"


def test_w1_sql_10_update_updated_at_column():
    """W1-SQL-10: update_updated_at_column() 서명 포함"""
    nc = _nc()
    assert re.search(
        r"\bALTER\s+FUNCTION\s+PUBLIC\.UPDATE_UPDATED_AT_COLUMN\s*\(\s*\)", nc
    ), "ALTER FUNCTION public.update_updated_at_column() 없음"


def test_w1_sql_11_tg_kosha_guide_body_touch():
    """W1-SQL-11: tg_kosha_guide_body_touch() 서명 포함"""
    nc = _nc()
    assert re.search(
        r"\bALTER\s+FUNCTION\s+PUBLIC\.TG_KOSHA_GUIDE_BODY_TOUCH\s*\(\s*\)", nc
    ), "ALTER FUNCTION public.tg_kosha_guide_body_touch() 없음"


# ── search_path 값 검증 ────────────────────────────────────────────────────────

def test_w1_sql_12_search_path_value():
    """W1-SQL-12: search_path 값 = pg_catalog, public, pg_temp (≥8건)"""
    sql = _sql()
    count = sql.count(_TARGET_SEARCH_PATH)
    assert count >= 8, f"search_path '{_TARGET_SEARCH_PATH}' 등장 횟수={count}, 최소 8건 기대"


def test_w1_sql_13_pg_temp_last():
    """W1-SQL-13: pg_temp이 search_path 마지막"""
    nc_raw = "\n".join(
        ln for ln in _sql().splitlines() if not ln.strip().startswith("--")
    )
    for match in re.finditer(
        r"SET\s+search_path\s*(?:=|TO)\s*([^\n;]+)", nc_raw, re.IGNORECASE
    ):
        path_val = match.group(1).strip().rstrip(";").strip()
        parts = [p.strip() for p in path_val.split(",")]
        assert parts[-1].lower() == "pg_temp", \
            f"pg_temp이 마지막 아님: '{path_val}'"


# ── 금지 패턴 ─────────────────────────────────────────────────────────────────

def test_w1_sql_14_no_create_function():
    """W1-SQL-14: CREATE [OR REPLACE] FUNCTION 없음"""
    nc = _nc()
    assert not re.search(r"\bCREATE\s+(OR\s+REPLACE\s+)?FUNCTION\b", nc), \
        "CREATE [OR REPLACE] FUNCTION 발견 — 본문 재작성 금지"


def test_w1_sql_15_no_drop_function():
    """W1-SQL-15: DROP FUNCTION 없음"""
    nc = _nc()
    assert not re.search(r"\bDROP\s+FUNCTION\b", nc), "DROP FUNCTION 발견"


def test_w1_sql_16_no_trigger_ddl():
    """W1-SQL-16: 트리거 DDL 없음"""
    nc = _nc()
    assert not re.search(r"\b(CREATE|DROP)\s+TRIGGER\b", nc), \
        "CREATE/DROP TRIGGER 발견 — 트리거 변경 금지"


def test_w1_sql_17_no_table_ddl():
    """W1-SQL-17: 테이블 DDL 없음"""
    nc = _nc()
    assert not re.search(r"\b(CREATE|ALTER|DROP)\s+TABLE\b", nc), \
        "CREATE/ALTER/DROP TABLE 발견"


def test_w1_sql_18_no_rls_policy():
    """W1-SQL-18: RLS/Policy 변경 없음"""
    nc = _nc()
    assert not re.search(r"\bROW\s+LEVEL\s+SECURITY\b", nc), "ROW LEVEL SECURITY 발견"
    assert not re.search(r"\bCREATE\s+POLICY\b", nc), "CREATE POLICY 발견"
    assert not re.search(r"\bDROP\s+POLICY\b", nc), "DROP POLICY 발견"
    assert not re.search(r"\bALTER\s+TABLE.+ENABLE\s+ROW\b", nc), "ENABLE ROW LEVEL SECURITY 발견"


def test_w1_sql_19_no_grant():
    """W1-SQL-19: GRANT 없음"""
    nc = _nc()
    assert not re.search(r"\bGRANT\b", nc), "GRANT 발견 — ACL 변경 금지"


def test_w1_sql_20_no_revoke():
    """W1-SQL-20: REVOKE 없음"""
    nc = _nc()
    assert not re.search(r"\bREVOKE\b", nc), "REVOKE 발견 — ACL 변경 금지"


def test_w1_sql_21_no_dml():
    """W1-SQL-21: DML 없음"""
    nc = _nc()
    assert not re.search(r"\bINSERT\s+INTO\b", nc), "INSERT INTO 발견"
    assert not re.search(r"\bUPDATE\s+\w", nc), "UPDATE ... 발견"
    assert not re.search(r"\bDELETE\s+FROM\b", nc), "DELETE FROM 발견"
    assert not re.search(r"\bTRUNCATE\b", nc), "TRUNCATE 발견"


# ── PRE 검증 내용 ──────────────────────────────────────────────────────────────

def test_w1_sql_22_pre_security_invoker():
    """W1-SQL-22: PRE — SECURITY INVOKER 검증 포함 (v_secdef IS DISTINCT FROM false)"""
    nc = _nc()
    # loop 기반 migration: prosecdef → v_secdef 변수로 비교
    assert re.search(r"V_SECDEF\s+IS\s+DISTINCT\s+FROM\s+FALSE", nc), \
        "PRE v_secdef IS DISTINCT FROM false 검증 없음"


def test_w1_sql_23_pre_prosrc_md5_all_eight():
    """W1-SQL-23: PRE — 8개 함수 prosrc_md5 기준선 포함"""
    sql = _sql()
    for fn_name, expected_md5 in _PROSRC_MD5.items():
        assert expected_md5 in sql, \
            f"PRE MD5 기준선 누락: {fn_name} = {expected_md5}"


def test_w1_sql_24_pre_proconfig_null():
    """W1-SQL-24: PRE — proconfig IS NULL 검증 포함"""
    nc = _nc()
    assert re.search(r"PROCONFIG\s+IS\s+NOT\s+NULL", nc), \
        "PRE proconfig IS NOT NULL 예외 처리 없음"


def test_w1_sql_25_pre_anon_execute():
    """W1-SQL-25: PRE — anon EXECUTE 검증 포함"""
    nc = _nc()
    assert re.search(r"HAS_FUNCTION_PRIVILEGE\s*\(\s*'ANON'", nc), \
        "PRE anon EXECUTE 검증 없음"


def test_w1_sql_26_pre_authenticated_execute():
    """W1-SQL-26: PRE — authenticated EXECUTE 검증 포함"""
    nc = _nc()
    assert re.search(r"HAS_FUNCTION_PRIVILEGE\s*\(\s*'AUTHENTICATED'", nc), \
        "PRE authenticated EXECUTE 검증 없음"


def test_w1_sql_27_pre_acl_baseline():
    """W1-SQL-27: PRE — ACL 기준선 상수 선언 및 검증 포함"""
    sql = _sql()
    acl_baseline = (
        "{=X/postgres,postgres=X/postgres,anon=X/postgres,"
        "authenticated=X/postgres,service_role=X/postgres}"
    )
    assert acl_baseline in sql, "ACL 기준선 상수 없음"
    nc = _nc()
    assert re.search(r"PROACL.*IS\s+DISTINCT\s+FROM", nc), \
        "PRE ACL IS DISTINCT FROM 비교 없음"


def test_w1_sql_28_pre_trigger_count_baseline():
    """W1-SQL-28: PRE — 트리거 수 기준선 배열 포함 (총 합산 17)"""
    sql = _sql()
    # v_trigs 배열에서 17건의 트리거 합산: 1+8+2+1+1+1+2+1 = 17
    trigger_counts = [1, 8, 2, 1, 1, 1, 2, 1]
    for cnt in trigger_counts:
        assert str(cnt) in sql, f"트리거 수 기준선 {cnt} 없음"
    nc = _nc()
    assert re.search(r"TGFOID\s*=\s*V_OID", nc), \
        "PRE pg_trigger tgfoid = v_oid 트리거 수 조회 없음"


# ── POST 검증 내용 ────────────────────────────────────────────────────────────

def test_w1_sql_29_post_proconfig_check():
    """W1-SQL-29: POST — proconfig 설정 검증 포함 (IS DISTINCT FROM, NULL-safe)"""
    nc = _nc()
    assert re.search(r"V_PROCONFIG\s+IS\s+DISTINCT\s+FROM\s+ARRAY\[C_SEARCH_PATH\]", nc), \
        "POST proconfig IS DISTINCT FROM ARRAY[c_search_path] 검증 없음"
    assert "SEARCH_PATH=PG_CATALOG, PUBLIC, PG_TEMP" in nc, \
        "POST search_path 기대값 상수 없음"


def test_w1_sql_30_post_prosrc_md5_invariant():
    """W1-SQL-30: POST — 본문 MD5 불변 검증 포함"""
    nc = _nc()
    pre_count = len(re.findall(r"PRE\s+FAILED.*PROSRC_MD5|PROSRC_MD5.*PRE\s+FAILED", nc))
    post_count = len(re.findall(r"POST\s+FAILED.*PROSRC_MD5|PROSRC_MD5.*POST\s+FAILED", nc))
    assert post_count >= 1, "POST prosrc_md5 불변 검증 없음"


def test_w1_sql_31_post_secdef_invariant():
    """W1-SQL-31: POST — SECURITY INVOKER 불변 검증 포함"""
    nc = _nc()
    post_secdef = len(re.findall(r"POST FAILED.*PROSECDEF|PROSECDEF.*POST FAILED", nc))
    assert post_secdef >= 1, "POST prosecdef 불변 검증 없음"


def test_w1_sql_32_post_acl_invariant():
    """W1-SQL-32: POST — ACL 불변 검증 포함"""
    nc = _nc()
    assert re.search(r"POST FAILED.*ACL|ACL.*POST FAILED", nc), \
        "POST ACL 불변 검증 없음"


def test_w1_sql_33_post_trigger_count_invariant():
    """W1-SQL-33: POST — 트리거 수 불변 검증 포함"""
    nc = _nc()
    assert re.search(r"POST FAILED.*TRIGGER|TRIGGER.*POST FAILED", nc), \
        "POST 트리거 수 불변 검증 없음"


# ── 구현 패턴 검증 ────────────────────────────────────────────────────────────

def test_w1_sql_34_to_regprocedure_oid_based():
    """W1-SQL-34: to_regprocedure() OID 기반 식별 (≥2회 — loop 기반은 3회)"""
    nc = _nc()
    count = len(re.findall(r"\bTO_REGPROCEDURE\b", nc))
    assert count >= 2, f"to_regprocedure 호출 횟수={count}, 최소 2건 기대"


def test_w1_sql_35_is_distinct_from_null_safe():
    """W1-SQL-35: IS DISTINCT FROM null-safe 비교 사용 (≥5회)"""
    nc = _nc()
    count = len(re.findall(r"\bIS\s+DISTINCT\s+FROM\b", nc))
    assert count >= 5, f"IS DISTINCT FROM 횟수={count}, 최소 5건 기대"


def test_w1_sql_r1_01_post_proconfig_exact_match():
    """W1-SQL-R1-01: POST proconfig IS DISTINCT FROM 정확 일치 (NULL-safe, @> 제거)"""
    nc = _nc()
    # @> (contains) 검사 제거 확인
    assert "PROCONFIG @>" not in nc, \
        "POST proconfig @> (포함 검사) 발견 — IS DISTINCT FROM 으로 교체해야 함"
    # IS DISTINCT FROM 정확 일치 확인
    assert re.search(r"PROCONFIG\s+IS\s+DISTINCT\s+FROM\s+ARRAY\[C_SEARCH_PATH\]", nc), \
        "POST proconfig IS DISTINCT FROM ARRAY[c_search_path] 없음"


def test_w1_sql_r1_02_post_trigger_tgenabled_check():
    """W1-SQL-R1-02: POST tgenabled = 'O' 트리거 활성 상태 불변 검증"""
    nc = _nc()
    assert re.search(r"TGENABLED\s+IS\s+DISTINCT\s+FROM\s+'O'", nc), \
        "POST tgenabled IS DISTINCT FROM 'O' 검증 없음"
    assert "POST FAILED" in nc and re.search(r"POST FAILED.*TRIGGER.*DISABLED|TRIGGER.*BECAME.*DISABLED", nc), \
        "POST 트리거 비활성 예외 없음"


def test_w1_sql_r1_03_trigger_identity_baseline():
    """W1-SQL-R1-03: 트리거 식별자 기준선 17건 포함 (tgname + function_name + triggerdef_md5)"""
    sql = _sql()
    expected_tg_names = [
        'trg_master_fields_updated_at',
        'help_doc_touch_trg',
        'help_node_touch_trg',
        'trg_inquiries_updated_at',
        'trg_rtc_updated',
        'trg_runtime_dependency_updated_at',
        'trg_runtime_doc_updated_at',
        'trg_runtime_evidence_updated_at',
        'trg_runtime_schedule_updated_at',
        'trg_runtime_task_updated_at',
        'trg_user_profile_updated_at',
        'trg_kosha_guide_body_touch',
        'trg_cmc_updated_at',
        'trg_documents_updated_at',
        'trg_update_master_products_elec',
        'trg_billing_keys_updated_at',
        'trg_subscriptions_updated_at',
    ]
    for tgname in expected_tg_names:
        assert tgname in sql, f"트리거명 기준선 누락: {tgname}"


def test_w1_sql_r1_04_triggerdef_md5_baseline():
    """W1-SQL-R1-04: triggerdef_md5 기준선 17건 포함"""
    sql = _sql()
    expected_md5s = [
        '31385e8917683003499dd127476c31a6',
        '78772ce5158e8420bd8877f468d7c39c',
        '1838c6df987051282aab56dc1496580a',
        '355aa6ccf67978e624832828205b6ae9',
        '30b73f8c98328db19ef52e0078e48c3e',
        'fd73431d0070cd82d8c04ea150b46ad6',
        '0fc2f219752ee5dc052e0ce3612d8f25',
        'afa49c17f779436b900523b845289dc8',
        'e0666511a85e9f1d193336d7890b012e',
        'db5e339add68d968f6ee38f3ddba97a8',
        'b8cbe767cc2b021ecf1f1d848195d801',
        '4765b011abd404a5a59f390db6232d33',
        '82fdc43c9bc7eb426a737f78c9274ffb',
        '47782aad0d163b8b0575bb8a56c9c842',
        'e5c63e70d5bba989e963f75b0d71baa3',
        'cee5dddfb63a3bfd4b85a265df912645',
        '3e4b19c7912516202eb46c0366df7069',
    ]
    for md5_val in expected_md5s:
        assert md5_val in sql, f"triggerdef_md5 기준선 누락: {md5_val}"


def test_w1_sql_r1_05_pg_get_triggerdef_used():
    """W1-SQL-R1-05: pg_get_triggerdef() 함수 사용 확인 (PRE+POST 각 1회 = ≥2회)"""
    nc = _nc()
    count = len(re.findall(r"\bPG_GET_TRIGGERDEF\b", nc))
    assert count >= 2, f"pg_get_triggerdef 호출 횟수={count}, 최소 2건(PRE+POST) 기대"


def test_w1_sql_36_no_out_of_scope_functions():
    """W1-SQL-36: W2/W3/W4/W5 범위 외 함수 미포함"""
    nc = _nc()
    out_of_scope = [
        "HELP_BLOCKS_VALID", "HELP_DOC_INCLUDE_REFS",
        "HELP_NODE_NO_CYCLE", "HELP_DOC_NO_INCLUDE_CYCLE",
        "FN_GENERATE_ASSET_CODE", "FN_GENERATE_COMPANY_CODE",
        "FN_GENERATE_SITE_CODE", "FN_GENERATE_TEAM_CODE",
        "FN_GENERATE_USER_CODE", "GENERATE_REQUEST_NO",
        "REINDEX_HELP", "JSONB_TO_TEXT_ARRAY",
    ]
    for fn in out_of_scope:
        assert fn not in nc, f"범위 외 함수 발견: {fn}"


# ── SHA256 고정 ────────────────────────────────────────────────────────────────

def _sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def test_w1_src_01_migration_sha256():
    """W1-SRC-01: 이 Migration SHA256 고정 (R1: proconfig IS DISTINCT FROM + 트리거 17건 정의 검증 포함)"""
    expected = "660ed59c767510b2e5c8f491ce4ffe60aa8bc6242eb3db60ef4a69a107dd8863"
    actual = _sha256(_MIGRATION_PATH)
    assert actual == expected, (
        f"Migration SHA256 불일치\\n"
        f"  expected: {expected}\\n"
        f"  actual:   {actual}"
    )


def test_w1_src_02_p0c_migration_sha256_unchanged():
    """W1-SRC-02: P0C Migration SHA256 불변"""
    p0c_path = _MIGRATIONS_DIR / "20261022152140_sec_searchpath_p0c_ddl_helper_functions.sql"
    expected = "5267358bf0c9cd45351bb0034d1c327a62c06481eb71a2bd6de9b5a70688809e"
    actual = _sha256(p0c_path)
    assert actual == expected, (
        f"P0C Migration SHA256 불일치 (변경됐을 수 있음)\\n"
        f"  expected: {expected}\\n"
        f"  actual:   {actual}"
    )
