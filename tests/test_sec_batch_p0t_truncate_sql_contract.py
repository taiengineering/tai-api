"""SEC-BATCH-P0T — WO-TAI-SUPABASE-SEC-BATCH-P0T-001 SQL 계약 테스트.

마이그레이션: supabase/migrations/20261020000003_sec_batch_p0t_truncate_revoke.sql

검증 방식: 정적 SQL 파일 분석 (파일 기반).
격리 DB 실측 테스트(DB_INT)는 TEST_DB_ENVIRONMENT_REQUIRED.

SQL 계약 테스트 목록:
  P0T-SQL-01  마이그레이션 파일 존재
  P0T-SQL-02  트랜잭션 (BEGIN / COMMIT) 존재
  P0T-SQL-03  DO $$ 블록 존재
  P0T-SQL-04  사전 조건 — P0T-PRE FAILED 키워드
  P0T-SQL-05  사전 조건 — 362 수량 검증 포함
  P0T-SQL-06  사전 조건 — Manifest 해시 d6d190116b9b1579d8570b5cddb8a9fb 포함
  P0T-SQL-07  REVOKE TRUNCATE 구문 존재
  P0T-SQL-08  REVOKE 대상이 anon, authenticated (SELECT/INSERT/UPDATE/DELETE 미포함)
  P0T-SQL-09  사후 조건 — P0T-POST FAILED 키워드
  P0T-SQL-10  사후 조건 — P0T-COMPLETE 키워드
  P0T-SQL-11  ALTER DEFAULT PRIVILEGES REVOKE TRUNCATE 존재 (postgres 기본 권한)
  P0T-SQL-12  supabase_admin DEFAULT_ACL_GAP 주석 존재 (BLOCKED 명시)
  P0T-SQL-13  데이터 변경 없음 (DELETE FROM / TRUNCATE TABLE / DROP TABLE 없음)
  P0T-SQL-14  CASCADE 미사용
  P0T-SQL-15  REVOKE ALL 없음 (TRUNCATE만 대상, 범위 초과 금지)
  P0T-SQL-16  service_role 권한 변경 없음
  P0T-SQL-17  format('%I') 동적 식별자 인용 확인
"""
from __future__ import annotations

import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_MIGRATION = (
    _ROOT
    / "supabase"
    / "migrations"
    / "20261020000003_sec_batch_p0t_truncate_revoke.sql"
)

MANIFEST_HASH = "d6d190116b9b1579d8570b5cddb8a9fb"
TARGET_COUNT = 362


def _sql() -> str:
    return _MIGRATION.read_text(encoding="utf-8")


def _sql_upper() -> str:
    return _sql().upper()


# ════════════════════════════════════════════════════════════════
# P0T-SQL-01: 파일 존재
# ════════════════════════════════════════════════════════════════

def test_P0T_SQL_01_migration_file_exists():
    assert _MIGRATION.exists(), f"마이그레이션 파일 없음: {_MIGRATION}"


# ════════════════════════════════════════════════════════════════
# P0T-SQL-02: BEGIN / COMMIT 트랜잭션
# ════════════════════════════════════════════════════════════════

def test_P0T_SQL_02_transaction_wraps():
    sql_u = _sql_upper()
    assert re.search(r"^\s*BEGIN\s*;", sql_u, re.MULTILINE), "BEGIN; 없음"
    assert re.search(r"^\s*COMMIT\s*;", sql_u, re.MULTILINE), "COMMIT; 없음"


# ════════════════════════════════════════════════════════════════
# P0T-SQL-03: DO $$ 블록 존재
# ════════════════════════════════════════════════════════════════

def test_P0T_SQL_03_do_block_exists():
    assert "DO $$" in _sql(), "DO $$ 블록 없음"


# ════════════════════════════════════════════════════════════════
# P0T-SQL-04: 사전 조건 P0T-PRE FAILED 키워드
# ════════════════════════════════════════════════════════════════

def test_P0T_SQL_04_pre_failed_keyword():
    assert "P0T-PRE FAILED" in _sql(), "P0T-PRE FAILED 키워드 없음"


# ════════════════════════════════════════════════════════════════
# P0T-SQL-05: 사전 조건 — 362 수량 검증
# ════════════════════════════════════════════════════════════════

def test_P0T_SQL_05_count_362():
    assert "362" in _sql(), "362 수량 검증 없음"


# ════════════════════════════════════════════════════════════════
# P0T-SQL-06: 사전 조건 — Manifest 해시
# ════════════════════════════════════════════════════════════════

def test_P0T_SQL_06_manifest_hash():
    assert MANIFEST_HASH in _sql(), f"Manifest 해시 {MANIFEST_HASH} 없음"


# ════════════════════════════════════════════════════════════════
# P0T-SQL-07: REVOKE TRUNCATE 구문 존재
# ════════════════════════════════════════════════════════════════

def test_P0T_SQL_07_revoke_truncate_present():
    sql_u = _sql_upper()
    assert re.search(r"REVOKE\s+TRUNCATE", sql_u), "REVOKE TRUNCATE 구문 없음"


# ════════════════════════════════════════════════════════════════
# P0T-SQL-08: REVOKE 대상이 anon, authenticated만 (SELECT/INSERT/UPDATE/DELETE 미포함)
# ════════════════════════════════════════════════════════════════

def test_P0T_SQL_08_revoke_truncate_only_not_select_insert_update_delete():
    sql_u = _sql_upper()
    # REVOKE TRUNCATE ... FROM anon, authenticated 패턴 존재
    assert re.search(r"REVOKE\s+TRUNCATE\b", sql_u), "REVOKE TRUNCATE 없음"
    # REVOKE SELECT / INSERT / UPDATE / DELETE 없음 (범위 초과 금지)
    for priv in ("REVOKE SELECT", "REVOKE INSERT", "REVOKE UPDATE", "REVOKE DELETE"):
        assert priv not in sql_u, f"{priv} 발견 — 이번 범위 외 권한 변경 금지"


# ════════════════════════════════════════════════════════════════
# P0T-SQL-09: 사후 조건 P0T-POST FAILED
# ════════════════════════════════════════════════════════════════

def test_P0T_SQL_09_post_failed_keyword():
    assert "P0T-POST FAILED" in _sql(), "P0T-POST FAILED 키워드 없음"


# ════════════════════════════════════════════════════════════════
# P0T-SQL-10: P0T-COMPLETE 완료 키워드
# ════════════════════════════════════════════════════════════════

def test_P0T_SQL_10_complete_keyword():
    assert "P0T-COMPLETE" in _sql(), "P0T-COMPLETE 키워드 없음"


# ════════════════════════════════════════════════════════════════
# P0T-SQL-11: ALTER DEFAULT PRIVILEGES REVOKE TRUNCATE 존재
# ════════════════════════════════════════════════════════════════

def test_P0T_SQL_11_alter_default_privileges():
    sql_u = _sql_upper()
    assert re.search(
        r"ALTER\s+DEFAULT\s+PRIVILEGES\b.*REVOKE\s+TRUNCATE",
        sql_u,
        re.DOTALL,
    ), "ALTER DEFAULT PRIVILEGES REVOKE TRUNCATE 없음"


# ════════════════════════════════════════════════════════════════
# P0T-SQL-12: supabase_admin DEFAULT_ACL_GAP BLOCKED 주석
# ════════════════════════════════════════════════════════════════

def test_P0T_SQL_12_supabase_admin_blocked_comment():
    sql = _sql()
    assert "DEFAULT_ACL_GAP" in sql, "DEFAULT_ACL_GAP 주석 없음"
    assert "BLOCKED" in sql, "BLOCKED 명시 없음"
    assert "supabase_admin" in sql, "supabase_admin 언급 없음"


# ════════════════════════════════════════════════════════════════
# P0T-SQL-13: 데이터 변경 없음
# ════════════════════════════════════════════════════════════════

def test_P0T_SQL_13_no_data_modification():
    sql_u = _sql_upper()
    assert not re.search(r"\bDELETE\s+FROM\b", sql_u), "DELETE FROM 발견"
    assert not re.search(r"\bTRUNCATE\s+TABLE\b", sql_u), "TRUNCATE TABLE 발견"
    assert not re.search(r"\bDROP\s+TABLE\b", sql_u), "DROP TABLE 발견"


# ════════════════════════════════════════════════════════════════
# P0T-SQL-14: CASCADE 미사용
# ════════════════════════════════════════════════════════════════

def test_P0T_SQL_14_no_cascade():
    sql_u = _sql_upper()
    assert not re.search(r"\bCASCADE\b", sql_u), "CASCADE 사용 발견 — 금지 사항"


# ════════════════════════════════════════════════════════════════
# P0T-SQL-15: REVOKE ALL 없음 (TRUNCATE만 대상)
# ════════════════════════════════════════════════════════════════

def test_P0T_SQL_15_no_revoke_all():
    sql_u = _sql_upper()
    assert not re.search(r"\bREVOKE\s+ALL\b", sql_u), (
        "REVOKE ALL 발견 — 이번 범위는 TRUNCATE만"
    )


# ════════════════════════════════════════════════════════════════
# P0T-SQL-16: service_role 권한 변경 없음
# ════════════════════════════════════════════════════════════════

def test_P0T_SQL_16_service_role_not_revoked():
    sql_u = _sql_upper()
    # REVOKE ... FROM ... SERVICE_ROLE 패턴 없어야 함 (단일 행 검사, 주석 포함 무방)
    # re.DOTALL 미사용: 개행을 넘지 않아야 실행 SQL만 검사
    assert not re.search(r"REVOKE\b[^-\n]*\bFROM\b[^-\n]*\bSERVICE_ROLE\b", sql_u), (
        "service_role 대상 REVOKE 발견 — service_role 권한은 유지해야 함"
    )


# ════════════════════════════════════════════════════════════════
# P0T-SQL-17: format('%I') 동적 식별자 인용
# ════════════════════════════════════════════════════════════════

def test_P0T_SQL_17_format_identifier_quoting():
    sql = _sql()
    assert "format(" in sql, "format() 동적 EXECUTE 없음"
    assert "%I" in sql, "format('%I') 식별자 인용 없음"
