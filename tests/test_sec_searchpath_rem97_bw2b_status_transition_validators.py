"""
WO-TAI-SEC-SEARCHPATH-REM97-BW2B-SOURCE-001
B-W2B 상태 전이 검증 트리거 함수 2개 search_path 고정 — 정적 계약 검증

FUNCTIONS : fn_validate_inspection_reviewer (B05, OID=69146)
            fn_validate_reviewer_not_assignee (B07, OID=68962)
TRIGGERS  : trg_validate_inspection_reviewer (runtime_inspection_review)
            trg_validate_reviewer (runtime_work_order_review)
ISOLATED_TESTS : BLOCKED (격리 DB 없음 — 기능검증 미실행)
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
    / "20261024094500_sec_searchpath_rem97_bw2b_status_transition_validators.sql"
)

BW2A_MIGRATION_PATH = (
    REPO_ROOT
    / "supabase"
    / "migrations"
    / "20261024073606_sec_searchpath_rem97_bw2a_runtime_validators.sql"
)

EXPECTED_SHA256 = (
    "c9598ab60537698c8ff58b64b94deebb959ebe0521b2fe11f6a9c03b787fc02e"
)

BW2A_EXPECTED_SHA256 = (
    "5a2b242a60d33cfef0e9e08a22779ff7b5176a8d93c7aaaebb4de700f3801d23"
)

FN_SIGS = [
    "public.fn_validate_inspection_reviewer()",
    "public.fn_validate_reviewer_not_assignee()",
]

FN_OIDS = [69146, 68962]

FN_MD5S = [
    "d11c6e83fc4105683304bfed9679ba47",
    "2b7fbd47bb00b04b5e52e5a177ba8e97",
]

ALL_TRIGGERS = [
    "trg_validate_inspection_reviewer",
    "trg_validate_reviewer",
]

TRIGGER_TABLES = {
    "trg_validate_inspection_reviewer": "runtime_inspection_review",
    "trg_validate_reviewer": "runtime_work_order_review",
}

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


# ─── BW2B-SRC: 소스 파일 무결성 ──────────────────────────────────────────────
def test_bw2b_src_01_migration_sha256():
    """Migration 파일 SHA256이 승인된 기준값과 일치해야 한다."""
    digest = hashlib.sha256(MIGRATION_PATH.read_bytes()).hexdigest()
    assert digest == EXPECTED_SHA256, (
        f"Migration SHA256 mismatch.\n  expected: {EXPECTED_SHA256}\n  got:      {digest}"
    )


# ─── BW2B-SQL: Migration SQL 구조 검증 ───────────────────────────────────────
def test_bw2b_sql_01_transaction_boundary(sql: str):
    """Migration은 BEGIN/COMMIT으로 감싸여야 한다."""
    assert re.search(r"^\s*BEGIN\s*;", sql, re.MULTILINE), "BEGIN; not found"
    assert re.search(r"^\s*COMMIT\s*;", sql, re.MULTILINE), "COMMIT; not found"


def test_bw2b_sql_02_alter_function_count(step2_sql: str):
    """STEP 2에서 ALTER FUNCTION이 정확히 2회여야 한다."""
    matches = re.findall(
        r"ALTER\s+FUNCTION\s+public\.",
        step2_sql,
        re.IGNORECASE,
    )
    assert len(matches) == 2, f"Expected 2 ALTER FUNCTION in STEP 2, got {len(matches)}"


def test_bw2b_sql_03_each_function_altered(step2_sql: str):
    """STEP 2에서 B05·B07 각 함수가 ALTER 대상에 포함되어야 한다."""
    for fn in [
        "fn_validate_inspection_reviewer",
        "fn_validate_reviewer_not_assignee",
    ]:
        assert fn in step2_sql, f"Function {fn} not found in STEP 2"


def test_bw2b_sql_04_search_path_value(step2_sql: str):
    """STEP 2 ALTER FUNCTION 2개 모두 search_path=pg_catalog, public, pg_temp이어야 한다."""
    matches = re.findall(
        r"SET\s+search_path\s*=\s*pg_catalog\s*,\s*public\s*,\s*pg_temp",
        step2_sql,
        re.IGNORECASE,
    )
    assert len(matches) == 2, (
        f"Expected 2 SET search_path in STEP 2, got {len(matches)}"
    )


def test_bw2b_sql_05_pre_oid_baseline(sql: str):
    """STEP 1 PRE 블록에 승인된 OID 2개가 모두 존재해야 한다."""
    for oid in FN_OIDS:
        assert str(oid) in sql, f"OID {oid} not found in migration"


def test_bw2b_sql_06_pre_prosrc_md5_baseline(sql: str):
    """STEP 1 PRE 블록에 승인된 prosrc MD5 2개가 모두 존재해야 한다."""
    for md5 in FN_MD5S:
        assert md5 in sql, f"prosrc MD5 {md5} not found in migration"


def test_bw2b_sql_07_pre_proconfig_null_check(sql: str):
    """STEP 1에서 proconfig IS NOT NULL을 예외로 잡는 PRE 검증이 있어야 한다."""
    assert "proconfig IS NOT NULL" in sql, (
        "PRE proconfig=NULL guard not found"
    )


def test_bw2b_sql_08_post_proconfig_exact(sql: str):
    """STEP 3에서 proconfig IS DISTINCT FROM ARRAY[c_search_path] 검증이 있어야 한다."""
    assert "IS DISTINCT FROM ARRAY[c_search_path]" in sql, (
        "POST proconfig exact-match check not found"
    )


def test_bw2b_sql_09_pre_trigger_count_2(sql: str):
    """STEP 1C에서 트리거 수 2개를 검증하는 PRE 블록이 있어야 한다."""
    assert "expected 2 triggers for B05/B07" in sql, (
        "PRE trigger count=2 guard not found"
    )


def test_bw2b_sql_10_all_trigger_names_present(sql: str):
    """Migration에 B05·B07 트리거 이름이 모두 포함되어야 한다."""
    for tg in ALL_TRIGGERS:
        assert tg in sql, f"Trigger name {tg} not found in migration"


def test_bw2b_sql_11_post_trigger_immutability(sql: str):
    """STEP 3C에서 트리거 수·MD5·활성 상태 불변 검증이 있어야 한다."""
    assert "trigger count changed" in sql, "POST trigger count check not found"
    assert "definition changed" in sql, "POST trigger MD5 check not found"
    assert "enabled state changed" in sql, "POST trigger enabled check not found"


def test_bw2b_sql_12_pre_acl_snapshot(sql: str):
    """STEP 1B에서 _bw2b_fn_acl_baseline 동적 스냅샷이 있어야 한다."""
    assert "_bw2b_fn_acl_baseline" in sql, "_bw2b_fn_acl_baseline temp table not found"
    assert "ON COMMIT DROP" in sql, "ON COMMIT DROP not found"
    assert "ACL baseline captured % rows, expected 2" in sql, (
        "PRE ACL count=2 guard not found"
    )


def test_bw2b_sql_13_trigger_snapshot_composite_key(sql: str):
    """STEP 1C에서 _bw2b_trig_baseline이 (tg_name, rel_name) 복합 PK를 가져야 한다."""
    assert "_bw2b_trig_baseline" in sql, "_bw2b_trig_baseline temp table not found"
    assert "PRIMARY KEY (tg_name, rel_name)" in sql, (
        "Composite PK (tg_name, rel_name) not found"
    )


def test_bw2b_sql_14_no_create_drop_function_trigger(sql: str):
    """함수 본문 재생성(CREATE OR REPLACE FUNCTION) 또는 DROP TRIGGER가 없어야 한다."""
    assert not re.search(r"CREATE\s+OR\s+REPLACE\s+FUNCTION", sql, re.IGNORECASE), (
        "CREATE OR REPLACE FUNCTION found — body must not change"
    )
    assert not re.search(r"DROP\s+TRIGGER", sql, re.IGNORECASE), (
        "DROP TRIGGER found — triggers must not be modified"
    )


def test_bw2b_sql_15_post_acl_immutability(sql: str):
    """STEP 3B에서 ACL 불변 검증 로직이 있어야 한다."""
    assert "ACL changed for OID" in sql, "POST ACL immutability check not found"


def test_bw2b_sql_16_step_markers_order(sql: str):
    """STEP 1 → 1B → 1C → 2 → 3 → 3B → 3C 순서가 보장되어야 한다."""
    positions = {
        "STEP 1:": sql.index("-- STEP 1:"),
        "STEP 1B:": sql.index("-- STEP 1B:"),
        "STEP 1C:": sql.index("-- STEP 1C:"),
        "STEP 2:": sql.index("-- STEP 2:"),
        "STEP 3:": sql.index("-- STEP 3:"),
        "STEP 3B:": sql.index("-- STEP 3B:"),
        "STEP 3C:": sql.index("-- STEP 3C:"),
    }
    ordered = list(positions.values())
    assert ordered == sorted(ordered), (
        f"STEP markers not in expected order: {positions}"
    )


def test_bw2b_sql_17_oid_in_pre_and_post(sql: str):
    """OID 2개가 PRE(STEP 1) 및 POST(STEP 3) 양쪽 모두에 있어야 한다."""
    step1_idx = sql.index("-- STEP 1:")
    step2_idx = sql.index("-- STEP 2:")
    step3_idx = sql.index("-- STEP 3:")
    commit_idx = sql.rindex("COMMIT;")

    pre_section = sql[step1_idx:step2_idx]
    post_section = sql[step3_idx:commit_idx]

    for oid in FN_OIDS:
        assert str(oid) in pre_section, f"OID {oid} not in PRE section"
        assert str(oid) in post_section, f"OID {oid} not in POST section"


def test_bw2b_sql_18_md5_in_pre_and_post(sql: str):
    """prosrc MD5 2개가 PRE 및 POST 양쪽 모두에 있어야 한다."""
    step1_idx = sql.index("-- STEP 1:")
    step2_idx = sql.index("-- STEP 2:")
    step3_idx = sql.index("-- STEP 3:")
    commit_idx = sql.rindex("COMMIT;")

    pre_section = sql[step1_idx:step2_idx]
    post_section = sql[step3_idx:commit_idx]

    for md5 in FN_MD5S:
        assert md5 in pre_section, f"MD5 {md5} not in PRE section"
        assert md5 in post_section, f"MD5 {md5} not in POST section"


def test_bw2b_sql_19_bw2a_migration_unchanged():
    """BW2A Migration 파일이 승인된 SHA256 그대로 유지되어야 한다."""
    assert BW2A_MIGRATION_PATH.exists(), "BW2A migration file missing"
    digest = hashlib.sha256(BW2A_MIGRATION_PATH.read_bytes()).hexdigest()
    assert digest == BW2A_EXPECTED_SHA256, (
        f"BW2A migration SHA256 changed!\n  expected: {BW2A_EXPECTED_SHA256}\n  got:      {digest}"
    )


# ─── BW2B-RUNTIME: 격리 기능검증 — BLOCKED ───────────────────────────────────
@pytest.mark.skip(
    reason=(
        "ISOLATED_TESTS=BLOCKED: 격리 DB 없음. "
        "fn_validate_inspection_reviewer / fn_validate_reviewer_not_assignee "
        "상태 전이 기능검증은 격리 DB 확보 후 별도 WO에서 실행."
    )
)
def test_bw2b_runtime_01_isolated_functional_tests_blocked():
    """
    격리 기능검증 시나리오 (미실행 — BLOCKED):

    B05 fn_validate_inspection_reviewer:
      - 검사자 본인이 reviewer이면 RAISE EXCEPTION 차단
      - 다른 reviewer의 APPROVE/REJECT/REOPEN/ESCALATE 처리 허용
      - runtime_inspection_session.session_status·review_status·updated_at 변화 확인
      - 예외 발생 시 상태 변경이 남지 않는지 확인

    B07 fn_validate_reviewer_not_assignee:
      - 배정 작업자 본인이 reviewer이면 RAISE EXCEPTION 차단
      - 다른 reviewer 처리 시 runtime_operational_work_order.work_status 변경 확인
      - updated_at 변화 확인
      - 예외 발생 시 업무 상태 불변 확인
    """
    pytest.fail("This test must not run without an isolated DB.")
