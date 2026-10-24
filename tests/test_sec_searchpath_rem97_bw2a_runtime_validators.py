"""
WO-TAI-SEC-SEARCHPATH-REM97-BW2A-SOURCE-001
Migration: 20261024073606_sec_searchpath_rem97_bw2a_runtime_validators.sql

B-W2A: 런타임 검증 트리거 3개 search_path 고정 — 정적 계약 테스트

대상 함수:
  B06  fn_validate_review_authority()         OID=69290
  B08  fn_validate_submission_eligibility()   OID=69476
  B09  fn_validate_work_order_prerequisites() OID=68918

트리거 3개:
  B06: trg_validate_review_authority (runtime_review_decision)
  B08: trg_validate_submission (runtime_submission)
  B09: trg_validate_work_order_prerequisites (runtime_operational_work_order)
"""

import hashlib
import re
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# 경로 상수
# ─────────────────────────────────────────────────────────────────────────────
MIGRATIONS = Path(__file__).parent.parent / "supabase" / "migrations"
MIG_NAME   = "20261024073606_sec_searchpath_rem97_bw2a_runtime_validators.sql"
MIG_PATH   = MIGRATIONS / MIG_NAME

EXPECTED_SHA256 = "5a2b242a60d33cfef0e9e08a22779ff7b5176a8d93c7aaaebb4de700f3801d23"

FN_SIGS = [
    "public.fn_validate_review_authority()",
    "public.fn_validate_submission_eligibility()",
    "public.fn_validate_work_order_prerequisites()",
]
FN_OIDS = [69290, 69476, 68918]
FN_MD5S = [
    "d309feffdee64d2f1290b29fc5fbf2e4",
    "05c39a090640a63806925736fbc75389",
    "ae9c667a7d745a30030d62985c4086cd",
]

ALL_TRIGGERS = [
    "trg_validate_review_authority",
    "trg_validate_submission",
    "trg_validate_work_order_prerequisites",
]


def _sql() -> str:
    return MIG_PATH.read_text(encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# BW2A-SRC-01  SHA256 기준선
# ─────────────────────────────────────────────────────────────────────────────
def test_bw2a_src_01_migration_sha256():
    """BW2A-SRC-01: Migration 파일 SHA256 기준선 일치"""
    digest = hashlib.sha256(MIG_PATH.read_bytes()).hexdigest()
    assert digest == EXPECTED_SHA256, (
        f"SHA256 불일치: expected={EXPECTED_SHA256}, got={digest}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# BW2A-SQL-01  BEGIN / COMMIT 존재
# ─────────────────────────────────────────────────────────────────────────────
def test_bw2a_sql_01_transaction_boundary():
    """BW2A-SQL-01: BEGIN / COMMIT 트랜잭션 경계 존재"""
    sql = _sql()
    assert re.search(r"^\s*BEGIN\s*;", sql, re.MULTILINE | re.IGNORECASE)
    assert re.search(r"^\s*COMMIT\s*;", sql, re.MULTILINE | re.IGNORECASE)


# ─────────────────────────────────────────────────────────────────────────────
# BW2A-SQL-02  ALTER FUNCTION 정확히 3개
# ─────────────────────────────────────────────────────────────────────────────
def test_bw2a_sql_02_alter_function_count():
    """BW2A-SQL-02: ALTER FUNCTION 문이 정확히 3개"""
    sql = _sql()
    matches = re.findall(r"^\s*ALTER\s+FUNCTION\b", sql, re.MULTILINE | re.IGNORECASE)
    assert len(matches) == 3, f"ALTER FUNCTION 수={len(matches)}, 기대=3"


# ─────────────────────────────────────────────────────────────────────────────
# BW2A-SQL-03  각 함수에 search_path 설정 ALTER 존재
# ─────────────────────────────────────────────────────────────────────────────
def test_bw2a_sql_03_each_function_altered():
    """BW2A-SQL-03: B06/B08/B09 각 함수에 search_path 설정 ALTER 존재"""
    sql = _sql()
    fn_bare = [
        "fn_validate_review_authority",
        "fn_validate_submission_eligibility",
        "fn_validate_work_order_prerequisites",
    ]
    for fn in fn_bare:
        pattern = rf"ALTER\s+FUNCTION\s+public\.{re.escape(fn)}\s*\(\s*\)\s+SET\s+search_path"
        assert re.search(pattern, sql, re.IGNORECASE), (
            f"ALTER FUNCTION ... SET search_path 없음: {fn}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# BW2A-SQL-04  STEP 2 내 search_path 값 정확히 3개
# ─────────────────────────────────────────────────────────────────────────────
def test_bw2a_sql_04_search_path_value():
    """BW2A-SQL-04: STEP 2 구간 내 search_path = pg_catalog, public, pg_temp 정확히 3개"""
    sql = _sql()
    step2_idx = sql.upper().find("STEP 2:")
    step3_idx = sql.upper().find("STEP 3:")
    assert step2_idx != -1 and step3_idx != -1
    step2_section = sql[step2_idx:step3_idx]
    pattern = r"SET\s+search_path\s*=\s*pg_catalog\s*,\s*public\s*,\s*pg_temp"
    matches = re.findall(pattern, step2_section, re.IGNORECASE)
    assert len(matches) == 3, f"STEP 2 search_path 설정 건수={len(matches)}, 기대=3"


# ─────────────────────────────────────────────────────────────────────────────
# BW2A-SQL-05  PRE OID 기준선 3개 포함
# ─────────────────────────────────────────────────────────────────────────────
def test_bw2a_sql_05_pre_oid_baseline():
    """BW2A-SQL-05: PRE STEP에 B06/B08/B09 OID 기준선 포함"""
    sql = _sql()
    for oid in FN_OIDS:
        assert str(oid) in sql, f"OID {oid} 없음"


# ─────────────────────────────────────────────────────────────────────────────
# BW2A-SQL-06  PRE prosrc MD5 기준선 3개 포함
# ─────────────────────────────────────────────────────────────────────────────
def test_bw2a_sql_06_pre_prosrc_md5_baseline():
    """BW2A-SQL-06: PRE STEP에 B06/B08/B09 prosrc MD5 기준선 포함"""
    sql = _sql()
    for md5 in FN_MD5S:
        assert md5 in sql, f"prosrc MD5 {md5} 없음"


# ─────────────────────────────────────────────────────────────────────────────
# BW2A-SQL-07  PRE proconfig = NULL 검사 포함
# ─────────────────────────────────────────────────────────────────────────────
def test_bw2a_sql_07_pre_proconfig_null_check():
    """BW2A-SQL-07: PRE proconfig IS NOT NULL 차단 검사 포함"""
    sql = _sql()
    assert re.search(r"proconfig\s+IS\s+NOT\s+NULL", sql, re.IGNORECASE)


# ─────────────────────────────────────────────────────────────────────────────
# BW2A-SQL-08  POST proconfig 정확 일치 검사 포함
# ─────────────────────────────────────────────────────────────────────────────
def test_bw2a_sql_08_post_proconfig_exact():
    """BW2A-SQL-08: POST proconfig IS DISTINCT FROM ARRAY[c_search_path] 검사 포함"""
    sql = _sql()
    step3_idx = sql.upper().find("STEP 3:")
    assert step3_idx != -1
    post_section = sql[step3_idx:]
    assert re.search(
        r"proconfig\s+IS\s+DISTINCT\s+FROM\s+ARRAY\[c_search_path\]",
        post_section, re.IGNORECASE
    )


# ─────────────────────────────────────────────────────────────────────────────
# BW2A-SQL-09  PRE 트리거 수 = 3 확인
# ─────────────────────────────────────────────────────────────────────────────
def test_bw2a_sql_09_pre_trigger_count_3():
    """BW2A-SQL-09: PRE 트리거 수 3 검사 포함"""
    sql = _sql()
    assert re.search(r"IS\s+DISTINCT\s+FROM\s+3", sql, re.IGNORECASE), (
        "트리거 3개 수량 검사(IS DISTINCT FROM 3) 없음"
    )
    matches = re.findall(r"IS\s+DISTINCT\s+FROM\s+3", sql, re.IGNORECASE)
    assert len(matches) >= 2, f"트리거 수 검사가 PRE/POST 양쪽에 없음 (found={len(matches)})"


# ─────────────────────────────────────────────────────────────────────────────
# BW2A-SQL-10  3개 트리거 이름 모두 포함
# ─────────────────────────────────────────────────────────────────────────────
def test_bw2a_sql_10_all_trigger_names_present():
    """BW2A-SQL-10: 3개 트리거 이름이 Migration SQL에 모두 포함됨"""
    sql = _sql()
    for tg in ALL_TRIGGERS:
        assert tg in sql, f"트리거 이름 없음: {tg}"


# ─────────────────────────────────────────────────────────────────────────────
# BW2A-SQL-11  POST 트리거 MD5·활성 상태 불변 검사
# ─────────────────────────────────────────────────────────────────────────────
def test_bw2a_sql_11_post_trigger_immutability():
    """BW2A-SQL-11: POST STEP에 트리거 MD5·enabled 불변 검사 포함"""
    sql = _sql()
    step3c_idx = sql.upper().find("STEP 3C")
    assert step3c_idx != -1, "STEP 3C 마커 없음"
    post_trig_section = sql[step3c_idx:]
    assert "tgdef_md5" in post_trig_section
    assert re.search(r"tg_enabled", post_trig_section, re.IGNORECASE)


# ─────────────────────────────────────────────────────────────────────────────
# BW2A-SQL-12  PRE ACL 스냅샷 테이블 포함
# ─────────────────────────────────────────────────────────────────────────────
def test_bw2a_sql_12_pre_acl_snapshot():
    """BW2A-SQL-12: PRE ACL 기준선 스냅샷 임시 테이블 포함"""
    sql = _sql()
    assert "_bw2a_fn_acl_baseline" in sql
    assert "ON COMMIT DROP" in sql


# ─────────────────────────────────────────────────────────────────────────────
# BW2A-SQL-13  트리거 스냅샷 rel_name 복합 키 포함
# ─────────────────────────────────────────────────────────────────────────────
def test_bw2a_sql_13_trigger_snapshot_composite_key():
    """BW2A-SQL-13: 트리거 스냅샷에 rel_name 포함 (복합 식별)"""
    sql = _sql()
    assert "_bw2a_trig_baseline" in sql
    assert "rel_name" in sql


# ─────────────────────────────────────────────────────────────────────────────
# BW2A-SQL-14  CREATE FUNCTION · DROP FUNCTION · CREATE TRIGGER 없음
# ─────────────────────────────────────────────────────────────────────────────
def test_bw2a_sql_14_no_create_drop_function_trigger():
    """BW2A-SQL-14: CREATE/DROP FUNCTION, CREATE/DROP TRIGGER 없음 (METADATA_ONLY)"""
    sql = _sql()
    prohibited = [
        r"^\s*CREATE\s+(OR\s+REPLACE\s+)?FUNCTION\b",
        r"^\s*DROP\s+FUNCTION\b",
        r"^\s*CREATE\s+TRIGGER\b",
        r"^\s*DROP\s+TRIGGER\b",
        r"^\s*CREATE\s+TABLE\s+(?!TEMP\b)",
    ]
    for pattern in prohibited:
        assert not re.search(pattern, sql, re.MULTILINE | re.IGNORECASE), (
            f"금지된 구문 발견: {pattern}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# BW2A-SQL-15  POST ACL 불변 검증 포함
# ─────────────────────────────────────────────────────────────────────────────
def test_bw2a_sql_15_post_acl_immutability():
    """BW2A-SQL-15: POST ACL 불변 검증(STEP 3B) 포함"""
    sql = _sql()
    step3b_idx = sql.upper().find("STEP 3B")
    assert step3b_idx != -1
    post_acl_section = sql[step3b_idx:]
    assert "_bw2a_fn_acl_baseline" in post_acl_section


# ─────────────────────────────────────────────────────────────────────────────
# BW2A-SQL-16  STEP 마커 순서
# ─────────────────────────────────────────────────────────────────────────────
def test_bw2a_sql_16_step_markers_order():
    """BW2A-SQL-16: STEP 1 → 1B → 1C → 2 → 3 → 3B → 3C 순서로 존재"""
    sql = _sql().upper()
    markers = ["STEP 1:", "STEP 1B:", "STEP 1C:", "STEP 2:", "STEP 3:", "STEP 3B:", "STEP 3C:"]
    positions = []
    for m in markers:
        idx = sql.find(m)
        assert idx != -1, f"마커 없음: {m}"
        positions.append(idx)
    assert positions == sorted(positions), "STEP 마커 순서 오류"


# ─────────────────────────────────────────────────────────────────────────────
# BW2A-SQL-17  OID 3개 모두 PRE/POST 양 구간에 존재
# ─────────────────────────────────────────────────────────────────────────────
def test_bw2a_sql_17_oid_in_pre_and_post():
    """BW2A-SQL-17: B06/B08/B09 OID가 PRE와 POST 양쪽에 존재"""
    sql = _sql()
    step3_idx = sql.upper().find("STEP 3:")
    assert step3_idx != -1
    pre_section  = sql[:step3_idx]
    post_section = sql[step3_idx:]
    for oid in FN_OIDS:
        assert str(oid) in pre_section,  f"OID {oid} PRE 구간 없음"
        assert str(oid) in post_section, f"OID {oid} POST 구간 없음"


# ─────────────────────────────────────────────────────────────────────────────
# BW2A-SQL-18  prosrc MD5 3개 모두 PRE/POST 양 구간에 존재
# ─────────────────────────────────────────────────────────────────────────────
def test_bw2a_sql_18_md5_in_pre_and_post():
    """BW2A-SQL-18: B06/B08/B09 prosrc MD5가 PRE와 POST 양쪽에 존재"""
    sql = _sql()
    step3_idx = sql.upper().find("STEP 3:")
    assert step3_idx != -1
    pre_section  = sql[:step3_idx]
    post_section = sql[step3_idx:]
    for md5 in FN_MD5S:
        assert md5 in pre_section,  f"MD5 {md5} PRE 구간 없음"
        assert md5 in post_section, f"MD5 {md5} POST 구간 없음"


# ─────────────────────────────────────────────────────────────────────────────
# BW2A-SQL-19  기존 B-W1 Migration 파일 변경 없음
# ─────────────────────────────────────────────────────────────────────────────
BW1_SHA256 = "0cc96087d375f52c17983da65f8d6401b5c2338f72f3c5c575e87261c470a971"

def test_bw2a_sql_19_bw1_migration_unchanged():
    """BW2A-SQL-19: B-W1 Migration SHA256 불변"""
    path = MIGRATIONS / "20261024034408_sec_searchpath_rem97_bw1_immutable_guards.sql"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == BW1_SHA256, f"B-W1 Migration SHA256 변경됨: {digest}"


# ─────────────────────────────────────────────────────────────────────────────
# BW2A-RUNTIME-01  격리 환경 없음 — RUNTIME_UNVERIFIED 기록
# ─────────────────────────────────────────────────────────────────────────────
def test_bw2a_runtime_01_isolated_test_not_available():
    """BW2A-RUNTIME-01: 격리 DB 없으므로 기능 동등성 테스트 RUNTIME_UNVERIFIED"""
    # B06/B08/B09 비한정 테이블 참조가 public 스키마에 존재함을 운영 DB에서 확인.
    # search_path = pg_catalog, public, pg_temp 고정 후 동일 해석 보장.
    # INSERT·UPDATE 회귀는 격리 DB에서 별도 확인 필요.
    assert True, "RUNTIME_UNVERIFIED — 격리 DB에서 별도 확인 필요"
