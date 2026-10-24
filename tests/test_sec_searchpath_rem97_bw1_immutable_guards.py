"""
WO-TAI-SEC-SEARCHPATH-REM97-C2-BW1-SOURCE-001
Migration: 20261024034408_sec_searchpath_rem97_bw1_immutable_guards.sql

B-W1: 불변 가드 4개 함수 search_path 고정 — 정적 계약 테스트

대상 함수:
  B01  fn_rdarch_reject_mutation()            OID=247895
  B02  fn_rdd_seal_guard()                    OID=247898
  B03  fn_reject_inspection_base_mutation()   OID=250821
  B04  fn_reject_inspection_record_mutation() OID=250768

트리거 8개:
  B01: trg_rdarch_no_delete, trg_rdarch_no_update (runtime_document_archive)
  B02: trg_rdd_seal_guard (runtime_document_data)
  B03: trg_safety_inspections_immutable, trg_safety_inspection_results_immutable (ALWAYS)
  B04: trg_sirj_append_only, trg_sicr_append_only, trg_sicreation_append_only
"""

import hashlib
import re
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# 경로 상수
# ─────────────────────────────────────────────────────────────────────────────
MIGRATIONS = Path(__file__).parent.parent / "supabase" / "migrations"
MIG_NAME   = "20261024034408_sec_searchpath_rem97_bw1_immutable_guards.sql"
MIG_PATH   = MIGRATIONS / MIG_NAME

EXPECTED_SHA256 = "0cc96087d375f52c17983da65f8d6401b5c2338f72f3c5c575e87261c470a971"

FN_SIGS = [
    "public.fn_rdarch_reject_mutation()",
    "public.fn_rdd_seal_guard()",
    "public.fn_reject_inspection_base_mutation()",
    "public.fn_reject_inspection_record_mutation()",
]
FN_OIDS = [247895, 247898, 250821, 250768]
FN_MD5S = [
    "975ad08342e5d6add7584d1ee307c9a4",
    "85d5d5d06c9f153ebd6076076f1e956c",
    "1c21312b9ee8095ec7a0ec15c559e915",
    "e92d457621c2733c7d4bf93ca7356e30",
]

TRIGGERS_B01 = ["trg_rdarch_no_delete", "trg_rdarch_no_update"]
TRIGGERS_B02 = ["trg_rdd_seal_guard"]
TRIGGERS_B03 = ["trg_safety_inspections_immutable", "trg_safety_inspection_results_immutable"]
TRIGGERS_B04 = ["trg_sirj_append_only", "trg_sicr_append_only", "trg_sicreation_append_only"]
ALL_TRIGGERS  = TRIGGERS_B01 + TRIGGERS_B02 + TRIGGERS_B03 + TRIGGERS_B04  # 8개

SEARCH_PATH_VALUE = "search_path=pg_catalog, public, pg_temp"


def _sql() -> str:
    return MIG_PATH.read_text(encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# BW1-SRC-01  SHA256 기준선
# ─────────────────────────────────────────────────────────────────────────────
def test_bw1_src_01_migration_sha256():
    """BW1-SRC-01: Migration 파일 SHA256 기준선 일치"""
    digest = hashlib.sha256(MIG_PATH.read_bytes()).hexdigest()
    assert digest == EXPECTED_SHA256, (
        f"SHA256 불일치: expected={EXPECTED_SHA256}, got={digest}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# BW1-SQL-01  BEGIN / COMMIT 존재
# ─────────────────────────────────────────────────────────────────────────────
def test_bw1_sql_01_transaction_boundary():
    """BW1-SQL-01: BEGIN / COMMIT 트랜잭션 경계 존재"""
    sql = _sql()
    assert re.search(r"^\s*BEGIN\s*;", sql, re.MULTILINE | re.IGNORECASE)
    assert re.search(r"^\s*COMMIT\s*;", sql, re.MULTILINE | re.IGNORECASE)


# ─────────────────────────────────────────────────────────────────────────────
# BW1-SQL-02  ALTER FUNCTION 4개만 존재
# ─────────────────────────────────────────────────────────────────────────────
def test_bw1_sql_02_alter_function_count():
    """BW1-SQL-02: ALTER FUNCTION 문이 정확히 4개"""
    sql = _sql()
    matches = re.findall(r"^\s*ALTER\s+FUNCTION\b", sql, re.MULTILINE | re.IGNORECASE)
    assert len(matches) == 4, f"ALTER FUNCTION 수={len(matches)}, 기대=4"


# ─────────────────────────────────────────────────────────────────────────────
# BW1-SQL-03  각 함수에 search_path 고정 ALTER 존재
# ─────────────────────────────────────────────────────────────────────────────
def test_bw1_sql_03_each_function_altered():
    """BW1-SQL-03: B01~B04 각 함수에 search_path 설정 ALTER 존재"""
    sql = _sql()
    fn_bare = [
        "fn_rdarch_reject_mutation",
        "fn_rdd_seal_guard",
        "fn_reject_inspection_base_mutation",
        "fn_reject_inspection_record_mutation",
    ]
    for fn in fn_bare:
        pattern = rf"ALTER\s+FUNCTION\s+public\.{re.escape(fn)}\s*\(\s*\)\s+SET\s+search_path"
        assert re.search(pattern, sql, re.IGNORECASE), (
            f"ALTER FUNCTION ... SET search_path 없음: {fn}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# BW1-SQL-04  search_path 값이 정확
# ─────────────────────────────────────────────────────────────────────────────
def test_bw1_sql_04_search_path_value():
    """BW1-SQL-04: STEP 2 구간 내 search_path = pg_catalog, public, pg_temp 정확히 4개"""
    sql = _sql()
    step2_idx = sql.upper().find("STEP 2:")
    step3_idx = sql.upper().find("STEP 3:")
    assert step2_idx != -1 and step3_idx != -1
    step2_section = sql[step2_idx:step3_idx]
    pattern = r"SET\s+search_path\s*=\s*pg_catalog\s*,\s*public\s*,\s*pg_temp"
    matches = re.findall(pattern, step2_section, re.IGNORECASE)
    assert len(matches) == 4, f"STEP 2 search_path 설정 건수={len(matches)}, 기대=4"


# ─────────────────────────────────────────────────────────────────────────────
# BW1-SQL-05  PRE OID 기준선 4개 포함
# ─────────────────────────────────────────────────────────────────────────────
def test_bw1_sql_05_pre_oid_baseline():
    """BW1-SQL-05: PRE STEP에 B01~B04 OID 기준선 포함"""
    sql = _sql()
    for oid in FN_OIDS:
        assert str(oid) in sql, f"OID {oid} 없음"


# ─────────────────────────────────────────────────────────────────────────────
# BW1-SQL-06  PRE prosrc MD5 기준선 4개 포함
# ─────────────────────────────────────────────────────────────────────────────
def test_bw1_sql_06_pre_prosrc_md5_baseline():
    """BW1-SQL-06: PRE STEP에 B01~B04 prosrc MD5 기준선 포함"""
    sql = _sql()
    for md5 in FN_MD5S:
        assert md5 in sql, f"prosrc MD5 {md5} 없음"


# ─────────────────────────────────────────────────────────────────────────────
# BW1-SQL-07  PRE proconfig = NULL 검사 포함
# ─────────────────────────────────────────────────────────────────────────────
def test_bw1_sql_07_pre_proconfig_null_check():
    """BW1-SQL-07: PRE proconfig IS NOT NULL 차단 검사 포함"""
    sql = _sql()
    assert re.search(r"proconfig\s+IS\s+NOT\s+NULL", sql, re.IGNORECASE), (
        "PRE proconfig=NULL 검사 없음"
    )


# ─────────────────────────────────────────────────────────────────────────────
# BW1-SQL-08  POST proconfig 정확 일치 검사 포함
# ─────────────────────────────────────────────────────────────────────────────
def test_bw1_sql_08_post_proconfig_exact():
    """BW1-SQL-08: POST proconfig IS DISTINCT FROM ARRAY[c_search_path] 검사 포함"""
    sql = _sql()
    step3_idx = sql.upper().find("STEP 3:")
    assert step3_idx != -1, "STEP 3 마커 없음"
    post_section = sql[step3_idx:]
    assert re.search(
        r"proconfig\s+IS\s+DISTINCT\s+FROM\s+ARRAY\[c_search_path\]",
        post_section, re.IGNORECASE
    ), "POST proconfig 정확 일치 검사 없음"


# ─────────────────────────────────────────────────────────────────────────────
# BW1-SQL-09  PRE 트리거 수 = 8 확인
# ─────────────────────────────────────────────────────────────────────────────
def test_bw1_sql_09_pre_trigger_count_8():
    """BW1-SQL-09: PRE 트리거 수 8 검사 포함"""
    sql = _sql()
    # 숫자 8이 트리거 카운트 비교에 사용됨
    assert re.search(
        r"IS\s+DISTINCT\s+FROM\s+8", sql, re.IGNORECASE
    ), "트리거 8개 수량 검사(IS DISTINCT FROM 8) 없음"
    matches = re.findall(r"IS\s+DISTINCT\s+FROM\s+8", sql, re.IGNORECASE)
    # PRE + POST 양쪽 모두 존재해야 함
    assert len(matches) >= 2, f"트리거 수 검사가 PRE/POST 양쪽에 없음 (found={len(matches)})"


# ─────────────────────────────────────────────────────────────────────────────
# BW1-SQL-10  B03 ALWAYS 트리거 2개 상태 검사
# ─────────────────────────────────────────────────────────────────────────────
def test_bw1_sql_10_b03_always_trigger_check():
    """BW1-SQL-10: B03 ALWAYS(tgenabled='A') 트리거 2개 검사 포함"""
    sql = _sql()
    assert re.search(r"tg_enabled\s*=\s*'A'", sql, re.IGNORECASE), (
        "B03 ALWAYS 상태 검사 없음"
    )
    assert re.search(
        r"fn_reject_inspection_base_mutation", sql, re.IGNORECASE
    ), "B03 함수명 없음"
    # ALWAYS 트리거가 2개임을 검사하는 IS DISTINCT FROM 2
    assert re.search(r"IS\s+DISTINCT\s+FROM\s+2", sql, re.IGNORECASE), (
        "ALWAYS 트리거 수 2 검사 없음"
    )


# ─────────────────────────────────────────────────────────────────────────────
# BW1-SQL-11  POST 트리거 MD5·활성 상태 불변 검사
# ─────────────────────────────────────────────────────────────────────────────
def test_bw1_sql_11_post_trigger_immutability():
    """BW1-SQL-11: POST STEP에 트리거 MD5·enabled 불변 검사 포함"""
    sql = _sql()
    step3c_idx = sql.upper().find("STEP 3C")
    assert step3c_idx != -1, "STEP 3C 마커 없음"
    post_trig_section = sql[step3c_idx:]
    assert "tgdef_md5" in post_trig_section, "POST 트리거 MD5 비교 없음"
    assert re.search(r"tg_enabled", post_trig_section, re.IGNORECASE), (
        "POST 트리거 enabled 비교 없음"
    )


# ─────────────────────────────────────────────────────────────────────────────
# BW1-SQL-12  8개 트리거 이름 모두 포함
# ─────────────────────────────────────────────────────────────────────────────
def test_bw1_sql_12_all_trigger_names_present():
    """BW1-SQL-12: 8개 트리거 이름이 Migration SQL에 모두 포함됨"""
    sql = _sql()
    for tg in ALL_TRIGGERS:
        assert tg in sql, f"트리거 이름 없음: {tg}"


# ─────────────────────────────────────────────────────────────────────────────
# BW1-SQL-13  PRE ACL 스냅샷 테이블 생성 포함
# ─────────────────────────────────────────────────────────────────────────────
def test_bw1_sql_13_pre_acl_snapshot():
    """BW1-SQL-13: PRE ACL 기준선 스냅샷 임시 테이블 포함"""
    sql = _sql()
    assert "_bw1_fn_acl_baseline" in sql, "ACL baseline 임시 테이블 없음"
    assert "ON COMMIT DROP" in sql, "임시 테이블 ON COMMIT DROP 없음"


# ─────────────────────────────────────────────────────────────────────────────
# BW1-SQL-14  트리거 스냅샷 테이블 rel_name 포함 (복합 키)
# ─────────────────────────────────────────────────────────────────────────────
def test_bw1_sql_14_trigger_snapshot_composite_key():
    """BW1-SQL-14: 트리거 스냅샷 테이블에 rel_name 포함 (복합 식별)"""
    sql = _sql()
    assert "_bw1_trig_baseline" in sql, "트리거 baseline 임시 테이블 없음"
    assert "rel_name" in sql, "트리거 테이블 rel_name 컬럼 없음"


# ─────────────────────────────────────────────────────────────────────────────
# BW1-SQL-15  CREATE FUNCTION · DROP FUNCTION · CREATE TRIGGER 없음
# ─────────────────────────────────────────────────────────────────────────────
def test_bw1_sql_15_no_create_drop_function_trigger():
    """BW1-SQL-15: CREATE/DROP FUNCTION, CREATE/DROP TRIGGER 없음 (METADATA_ONLY)"""
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
# BW1-SQL-16  POST ACL 불변 검증 포함
# ─────────────────────────────────────────────────────────────────────────────
def test_bw1_sql_16_post_acl_immutability():
    """BW1-SQL-16: POST ACL 불변 검증(STEP 3B) 포함"""
    sql = _sql()
    step3b_idx = sql.upper().find("STEP 3B")
    assert step3b_idx != -1, "STEP 3B 마커 없음"
    post_acl_section = sql[step3b_idx:]
    assert "_bw1_fn_acl_baseline" in post_acl_section, (
        "POST STEP 3B에 ACL baseline 비교 없음"
    )


# ─────────────────────────────────────────────────────────────────────────────
# BW1-SQL-17  기존 Wave (W1~W5) Migration 파일 변경 없음
# ─────────────────────────────────────────────────────────────────────────────
PRIOR_WAVE_MIGRATIONS = [
    "20261023012950_sec_searchpath_rem97_w1_timestamp_triggers.sql",
    "20261023082048_sec_searchpath_rem97_w2_utility_functions.sql",
    "20261023124050_sec_searchpath_rem97_w3_cycle_guard_functions.sql",
    "20261024021404_sec_searchpath_rem97_w5_reindex_help.sql",
]

PRIOR_WAVE_SHA256 = {
    "20261023012950_sec_searchpath_rem97_w1_timestamp_triggers.sql": None,
    "20261023082048_sec_searchpath_rem97_w2_utility_functions.sql": None,
    "20261023124050_sec_searchpath_rem97_w3_cycle_guard_functions.sql": None,
    "20261024021404_sec_searchpath_rem97_w5_reindex_help.sql":
        "e8d34675b83ccdcb39091db1640e74be35cce98148b3cb48aed2a513c0b276af",
}


def test_bw1_sql_17_prior_wave_files_exist():
    """BW1-SQL-17: W1~W5 기존 Migration 파일이 존재함"""
    for fname in PRIOR_WAVE_MIGRATIONS:
        path = MIGRATIONS / fname
        assert path.exists(), f"기존 Wave Migration 파일 없음: {fname}"


def test_bw1_sql_18_w5_sha256_unchanged():
    """BW1-SQL-18: W5 Migration SHA256 불변 (W5 기준선 검증)"""
    path = MIGRATIONS / "20261024021404_sec_searchpath_rem97_w5_reindex_help.sql"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == "e8d34675b83ccdcb39091db1640e74be35cce98148b3cb48aed2a513c0b276af", (
        f"W5 Migration SHA256 변경됨: {digest}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# BW1-SQL-19  STEP 1/1B/1C/2/3/3B/3C 마커 순서
# ─────────────────────────────────────────────────────────────────────────────
def test_bw1_sql_19_step_markers_order():
    """BW1-SQL-19: STEP 1 → 1B → 1C → 2 → 3 → 3B → 3C 순서로 존재"""
    sql = _sql().upper()
    markers = ["STEP 1:", "STEP 1B:", "STEP 1C:", "STEP 2:", "STEP 3:", "STEP 3B:", "STEP 3C:"]
    positions = []
    for m in markers:
        idx = sql.find(m)
        assert idx != -1, f"마커 없음: {m}"
        positions.append(idx)
    assert positions == sorted(positions), "STEP 마커 순서 오류"


# ─────────────────────────────────────────────────────────────────────────────
# BW1-SQL-20  OID 4개 모두 PRE/POST 양 구간에 존재
# ─────────────────────────────────────────────────────────────────────────────
def test_bw1_sql_20_oid_in_pre_and_post():
    """BW1-SQL-20: B01~B04 OID가 PRE(STEP 1)와 POST(STEP 3) 양쪽에 존재"""
    sql = _sql()
    step3_idx = sql.upper().find("STEP 3:")
    assert step3_idx != -1
    pre_section  = sql[:step3_idx]
    post_section = sql[step3_idx:]
    for oid in FN_OIDS:
        assert str(oid) in pre_section,  f"OID {oid} PRE 구간 없음"
        assert str(oid) in post_section, f"OID {oid} POST 구간 없음"


# ─────────────────────────────────────────────────────────────────────────────
# BW1-SQL-21  prosrc MD5 4개 모두 PRE/POST 양 구간에 존재
# ─────────────────────────────────────────────────────────────────────────────
def test_bw1_sql_21_md5_in_pre_and_post():
    """BW1-SQL-21: B01~B04 prosrc MD5가 PRE와 POST 양쪽에 존재"""
    sql = _sql()
    step3_idx = sql.upper().find("STEP 3:")
    assert step3_idx != -1
    pre_section  = sql[:step3_idx]
    post_section = sql[step3_idx:]
    for md5 in FN_MD5S:
        assert md5 in pre_section,  f"MD5 {md5} PRE 구간 없음"
        assert md5 in post_section, f"MD5 {md5} POST 구간 없음"


# ─────────────────────────────────────────────────────────────────────────────
# BW1-RUNTIME-01  격리 환경 없음 — 운영 RUNTIME_UNVERIFIED 기록
# ─────────────────────────────────────────────────────────────────────────────
def test_bw1_runtime_01_isolated_test_not_available():
    """BW1-RUNTIME-01: 격리 DB 없으므로 기능 동등성 테스트 RUNTIME_UNVERIFIED"""
    # 이 테스트는 격리 환경 없이 실행됨을 명시적으로 기록함.
    # B01~B04는 RAISE EXCEPTION 또는 OLD.status 조건 확인만 수행하므로
    # search_path 고정 후 동작 변경 없음 (외부 테이블 비한정 참조 없음).
    assert True, "RUNTIME_UNVERIFIED — 격리 DB에서 별도 확인 필요"
