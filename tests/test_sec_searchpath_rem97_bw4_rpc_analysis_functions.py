"""
WO-TAI-SEC-SEARCHPATH-REM97-BW4-SOURCE-001
B-W4 RPC·분석 함수 8개 search_path 고정 — 정적 계약 검증

FUNCTIONS : get_diagrams_for_diagnosis  (B17, OID=18566)
            get_equip_count_by_process  (B18, OID=18567)
            get_precompiled_factory_ids (B19, OID=70200)
            search_help                 (B20, OID=243821)
            search_help_count           (B21, OID=243822)
            search_safety_materials     (B22, OID=223735)
            stats_customer_sites        (B23, OID=242472)
            stats_diagnosis_funnel      (B24, OID=242471)
TRIGGERS  : 없음 (전원 SELECT 전용 RPC)
ISOLATED_TESTS : 불필요 (외부 DML 없음 — 기능검증 Gate 없음)
"""

import hashlib
import re
import pytest
from pathlib import Path

# ─── 경로 및 상수 ────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent

MIGRATION_PATH = (
    REPO_ROOT
    / "supabase"
    / "migrations"
    / "20261024103000_sec_searchpath_rem97_bw4_rpc_analysis_functions.sql"
)

BW3B_MIGRATION_PATH = (
    REPO_ROOT
    / "supabase"
    / "migrations"
    / "20261024101500_sec_searchpath_rem97_bw3b_sync_triggers.sql"
)

EXPECTED_SHA256 = (
    "9428e68fd144389c5e90d30323f87926a18858829adf4b52109b855d97f161ae"
)

BW3B_EXPECTED_SHA256 = (
    "92ec79cca4b2d0eaeef9793f9920cb2f538a9ab8559ec883be93dfd9a0df6644"
)

FN_SIGS = [
    "public.get_diagrams_for_diagnosis(text, text[])",
    "public.get_equip_count_by_process(text[])",
    "public.get_precompiled_factory_ids()",
    "public.search_help(text, text[], text, text, integer, text[], text, integer, integer)",
    "public.search_help_count(text, text[], text, integer, text[], text)",
    "public.search_safety_materials(text, text, text, integer, integer)",
    "public.stats_customer_sites(date, date, text)",
    "public.stats_diagnosis_funnel(date, date, text)",
]

FN_OIDS = [18566, 18567, 70200, 243821, 243822, 223735, 242472, 242471]

FN_MD5S = [
    "5e66840f274e21e02ee20c5ed4d9db0d",
    "a22fb0bc8c91cbd82eeb65a059a982d4",
    "fa38689f8ad0f1fd6b904df01237bbde",
    "736962e539ec4be659ef6712f57d05a0",
    "b5f39c3c761e54f88c4d451d8454c1ab",
    "349e30be44996f011cea340aecbeb093",
    "4ee2731ed5cf2b66d6757ed41bff6fc9",
    "49351eb5a856c2e0c19485dd03e9d629",
]

EXPECTED_SEARCH_PATH = "search_path=pg_catalog, public, pg_temp"


# ─── 픽스처 ───────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def sql() -> str:
    return MIGRATION_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def step2_sql(sql: str) -> str:
    """STEP 2 섹션만 추출 (STEP 3 이전까지)."""
    step2_idx = sql.index("-- STEP 2:")
    step3_idx = sql.index("-- STEP 3:")
    return sql[step2_idx:step3_idx]


# ─── BW4-SRC: 소스 파일 무결성 ───────────────────────────────────────────────
def test_bw4_src_01_migration_sha256():
    """Migration 파일 SHA256이 승인된 기준값과 일치해야 한다."""
    digest = hashlib.sha256(MIGRATION_PATH.read_bytes()).hexdigest()
    assert digest == EXPECTED_SHA256, (
        f"Migration SHA256 mismatch.\n  expected: {EXPECTED_SHA256}\n  got:      {digest}"
    )


# ─── BW4-SQL: Migration SQL 구조 검증 ────────────────────────────────────────
def test_bw4_sql_01_transaction_boundary(sql: str):
    """Migration은 BEGIN/COMMIT으로 감싸여야 한다."""
    assert re.search(r"^\s*BEGIN\s*;", sql, re.MULTILINE), "BEGIN; not found"
    assert re.search(r"^\s*COMMIT\s*;", sql, re.MULTILINE), "COMMIT; not found"


def test_bw4_sql_02_alter_function_count(step2_sql: str):
    """STEP 2에서 ALTER FUNCTION이 정확히 8회여야 한다."""
    matches = re.findall(
        r"ALTER\s+FUNCTION\s+public\.",
        step2_sql,
        re.IGNORECASE,
    )
    assert len(matches) == 8, f"Expected 8 ALTER FUNCTION in STEP 2, got {len(matches)}"


def test_bw4_sql_03_each_function_altered(step2_sql: str):
    """STEP 2에서 B17-B24 각 함수가 ALTER 대상에 포함되어야 한다."""
    for fn in [
        "get_diagrams_for_diagnosis",
        "get_equip_count_by_process",
        "get_precompiled_factory_ids",
        "search_help",
        "search_help_count",
        "search_safety_materials",
        "stats_customer_sites",
        "stats_diagnosis_funnel",
    ]:
        assert fn in step2_sql, f"Function {fn} not found in STEP 2"


def test_bw4_sql_04_search_path_value(step2_sql: str):
    """STEP 2 ALTER FUNCTION 8개 모두 search_path=pg_catalog, public, pg_temp이어야 한다."""
    matches = re.findall(
        r"SET\s+search_path\s*=\s*pg_catalog\s*,\s*public\s*,\s*pg_temp",
        step2_sql,
        re.IGNORECASE,
    )
    assert len(matches) == 8, (
        f"Expected 8 SET search_path in STEP 2, got {len(matches)}"
    )


def test_bw4_sql_05_pre_oid_baseline(sql: str):
    """STEP 1 PRE 블록에 승인된 OID 8개가 모두 존재해야 한다."""
    for oid in FN_OIDS:
        assert str(oid) in sql, f"OID {oid} not found in migration"


def test_bw4_sql_06_pre_prosrc_md5_baseline(sql: str):
    """STEP 1 PRE 블록에 승인된 prosrc MD5 8개가 모두 존재해야 한다."""
    for md5 in FN_MD5S:
        assert md5 in sql, f"prosrc MD5 {md5} not found in migration"


def test_bw4_sql_07_pre_proconfig_null_check(sql: str):
    """STEP 1에서 proconfig IS NOT NULL을 예외로 잡는 PRE 검증이 있어야 한다."""
    assert "proconfig IS NOT NULL" in sql, "PRE proconfig=NULL guard not found"


def test_bw4_sql_08_post_proconfig_exact(sql: str):
    """STEP 3에서 proconfig IS DISTINCT FROM ARRAY[c_search_path] 검증이 있어야 한다."""
    assert "IS DISTINCT FROM ARRAY[c_search_path]" in sql, (
        "POST proconfig exact-match check not found"
    )


def test_bw4_sql_09_pre_acl_snapshot(sql: str):
    """STEP 1B에서 _bw4_fn_acl_baseline 동적 스냅샷이 있어야 한다."""
    assert "_bw4_fn_acl_baseline" in sql, "_bw4_fn_acl_baseline temp table not found"
    assert "ON COMMIT DROP" in sql, "ON COMMIT DROP not found"
    assert "ACL baseline captured % rows, expected 8" in sql, (
        "PRE ACL count=8 guard not found"
    )


def test_bw4_sql_10_no_create_drop_function_trigger(sql: str):
    """함수 본문 재생성(CREATE OR REPLACE FUNCTION) 또는 DROP TRIGGER가 없어야 한다."""
    assert not re.search(r"CREATE\s+OR\s+REPLACE\s+FUNCTION", sql, re.IGNORECASE), (
        "CREATE OR REPLACE FUNCTION found — body must not change"
    )
    assert not re.search(r"DROP\s+TRIGGER", sql, re.IGNORECASE), (
        "DROP TRIGGER found — triggers must not exist for BW4"
    )


def test_bw4_sql_11_post_acl_immutability(sql: str):
    """STEP 3B에서 ACL 불변 검증 로직이 있어야 한다."""
    assert "ACL changed for OID" in sql, "POST ACL immutability check not found"


def test_bw4_sql_12_step_markers_order(sql: str):
    """STEP 1 → 1B → 2 → 3 → 3B 순서가 보장되어야 한다 (트리거 없으므로 1C·3C 없음)."""
    positions = {
        "STEP 1:": sql.index("-- STEP 1:"),
        "STEP 1B:": sql.index("-- STEP 1B:"),
        "STEP 2:": sql.index("-- STEP 2:"),
        "STEP 3:": sql.index("-- STEP 3:"),
        "STEP 3B:": sql.index("-- STEP 3B:"),
    }
    ordered = list(positions.values())
    assert ordered == sorted(ordered), (
        f"STEP markers not in expected order: {positions}"
    )
    assert "-- STEP 1C:" not in sql, "STEP 1C found — BW4 has no triggers"
    assert "-- STEP 3C:" not in sql, "STEP 3C found — BW4 has no triggers"


def test_bw4_sql_13_oid_in_pre_and_post(sql: str):
    """OID 8개가 PRE(STEP 1) 및 POST(STEP 3) 양쪽 모두에 있어야 한다."""
    step1_idx = sql.index("-- STEP 1:")
    step2_idx = sql.index("-- STEP 2:")
    step3_idx = sql.index("-- STEP 3:")
    commit_idx = sql.rindex("COMMIT;")

    pre_section = sql[step1_idx:step2_idx]
    post_section = sql[step3_idx:commit_idx]

    for oid in FN_OIDS:
        assert str(oid) in pre_section, f"OID {oid} not in PRE section"
        assert str(oid) in post_section, f"OID {oid} not in POST section"


def test_bw4_sql_14_md5_in_pre_and_post(sql: str):
    """prosrc MD5 8개가 PRE 및 POST 양쪽 모두에 있어야 한다."""
    step1_idx = sql.index("-- STEP 1:")
    step2_idx = sql.index("-- STEP 2:")
    step3_idx = sql.index("-- STEP 3:")
    commit_idx = sql.rindex("COMMIT;")

    pre_section = sql[step1_idx:step2_idx]
    post_section = sql[step3_idx:commit_idx]

    for md5 in FN_MD5S:
        assert md5 in pre_section, f"MD5 {md5} not in PRE section"
        assert md5 in post_section, f"MD5 {md5} not in POST section"


def test_bw4_sql_15_bw3b_migration_unchanged():
    """BW3B Migration 파일(직전 BASE)이 승인된 SHA256 그대로 유지되어야 한다."""
    assert BW3B_MIGRATION_PATH.exists(), "BW3B migration file missing"
    digest = hashlib.sha256(BW3B_MIGRATION_PATH.read_bytes()).hexdigest()
    assert digest == BW3B_EXPECTED_SHA256, (
        f"BW3B migration SHA256 changed!\n  expected: {BW3B_EXPECTED_SHA256}\n  got:      {digest}"
    )
