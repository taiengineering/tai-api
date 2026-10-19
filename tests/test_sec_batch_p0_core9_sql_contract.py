"""SEC-BATCH-P0 — WO-TAI-SUPABASE-SEC-BATCH-P0-IMPLEMENT-001 SQL 계약 테스트.

마이그레이션: supabase/migrations/20261020000002_sec_batch_p0_core9_acl_hardening.sql

검증 방식: 정적 SQL 파일 분석 (파일 기반).
격리 DB 실측 테스트(DB_INT)는 TEST_DB_ENVIRONMENT_REQUIRED.

SQL 계약 테스트 목록:
  P0-SQL-01  마이그레이션 파일 존재
  P0-SQL-02  트랜잭션 (BEGIN / COMMIT) 존재
  P0-SQL-03  DO $$ 사전 조건 블록 존재
  P0-SQL-04  사전 조건 — Group A 5개 테이블 이름 모두 검사
  P0-SQL-05  사전 조건 — Group B 3개 테이블 이름 모두 검사
  P0-SQL-06  사전 조건 — v_payments_list View 검사
  P0-SQL-07  사전 조건 — 예상 외 정책 차단 (payments / users / companies)
  P0-SQL-08  Group A — ENABLE ROW LEVEL SECURITY 5개 모두 존재
  P0-SQL-09  Group A — REVOKE ALL FROM anon/authenticated/PUBLIC 5개 테이블 모두 존재
  P0-SQL-10  Group B — 제거 정책 15개 모두 DROP POLICY (IF EXISTS 없음, 명시 DROP)
  P0-SQL-11  Group B — REVOKE ALL FROM anon/authenticated/PUBLIC 3개 테이블 모두 존재
  P0-SQL-12  Group C — REVOKE ON v_payments_list 존재
  P0-SQL-13  무조건 허용 정책 재생성 없음 (USING(true) 신규 생성 금지)
  P0-SQL-14  service_role_full 정책 DROP 없음 (유지 검증)
  P0-SQL-15  사후 조건 블록 존재 (P0-POST 키워드)
  P0-SQL-16  데이터 변경 없음 (DELETE / TRUNCATE / DROP TABLE 없음)
  P0-SQL-17  9개 외 객체 변경 없음 (ALTER TABLE 대상 9개만)
  P0-SQL-18  CASCADE 미사용
"""
from __future__ import annotations

import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_MIGRATION = (
    _ROOT
    / "supabase"
    / "migrations"
    / "20261020000002_sec_batch_p0_core9_acl_hardening.sql"
)

GROUP_A_TABLES = [
    "refunds",
    "worker_attendance",
    "safety_committee_attendees",
    "work_permits",
    "ra_participation",
]
GROUP_B_TABLES = ["payments", "users", "companies"]
GROUP_C_VIEW = "v_payments_list"
ALL_9 = GROUP_A_TABLES + GROUP_B_TABLES + [GROUP_C_VIEW]

# Group B 제거 대상 정책 15개
GROUP_B_DROP_POLICIES = [
    "anon_delete_payments",
    "anon_insert_payments",
    "anon_select_payments",
    "anon_update_payments",
    "authenticated_all_payments",
    "anon_delete_users",
    "anon_insert_users",
    "anon_select_users",
    "anon_update_users",
    "authenticated_all_users",
    "anon_delete_companies",
    "anon_insert_companies",
    "anon_select_companies",
    "anon_update_companies",
    "authenticated_all_companies",
]


def _sql() -> str:
    return _MIGRATION.read_text(encoding="utf-8")


def _sql_upper() -> str:
    return _sql().upper()


# ════════════════════════════════════════════════════════════════
# P0-SQL-01: 파일 존재
# ════════════════════════════════════════════════════════════════

def test_P0_SQL_01_migration_file_exists():
    assert _MIGRATION.exists(), f"마이그레이션 파일 없음: {_MIGRATION}"


# ════════════════════════════════════════════════════════════════
# P0-SQL-02: BEGIN / COMMIT 트랜잭션
# ════════════════════════════════════════════════════════════════

def test_P0_SQL_02_transaction_wraps():
    sql_u = _sql_upper()
    assert re.search(r"^\s*BEGIN\s*;", sql_u, re.MULTILINE), "BEGIN; 없음"
    assert re.search(r"^\s*COMMIT\s*;", sql_u, re.MULTILINE), "COMMIT; 없음"


# ════════════════════════════════════════════════════════════════
# P0-SQL-03: DO $$ 사전 조건 블록
# ════════════════════════════════════════════════════════════════

def test_P0_SQL_03_do_block_exists():
    assert "DO $$" in _sql(), "DO $$ 블록 없음"
    assert "P0-PRE FAILED" in _sql(), "사전 조건 RAISE EXCEPTION 없음"


# ════════════════════════════════════════════════════════════════
# P0-SQL-04: Group A 5개 테이블 사전 조건 검사
# ════════════════════════════════════════════════════════════════

def test_P0_SQL_04_pre_condition_group_a_tables():
    sql = _sql()
    missing = [t for t in GROUP_A_TABLES if t not in sql]
    assert not missing, f"사전 조건에서 Group-A 테이블 이름 누락: {missing}"


# ════════════════════════════════════════════════════════════════
# P0-SQL-05: Group B 3개 테이블 사전 조건 검사
# ════════════════════════════════════════════════════════════════

def test_P0_SQL_05_pre_condition_group_b_tables():
    sql = _sql()
    missing = [t for t in GROUP_B_TABLES if t not in sql]
    assert not missing, f"사전 조건에서 Group-B 테이블 이름 누락: {missing}"


# ════════════════════════════════════════════════════════════════
# P0-SQL-06: v_payments_list View 사전 조건 검사
# ════════════════════════════════════════════════════════════════

def test_P0_SQL_06_pre_condition_view():
    assert GROUP_C_VIEW in _sql(), f"사전 조건에서 {GROUP_C_VIEW} 누락"


# ════════════════════════════════════════════════════════════════
# P0-SQL-07: 예상 외 정책 차단 (P0-PRE FAILED: Unexpected policies)
# ════════════════════════════════════════════════════════════════

def test_P0_SQL_07_unexpected_policy_guard():
    sql = _sql()
    for table in GROUP_B_TABLES:
        assert f"Unexpected policies on {table}" in sql, (
            f"{table}의 예상 외 정책 차단 구문 없음"
        )


# ════════════════════════════════════════════════════════════════
# P0-SQL-08: Group A — ENABLE ROW LEVEL SECURITY 5개
# ════════════════════════════════════════════════════════════════

def test_P0_SQL_08_group_a_enable_rls():
    sql_u = _sql_upper()
    missing = []
    for table in GROUP_A_TABLES:
        pattern = rf"ALTER\s+TABLE\s+PUBLIC\.{table.upper()}\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY"
        if not re.search(pattern, sql_u):
            missing.append(table)
    assert not missing, f"ENABLE ROW LEVEL SECURITY 누락: {missing}"


# ════════════════════════════════════════════════════════════════
# P0-SQL-09: Group A — REVOKE ALL 5개 테이블
# ════════════════════════════════════════════════════════════════

def test_P0_SQL_09_group_a_revoke_all():
    sql_u = _sql_upper()
    missing = []
    for table in GROUP_A_TABLES:
        pattern = (
            rf"REVOKE\s+ALL\s+PRIVILEGES\s+ON\s+TABLE\s+PUBLIC\.{table.upper()}"
            rf"\s+FROM\s+PUBLIC,\s*ANON,\s*AUTHENTICATED"
        )
        if not re.search(pattern, sql_u):
            missing.append(table)
    assert not missing, f"Group-A REVOKE ALL 누락: {missing}"


# ════════════════════════════════════════════════════════════════
# P0-SQL-10: Group B — DROP POLICY 15개 모두 존재
# ════════════════════════════════════════════════════════════════

def test_P0_SQL_10_group_b_drop_policies_all():
    sql_u = _sql_upper()
    missing = []
    for policy in GROUP_B_DROP_POLICIES:
        # DROP POLICY <name> ON ...  (IF EXISTS 없이 명시 DROP)
        pattern = rf"DROP\s+POLICY\s+{policy.upper()}\s+ON\s+PUBLIC\."
        if not re.search(pattern, sql_u):
            missing.append(policy)
    assert not missing, f"DROP POLICY 누락: {missing}"


# ════════════════════════════════════════════════════════════════
# P0-SQL-11: Group B — REVOKE ALL 3개 테이블
# ════════════════════════════════════════════════════════════════

def test_P0_SQL_11_group_b_revoke_all():
    sql_u = _sql_upper()
    missing = []
    for table in GROUP_B_TABLES:
        pattern = (
            rf"REVOKE\s+ALL\s+PRIVILEGES\s+ON\s+TABLE\s+PUBLIC\.{table.upper()}"
            rf"\s+FROM\s+PUBLIC,\s*ANON,\s*AUTHENTICATED"
        )
        if not re.search(pattern, sql_u):
            missing.append(table)
    assert not missing, f"Group-B REVOKE ALL 누락: {missing}"


# ════════════════════════════════════════════════════════════════
# P0-SQL-12: Group C — v_payments_list REVOKE
# ════════════════════════════════════════════════════════════════

def test_P0_SQL_12_group_c_view_revoke():
    sql_u = _sql_upper()
    assert re.search(
        r"REVOKE\s+ALL\s+PRIVILEGES\s+ON\s+TABLE\s+PUBLIC\.V_PAYMENTS_LIST"
        r"\s+FROM\s+PUBLIC,\s*ANON,\s*AUTHENTICATED",
        sql_u,
    ), "v_payments_list REVOKE 구문 없음"


# ════════════════════════════════════════════════════════════════
# P0-SQL-13: 무조건 허용 정책 재생성 없음
# ════════════════════════════════════════════════════════════════

def test_P0_SQL_13_no_using_true_policy_recreation():
    sql_u = _sql_upper()
    # CREATE POLICY 구문이 없어야 함
    assert not re.search(r"CREATE\s+POLICY", sql_u), (
        "CREATE POLICY 구문 발견 — 무조건 허용 정책 신규 생성 금지"
    )


# ════════════════════════════════════════════════════════════════
# P0-SQL-14: service_role_full 정책 DROP 없음
# ════════════════════════════════════════════════════════════════

def test_P0_SQL_14_service_role_full_not_dropped():
    sql_u = _sql_upper()
    assert not re.search(r"DROP\s+POLICY\s+SERVICE_ROLE_FULL", sql_u), (
        "service_role_full 정책을 DROP하면 서버 접근이 차단됨"
    )


# ════════════════════════════════════════════════════════════════
# P0-SQL-15: 사후 조건 블록 (P0-POST 키워드)
# ════════════════════════════════════════════════════════════════

def test_P0_SQL_15_post_condition_block():
    sql = _sql()
    assert "P0-POST FAILED" in sql, "사후 조건 검증 블록 없음"
    assert "P0-COMPLETE" in sql, "P0-COMPLETE 완료 NOTICE 없음"


# ════════════════════════════════════════════════════════════════
# P0-SQL-16: 데이터 변경 없음
# ════════════════════════════════════════════════════════════════

def test_P0_SQL_16_no_data_modification():
    sql_u = _sql_upper()
    # DELETE FROM (테이블 데이터 삭제) 없음
    assert not re.search(r"\bDELETE\s+FROM\b", sql_u), "DELETE FROM 발견 — 데이터 변경 금지"
    # TRUNCATE TABLE 없음
    assert not re.search(r"\bTRUNCATE\s+TABLE\b", sql_u), "TRUNCATE TABLE 발견"
    # DROP TABLE 없음
    assert not re.search(r"\bDROP\s+TABLE\b", sql_u), "DROP TABLE 발견"


# ════════════════════════════════════════════════════════════════
# P0-SQL-17: ALTER TABLE 대상이 승인된 9개 테이블만
# ════════════════════════════════════════════════════════════════

def test_P0_SQL_17_alter_table_only_approved_targets():
    sql_u = _sql_upper()
    approved_upper = {t.upper() for t in GROUP_A_TABLES}
    # ALTER TABLE 구문에서 테이블명 추출
    for m in re.finditer(
        r"ALTER\s+TABLE\s+(?:PUBLIC\.)?(\w+)\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY",
        sql_u,
    ):
        tname = m.group(1)
        assert tname in approved_upper, (
            f"ALTER TABLE ENABLE RLS 대상 '{tname}'이 승인 목록(Group-A)에 없음"
        )


# ════════════════════════════════════════════════════════════════
# P0-SQL-18: CASCADE 미사용
# ════════════════════════════════════════════════════════════════

def test_P0_SQL_18_no_cascade():
    sql_u = _sql_upper()
    assert not re.search(r"\bCASCADE\b", sql_u), "CASCADE 사용 발견 — 금지 사항"
